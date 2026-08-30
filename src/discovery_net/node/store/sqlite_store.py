# Persists committed artifact-ledger state in an embedded SQLite database.

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import final

from discovery_net.node.application_state import ApplicationStateSnapshot
from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry
from discovery_net.node.store import queries
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.node.store.queries import StoredArtifactLedgerEntry
from discovery_net.node.validator_governance_codec import (
    decode_validator_governance_state,
    encode_validator_governance_state,
)
from discovery_net.wire import decode_transaction, encode_transaction


@final
class SQLiteApplicationStateStore:
    """Persists all consensus-visible application state transactionally."""

    __slots__ = ("_path",)

    def __init__(self, *, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")

        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        with self._open_transaction(immediate=True) as connection:
            queries.create_schema(connection)

    def load(self) -> ApplicationStateSnapshot | None:
        """Load the latest committed application state."""
        with self._open_transaction() as connection:
            return _read_application_state(connection)

    def load_artifact_ledger(self) -> ArtifactLedgerSnapshot | None:
        """Load the artifact-ledger view used by indexers and query applications."""
        with self._open_transaction() as connection:
            state = _read_application_state(connection)
            return None if state is None else state.artifact_ledger

    def save_artifact_ledger(self, snapshot: ArtifactLedgerSnapshot) -> None:
        """Persist an artifact-ledger view while preserving existing governance."""
        if not isinstance(snapshot, ArtifactLedgerSnapshot):
            raise TypeError("snapshot must be an ArtifactLedgerSnapshot")
        with self._open_transaction(immediate=True) as connection:
            persisted = _read_application_state(connection)
            if persisted is not None and persisted.validator_governance is not None:
                raise ValueError("artifact-only writes are disabled for governance-enabled ledgers")
            _save_application_state(
                connection,
                persisted,
                ApplicationStateSnapshot(
                    artifact_ledger=snapshot,
                    validator_governance=(
                        None if persisted is None else persisted.validator_governance
                    ),
                ),
            )

    def save(self, snapshot: ApplicationStateSnapshot) -> None:
        """Atomically persist artifacts, governance, and their shared height."""
        if not isinstance(snapshot, ApplicationStateSnapshot):
            raise TypeError("snapshot must be an ApplicationStateSnapshot")
        with self._open_transaction(immediate=True) as connection:
            _save_application_state(
                connection,
                _read_application_state(connection),
                snapshot,
            )

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


@final
class SQLiteArtifactLedgerStore:
    """Preserves the legacy artifact-only store API for fixed-validator chains."""

    __slots__ = ("_application_store",)

    def __init__(self, *, path: Path) -> None:
        self._application_store = SQLiteApplicationStateStore(path=path)

    def load(self) -> ArtifactLedgerSnapshot | None:
        """Load the committed artifact-ledger view."""
        return self._application_store.load_artifact_ledger()

    def save(self, snapshot: ArtifactLedgerSnapshot) -> None:
        """Persist a legacy artifact-only snapshot."""
        self._application_store.save_artifact_ledger(snapshot)


def _read_application_state(connection: sqlite3.Connection) -> ApplicationStateSnapshot | None:
    committed_height = queries.select_committed_height(connection)
    governance_bytes = queries.select_validator_governance_state(connection)
    if committed_height is None:
        if queries.contains_entries(connection) or governance_bytes is not None:
            raise ValueError("application database contains values without committed state")
        return None

    try:
        entries = tuple(_ledger_entry(entry) for entry in queries.select_entries(connection))
        governance = (
            None
            if governance_bytes is None
            else decode_validator_governance_state(governance_bytes)
        )
        return ApplicationStateSnapshot(
            artifact_ledger=ArtifactLedgerSnapshot(height=committed_height, entries=entries),
            validator_governance=governance,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("application database contains invalid state") from error


def _save_application_state(
    connection: sqlite3.Connection,
    persisted: ApplicationStateSnapshot | None,
    snapshot: ApplicationStateSnapshot,
) -> None:
    persisted_ledger = None if persisted is None else persisted.artifact_ledger
    new_entries = _new_entries(persisted_ledger, snapshot.artifact_ledger)
    _validate_governance_transition(persisted, snapshot)
    queries.insert_entries(
        connection,
        tuple(_stored_entry(entry) for entry in new_entries),
    )
    if snapshot.validator_governance is not None and (
        persisted is None or snapshot.validator_governance != persisted.validator_governance
    ):
        queries.upsert_validator_governance_state(
            connection,
            encode_validator_governance_state(snapshot.validator_governance),
        )
    queries.upsert_committed_height(connection, snapshot.height)


def _validate_governance_transition(
    persisted: ApplicationStateSnapshot | None,
    snapshot: ApplicationStateSnapshot,
) -> None:
    proposed = snapshot.validator_governance
    if persisted is None:
        if proposed is not None and snapshot.height != 0:
            raise ValueError("validator governance may only be initialized at genesis")
        return

    current = persisted.validator_governance
    if current is None:
        if proposed is not None and snapshot.height != 0:
            raise ValueError("validator governance may only be initialized at genesis")
        return
    if proposed is None:
        raise ValueError("snapshot must not remove validator governance")
    if proposed.validator_power != current.validator_power:
        raise ValueError("snapshot must not replace equal validator power")
    if snapshot.height == persisted.height and proposed != current:
        raise ValueError("snapshot must not change an already committed height")


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
