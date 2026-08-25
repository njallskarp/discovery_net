# Handles CometBFT callbacks for the local Discovery Net node.

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionResult:
    """The deterministic application result for one transaction."""

    code: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizeBlockResult:
    """The deterministic response produced after executing an agreed block."""

    transaction_results: tuple[TransactionResult, ...]
    state_hash: bytes


class CometBFTCallbackHandler(Protocol):
    """Handles CometBFT callbacks that validate transactions and advance local state."""

    def check_tx(self, transaction: bytes) -> TransactionResult: ...

    def finalize_block(
        self,
        *,
        height: int,
        transactions: Sequence[bytes],
    ) -> FinalizeBlockResult: ...

    def commit(self) -> tuple[ArtifactLedgerEntry, ...]: ...
