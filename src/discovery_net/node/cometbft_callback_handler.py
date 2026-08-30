# Handles CometBFT callbacks for the local Discovery Net node.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from threading import RLock
from typing import Final, final

from discovery_net.node._ledger_from_snapshot import ledger_from_snapshot
from discovery_net.node.application_state import ApplicationStateSnapshot, ApplicationStateStore
from discovery_net.node.local_artifact_ledger import (
    AppendOutcome,
    ArtifactLedgerEntry,
    LocalArtifactLedger,
)
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.node.transaction_validator import (
    TransactionCode,
    TransactionResult,
    TransactionValidator,
)
from discovery_net.node.validator_governance import (
    GovernanceDecision,
    ValidatorGovernanceState,
    ValidatorPowerUpdate,
)
from discovery_net.node.validator_governance_codec import decode_genesis_application_state
from discovery_net.wire import (
    TRANSACTION_LIMITS,
    CodecError,
    TransactionLimitError,
    decode_transaction,
)
from discovery_net.wire.validator_governance import SignedValidatorSetChange
from discovery_net.wire.validator_governance_codec import decode_validator_set_change

_MAX_INT64: Final = (1 << 63) - 1


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizeBlockResult:
    """The deterministic response produced after executing an agreed block."""

    transaction_results: tuple[TransactionResult, ...]
    state_hash: bytes
    validator_updates: tuple[ValidatorPowerUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationHead:
    """The block height and application hash most recently persisted by this node."""

    height: int
    state_hash: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class _PendingBlock:
    height: int
    ledger: LocalArtifactLedger
    validator_governance: ValidatorGovernanceState | None
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
        "_validator_governance",
    )

    def __init__(
        self,
        *,
        validator: TransactionValidator,
        store: ApplicationStateStore,
    ) -> None:
        application_state = store.load()
        if application_state is None:
            committed_height = 0
            committed_ledger = LocalArtifactLedger()
            validator_governance = None
        else:
            committed_height = application_state.height
            committed_ledger = ledger_from_snapshot(application_state.artifact_ledger, validator)
            validator_governance = application_state.validator_governance

        self._validator = validator
        self._store = store
        self._committed_height = committed_height
        self._committed_ledger = committed_ledger
        self._validator_governance = validator_governance
        self._pending_block: _PendingBlock | None = None
        self._lock = RLock()

    def committed_head(self) -> ApplicationHead:
        """Return one consistent view of the latest committed application state."""
        with self._lock:
            return ApplicationHead(
                height=self._committed_height,
                state_hash=_application_state(
                    height=self._committed_height,
                    ledger=self._committed_ledger,
                    validator_governance=self._validator_governance,
                ).state_hash(self._committed_ledger.state_hash()),
            )

    def initialize_chain(
        self,
        *,
        chain_id: str,
        initial_height: int,
        genesis_state: bytes,
        genesis_validators: Sequence[ValidatorPowerUpdate],
    ) -> bytes:
        """Validate this node's supported genesis and return its initial state hash."""
        if not isinstance(chain_id, str):
            raise TypeError("chain_id must be a string")
        _require_block_height(initial_height)
        if not isinstance(genesis_state, bytes):
            raise TypeError("genesis_state must be bytes")
        validator_updates = tuple(genesis_validators)
        if any(not isinstance(update, ValidatorPowerUpdate) for update in validator_updates):
            raise TypeError("genesis_validators must contain ValidatorPowerUpdate values")

        with self._lock:
            if self._committed_height != 0 or self._pending_block is not None:
                raise RuntimeError("chain initialization must precede block execution")
            if chain_id != self._validator.expected_chain_id:
                raise ValueError("chain_id does not match the configured chain")
            if initial_height != 1:
                raise ValueError("only an initial height of 1 is supported")
            if not genesis_state:
                if self._validator_governance is not None:
                    raise ValueError("genesis application state does not match persisted state")
                return self._committed_ledger.state_hash()

            try:
                validator_governance = decode_genesis_application_state(genesis_state)
            except (CodecError, TypeError) as error:
                raise ValueError("genesis application state is not supported") from error
            if not isinstance(validator_governance, ValidatorGovernanceState):
                raise AssertionError("decoded genesis state has an unexpected type")
            if validator_governance.sequence != 0:
                raise ValueError("genesis validator-governance sequence must be zero")
            if tuple(sorted(update.public_key for update in validator_updates)) != (
                validator_governance.validator_public_keys
            ) or any(
                update.voting_power != validator_governance.validator_power
                for update in validator_updates
            ):
                raise ValueError(
                    "genesis validator governance does not match the CometBFT validator set"
                )
            if self._validator_governance is not None:
                if validator_governance != self._validator_governance:
                    raise ValueError("genesis application state does not match persisted state")
            else:
                self._store.save(
                    _application_state(
                        height=0,
                        ledger=self._committed_ledger,
                        validator_governance=validator_governance,
                    )
                )
                self._validator_governance = validator_governance
            return self.committed_head().state_hash

    def check_tx(self, transaction: bytes) -> TransactionResult:
        """Validate a transaction against committed state without changing it."""
        with self._lock:
            result, _ = self._validate_transaction(
                transaction,
                self._committed_ledger,
                self._validator_governance,
            )
            return result

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
            validator_governance = self._validator_governance
            new_entries: list[ArtifactLedgerEntry] = []
            transaction_results: list[TransactionResult] = []
            validator_updates: list[ValidatorPowerUpdate] = []
            updated_validator_keys: set[bytes] = set()

            for transaction_index, transaction in enumerate(transaction_bytes):
                result, governance_transaction = self._validate_transaction(
                    transaction,
                    ledger,
                    validator_governance,
                )
                if governance_transaction is not None and result.code is TransactionCode.ACCEPTED:
                    change_keys = {
                        change.public_key for change in governance_transaction.change.changes
                    }
                    if change_keys & updated_validator_keys:
                        result = TransactionResult(code=TransactionCode.INVALID_VALIDATOR_CHANGE)
                transaction_results.append(result)
                if result.code is not TransactionCode.ACCEPTED:
                    continue

                if governance_transaction is not None:
                    if validator_governance is None:
                        raise AssertionError("governance transaction accepted without governance")
                    decision, transition = validator_governance.evaluate(
                        governance_transaction,
                        expected_chain_id=self._validator.expected_chain_id,
                    )
                    if decision is not GovernanceDecision.ACCEPTED or transition is None:
                        raise RuntimeError("validated governance transaction could not be applied")
                    validator_governance = transition.state
                    validator_updates.extend(transition.validator_updates)
                    updated_validator_keys.update(
                        update.public_key for update in transition.validator_updates
                    )
                    continue

                entry = ArtifactLedgerEntry(
                    transaction=decode_transaction(transaction),
                    height=height,
                    transaction_index=transaction_index,
                )
                ledger, outcome = ledger.append_transaction(entry)
                if outcome is not AppendOutcome.ACCEPTED:
                    raise RuntimeError("validated transaction could not be appended")
                new_entries.append(entry)

            self._pending_block = _PendingBlock(
                height=height,
                ledger=ledger,
                validator_governance=validator_governance,
                new_entries=tuple(new_entries),
            )
            application_state = _application_state(
                height=height,
                ledger=ledger,
                validator_governance=validator_governance,
            )
            return FinalizeBlockResult(
                transaction_results=tuple(transaction_results),
                state_hash=application_state.state_hash(ledger.state_hash()),
                validator_updates=tuple(validator_updates),
            )

    def commit(self) -> tuple[ArtifactLedgerEntry, ...]:
        """Persist and promote the finalized block, returning its new entries."""
        with self._lock:
            pending_block = self._pending_block
            if pending_block is None:
                raise RuntimeError("no finalized block is awaiting commit")

            self._store.save(
                _application_state(
                    height=pending_block.height,
                    ledger=pending_block.ledger,
                    validator_governance=pending_block.validator_governance,
                )
            )
            self._committed_height = pending_block.height
            self._committed_ledger = pending_block.ledger
            self._validator_governance = pending_block.validator_governance
            self._pending_block = None
            return pending_block.new_entries

    def _validate_transaction(
        self,
        transaction: bytes,
        ledger: LocalArtifactLedger,
        validator_governance: ValidatorGovernanceState | None,
    ) -> tuple[TransactionResult, SignedValidatorSetChange | None]:
        try:
            TRANSACTION_LIMITS.require_encoded_size(transaction)
        except TransactionLimitError:
            return TransactionResult(code=TransactionCode.TRANSACTION_TOO_LARGE), None
        except TypeError:
            return TransactionResult(code=TransactionCode.INVALID_TRANSACTION), None

        try:
            governance_transaction = decode_validator_set_change(transaction)
        except (CodecError, TypeError):
            return self._validator.validate(transaction, ledger), None
        if validator_governance is None:
            return (
                TransactionResult(code=TransactionCode.GOVERNANCE_DISABLED),
                governance_transaction,
            )
        decision, _ = validator_governance.evaluate(
            governance_transaction,
            expected_chain_id=self._validator.expected_chain_id,
        )
        return TransactionResult(code=_transaction_code(decision)), governance_transaction


def _application_state(
    *,
    height: int,
    ledger: LocalArtifactLedger,
    validator_governance: ValidatorGovernanceState | None,
) -> ApplicationStateSnapshot:
    return ApplicationStateSnapshot(
        artifact_ledger=ArtifactLedgerSnapshot(height=height, entries=ledger.entries()),
        validator_governance=validator_governance,
    )


def _transaction_code(decision: GovernanceDecision) -> TransactionCode:
    return {
        GovernanceDecision.ACCEPTED: TransactionCode.ACCEPTED,
        GovernanceDecision.WRONG_CHAIN: TransactionCode.WRONG_CHAIN,
        GovernanceDecision.INVALID_SEQUENCE: TransactionCode.INVALID_SEQUENCE,
        GovernanceDecision.UNAUTHORIZED: TransactionCode.UNAUTHORIZED,
        GovernanceDecision.INVALID_SIGNATURE: TransactionCode.INVALID_SIGNATURE,
        GovernanceDecision.INVALID_CHANGE: TransactionCode.INVALID_VALIDATOR_CHANGE,
    }[decision]


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
