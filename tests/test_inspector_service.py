from datetime import UTC, datetime

import pytest

from discovery_net.inspector import InspectorService
from discovery_net.inspector.models import (
    ConnectionDirection,
    NodeObservation,
    PeerObservation,
)
from discovery_net.inspector.seed import (
    SeedArtifactLedgerReader,
    SeedNodeObservationSource,
    seed_ledger_snapshot,
    seeded_inspector_service,
)
from discovery_net.inspector.sources import ArtifactLedgerUpdate
from discovery_net.knowledge_graph import ArtifactRef
from discovery_net.node import ArtifactLedgerSnapshot
from discovery_net.wire import verify_transaction

NOW = datetime(2026, 8, 26, 20, tzinfo=UTC)


def test_seeded_service_projects_a_valid_committed_graph() -> None:
    # The demo follows the real signed-transaction-to-index path instead of inventing UI data.
    ledger = seed_ledger_snapshot()

    snapshot = seeded_inspector_service().snapshot()

    assert ledger.height == 8
    assert all(verify_transaction(entry.transaction) for entry in ledger.entries)
    assert snapshot.node.chain_id == "discovery-net-demo"
    assert snapshot.node.application_height == ledger.height
    assert snapshot.knowledge_graph.indexed_height == ledger.height
    assert len(snapshot.knowledge_graph.contributions) == 8
    assert len(snapshot.knowledge_graph.relations) == 8
    contribution_refs = {
        contribution.artifact_ref for contribution in snapshot.knowledge_graph.contributions
    }
    assert all(
        relation.from_contribution in contribution_refs
        and relation.to_contribution in contribution_refs
        for relation in snapshot.knowledge_graph.relations
    )


def test_service_redacts_peer_addresses_by_default() -> None:
    # Browser snapshots retain useful network locality without exposing exact peer addresses.
    snapshot = seeded_inspector_service().snapshot()

    assert tuple(peer.observed_address for peer in snapshot.node.peers) == (
        "10.42.x.x",
        "10.42.x.x",
        "192.0.x.x",
        "2001:0db8::/32",
    )


def test_service_can_expose_full_peer_addresses_when_explicitly_configured() -> None:
    # Operators may opt into exact local observations for private debugging environments.
    node = _node(chain_id="test-chain", remote_ip="203.0.113.17")
    service = InspectorService(
        node_source=SeedNodeObservationSource(observation=node),
        ledger_reader=SeedArtifactLedgerReader(
            snapshot=ArtifactLedgerSnapshot(height=0, entries=())
        ),
        redact_peer_ips=False,
        clock=lambda: NOW,
    )

    snapshot = service.snapshot()

    assert snapshot.observed_at == NOW
    assert snapshot.node.peers[0].observed_address == "203.0.113.17"


def test_service_rejects_node_and_ledger_chain_disagreement() -> None:
    # A local view must never combine network observations with another chain's ledger state.
    service = InspectorService(
        node_source=SeedNodeObservationSource(observation=_node(chain_id="another-chain")),
        ledger_reader=SeedArtifactLedgerReader(snapshot=seed_ledger_snapshot()),
    )

    with pytest.raises(ValueError, match="node chain does not match the artifact ledger"):
        service.snapshot()


def test_service_reuses_the_graph_projection_at_an_unchanged_height() -> None:
    # Frequent browser polling does not repeatedly decode an unchanged committed ledger.
    reader = _MutableLedgerReader(seed_ledger_snapshot())
    service = InspectorService(
        node_source=SeedNodeObservationSource(
            observation=_node(chain_id="discovery-net-demo", height=8)
        ),
        ledger_reader=reader,
    )
    first = service.snapshot()
    reader.snapshot = ArtifactLedgerSnapshot(height=8, entries=())

    second = service.snapshot()

    assert second.knowledge_graph == first.knowledge_graph
    assert len(second.knowledge_graph.contributions) == 8
    assert reader.requested_heights == [0, 8]


def test_service_checks_the_node_chain_when_the_ledger_height_is_unchanged() -> None:
    # Cached graph data must not be combined with observations from another chain.
    node_source = _MutableNodeSource(_node(chain_id="discovery-net-demo", height=8))
    service = InspectorService(
        node_source=node_source,
        ledger_reader=_MutableLedgerReader(seed_ledger_snapshot()),
    )
    service.snapshot()
    node_source.observation = _node(chain_id="another-chain", height=8)

    with pytest.raises(ValueError, match="node chain does not match the indexed artifact ledger"):
        service.snapshot()


