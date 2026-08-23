"""Immutable, persistence-independent domain dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from discovery_net.domain.enums import (
    ContributionKind,
    EpistemicStatus,
    HashAlgorithm,
    ModerationStatus,
    PublicationStatus,
    RelationKind,
    ReputationCategory,
    ReviewAssignmentStatus,
    ReviewVerdict,
    SignatureAlgorithm,
)
from discovery_net.domain.identifiers import (
    AgentId,
    ContributionId,
    KeyId,
    RelationId,
    ReputationEventId,
    ReviewAssignmentId,
    ReviewId,
)


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_optional_non_blank(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_blank(value, field_name)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExternalReference:
    """A namespaced identifier or source outside discovery_net."""

    namespace: str
    identifier: str
    url: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.namespace, "namespace")
        _require_non_blank(self.identifier, "identifier")
        _require_optional_non_blank(self.url, "url")
        _require_optional_non_blank(self.label, "label")


@dataclass(frozen=True, slots=True, kw_only=True)
class Signature:
    """A raw signature over a canonical payload digest."""

    key_id: KeyId
    digest: bytes
    value: bytes
    algorithm: SignatureAlgorithm = SignatureAlgorithm.ED25519
    hash_algorithm: HashAlgorithm = HashAlgorithm.SHA256

    def __post_init__(self) -> None:
        _require_non_blank(self.key_id, "key_id")
        if self.hash_algorithm is HashAlgorithm.SHA256 and len(self.digest) != 32:
            raise ValueError("a SHA-256 digest must be exactly 32 bytes")
        if self.algorithm is SignatureAlgorithm.ED25519 and len(self.value) != 64:
            raise ValueError("a raw Ed25519 signature must be exactly 64 bytes")


@dataclass(frozen=True, slots=True, kw_only=True)
class Agent:
    """A persistent participant in the research network."""

    id: AgentId
    display_name: str
    created_at: datetime
    bio: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.display_name, "display_name")
        _require_aware(self.created_at, "created_at")
        _require_optional_non_blank(self.bio, "bio")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentKey:
    """A raw public key associated with an agent identity."""

    id: KeyId
    agent_id: AgentId
    public_key: bytes
    created_at: datetime
    algorithm: SignatureAlgorithm = SignatureAlgorithm.ED25519
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.agent_id, "agent_id")
        _require_aware(self.created_at, "created_at")
        if self.algorithm is SignatureAlgorithm.ED25519 and len(self.public_key) != 32:
            raise ValueError("a raw Ed25519 public key must be exactly 32 bytes")
        if self.revoked_at is not None:
            _require_aware(self.revoked_at, "revoked_at")
            if self.revoked_at < self.created_at:
                raise ValueError("revoked_at must not precede created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class Contribution:
    """A signed mathematical, conversational, or organizational artifact."""

    id: ContributionId
    author_id: AgentId
    thread_root_id: ContributionId
    kind: ContributionKind
    title: str
    created_at: datetime
    review_policy_version: str
    body: str = ""
    parent_id: ContributionId | None = None
    references: tuple[ExternalReference, ...] = ()
    publication_status: PublicationStatus = PublicationStatus.AWAITING_REVIEW
    epistemic_status: EpistemicStatus = EpistemicStatus.UNASSESSED
    moderation_status: ModerationStatus = ModerationStatus.VISIBLE
    signature: Signature | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.author_id, "author_id")
        _require_non_blank(self.thread_root_id, "thread_root_id")
        _require_non_blank(self.title, "title")
        _require_non_blank(self.review_policy_version, "review_policy_version")
        _require_aware(self.created_at, "created_at")

        if self.parent_id is None:
            if self.thread_root_id != self.id:
                raise ValueError("a root contribution must identify itself as thread_root_id")
        else:
            _require_non_blank(self.parent_id, "parent_id")
            if self.parent_id == self.id:
                raise ValueError("a contribution cannot reply to itself")
            if self.thread_root_id == self.id:
                raise ValueError("a reply cannot identify itself as the thread root")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionRelation:
    """An attributable edge connecting two contributions."""

    id: RelationId
    author_id: AgentId
    source_id: ContributionId
    target_id: ContributionId
    kind: RelationKind
    created_at: datetime
    signature: Signature | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.author_id, "author_id")
        _require_non_blank(self.source_id, "source_id")
        _require_non_blank(self.target_id, "target_id")
        _require_aware(self.created_at, "created_at")
        if self.source_id == self.target_id:
            raise ValueError("a relation must connect two distinct contributions")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewPolicy:
    """Versioned admission requirements for one kind of contribution."""

    contribution_kind: ContributionKind
    policy_version: str
    rubric: str
    reviewer_count: int
    approval_threshold: int
    rejection_threshold: int
    minimum_author_karma: int = 0
    minimum_reviewer_karma: int = 0

    def __post_init__(self) -> None:
        _require_non_blank(self.policy_version, "policy_version")
        _require_non_blank(self.rubric, "rubric")
        if self.reviewer_count < 1:
            raise ValueError("reviewer_count must be positive")
        if not 1 <= self.approval_threshold <= self.reviewer_count:
            raise ValueError("approval_threshold must be between 1 and reviewer_count")
        if not 1 <= self.rejection_threshold <= self.reviewer_count:
            raise ValueError("rejection_threshold must be between 1 and reviewer_count")
        if self.approval_threshold + self.rejection_threshold <= self.reviewer_count:
            raise ValueError("approval and rejection thresholds must be mutually exclusive")
        if self.minimum_author_karma < 0:
            raise ValueError("minimum_author_karma must not be negative")
        if self.minimum_reviewer_karma < 0:
            raise ValueError("minimum_reviewer_karma must not be negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewAssignment:
    """A system-selected reviewer and the contribution assigned to them."""

    id: ReviewAssignmentId
    target_contribution_id: ContributionId
    target_author_id: AgentId
    reviewer_id: AgentId
    assigned_at: datetime
    status: ReviewAssignmentStatus = ReviewAssignmentStatus.ASSIGNED
    resolved_at: datetime | None = None
    review_id: ReviewId | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.target_contribution_id, "target_contribution_id")
        _require_non_blank(self.target_author_id, "target_author_id")
        _require_non_blank(self.reviewer_id, "reviewer_id")
        _require_aware(self.assigned_at, "assigned_at")
        if self.reviewer_id == self.target_author_id:
            raise ValueError("an agent cannot review its own contribution")
        if self.resolved_at is not None:
            _require_aware(self.resolved_at, "resolved_at")
            if self.resolved_at < self.assigned_at:
                raise ValueError("resolved_at must not precede assigned_at")

        if self.status is ReviewAssignmentStatus.ASSIGNED:
            if self.resolved_at is not None or self.review_id is not None:
                raise ValueError("an assigned review must not be resolved")
        elif self.status is ReviewAssignmentStatus.COMPLETED:
            if self.resolved_at is None or self.review_id is None:
                raise ValueError("a completed assignment requires a review and resolution time")
            _require_non_blank(self.review_id, "review_id")
        else:
            if self.resolved_at is None or self.review_id is not None:
                raise ValueError("an expired or cancelled assignment must resolve without a review")


@dataclass(frozen=True, slots=True, kw_only=True)
class Review:
    """A signed admission decision with a textual rationale."""

    id: ReviewId
    assignment_id: ReviewAssignmentId
    reviewer_id: AgentId
    target_contribution_id: ContributionId
    verdict: ReviewVerdict
    body: str
    created_at: datetime
    signature: Signature | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.assignment_id, "assignment_id")
        _require_non_blank(self.reviewer_id, "reviewer_id")
        _require_non_blank(self.target_contribution_id, "target_contribution_id")
        if not self.body.strip():
            raise ValueError("a review must have a textual body")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReputationEvent:
    """An immutable change in one dimension of an agent's reputation."""

    id: ReputationEventId
    agent_id: AgentId
    category: ReputationCategory
    delta: int
    reason: str
    scoring_version: str
    created_at: datetime
    area_id: ContributionId | None = None
    source_contribution_id: ContributionId | None = None
    source_relation_id: RelationId | None = None
    source_review_id: ReviewId | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.agent_id, "agent_id")
        _require_non_blank(self.reason, "reason")
        _require_non_blank(self.scoring_version, "scoring_version")
        _require_aware(self.created_at, "created_at")
        if self.delta == 0:
            raise ValueError("a reputation event delta must be non-zero")
        if self.area_id is not None:
            _require_non_blank(self.area_id, "area_id")
        sources = (
            self.source_contribution_id,
            self.source_relation_id,
            self.source_review_id,
        )
        if sum(source is not None for source in sources) != 1:
            raise ValueError("a reputation event must identify exactly one source artifact")
