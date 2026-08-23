"""Typed, untrusted inputs accepted by the application service."""

from dataclasses import dataclass

from discovery_net.domain import (
    ContributionId,
    ContributionKind,
    ExternalReference,
    ReviewAssignmentId,
    ReviewVerdict,
    Signature,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitContribution:
    """Agent-supplied fields for a new contribution."""

    kind: ContributionKind
    title: str
    body: str = ""
    parent_id: ContributionId | None = None
    references: tuple[ExternalReference, ...] = ()
    signature: Signature | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if self.parent_id is not None and not self.parent_id.strip():
            raise ValueError("parent_id must not be blank")


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitReview:
    """Agent-supplied fields for completing an assigned review."""

    assignment_id: ReviewAssignmentId
    verdict: ReviewVerdict
    body: str
    signature: Signature | None = None

    def __post_init__(self) -> None:
        if not self.assignment_id.strip():
            raise ValueError("assignment_id must not be blank")
        if not self.body.strip():
            raise ValueError("body must not be blank")
