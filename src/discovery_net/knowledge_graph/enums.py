# Enumerations describing knowledge-graph concepts and relationships.

from enum import StrEnum


class ContributionKind(StrEnum):
    """The mathematical or organizational role of a contribution."""

    MATHEMATICAL_AREA = "mathematical_area"
    AXIOM = "axiom"
    DEFINITION = "definition"
    PROBLEM_STATEMENT = "problem_statement"
    CONJECTURE = "conjecture"
    QUESTION = "question"
    FINDING = "finding"
    LEMMA = "lemma"
    THEOREM = "theorem"
    COROLLARY = "corollary"
    PROOF_ATTEMPT = "proof_attempt"
    COUNTEREXAMPLE = "counterexample"
    OBJECTION = "objection"
    REPRODUCTION = "reproduction"
    FORMALIZATION = "formalization"
    SUMMARY = "summary"
    DISCUSSION = "discussion"
    REVIEW_ASSIGNMENT = "review_assignment"
    REVIEW = "review"
    RETRACTION = "retraction"
    ERRATUM = "erratum"


class RelationKind(StrEnum):
    """An attributable claim connecting two contributions."""

    REPLIES_TO = "replies_to"
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
    PROVES = "proves"
    REFUTES = "refutes"
    SUPERSEDES = "supersedes"
    RETRACTS = "retracts"
    CORRECTS = "corrects"
    ENDORSES = "endorses"
