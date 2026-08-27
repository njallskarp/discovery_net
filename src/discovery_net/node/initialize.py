# Provides the one-shot command that initializes one independently owned node home.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from discovery_net.node.cometbft_home import CometBFTNodeHome
from discovery_net.node.peer_address import PeerAddress, PeerEndpoint


def main() -> None:
    """Initialize persistent CometBFT identity and print its reachable peer address."""
    arguments = _argument_parser().parse_args()
    node_id = CometBFTNodeHome(path=arguments.home).initialize(
        genesis_path=arguments.genesis,
        expected_chain_id=arguments.chain_id,
        binary=arguments.cometbft_binary,
    )
    sys.stdout.write(f"{PeerAddress(node_id=node_id, endpoint=arguments.advertised_endpoint)}\n")


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-node-initialize",
        description="Initialize or verify one Discovery Net node's durable CometBFT home.",
    )
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--genesis", required=True, type=Path)
    parser.add_argument("--chain-id", required=True)
    parser.add_argument(
        "--advertised-address",
        required=True,
        dest="advertised_endpoint",
        type=PeerEndpoint.parse,
    )
    parser.add_argument("--cometbft-binary", default=Path("cometbft"), type=Path)
    return parser


if __name__ == "__main__":
    main()
