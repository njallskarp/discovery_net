# Projects local node and ledger observations into browser-safe snapshots.

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import IPv4Address, ip_address
from threading import RLock
from typing import final

from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.inspector.models import (
    InspectorContribution,
    InspectorKnowledgeGraph,
    InspectorNode,
    InspectorPeer,
    InspectorRelation,
    InspectorSnapshot,
    NodeObservation,
)
from discovery_net.inspector.sources import ArtifactLedgerSnapshotReader, NodeObservationSource
from discovery_net.knowledge_graph import Contribution, ContributionRelation
from discovery_net.node import ArtifactLedgerSnapshot


@final
class InspectorService:
    """Builds sanitized read-only views from node and committed ledger state."""

    __slots__ = (
        "_clock",
        "_index",
        "_indexed_chain_id",
        "_indexed_height",
        "_ledger_reader",
        "_lock",
        "_node_source",
        "_redact_peer_ips",
    )

    def __init__(
        self,
        *,
        node_source: NodeObservationSource,
        ledger_reader: ArtifactLedgerSnapshotReader,
        redact_peer_ips: bool = True,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(redact_peer_ips, bool):
            raise TypeError("redact_peer_ips must be a boolean")
        if not callable(clock):
            raise TypeError("clock must be callable")

        self._node_source = node_source
        self._ledger_reader = ledger_reader
        self._redact_peer_ips = redact_peer_ips
        self._clock = clock
        self._index = KnowledgeGraphIndex()
        self._indexed_height: int | None = None
        self._indexed_chain_id: str | None = None
        self._lock = RLock()

    def snapshot(self) -> InspectorSnapshot:
        """Return the latest internally consistent inspector snapshot."""
        node = self._node_source.observe()
        if not isinstance(node, NodeObservation):
            raise TypeError("node source must return a NodeObservation")
        ledger_snapshot = self._ledger_reader.load()
        if ledger_snapshot is not None and not isinstance(ledger_snapshot, ArtifactLedgerSnapshot):
            raise TypeError("ledger reader must return an ArtifactLedgerSnapshot or None")

        with self._lock:
            self._refresh_index(ledger_snapshot, node.chain_id)
            observed_at = self._clock()
            return InspectorSnapshot(
                observed_at=observed_at,
                node=_node_view(node, redact_peer_ips=self._redact_peer_ips),
                knowledge_graph=_knowledge_graph_view(self._index),
            )

    def _refresh_index(
        self,
        snapshot: ArtifactLedgerSnapshot | None,
        node_chain_id: str,
    ) -> None:
        if self._indexed_chain_id is not None and self._indexed_chain_id != node_chain_id:
            raise ValueError("node chain does not match the indexed artifact ledger")
        if snapshot is None or snapshot.height == self._indexed_height:
            return

        ledger_chain_id = _snapshot_chain_id(snapshot)
        if ledger_chain_id is not None and ledger_chain_id != node_chain_id:
            raise ValueError("node chain does not match the artifact ledger")
        self._index.refresh(snapshot)
        self._indexed_height = snapshot.height
        self._indexed_chain_id = ledger_chain_id


def _snapshot_chain_id(snapshot: ArtifactLedgerSnapshot) -> str | None:
    chain_ids = {entry.transaction.chain_id for entry in snapshot.entries}
    if len(chain_ids) > 1:
        raise ValueError("artifact ledger contains multiple chains")
    return next(iter(chain_ids), None)


def _node_view(node: NodeObservation, *, redact_peer_ips: bool) -> InspectorNode:
    return InspectorNode(
        node_id=node.node_id,
        moniker=node.moniker,
        chain_id=node.chain_id,
        version=node.version,
        latest_height=node.latest_height,
        application_height=node.application_height,
        latest_block_time=node.latest_block_time,
        catching_up=node.catching_up,
        validator_power=node.validator_power,
        mempool_transactions=node.mempool_transactions,
        consensus_round=node.consensus_round,
        consensus_step=node.consensus_step,
        peers=tuple(
            InspectorPeer(
                node_id=peer.node_id,
                moniker=peer.moniker,
                observed_address=(
                    _redacted_ip(peer.remote_ip) if redact_peer_ips else peer.remote_ip
                ),
                direction=peer.direction,
                connected_seconds=peer.connected_seconds,
                bytes_sent=peer.bytes_sent,
                bytes_received=peer.bytes_received,
            )
            for peer in node.peers
        ),
    )


def _redacted_ip(value: str) -> str:
    try:
        address = ip_address(value)
    except ValueError:
        return "redacted"
    if isinstance(address, IPv4Address):
        first, second, *_remaining = str(address).split(".")
        return f"{first}.{second}.x.x"
    first, second, *_remaining = address.exploded.split(":")
    return f"{first}:{second}::/32"


def _knowledge_graph_view(index: KnowledgeGraphIndex) -> InspectorKnowledgeGraph:
    return InspectorKnowledgeGraph(
        indexed_height=index.indexed_height,
        contributions=tuple(_contribution_view(indexed) for indexed in index.contributions()),
        relations=tuple(_relation_view(indexed) for indexed in index.relations()),
    )


def _contribution_view(indexed: IndexedArtifact) -> InspectorContribution:
    artifact = indexed.artifact
    if not isinstance(artifact, Contribution):
        raise TypeError("indexed artifact must be a Contribution")
    return InspectorContribution(
        artifact_ref=indexed.artifact_ref,
        kind=artifact.kind,
        title=artifact.title,
        body=artifact.body,
        created_at=artifact.created_at,
        signer_public_key=indexed.envelope.signer_public_key.hex(),
        signature=indexed.envelope.signature.hex(),
        height=indexed.ledger_entry.height,
        transaction_index=indexed.ledger_entry.transaction_index,
    )


def _relation_view(indexed: IndexedArtifact) -> InspectorRelation:
    artifact = indexed.artifact
    if not isinstance(artifact, ContributionRelation):
        raise TypeError("indexed artifact must be a ContributionRelation")
    return InspectorRelation(
        artifact_ref=indexed.artifact_ref,
        kind=artifact.kind,
        from_contribution=artifact.from_contribution,
        to_contribution=artifact.to_contribution,
        created_at=artifact.created_at,
        signer_public_key=indexed.envelope.signer_public_key.hex(),
        signature=indexed.envelope.signature.hex(),
        height=indexed.ledger_entry.height,
        transaction_index=indexed.ledger_entry.transaction_index,
    )
