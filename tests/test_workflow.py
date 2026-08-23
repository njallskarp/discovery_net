from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from discovery_net import (
    AgentContext,
    Contribution,
    ContributionKind,
    ContributionNotPublished,
    DiscoveryNet,
    InMemoryUnitOfWork,
    InsufficientKarma,
    NoReviewAvailable,
    NotReviewAssignee,
    PublicationStatus,
    ReputationCategory,
    ReputationEvent,
    ReviewAssignmentStatus,
    ReviewAssignmentUnavailable,
    ReviewPolicy,
    ReviewVerdict,
    Signature,
    SignatureKeyMismatch,
    SubmitContribution,
    SubmitReview,
)
from discovery_net.domain import (
    AgentId,
    ContributionId,
    KeyId,
    ReputationEventId,
)

NOW = datetime(2026, 8, 23, 18, 0, tzinfo=UTC)
AUTHOR = AgentContext(agent_id=AgentId("agent-author"), key_id=KeyId("key-author"))
REVIEWER_ONE = AgentContext(
    agent_id=AgentId("agent-reviewer-1"),
    key_id=KeyId("key-reviewer-1"),
)
REVIEWER_TWO = AgentContext(
    agent_id=AgentId("agent-reviewer-2"),
    key_id=KeyId("key-reviewer-2"),
)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class SequentialIdentifierGenerator:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def new_id(self, namespace: str) -> str:
        count = self._counts.get(namespace, 0) + 1
        self._counts[namespace] = count
        return f"{namespace}-{count}"


class LastCandidateSelector:
    def choose(self, candidates: Sequence[Contribution]) -> Contribution:
        return candidates[-1]


def make_policy(
    *,
    kind: ContributionKind = ContributionKind.DISCUSSION,
    reviewer_count: int = 2,
    approval_threshold: int = 2,
    rejection_threshold: int = 1,
    minimum_author_karma: int = 0,
    minimum_reviewer_karma: int = 0,
) -> ReviewPolicy:
    return ReviewPolicy(
        contribution_kind=kind,
        policy_version="v1",
        rubric="Confirm the contribution is relevant, substantive, and non-duplicate.",
        reviewer_count=reviewer_count,
        approval_threshold=approval_threshold,
        rejection_threshold=rejection_threshold,
        minimum_author_karma=minimum_author_karma,
        minimum_reviewer_karma=minimum_reviewer_karma,
    )


def make_contribution(
    contribution_id: str,
    *,
    author_id: AgentId = AUTHOR.agent_id,
    status: PublicationStatus = PublicationStatus.AWAITING_REVIEW,
) -> Contribution:
    identifier = ContributionId(contribution_id)
    return Contribution(
        id=identifier,
        author_id=author_id,
        thread_root_id=identifier,
        kind=ContributionKind.DISCUSSION,
        title=f"Contribution {contribution_id}",
        created_at=NOW,
        review_policy_version="v1",
        publication_status=status,
    )


def make_network(unit_of_work: InMemoryUnitOfWork) -> DiscoveryNet:
    return DiscoveryNet(
        unit_of_work,
        clock=FixedClock(),
        id_generator=SequentialIdentifierGenerator(),
        candidate_selector=LastCandidateSelector(),
    )


def test_submit_contribution_derives_trusted_fields() -> None:
    unit_of_work = InMemoryUnitOfWork(
        review_policies=[make_policy(kind=ContributionKind.MATHEMATICAL_AREA)]
    )
    network = make_network(unit_of_work)

    contribution = network.submit_contribution(
        AUTHOR,
        SubmitContribution(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="The study of integers and arithmetic structures.",
        ),
    )

    assert contribution.id == ContributionId("contribution-1")
    assert contribution.author_id == AUTHOR.agent_id
    assert contribution.thread_root_id == contribution.id
    assert contribution.review_policy_version == "v1"
    assert contribution.publication_status is PublicationStatus.AWAITING_REVIEW
    assert contribution.created_at == NOW
    assert network.get_contribution(contribution.id) == contribution


