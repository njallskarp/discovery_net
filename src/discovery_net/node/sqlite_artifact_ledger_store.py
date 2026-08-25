# Persists committed artifact-ledger state in an embedded SQLite database.

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Final, final

from discovery_net.node.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry
from discovery_net.wire import decode_envelope, encode_envelope

_TRANSACTION_INDEX_BYTES: Final = 8

_CREATE_STATE_TABLE: Final = """
CREATE TABLE IF NOT EXISTS artifact_ledger_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    committed_height INTEGER NOT NULL
        CHECK (
            typeof(committed_height) = 'integer'
            AND committed_height BETWEEN 0 AND 9223372036854775807
        )
)
"""

_CREATE_ENTRIES_TABLE: Final = """
CREATE TABLE IF NOT EXISTS artifact_ledger_entries (
    height INTEGER NOT NULL
        CHECK (
            typeof(height) = 'integer'
            AND height BETWEEN 1 AND 9223372036854775807
        ),
    transaction_index BLOB NOT NULL
        CHECK (
            typeof(transaction_index) = 'blob'
            AND length(transaction_index) = 8
        ),
    transaction_bytes BLOB NOT NULL
        CHECK (typeof(transaction_bytes) = 'blob'),
    PRIMARY KEY (height, transaction_index)
)
"""


@final
class SQLiteArtifactLedgerStore:
    """Persists append-only artifact-ledger snapshots transactionally."""

    __slots__ = ("_path",)

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")

        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with closing(self._connect()) as connection, _transaction(connection, immediate=True):
            connection.execute(_CREATE_STATE_TABLE)
            connection.execute(_CREATE_ENTRIES_TABLE)

    def load(self) -> ArtifactLedgerSnapshot | None:
        """Load the latest committed snapshot, or return none before the first commit."""
        with closing(self._connect()) as connection, _transaction(connection):
            return _read_snapshot(connection)

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None:
        """Atomically persist a snapshot that extends committed history."""
        if not isinstance(snapshot, ArtifactLedgerSnapshot):
            raise TypeError("snapshot must be an ArtifactLedgerSnapshot")

        with closing(self._connect()) as connection, _transaction(connection, immediate=True):
            persisted = _read_snapshot(connection)
            new_entries = _new_entries(persisted, snapshot)

            connection.executemany(
                """
                INSERT INTO artifact_ledger_entries (
                    height,
                    transaction_index,
                    transaction_bytes
                ) VALUES (?, ?, ?)
                """,
                (
                    (
                        entry.height,
                        entry.transaction_index.to_bytes(_TRANSACTION_INDEX_BYTES, "big"),
                        encode_envelope(entry.envelope),
                    )
                    for entry in new_entries
                ),
            )
            connection.execute(
                """
                INSERT INTO artifact_ledger_state (singleton, committed_height)
                VALUES (1, ?)
                ON CONFLICT(singleton)
                DO UPDATE SET committed_height = excluded.committed_height
                """,
                (snapshot.height,),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous = FULL")
        except BaseException:
            connection.close()
            raise
        return connection


def _read_snapshot(connection: sqlite3.Connection) -> ArtifactLedgerSnapshot | None:
    state_row = connection.execute(
        "SELECT committed_height FROM artifact_ledger_state WHERE singleton = 1"
    ).fetchone()
    if state_row is None:
        orphaned_entry = connection.execute(
            "SELECT 1 FROM artifact_ledger_entries LIMIT 1"
        ).fetchone()
        if orphaned_entry is not None:
            raise ValueError("artifact ledger database contains entries without committed state")
        return None

    committed_height = state_row[0]
    if not isinstance(committed_height, int):
        raise ValueError("artifact ledger database contains an invalid committed height")

    rows = connection.execute(
        """
        SELECT height, transaction_index, transaction_bytes
        FROM artifact_ledger_entries
        ORDER BY height, transaction_index
        """
    ).fetchall()
    try:
        entries = tuple(_entry_from_row(row) for row in rows)
        return ArtifactLedgerSnapshot(height=committed_height, entries=entries)
    except (TypeError, ValueError) as error:
        raise ValueError("artifact ledger database contains invalid state") from error


def _entry_from_row(row: tuple[object, ...]) -> ArtifactLedgerEntry:
    if len(row) != 3:
        raise ValueError("artifact ledger entry must contain three columns")
    height, encoded_index, transaction = row
    if not isinstance(height, int):
        raise TypeError("stored entry height must be an integer")
    if not isinstance(encoded_index, bytes) or len(encoded_index) != _TRANSACTION_INDEX_BYTES:
        raise TypeError("stored transaction index must be eight bytes")
    if not isinstance(transaction, bytes):
        raise TypeError("stored transaction must be bytes")

    return ArtifactLedgerEntry(
        envelope=decode_envelope(transaction),
        height=height,
        transaction_index=int.from_bytes(encoded_index, "big"),
    )


def _new_entries(
    persisted: ArtifactLedgerSnapshot | None,
    snapshot: ArtifactLedgerSnapshot,
) -> tuple[ArtifactLedgerEntry, ...]:
    if persisted is None:
        return snapshot.entries
    if snapshot.height < persisted.height:
        raise ValueError("snapshot height must not precede the committed height")
    if len(snapshot.entries) < len(persisted.entries):
        raise ValueError("snapshot must not remove committed entries")
    if snapshot.entries[: len(persisted.entries)] != persisted.entries:
        raise ValueError("snapshot must not replace committed entries")

    new_entries = snapshot.entries[len(persisted.entries) :]
    if snapshot.height == persisted.height:
        if new_entries:
            raise ValueError("snapshot must not change an already committed height")
        return ()
    if any(entry.height <= persisted.height for entry in new_entries):
        raise ValueError("new entries must follow the committed height")
    return new_entries


@contextmanager
def _transaction(
    connection: sqlite3.Connection,
    *,
    immediate: bool = False,
) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
