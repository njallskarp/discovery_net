# Encodes validator-governance state for genesis and local persistence.

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError, field_validator

from discovery_net.node.validator_governance import ValidatorGovernanceState
from discovery_net.wire.codec import CodecError

type JSONObject = dict[str, object]


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _GovernanceStatePayload(_WireModel):
    approval_threshold: StrictInt
    member_public_keys: tuple[StrictStr, ...]
    sequence: StrictInt
    validator_power: StrictInt
    validator_public_keys: tuple[StrictStr, ...]

    @field_validator("member_public_keys", "validator_public_keys")
    @classmethod
    def validate_public_keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_public_key(value)
        return values


class _GenesisApplicationStatePayload(_WireModel):
    validator_governance: _GovernanceStatePayload


def encode_validator_governance_state(state: ValidatorGovernanceState) -> bytes:
    """Encode deterministic validator-governance state for local persistence."""
    if not isinstance(state, ValidatorGovernanceState):
        raise TypeError("state must be a ValidatorGovernanceState")
    return _canonical_json(_governance_state_value(state))


def decode_validator_governance_state(data: bytes) -> ValidatorGovernanceState:
    """Decode canonical validator-governance state from local persistence."""
    if not isinstance(data, bytes):
        raise TypeError("governance state data must be bytes")
    try:
        state = _state_from_model(_GovernanceStatePayload.model_validate_json(data))
    except (ValidationError, TypeError, ValueError) as error:
        raise CodecError("validator-governance state is invalid") from error
    if encode_validator_governance_state(state) != data:
        raise CodecError("validator-governance state is not canonical")
    return state


def encode_genesis_application_state(state: ValidatorGovernanceState) -> bytes:
    """Encode governance state in the application-state shape used by genesis."""
    if not isinstance(state, ValidatorGovernanceState):
        raise TypeError("state must be a ValidatorGovernanceState")
    return _canonical_json({"validator_governance": _governance_state_value(state)})


def decode_genesis_application_state(data: bytes) -> ValidatorGovernanceState:
    """Decode the supported Discovery Net genesis application state."""
    if not isinstance(data, bytes):
        raise TypeError("genesis application state must be bytes")
    try:
        model = _GenesisApplicationStatePayload.model_validate_json(data)
        return _state_from_model(model.validator_governance)
    except (ValidationError, TypeError, ValueError) as error:
        raise CodecError("genesis application state is invalid") from error


def _state_from_model(model: _GovernanceStatePayload) -> ValidatorGovernanceState:
    return ValidatorGovernanceState(
        member_public_keys=tuple(bytes.fromhex(value) for value in model.member_public_keys),
        approval_threshold=model.approval_threshold,
        validator_power=model.validator_power,
        validator_public_keys=tuple(bytes.fromhex(value) for value in model.validator_public_keys),
        sequence=model.sequence,
    )


def _governance_state_value(state: ValidatorGovernanceState) -> JSONObject:
    return {
        "approval_threshold": state.approval_threshold,
        "member_public_keys": [value.hex() for value in state.member_public_keys],
        "sequence": state.sequence,
        "validator_power": state.validator_power,
        "validator_public_keys": [value.hex() for value in state.validator_public_keys],
    }


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CodecError("value cannot be represented as canonical JSON") from error


def _validate_public_key(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("public key must be lowercase hexadecimal")
