# Defines the read-only sources consumed by the inspector service.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.inspector.models import NodeObservation
from discovery_net.node import ArtifactLedgerEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerUpdate:
    """New ledger entries together with the committed height they advance to."""

    height: int
    entries: tuple[ArtifactLedgerEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.height, int) or isinstance(self.height, bool):
            raise TypeError("height must be an integer")
        if self.height < 0:
            raise ValueError("height must be nonnegative")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        if any(not isinstance(entry, ArtifactLedgerEntry) for entry in self.entries):
            raise TypeError("entries must contain ArtifactLedgerEntry values")
        if any(entry.height > self.height for entry in self.entries):
            raise ValueError("entry height must not exceed the committed height")


class NodeObservationSource(Protocol):
    """Observes the current state of one local consensus node."""

    def observe(self) -> NodeObservation: ...


class ArtifactLedgerReader(Protocol):
    """Reads newly committed artifact-ledger entries without mutation."""

    def updates_after(self, height: int) -> ArtifactLedgerUpdate: ...
