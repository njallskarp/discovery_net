"""Enumerations used by the discovery_net domain model."""

from enum import StrEnum


class ContributionKind(StrEnum):
    """The mathematical or organizational role of a contribution."""

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


class RelationKind(StrEnum):
    """An attributable claim connecting two contributions."""

    SUBAREA_OF = "subarea_of"
    ABOUT = "about"
    HAS_APPLICATION_IN = "has_application_in"
    DUPLICATE_OF = "duplicate_of"
    VARIANT_OF = "variant_of"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    REFINES = "refines"
    GENERALIZES = "generalizes"
    SPECIALIZES = "specializes"
    CITES = "cites"
    REPRODUCES = "reproduces"
    FORMALIZES = "formalizes"
    VERIFIES = "verifies"


class PublicationStatus(StrEnum):
    """A contribution's position in the admission workflow."""

    AWAITING_REVIEW = "awaiting_review"
    UNDER_REVIEW = "under_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class EpistemicStatus(StrEnum):
    """A derived summary of the mathematical evidence for a contribution."""

    UNASSESSED = "unassessed"
    DISPUTED = "disputed"
    CORROBORATED = "corroborated"
    COMPUTATIONALLY_REPRODUCED = "computationally_reproduced"
    FORMALLY_VERIFIED = "formally_verified"
    REFUTED = "refuted"


class ModerationStatus(StrEnum):
    """Whether community-safety rules allow an artifact to be displayed."""

    VISIBLE = "visible"
    QUARANTINED = "quarantined"
    HIDDEN = "hidden"


class ReviewAssignmentStatus(StrEnum):
    """The state of one system-issued review assignment."""

    ASSIGNED = "assigned"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ReviewVerdict(StrEnum):
    """A reviewer's decision in the contribution admission workflow."""

    APPROVE = "approve"
    REJECT = "reject"


class ReputationCategory(StrEnum):
    """Independent dimensions of earned reputation."""

    DISCOVERY = "discovery"
    REVIEWING = "reviewing"
    REPRODUCTION = "reproduction"
    FORMALIZATION = "formalization"
    CURATION = "curation"


class SignatureAlgorithm(StrEnum):
    """Supported contribution-signing algorithms."""

    ED25519 = "ed25519"


class HashAlgorithm(StrEnum):
    """Supported content-digest algorithms."""

    SHA256 = "sha256"
