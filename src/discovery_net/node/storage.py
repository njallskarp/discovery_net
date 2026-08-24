# Persists committed ledger state for node recovery.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.ledger import LedgerState


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredLedgerState:
    """The latest atomically persisted application state."""

    height: int
    state: LedgerState


class LedgerStore(Protocol):
    """Loads and atomically persists committed ledger state."""

    def load(self) -> StoredLedgerState | None: ...

    def save(self, stored_state: StoredLedgerState) -> None: ...
