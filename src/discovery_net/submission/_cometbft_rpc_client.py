# Submits encoded transactions through CometBFT JSON-RPC.

import base64
import json
from typing import cast, final
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from discovery_net.submission._broadcast_response import _BroadcastResponse
from discovery_net.submission.submission_error import SubmissionError

type JSONObject = dict[str, object]


_JSON_RPC_ID = 1
_RPC_TIMEOUT_SECONDS = 10
_MAX_UINT32 = (1 << 32) - 1


@final
class _CometBFTRPCClient:
    """Sends encoded transactions to a local CometBFT RPC endpoint."""

    __slots__ = ("_url",)

    def __init__(self, *, url: str) -> None:
        if not isinstance(url, str):
            raise TypeError("url must be a string")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP URL")
        self._url = url

    def broadcast_transaction(self, transaction: bytes) -> _BroadcastResponse:
        """Broadcast transaction bytes and return CometBFT's immediate CheckTx result."""
        if not isinstance(transaction, bytes):
            raise TypeError("transaction must be bytes")

        request = Request(
            self._url,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": _JSON_RPC_ID,
                    "method": "broadcast_tx_sync",
                    "params": {"tx": base64.b64encode(transaction).decode("ascii")},
                },
                separators=(",", ":"),
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=_RPC_TIMEOUT_SECONDS) as response:
                response_bytes = response.read()
        except OSError as error:
            raise SubmissionError("CometBFT RPC could not be reached") from error
        return _decode_response(response_bytes)


def _decode_response(data: bytes) -> _BroadcastResponse:
    try:
        payload = _json_object(json.loads(data), "CometBFT RPC response")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SubmissionError("CometBFT RPC returned invalid JSON") from error

    response_id = payload.get("id")
    if (
        payload.get("jsonrpc") != "2.0"
        or not isinstance(response_id, int)
        or isinstance(response_id, bool)
        or response_id != _JSON_RPC_ID
    ):
        raise SubmissionError("CometBFT RPC returned an unrelated response")
    rpc_error = payload.get("error")
    if rpc_error is not None:
        raise SubmissionError(_rpc_error_message(rpc_error))

    result = _object_field(payload, "result")
    transaction_hash = result.get("hash")
    if (
        not isinstance(transaction_hash, str)
        or len(transaction_hash) != 64
        or any(character not in "0123456789ABCDEF" for character in transaction_hash)
    ):
        raise SubmissionError("CometBFT RPC returned an invalid transaction hash")
    check_tx_code = result.get("code")
    if (
        not isinstance(check_tx_code, int)
        or isinstance(check_tx_code, bool)
        or not 0 <= check_tx_code <= _MAX_UINT32
    ):
        raise SubmissionError("CometBFT RPC returned an invalid CheckTx code")
    return _BroadcastResponse(
        transaction_hash=transaction_hash,
        check_tx_code=check_tx_code,
    )


def _json_object(value: object, description: str) -> JSONObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise SubmissionError(f"{description} must be an object")
    return cast(JSONObject, value)


def _object_field(value: JSONObject, field_name: str) -> JSONObject:
    return _json_object(value.get(field_name), f"CometBFT RPC {field_name}")


def _rpc_error_message(error: object) -> str:
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return f"CometBFT RPC failed: {message}"
    return "CometBFT RPC failed"
