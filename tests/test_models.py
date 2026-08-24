from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from discovery_net.domain import (
    Agent,
    AgentId,
    Contribution,
    ContributionId,
    ContributionKind,
    ContributionRelation,
    RelationId,
    RelationKind,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)
AGENT_ID = AgentId("agent-gauss")
REVIEWER_ID = AgentId("agent-euler")
ROOT_ID = ContributionId("contribution-number-theory")


def test_agent_is_immutable() -> None:
    agent = Agent(id=AGENT_ID)

    with pytest.raises(FrozenInstanceError):
        agent.id = REVIEWER_ID  # type: ignore[misc]


def test_agent_id_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="id must not be blank"):
        Agent(id=AgentId(" "))


def test_root_contribution_identifies_itself_as_thread_root() -> None:
    area = Contribution(
        id=ROOT_ID,
        author_id=AGENT_ID,
        thread_root_id=ROOT_ID,
        kind=ContributionKind.MATHEMATICAL_AREA,
        title="Number theory",
        body="The study of integers and arithmetic structures.",
        created_at=NOW,
    )

    assert area.parent_id is None
    assert area.thread_root_id == area.id


def test_root_contribution_rejects_a_different_thread_root() -> None:
    with pytest.raises(ValueError, match="identify itself"):
        Contribution(
            id=ContributionId("contribution-a"),
            author_id=AGENT_ID,
            thread_root_id=ContributionId("contribution-b"),
            kind=ContributionKind.FINDING,
            title="A finding",
            body="The details of the finding.",
            created_at=NOW,
        )


def test_reply_can_be_a_finding_in_a_larger_thread() -> None:
    finding = Contribution(
        id=ContributionId("contribution-finding"),
        author_id=AGENT_ID,
        thread_root_id=ROOT_ID,
        parent_id=ROOT_ID,
        kind=ContributionKind.FINDING,
        title="Mellin inversion identity",
        body="A potentially useful identity appears after applying Mellin inversion.",
        created_at=NOW,
    )

    assert finding.kind is ContributionKind.FINDING
    assert finding.parent_id == ROOT_ID


def test_contribution_body_is_required() -> None:
    with pytest.raises(TypeError):
        Contribution(  # type: ignore[call-arg]
            id=ROOT_ID,
            author_id=AGENT_ID,
            thread_root_id=ROOT_ID,
            kind=ContributionKind.DISCUSSION,
            title="A discussion",
            created_at=NOW,
        )


def test_contribution_title_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="title must not be blank"):
        Contribution(
            id=ContributionId("contribution-untitled"),
            author_id=AGENT_ID,
            thread_root_id=ContributionId("contribution-untitled"),
            kind=ContributionKind.DISCUSSION,
            title=" ",
            body="A body is still present.",
            created_at=NOW,
        )


def test_contribution_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Contribution(
            id=ROOT_ID,
            author_id=AGENT_ID,
            thread_root_id=ROOT_ID,
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
        id=ContributionId(f"contribution-{kind.value}"),
        author_id=REVIEWER_ID,
        thread_root_id=ROOT_ID,
        parent_id=ROOT_ID,
        kind=kind,
        title=kind.value.replace("_", " ").title(),
        body="Review workflow details can be modeled later.",
        created_at=NOW,
    )

    assert contribution.kind is kind


def test_relation_is_an_attributable_cross_link() -> None:
    relation = ContributionRelation(
        id=RelationId("relation-analytic-number-theory"),
        author_id=AGENT_ID,
        from_contribution_id=ContributionId("area-analytic-number-theory"),
        to_contribution_id=ROOT_ID,
        kind=RelationKind.SUBAREA_OF,
        created_at=NOW,
    )

    assert relation.from_contribution_id == ContributionId("area-analytic-number-theory")
    assert relation.to_contribution_id == ROOT_ID


def test_relation_cannot_link_a_contribution_to_itself() -> None:
    with pytest.raises(ValueError, match="two distinct"):
        ContributionRelation(
            id=RelationId("relation-self"),
            author_id=AGENT_ID,
            from_contribution_id=ROOT_ID,
            to_contribution_id=ROOT_ID,
            kind=RelationKind.SUPPORTS,
            created_at=NOW,
        )
