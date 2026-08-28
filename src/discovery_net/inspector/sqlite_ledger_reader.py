# Reads committed artifact-ledger state from SQLite without modifying the database.

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import final

from discovery_net.inspector.sources import ArtifactLedgerUpdate
from discovery_net.node import ArtifactLedgerEntry
from discovery_net.node.store import queries
from discovery_net.node.store.queries import StoredArtifactLedgerEntry
from discovery_net.wire import decode_transaction


@final
class SQLiteArtifactLedgerReader:
    """Reads committed artifact-ledger updates through a read-only connection."""

    __slots__ = ("_uri",)

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        self._uri = f"{path.resolve().as_uri()}?mode=ro"

    def updates_after(self, height: int) -> ArtifactLedgerUpdate:
        """Load entries committed after a previously observed height."""
        if not isinstance(height, int) or isinstance(height, bool):
            raise TypeError("height must be an integer")
        if height < 0:
            raise ValueError("height must be nonnegative")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            try:
                committed_height = queries.select_committed_height(connection)
                if committed_height is None:
                    if queries.contains_entries(connection):
                        raise ValueError(
                            "artifact ledger database contains entries without committed state"
                        )
                    committed_height = 0
                entries = tuple(
                    _ledger_entry(entry)
                    for entry in queries.select_entries_after(connection, height)
                )
                return ArtifactLedgerUpdate(height=committed_height, entries=entries)
            except (TypeError, ValueError) as error:
                raise ValueError("artifact ledger database contains invalid state") from error
            finally:
                connection.execute("ROLLBACK")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._uri, uri=True, isolation_level=None)


def _ledger_entry(entry: StoredArtifactLedgerEntry) -> ArtifactLedgerEntry:
    return ArtifactLedgerEntry(
        transaction=decode_transaction(entry.transaction_bytes),
        height=entry.height,
        transaction_index=entry.transaction_index,
    )
