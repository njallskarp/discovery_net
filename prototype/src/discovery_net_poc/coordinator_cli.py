"""Command-line entry point for a Discovery Net coordinator."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from discovery_net_poc.coordinator_app import CoordinatorConfig, create_coordinator_app


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="discovery-coordinator")
    result.add_argument("--host", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8760)
    result.add_argument("--database", type=Path, default=Path("coordinator.sqlite3"))
    result.add_argument("--key-file", type=Path, default=Path("coordinator-key.json"))
    result.add_argument("--reviewers", type=int, default=2)
    result.add_argument("--log-level", default="info")
    return result


def main(argv: Sequence[str] | None = None) -> None:
    arguments = parser().parse_args(argv)
    app = create_coordinator_app(
        CoordinatorConfig(
            database_path=arguments.database,
            key_path=arguments.key_file,
            default_reviewer_count=arguments.reviewers,
        )
    )
    uvicorn.run(app, host=arguments.host, port=arguments.port, log_level=arguments.log_level)


if __name__ == "__main__":
    main()
