# Defines the private interface for submitting transactions through CometBFT RPC.

from typing import Protocol

from discovery_net.client._broadcast_response import _BroadcastResponse


class _CometBFTRPCClient(Protocol):
    """Sends encoded transactions to a local CometBFT RPC endpoint."""

    def broadcast_transaction(self, transaction: bytes) -> _BroadcastResponse: ...
