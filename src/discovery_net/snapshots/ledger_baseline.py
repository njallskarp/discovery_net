"""Export and replay a consistent copy of a ledger without writing to its source."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import BaseModel, ConfigDict

from discovery_net.inspector.sqlite_ledger_reader import SQLiteArtifactLedgerReader
from discovery_net.node import ArtifactLedgerSnapshot, TransactionValidator
from discovery_net.node._ledger_from_snapshot import ledger_from_snapshot


class BaselineManifest(BaseModel):
    """A completed offline capture, not an independent proof of chain consensus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: Literal[1] = 1
    chain_id: str
    chain_id_verified: bool
    height: int
    state_hash: str
    transaction_count: int
    artifact_count: int
    payload_counts: dict[str, int]
    snapshot_file: Literal["ledger.sqlite"] = "ledger.sqlite"
    snapshot_sha256: str
    snapshot_bytes: int
    source_revision: str | None
    source_dirty: bool | None
    captured_at: datetime


def export_baseline(*, ledger: Path, output: Path, chain_id: str) -> BaselineManifest:
    """Verify a backup, then publish its files with manifest.json as completion marker.

    An existing output is never reused, including one created during the backup.
    All source transactions are read from a pinned SQLite snapshot. The copied
    ledger is verified without initializing or modifying its application schema.
    """
    validator = TransactionValidator(expected_chain_id=chain_id)
    source = ledger.resolve(strict=True)
    if not source.is_file():
        raise ValueError("ledger must be a regular file")
    destination = output.resolve()
    if source == destination or source.is_relative_to(destination):
        raise ValueError("output must not contain or replace the source ledger")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output already exists: {output}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix=".ledger-baseline-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        snapshot_path = staging / "ledger.sqlite"
        _backup(source, snapshot_path)
        update = SQLiteArtifactLedgerReader(path=snapshot_path).updates_after(0)
        snapshot = ArtifactLedgerSnapshot(height=update.height, entries=update.entries)
        verified = ledger_from_snapshot(snapshot, validator)
        counts = Counter(
            envelope.payload_type.value
            for entry in snapshot.entries
            for envelope in entry.transaction.envelopes
        )
        revision, dirty = _source_revision()
        with snapshot_path.open("rb") as stream:
            checksum = file_digest(stream, "sha256").hexdigest()
        manifest = BaselineManifest(
            chain_id=chain_id,
            chain_id_verified=bool(snapshot.entries),
            height=snapshot.height,
            state_hash=verified.state_hash().hex(),
            transaction_count=len(snapshot.entries),
            artifact_count=sum(counts.values()),
            payload_counts=dict(sorted(counts.items())),
            snapshot_sha256=checksum,
            snapshot_bytes=snapshot_path.stat().st_size,
            source_revision=revision,
            source_dirty=dirty,
            captured_at=datetime.now(UTC),
        )
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")

        # Reserve exclusively only after verification. Publish the manifest last:
        # readers must require it, and failed publication removes only our files.
        destination.mkdir()
        published: list[Path] = []
        try:
            for path in (snapshot_path, manifest_path):
                target = destination / path.name
                os.link(path, target)
                published.append(target)
        except BaseException:
            for path in reversed(published):
                path.unlink()
            if not any(destination.iterdir()):
                destination.rmdir()
            raise
    return manifest


def _backup(source: Path, destination: Path) -> None:
    with (
        closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as reader,
        closing(sqlite3.connect(destination)) as writer,
    ):
        reader.execute("BEGIN")
        # Establish the read snapshot before backup so concurrent WAL commits
        # cannot change the captured history midway through a paged backup.
        reader.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        reader.backup(writer, pages=128)
        reader.rollback()
        writer.execute("PRAGMA journal_mode = DELETE")
        result = writer.execute("PRAGMA integrity_check").fetchall()
        if result != [("ok",)]:
            raise ValueError("ledger backup failed SQLite integrity checking")


def _source_revision() -> tuple[str | None, bool | None]:
    """Identify an editable checkout; installed wheels deliberately report unknown."""
    root = Path(__file__).resolve().parents[3]
    try:
        top = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "--show-toplevel"),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if Path(top.stdout.strip()).resolve() != root:
            return None, None
        revision = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = subprocess.run(
            ("git", "-C", str(root), "status", "--porcelain", "--", "src", "pyproject.toml"),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return revision.stdout.strip(), bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None
