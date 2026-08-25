# Defines deterministic transitions over the node-local artifact ledger.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Self

from discovery_net.knowledge_graph import Artifact, ArtifactRef
from discovery_net.wire import SignedEnvelope


class AppendOutcome(StrEnum):
    """The consensus-visible outcome of appending a verified artifact."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifiedArtifact:
    """A signed artifact that passed deterministic transaction validation."""

    artifact_ref: ArtifactRef
    envelope: SignedEnvelope
    artifact: Artifact


@dataclass(frozen=True, slots=True, kw_only=True)
class AcceptedArtifact:
    """An artifact accepted while executing an agreed block."""

    verified_artifact: VerifiedArtifact
    height: int
    transaction_index: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CommittedArtifact:
    """An accepted artifact made durable by Commit."""

    accepted_artifact: AcceptedArtifact


class LocalArtifactLedger(Protocol):
    """Records verified artifacts without signing, broadcasting, or persistence."""

    def contains(self, artifact_ref: ArtifactRef) -> bool: ...

    def append_artifact(
        self,
        artifact: VerifiedArtifact,
    ) -> tuple[Self, AppendOutcome]: ...

    def artifact_refs(self) -> tuple[ArtifactRef, ...]: ...

    def state_hash(self) -> bytes: ...
