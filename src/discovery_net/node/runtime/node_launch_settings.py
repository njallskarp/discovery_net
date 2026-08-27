# Defines the complete operator-supplied configuration for one CometBFT process.

from dataclasses import dataclass, field
from pathlib import Path

from discovery_net.node.runtime.endpoint import Endpoint
from discovery_net.node.runtime.genesis import GenesisTrustAnchor
from discovery_net.node.runtime.peer_address import PeerAddress
from discovery_net.node.runtime.peer_admission_policy import PeerAdmissionPolicy


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeLaunchSettings:
    """Captures every Discovery Net setting applied before starting CometBFT."""

    home: Path
    moniker: str
    genesis_path: Path
    genesis_trust_anchor: GenesisTrustAnchor
    abci_endpoint: Endpoint
    rpc_listen_endpoint: Endpoint
    p2p_listen_endpoint: Endpoint
    p2p_advertised_endpoint: Endpoint | None = None
    persistent_peers: tuple[PeerAddress, ...] = ()
    peer_exchange: bool = True
    peer_admission: PeerAdmissionPolicy = field(default_factory=PeerAdmissionPolicy)
    create_empty_blocks: bool = True
    log_level: str = "info"

    def __post_init__(self) -> None:
        if not isinstance(self.home, Path):
            raise TypeError("home must be a Path")
        if not isinstance(self.moniker, str):
            raise TypeError("moniker must be a string")
        if not self.moniker.strip():
            raise ValueError("moniker must not be blank")
        if not isinstance(self.genesis_path, Path):
            raise TypeError("genesis_path must be a Path")
        if not isinstance(self.genesis_trust_anchor, GenesisTrustAnchor):
            raise TypeError("genesis_trust_anchor must be a GenesisTrustAnchor")
        if not isinstance(self.abci_endpoint, Endpoint):
            raise TypeError("abci_endpoint must be an Endpoint")
        if self.abci_endpoint.is_unspecified:
            raise ValueError("abci_endpoint must be dialable")
        if not isinstance(self.rpc_listen_endpoint, Endpoint):
            raise TypeError("rpc_listen_endpoint must be an Endpoint")
        if not isinstance(self.p2p_listen_endpoint, Endpoint):
            raise TypeError("p2p_listen_endpoint must be an Endpoint")
        if self.p2p_advertised_endpoint is not None and not isinstance(
            self.p2p_advertised_endpoint, Endpoint
        ):
            raise TypeError("p2p_advertised_endpoint must be an Endpoint or None")
        if self.p2p_advertised_endpoint is not None and self.p2p_advertised_endpoint.is_unspecified:
            raise ValueError("p2p_advertised_endpoint must be dialable")
        if not isinstance(self.persistent_peers, tuple) or any(
            not isinstance(peer, PeerAddress) for peer in self.persistent_peers
        ):
            raise TypeError("persistent_peers must be a tuple of PeerAddress values")
        node_ids = tuple(peer.node_id for peer in self.persistent_peers)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("persistent_peers must not contain duplicate node identities")
        if not isinstance(self.peer_exchange, bool):
            raise TypeError("peer_exchange must be a boolean")
        if not isinstance(self.peer_admission, PeerAdmissionPolicy):
            raise TypeError("peer_admission must be a PeerAdmissionPolicy")
        if not isinstance(self.create_empty_blocks, bool):
            raise TypeError("create_empty_blocks must be a boolean")
        if not isinstance(self.log_level, str):
            raise TypeError("log_level must be a string")
        if not self.log_level.strip():
            raise ValueError("log_level must not be blank")
