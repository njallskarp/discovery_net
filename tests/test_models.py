from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from discovery_net.domain import (
    Agent,
    AgentId,
    AgentKey,
    Contribution,
    ContributionId,
    ContributionKind,
    ContributionRelation,
    EpistemicStatus,
    KeyId,
    PublicationStatus,
    RelationId,
    RelationKind,
    ReputationCategory,
    ReputationEvent,
    ReputationEventId,
    Review,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentStatus,
    ReviewId,
    ReviewPolicy,
    ReviewVerdict,
    Signature,
)

NOW = datetime(2026, 8, 23, tzinfo=UTC)
AGENT_ID = AgentId("agent-gauss")
REVIEWER_ID = AgentId("agent-euler")
ROOT_ID = ContributionId("contribution-number-theory")


def test_agent_is_immutable() -> None:
    agent = Agent(id=AGENT_ID, display_name="Gauss", created_at=NOW)

    with pytest.raises(FrozenInstanceError):
        agent.display_name = "Euler"  # type: ignore[misc]


def test_agent_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Agent(
            id=AGENT_ID,
            display_name="Gauss",
            created_at=datetime(2026, 8, 23),
        )


def test_ed25519_key_and_signature_validate_raw_lengths() -> None:
    key = AgentKey(
        id=KeyId("key-gauss-1"),
        agent_id=AGENT_ID,
        public_key=b"p" * 32,
        created_at=NOW,
    )
    signature = Signature(
        key_id=key.id,
        digest=b"d" * 32,
        value=b"s" * 64,
    )

    assert signature.key_id == key.id


def test_agent_key_rejects_revocation_before_creation() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        AgentKey(
            id=KeyId("key-gauss-1"),
            agent_id=AGENT_ID,
            public_key=b"p" * 32,
            created_at=NOW,
            revoked_at=NOW - timedelta(seconds=1),
        )


def test_root_contribution_identifies_itself_as_thread_root() -> None:
    area = Contribution(
        id=ROOT_ID,
        author_id=AGENT_ID,
        thread_root_id=ROOT_ID,
        kind=ContributionKind.MATHEMATICAL_AREA,
        title="Number theory",
        body="The study of integers and arithmetic structures.",
        created_at=NOW,
        review_policy_version="v1",
    )

    assert area.parent_id is None
    assert area.thread_root_id == area.id
    assert area.publication_status is PublicationStatus.AWAITING_REVIEW
    assert area.epistemic_status is EpistemicStatus.UNASSESSED


def test_root_contribution_rejects_a_different_thread_root() -> None:
    with pytest.raises(ValueError, match="identify itself"):
        Contribution(
            id=ContributionId("contribution-a"),
            author_id=AGENT_ID,
            thread_root_id=ContributionId("contribution-b"),
            kind=ContributionKind.FINDING,
            title="A finding",
            created_at=NOW,
            review_policy_version="v1",
        )


def test_reply_can_be_a_finding_in_a_larger_thread() -> None:
    finding_id = ContributionId("contribution-finding")
    finding = Contribution(
        id=finding_id,
        author_id=AGENT_ID,
        thread_root_id=ROOT_ID,
        parent_id=ROOT_ID,
        kind=ContributionKind.FINDING,
        title="Mellin inversion identity",
        body="A potentially useful identity appears after applying Mellin inversion.",
        created_at=NOW,
        review_policy_version="v1",
    )

    assert finding.kind is ContributionKind.FINDING
    assert finding.parent_id == ROOT_ID


def test_contribution_title_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="title must not be blank"):
        Contribution(
            id=ContributionId("contribution-untitled"),
            author_id=AGENT_ID,
            thread_root_id=ContributionId("contribution-untitled"),
            kind=ContributionKind.DISCUSSION,
            title=" ",
            created_at=NOW,
            review_policy_version="v1",
        )


def test_relation_is_an_attributable_cross_link() -> None:
    relation = ContributionRelation(
        id=RelationId("relation-analytic-number-theory"),
        author_id=AGENT_ID,
        source_id=ContributionId("area-analytic-number-theory"),
        target_id=ROOT_ID,
        kind=RelationKind.SUBAREA_OF,
        created_at=NOW,
    )

    assert relation.kind is RelationKind.SUBAREA_OF


def test_relation_cannot_link_a_contribution_to_itself() -> None:
    with pytest.raises(ValueError, match="two distinct"):
        ContributionRelation(
            id=RelationId("relation-self"),
            author_id=AGENT_ID,
            source_id=ROOT_ID,
            target_id=ROOT_ID,
            kind=RelationKind.SUPPORTS,
            created_at=NOW,
        )


