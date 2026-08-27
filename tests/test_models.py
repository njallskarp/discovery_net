from datetime import UTC, datetime

import pytest

from discovery_net.knowledge_graph import (
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)
ROOT_REF = ArtifactRef("bafkreibm6jg3ux5qumhcn2b3flc3tyu6dmlb4xa7u5bf44yegnrjhc4yeq")
AREA_REF = ArtifactRef("bafkreif2akiscaildc3up25n4nhiiu5cl2f3l5xptmm5x4ncug5ue5o3am")


def test_contribution_body_is_required() -> None:
    with pytest.raises(TypeError):
        Contribution(  # type: ignore[call-arg]
            kind=ContributionKind.DISCUSSION,
            title="A discussion",
            created_at=NOW,
        )


def test_contribution_title_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="title must not be blank"):
        Contribution(
            kind=ContributionKind.DISCUSSION,
            title=" ",
            body="A body is still present.",
            created_at=NOW,
        )


def test_contribution_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Contribution(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="The study of integers and arithmetic structures.",
            created_at=datetime(2026, 8, 23),
        )


@pytest.mark.parametrize(
    "kind",
    [ContributionKind.REVIEW_ASSIGNMENT, ContributionKind.REVIEW],
)
def test_review_artifacts_are_ordinary_contributions(kind: ContributionKind) -> None:
    contribution = Contribution(
        kind=kind,
        title=kind.value.replace("_", " ").title(),
        body="Review workflow details can be modeled later.",
        created_at=NOW,
    )

    assert contribution.kind is kind


def test_relation_connects_two_artifact_references() -> None:
    relation = ContributionRelation(
        from_contribution=AREA_REF,
        to_contribution=ROOT_REF,
        kind=RelationKind.SUBAREA_OF,
        created_at=NOW,
    )

    assert relation.from_contribution == AREA_REF
    assert relation.to_contribution == ROOT_REF


def test_reply_is_an_ordinary_directed_relation() -> None:
    relation = ContributionRelation(
        from_contribution=AREA_REF,
        to_contribution=ROOT_REF,
        kind=RelationKind.REPLIES_TO,
        created_at=NOW,
    )

    assert relation.kind is RelationKind.REPLIES_TO


def test_relation_cannot_link_a_contribution_to_itself() -> None:
    with pytest.raises(ValueError, match="two distinct"):
        ContributionRelation(
            from_contribution=ROOT_REF,
            to_contribution=ROOT_REF,
            kind=RelationKind.SUPPORTS,
            created_at=NOW,
        )
