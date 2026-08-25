# Persists committed artifact-ledger state for node recovery.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerSnapshot:
    """The ordered ledger entries persisted at a committed block height."""

    height: int
    entries: tuple[ArtifactLedgerEntry, ...]


class ArtifactLedgerStore(Protocol):
    """Loads and atomically persists artifact-ledger snapshots."""

    def load(self) -> ArtifactLedgerSnapshot | None: ...

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None: ...
