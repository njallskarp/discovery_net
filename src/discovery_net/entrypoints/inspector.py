# Runs the standalone read-only Discovery Net inspector.

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from discovery_net.inspector import (
    CometBFTObservationSource,
    InspectorService,
    SQLiteArtifactLedgerReader,
)
from discovery_net.inspector.seed import seeded_inspector_service
from discovery_net.inspector.server import InspectorServer

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765
_DEFAULT_COMETBFT_RPC_URL = "http://127.0.0.1:26657"


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the configured inspector until interrupted."""
    parsed = _argument_parser().parse_args(arguments)

    with InspectorServer(
        service=_inspector_service(parsed),
        listen_host=parsed.listen_host,
        listen_port=parsed.listen_port,
    ) as server:
        print(
            f"Discovery Net inspector listening at "
            f"http://{server.listen_host}:{server.listen_port}",
            flush=True,
        )
        with suppress(KeyboardInterrupt):
            server.serve_forever()
    return 0


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-inspector",
        description="Run the read-only Discovery Net inspector.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--demo",
        action="store_true",
        help="use deterministic seed node and knowledge-graph data",
    )
    mode.add_argument(
        "--ledger-path",
        type=Path,
        help="path to the local SQLite artifact ledger",
    )
    parser.add_argument(
        "--cometbft-rpc-url",
        default=_DEFAULT_COMETBFT_RPC_URL,
        help=f"local CometBFT RPC URL (default: {_DEFAULT_COMETBFT_RPC_URL})",
    )
    parser.add_argument(
        "--listen-host",
        default=_DEFAULT_HOST,
        help=f"HTTP host to bind (default: {_DEFAULT_HOST})",
    )
    parser.add_argument(
        "--listen-port",
        default=_DEFAULT_PORT,
        type=int,
        help=f"HTTP port to bind (default: {_DEFAULT_PORT})",
    )
    return parser


def _inspector_service(arguments: argparse.Namespace) -> InspectorService:
    if arguments.demo:
        return seeded_inspector_service()
    if not isinstance(arguments.ledger_path, Path):
        raise RuntimeError("validated live mode has no ledger path")
    return InspectorService(
        node_source=CometBFTObservationSource(url=arguments.cometbft_rpc_url),
        ledger_reader=SQLiteArtifactLedgerReader(path=arguments.ledger_path),
    )


if __name__ == "__main__":
    raise SystemExit(main())
