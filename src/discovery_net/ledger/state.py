# Defines deterministic transitions over the accepted artifact ledger.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from discovery_net.knowledge_graph import Artifact, ArtifactRef
from discovery_net.wire import SignedEnvelope


class ApplyStatus(StrEnum):
    """The consensus-visible outcome of applying a validated artifact."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatedArtifact:
    """A signed artifact that passed deterministic transaction validation."""

    artifact_ref: ArtifactRef
    envelope: SignedEnvelope
    artifact: Artifact


@dataclass(frozen=True, slots=True, kw_only=True)
class CommittedArtifact:
    """An accepted artifact with its canonical position in the ledger."""

    validated_artifact: ValidatedArtifact
    height: int
    transaction_index: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplyResult:
    """The deterministic result of one ledger-state transition."""

    state: LedgerState
    status: ApplyStatus
    artifact_ref: ArtifactRef


class LedgerState(Protocol):
    """Applies validated artifacts without signing, broadcasting, or persistence."""

    def contains(self, artifact_ref: ArtifactRef) -> bool: ...

    def apply(self, artifact: ValidatedArtifact) -> ApplyResult: ...

    def accepted_refs(self) -> tuple[ArtifactRef, ...]: ...

    def app_hash(self) -> bytes: ...