def test_service_rejects_removal_of_previously_committed_state() -> None:
    # A replaced or truncated ledger cannot silently leave a stale graph marked as current.
    reader = _MutableLedgerReader(seed_ledger_snapshot())
    service = InspectorService(
        node_source=SeedNodeObservationSource(
            observation=_node(chain_id="discovery-net-demo", height=8)
        ),
        ledger_reader=reader,
    )
    service.snapshot()
    reader.snapshot = None

    with pytest.raises(ValueError, match="artifact ledger moved behind the indexed height"):
        service.snapshot()


def test_service_rejects_regression_of_the_committed_height() -> None:
    # A replaced ledger cannot make the locally presented consensus history move backward.
    reader = _MutableLedgerReader(seed_ledger_snapshot())
    service = InspectorService(
        node_source=SeedNodeObservationSource(
            observation=_node(chain_id="discovery-net-demo", height=8)
        ),
        ledger_reader=reader,
    )
    service.snapshot()
    reader.snapshot = ArtifactLedgerSnapshot(height=7, entries=())

    with pytest.raises(ValueError, match="artifact ledger moved behind the indexed height"):
        service.snapshot()


def test_node_snapshot_does_not_read_the_artifact_ledger() -> None:
    # Status polling remains fast and independent from graph synchronization.
    reader = _MutableLedgerReader(seed_ledger_snapshot())
    service = InspectorService(
        node_source=SeedNodeObservationSource(
            observation=_node(chain_id="discovery-net-demo", height=8)
        ),
        ledger_reader=reader,
    )

    snapshot = service.node_snapshot()

    assert snapshot.node.application_height == 8
    assert reader.requested_heights == []


def test_graph_updates_exclude_bodies_and_known_history() -> None:
    # Topology polling returns only metadata committed after the browser cursor.
    service = seeded_inspector_service()

    complete = service.knowledge_graph()
    unchanged = service.knowledge_graph(after_height=complete.indexed_height)

    assert complete.contributions
    assert not hasattr(complete.contributions[0], "body")
    assert unchanged.indexed_height == complete.indexed_height
    assert unchanged.contributions == ()
    assert unchanged.relations == ()


def test_feed_pages_transactions_without_loading_the_entire_history() -> None:
    # Feed pagination preserves atomic transactions and supplies an opaque next cursor.
    service = seeded_inspector_service()

    first = service.feed_page(limit=2)
    assert len(first.transactions) == 2
    assert first.next_before is not None
    before_height, before_index = (int(part) for part in first.next_before.split(":"))
    second = service.feed_page(before=(before_height, before_index), limit=2)

    assert len(second.transactions) == 2
    assert second.transactions[0].height < first.transactions[-1].height


def test_contribution_detail_loads_one_full_body_by_reference() -> None:
    # Detail requests add the body and signature only for the selected contribution.
    service = seeded_inspector_service()
    summary = service.knowledge_graph().contributions[0]

    detail = service.contribution(ArtifactRef(summary.artifact_ref))

    assert detail is not None
    assert detail.artifact_ref == summary.artifact_ref
    assert detail.body
    assert detail.signature


class _MutableLedgerReader:
    def __init__(self, snapshot: ArtifactLedgerSnapshot | None) -> None:
        self.snapshot = snapshot
        self.requested_heights: list[int] = []

    def updates_after(self, height: int) -> ArtifactLedgerUpdate:
        self.requested_heights.append(height)
        if self.snapshot is None:
            return ArtifactLedgerUpdate(height=0, entries=())
        return ArtifactLedgerUpdate(
            height=self.snapshot.height,
            entries=tuple(entry for entry in self.snapshot.entries if entry.height > height),
        )


class _MutableNodeSource:
    def __init__(self, observation: NodeObservation) -> None:
        self.observation = observation

    def observe(self) -> NodeObservation:
        return self.observation


def _node(
    *,
    chain_id: str,
    remote_ip: str = "127.0.0.2",
    height: int = 0,
) -> NodeObservation:
    return NodeObservation(
        node_id="a" * 40,
        moniker="test-node",
        chain_id=chain_id,
        version="0.40.0",
        latest_height=height,
        application_height=height,
        latest_block_time=NOW,
        catching_up=False,
        validator_power=1,
        mempool_transactions=0,
        consensus_round=0,
        consensus_step="commit",
        peers=(
            PeerObservation(
                node_id="b" * 40,
                moniker="test-peer",
                remote_ip=remote_ip,
                direction=ConnectionDirection.OUTBOUND,
                connected_seconds=1,
                bytes_sent=2,
                bytes_received=3,
            ),
        ),
    )
