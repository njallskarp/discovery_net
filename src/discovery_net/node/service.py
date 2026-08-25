# Coordinates the components required to run a network node.

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from discovery_net.knowledge_graph import ArtifactRef
from discovery_net.ledger import (
    ArtifactLedgerEntry,
    LocalArtifactLedger,
)
from discovery_net.wire import SignedEnvelope


@dataclass(frozen=True, slots=True, kw_only=True)
class TransactionResult:
    """The deterministic application result for one transaction."""

    code: int
    artifact_ref: ArtifactRef | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizeBlockResult:
    """The pending application result produced for an agreed block."""

    height: int
    ledger: LocalArtifactLedger
    transaction_results: tuple[TransactionResult, ...]
    accepted_envelopes: tuple[SignedEnvelope, ...]
    state_hash: bytes


class DiscoveryApplication(Protocol):
    """Processes transactions delivered by a local CometBFT node."""

    def check_tx(self, transaction: bytes) -> TransactionResult: ...

    def finalize_block(
        self,
        *,
        height: int,
        transactions: Sequence[bytes],
    ) -> FinalizeBlockResult: ...

    def commit(self) -> tuple[ArtifactLedgerEntry, ...]: ...
