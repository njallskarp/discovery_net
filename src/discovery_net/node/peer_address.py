# Defines the authenticated network addresses used to reach CometBFT peers.

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from typing import Self

_NODE_ID_LENGTH = 40
_MAX_PORT = 65_535


@dataclass(frozen=True, slots=True, kw_only=True)
class PeerEndpoint:
    """Identifies one reachable P2P listener without its cryptographic identity."""

    host: str
    port: int

    def __post_init__(self) -> None:
        if not isinstance(self.host, str):
            raise TypeError("host must be a string")
        if (
            not self.host
            or self.host != self.host.strip()
            or any(character.isspace() for character in self.host)
            or any(character in self.host for character in "@,[]")
        ):
            raise ValueError("host must be a non-blank hostname or IP address")
        if ":" in self.host:
            try:
                address = ip_address(self.host)
            except ValueError as error:
                raise ValueError("a host containing ':' must be an IPv6 address") from error
            if not isinstance(address, IPv6Address):
                raise ValueError("a host containing ':' must be an IPv6 address")
        if not isinstance(self.port, int) or isinstance(self.port, bool):
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= _MAX_PORT:
            raise ValueError(f"port must be between 1 and {_MAX_PORT}")

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse a host and port without resolving the host through DNS."""
        if not isinstance(value, str):
            raise TypeError("peer endpoint must be a string")
        host, encoded_port = _split_endpoint(value)
        try:
            port = int(encoded_port)
        except ValueError as error:
            raise ValueError("peer endpoint port must be an integer") from error
        return cls(host=host, port=port)

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"


@dataclass(frozen=True, slots=True, kw_only=True)
class PeerAddress:
    """Combines a peer's authenticated node ID with its reachable endpoint."""

    node_id: str
    endpoint: PeerEndpoint

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str):
            raise TypeError("node_id must be a string")
        if len(self.node_id) != _NODE_ID_LENGTH or any(
            character not in "0123456789abcdef" for character in self.node_id
        ):
            raise ValueError("node_id must be 40 lowercase hexadecimal characters")
        if not isinstance(self.endpoint, PeerEndpoint):
            raise TypeError("endpoint must be a PeerEndpoint")

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse CometBFT's node-id@host:port peer-address format."""
        if not isinstance(value, str):
            raise TypeError("peer address must be a string")
        node_id, separator, endpoint = value.partition("@")
        if not separator or "@" in endpoint:
            raise ValueError("peer address must use node-id@host:port format")
        return cls(node_id=node_id, endpoint=PeerEndpoint.parse(endpoint))

    def __str__(self) -> str:
        return f"{self.node_id}@{self.endpoint}"


def _split_endpoint(value: str) -> tuple[str, str]:
    if value.startswith("["):
        closing_bracket = value.find("]")
        if closing_bracket < 0 or value[closing_bracket + 1 : closing_bracket + 2] != ":":
            raise ValueError("IPv6 peer endpoint must use [host]:port format")
        return value[1:closing_bracket], value[closing_bracket + 2 :]
    host, separator, encoded_port = value.rpartition(":")
    if not separator:
        raise ValueError("peer endpoint must use host:port format")
    return host, encoded_port
