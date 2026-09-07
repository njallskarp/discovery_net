"""Exercise real SQLite backup/replay and the development command's failure paths."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.development.__main__ import main
from discovery_net.development.ledger_baseline import BaselineManifest, export_baseline
from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import (
    ArtifactLedgerEntry,
    ArtifactLedgerSnapshot,
    LocalArtifactLedger,
    SQLiteArtifactLedgerStore,
)
from discovery_net.wire import sign_artifact, sign_transaction

CHAIN = "baseline-test"


def _entry(height: int) -> ArtifactLedgerEntry:
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    envelope = sign_artifact(
        chain_id=CHAIN,
        artifact=Contribution(
            kind=ContributionKind.FINDING,
            title=f"Finding {height}",
            body="Synthetic export test",
            created_at=datetime(2026, 9, 7, tzinfo=UTC),
        ),
        private_key=key,
    )
    return ArtifactLedgerEntry(
        transaction=sign_transaction(envelopes=(envelope,), private_key=key),
        height=height,
        transaction_index=0,
    )


def _ledger(path: Path) -> ArtifactLedgerSnapshot:
    snapshot = ArtifactLedgerSnapshot(height=1, entries=(_entry(1),))
    SQLiteArtifactLedgerStore(path=path).save(snapshot)
    return snapshot


def test_export_verifies_a_standalone_copy_without_changing_source(tmp_path: Path) -> None:
    source, output = tmp_path / "live.sqlite", tmp_path / "baseline"
    snapshot = _ledger(source)
    original_bytes = source.read_bytes()
    original_files = set(tmp_path.iterdir())

    manifest = export_baseline(ledger=source, output=output, chain_id=CHAIN)

    assert source.read_bytes() == original_bytes
    assert set(tmp_path.iterdir()) == original_files | {output}
    assert set(path.name for path in output.iterdir()) == {"ledger.sqlite", "manifest.json"}
    assert SQLiteArtifactLedgerStore(path=output / "ledger.sqlite").load() == snapshot
    assert manifest == BaselineManifest.model_validate_json((output / "manifest.json").read_bytes())
    assert manifest.chain_id == CHAIN
    assert manifest.chain_id_verified
    assert manifest.height == 1
    assert manifest.transaction_count == manifest.artifact_count == 1
    assert manifest.payload_counts == {"contribution": 1}
    assert manifest.state_hash == LocalArtifactLedger(entries=snapshot.entries).state_hash().hex()
    assert manifest.snapshot_sha256 == sha256((output / "ledger.sqlite").read_bytes()).hexdigest()
    assert manifest.snapshot_bytes == (output / "ledger.sqlite").stat().st_size


def test_empty_ledger_does_not_claim_to_verify_a_chain_identity(tmp_path: Path) -> None:
    source = tmp_path / "empty.sqlite"
    SQLiteArtifactLedgerStore(path=source)

    manifest = export_baseline(ledger=source, output=tmp_path / "baseline", chain_id=CHAIN)

    assert manifest.height == manifest.transaction_count == manifest.artifact_count == 0
    assert not manifest.chain_id_verified
    assert manifest.state_hash == LocalArtifactLedger().state_hash().hex()


@pytest.mark.parametrize("failure", ["wrong-chain", "bad-signature", "bad-database", "missing"])
def test_invalid_sources_leave_no_output_or_staging_files(tmp_path: Path, failure: str) -> None:
    source, output = tmp_path / "live.sqlite", tmp_path / "baseline"
    _ledger(source)
    if failure == "bad-signature":
        with closing(sqlite3.connect(source)) as connection:
            encoded = connection.execute(
                "SELECT transaction_bytes FROM artifact_ledger_entries"
            ).fetchone()[0]
            decoded = json.loads(encoded)
            decoded["signature"] = "00" * 64
            connection.execute(
                "UPDATE artifact_ledger_entries SET transaction_bytes = ?",
                (json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode(),),
            )
            connection.commit()
    elif failure == "bad-database":
        source.write_bytes(b"not a database")
    elif failure == "missing":
        source.unlink()
    before = set(tmp_path.iterdir())

    with pytest.raises((ValueError, sqlite3.Error, FileNotFoundError)):
        export_baseline(
            ledger=source,
            output=output,
            chain_id="wrong" if failure == "wrong-chain" else CHAIN,
        )

    assert not output.exists()
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("destination", ["directory", "file", "symlink", "source", "ancestor"])
def test_destination_collisions_and_aliases_are_never_overwritten(
    tmp_path: Path,
    destination: str,
) -> None:
    source, output = tmp_path / "live.sqlite", tmp_path / "baseline"
    _ledger(source)
    if destination == "directory":
        output.mkdir()
        (output / "keep").write_text("existing")
    elif destination == "file":
        output.write_text("existing")
    elif destination == "symlink":
        output.symlink_to(source)
    elif destination == "source":
        output = source
    else:
        output = tmp_path
    before = source.read_bytes()

    with pytest.raises((FileExistsError, ValueError)):
        export_baseline(ledger=source, output=output, chain_id=CHAIN)

    assert source.read_bytes() == before
    if destination == "directory":
        assert (output / "keep").read_text() == "existing"
    elif destination == "file":
        assert output.read_text() == "existing"


def test_backup_pins_a_consistent_snapshot_during_a_real_wal_commit(tmp_path: Path) -> None:
    source, output = tmp_path / "live.sqlite", tmp_path / "baseline"
    first = _ledger(source)
    next_snapshot = ArtifactLedgerSnapshot(height=2, entries=(*first.entries, _entry(2)))
    live_store = SQLiteArtifactLedgerStore(path=source)

    # Keep WAL open and commit from a second connection during the actual backup.
    with closing(sqlite3.connect(source)) as wal:
        wal.execute("PRAGMA journal_mode = WAL")

        class ConcurrentReader(sqlite3.Connection):
            def backup(
                self,
                target: sqlite3.Connection,
                *,
                pages: int = -1,
                progress: object = None,
                name: str = "main",
                sleep: float = 0.250,
            ) -> None:
                written = False

                def commit_during_backup(status: int, remaining: int, total: int) -> None:
                    nonlocal written
                    if not written:
                        live_store.save(next_snapshot)
                        written = True

                super().backup(
                    target, pages=1, progress=commit_during_backup, name=name, sleep=sleep
                )
                assert written

        connect = sqlite3.connect

        def connect_with_reader(database: str | Path, **kwargs: object) -> sqlite3.Connection:
            if isinstance(database, str) and database.endswith("?mode=ro"):
                return connect(database, uri=True, factory=ConcurrentReader)
            return connect(database)

        with patch(
            "discovery_net.development.ledger_baseline.sqlite3.connect", connect_with_reader
        ):
            manifest = export_baseline(ledger=source, output=output, chain_id=CHAIN)

        assert live_store.load() == next_snapshot
        assert SQLiteArtifactLedgerStore(path=output / "ledger.sqlite").load() == first
        assert manifest.height == 1


def test_an_output_created_during_capture_is_preserved(tmp_path: Path) -> None:
    source, output = tmp_path / "live.sqlite", tmp_path / "baseline"
    _ledger(source)

    def competing_output() -> tuple[None, None]:
        output.mkdir()
        (output / "keep").write_text("concurrent owner")
        return None, None

    with (
        patch("discovery_net.development.ledger_baseline._source_revision", competing_output),
        pytest.raises(FileExistsError),
    ):
        export_baseline(ledger=source, output=output, chain_id=CHAIN)

    assert list(output.iterdir()) == [output / "keep"]
    assert (output / "keep").read_text() == "concurrent owner"


def test_development_command_reports_manifest_and_actionable_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, output = tmp_path / "live.sqlite", tmp_path / "baseline"
    _ledger(source)
    arguments = ["baseline", "--ledger", str(source), "--output", str(output), "--chain-id", CHAIN]

    assert main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["height"] == 1
    assert main(arguments) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "output already exists" in captured.err
