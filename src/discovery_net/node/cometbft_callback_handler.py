# Handles CometBFT callbacks for the local Discovery Net node.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from threading import RLock
from typing import final

from discovery_net.node._ledger_from_snapshot import ledger_from_snapshot
from discovery_net.node.local_artifact_ledger import (
    AppendOutcome,
    ArtifactLedgerEntry,
    LocalArtifactLedger,
)
from discovery_net.node.store.artifact_ledger_store import (
    ArtifactLedgerSnapshot,
    ArtifactLedgerStore,
)
from discovery_net.node.transaction_validator import (
    TransactionCode,
    TransactionResult,
    TransactionValidator,
)
from discovery_net.wire import decode_envelope


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizeBlockResult:
    """The deterministic response produced after executing an agreed block."""

    transaction_results: tuple[TransactionResult, ...]
    state_hash: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class _PendingBlock:
    height: int
    ledger: LocalArtifactLedger
    new_entries: tuple[ArtifactLedgerEntry, ...]


@final
class CometBFTCallbackHandler:
    """Coordinates validation, block execution, and atomic state commitment."""

    __slots__ = (
        "_committed_height",
        "_committed_ledger",
        "_lock",
        "_pending_block",
        "_store",
        "_validator",
    )

    def __init__(
        self,
        *,
        validator: TransactionValidator,
        store: ArtifactLedgerStore,
    ) -> None:
        snapshot = store.load()
        if snapshot is None:
            committed_height = 0
            committed_ledger = LocalArtifactLedger()
        else:
            committed_height = snapshot.height
            committed_ledger = ledger_from_snapshot(snapshot, validator)

        self._validator = validator
        self._store = store
        self._committed_height = committed_height
        self._committed_ledger = committed_ledger
        self._pending_block: _PendingBlock | None = None
        self._lock = RLock()

    def check_tx(self, transaction: bytes) -> TransactionResult:
        """Validate a transaction against committed state without changing it."""
        with self._lock:
            return self._validator.validate(transaction, self._committed_ledger)

    def finalize_block(
        self,
        *,
        height: int,
        transactions: Sequence[bytes],
    ) -> FinalizeBlockResult:
        """Execute one decided block into pending, unpersisted state."""
        _require_block_height(height)

        with self._lock:
            if self._pending_block is not None:
                raise RuntimeError("a finalized block is already awaiting commit")
            if height != self._committed_height + 1:
                raise ValueError("height must immediately follow the committed height")

            ledger = self._committed_ledger
            new_entries: list[ArtifactLedgerEntry] = []
            transaction_results: list[TransactionResult] = []

            for transaction_index, transaction in enumerate(tuple(transactions)):
                result = self._validator.validate(transaction, ledger)
                transaction_results.append(result)
                if result.code is not TransactionCode.ACCEPTED:
                    continue

                entry = ArtifactLedgerEntry(
                    envelope=decode_envelope(transaction),
                    height=height,
                    transaction_index=transaction_index,
                )
                ledger, outcome = ledger.append_artifact(entry)
                if outcome is not AppendOutcome.ACCEPTED:
                    raise RuntimeError("validated transaction could not be appended")
                new_entries.append(entry)

            self._pending_block = _PendingBlock(
                height=height,
                ledger=ledger,
                new_entries=tuple(new_entries),
            )
            return FinalizeBlockResult(
                transaction_results=tuple(transaction_results),
                state_hash=ledger.state_hash(),
            )

    def commit(self) -> tuple[ArtifactLedgerEntry, ...]:
        """Persist and promote the finalized block, returning its new entries."""
        with self._lock:
            pending_block = self._pending_block
            if pending_block is None:
                raise RuntimeError("no finalized block is awaiting commit")

            self._store.save(
                ArtifactLedgerSnapshot(
                    height=pending_block.height,
                    entries=pending_block.ledger.entries(),
                )
            )
            self._committed_height = pending_block.height
            self._committed_ledger = pending_block.ledger
            self._pending_block = None
            return pending_block.new_entries


def _require_block_height(height: int) -> None:
    if not isinstance(height, int) or isinstance(height, bool):
        raise TypeError("height must be an integer")
    if not 1 <= height <= (1 << 63) - 1:
        raise ValueError("height must be between 1 and the maximum signed 64-bit integer")
