# Defines deterministic transitions over the node-local artifact ledger.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Self

from discovery_net.knowledge_graph import ArtifactRef
from discovery_net.wire import SignedEnvelope


class AppendOutcome(StrEnum):
    """The consensus-visible outcome of appending a verified envelope."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerEntry:
    """A signed envelope paired with its consensus-assigned block position."""

    envelope: SignedEnvelope
    height: int
    transaction_index: int


class ArtifactLedgerLookup(Protocol):
    """Looks up artifacts already recorded in committed ledger state."""

    def contains(self, artifact_ref: ArtifactRef) -> bool:
        """Return whether an artifact has already been recorded."""
        ...


class LocalArtifactLedger(ArtifactLedgerLookup, Protocol):
    """Maintains the ordered artifact entries accepted by this node."""

    def append_artifact(
        self,
        entry: ArtifactLedgerEntry,
    ) -> tuple[Self, AppendOutcome]:
        """Return the resulting ledger and append outcome."""
        ...

    def entries(self) -> tuple[ArtifactLedgerEntry, ...]:
        """Return entries in canonical ledger order."""
        ...

    def state_hash(self) -> bytes:
        """Return the deterministic hash of the current ledger state."""
        ...
