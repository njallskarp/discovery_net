# Parses operator input and starts one local CometBFT process through the trusted launcher.

import argparse
from pathlib import Path

from discovery_net.node.runtime.cometbft_node_launcher import CometBFTNodeLauncher
from discovery_net.node.runtime.endpoint import Endpoint
from discovery_net.node.runtime.genesis import GenesisTrustAnchor
from discovery_net.node.runtime.node_launch_settings import NodeLaunchSettings
from discovery_net.node.runtime.peer_address import PeerAddress
from discovery_net.node.runtime.peer_admission_policy import PeerAdmissionPolicy


def main() -> None:
    """Start one explicitly configured CometBFT process."""
    arguments = _argument_parser().parse_args()
    CometBFTNodeLauncher(binary=arguments.cometbft_binary).start(
        NodeLaunchSettings(
            home=arguments.home,
            moniker=arguments.moniker,
            genesis_path=arguments.genesis_path,
            genesis_trust_anchor=GenesisTrustAnchor(
                expected_chain_id=arguments.chain_id,
                expected_sha256=arguments.genesis_sha256,
            ),
            abci_endpoint=arguments.abci_endpoint,
            rpc_listen_endpoint=arguments.rpc_listen_endpoint,
            p2p_listen_endpoint=arguments.p2p_listen_endpoint,
            p2p_advertised_endpoint=arguments.p2p_advertised_endpoint,
            persistent_peers=tuple(arguments.persistent_peer),
            peer_exchange=arguments.peer_exchange,
            peer_admission=PeerAdmissionPolicy(
                address_book_strict=arguments.address_book_strict,
                allow_duplicate_ip=arguments.allow_duplicate_ip,
            ),
            create_empty_blocks=arguments.create_empty_blocks,
            log_level=arguments.log_level,
        )
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-cometbft",
        description="Start CometBFT from an explicitly trusted Discovery Net configuration.",
    )
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--moniker", required=True)
    parser.add_argument("--genesis", required=True, type=Path, dest="genesis_path")
    parser.add_argument("--genesis-sha256", required=True)
    parser.add_argument("--chain-id", required=True)
    parser.add_argument("--abci-endpoint", required=True, type=Endpoint.parse)
    parser.add_argument("--rpc-listen-endpoint", required=True, type=Endpoint.parse)
    parser.add_argument("--p2p-listen-endpoint", required=True, type=Endpoint.parse)
    parser.add_argument("--p2p-advertised-endpoint", type=Endpoint.parse)
    parser.add_argument(
        "--persistent-peer",
        action="append",
        default=[],
        type=PeerAddress.parse,
    )
    parser.add_argument(
        "--peer-exchange",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--address-book-strict",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--allow-duplicate-ip", action="store_true")
    parser.add_argument(
        "--create-empty-blocks",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--cometbft-binary", default=Path("cometbft"), type=Path)
    return parser


if __name__ == "__main__":
    main()
