import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import (
    ArtifactLedgerEntry,
    ArtifactLedgerSnapshot,
    CometBFTCallbackHandler,
    SQLiteArtifactLedgerStore,
    TransactionCode,
    TransactionValidator,
)
from discovery_net.wire import encode_transaction, sign_artifact, sign_transaction

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def entry(
    title: str,
    *,
    height: int,
    transaction_index: int = 0,
) -> ArtifactLedgerEntry:
    envelope = sign_artifact(
        chain_id=CHAIN_ID,
        artifact=Contribution(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title=title,
            body=f"Body for {title}",
            created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
        ),
        private_key=PRIVATE_KEY,
    )
    return ArtifactLedgerEntry(
        transaction=sign_transaction(envelopes=(envelope,), private_key=PRIVATE_KEY),
        height=height,
        transaction_index=transaction_index,
    )


def store_at(tmp_path: Path) -> SQLiteArtifactLedgerStore:
    return SQLiteArtifactLedgerStore(path=tmp_path / "node" / "artifact-ledger.sqlite3")


def test_new_store_has_no_committed_snapshot(tmp_path: Path) -> None:
    store = store_at(tmp_path)

    assert store.load() is None


def test_snapshot_survives_a_new_store_instance(tmp_path: Path) -> None:
    path = tmp_path / "node" / "artifact-ledger.sqlite3"
    snapshot = ArtifactLedgerSnapshot(
        height=2,
        entries=(entry("First", height=1), entry("Second", height=2)),
    )
    SQLiteArtifactLedgerStore(path=path).save(snapshot)

    assert SQLiteArtifactLedgerStore(path=path).load() == snapshot


def test_store_preserves_one_atomic_transaction_as_one_ledger_row(tmp_path: Path) -> None:
    path = tmp_path / "node" / "artifact-ledger.sqlite3"
    first_envelope = entry("First", height=1).transaction.envelopes[0]
    second_envelope = entry("Second", height=1).transaction.envelopes[0]
    atomic_entry = ArtifactLedgerEntry(
        transaction=sign_transaction(
            envelopes=(first_envelope, second_envelope),
            private_key=PRIVATE_KEY,
        ),
        height=1,
        transaction_index=0,
    )
    snapshot = ArtifactLedgerSnapshot(height=1, entries=(atomic_entry,))

    SQLiteArtifactLedgerStore(path=path).save(snapshot)

    assert SQLiteArtifactLedgerStore(path=path).load() == snapshot
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM artifact_ledger_entries").fetchone() == (1,)


def test_callback_handler_recovers_committed_state_from_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "artifact-ledger.sqlite3"
    first = entry("First", height=1)
    encoded = encode_transaction(first.transaction)
    handler = CometBFTCallbackHandler(
        validator=TransactionValidator(expected_chain_id=CHAIN_ID),
        store=SQLiteArtifactLedgerStore(path=path),
    )
    handler.finalize_block(height=1, transactions=(encoded,))
    handler.commit()

    recovered = CometBFTCallbackHandler(
        validator=TransactionValidator(expected_chain_id=CHAIN_ID),
        store=SQLiteArtifactLedgerStore(path=path),
    )

    assert recovered.check_tx(encoded).code is TransactionCode.DUPLICATE
    recovered.finalize_block(height=2, transactions=())
    recovered.commit()
    assert SQLiteArtifactLedgerStore(path=path).load() == ArtifactLedgerSnapshot(
        height=2,
        entries=(first,),
    )


