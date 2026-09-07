"""Verified ledger snapshot commands: python -m discovery_net.snapshots."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from discovery_net.snapshots.ledger_baseline import export_baseline


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline Discovery Net ledger snapshots")
    commands = parser.add_subparsers(dest="command", required=True)
    baseline = commands.add_parser("baseline", help="export and verify a read-only ledger backup")
    baseline.add_argument("--ledger", type=Path, required=True)
    baseline.add_argument("--output", type=Path, required=True)
    baseline.add_argument("--chain-id", required=True)
    baseline.add_argument("--genesis", type=Path)
    baseline.add_argument("--genesis-sha256")
    parsed = parser.parse_args(arguments)
    try:
        manifest = export_baseline(
            ledger=parsed.ledger,
            output=parsed.output,
            chain_id=parsed.chain_id,
            genesis=parsed.genesis,
            genesis_sha256=parsed.genesis_sha256,
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(manifest.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
