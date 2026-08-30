# Executes typed SQLite operations for artifact-ledger persistence.

import sqlite3
from dataclasses import dataclass
from typing import Final

_TRANSACTION_INDEX_BYTES: Final = 8
_MAX_UINT64: Final = (1 << 64) - 1

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

_CREATE_GOVERNANCE_TABLE: Final = """
CREATE TABLE IF NOT EXISTS validator_governance_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    state_bytes BLOB NOT NULL CHECK (typeof(state_bytes) = 'blob')
)
"""


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredArtifactLedgerEntry:
    """The typed Python representation of one persisted ledger row."""

    height: int
    transaction_index: int
    transaction_bytes: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.height, int) or isinstance(self.height, bool):
            raise TypeError("stored entry height must be an integer")
        if not isinstance(self.transaction_index, int) or isinstance(self.transaction_index, bool):
            raise TypeError("stored transaction index must be an integer")
        if not 0 <= self.transaction_index <= _MAX_UINT64:
            raise ValueError("stored transaction index must be an unsigned 64-bit integer")
        if not isinstance(self.transaction_bytes, bytes):
            raise TypeError("stored transaction must be bytes")


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the application-state tables when they do not exist."""
    connection.execute(_CREATE_STATE_TABLE)
    connection.execute(_CREATE_ENTRIES_TABLE)
    connection.execute(_CREATE_GOVERNANCE_TABLE)


def select_committed_height(connection: sqlite3.Connection) -> int | None:
    """Return the committed height, or none before the first commit."""
    row = connection.execute(
        "SELECT committed_height FROM artifact_ledger_state WHERE singleton = 1"
    ).fetchone()
    if row is None:
        return None
    if len(row) != 1:
        raise ValueError("committed state query returned an invalid row")

    height = row[0]
    if not isinstance(height, int) or isinstance(height, bool):
        raise ValueError("artifact ledger database contains an invalid committed height")
    return height


def contains_entries(connection: sqlite3.Connection) -> bool:
    """Return whether any persisted ledger entry exists."""
    return (
        connection.execute("SELECT 1 FROM artifact_ledger_entries LIMIT 1").fetchone() is not None
    )


def select_entries(
    connection: sqlite3.Connection,
) -> tuple[StoredArtifactLedgerEntry, ...]:
    """Return all persisted entries in canonical ledger order."""
    rows = connection.execute(
        """
        SELECT height, transaction_index, transaction_bytes
        FROM artifact_ledger_entries
        ORDER BY height, transaction_index
        """
    ).fetchall()
    try:
        return tuple(_stored_entry(row) for row in rows)
    except (TypeError, ValueError) as error:
        raise ValueError("artifact ledger database contains an invalid entry") from error


def select_entries_after(
    connection: sqlite3.Connection,
    height: int,
) -> tuple[StoredArtifactLedgerEntry, ...]:
    """Return persisted entries committed after the supplied block height."""
    if not isinstance(height, int) or isinstance(height, bool):
        raise TypeError("height must be an integer")
    if height < 0:
        raise ValueError("height must be nonnegative")
    rows = connection.execute(
        """
        SELECT height, transaction_index, transaction_bytes
        FROM artifact_ledger_entries
        WHERE height > ?
        ORDER BY height, transaction_index
        """,
        (height,),
    ).fetchall()
    try:
        return tuple(_stored_entry(row) for row in rows)
    except (TypeError, ValueError) as error:
        raise ValueError("artifact ledger database contains an invalid entry") from error


def insert_entries(
    connection: sqlite3.Connection,
    entries: tuple[StoredArtifactLedgerEntry, ...],
) -> None:
    """Insert new ledger entries at their consensus positions."""
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
                entry.transaction_bytes,
            )
            for entry in entries
        ),
    )


def upsert_committed_height(connection: sqlite3.Connection, height: int) -> None:
    """Insert or advance the singleton committed-height row."""
    connection.execute(
        """
        INSERT INTO artifact_ledger_state (singleton, committed_height)
        VALUES (1, ?)
        ON CONFLICT(singleton)
        DO UPDATE SET committed_height = excluded.committed_height
        """,
        (height,),
    )


def select_validator_governance_state(connection: sqlite3.Connection) -> bytes | None:
    """Return encoded validator-governance state when the chain enables it."""
    row = connection.execute(
        "SELECT state_bytes FROM validator_governance_state WHERE singleton = 1"
    ).fetchone()
    if row is None:
        return None
    if len(row) != 1:
        raise ValueError("validator-governance query returned an invalid row")
    return _bytes(row[0], "validator-governance state")


def upsert_validator_governance_state(
    connection: sqlite3.Connection,
    state_bytes: bytes,
) -> None:
    """Insert or replace the singleton validator-governance state value."""
    if not isinstance(state_bytes, bytes):
        raise TypeError("state_bytes must be bytes")
    connection.execute(
        """
        INSERT INTO validator_governance_state (singleton, state_bytes)
        VALUES (1, ?)
        ON CONFLICT(singleton)
        DO UPDATE SET state_bytes = excluded.state_bytes
        """,
        (state_bytes,),
    )


def _stored_entry(row: tuple[object, ...]) -> StoredArtifactLedgerEntry:
    if len(row) != 3:
        raise ValueError("artifact ledger entry query returned an invalid row")
    encoded_index = _bytes(row[1], "stored transaction index")
    if len(encoded_index) != _TRANSACTION_INDEX_BYTES:
        raise ValueError("stored transaction index must be eight bytes")
    return StoredArtifactLedgerEntry(
        height=_integer(row[0], "stored entry height"),
        transaction_index=int.from_bytes(encoded_index, "big"),
        transaction_bytes=_bytes(row[2], "stored transaction"),
    )


def _integer(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    return value


def _bytes(value: object, field_name: str) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f"{field_name} must be bytes")
    return value
