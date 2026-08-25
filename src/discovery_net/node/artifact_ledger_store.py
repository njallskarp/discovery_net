# Persists committed artifact-ledger state for node recovery.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.node.local_artifact_ledger import LocalArtifactLedger


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerSnapshot:
    """The artifact ledger persisted at a committed block height."""

    height: int
    ledger: LocalArtifactLedger


class ArtifactLedgerStore(Protocol):
    """Loads and atomically persists artifact-ledger snapshots."""

    def load(self) -> ArtifactLedgerSnapshot | None: ...

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None: ...
