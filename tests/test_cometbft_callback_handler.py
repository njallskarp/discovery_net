from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import (
    AppendOutcome,
    ArtifactLedgerEntry,
    ArtifactLedgerHead,
    ArtifactLedgerSnapshot,
    CometBFTCallbackHandler,
    FinalizeBlockResult,
    LocalArtifactLedger,
    TransactionCode,
    TransactionResult,
    TransactionValidator,
)
from discovery_net.wire import SignedEnvelope, decode_envelope, encode_envelope, sign_artifact

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


@dataclass(slots=True)
class MemoryArtifactLedgerStore:
    snapshot: ArtifactLedgerSnapshot | None = None
    failures_remaining: int = 0
    save_calls: int = 0
    saved_snapshots: list[ArtifactLedgerSnapshot] = field(default_factory=list)

    def load(self) -> ArtifactLedgerSnapshot | None:
        return self.snapshot

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None:
        self.save_calls += 1
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise OSError("persistence failed")
        self.snapshot = snapshot
        self.saved_snapshots.append(snapshot)


def signed_envelope(
    title: str,
    *,
    chain_id: str = CHAIN_ID,
) -> SignedEnvelope:
    return sign_artifact(
        chain_id=chain_id,
        artifact=Contribution(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title=title,
            body=f"Body for {title}",
            created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
        ),
        private_key=PRIVATE_KEY,
    )


def transaction(title: str, *, chain_id: str = CHAIN_ID) -> bytes:
    return encode_envelope(signed_envelope(title, chain_id=chain_id))


def callback_handler(
    store: MemoryArtifactLedgerStore | None = None,
) -> tuple[CometBFTCallbackHandler, MemoryArtifactLedgerStore]:
    artifact_store = store if store is not None else MemoryArtifactLedgerStore()
    return (
        CometBFTCallbackHandler(
            validator=TransactionValidator(expected_chain_id=CHAIN_ID),
            store=artifact_store,
        ),
        artifact_store,
    )


def invalid_signature_transaction(title: str) -> bytes:
    return encode_envelope(replace(signed_envelope(title), signature=bytes(64)))


def test_check_tx_reads_committed_state_without_mutation() -> None:
    handler, store = callback_handler()
    encoded = transaction("First")

    assert handler.check_tx(encoded) == TransactionResult(code=TransactionCode.ACCEPTED)
    assert handler.check_tx(encoded) == TransactionResult(code=TransactionCode.ACCEPTED)
    assert store.save_calls == 0
    assert store.snapshot is None


def test_committed_head_changes_only_after_successful_commit() -> None:
    handler, _ = callback_handler()
    initial_head = ArtifactLedgerHead(
        height=0,
        state_hash=LocalArtifactLedger().state_hash(),
    )

    assert handler.committed_head() == initial_head

    finalized = handler.finalize_block(height=1, transactions=(transaction("First"),))

    assert handler.committed_head() == initial_head

    handler.commit()

    assert handler.committed_head() == ArtifactLedgerHead(
        height=1,
        state_hash=finalized.state_hash,
    )


def test_finalize_block_executes_transactions_in_order_without_persisting() -> None:
    handler, store = callback_handler()
    first = transaction("First")
    second = transaction("Second")
    transactions = (
        first,
        b"not-json",
        transaction("Wrong chain", chain_id="discovery-net-mainnet"),
        invalid_signature_transaction("Invalid signature"),
        first,
        second,
    )

    result = handler.finalize_block(height=1, transactions=transactions)

    expected_ledger = LocalArtifactLedger()
    for transaction_index in (0, 5):
        expected_ledger, outcome = expected_ledger.append_artifact(
            ArtifactLedgerEntry(
                envelope=decode_envelope(transactions[transaction_index]),
                height=1,
                transaction_index=transaction_index,
            )
        )
        assert outcome is AppendOutcome.ACCEPTED

    assert result == FinalizeBlockResult(
        transaction_results=(
            TransactionResult(code=TransactionCode.ACCEPTED),
            TransactionResult(code=TransactionCode.INVALID_ENVELOPE),
            TransactionResult(code=TransactionCode.WRONG_CHAIN),
            TransactionResult(code=TransactionCode.INVALID_SIGNATURE),
            TransactionResult(code=TransactionCode.DUPLICATE),
            TransactionResult(code=TransactionCode.ACCEPTED),
        ),
        state_hash=expected_ledger.state_hash(),
    )
    assert store.save_calls == 0
    assert store.snapshot is None
    assert handler.check_tx(first) == TransactionResult(code=TransactionCode.ACCEPTED)


