from datetime import UTC, datetime
from pathlib import Path

from discovery_net import (
    AgentContext,
    Contribution,
    ContributionKind,
    DiscoveryNet,
    ExternalReference,
    JsonUnitOfWork,
    PublicationStatus,
    ReputationCategory,
    ReputationEvent,
    ReviewAssignmentStatus,
    ReviewPolicy,
    ReviewVerdict,
    Signature,
    SubmitContribution,
    SubmitReview,
)
from discovery_net.domain import (
    AgentId,
    ContributionId,
    KeyId,
    ReputationEventId,
)

NOW = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
AUTHOR = AgentContext(agent_id=AgentId("agent-author"), key_id=KeyId("key-author"))
REVIEWER = AgentContext(agent_id=AgentId("agent-reviewer"), key_id=KeyId("key-reviewer"))


class FixedClock:
    def now(self) -> datetime:
        return NOW


def make_policy() -> ReviewPolicy:
    return ReviewPolicy(
        contribution_kind=ContributionKind.MATHEMATICAL_AREA,
        policy_version="v1",
        rubric="Confirm this is a real, non-duplicate mathematical area.",
        reviewer_count=1,
        approval_threshold=1,
        rejection_threshold=1,
    )


def test_json_workflow_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "discovery_net.json"
    signature = Signature(
        key_id=AUTHOR.key_id,
        digest=b"d" * 32,
        value=b"s" * 64,
    )
    network = DiscoveryNet(
        JsonUnitOfWork(path, review_policies=[make_policy()]),
        clock=FixedClock(),
    )
    contribution = network.submit_contribution(
        AUTHOR,
        SubmitContribution(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="The study of integers and arithmetic structures.",
            references=(
                ExternalReference(
                    namespace="msc",
                    identifier="11",
                    label="Number theory",
                ),
            ),
            signature=signature,
        ),
    )

    reopened = JsonUnitOfWork(path)
    network = DiscoveryNet(reopened, clock=FixedClock())
    loaded = network.get_contribution(contribution.id)
    assert loaded == contribution
    assert loaded.signature == signature
    assert loaded.references[0].identifier == "11"

    assignment = network.request_review(REVIEWER)
    review = network.submit_review(
        REVIEWER,
        SubmitReview(
            assignment_id=assignment.id,
            verdict=ReviewVerdict.APPROVE,
            body="This is a recognized mathematical area and is not duplicated.",
        ),
    )

    reopened = JsonUnitOfWork(path)
    network = DiscoveryNet(reopened, clock=FixedClock())
    assert (
        network.get_contribution(contribution.id).publication_status is PublicationStatus.PUBLISHED
    )
    with reopened as transaction:
        assignments = transaction.review_assignments.list_for_contribution(contribution.id)
        reviews = transaction.reviews.list_for_contribution(contribution.id)
        assert assignments[0].status is ReviewAssignmentStatus.COMPLETED
        assert reviews == (review,)


def test_json_repository_persists_reputation_events(tmp_path: Path) -> None:
    path = tmp_path / "discovery_net.json"
    event = ReputationEvent(
        id=ReputationEventId("reputation-1"),
        agent_id=AUTHOR.agent_id,
        category=ReputationCategory.CURATION,
        delta=4,
        reason="Added a useful area classification.",
        scoring_version="v1",
        created_at=NOW,
        source_contribution_id=ContributionId("contribution-1"),
    )
    unit_of_work = JsonUnitOfWork(path, reputation_events=[event])
    with unit_of_work as transaction:
        transaction.commit()

    with JsonUnitOfWork(path) as reopened:
        assert reopened.reputation.total_for_agent(AUTHOR.agent_id) == 4


def test_json_repository_does_not_write_uncommitted_changes(tmp_path: Path) -> None:
    path = tmp_path / "discovery_net.json"
    identifier = ContributionId("temporary")
    contribution = Contribution(
        id=identifier,
        author_id=AUTHOR.agent_id,
        thread_root_id=identifier,
        kind=ContributionKind.MATHEMATICAL_AREA,
        title="Temporary area",
        created_at=NOW,
        review_policy_version="v1",
    )
    unit_of_work = JsonUnitOfWork(path, review_policies=[make_policy()])

    with unit_of_work as transaction:
        transaction.contributions.add(contribution)

    assert not path.exists()
