# Adapts one node's networking policy to CometBFT command-line options.

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from discovery_net.node.network_config import NetworkScope, NodeNetworkConfig


@dataclass(frozen=True, slots=True, kw_only=True)
class CometBFTP2PConfig:
    """Contains the small CometBFT P2P surface controlled by Discovery Net."""

    external_address: str
    persistent_peers: str
    peer_exchange: bool
    addr_book_strict: bool
    allow_duplicate_ip: bool

    @classmethod
    def from_node_config(cls, config: NodeNetworkConfig) -> Self:
        """Derive CometBFT settings without exposing unsafe independent overrides."""
        return cls(
            external_address=str(config.advertised_endpoint),
            persistent_peers=",".join(str(peer) for peer in config.persistent_peers),
            peer_exchange=config.peer_exchange,
            addr_book_strict=config.scope is NetworkScope.PUBLIC,
            allow_duplicate_ip=config.scope is NetworkScope.LOOPBACK,
        )

    def command_arguments(self) -> tuple[str, ...]:
        """Return the corresponding arguments accepted by CometBFT start."""
        return (
            "--p2p.external-address",
            self.external_address,
            "--p2p.persistent_peers",
            self.persistent_peers,
            f"--p2p.pex={_boolean(self.peer_exchange)}",
        )


def _boolean(value: bool) -> str:
    return str(value).lower()
