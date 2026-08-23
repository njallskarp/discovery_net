"""Persistence contracts required by the application layer."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from discovery_net.domain import (
    AgentId,
    Contribution,
    ContributionId,
    ContributionKind,
    ReputationEvent,
    Review,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewPolicy,
)


class ContributionRepository(Protocol):
    def add(self, contribution: Contribution) -> None: ...

    def get(self, contribution_id: ContributionId) -> Contribution | None: ...

    def save(self, contribution: Contribution) -> None: ...

    def list_reviewable(self) -> tuple[Contribution, ...]: ...


class ReviewPolicyRepository(Protocol):
    def get_active(self, contribution_kind: ContributionKind) -> ReviewPolicy | None: ...

    def get_version(
        self,
        contribution_kind: ContributionKind,
        policy_version: str,
    ) -> ReviewPolicy | None: ...


class ReviewAssignmentRepository(Protocol):
    def add(self, assignment: ReviewAssignment) -> None: ...

    def get(self, assignment_id: ReviewAssignmentId) -> ReviewAssignment | None: ...

    def save(self, assignment: ReviewAssignment) -> None: ...

    def list_for_contribution(
        self,
        contribution_id: ContributionId,
    ) -> tuple[ReviewAssignment, ...]: ...


class ReviewRepository(Protocol):
    def add(self, review: Review) -> None: ...

    def list_for_contribution(self, contribution_id: ContributionId) -> tuple[Review, ...]: ...


class ReputationRepository(Protocol):
    def add(self, event: ReputationEvent) -> None: ...

    def total_for_agent(self, agent_id: AgentId) -> int: ...


class UnitOfWork(Protocol):
    @property
    def contributions(self) -> ContributionRepository: ...

    @property
    def review_policies(self) -> ReviewPolicyRepository: ...

    @property
    def review_assignments(self) -> ReviewAssignmentRepository: ...

    @property
    def reviews(self) -> ReviewRepository: ...

    @property
    def reputation(self) -> ReputationRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...