def test_commit_persists_then_promotes_pending_state() -> None:
    handler, store = callback_handler()
    encoded = transaction("First")
    handler.finalize_block(height=1, transactions=(encoded,))

    committed_entries = handler.commit()

    assert len(committed_entries) == 1
    assert committed_entries[0] == ArtifactLedgerEntry(
        envelope=decode_envelope(encoded),
        height=1,
        transaction_index=0,
    )
    assert store.snapshot == ArtifactLedgerSnapshot(height=1, entries=committed_entries)
    assert handler.check_tx(encoded) == TransactionResult(code=TransactionCode.DUPLICATE)


def test_empty_block_advances_committed_height_without_changing_state_hash() -> None:
    handler, store = callback_handler()
    empty_hash = LocalArtifactLedger().state_hash()

    result = handler.finalize_block(height=1, transactions=())

    assert result == FinalizeBlockResult(transaction_results=(), state_hash=empty_hash)
    assert handler.commit() == ()
    assert store.snapshot == ArtifactLedgerSnapshot(height=1, entries=())

    next_result = handler.finalize_block(height=2, transactions=())
    assert next_result.state_hash == empty_hash


def test_handler_enforces_finalize_and_commit_sequence() -> None:
    handler, _ = callback_handler()

    with pytest.raises(RuntimeError, match="no finalized block"):
        handler.commit()
    with pytest.raises(ValueError, match="immediately follow"):
        handler.finalize_block(height=2, transactions=())

    handler.finalize_block(height=1, transactions=())
    with pytest.raises(RuntimeError, match="already awaiting commit"):
        handler.finalize_block(height=1, transactions=())

    handler.commit()
    with pytest.raises(ValueError, match="immediately follow"):
        handler.finalize_block(height=1, transactions=())
    with pytest.raises(ValueError, match="immediately follow"):
        handler.finalize_block(height=3, transactions=())


@pytest.mark.parametrize("height", [0, -1, 1 << 63])
def test_finalize_block_rejects_height_outside_cometbft_range(height: int) -> None:
    handler, _ = callback_handler()

    with pytest.raises(ValueError, match="height"):
        handler.finalize_block(height=height, transactions=())


@pytest.mark.parametrize("height", [True, "1"])
def test_finalize_block_requires_an_integer_height(height: object) -> None:
    handler, _ = callback_handler()

    with pytest.raises(TypeError, match="height must be an integer"):
        handler.finalize_block(height=height, transactions=())  # type: ignore[arg-type]


def test_failed_persistence_preserves_pending_and_committed_state_for_retry() -> None:
    store = MemoryArtifactLedgerStore(failures_remaining=1)
    handler, _ = callback_handler(store)
    encoded = transaction("First")
    handler.finalize_block(height=1, transactions=(encoded,))

    with pytest.raises(OSError, match="persistence failed"):
        handler.commit()

    assert store.snapshot is None
    assert handler.check_tx(encoded) == TransactionResult(code=TransactionCode.ACCEPTED)
    with pytest.raises(RuntimeError, match="already awaiting commit"):
        handler.finalize_block(height=1, transactions=(encoded,))

    committed_entries = handler.commit()

    assert store.save_calls == 2
    assert store.snapshot == ArtifactLedgerSnapshot(height=1, entries=committed_entries)
    assert handler.check_tx(encoded) == TransactionResult(code=TransactionCode.DUPLICATE)