def test_later_snapshot_appends_entries_and_advances_empty_blocks(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = entry("First", height=1)
    second = entry("Second", height=3)

    store.save(ArtifactLedgerSnapshot(height=1, entries=(first,)))
    store.save(ArtifactLedgerSnapshot(height=2, entries=(first,)))
    store.save(ArtifactLedgerSnapshot(height=3, entries=(first, second)))

    assert store.load() == ArtifactLedgerSnapshot(height=3, entries=(first, second))


def test_saving_the_same_snapshot_twice_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "artifact-ledger.sqlite3"
    store = SQLiteArtifactLedgerStore(path=path)
    snapshot = ArtifactLedgerSnapshot(height=1, entries=(entry("First", height=1),))

    store.save(snapshot)
    store.save(snapshot)

    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM artifact_ledger_entries").fetchone()
    assert row == (1,)
    assert store.load() == snapshot


def test_store_preserves_the_full_unsigned_transaction_index(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    snapshot = ArtifactLedgerSnapshot(
        height=1,
        entries=(entry("Last possible index", height=1, transaction_index=(1 << 64) - 1),),
    )

    store.save(snapshot)

    assert store.load() == snapshot


def test_store_rejects_a_snapshot_that_moves_backwards(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    committed = ArtifactLedgerSnapshot(height=2, entries=(entry("First", height=1),))
    store.save(committed)

    with pytest.raises(ValueError, match="must not precede"):
        store.save(ArtifactLedgerSnapshot(height=1, entries=committed.entries))

    assert store.load() == committed


def test_store_rejects_replaced_or_removed_history(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = entry("First", height=1)
    committed = ArtifactLedgerSnapshot(height=1, entries=(first,))
    store.save(committed)

    with pytest.raises(ValueError, match="must not remove"):
        store.save(ArtifactLedgerSnapshot(height=2, entries=()))
    with pytest.raises(ValueError, match="must not replace"):
        store.save(
            ArtifactLedgerSnapshot(
                height=2,
                entries=(entry("Replacement", height=1),),
            )
        )

    assert store.load() == committed


def test_store_rejects_changes_to_an_already_committed_height(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = entry("First", height=1)
    committed = ArtifactLedgerSnapshot(height=1, entries=(first,))
    store.save(committed)

    with pytest.raises(ValueError, match="already committed height"):
        store.save(
            ArtifactLedgerSnapshot(
                height=1,
                entries=(first, entry("Late", height=1, transaction_index=1)),
            )
        )

    assert store.load() == committed


def test_store_rejects_late_entries_for_an_earlier_height(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = entry("First", height=1)
    committed = ArtifactLedgerSnapshot(height=2, entries=(first,))
    store.save(committed)

    with pytest.raises(ValueError, match="must follow the committed height"):
        store.save(
            ArtifactLedgerSnapshot(
                height=3,
                entries=(first, entry("Late", height=2)),
            )
        )

    assert store.load() == committed


def test_failed_sqlite_transaction_leaves_committed_state_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "artifact-ledger.sqlite3"
    store = SQLiteArtifactLedgerStore(path=path)
    first = entry("First", height=1)
    committed = ArtifactLedgerSnapshot(height=1, entries=(first,))
    store.save(committed)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_height_two
            BEFORE INSERT ON artifact_ledger_entries
            WHEN NEW.height = 2
            BEGIN
                SELECT RAISE(ABORT, 'forced failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced failure"):
        store.save(
            ArtifactLedgerSnapshot(
                height=2,
                entries=(first, entry("Second", height=2)),
            )
        )

    assert store.load() == committed


def test_store_rejects_corrupted_transaction_bytes(tmp_path: Path) -> None:
    path = tmp_path / "artifact-ledger.sqlite3"
    store = SQLiteArtifactLedgerStore(path=path)
    store.save(ArtifactLedgerSnapshot(height=1, entries=(entry("First", height=1),)))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE artifact_ledger_entries SET transaction_bytes = ?",
            (b"not-an-envelope",),
        )

    with pytest.raises(ValueError, match="contains invalid state"):
        store.load()


def test_store_rejects_entries_without_committed_state(tmp_path: Path) -> None:
    path = tmp_path / "artifact-ledger.sqlite3"
    store = SQLiteArtifactLedgerStore(path=path)
    first = entry("First", height=1)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO artifact_ledger_entries (
                height,
                transaction_index,
                transaction_bytes
            ) VALUES (?, ?, ?)
            """,
            (
                first.height,
                first.transaction_index.to_bytes(8, "big"),
                encode_transaction(first.transaction),
            ),
        )

    with pytest.raises(ValueError, match="without committed state"):
        store.load()


def test_store_requires_a_path() -> None:
    with pytest.raises(TypeError, match="path must be a Path"):
        SQLiteArtifactLedgerStore(path="ledger.sqlite3")  # type: ignore[arg-type]


def test_store_requires_an_artifact_ledger_snapshot(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="ArtifactLedgerSnapshot"):
        store_at(tmp_path).save(object())  # type: ignore[arg-type]
