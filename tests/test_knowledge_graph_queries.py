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
from discovery_net.wire import artifact_ref, sign_artifact

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

    indexed = graph.queries.artifact(graph.problem)

    assert isinstance(indexed, IndexedArtifact)
    assert indexed.artifact_ref == graph.problem
    assert graph.queries.indexed_height == 2
    assert graph.queries.artifact(ArtifactRef("missing")) is None


def test_contributions_support_kind_and_parent_filters() -> None:
    # CLI, GraphQL, and MCP callers share one implementation of combined contribution filters.
    graph = _graph_fixture()

    assert _refs(graph.queries.contributions()) == (
        graph.area,
        graph.problem,
        graph.finding,
        graph.discussion,
        graph.other_finding,
    )
    assert _refs(graph.queries.contributions(kind=ContributionKind.FINDING)) == (
        graph.finding,
        graph.other_finding,
    )
    assert _refs(graph.queries.contributions(parent=graph.problem)) == (
        graph.finding,
        graph.discussion,
    )
    assert _refs(
        graph.queries.contributions(
            kind=ContributionKind.FINDING,
            parent=graph.problem,
        )
    ) == (graph.finding,)


def test_relations_support_kind_and_endpoint_filters() -> None:
    # Directional and kind filters compose without exposing adjacency details to entrypoints.
    graph = _graph_fixture()

    assert _refs(graph.queries.relations()) == (
        graph.supports,
        graph.discusses,
        graph.categorizes,
    )
    assert _refs(graph.queries.relations(kind=RelationKind.ABOUT)) == (
        graph.discusses,
        graph.categorizes,
    )
    assert _refs(graph.queries.relations(from_contribution=graph.finding)) == (
        graph.supports,
        graph.categorizes,
    )
    assert _refs(graph.queries.relations(to_contribution=graph.problem)) == (
        graph.supports,
        graph.discusses,
    )
    assert _refs(
        graph.queries.relations(
            from_contribution=graph.finding,
            to_contribution=graph.problem,
        )
    ) == (graph.supports,)
    assert (
        graph.queries.relations(
            kind=RelationKind.ABOUT,
            from_contribution=graph.finding,
            to_contribution=graph.problem,
        )
        == ()
    )


def test_query_filters_preserve_index_validation() -> None:
    # Invalid filter enum families fail consistently on every query path.
    graph = _graph_fixture()

    with pytest.raises(TypeError, match="ContributionKind"):
        graph.queries.contributions(
            kind=RelationKind.ABOUT,  # type: ignore[arg-type]
            parent=graph.problem,
        )
    with pytest.raises(TypeError, match="RelationKind"):
        graph.queries.relations(
            kind=ContributionKind.FINDING,  # type: ignore[arg-type]
            from_contribution=graph.finding,
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
        _contribution(ContributionKind.FINDING, "A finding", parent=problem),
    )
    discussion = _append(
        entries,
        _contribution(ContributionKind.DISCUSSION, "A discussion", parent=problem),
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
    entry = ArtifactLedgerEntry(
        envelope=sign_artifact(
            chain_id=CHAIN_ID,
            artifact=artifact,
            private_key=PRIVATE_KEY,
        ),
        height=height,
        transaction_index=transaction_index,
    )
    entries.append(entry)
    return artifact_ref(entry.envelope)


def _contribution(
    kind: ContributionKind,
    title: str,
    *,
    parent: ArtifactRef | None = None,
) -> Contribution:
    return Contribution(
        kind=kind,
        title=title,
        body=f"Body for {title}",
        created_at=NOW,
        parent=parent,
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
