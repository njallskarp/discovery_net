"""Transactional in-memory repositories for tests and local use."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self

from discovery_net.domain import (
    AgentId,
    Contribution,
    ContributionId,
    ContributionKind,
    PublicationStatus,
    ReputationEvent,
    ReputationEventId,
    Review,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewId,
    ReviewPolicy,
)
from discovery_net.repositories.protocols import (
    ContributionRepository,
    ReputationRepository,
    ReviewAssignmentRepository,
    ReviewPolicyRepository,
    ReviewRepository,
)


@dataclass(slots=True)
class _MemoryState:
    contributions: dict[ContributionId, Contribution] = field(default_factory=dict)
    review_policies: dict[tuple[ContributionKind, str], ReviewPolicy] = field(default_factory=dict)
    active_policy_versions: dict[ContributionKind, str] = field(default_factory=dict)
    review_assignments: dict[ReviewAssignmentId, ReviewAssignment] = field(default_factory=dict)
    reviews: dict[ReviewId, Review] = field(default_factory=dict)
    reputation_events: dict[ReputationEventId, ReputationEvent] = field(default_factory=dict)


def _insert_unique[Identifier, Value](
    values: dict[Identifier, Value],
    identifier: Identifier,
    value: Value,
    artifact_name: str,
) -> None:
    if identifier in values:
        raise ValueError(f"{artifact_name} {identifier!r} already exists")
    values[identifier] = value


class _MemoryContributionRepository(ContributionRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def add(self, contribution: Contribution) -> None:
        _insert_unique(
            self._state.contributions,
            contribution.id,
            contribution,
            "contribution",
        )

    def get(self, contribution_id: ContributionId) -> Contribution | None:
        return self._state.contributions.get(contribution_id)

    def save(self, contribution: Contribution) -> None:
        if contribution.id not in self._state.contributions:
            raise ValueError(f"contribution {contribution.id!r} does not exist")
        self._state.contributions[contribution.id] = contribution

    def list_reviewable(self) -> tuple[Contribution, ...]:
        reviewable_statuses = {
            PublicationStatus.AWAITING_REVIEW,
            PublicationStatus.UNDER_REVIEW,
        }
        return tuple(
            sorted(
                (
                    contribution
                    for contribution in self._state.contributions.values()
                    if contribution.publication_status in reviewable_statuses
                ),
                key=lambda contribution: (contribution.created_at, contribution.id),
            )
        )


class _MemoryReviewPolicyRepository(ReviewPolicyRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def get_active(self, contribution_kind: ContributionKind) -> ReviewPolicy | None:
        policy_version = self._state.active_policy_versions.get(contribution_kind)
        if policy_version is None:
            return None
        return self.get_version(contribution_kind, policy_version)

    def get_version(
        self,
        contribution_kind: ContributionKind,
        policy_version: str,
    ) -> ReviewPolicy | None:
        return self._state.review_policies.get((contribution_kind, policy_version))


class _MemoryReviewAssignmentRepository(ReviewAssignmentRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def add(self, assignment: ReviewAssignment) -> None:
        _insert_unique(
            self._state.review_assignments,
            assignment.id,
            assignment,
            "review assignment",
        )

    def get(self, assignment_id: ReviewAssignmentId) -> ReviewAssignment | None:
        return self._state.review_assignments.get(assignment_id)

    def save(self, assignment: ReviewAssignment) -> None:
        if assignment.id not in self._state.review_assignments:
            raise ValueError(f"review assignment {assignment.id!r} does not exist")
        self._state.review_assignments[assignment.id] = assignment

    def list_for_contribution(
        self,
        contribution_id: ContributionId,
    ) -> tuple[ReviewAssignment, ...]:
        return tuple(
            sorted(
                (
                    assignment
                    for assignment in self._state.review_assignments.values()
                    if assignment.target_contribution_id == contribution_id
                ),
                key=lambda assignment: (assignment.assigned_at, assignment.id),
            )
        )


class _MemoryReviewRepository(ReviewRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def add(self, review: Review) -> None:
        _insert_unique(self._state.reviews, review.id, review, "review")

    def list_for_contribution(self, contribution_id: ContributionId) -> tuple[Review, ...]:
        return tuple(
            sorted(
                (
                    review
                    for review in self._state.reviews.values()
                    if review.target_contribution_id == contribution_id
                ),
                key=lambda review: (review.created_at, review.id),
            )
        )


class _MemoryReputationRepository(ReputationRepository):
    def __init__(self, state: _MemoryState) -> None:
        self._state = state

    def add(self, event: ReputationEvent) -> None:
        _insert_unique(self._state.reputation_events, event.id, event, "reputation event")

    def total_for_agent(self, agent_id: AgentId) -> int:
        return sum(
            event.delta
            for event in self._state.reputation_events.values()
            if event.agent_id == agent_id
        )


class InMemoryUnitOfWork:
    """Copy-on-write unit of work whose commits are atomic within one process."""

    def __init__(
        self,
        *,
        contributions: Iterable[Contribution] = (),
        review_policies: Iterable[ReviewPolicy] = (),
        review_assignments: Iterable[ReviewAssignment] = (),
        reviews: Iterable[Review] = (),
        reputation_events: Iterable[ReputationEvent] = (),
    ) -> None:
        self._state = _MemoryState()
        self._working_state: _MemoryState | None = None
        self._committed = False
        self._contributions: ContributionRepository | None = None
        self._review_policies: ReviewPolicyRepository | None = None
        self._review_assignments: ReviewAssignmentRepository | None = None
        self._reviews: ReviewRepository | None = None
        self._reputation: ReputationRepository | None = None

        for contribution in contributions:
            _insert_unique(
                self._state.contributions,
                contribution.id,
                contribution,
                "contribution",
            )
        for policy in review_policies:
            key = (policy.contribution_kind, policy.policy_version)
            _insert_unique(self._state.review_policies, key, policy, "review policy")
            self._state.active_policy_versions[policy.contribution_kind] = policy.policy_version
        for assignment in review_assignments:
            _insert_unique(
                self._state.review_assignments,
                assignment.id,
                assignment,
                "review assignment",
            )
        for review in reviews:
            _insert_unique(self._state.reviews, review.id, review, "review")
        for event in reputation_events:
            _insert_unique(
                self._state.reputation_events,
                event.id,
                event,
                "reputation event",
            )

    @property
    def contributions(self) -> ContributionRepository:
        if self._contributions is None:
            raise RuntimeError("unit of work has not been entered")
        return self._contributions

    @property
    def review_policies(self) -> ReviewPolicyRepository:
        if self._review_policies is None:
            raise RuntimeError("unit of work has not been entered")
        return self._review_policies

    @property
    def review_assignments(self) -> ReviewAssignmentRepository:
        if self._review_assignments is None:
            raise RuntimeError("unit of work has not been entered")
        return self._review_assignments

    @property
    def reviews(self) -> ReviewRepository:
        if self._reviews is None:
            raise RuntimeError("unit of work has not been entered")
        return self._reviews

    @property
    def reputation(self) -> ReputationRepository:
        if self._reputation is None:
            raise RuntimeError("unit of work has not been entered")
        return self._reputation

    def __enter__(self) -> Self:
        if self._working_state is not None:
            raise RuntimeError("unit of work is already active")
        self._working_state = deepcopy(self._state)
        self._committed = False
        self._contributions = _MemoryContributionRepository(self._working_state)
        self._review_policies = _MemoryReviewPolicyRepository(self._working_state)
        self._review_assignments = _MemoryReviewAssignmentRepository(self._working_state)
        self._reviews = _MemoryReviewRepository(self._working_state)
        self._reputation = _MemoryReputationRepository(self._working_state)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is None and self._committed:
            if self._working_state is None:
                raise RuntimeError("unit of work has not been entered")
            self._state = self._working_state
        self._working_state = None
        self._committed = False
        self._contributions = None
        self._review_policies = None
        self._review_assignments = None
        self._reviews = None
        self._reputation = None

    def commit(self) -> None:
        if self._working_state is None:
            raise RuntimeError("unit of work has not been entered")
        self._committed = True
