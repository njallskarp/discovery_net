# Defines operator-owned networking policy for one independent node.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from ipaddress import ip_address

from discovery_net.node.peer_address import PeerAddress, PeerEndpoint


class NetworkScope(StrEnum):
    """Describes the routability boundary on which a node accepts peers."""

    PUBLIC = "public"
    PRIVATE = "private"
    LOOPBACK = "loopback"


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeNetworkConfig:
    """Captures one node's advertised endpoint and independently chosen peers."""

    scope: NetworkScope
    advertised_endpoint: PeerEndpoint
    persistent_peers: tuple[PeerAddress, ...] = ()
    peer_exchange: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.scope, NetworkScope):
            raise TypeError("scope must be a NetworkScope")
        if not isinstance(self.advertised_endpoint, PeerEndpoint):
            raise TypeError("advertised_endpoint must be a PeerEndpoint")
        if not isinstance(self.persistent_peers, tuple) or any(
            not isinstance(peer, PeerAddress) for peer in self.persistent_peers
        ):
            raise TypeError("persistent_peers must be a tuple of PeerAddress values")
        if len(set(self.persistent_peers)) != len(self.persistent_peers):
            raise ValueError("persistent_peers must not contain duplicates")
        if not isinstance(self.peer_exchange, bool):
            raise TypeError("peer_exchange must be a boolean")
        _require_address_matches_scope(self.advertised_endpoint.host, self.scope)


def _require_address_matches_scope(host: str, scope: NetworkScope) -> None:
    if host.lower() == "localhost":
        is_loopback = True
        is_global = False
    else:
        try:
            address = ip_address(host)
        except ValueError:
            if scope is NetworkScope.LOOPBACK:
                raise ValueError("loopback nodes must advertise a loopback address") from None
            return
        is_loopback = address.is_loopback
        is_global = address.is_global

    if scope is NetworkScope.LOOPBACK and not is_loopback:
        raise ValueError("loopback nodes must advertise a loopback address")
    if scope is NetworkScope.PRIVATE and is_global:
        raise ValueError("private nodes must not advertise a public IP address")
    if scope is NetworkScope.PUBLIC and not is_global:
        raise ValueError("public nodes must advertise a globally routable IP address")
