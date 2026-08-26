# Models the private JSON-RPC messages exchanged with CometBFT.

from __future__ import annotations

import base64
from typing import Final, Literal, Self
from urllib.request import Request

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from discovery_net.submission._broadcast_response import _BroadcastResponse
from discovery_net.submission.submission_error import SubmissionError

_JSON_RPC_ID: Final[Literal[1]] = 1
_MAX_UINT32 = (1 << 32) - 1


class _RPCMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _BroadcastParameters(_RPCMessage):
    tx: StrictStr


class _BroadcastRequest(_RPCMessage):
    """The JSON-RPC request that submits one encoded transaction."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Literal[1] = _JSON_RPC_ID
    method: Literal["broadcast_tx_sync"] = "broadcast_tx_sync"
    params: _BroadcastParameters

    @classmethod
    def from_transaction(cls, transaction: bytes) -> Self:
        """Create a request containing one base64-encoded transaction."""
        if not isinstance(transaction, bytes):
            raise TypeError("transaction must be bytes")
        return cls(
            params=_BroadcastParameters(
                tx=base64.b64encode(transaction).decode("ascii"),
            )
        )

    def to_http_request(self, url: str) -> Request:
        """Build the complete HTTP request for this JSON-RPC message."""
        return Request(
            url,
            data=self.model_dump_json().encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )


class _BroadcastResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    hash: StrictStr
    code: StrictInt

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value):
            raise ValueError("transaction hash must be 64 uppercase hexadecimal characters")
        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: int) -> int:
        if not 0 <= value <= _MAX_UINT32:
            raise ValueError("CheckTx code must be an unsigned 32-bit integer")
        return value


class _RPCError(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    message: StrictStr | None = None


class _BroadcastRPCResponse(_RPCMessage):
    """A successful or failed JSON-RPC response to a transaction broadcast."""

    jsonrpc: Literal["2.0"]
    id: Literal[1]
    result: _BroadcastResult | None = None
    error: _RPCError | None = None

    @model_validator(mode="after")
    def require_one_outcome(self) -> Self:
        if (self.result is None) == (self.error is None):
            raise ValueError("response must contain exactly one outcome")
        return self

    @classmethod
    def decode(cls, data: bytes) -> Self:
        """Decode and validate one complete CometBFT JSON-RPC response."""
        if not isinstance(data, bytes):
            raise TypeError("response data must be bytes")
        try:
            return cls.model_validate_json(data)
        except ValidationError as error:
            raise SubmissionError("CometBFT RPC returned an invalid response") from error

    def outcome(self) -> _BroadcastResponse:
        """Translate the wire response into the submission-layer result."""
        if self.error is not None and self.error.message:
            raise SubmissionError(f"CometBFT RPC failed: {self.error.message}")
        if self.error is not None:
            raise SubmissionError("CometBFT RPC failed")
        if self.result is None:
            raise RuntimeError("validated response has no outcome")
        return _BroadcastResponse(
            transaction_hash=self.result.hash,
            check_tx_code=self.result.code,
        )