def test_handler_recovers_committed_state_from_store() -> None:
    handler, store = callback_handler()
    first = transaction("First")
    handler.finalize_block(height=1, transactions=(first,))
    handler.commit()

    recovered, _ = callback_handler(store)

    assert recovered.check_tx(first) == TransactionResult(code=TransactionCode.DUPLICATE)
    second = transaction("Second")
    result = recovered.finalize_block(height=2, transactions=(second,))
    assert result.transaction_results == (TransactionResult(code=TransactionCode.ACCEPTED),)
    newly_committed = recovered.commit()
    assert store.snapshot is not None
    assert store.snapshot.height == 2
    assert len(store.snapshot.entries) == 2
    assert len(newly_committed) == 1
    assert newly_committed[0].envelope == decode_envelope(second)


def test_uncommitted_block_can_be_reexecuted_after_restart() -> None:
    first_handler, store = callback_handler()
    transactions = (transaction("First"), transaction("Second"))
    first_result = first_handler.finalize_block(height=1, transactions=transactions)

    recovered, _ = callback_handler(store)
    replayed_result = recovered.finalize_block(height=1, transactions=transactions)

    assert replayed_result == first_result
    recovered.commit()
    assert store.snapshot is not None
    assert store.snapshot.height == 1


@pytest.mark.parametrize(
    "envelope",
    [
        signed_envelope("Wrong chain", chain_id="discovery-net-mainnet"),
        replace(signed_envelope("Invalid signature"), signature=bytes(64)),
    ],
)
def test_handler_rejects_invalid_stored_transactions(envelope: SignedEnvelope) -> None:
    store = MemoryArtifactLedgerStore(
        snapshot=ArtifactLedgerSnapshot(
            height=1,
            entries=(ArtifactLedgerEntry(envelope=envelope, height=1, transaction_index=0),),
        )
    )

    with pytest.raises(ValueError, match="stored snapshot contains an invalid transaction"):
        callback_handler(store)


def test_handler_rejects_duplicate_artifacts_in_stored_state() -> None:
    envelope = signed_envelope("First")
    store = MemoryArtifactLedgerStore(
        snapshot=ArtifactLedgerSnapshot(
            height=1,
            entries=(
                ArtifactLedgerEntry(envelope=envelope, height=1, transaction_index=0),
                ArtifactLedgerEntry(envelope=envelope, height=1, transaction_index=1),
            ),
        )
    )

    with pytest.raises(ValueError, match="stored snapshot contains an invalid transaction"):
        callback_handler(store)


def test_separate_handlers_produce_identical_results_and_snapshots() -> None:
    first_handler, first_store = callback_handler()
    second_handler, second_store = callback_handler()
    transactions = (transaction("First"), b"invalid", transaction("Second"))

    first_result = first_handler.finalize_block(height=1, transactions=transactions)
    second_result = second_handler.finalize_block(height=1, transactions=transactions)
    first_handler.commit()
    second_handler.commit()

    assert first_result == second_result
    assert first_store.snapshot == second_store.snapshot


@pytest.mark.parametrize(
    ("height", "entries"),
    [
        (-1, ()),
        (1 << 63, ()),
        (
            0,
            (
                ArtifactLedgerEntry(
                    envelope=signed_envelope("First"), height=1, transaction_index=0
                ),
            ),
        ),
    ],
)
def test_snapshot_rejects_invalid_height_or_future_entries(
    height: int,
    entries: tuple[ArtifactLedgerEntry, ...],
) -> None:
    with pytest.raises(ValueError):
        ArtifactLedgerSnapshot(height=height, entries=entries)


def test_snapshot_requires_integer_height_and_tuple_entries() -> None:
    with pytest.raises(TypeError, match="height must be an integer"):
        ArtifactLedgerSnapshot(height=True, entries=())
    with pytest.raises(TypeError, match="entries must be a tuple"):
        ArtifactLedgerSnapshot(height=0, entries=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ArtifactLedgerEntry"):
        ArtifactLedgerSnapshot(height=0, entries=(object(),))  # type: ignore[arg-type]
