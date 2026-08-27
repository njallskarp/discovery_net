# Persists committed artifact-ledger state in an embedded SQLite database.

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import final

from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry
from discovery_net.node.store import queries
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.node.store.queries import StoredArtifactLedgerEntry
from discovery_net.wire import decode_transaction, encode_transaction


@final
class SQLiteArtifactLedgerStore:
    """Persists append-only artifact-ledger snapshots transactionally."""

    __slots__ = ("_path",)

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")

        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._open_transaction(immediate=True) as connection:
            queries.create_schema(connection)

    def load(self) -> ArtifactLedgerSnapshot | None:
        """Load the latest committed snapshot, or return none before the first commit."""
        with self._open_transaction() as connection:
            return _read_snapshot(connection)

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None:
        """Atomically persist a snapshot that extends committed history."""
        if not isinstance(snapshot, ArtifactLedgerSnapshot):
            raise TypeError("snapshot must be an ArtifactLedgerSnapshot")

        with self._open_transaction(immediate=True) as connection:
            persisted = _read_snapshot(connection)
            new_entries = _new_entries(persisted, snapshot)
            queries.insert_entries(
                connection,
                tuple(_stored_entry(entry) for entry in new_entries),
            )
            queries.upsert_committed_height(connection, snapshot.height)

    @contextmanager
    def _open_transaction(
        self,
        *,
        immediate: bool = False,
    ) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def _read_snapshot(connection: sqlite3.Connection) -> ArtifactLedgerSnapshot | None:
    committed_height = queries.select_committed_height(connection)
    if committed_height is None:
        if queries.contains_entries(connection):
            raise ValueError("artifact ledger database contains entries without committed state")
        return None

    try:
        entries = tuple(_ledger_entry(entry) for entry in queries.select_entries(connection))
        return ArtifactLedgerSnapshot(height=committed_height, entries=entries)
    except (TypeError, ValueError) as error:
        raise ValueError("artifact ledger database contains invalid state") from error


def _stored_entry(entry: ArtifactLedgerEntry) -> StoredArtifactLedgerEntry:
    return StoredArtifactLedgerEntry(
        height=entry.height,
        transaction_index=entry.transaction_index,
        transaction_bytes=encode_transaction(entry.transaction),
    )


def _ledger_entry(entry: StoredArtifactLedgerEntry) -> ArtifactLedgerEntry:
    return ArtifactLedgerEntry(
        transaction=decode_transaction(entry.transaction_bytes),
        height=entry.height,
        transaction_index=entry.transaction_index,
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
