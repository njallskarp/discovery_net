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
    REVIEW_ASSIGNMENT = "review_assignment"
    REVIEW = "review"


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
