"""Command-line entry point for a Discovery Net node."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from discovery_net_poc.node_app import NodeConfig, create_node_app


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="discovery-node")
    result.add_argument("--host", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8761)
    result.add_argument("--public-url")
    result.add_argument("--database", type=Path, default=Path("node.sqlite3"))
    result.add_argument("--key-file", type=Path, default=Path("node-key.json"))
    result.add_argument("--coordinator")
    result.add_argument("--peer", action="append", default=[])
    result.add_argument("--log-level", default="info")
    return result


def main(argv: Sequence[str] | None = None) -> None:
    arguments = parser().parse_args(argv)
    public_url = arguments.public_url or f"http://{arguments.host}:{arguments.port}"
    app = create_node_app(
        NodeConfig(
            database_path=arguments.database,
            key_path=arguments.key_file,
            public_url=public_url,
            coordinator_url=arguments.coordinator,
            peers=tuple(arguments.peer),
        )
    )
    uvicorn.run(app, host=arguments.host, port=arguments.port, log_level=arguments.log_level)


if __name__ == "__main__":
    main()
