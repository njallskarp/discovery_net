# Encodes validator-governance messages as canonical JSON.

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError, field_validator

from discovery_net.wire.codec import CodecError
from discovery_net.wire.validator_governance import (
    ConsensusValidatorNomination,
    SignedValidatorNomination,
    ValidatorGovernanceTransaction,
    ValidatorMembershipOperation,
    ValidatorMembershipProposal,
    ValidatorOperator,
    ValidatorProposalApproval,
)

type JSONObject = dict[str, object]

_PROPOSAL_TYPE = "validator_membership_proposal"
_APPROVAL_TYPE = "validator_proposal_approval"


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _OperatorPayload(_WireModel):
    consensus_public_key: StrictStr
    governance_public_key: StrictStr

    @field_validator("consensus_public_key", "governance_public_key")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _validate_lower_hex(value, "public key", 32)
        return value


class _NominationPayload(_WireModel):
    chain_id: StrictStr
    consensus_signature: StrictStr
    governance_signature: StrictStr
    operator: _OperatorPayload

    @field_validator("consensus_signature", "governance_signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        _validate_lower_hex(value, "signature", 64)
        return value


class _ConsensusNominationPayload(_WireModel):
    chain_id: StrictStr
    consensus_signature: StrictStr
    operator: _OperatorPayload

    @field_validator("consensus_signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        _validate_lower_hex(value, "signature", 64)
        return value


class _ProposalPayload(_WireModel):
    chain_id: StrictStr
    nomination: _NominationPayload | None
    operation: ValidatorMembershipOperation
    operator: _OperatorPayload
    sponsor_public_key: StrictStr
    sponsor_signature: StrictStr
    type: StrictStr

    @field_validator("sponsor_public_key")
    @classmethod
    def validate_public_key(cls, value: str) -> str:
        _validate_lower_hex(value, "sponsor_public_key", 32)
        return value

    @field_validator("sponsor_signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        _validate_lower_hex(value, "sponsor_signature", 64)
        return value

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != _PROPOSAL_TYPE:
            raise ValueError("type must identify a validator-membership proposal")
        return value


class _ApprovalPayload(_WireModel):
    chain_id: StrictStr
    proposal_id: StrictStr
    signature: StrictStr
    signer_public_key: StrictStr
    type: StrictStr

    @field_validator("proposal_id")
    @classmethod
    def validate_proposal_id(cls, value: str) -> str:
        _validate_lower_hex(value, "proposal_id", 32)
        return value

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

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != _APPROVAL_TYPE:
            raise ValueError("type must identify a validator-proposal approval")
        return value


def encode_nomination_signing_payload(
    *,
    chain_id: str,
    operator: ValidatorOperator,
) -> bytes:
    """Encode the nomination fields covered by both candidate signatures."""
    return _canonical_json({"chain_id": chain_id, "operator": _operator_value(operator)})


def encode_validator_nomination(nomination: SignedValidatorNomination) -> bytes:
    """Encode a signed candidate nomination for transport between operators."""
    if not isinstance(nomination, SignedValidatorNomination):
        raise TypeError("nomination must be a SignedValidatorNomination")
    return _canonical_json(_nomination_value(nomination))


def encode_consensus_validator_nomination(
    nomination: ConsensusValidatorNomination,
) -> bytes:
    """Encode the candidate consensus key's shareable nomination half."""
    if not isinstance(nomination, ConsensusValidatorNomination):
        raise TypeError("nomination must be a ConsensusValidatorNomination")
    return _canonical_json(
        {
            "chain_id": nomination.chain_id,
            "consensus_signature": nomination.consensus_signature.hex(),
            "operator": _operator_value(nomination.operator),
        }
    )


def decode_consensus_validator_nomination(data: bytes) -> ConsensusValidatorNomination:
    """Decode one canonical consensus-signed nomination half."""
    if not isinstance(data, bytes):
        raise TypeError("nomination data must be bytes")
    try:
        model = _ConsensusNominationPayload.model_validate_json(data)
        nomination = ConsensusValidatorNomination(
            chain_id=model.chain_id,
            operator=_operator_from_model(model.operator),
            consensus_signature=bytes.fromhex(model.consensus_signature),
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise CodecError("consensus validator nomination fields are invalid") from error
    if encode_consensus_validator_nomination(nomination) != data:
        raise CodecError("consensus validator nomination is not canonical")
    return nomination


def decode_validator_nomination(data: bytes) -> SignedValidatorNomination:
    """Decode one canonical candidate nomination."""
    if not isinstance(data, bytes):
        raise TypeError("nomination data must be bytes")
    try:
        nomination = _nomination_from_model(_NominationPayload.model_validate_json(data))
    except (ValidationError, TypeError, ValueError) as error:
        raise CodecError("validator nomination fields are invalid") from error
    if encode_validator_nomination(nomination) != data:
        raise CodecError("validator nomination is not canonical")
    return nomination


def encode_proposal_signing_payload(proposal: ValidatorMembershipProposal) -> bytes:
    """Encode exactly the proposal fields covered by the sponsor signature."""
    return _canonical_json(_proposal_value(proposal, include_signature=False))


def encode_approval_signing_payload(approval: ValidatorProposalApproval) -> bytes:
    """Encode exactly the approval fields covered by the operator signature."""
    return _canonical_json(_approval_value(approval, include_signature=False))


def encode_validator_governance_transaction(transaction: ValidatorGovernanceTransaction) -> bytes:
    """Encode one governance transaction into its unique wire representation."""
    if isinstance(transaction, ValidatorMembershipProposal):
        return _canonical_json(_proposal_value(transaction, include_signature=True))
    if isinstance(transaction, ValidatorProposalApproval):
        return _canonical_json(_approval_value(transaction, include_signature=True))
    raise TypeError("transaction must be a validator-governance transaction")


def decode_validator_governance_transaction(data: bytes) -> ValidatorGovernanceTransaction:
    """Decode one canonical validator-governance transaction."""
    if not isinstance(data, bytes):
        raise TypeError("transaction data must be bytes")
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("transaction must be an object")
        transaction_type = value.get("type")
        if transaction_type == _PROPOSAL_TYPE:
            transaction: ValidatorGovernanceTransaction = _proposal_from_model(
                _ProposalPayload.model_validate_json(data)
            )
        elif transaction_type == _APPROVAL_TYPE:
            transaction = _approval_from_model(_ApprovalPayload.model_validate_json(data))
        else:
            raise ValueError("transaction type is not validator governance")
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
        raise CodecError("validator-governance transaction fields are invalid") from error
    if encode_validator_governance_transaction(transaction) != data:
        raise CodecError("validator-governance transaction is not canonical")
    return transaction


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


def _nomination_value(nomination: SignedValidatorNomination) -> JSONObject:
    return {
        "chain_id": nomination.chain_id,
        "consensus_signature": nomination.consensus_signature.hex(),
        "governance_signature": nomination.governance_signature.hex(),
        "operator": _operator_value(nomination.operator),
    }


def _nomination_from_model(model: _NominationPayload) -> SignedValidatorNomination:
    return SignedValidatorNomination(
        chain_id=model.chain_id,
        operator=_operator_from_model(model.operator),
        consensus_signature=bytes.fromhex(model.consensus_signature),
        governance_signature=bytes.fromhex(model.governance_signature),
    )


def _proposal_value(
    proposal: ValidatorMembershipProposal,
    *,
    include_signature: bool,
) -> JSONObject:
    value: JSONObject = {
        "chain_id": proposal.chain_id,
        "nomination": (
            None if proposal.nomination is None else _nomination_value(proposal.nomination)
        ),
        "operation": proposal.operation.value,
        "operator": _operator_value(proposal.operator),
        "sponsor_public_key": proposal.sponsor_public_key.hex(),
        "type": _PROPOSAL_TYPE,
    }
    if include_signature:
        value["sponsor_signature"] = proposal.sponsor_signature.hex()
    return value


def _proposal_from_model(model: _ProposalPayload) -> ValidatorMembershipProposal:
    return ValidatorMembershipProposal(
        chain_id=model.chain_id,
        operation=model.operation,
        operator=_operator_from_model(model.operator),
        sponsor_public_key=bytes.fromhex(model.sponsor_public_key),
        sponsor_signature=bytes.fromhex(model.sponsor_signature),
        nomination=(None if model.nomination is None else _nomination_from_model(model.nomination)),
    )


def _approval_value(
    approval: ValidatorProposalApproval,
    *,
    include_signature: bool,
) -> JSONObject:
    value: JSONObject = {
        "chain_id": approval.chain_id,
        "proposal_id": approval.proposal_id.hex(),
        "signer_public_key": approval.signer_public_key.hex(),
        "type": _APPROVAL_TYPE,
    }
    if include_signature:
        value["signature"] = approval.signature.hex()
    return value


def _approval_from_model(model: _ApprovalPayload) -> ValidatorProposalApproval:
    return ValidatorProposalApproval(
        chain_id=model.chain_id,
        proposal_id=bytes.fromhex(model.proposal_id),
        signer_public_key=bytes.fromhex(model.signer_public_key),
        signature=bytes.fromhex(model.signature),
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
