# Defines the authenticated address used to dial one persistent CometBFT peer.

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from discovery_net.node.runtime.endpoint import Endpoint

_NODE_ID_LENGTH = 40


@dataclass(frozen=True, slots=True, kw_only=True)
class PeerAddress:
    """Pairs a CometBFT node identity with its dialable P2P endpoint."""

    node_id: str
    endpoint: Endpoint

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str):
            raise TypeError("node_id must be a string")
        normalized_node_id = self.node_id.lower()
        if len(normalized_node_id) != _NODE_ID_LENGTH or any(
            character not in "0123456789abcdef" for character in normalized_node_id
        ):
            raise ValueError("node_id must be a 40-character hexadecimal CometBFT node ID")
        if not isinstance(self.endpoint, Endpoint):
            raise TypeError("endpoint must be an Endpoint")
        if self.endpoint.is_unspecified:
            raise ValueError("a peer endpoint must be dialable")
        object.__setattr__(self, "node_id", normalized_node_id)

    @classmethod
    def parse(cls, value: str) -> Self:
        """Parse CometBFT's node-id-at-endpoint peer representation."""
        if not isinstance(value, str):
            raise TypeError("peer address must be a string")
        node_id, separator, endpoint = value.partition("@")
        if not separator or "@" in endpoint:
            raise ValueError("peer address must use node_id@host:port")
        return cls(node_id=node_id, endpoint=Endpoint.parse(endpoint))

    def __str__(self) -> str:
        return f"{self.node_id}@{self.endpoint}"
