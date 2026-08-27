# Calls the local CometBFT JSON-RPC interface in integration tests.

from __future__ import annotations

import base64
import json
from typing import cast, final
from urllib.request import Request, urlopen

type JSONObject = dict[str, object]

_RPC_TIMEOUT_SECONDS = 15


@final
class CometBFTRPCClient:
    """Provides the small typed CometBFT RPC surface exercised by the tests."""

    __slots__ = ("_url",)

    def __init__(self, *, url: str) -> None:
        self._url = url

    def status(self) -> JSONObject:
        """Return the current CometBFT status payload."""
        return self._call("status")

    def is_catching_up(self) -> bool:
        """Return whether CometBFT is still synchronizing before normal consensus."""
        return boolean_field(object_field(self.status(), "sync_info"), "catching_up")

    def peer_ids(self) -> tuple[str, ...]:
        """Return the node IDs of this node's current direct peers."""
        peers = list_field(self._call("net_info"), "peers")
        return tuple(
            string_field(object_field(json_object(peer, "peer"), "node_info"), "id")
            for peer in peers
        )

    def broadcast_sync(self, transaction: bytes) -> int:
        """Broadcast a transaction and return its CheckTx code."""
        result = self._call(
            "broadcast_tx_sync",
            {"tx": base64.b64encode(transaction).decode("ascii")},
        )
        return integer_field(result, "code")

    def broadcast_commit(self, transaction: bytes) -> int:
        """Broadcast an accepted transaction and return its committed height."""
        result = self._call(
            "broadcast_tx_commit",
            {"tx": base64.b64encode(transaction).decode("ascii")},
        )
        check_code = integer_field(object_field(result, "check_tx"), "code")
        execution_code = integer_field(object_field(result, "tx_result"), "code")
        if check_code != 0 or execution_code != 0:
            raise AssertionError(
                f"transaction was not committed: CheckTx={check_code}, execution={execution_code}"
            )
        return int(string_field(result, "height"))

    def block_app_hash(self, *, height: int) -> bytes:
        """Return the application hash committed for one block height."""
        result = self._call("block_results", {"height": str(height)})
        if string_field(result, "height") != str(height):
            raise ValueError("CometBFT returned block results for the wrong height")
        return base64.b64decode(string_field(result, "app_hash"), validate=True)

    def _call(
        self,
        method: str,
        parameters: JSONObject | None = None,
    ) -> JSONObject:
        request = Request(
            self._url,
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": parameters or {},
                },
                separators=(",", ":"),
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=_RPC_TIMEOUT_SECONDS) as response:
            payload = json_object(json.loads(response.read()), "CometBFT RPC response")
        if payload.get("error") is not None:
            raise ValueError(f"CometBFT RPC returned an error: {payload['error']!r}")
        return object_field(payload, "result")


def json_object(value: object, description: str) -> JSONObject:
    """Require a decoded JSON object with string keys."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{description} must be an object with string keys")
    return cast(JSONObject, value)


def object_field(value: JSONObject, field_name: str) -> JSONObject:
    """Return one required object field."""
    return json_object(value.get(field_name), field_name)


def string_field(value: JSONObject, field_name: str) -> str:
    """Return one required string field."""
    field = value.get(field_name)
    if not isinstance(field, str):
        raise ValueError(f"{field_name} must be a string")
    return field


def integer_field(value: JSONObject, field_name: str) -> int:
    """Return one required integer field."""
    field = value.get(field_name)
    if not isinstance(field, int) or isinstance(field, bool):
        raise ValueError(f"{field_name} must be an integer")
    return field


def boolean_field(value: JSONObject, field_name: str) -> bool:
    """Return one required boolean field."""
    field = value.get(field_name)
    if not isinstance(field, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return field


def list_field(value: JSONObject, field_name: str) -> list[object]:
    """Return one required list field."""
    field = value.get(field_name)
    if not isinstance(field, list):
        raise ValueError(f"{field_name} must be a list")
    return field
