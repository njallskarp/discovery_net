# Runs the local Discovery Net application process called by CometBFT.

from __future__ import annotations

import argparse
from contextlib import suppress
from pathlib import Path

from discovery_net.node.abci import CometBFTABCIAdapter
from discovery_net.node.abci_grpc_server import ABCIGRPCServer
from discovery_net.node.cometbft_callback_handler import CometBFTCallbackHandler
from discovery_net.node.store.sqlite_store import SQLiteArtifactLedgerStore
from discovery_net.node.transaction_validator import TransactionValidator

_DEFAULT_ABCI_LISTEN_ADDRESS = "127.0.0.1:26658"


def main() -> None:
    """Run one configured node application until it is interrupted."""
    arguments = _argument_parser().parse_args()
    server = ABCIGRPCServer(
        adapter=CometBFTABCIAdapter(
            handler=CometBFTCallbackHandler(
                validator=TransactionValidator(expected_chain_id=arguments.chain_id),
                store=SQLiteArtifactLedgerStore(path=arguments.ledger_path),
            )
        ),
        listen_address=arguments.abci_listen_address,
    )

    with server, suppress(KeyboardInterrupt):
        server.wait_for_termination()


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
