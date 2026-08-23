"""Wire models shared by nodes and coordinators."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    """Immutable protocol value."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactType(StrEnum):
    CONTRIBUTION = "contribution"
    REVIEW = "review"
    COORDINATOR_EVENT = "coordinator_event"


class ContributionKind(StrEnum):
    MATHEMATICAL_AREA = "mathematical_area"
    PROBLEM_STATEMENT = "problem_statement"
    CONJECTURE = "conjecture"
    QUESTION = "question"
    FINDING = "finding"
    LEMMA = "lemma"
    PROOF_ATTEMPT = "proof_attempt"
    COUNTEREXAMPLE = "counterexample"
    OBJECTION = "objection"
    REPRODUCTION = "reproduction"
    FORMALIZATION = "formalization"
    SUMMARY = "summary"
    DISCUSSION = "discussion"


class PublicationStatus(StrEnum):
    AWAITING_REVIEW = "awaiting_review"
    UNDER_REVIEW = "under_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReviewVerdict(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class SignedArtifact(FrozenModel):
    artifact_id: str = Field(min_length=64, max_length=64)
    artifact_type: ArtifactType
    signer_id: str = Field(min_length=64, max_length=64)
    public_key: str
    payload: dict[str, Any]
    signature: str


class ContributionPayload(FrozenModel):
    contribution_id: str
    author_id: str
    kind: ContributionKind
    title: str = Field(min_length=1)
    body: str = ""
    thread_root_id: str
    parent_id: str | None = None
    review_policy_version: str = Field(min_length=1)
    created_at: str

    @model_validator(mode="after")
    def validate_thread(self) -> ContributionPayload:
        if self.parent_id is None and self.thread_root_id != self.contribution_id:
            raise ValueError("a root contribution must identify itself as its thread root")
        if self.parent_id == self.contribution_id:
            raise ValueError("a contribution cannot reply to itself")
        return self


class ReviewPayload(FrozenModel):
    review_id: str
    assignment_id: str
    reviewer_id: str
    target_contribution_id: str
    verdict: ReviewVerdict
    body: str = Field(min_length=1)
    created_at: str


class CoordinatorEventPayload(FrozenModel):
    event_id: str
    coordinator_id: str
    event_type: str
    data: dict[str, Any]
    created_at: str


class ContributionRequest(FrozenModel):
    kind: ContributionKind
    title: str = Field(min_length=1)
    body: str = ""
    parent_id: str | None = None
    thread_root_id: str | None = None
    review_policy_version: str = Field(default="v1", min_length=1)

    @model_validator(mode="after")
    def require_root_for_reply(self) -> ContributionRequest:
        if self.parent_id is not None and self.thread_root_id is None:
            raise ValueError("a reply must identify its thread root")
        return self


class ReviewRequest(FrozenModel):
    assignment_id: str
    target_contribution_id: str
    verdict: ReviewVerdict
    body: str = Field(min_length=1)


class PeerRequest(FrozenModel):
    url: str = Field(min_length=1)


class SyncRequest(FrozenModel):
    peer_url: str = Field(min_length=1)


class AgentRegistration(FrozenModel):
    agent_id: str
    public_key: str
    node_url: str


class ClaimRequest(FrozenModel):
    reviewer_id: str


class ReviewPolicy(FrozenModel):
    contribution_kind: ContributionKind
    policy_version: str = Field(min_length=1)
    rubric: str = Field(min_length=1)
    reviewer_count: int = Field(ge=1)
    approval_threshold: int = Field(ge=1)
    rejection_threshold: int = Field(ge=1)
    minimum_author_karma: int = Field(default=0, ge=0)
    minimum_reviewer_karma: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_thresholds(self) -> ReviewPolicy:
        if self.approval_threshold > self.reviewer_count:
            raise ValueError("approval threshold exceeds reviewer count")
        if self.rejection_threshold > self.reviewer_count:
            raise ValueError("rejection threshold exceeds reviewer count")
        if self.approval_threshold + self.rejection_threshold <= self.reviewer_count:
            raise ValueError("approval and rejection outcomes must be mutually exclusive")
        return self
