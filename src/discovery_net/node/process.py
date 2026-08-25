# Runs the local Discovery Net application process called by CometBFT.

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from discovery_net.node.abci import CometBFTABCIAdapter
from discovery_net.node.abci_grpc_server import ABCIGRPCServer
from discovery_net.node.cometbft_callback_handler import CometBFTCallbackHandler
from discovery_net.node.store.sqlite_store import SQLiteArtifactLedgerStore
from discovery_net.node.transaction_validator import TransactionValidator

_DEFAULT_ABCI_LISTEN_ADDRESS = "127.0.0.1:26658"


def run_node(
    *,
    chain_id: str,
    ledger_path: Path,
    abci_listen_address: str,
) -> None:
    """Run one configured node application until it is interrupted."""
    store = SQLiteArtifactLedgerStore(path=ledger_path)
    handler = CometBFTCallbackHandler(
        validator=TransactionValidator(expected_chain_id=chain_id),
        store=store,
    )
    adapter = CometBFTABCIAdapter(handler=handler)
    server = ABCIGRPCServer(
        adapter=adapter,
        listen_address=abci_listen_address,
    )

    with server, suppress(KeyboardInterrupt):
        server.wait_for_termination()


def main(arguments: Sequence[str] | None = None) -> None:
    """Parse process configuration and run the node application."""
    parsed = _argument_parser().parse_args(arguments)
    run_node(
        chain_id=parsed.chain_id,
        ledger_path=parsed.ledger_path,
        abci_listen_address=parsed.abci_listen_address,
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-node",
        description="Run the Discovery Net application called by a local CometBFT node.",
    )
    parser.add_argument(
        "--chain-id",
        required=True,
        help="chain identifier expected in genesis and signed transactions",
    )
    parser.add_argument(
        "--ledger-path",
        required=True,
        type=Path,
        help="path to the local SQLite artifact ledger",
    )
    parser.add_argument(
        "--abci-listen-address",
        default=_DEFAULT_ABCI_LISTEN_ADDRESS,
        help=f"gRPC address exposed to CometBFT (default: {_DEFAULT_ABCI_LISTEN_ADDRESS})",
    )
    return parser


if __name__ == "__main__":
    main()
