from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.knowledge_graph import (
    Artifact,
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import ArtifactLedgerEntry, ArtifactLedgerSnapshot
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.wire import artifact_ref, sign_artifact, sign_transaction

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
NOW = datetime(2026, 8, 26, 15, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _GraphFixture:
    queries: KnowledgeGraphQueries
    area: ArtifactRef
    problem: ArtifactRef
    finding: ArtifactRef
    discussion: ArtifactRef
    other_finding: ArtifactRef
    supports: ArtifactRef
    discusses: ArtifactRef
    categorizes: ArtifactRef


def test_artifact_lookup_exposes_the_indexed_consensus_height() -> None:
    # Transport adapters can retrieve one artifact and report the state height behind it.
    graph = _graph_fixture()

    indexed = graph.queries.artifact_by_ref(graph.problem)

    assert isinstance(indexed, IndexedArtifact)
    assert indexed.artifact_ref == graph.problem
    assert graph.queries.indexed_height == 2
    assert graph.queries.artifact_by_ref(ArtifactRef("missing")) is None


def test_contribution_queries_expose_selection_explicitly() -> None:
    # Entry points select all nodes or one kind without overloading filters with traversal.
    graph = _graph_fixture()

    assert _refs(graph.queries.contributions()) == (
        graph.area,
        graph.problem,
        graph.finding,
        graph.discussion,
        graph.other_finding,
    )
    assert _refs(graph.queries.contributions_by_kind(ContributionKind.FINDING)) == (
        graph.finding,
        graph.other_finding,
    )
    assert _refs(
        graph.queries.contributions_containing_title(
            "FINDING",
            kind=ContributionKind.FINDING,
        )
    ) == (graph.finding, graph.other_finding)


def test_relation_queries_expose_selection_and_direction_explicitly() -> None:
    # Entry points select relations or traverse one direction without choosing behavior by filters.
    graph = _graph_fixture()

    assert _refs(graph.queries.relations()) == (
        graph.supports,
        graph.discusses,
        graph.categorizes,
    )
    assert _refs(graph.queries.relations_by_kind(RelationKind.ABOUT)) == (
        graph.discusses,
        graph.categorizes,
    )
    assert _refs(graph.queries.outgoing_relations_by_ref(graph.finding)) == (
        graph.supports,
        graph.categorizes,
    )
    assert _refs(graph.queries.incoming_relations_by_ref(graph.problem)) == (
        graph.supports,
        graph.discusses,
    )
    assert _refs(
        graph.queries.outgoing_relations_by_ref(
            graph.discussion,
            kind=RelationKind.ABOUT,
        )
    ) == (graph.discusses,)


def test_contribution_traversal_resolves_directed_relation_endpoints() -> None:
    # Node queries hide edge mechanics while preserving direction and optional kind filters.
    graph = _graph_fixture()

    assert _refs(
        graph.queries.outgoing_contributions_by_ref(
            graph.finding,
            via=RelationKind.ABOUT,
        )
    ) == (graph.area,)
    assert _refs(
        graph.queries.incoming_contributions_by_ref(
            graph.problem,
            via=RelationKind.ABOUT,
            kind=ContributionKind.DISCUSSION,
        )
    ) == (graph.discussion,)
    assert (
        graph.queries.incoming_contributions_by_ref(
            graph.problem,
            via=RelationKind.ABOUT,
            kind=ContributionKind.PROOF_ATTEMPT,
        )
        == ()
    )


def test_query_kinds_preserve_index_validation() -> None:
    # Invalid enum families fail consistently on selection and traversal methods.
    graph = _graph_fixture()

    with pytest.raises(TypeError, match="ContributionKind"):
        graph.queries.contributions_by_kind(
            RelationKind.ABOUT,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="RelationKind"):
        graph.queries.incoming_relations_by_ref(
            graph.problem,
            kind=ContributionKind.FINDING,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="ContributionKind"):
        graph.queries.outgoing_contributions_by_ref(
            graph.finding,
            via=RelationKind.ABOUT,
            kind=RelationKind.SUPPORTS,  # type: ignore[arg-type]
        )


def test_queries_require_a_knowledge_graph_index() -> None:
    # Construction rejects objects that cannot provide the promised query behavior.
    with pytest.raises(TypeError, match="KnowledgeGraphIndex"):
        KnowledgeGraphQueries(index=object())  # type: ignore[arg-type]


def _graph_fixture() -> _GraphFixture:
    entries: list[ArtifactLedgerEntry] = []

    area = _append(entries, _contribution(ContributionKind.MATHEMATICAL_AREA, "Number theory"))
    problem = _append(entries, _contribution(ContributionKind.PROBLEM_STATEMENT, "A problem"))
    finding = _append(
        entries,
        _contribution(ContributionKind.FINDING, "A finding"),
    )
    discussion = _append(
        entries,
        _contribution(ContributionKind.DISCUSSION, "A discussion"),
    )
    other_finding = _append(
        entries,
        _contribution(ContributionKind.FINDING, "Another finding"),
    )
    supports = _append(
        entries,
        _relation(finding, problem, RelationKind.SUPPORTS),
    )
    discusses = _append(
        entries,
        _relation(discussion, problem, RelationKind.ABOUT),
    )
    categorizes = _append(
        entries,
        _relation(finding, area, RelationKind.ABOUT),
    )

    index = KnowledgeGraphIndex()
    index.refresh(ArtifactLedgerSnapshot(height=2, entries=tuple(entries)))
    return _GraphFixture(
        queries=KnowledgeGraphQueries(index=index),
        area=area,
        problem=problem,
        finding=finding,
        discussion=discussion,
        other_finding=other_finding,
        supports=supports,
        discusses=discusses,
        categorizes=categorizes,
    )


def _append(entries: list[ArtifactLedgerEntry], artifact: Artifact) -> ArtifactRef:
    height = 1 if len(entries) < 4 else 2
    transaction_index = len(entries) if height == 1 else len(entries) - 4
    envelope = sign_artifact(
        chain_id=CHAIN_ID,
        artifact=artifact,
        private_key=PRIVATE_KEY,
    )
    entry = ArtifactLedgerEntry(
        transaction=sign_transaction(envelopes=(envelope,), private_key=PRIVATE_KEY),
        height=height,
        transaction_index=transaction_index,
    )
    entries.append(entry)
    return artifact_ref(envelope)


def _contribution(
    kind: ContributionKind,
    title: str,
) -> Contribution:
    return Contribution(
        kind=kind,
        title=title,
        body=f"Body for {title}",
        created_at=NOW,
    )


def _relation(
    from_contribution: ArtifactRef,
    to_contribution: ArtifactRef,
    kind: RelationKind,
) -> ContributionRelation:
    return ContributionRelation(
        from_contribution=from_contribution,
        to_contribution=to_contribution,
        kind=kind,
        created_at=NOW,
    )


def _refs(indexed: tuple[IndexedArtifact, ...]) -> tuple[ArtifactRef, ...]:
    return tuple(value.artifact_ref for value in indexed)
