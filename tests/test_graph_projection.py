"""View selection changes graph traversal without changing signed ledger records."""

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.index import ArtifactIndex, IndexedEnvelope
from discovery_net.artifacts.projection import (
    GraphEdge,
    GraphEdgeRevocation,
    GraphNode,
    ProjectedGraph,
)
from discovery_net.domains.math import (
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.domains.math.projection import MathProjection
from discovery_net.indexing import KnowledgeGraphIndex
from discovery_net.node import ArtifactLedgerEntry, ArtifactLedgerSnapshot, LocalArtifactLedger
from discovery_net.node._ledger_from_snapshot import ledger_from_snapshot
from discovery_net.node.transaction_validator import TransactionValidator
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.wire import artifact_ref, encode_envelope, sign_artifact, sign_transaction

KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
NOW = datetime(2026, 9, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    ("node_kind", "edge_kind"),
    [
        (ContributionKind.AXIOM, RelationKind.PROVES),
        (ContributionKind.DEFINITION, RelationKind.REFUTES),
        (ContributionKind.THEOREM, RelationKind.SUPERSEDES),
        (ContributionKind.COROLLARY, RelationKind.RETRACTS),
        (ContributionKind.RETRACTION, RelationKind.CORRECTS),
        (ContributionKind.ERRATUM, RelationKind.ENDORSES),
    ],
)
def test_peer_review_vocabulary_survives_replay_and_projection(
    node_kind: ContributionKind, edge_kind: RelationKind
) -> None:
    # Exercise every kind added in PR #58 across the moved codec, validator, and index.
    source = Contribution(kind=node_kind, title="Peer review", body="", created_at=NOW)
    target = _node("Target")
    source_ref = artifact_ref(_entry(source).transaction.envelopes[0])
    target_ref = artifact_ref(_entry(target).transaction.envelopes[0])
    relation = ContributionRelation(
        kind=edge_kind,
        from_contribution=source_ref,
        to_contribution=target_ref,
        created_at=NOW,
    )
    entry = _entry(source, target, relation)
    snapshot = ArtifactLedgerSnapshot(height=1, entries=(entry,))
    ledger_from_snapshot(snapshot, TransactionValidator(expected_chain_id="projection-test"))
    index = KnowledgeGraphIndex()
    index.refresh(snapshot)

    assert tuple(record.artifact for record in index.contributions(node_kind)) == (source,)
    assert tuple(record.artifact for record in index.relations(edge_kind)) == (relation,)
    assert index.outgoing_relations(source_ref, edge_kind) == index.relations(edge_kind)
    assert index.incoming_relations(target_ref, edge_kind) == index.relations(edge_kind)


def _node(title: str) -> Contribution:
    return Contribution(kind=ContributionKind.QUESTION, title=title, body="", created_at=NOW)


def _entry(*artifacts: Contribution | ContributionRelation, height: int = 1) -> ArtifactLedgerEntry:
    envelopes = tuple(
        sign_artifact(chain_id="projection-test", artifact=artifact, private_key=KEY)
        for artifact in artifacts
    )
    return ArtifactLedgerEntry(
        transaction=sign_transaction(envelopes=envelopes, private_key=KEY),
        height=height,
        transaction_index=0,
    )


@dataclass(frozen=True)
class _Fixture:
    snapshot: ArtifactLedgerSnapshot
    source: ArtifactRef
    target: ArtifactRef
    edge: ArtifactRef


def _fixture() -> _Fixture:
    source, target = _node("Source"), _node("Target")
    source_ref = artifact_ref(_entry(source).transaction.envelopes[0])
    target_ref = artifact_ref(_entry(target).transaction.envelopes[0])
    entry = _entry(
        ContributionRelation(
            from_contribution=source_ref,
            to_contribution=target_ref,
            kind=RelationKind.ABOUT,
            created_at=NOW,
        ),
        source,
        target,
    )
    return _Fixture(
        snapshot=ArtifactLedgerSnapshot(height=1, entries=(entry,)),
        source=source_ref,
        target=target_ref,
        edge=artifact_ref(entry.transaction.envelopes[0]),
    )


@dataclass(frozen=True)
class _Exclude:
    references: frozenset[ArtifactRef]

    def project(
        self, record: IndexedEnvelope
    ) -> GraphNode | GraphEdge | GraphEdgeRevocation | None:
        if record.artifact_ref in self.references:
            return None
        return MathProjection().project(record)


def test_two_projections_share_raw_records_without_math_specific_indexing() -> None:
    fixture = _fixture()
    raw = ArtifactIndex(fixture.snapshot)

    class AuditProjection:
        def project(self, record: IndexedEnvelope) -> GraphNode:
            # A second vocabulary can interpret records without contribution enums.
            return GraphNode(kind="audit_record")

    audit = ProjectedGraph(raw=raw, projection=AuditProjection())
    math = ProjectedGraph(raw=raw, projection=MathProjection())

    assert audit.raw is math.raw is raw
    assert audit.nodes("audit_record") == raw.artifacts()
    assert audit.edges() == ()
    assert len(math.nodes()) == 2
    assert len(math.edges()) == 1
    assert math.edges()[0] is raw.get(fixture.edge)
    # The source comes after the edge in the atomic transaction but is still visible.
    assert math.outgoing(fixture.source) == math.incoming(fixture.target) == math.edges()


@pytest.mark.parametrize("incremental", [False, True])
def test_omitting_an_edge_changes_all_traversals_but_preserves_raw_history(
    incremental: bool,
) -> None:
    fixture = _fixture()
    original_hash = LocalArtifactLedger(entries=fixture.snapshot.entries).state_hash()
    index = KnowledgeGraphIndex(projection=_Exclude(frozenset({fixture.edge})))
    if incremental:
        index.append(entries=fixture.snapshot.entries, height=1)
    else:
        index.refresh(fixture.snapshot)
    queries = KnowledgeGraphQueries(index=index)

    assert len(queries.contributions()) == 2
    assert queries.relations() == queries.relations_by_kind(RelationKind.ABOUT) == ()
    assert queries.outgoing_relations_by_ref(fixture.source) == ()
    assert queries.incoming_relations_by_ref(fixture.target) == ()
    assert queries.outgoing_contributions_by_ref(fixture.source, via=RelationKind.ABOUT) == ()
    assert queries.incoming_contributions_by_ref(fixture.target, via=RelationKind.ABOUT) == ()
    assert len(index.artifacts()) == len(index.raw_index.artifacts()) == 3
    omitted = queries.artifact_by_ref(fixture.edge)
    assert omitted is not None
    assert encode_envelope(omitted.envelope) == encode_envelope(
        fixture.snapshot.entries[0].transaction.envelopes[0]
    )
    assert artifact_ref(omitted.envelope) == fixture.edge
    assert LocalArtifactLedger(entries=fixture.snapshot.entries).state_hash() == original_hash


def test_excluded_nodes_cannot_reappear_through_incident_edges() -> None:
    fixture = _fixture()
    index = KnowledgeGraphIndex(projection=_Exclude(frozenset({fixture.source})))
    index.refresh(fixture.snapshot)

    assert tuple(node.artifact_ref for node in index.contributions()) == (fixture.target,)
    assert index.relations() == index.incoming_relations(fixture.target) == ()
    assert index.outgoing_relations(fixture.source) == ()
    assert index.raw_index.get(fixture.source) is not None
    assert index.get(fixture.source) is not None


@pytest.mark.parametrize("refresh", [False, True])
def test_failed_projection_preserves_both_the_raw_and_decoded_index(refresh: bool) -> None:
    fixture = _fixture()
    next_entry = _entry(_node("Fail during projection"), height=2)
    rejected = artifact_ref(next_entry.transaction.envelopes[0])

    class FailingProjection:
        def project(self, record: IndexedEnvelope) -> GraphNode | GraphEdge | GraphEdgeRevocation:
            if record.artifact_ref == rejected:
                raise ValueError("cannot project candidate")
            return MathProjection().project(record)

    index = KnowledgeGraphIndex(projection=FailingProjection())
    index.refresh(fixture.snapshot)
    before = index.raw_index
    original_node = index.get(fixture.source)

    with pytest.raises(ValueError, match="cannot project"):
        if refresh:
            index.refresh(
                ArtifactLedgerSnapshot(height=2, entries=(*fixture.snapshot.entries, next_entry))
            )
        else:
            index.append(entries=(next_entry,), height=2)

    assert index.raw_index is before
    assert index.indexed_height == 1
    assert index.get(fixture.source) is original_node
    assert index.get(rejected) is None
    assert index.raw_index.get(rejected) is None
    assert len(index.relations()) == 1


def test_raw_append_is_persistent_and_preserves_old_record_objects() -> None:
    fixture = _fixture()
    raw = ArtifactIndex(fixture.snapshot)
    next_entry = _entry(_node("Later"), height=2)

    updated = raw.append(entries=(next_entry,), height=2)

    assert raw.height == 1
    assert updated.height == 2
    assert len(raw.artifacts()) == 3
    assert len(updated.artifacts()) == 4
    assert updated.get(fixture.source) is raw.get(fixture.source)
    empty_block = updated.append(entries=(), height=3)
    assert empty_block.height == 3
    assert empty_block.artifacts() == updated.artifacts()


def test_query_resolves_records_from_one_state_even_if_refresh_occurs_mid_query() -> None:
    fixture = _fixture()
    index = KnowledgeGraphIndex()
    index.refresh(fixture.snapshot)
    original = index.contributions()
    nodes = ProjectedGraph.nodes

    def refresh_during_lookup(
        graph: ProjectedGraph, kind: str | None = None
    ) -> tuple[IndexedEnvelope, ...]:
        index.refresh(ArtifactLedgerSnapshot(height=2, entries=()))
        return nodes(graph, kind)

    with patch.object(ProjectedGraph, "nodes", refresh_during_lookup):
        assert index.contributions() == original

    assert index.indexed_height == 2
    assert index.contributions() == ()
