# Defines deterministic transitions over the node-local artifact ledger.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Self

from discovery_net.knowledge_graph import Artifact, ArtifactRef
from discovery_net.wire import SignedEnvelope


class AppendOutcome(StrEnum):
    """The consensus-visible outcome of appending a verified transaction."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifiedTransaction:
    """A signed artifact transaction that passed deterministic validation."""

    artifact_ref: ArtifactRef
    envelope: SignedEnvelope
    artifact: Artifact


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerEntry:
    """A committed artifact transaction with its canonical ledger position."""

    transaction: VerifiedTransaction
    height: int
    transaction_index: int


class LocalArtifactLedger(Protocol):
    """Records verified transactions without signing, broadcasting, or persistence."""

    def contains(self, artifact_ref: ArtifactRef) -> bool: ...

    def append_artifact(
        self,
        transaction: VerifiedTransaction,
    ) -> tuple[Self, AppendOutcome]: ...

    def artifact_refs(self) -> tuple[ArtifactRef, ...]: ...

    def state_hash(self) -> bytes: ...