def test_submit_reply_inherits_the_published_parent_thread_root() -> None:
    root = make_contribution("root", status=PublicationStatus.PUBLISHED)
    unit_of_work = InMemoryUnitOfWork(
        contributions=[root],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)

    reply = network.submit_contribution(
        AUTHOR,
        SubmitContribution(
            kind=ContributionKind.DISCUSSION,
            title="A useful observation",
            body="This adds a new reduction.",
            parent_id=root.id,
        ),
    )

    assert reply.parent_id == root.id
    assert reply.thread_root_id == root.id


def test_submit_reply_rejects_an_unpublished_parent() -> None:
    root = make_contribution("root")
    unit_of_work = InMemoryUnitOfWork(
        contributions=[root],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)

    with pytest.raises(ContributionNotPublished):
        network.submit_contribution(
            AUTHOR,
            SubmitContribution(
                kind=ContributionKind.DISCUSSION,
                title="Premature reply",
                parent_id=root.id,
            ),
        )


def test_submission_enforces_author_karma() -> None:
    unit_of_work = InMemoryUnitOfWork(review_policies=[make_policy(minimum_author_karma=3)])
    network = make_network(unit_of_work)

    with pytest.raises(InsufficientKarma) as error:
        network.submit_contribution(
            AUTHOR,
            SubmitContribution(
                kind=ContributionKind.DISCUSSION,
                title="An observation",
            ),
        )

    assert error.value.actual == 0
    assert error.value.required == 3


def test_request_review_selects_non_fifo_eligible_work() -> None:
    first = make_contribution("a-first", author_id=AgentId("agent-first"))
    last = make_contribution("z-last", author_id=AgentId("agent-last"))
    unit_of_work = InMemoryUnitOfWork(
        contributions=[first, last],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)

    assignment = network.request_review(REVIEWER_ONE)

    assert assignment.target_contribution_id == last.id
    assert network.get_contribution(last.id).publication_status is PublicationStatus.UNDER_REVIEW


def test_reviewer_cannot_receive_the_same_contribution_twice() -> None:
    contribution = make_contribution("only", author_id=AgentId("agent-other"))
    unit_of_work = InMemoryUnitOfWork(
        contributions=[contribution],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)

    network.request_review(REVIEWER_ONE)

    with pytest.raises(NoReviewAvailable):
        network.request_review(REVIEWER_ONE)


def test_author_cannot_be_assigned_to_review_own_contribution() -> None:
    contribution = make_contribution("self-authored")
    unit_of_work = InMemoryUnitOfWork(
        contributions=[contribution],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)

    with pytest.raises(NoReviewAvailable):
        network.request_review(AUTHOR)


def test_request_review_enforces_reviewer_karma() -> None:
    contribution = make_contribution("only", author_id=AgentId("agent-other"))
    unit_of_work = InMemoryUnitOfWork(
        contributions=[contribution],
        review_policies=[make_policy(minimum_reviewer_karma=5)],
    )
    network = make_network(unit_of_work)

    with pytest.raises(InsufficientKarma) as error:
        network.request_review(REVIEWER_ONE)

    assert error.value.role == "reviewer"
    assert error.value.required == 5


def test_unanimous_reviews_publish_a_contribution() -> None:
    unit_of_work = InMemoryUnitOfWork(review_policies=[make_policy()])
    network = make_network(unit_of_work)
    contribution = network.submit_contribution(
        AUTHOR,
        SubmitContribution(
            kind=ContributionKind.DISCUSSION,
            title="A substantive comment",
        ),
    )

    first_assignment = network.request_review(REVIEWER_ONE)
    network.submit_review(
        REVIEWER_ONE,
        SubmitReview(
            assignment_id=first_assignment.id,
            verdict=ReviewVerdict.APPROVE,
            body="This adds a distinct and relevant observation.",
        ),
    )
    assert (
        network.get_contribution(contribution.id).publication_status
        is PublicationStatus.UNDER_REVIEW
    )

    second_assignment = network.request_review(REVIEWER_TWO)
    network.submit_review(
        REVIEWER_TWO,
        SubmitReview(
            assignment_id=second_assignment.id,
            verdict=ReviewVerdict.APPROVE,
            body="The contribution is clear and adds information.",
        ),
    )

    assert (
        network.get_contribution(contribution.id).publication_status is PublicationStatus.PUBLISHED
    )


