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
from discovery_net.wire import artifact_ref, sign_artifact

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


def test_empty_index_has_no_artifacts() -> None:
    # The initial index represents the empty ledger before the first commit.
    index = KnowledgeGraphIndex()

    assert index.indexed_height == 0
    assert index.contributions() == ()
    assert index.relations() == ()


def test_refresh_preserves_canonical_provenance_without_copying_it() -> None:
    # The indexed view decodes the payload but keeps position and envelope on one ledger entry.
    contribution = _contribution(ContributionKind.FINDING, "A finding")
    entry = _entry(contribution, height=3)
    reference = artifact_ref(entry.envelope)
    index = KnowledgeGraphIndex()

    index.refresh(_snapshot(3, entry))

    indexed = index.get(reference)
    assert isinstance(indexed, IndexedArtifact)
    assert indexed.artifact == contribution
    assert indexed.ledger_entry is entry
    assert indexed.artifact_ref == reference
    assert indexed.ledger_entry.height == 3


def test_queries_filter_artifacts_by_kind_in_ledger_order() -> None:
    # Kind sentinels provide direct lookup while preserving consensus order.
    area = _entry(_contribution(ContributionKind.MATHEMATICAL_AREA, "Number theory"))
    problem = _entry(
        _contribution(ContributionKind.PROBLEM_STATEMENT, "A problem"),
        transaction_index=1,
    )
    proof = _entry(
        _contribution(ContributionKind.PROOF_ATTEMPT, "A proof"),
        transaction_index=2,
    )
    relation = _entry(
        ContributionRelation(
            from_contribution=artifact_ref(proof.envelope),
            to_contribution=artifact_ref(problem.envelope),
            kind=RelationKind.ABOUT,
            created_at=NOW,
        ),
        transaction_index=3,
    )
    index = KnowledgeGraphIndex()

    index.refresh(_snapshot(1, area, problem, proof, relation))

    assert _refs(index.contributions()) == (
        artifact_ref(area.envelope),
        artifact_ref(problem.envelope),
        artifact_ref(proof.envelope),
    )
    assert _refs(index.contributions(ContributionKind.PROOF_ATTEMPT)) == (
        artifact_ref(proof.envelope),
    )
    assert _refs(index.relations(RelationKind.ABOUT)) == (artifact_ref(relation.envelope),)


def test_graph_queries_share_one_adjacency_map() -> None:
    # Parent and directed-relation queries distinguish artifacts stored in the same neighbor bucket.
    problem = _entry(_contribution(ContributionKind.PROBLEM_STATEMENT, "A problem"))
    problem_ref = artifact_ref(problem.envelope)
    reply = _entry(
        _contribution(ContributionKind.DISCUSSION, "A reply", parent=problem_ref),
        transaction_index=1,
    )
    proof = _entry(
        _contribution(ContributionKind.PROOF_ATTEMPT, "A proof"),
        transaction_index=2,
    )
    proof_ref = artifact_ref(proof.envelope)
    relation = _entry(
        ContributionRelation(
            from_contribution=proof_ref,
            to_contribution=problem_ref,
            kind=RelationKind.ABOUT,
            created_at=NOW,
        ),
        transaction_index=3,
    )
    index = KnowledgeGraphIndex()
    index.refresh(_snapshot(1, problem, reply, proof, relation))

    assert _refs(index.children_of(problem_ref)) == (artifact_ref(reply.envelope),)
    assert _refs(index.incoming_relations(problem_ref)) == (artifact_ref(relation.envelope),)
    assert _refs(index.outgoing_relations(proof_ref, RelationKind.ABOUT)) == (
        artifact_ref(relation.envelope),
    )
    assert index.outgoing_relations(problem_ref) == ()
    assert index.incoming_relations(proof_ref) == ()


def test_relations_remain_queryable_when_an_endpoint_is_not_indexed() -> None:
    # A relation can identify graph edges before this node has indexed both endpoint artifacts.
    source = _entry(_contribution(ContributionKind.FINDING, "Source"))
    target = _entry(_contribution(ContributionKind.PROBLEM_STATEMENT, "Target"))
    relation = _entry(
        ContributionRelation(
            from_contribution=artifact_ref(source.envelope),
            to_contribution=artifact_ref(target.envelope),
            kind=RelationKind.SUPPORTS,
            created_at=NOW,
        )
    )
    index = KnowledgeGraphIndex()

    index.refresh(_snapshot(1, relation))

    assert _refs(index.outgoing_relations(artifact_ref(source.envelope))) == (
        artifact_ref(relation.envelope),
    )
    assert _refs(index.incoming_relations(artifact_ref(target.envelope))) == (
        artifact_ref(relation.envelope),
    )


def test_refresh_replaces_the_projection_with_the_latest_snapshot() -> None:
    # Rebuilding is deterministic and removes data absent from the supplied committed snapshot.
    first = _entry(_contribution(ContributionKind.FINDING, "First"))
    second = _entry(_contribution(ContributionKind.FINDING, "Second"), height=2)
    index = KnowledgeGraphIndex()
    index.refresh(_snapshot(1, first))

    index.refresh(_snapshot(2, second))

    assert index.indexed_height == 2
    assert index.get(artifact_ref(first.envelope)) is None
    assert _refs(index.contributions()) == (artifact_ref(second.envelope),)


def test_failed_refresh_leaves_the_previous_projection_intact() -> None:
    # A complete state is swapped in only after every snapshot entry has been decoded and indexed.
    first = _entry(_contribution(ContributionKind.FINDING, "First"))
    index = KnowledgeGraphIndex()
    index.refresh(_snapshot(1, first))

    with pytest.raises(ValueError, match="duplicate artifacts"):
        index.refresh(_snapshot(2, first, first))

    assert index.indexed_height == 1
    assert _refs(index.contributions()) == (artifact_ref(first.envelope),)


def test_query_kind_arguments_are_typed() -> None:
    # Invalid enum families fail clearly instead of silently returning an empty result.
    index = KnowledgeGraphIndex()

    with pytest.raises(TypeError, match="ContributionKind"):
        index.contributions(RelationKind.ABOUT)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RelationKind"):
        index.relations(ContributionKind.FINDING)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RelationKind"):
        index.incoming_relations(ArtifactRef("missing"), ContributionKind.FINDING)  # type: ignore[arg-type]


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


def _entry(
    artifact: Artifact,
    *,
    height: int = 1,
    transaction_index: int = 0,
) -> ArtifactLedgerEntry:
    return ArtifactLedgerEntry(
        envelope=sign_artifact(
            chain_id=CHAIN_ID,
            artifact=artifact,
            private_key=PRIVATE_KEY,
        ),
        height=height,
        transaction_index=transaction_index,
    )


def _snapshot(height: int, *entries: ArtifactLedgerEntry) -> ArtifactLedgerSnapshot:
    return ArtifactLedgerSnapshot(height=height, entries=entries)


def _refs(indexed: tuple[IndexedArtifact, ...]) -> tuple[ArtifactRef, ...]:
    return tuple(value.artifact_ref for value in indexed)
