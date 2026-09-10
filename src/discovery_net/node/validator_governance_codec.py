# Encodes validator-governance state for genesis and local persistence.

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError, field_validator

from discovery_net.node.validator_governance import (
    ScheduledValidatorChange,
    ValidatorGovernanceState,
    ValidatorProposalRecord,
)
from discovery_net.wire.codec import CodecError
from discovery_net.wire.validator_governance import (
    ValidatorMembershipOperation,
    ValidatorMembershipProposal,
    ValidatorOperator,
)
from discovery_net.wire.validator_governance_codec import (
    decode_validator_governance_transaction,
    encode_validator_governance_transaction,
)

type JSONObject = dict[str, object]


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _OperatorPayload(_WireModel):
    consensus_public_key: StrictStr
    governance_public_key: StrictStr

    @field_validator("consensus_public_key", "governance_public_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        _validate_hex(value, 32, "public key")
        return value


class _ProposalRecordPayload(_WireModel):
    approvals: tuple[StrictStr, ...]
    proposal: StrictStr
    proposal_id: StrictStr
    validator_set_hash: StrictStr

    @field_validator("approvals")
    @classmethod
    def validate_approvals(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            _validate_hex(value, 32, "approval public key")
        return values

    @field_validator("proposal_id", "validator_set_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_hex(value, 32, "hash")
        return value

    @field_validator("proposal")
    @classmethod
    def validate_proposal(cls, value: str) -> str:
        _validate_variable_hex(value, "proposal")
        return value


class _ScheduledChangePayload(_WireModel):
    effective_height: StrictInt
    operation: ValidatorMembershipOperation
    operator: _OperatorPayload
    proposal_id: StrictStr

    @field_validator("proposal_id")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _validate_hex(value, 32, "proposal ID")
        return value


class _GovernanceStatePayload(_WireModel):
    operators: tuple[_OperatorPayload, ...]
    proposals: tuple[_ProposalRecordPayload, ...]
    scheduled_change: _ScheduledChangePayload | None
    validator_power: StrictInt


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
        value = json.loads(data, object_pairs_hook=_object_without_duplicate_keys)
        model = _GenesisApplicationStatePayload.model_validate_json(_canonical_json(value))
        state = _state_from_model(model.validator_governance)
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        ValidationError,
        TypeError,
        ValueError,
    ) as error:
        raise CodecError("genesis application state is invalid") from error
    return state


def _state_from_model(model: _GovernanceStatePayload) -> ValidatorGovernanceState:
    proposals: list[ValidatorProposalRecord] = []
    for value in model.proposals:
        proposal = decode_validator_governance_transaction(bytes.fromhex(value.proposal))
        if not isinstance(proposal, ValidatorMembershipProposal):
            raise ValueError("stored proposal must be a membership proposal")
        proposals.append(
            ValidatorProposalRecord(
                proposal_id=bytes.fromhex(value.proposal_id),
                proposal=proposal,
                validator_set_hash=bytes.fromhex(value.validator_set_hash),
                approvals=tuple(bytes.fromhex(key) for key in value.approvals),
            )
        )
    scheduled = model.scheduled_change
    return ValidatorGovernanceState(
        operators=tuple(_operator_from_model(value) for value in model.operators),
        validator_power=model.validator_power,
        proposals=tuple(proposals),
        scheduled_change=(
            None
            if scheduled is None
            else ScheduledValidatorChange(
                proposal_id=bytes.fromhex(scheduled.proposal_id),
                operation=scheduled.operation,
                operator=_operator_from_model(scheduled.operator),
                effective_height=scheduled.effective_height,
            )
        ),
    )


def _governance_state_value(state: ValidatorGovernanceState) -> JSONObject:
    scheduled = state.scheduled_change
    return {
        "operators": [_operator_value(value) for value in state.operators],
        "proposals": [
            {
                "approvals": [key.hex() for key in value.approvals],
                "proposal": encode_validator_governance_transaction(value.proposal).hex(),
                "proposal_id": value.proposal_id.hex(),
                "validator_set_hash": value.validator_set_hash.hex(),
            }
            for value in state.proposals
        ],
        "scheduled_change": (
            None
            if scheduled is None
            else {
                "effective_height": scheduled.effective_height,
                "operation": scheduled.operation.value,
                "operator": _operator_value(scheduled.operator),
                "proposal_id": scheduled.proposal_id.hex(),
            }
        ),
        "validator_power": state.validator_power,
    }


def _operator_value(operator: ValidatorOperator) -> JSONObject:
    return {
        "consensus_public_key": operator.consensus_public_key.hex(),
        "governance_public_key": operator.governance_public_key.hex(),
    }


def _operator_from_model(model: _OperatorPayload) -> ValidatorOperator:
    return ValidatorOperator(
        consensus_public_key=bytes.fromhex(model.consensus_public_key),
        governance_public_key=bytes.fromhex(model.governance_public_key),
    )


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


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> JSONObject:
    value: JSONObject = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _validate_hex(value: str, byte_length: int, description: str) -> None:
    if len(value) != byte_length * 2 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{description} must be lowercase hexadecimal")


def _validate_variable_hex(value: str, description: str) -> None:
    if (
        not value
        or len(value) % 2
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{description} must be nonempty lowercase hexadecimal")
