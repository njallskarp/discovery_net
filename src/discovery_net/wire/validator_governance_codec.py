# Encodes validator-governance state and transactions as canonical JSON.

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError, field_validator

from discovery_net.wire.codec import CodecError
from discovery_net.wire.validator_governance import (
    GovernanceApproval,
    SignedValidatorSetChange,
    ValidatorMembershipChange,
    ValidatorMembershipOperation,
    ValidatorSetChange,
)

type JSONObject = dict[str, object]

_TRANSACTION_TYPE = "validator_set_change"


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _MembershipChangePayload(_WireModel):
    operation: ValidatorMembershipOperation
    public_key: StrictStr

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _validate_lower_hex(value, "public_key", 32)
        return value


class _ValidatorSetChangePayload(_WireModel):
    chain_id: StrictStr
    changes: tuple[_MembershipChangePayload, ...]
    sequence: StrictInt


class _ApprovalPayload(_WireModel):
    signature: StrictStr
    signer_public_key: StrictStr

    @field_validator("signer_public_key")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _validate_lower_hex(value, "signer_public_key", 32)
        return value

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        _validate_lower_hex(value, "signature", 64)
        return value


class _SignedChangePayload(_WireModel):
    approvals: tuple[_ApprovalPayload, ...]
    change: _ValidatorSetChangePayload
    type: StrictStr

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != _TRANSACTION_TYPE:
            raise ValueError("type must identify a validator-set change")
        return value


def encode_validator_set_change_signing_payload(change: ValidatorSetChange) -> bytes:
    """Encode exactly the validator-set-change fields covered by each approval."""
    return _canonical_json(_change_value(change))


def encode_validator_set_change(transaction: SignedValidatorSetChange) -> bytes:
    """Encode a signed validator-set change into its unique wire representation."""
    if not isinstance(transaction, SignedValidatorSetChange):
        raise TypeError("transaction must be a SignedValidatorSetChange")
    return _canonical_json(
        {
            "approvals": [_approval_value(approval) for approval in transaction.approvals],
            "change": _change_value(transaction.change),
            "type": _TRANSACTION_TYPE,
        }
    )


def decode_validator_set_change(data: bytes) -> SignedValidatorSetChange:
    """Decode one canonical signed validator-set-change transaction."""
    if not isinstance(data, bytes):
        raise TypeError("transaction data must be bytes")
    try:
        model = _SignedChangePayload.model_validate_json(data)
        transaction = SignedValidatorSetChange(
            change=_change_from_model(model.change),
            approvals=tuple(
                GovernanceApproval(
                    signer_public_key=bytes.fromhex(approval.signer_public_key),
                    signature=bytes.fromhex(approval.signature),
                )
                for approval in model.approvals
            ),
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise CodecError("validator-set-change fields are invalid") from error
    if encode_validator_set_change(transaction) != data:
        raise CodecError("validator-set-change transaction is not canonical")
    return transaction


def _change_value(change: ValidatorSetChange) -> JSONObject:
    return {
        "chain_id": change.chain_id,
        "changes": [
            {"operation": item.operation.value, "public_key": item.public_key.hex()}
            for item in change.changes
        ],
        "sequence": change.sequence,
    }


def _approval_value(approval: GovernanceApproval) -> JSONObject:
    return {
        "signature": approval.signature.hex(),
        "signer_public_key": approval.signer_public_key.hex(),
    }


def _change_from_model(model: _ValidatorSetChangePayload) -> ValidatorSetChange:
    return ValidatorSetChange(
        chain_id=model.chain_id,
        sequence=model.sequence,
        changes=tuple(
            ValidatorMembershipChange(
                public_key=bytes.fromhex(change.public_key),
                operation=change.operation,
            )
            for change in model.changes
        ),
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


def _validate_lower_hex(value: str, field_name: str, byte_length: int) -> None:
    if len(value) != byte_length * 2 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be lowercase hexadecimal")
