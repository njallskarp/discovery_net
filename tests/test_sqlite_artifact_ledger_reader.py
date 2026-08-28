import sqlite3
from pathlib import Path

import pytest

from discovery_net.inspector.seed import seed_ledger_snapshot
from discovery_net.inspector.sqlite_ledger_reader import SQLiteArtifactLedgerReader
from discovery_net.node import SQLiteArtifactLedgerStore


def test_reader_checks_height_before_loading_the_committed_snapshot(tmp_path: Path) -> None:
    # The inspector can skip full transaction decoding while the ledger head is unchanged.
    path = tmp_path / "artifact-ledger.sqlite"
    snapshot = seed_ledger_snapshot()
    SQLiteArtifactLedgerStore(path=path).save(snapshot)
    reader = SQLiteArtifactLedgerReader(path=path)

    assert reader.committed_height() == snapshot.height
    assert reader.load() == snapshot


def test_reader_never_creates_a_missing_database(tmp_path: Path) -> None:
    # A read-only inspector must fail without mutating an invalid ledger path.
    path = tmp_path / "missing.sqlite"
    reader = SQLiteArtifactLedgerReader(path=path)

    with pytest.raises(sqlite3.OperationalError):
        reader.committed_height()

    assert not path.exists()