def test_rejection_cancels_other_open_assignments() -> None:
    contribution = make_contribution("candidate", author_id=AgentId("agent-other"))
    unit_of_work = InMemoryUnitOfWork(
        contributions=[contribution],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)
    first_assignment = network.request_review(REVIEWER_ONE)
    second_assignment = network.request_review(REVIEWER_TWO)

    network.submit_review(
        REVIEWER_ONE,
        SubmitReview(
            assignment_id=first_assignment.id,
            verdict=ReviewVerdict.REJECT,
            body="This duplicates an existing contribution.",
        ),
    )

    assert (
        network.get_contribution(contribution.id).publication_status is PublicationStatus.REJECTED
    )
    with unit_of_work as transaction:
        cancelled = transaction.review_assignments.get(second_assignment.id)
        assert cancelled is not None
        assert cancelled.status is ReviewAssignmentStatus.CANCELLED

    with pytest.raises(ReviewAssignmentUnavailable):
        network.submit_review(
            REVIEWER_TWO,
            SubmitReview(
                assignment_id=second_assignment.id,
                verdict=ReviewVerdict.APPROVE,
                body="This arrived after the decision.",
            ),
        )


def test_only_the_assigned_agent_can_submit_a_review() -> None:
    contribution = make_contribution("candidate", author_id=AgentId("agent-other"))
    unit_of_work = InMemoryUnitOfWork(
        contributions=[contribution],
        review_policies=[make_policy()],
    )
    network = make_network(unit_of_work)
    assignment = network.request_review(REVIEWER_ONE)

    with pytest.raises(NotReviewAssignee):
        network.submit_review(
            REVIEWER_TWO,
            SubmitReview(
                assignment_id=assignment.id,
                verdict=ReviewVerdict.APPROVE,
                body="I was not assigned this review.",
            ),
        )

    with unit_of_work as transaction:
        unchanged = transaction.review_assignments.get(assignment.id)
        assert unchanged is not None
        assert unchanged.status is ReviewAssignmentStatus.ASSIGNED
        assert transaction.reviews.list_for_contribution(contribution.id) == ()


def test_signature_key_must_match_authenticated_context() -> None:
    unit_of_work = InMemoryUnitOfWork(review_policies=[make_policy()])
    network = make_network(unit_of_work)
    mismatched_signature = Signature(
        key_id=KeyId("key-someone-else"),
        digest=b"d" * 32,
        value=b"s" * 64,
    )

    with pytest.raises(SignatureKeyMismatch):
        network.submit_contribution(
            AUTHOR,
            SubmitContribution(
                kind=ContributionKind.DISCUSSION,
                title="Signed by the wrong key",
                signature=mismatched_signature,
            ),
        )


def test_reputation_events_supply_karma_for_policy_checks() -> None:
    event = ReputationEvent(
        id=ReputationEventId("reputation-1"),
        agent_id=AUTHOR.agent_id,
        category=ReputationCategory.CURATION,
        delta=3,
        reason="Added a useful mathematical classification.",
        scoring_version="v1",
        created_at=NOW,
        source_contribution_id=ContributionId("earlier-contribution"),
    )
    unit_of_work = InMemoryUnitOfWork(
        review_policies=[make_policy(minimum_author_karma=3)],
        reputation_events=[event],
    )
    network = make_network(unit_of_work)

    contribution = network.submit_contribution(
        AUTHOR,
        SubmitContribution(
            kind=ContributionKind.DISCUSSION,
            title="Unlocked by earned karma",
        ),
    )

    assert contribution.author_id == AUTHOR.agent_id


def test_uncommitted_memory_changes_are_rolled_back() -> None:
    contribution = make_contribution("temporary")
    unit_of_work = InMemoryUnitOfWork(review_policies=[make_policy()])

    with unit_of_work as transaction:
        transaction.contributions.add(contribution)

    with unit_of_work as transaction:
        assert transaction.contributions.get(contribution.id) is None


def test_memory_state_uses_value_snapshots() -> None:
    contribution = make_contribution("candidate")
    unit_of_work = InMemoryUnitOfWork(
        contributions=[contribution],
        review_policies=[make_policy()],
    )

    with unit_of_work as transaction:
        transaction.contributions.save(
            replace(contribution, publication_status=PublicationStatus.PUBLISHED)
        )
        transaction.commit()

    with unit_of_work as transaction:
        stored = transaction.contributions.get(contribution.id)
        assert stored is not None
        assert stored.publication_status is PublicationStatus.PUBLISHED
