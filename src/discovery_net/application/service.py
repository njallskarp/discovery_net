"""Agent-facing workflows for submitting and reviewing contributions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from discovery_net.application.commands import SubmitContribution, SubmitReview
from discovery_net.application.context import AgentContext
from discovery_net.application.errors import (
    ContributionNotFound,
    ContributionNotPublished,
    InsufficientKarma,
    NoReviewAvailable,
    NotReviewAssignee,
    ReviewAssignmentNotFound,
    ReviewAssignmentUnavailable,
    ReviewPolicyNotFound,
    SignatureKeyMismatch,
)
from discovery_net.application.runtime import (
    CandidateSelector,
    Clock,
    IdentifierGenerator,
    RandomCandidateSelector,
    SystemClock,
    UuidIdentifierGenerator,
)
from discovery_net.domain import (
    Contribution,
    ContributionId,
    PublicationStatus,
    Review,
    ReviewAssignment,
    ReviewAssignmentId,
    ReviewAssignmentStatus,
    ReviewId,
    ReviewPolicy,
    ReviewVerdict,
    Signature,
)
from discovery_net.repositories.protocols import UnitOfWork


class DiscoveryNet:
    """A persistence-independent facade over the contribution review workflow."""

    def __init__(
        self,
        unit_of_work: UnitOfWork,
        *,
        clock: Clock | None = None,
        id_generator: IdentifierGenerator | None = None,
        candidate_selector: CandidateSelector | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UuidIdentifierGenerator()
        self._candidate_selector = candidate_selector or RandomCandidateSelector()

    def submit_contribution(
        self,
        context: AgentContext,
        command: SubmitContribution,
    ) -> Contribution:
        self._require_context_key(context, command.signature)

        with self._unit_of_work as unit_of_work:
            policy = unit_of_work.review_policies.get_active(command.kind)
            if policy is None:
                raise ReviewPolicyNotFound(command.kind, None)

            author_karma = unit_of_work.reputation.total_for_agent(context.agent_id)
            if author_karma < policy.minimum_author_karma:
                raise InsufficientKarma(
                    agent_id=context.agent_id,
                    role="author",
                    actual=author_karma,
                    required=policy.minimum_author_karma,
                )

            contribution_id = ContributionId(self._id_generator.new_id("contribution"))
            thread_root_id = contribution_id
            if command.parent_id is not None:
                parent = unit_of_work.contributions.get(command.parent_id)
                if parent is None:
                    raise ContributionNotFound(command.parent_id)
                if parent.publication_status is not PublicationStatus.PUBLISHED:
                    raise ContributionNotPublished(parent.id)
                thread_root_id = parent.thread_root_id

            contribution = Contribution(
                id=contribution_id,
                author_id=context.agent_id,
                thread_root_id=thread_root_id,
                parent_id=command.parent_id,
                kind=command.kind,
                title=command.title,
                body=command.body,
                references=command.references,
                created_at=self._clock.now(),
                review_policy_version=policy.policy_version,
                signature=command.signature,
            )
            unit_of_work.contributions.add(contribution)
            unit_of_work.commit()
            return contribution

    def request_review(self, context: AgentContext) -> ReviewAssignment:
        with self._unit_of_work as unit_of_work:
            reviewer_karma = unit_of_work.reputation.total_for_agent(context.agent_id)
            candidates: list[Contribution] = []
            inaccessible_karma_levels: list[int] = []

            for contribution in unit_of_work.contributions.list_reviewable():
                if contribution.author_id == context.agent_id:
                    continue

                policy = self._get_policy(unit_of_work, contribution)
                assignments = unit_of_work.review_assignments.list_for_contribution(contribution.id)
                if any(assignment.reviewer_id == context.agent_id for assignment in assignments):
                    continue

                occupied_slots = sum(
                    assignment.status
                    in {
                        ReviewAssignmentStatus.ASSIGNED,
                        ReviewAssignmentStatus.COMPLETED,
                    }
                    for assignment in assignments
                )
                if occupied_slots >= policy.reviewer_count:
                    continue
                if reviewer_karma < policy.minimum_reviewer_karma:
                    inaccessible_karma_levels.append(policy.minimum_reviewer_karma)
                    continue
                candidates.append(contribution)

            if not candidates:
                if inaccessible_karma_levels:
                    raise InsufficientKarma(
                        agent_id=context.agent_id,
                        role="reviewer",
                        actual=reviewer_karma,
                        required=min(inaccessible_karma_levels),
                    )
                raise NoReviewAvailable(context.agent_id)

            contribution = self._candidate_selector.choose(candidates)
            assignment = ReviewAssignment(
                id=ReviewAssignmentId(self._id_generator.new_id("review_assignment")),
                target_contribution_id=contribution.id,
                target_author_id=contribution.author_id,
                reviewer_id=context.agent_id,
                assigned_at=self._clock.now(),
            )
            unit_of_work.review_assignments.add(assignment)
            if contribution.publication_status is PublicationStatus.AWAITING_REVIEW:
                unit_of_work.contributions.save(
                    replace(
                        contribution,
                        publication_status=PublicationStatus.UNDER_REVIEW,
                    )
                )
            unit_of_work.commit()
            return assignment

    def submit_review(self, context: AgentContext, command: SubmitReview) -> Review:
        self._require_context_key(context, command.signature)

        with self._unit_of_work as unit_of_work:
            assignment = unit_of_work.review_assignments.get(command.assignment_id)
            if assignment is None:
                raise ReviewAssignmentNotFound(command.assignment_id)
            if assignment.reviewer_id != context.agent_id:
                raise NotReviewAssignee(assignment.id, context.agent_id)
            if assignment.status is not ReviewAssignmentStatus.ASSIGNED:
                raise ReviewAssignmentUnavailable(assignment.id)

            contribution = unit_of_work.contributions.get(assignment.target_contribution_id)
            if contribution is None:
                raise ContributionNotFound(assignment.target_contribution_id)
            if contribution.publication_status not in {
                PublicationStatus.AWAITING_REVIEW,
                PublicationStatus.UNDER_REVIEW,
            }:
                raise ReviewAssignmentUnavailable(assignment.id)

            policy = self._get_policy(unit_of_work, contribution)
            reviewed_at = self._clock.now()
            review = Review(
                id=ReviewId(self._id_generator.new_id("review")),
                assignment_id=assignment.id,
                reviewer_id=context.agent_id,
                target_contribution_id=contribution.id,
                verdict=command.verdict,
                body=command.body,
                created_at=reviewed_at,
                signature=command.signature,
            )
            unit_of_work.reviews.add(review)
            unit_of_work.review_assignments.save(
                replace(
                    assignment,
                    status=ReviewAssignmentStatus.COMPLETED,
                    resolved_at=reviewed_at,
                    review_id=review.id,
                )
            )

            reviews = unit_of_work.reviews.list_for_contribution(contribution.id)
            approvals = sum(review.verdict is ReviewVerdict.APPROVE for review in reviews)
            rejections = sum(review.verdict is ReviewVerdict.REJECT for review in reviews)
            if approvals >= policy.approval_threshold:
                publication_status = PublicationStatus.PUBLISHED
            elif rejections >= policy.rejection_threshold:
                publication_status = PublicationStatus.REJECTED
            else:
                publication_status = PublicationStatus.UNDER_REVIEW

            unit_of_work.contributions.save(
                replace(contribution, publication_status=publication_status)
            )
            if publication_status in {
                PublicationStatus.PUBLISHED,
                PublicationStatus.REJECTED,
            }:
                self._cancel_open_assignments(
                    unit_of_work,
                    contribution.id,
                    completed_assignment_id=assignment.id,
                    resolved_at=reviewed_at,
                )
            unit_of_work.commit()
            return review

    def get_contribution(self, contribution_id: ContributionId) -> Contribution:
        with self._unit_of_work as unit_of_work:
            contribution = unit_of_work.contributions.get(contribution_id)
            if contribution is None:
                raise ContributionNotFound(contribution_id)
            return contribution

    @staticmethod
    def _get_policy(unit_of_work: UnitOfWork, contribution: Contribution) -> ReviewPolicy:
        policy = unit_of_work.review_policies.get_version(
            contribution.kind,
            contribution.review_policy_version,
        )
        if policy is None:
            raise ReviewPolicyNotFound(
                contribution.kind,
                contribution.review_policy_version,
            )
        return policy

    @staticmethod
    def _cancel_open_assignments(
        unit_of_work: UnitOfWork,
        contribution_id: ContributionId,
        *,
        completed_assignment_id: ReviewAssignmentId,
        resolved_at: datetime,
    ) -> None:
        for assignment in unit_of_work.review_assignments.list_for_contribution(contribution_id):
            if (
                assignment.id != completed_assignment_id
                and assignment.status is ReviewAssignmentStatus.ASSIGNED
            ):
                unit_of_work.review_assignments.save(
                    replace(
                        assignment,
                        status=ReviewAssignmentStatus.CANCELLED,
                        resolved_at=resolved_at,
                    )
                )

    @staticmethod
    def _require_context_key(context: AgentContext, signature: Signature | None) -> None:
        if signature is not None and signature.key_id != context.key_id:
            raise SignatureKeyMismatch()
