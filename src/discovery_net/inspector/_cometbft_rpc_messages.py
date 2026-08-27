# Models the private JSON-RPC messages used to observe a local CometBFT node.

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Literal, Self, TypeVar
from urllib.request import Request

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictBool,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

type _RPCMethod = Literal[
    "status",
    "net_info",
    "num_unconfirmed_txs",
    "consensus_state",
]
type _NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]

_JSON_RPC_ID: Final[Literal[1]] = 1
_ResultModel = TypeVar("_ResultModel", bound=BaseModel)


class _RPCModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class _EmptyParameters(_RPCModel):
    pass


class _RPCRequest(_RPCModel):
    """One parameterless CometBFT observation request."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Literal[1] = _JSON_RPC_ID
    method: _RPCMethod
    params: _EmptyParameters = _EmptyParameters()

    def to_http_request(self, url: str) -> Request:
        """Build the complete HTTP request for this JSON-RPC message."""
        return Request(
            url,
            data=self.model_dump_json().encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )


class _RPCError(_RPCModel):
    message: StrictStr | None = None


class _RPCResponse(_RPCModel):
    """The shared envelope around one typed CometBFT observation result."""

    jsonrpc: Literal["2.0"]
    id: Literal[1]
    result: dict[str, JsonValue] | None = None
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
            raise ValueError("CometBFT RPC returned an invalid response") from error

    def result_as(self, result_type: type[_ResultModel]) -> _ResultModel:
        """Decode the successful result as its method-specific model."""
        if self.error is not None:
            message = self.error.message or "unknown RPC error"
            raise ValueError(f"CometBFT RPC failed: {message}")
        if self.result is None:
            raise RuntimeError("validated response has no result")
        try:
            return result_type.model_validate(self.result)
        except ValidationError as error:
            raise ValueError("CometBFT RPC returned an invalid result") from error


class _NodeInfo(_RPCModel):
    node_id: StrictStr = Field(alias="id")
    network: StrictStr
    version: StrictStr
    moniker: StrictStr

    @field_validator("node_id", "network", "version", "moniker")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("node information must not be blank")
        return value


class _SyncInfo(_RPCModel):
    latest_block_height: _NonNegativeInt
    latest_block_time: AwareDatetime
    catching_up: StrictBool

    @field_validator("latest_block_height", mode="before")
    @classmethod
    def decode_height(cls, value: object) -> int:
        return _decimal_integer(value, "latest block height")

    @field_validator("latest_block_time", mode="before")
    @classmethod
    def decode_block_time(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("latest block time must be an ISO 8601 string")
        try:
            block_time = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("latest block time must be an ISO 8601 string") from error
        if block_time.tzinfo is None or block_time.utcoffset() is None:
            raise ValueError("latest block time must be timezone-aware")
        return block_time


class _ValidatorInfo(_RPCModel):
    voting_power: _NonNegativeInt

    @field_validator("voting_power", mode="before")
    @classmethod
    def decode_voting_power(cls, value: object) -> int:
        return _decimal_integer(value, "validator voting power")


class _StatusResult(_RPCModel):
    node_info: _NodeInfo
    sync_info: _SyncInfo
    validator_info: _ValidatorInfo


class _TransferMonitor(_RPCModel):
    transferred_bytes: _NonNegativeInt = Field(alias="Bytes")

    @field_validator("transferred_bytes", mode="before")
    @classmethod
    def decode_transferred_bytes(cls, value: object) -> int:
        return _decimal_integer(value, "transferred bytes")


class _ConnectionStatus(_RPCModel):
    duration_nanoseconds: _NonNegativeInt = Field(alias="Duration")
    send_monitor: _TransferMonitor = Field(alias="SendMonitor")
    receive_monitor: _TransferMonitor = Field(alias="RecvMonitor")

    @field_validator("duration_nanoseconds", mode="before")
    @classmethod
    def decode_duration(cls, value: object) -> int:
        return _decimal_integer(value, "connection duration")


class _PeerResult(_RPCModel):
    node_info: _NodeInfo
    is_outbound: StrictBool
    connection_status: _ConnectionStatus
    remote_ip: StrictStr

    @field_validator("remote_ip")
    @classmethod
    def require_remote_ip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("remote IP must not be blank")
        return value


class _NetInfoResult(_RPCModel):
    peer_count: _NonNegativeInt = Field(alias="n_peers")
    peers: tuple[_PeerResult, ...]

    @field_validator("peer_count", mode="before")
    @classmethod
    def decode_peer_count(cls, value: object) -> int:
        return _decimal_integer(value, "peer count")

    @field_validator("peers", mode="before")
    @classmethod
    def decode_peers(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("peers must be a JSON array")
        return tuple(value)

    @model_validator(mode="after")
    def require_complete_peer_list(self) -> Self:
        if self.peer_count != len(self.peers):
            raise ValueError("peer count does not match the peer list")
        return self


class _MempoolResult(_RPCModel):
    transaction_count: _NonNegativeInt = Field(alias="n_txs")

    @field_validator("transaction_count", mode="before")
    @classmethod
    def decode_transaction_count(cls, value: object) -> int:
        return _decimal_integer(value, "mempool transaction count")


class _RoundState(_RPCModel):
    height_round_step: StrictStr = Field(alias="height/round/step")

    def round_and_step(self) -> tuple[int, int]:
        """Return the consensus round and numeric step from CometBFT's compound value."""
        parts = self.height_round_step.split("/")
        if len(parts) != 3:
            raise ValueError("consensus state must contain height, round, and step")
        _height, round_number, step = (_decimal_integer(part, "consensus state") for part in parts)
        return round_number, step


class _ConsensusStateResult(_RPCModel):
    round_state: _RoundState


def _decimal_integer(value: object, description: str) -> int:
    if not isinstance(value, str) or not value.isdecimal():
        raise ValueError(f"{description} must be a nonnegative decimal string")
    return int(value)
