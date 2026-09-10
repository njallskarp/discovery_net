# Composes committed artifacts and validator governance into one atomic application state.

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final, Protocol

from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.node.validator_governance import ValidatorGovernanceState

_APPLICATION_HASH_DOMAIN: Final = b"discovery-net:application-state:\x00"


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationStateSnapshot:
    """The artifact ledger and governance state at one committed block height."""

    artifact_ledger: ArtifactLedgerSnapshot
    validator_governance: ValidatorGovernanceState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_ledger, ArtifactLedgerSnapshot):
            raise TypeError("artifact_ledger must be an ArtifactLedgerSnapshot")
        if self.validator_governance is not None and not isinstance(
            self.validator_governance, ValidatorGovernanceState
        ):
            raise TypeError("validator_governance must be a ValidatorGovernanceState or None")

    @property
    def height(self) -> int:
        """Return the block height shared by all committed application state."""
        return self.artifact_ledger.height

    def state_hash(self, artifact_state_hash: bytes) -> bytes:
        """Commit to governance when enabled while preserving legacy chain hashes."""
        if not isinstance(artifact_state_hash, bytes):
            raise TypeError("artifact_state_hash must be bytes")
        if self.validator_governance is None:
            return artifact_state_hash
        return sha256(
            _APPLICATION_HASH_DOMAIN + artifact_state_hash + self.validator_governance.state_hash()
        ).digest()


class ApplicationStateStore(Protocol):
    """Loads and atomically persists all consensus-visible application state."""

    def load(self) -> ApplicationStateSnapshot | None: ...

    def save(self, snapshot: ApplicationStateSnapshot) -> None: ...
