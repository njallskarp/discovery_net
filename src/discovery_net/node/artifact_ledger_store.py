# Persists committed artifact-ledger state for node recovery.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerSnapshot:
    """The ordered ledger entries persisted at a committed block height."""

    height: int
    entries: tuple[ArtifactLedgerEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.height, int) or isinstance(self.height, bool):
            raise TypeError("height must be an integer")
        if not 0 <= self.height <= (1 << 63) - 1:
            raise ValueError("height must be a nonnegative signed 64-bit integer")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        if any(not isinstance(entry, ArtifactLedgerEntry) for entry in self.entries):
            raise TypeError("entries must contain ArtifactLedgerEntry values")
        if any(entry.height > self.height for entry in self.entries):
            raise ValueError("entry height must not exceed snapshot height")


class ArtifactLedgerStore(Protocol):
    """Loads and atomically persists artifact-ledger snapshots."""

    def load(self) -> ArtifactLedgerSnapshot | None: ...

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None: ...