def test_review_policy_can_require_unanimous_approval() -> None:
    policy = ReviewPolicy(
        contribution_kind=ContributionKind.MATHEMATICAL_AREA,
        policy_version="v1",
        rubric="Confirm this is a real, non-duplicate mathematical area.",
        reviewer_count=10,
        approval_threshold=10,
        rejection_threshold=1,
        minimum_author_karma=20,
        minimum_reviewer_karma=5,
    )

    assert policy.approval_threshold == policy.reviewer_count


def test_review_policy_rejects_overlapping_outcomes() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        ReviewPolicy(
            contribution_kind=ContributionKind.DISCUSSION,
            policy_version="v1",
            rubric="Confirm this adds relevant, substantive information to the thread.",
            reviewer_count=3,
            approval_threshold=1,
            rejection_threshold=1,
        )


def test_agent_cannot_be_assigned_to_review_own_contribution() -> None:
    with pytest.raises(ValueError, match="cannot review its own"):
        ReviewAssignment(
            id=ReviewAssignmentId("assignment-1"),
            target_contribution_id=ROOT_ID,
            target_author_id=AGENT_ID,
            reviewer_id=AGENT_ID,
            assigned_at=NOW,
        )


def test_completed_assignment_requires_a_review() -> None:
    with pytest.raises(ValueError, match="requires a review"):
        ReviewAssignment(
            id=ReviewAssignmentId("assignment-1"),
            target_contribution_id=ROOT_ID,
            target_author_id=AGENT_ID,
            reviewer_id=REVIEWER_ID,
            assigned_at=NOW,
            status=ReviewAssignmentStatus.COMPLETED,
            resolved_at=NOW + timedelta(minutes=1),
        )


def test_completed_assignment_links_to_its_review() -> None:
    review_id = ReviewId("review-1")
    assignment = ReviewAssignment(
        id=ReviewAssignmentId("assignment-1"),
        target_contribution_id=ROOT_ID,
        target_author_id=AGENT_ID,
        reviewer_id=REVIEWER_ID,
        assigned_at=NOW,
        status=ReviewAssignmentStatus.COMPLETED,
        resolved_at=NOW + timedelta(minutes=1),
        review_id=review_id,
    )

    assert assignment.review_id == review_id


def test_review_requires_textual_rationale() -> None:
    with pytest.raises(ValueError, match="textual body"):
        Review(
            id=ReviewId("review-1"),
            assignment_id=ReviewAssignmentId("assignment-1"),
            reviewer_id=REVIEWER_ID,
            target_contribution_id=ROOT_ID,
            verdict=ReviewVerdict.REJECT,
            body="",
            created_at=NOW,
        )


def test_review_records_a_binary_decision_and_rationale() -> None:
    review = Review(
        id=ReviewId("review-1"),
        assignment_id=ReviewAssignmentId("assignment-1"),
        reviewer_id=REVIEWER_ID,
        target_contribution_id=ROOT_ID,
        verdict=ReviewVerdict.APPROVE,
        body="This is a recognized field and is not duplicated in the current graph.",
        created_at=NOW,
    )

    assert review.verdict is ReviewVerdict.APPROVE


def test_reputation_event_has_one_source_and_optional_area() -> None:
    event = ReputationEvent(
        id=ReputationEventId("reputation-1"),
        agent_id=AGENT_ID,
        category=ReputationCategory.CURATION,
        delta=5,
        reason="Added and sourced a previously missing open problem.",
        scoring_version="v1",
        created_at=NOW,
        area_id=ROOT_ID,
        source_contribution_id=ContributionId("problem-statement-1"),
    )

    assert event.delta == 5
    assert event.area_id == ROOT_ID


def test_reputation_event_rejects_ambiguous_sources() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        ReputationEvent(
            id=ReputationEventId("reputation-1"),
            agent_id=AGENT_ID,
            category=ReputationCategory.CURATION,
            delta=5,
            reason="Ambiguous source.",
            scoring_version="v1",
            created_at=NOW,
            source_contribution_id=ContributionId("problem-statement-1"),
            source_relation_id=RelationId("relation-1"),
        )


def test_review_can_be_the_source_of_reputation() -> None:
    event = ReputationEvent(
        id=ReputationEventId("reputation-review-1"),
        agent_id=REVIEWER_ID,
        category=ReputationCategory.REVIEWING,
        delta=3,
        reason="The review correctly identified a duplicate problem statement.",
        scoring_version="v1",
        created_at=NOW,
        source_review_id=ReviewId("review-1"),
    )

    assert event.source_review_id == ReviewId("review-1")
