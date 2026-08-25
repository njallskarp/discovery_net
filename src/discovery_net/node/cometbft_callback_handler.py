# Handles CometBFT callbacks for the local Discovery Net node.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from threading import RLock
from typing import Final, final

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

_MAX_INT64: Final = (1 << 63) - 1


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizeBlockResult:
    """The deterministic response produced after executing an agreed block."""

    transaction_results: tuple[TransactionResult, ...]
    state_hash: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerHead:
    """The block height and state hash most recently persisted by this node."""

    height: int
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

    def committed_head(self) -> ArtifactLedgerHead:
        """Return one consistent view of the latest committed ledger state."""
        with self._lock:
            return ArtifactLedgerHead(
                height=self._committed_height,
                state_hash=self._committed_ledger.state_hash(),
            )

    def initialize_chain(
        self,
        *,
        chain_id: str,
        initial_height: int,
        genesis_state: bytes,
    ) -> bytes:
        """Validate this node's supported genesis and return its initial state hash."""
        if not isinstance(chain_id, str):
            raise TypeError("chain_id must be a string")
        _require_block_height(initial_height)
        if not isinstance(genesis_state, bytes):
            raise TypeError("genesis_state must be bytes")

        with self._lock:
            if self._committed_height != 0 or self._pending_block is not None:
                raise RuntimeError("chain initialization must precede block execution")
            if chain_id != self._validator.expected_chain_id:
                raise ValueError("chain_id does not match the configured chain")
            if initial_height != 1:
                raise ValueError("only an initial height of 1 is supported")
            if genesis_state:
                raise ValueError("genesis application state is not supported")
            return self._committed_ledger.state_hash()

    def check_tx(self, transaction: bytes) -> TransactionResult:
        """Validate a transaction against committed state without changing it."""
        with self._lock:
            return self._validator.validate(transaction, self._committed_ledger)

    def prepare_proposal(
        self,
        *,
        transactions: Sequence[bytes],
        maximum_transaction_bytes: int,
    ) -> tuple[bytes, ...]:
        """Return the longest transaction prefix within the proposal byte limit."""
        _require_nonnegative_int64(maximum_transaction_bytes, "maximum_transaction_bytes")
        transaction_bytes = _transaction_bytes(transactions)
        selected: list[bytes] = []
        selected_size = 0

        for transaction in transaction_bytes:
            selected_size += len(transaction)
            if selected_size > maximum_transaction_bytes:
                break
            selected.append(transaction)

        return tuple(selected)

    def finalize_block(
        self,
        *,
        height: int,
        transactions: Sequence[bytes],
    ) -> FinalizeBlockResult:
        """Execute one decided block into pending, unpersisted state."""
        _require_block_height(height)
        transaction_bytes = _transaction_bytes(transactions)

        with self._lock:
            if self._pending_block is not None:
                raise RuntimeError("a finalized block is already awaiting commit")
            if height != self._committed_height + 1:
                raise ValueError("height must immediately follow the committed height")

            ledger = self._committed_ledger
            new_entries: list[ArtifactLedgerEntry] = []
            transaction_results: list[TransactionResult] = []

            for transaction_index, transaction in enumerate(transaction_bytes):
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
    if not 1 <= height <= _MAX_INT64:
        raise ValueError("height must be between 1 and the maximum signed 64-bit integer")


def _require_nonnegative_int64(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if not 0 <= value <= _MAX_INT64:
        raise ValueError(f"{field_name} must be a nonnegative signed 64-bit integer")


def _transaction_bytes(transactions: Sequence[bytes]) -> tuple[bytes, ...]:
    transaction_bytes = tuple(transactions)
    if any(not isinstance(transaction, bytes) for transaction in transaction_bytes):
        raise TypeError("transactions must contain bytes")
    return transaction_bytes
