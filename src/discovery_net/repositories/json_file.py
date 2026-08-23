"""JSON-file persistence for the discovery_net workflow."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from discovery_net.domain import (
    AgentId,
    Contribution,
    ContributionId,
    ContributionKind,
    EpistemicStatus,
    ExternalReference,
    HashAlgorithm,
    KeyId,
    ModerationStatus,
    PublicationStatus,
    RelationId,
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
    SignatureAlgorithm,
)
from discovery_net.repositories.memory import InMemoryUnitOfWork

JsonObject = dict[str, Any]


def _encode_reference(reference: ExternalReference) -> JsonObject:
    return {
        "namespace": reference.namespace,
        "identifier": reference.identifier,
        "url": reference.url,
        "label": reference.label,
    }


def _decode_reference(data: JsonObject) -> ExternalReference:
    return ExternalReference(
        namespace=data["namespace"],
        identifier=data["identifier"],
        url=data["url"],
        label=data["label"],
    )


def _encode_signature(signature: Signature | None) -> JsonObject | None:
    if signature is None:
        return None
    return {
        "key_id": signature.key_id,
        "digest": signature.digest.hex(),
        "value": signature.value.hex(),
        "algorithm": signature.algorithm.value,
        "hash_algorithm": signature.hash_algorithm.value,
    }


def _decode_signature(data: JsonObject | None) -> Signature | None:
    if data is None:
        return None
    return Signature(
        key_id=KeyId(data["key_id"]),
        digest=bytes.fromhex(data["digest"]),
        value=bytes.fromhex(data["value"]),
        algorithm=SignatureAlgorithm(data["algorithm"]),
        hash_algorithm=HashAlgorithm(data["hash_algorithm"]),
    )


def _encode_contribution(contribution: Contribution) -> JsonObject:
    return {
        "id": contribution.id,
        "author_id": contribution.author_id,
        "thread_root_id": contribution.thread_root_id,
        "kind": contribution.kind.value,
        "title": contribution.title,
        "created_at": contribution.created_at.isoformat(),
        "review_policy_version": contribution.review_policy_version,
        "body": contribution.body,
        "parent_id": contribution.parent_id,
        "references": [_encode_reference(reference) for reference in contribution.references],
        "publication_status": contribution.publication_status.value,
        "epistemic_status": contribution.epistemic_status.value,
        "moderation_status": contribution.moderation_status.value,
        "signature": _encode_signature(contribution.signature),
    }


def _decode_contribution(data: JsonObject) -> Contribution:
    parent_id = data["parent_id"]
    return Contribution(
        id=ContributionId(data["id"]),
        author_id=AgentId(data["author_id"]),
        thread_root_id=ContributionId(data["thread_root_id"]),
        kind=ContributionKind(data["kind"]),
        title=data["title"],
        created_at=datetime.fromisoformat(data["created_at"]),
        review_policy_version=data["review_policy_version"],
        body=data["body"],
        parent_id=ContributionId(parent_id) if parent_id is not None else None,
        references=tuple(_decode_reference(reference) for reference in data["references"]),
        publication_status=PublicationStatus(data["publication_status"]),
        epistemic_status=EpistemicStatus(data["epistemic_status"]),
        moderation_status=ModerationStatus(data["moderation_status"]),
        signature=_decode_signature(data["signature"]),
    )


def _encode_review_policy(policy: ReviewPolicy) -> JsonObject:
    return {
        "contribution_kind": policy.contribution_kind.value,
        "policy_version": policy.policy_version,
        "rubric": policy.rubric,
        "reviewer_count": policy.reviewer_count,
        "approval_threshold": policy.approval_threshold,
        "rejection_threshold": policy.rejection_threshold,
        "minimum_author_karma": policy.minimum_author_karma,
        "minimum_reviewer_karma": policy.minimum_reviewer_karma,
    }


def _decode_review_policy(data: JsonObject) -> ReviewPolicy:
    return ReviewPolicy(
        contribution_kind=ContributionKind(data["contribution_kind"]),
        policy_version=data["policy_version"],
        rubric=data["rubric"],
        reviewer_count=data["reviewer_count"],
        approval_threshold=data["approval_threshold"],
        rejection_threshold=data["rejection_threshold"],
        minimum_author_karma=data["minimum_author_karma"],
        minimum_reviewer_karma=data["minimum_reviewer_karma"],
    )


def _encode_review_assignment(assignment: ReviewAssignment) -> JsonObject:
    return {
        "id": assignment.id,
        "target_contribution_id": assignment.target_contribution_id,
        "target_author_id": assignment.target_author_id,
        "reviewer_id": assignment.reviewer_id,
        "assigned_at": assignment.assigned_at.isoformat(),
        "status": assignment.status.value,
        "resolved_at": (
            assignment.resolved_at.isoformat() if assignment.resolved_at is not None else None
        ),
        "review_id": assignment.review_id,
    }


def _decode_review_assignment(data: JsonObject) -> ReviewAssignment:
    resolved_at = data["resolved_at"]
    review_id = data["review_id"]
    return ReviewAssignment(
        id=ReviewAssignmentId(data["id"]),
        target_contribution_id=ContributionId(data["target_contribution_id"]),
        target_author_id=AgentId(data["target_author_id"]),
        reviewer_id=AgentId(data["reviewer_id"]),
        assigned_at=datetime.fromisoformat(data["assigned_at"]),
        status=ReviewAssignmentStatus(data["status"]),
        resolved_at=datetime.fromisoformat(resolved_at) if resolved_at is not None else None,
        review_id=ReviewId(review_id) if review_id is not None else None,
    )


def _encode_review(review: Review) -> JsonObject:
    return {
        "id": review.id,
        "assignment_id": review.assignment_id,
        "reviewer_id": review.reviewer_id,
        "target_contribution_id": review.target_contribution_id,
        "verdict": review.verdict.value,
        "body": review.body,
        "created_at": review.created_at.isoformat(),
        "signature": _encode_signature(review.signature),
    }


def _decode_review(data: JsonObject) -> Review:
    return Review(
        id=ReviewId(data["id"]),
        assignment_id=ReviewAssignmentId(data["assignment_id"]),
        reviewer_id=AgentId(data["reviewer_id"]),
        target_contribution_id=ContributionId(data["target_contribution_id"]),
        verdict=ReviewVerdict(data["verdict"]),
        body=data["body"],
        created_at=datetime.fromisoformat(data["created_at"]),
        signature=_decode_signature(data["signature"]),
    )


def _encode_reputation_event(event: ReputationEvent) -> JsonObject:
    return {
        "id": event.id,
        "agent_id": event.agent_id,
        "category": event.category.value,
        "delta": event.delta,
        "reason": event.reason,
        "scoring_version": event.scoring_version,
        "created_at": event.created_at.isoformat(),
        "area_id": event.area_id,
        "source_contribution_id": event.source_contribution_id,
        "source_relation_id": event.source_relation_id,
        "source_review_id": event.source_review_id,
    }


def _decode_reputation_event(data: JsonObject) -> ReputationEvent:
    area_id = data["area_id"]
    source_contribution_id = data["source_contribution_id"]
    source_relation_id = data["source_relation_id"]
    source_review_id = data["source_review_id"]
    return ReputationEvent(
        id=ReputationEventId(data["id"]),
        agent_id=AgentId(data["agent_id"]),
        category=ReputationCategory(data["category"]),
        delta=data["delta"],
        reason=data["reason"],
        scoring_version=data["scoring_version"],
        created_at=datetime.fromisoformat(data["created_at"]),
        area_id=ContributionId(area_id) if area_id is not None else None,
        source_contribution_id=(
            ContributionId(source_contribution_id) if source_contribution_id is not None else None
        ),
        source_relation_id=(
            RelationId(source_relation_id) if source_relation_id is not None else None
        ),
        source_review_id=ReviewId(source_review_id) if source_review_id is not None else None,
    )


class JsonUnitOfWork(InMemoryUnitOfWork):
    """Persist committed in-memory state to one human-readable JSON file."""

    def __init__(
        self,
        path: str | Path,
        *,
        contributions: Iterable[Contribution] = (),
        review_policies: Iterable[ReviewPolicy] = (),
        review_assignments: Iterable[ReviewAssignment] = (),
        reviews: Iterable[Review] = (),
        reputation_events: Iterable[ReputationEvent] = (),
    ) -> None:
        self._path = Path(path)
        if self._path.exists():
            data: JsonObject = json.loads(self._path.read_text(encoding="utf-8"))
            contributions = (_decode_contribution(item) for item in data.get("contributions", []))
            review_policies = (
                _decode_review_policy(item) for item in data.get("review_policies", [])
            )
            review_assignments = (
                _decode_review_assignment(item) for item in data.get("review_assignments", [])
            )
            reviews = (_decode_review(item) for item in data.get("reviews", []))
            reputation_events = (
                _decode_reputation_event(item) for item in data.get("reputation_events", [])
            )
        super().__init__(
            contributions=contributions,
            review_policies=review_policies,
            review_assignments=review_assignments,
            reviews=reviews,
            reputation_events=reputation_events,
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        should_write = exc_type is None and self._committed
        super().__exit__(exc_type, exc_value, traceback)
        if should_write:
            self._write()

    def _write(self) -> None:
        data = {
            "contributions": [
                _encode_contribution(contribution)
                for contribution in self._state.contributions.values()
            ],
            "review_policies": [
                _encode_review_policy(policy) for policy in self._state.review_policies.values()
            ],
            "review_assignments": [
                _encode_review_assignment(assignment)
                for assignment in self._state.review_assignments.values()
            ],
            "reviews": [_encode_review(review) for review in self._state.reviews.values()],
            "reputation_events": [
                _encode_reputation_event(event) for event in self._state.reputation_events.values()
            ],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
