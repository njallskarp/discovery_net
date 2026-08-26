# Submits encoded transactions through CometBFT JSON-RPC.

from typing import final
from urllib.request import urlopen

from discovery_net.submission._broadcast_response import _BroadcastResponse
from discovery_net.submission._cometbft_rpc_messages import (
    _BroadcastRequest,
    _BroadcastRPCResponse,
)
from discovery_net.submission.submission_error import SubmissionError

_RPC_TIMEOUT_SECONDS = 10


@final
class _CometBFTRPCClient:
    """Sends encoded transactions to a local CometBFT RPC endpoint."""

    __slots__ = ("_url",)

    def __init__(self, *, url: str) -> None:
        if not isinstance(url, str):
            raise TypeError("url must be a string")
        self._url = url

    def broadcast_transaction(self, transaction: bytes) -> _BroadcastResponse:
        """Broadcast transaction bytes and return CometBFT's immediate CheckTx result."""
        request = _BroadcastRequest.from_transaction(transaction).to_http_request(self._url)
        try:
            with urlopen(request, timeout=_RPC_TIMEOUT_SECONDS) as response:
                return _BroadcastRPCResponse.decode(response.read()).outcome()
        except OSError as error:
            raise SubmissionError("CometBFT RPC could not be reached") from error
