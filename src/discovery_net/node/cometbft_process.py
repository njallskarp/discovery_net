# Starts CometBFT with one node's explicit networking and application boundaries.

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import final

from discovery_net.node.cometbft_config_file import CometBFTConfigFile
from discovery_net.node.cometbft_p2p_config import CometBFTP2PConfig
from discovery_net.node.network_config import NetworkScope, NodeNetworkConfig
from discovery_net.node.peer_address import PeerAddress, PeerEndpoint


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CometBFTStartCommand:
    """Builds the CometBFT process boundary for one Discovery Net node."""

    home: Path
    moniker: str
    proxy_app: str
    rpc_listen_address: str
    p2p_listen_address: str
    network: NodeNetworkConfig
    create_empty_blocks: bool = True
    log_level: str = "info"

    def arguments(self, *, binary: Path = Path("cometbft")) -> tuple[str, ...]:
        """Return the complete process arguments without invoking a shell."""
        p2p = CometBFTP2PConfig.from_node_config(self.network)
        return (
            str(binary),
            "start",
            "--home",
            str(self.home),
            "--moniker",
            self.moniker,
            "--abci",
            "grpc",
            "--proxy_app",
            self.proxy_app,
            "--rpc.laddr",
            f"tcp://{self.rpc_listen_address}",
            "--p2p.laddr",
            f"tcp://{self.p2p_listen_address}",
            *p2p.command_arguments(),
            f"--consensus.create_empty_blocks={str(self.create_empty_blocks).lower()}",
            "--log_level",
            self.log_level,
        )


def main() -> None:
    """Replace this process with CometBFT configured for one independent node."""
    arguments = _argument_parser().parse_args()
    start_command = CometBFTStartCommand(
        home=arguments.home,
        moniker=arguments.moniker,
        proxy_app=arguments.proxy_app,
        rpc_listen_address=arguments.rpc_listen_address,
        p2p_listen_address=arguments.p2p_listen_address,
        network=NodeNetworkConfig(
            scope=arguments.network_scope,
            advertised_endpoint=arguments.advertised_endpoint,
            persistent_peers=_persistent_peers(arguments.persistent_peers),
        ),
        create_empty_blocks=arguments.create_empty_blocks,
        log_level=arguments.log_level,
    )
    CometBFTConfigFile(path=arguments.home / "config" / "config.toml").apply_p2p_policy(
        CometBFTP2PConfig.from_node_config(start_command.network)
    )
    command = start_command.arguments(binary=arguments.cometbft_binary)
    os.execvp(command[0], command)


def _persistent_peers(value: str) -> tuple[PeerAddress, ...]:
    if not value:
        return ()
    return tuple(PeerAddress.parse(peer) for peer in value.split(","))


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discovery-cometbft",
        description="Run CometBFT for one independently configured Discovery Net node.",
    )
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--moniker", required=True)
    parser.add_argument("--proxy-app", default="app:26658")
    parser.add_argument("--rpc-listen-address", default="0.0.0.0:26657")
    parser.add_argument("--p2p-listen-address", default="0.0.0.0:26656")
    parser.add_argument(
        "--advertised-address",
        required=True,
        dest="advertised_endpoint",
        type=PeerEndpoint.parse,
    )
    parser.add_argument(
        "--network-scope",
        default=NetworkScope.PUBLIC,
        type=NetworkScope,
        choices=tuple(NetworkScope),
    )
    parser.add_argument("--persistent-peers", default="")
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--create-empty-blocks",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--cometbft-binary", default=Path("cometbft"), type=Path)
    return parser


if __name__ == "__main__":
    main()
