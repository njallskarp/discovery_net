# Encodes and decodes application messages deterministically.

from __future__ import annotations

import json

from multiformats import CID, multihash
from pydantic import (
    BaseModel,
    ConfigDict,
    StrictStr,
    ValidationError,
    field_validator,
)

from discovery_net.artifacts.encoding import CodecError as CodecError
from discovery_net.artifacts.encoding import canonical_json as _canonical_json
from discovery_net.artifacts.identifiers import ArtifactRef
from discovery_net.artifacts.identifiers import parse_artifact_ref as parse_artifact_ref
from discovery_net.domains.math.codec import MATH_DOMAIN
from discovery_net.domains.math.models import Artifact
from discovery_net.wire.envelope import PayloadType, SignedEnvelope, SignedTransaction

type JSONObject = dict[str, object]


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _EnvelopePayload(_WireModel):
    chain_id: StrictStr
    payload: dict[str, object]
    payload_type: PayloadType
    signature: StrictStr
    signer_public_key: StrictStr

    @field_validator("chain_id")
    @classmethod
    def validate_chain_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chain_id must not be blank")
        return value

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        _validate_lower_hex(value, "signature", 64)
        return value

    @field_validator("signer_public_key")
    @classmethod
    def validate_signer_public_key(cls, value: str) -> str:
        _validate_lower_hex(value, "signer_public_key", 32)
        return value


class _TransactionPayload(_WireModel):
    envelopes: tuple[_EnvelopePayload, ...]
    signature: StrictStr

    @field_validator("signature")
    @classmethod
    def validate_signature(cls, value: str) -> str:
        _validate_lower_hex(value, "signature", 64)
        return value


def encode_payload(artifact: Artifact) -> tuple[PayloadType, bytes]:
    """Encode the one domain supported by the current network protocol."""
    payload_type, encoded = MATH_DOMAIN.encode(artifact)
    return PayloadType(payload_type), encoded


def decode_payload(payload_type: PayloadType, data: bytes) -> Artifact:
    """Validate a math payload without enabling additional wire types."""
    if not isinstance(data, bytes):
        raise TypeError("payload data must be bytes")
    if not isinstance(payload_type, PayloadType):
        raise CodecError("payload type is not supported")
    return MATH_DOMAIN.decode(payload_type.value, data)


def encode_signing_payload(envelope: SignedEnvelope) -> bytes:
    """Encode exactly the envelope fields covered by its signer signature."""

    return _canonical_json(_envelope_value(envelope, include_signature=False))


def encode_envelope(envelope: SignedEnvelope) -> bytes:
    """Encode a signed envelope into its unique wire representation."""

    return _canonical_json(_envelope_value(envelope, include_signature=True))


def decode_envelope(data: bytes) -> SignedEnvelope:
    """Decode one complete canonical signed envelope."""

    if not isinstance(data, bytes):
        raise TypeError("envelope data must be bytes")

    try:
        model = _EnvelopePayload.model_validate_json(data)
        envelope = _envelope_from_model(model)
    except ValidationError as error:
        raise CodecError("envelope fields are invalid") from error
    except (TypeError, ValueError) as error:
        raise CodecError("envelope fields are invalid") from error

    if encode_envelope(envelope) != data:
        raise CodecError("envelope is not canonical")
    return envelope


def encode_transaction_signing_payload(transaction: SignedTransaction) -> bytes:
    """Encode exactly the transaction fields covered by its signature."""
    return _canonical_json(_transaction_value(transaction, include_signature=False))


def encode_transaction(transaction: SignedTransaction) -> bytes:
    """Encode an atomic signed transaction into its unique wire representation."""
    return _canonical_json(_transaction_value(transaction, include_signature=True))


def decode_transaction(data: bytes) -> SignedTransaction:
    """Decode one canonical atomic transaction."""
    if not isinstance(data, bytes):
        raise TypeError("transaction data must be bytes")

    try:
        model = _TransactionPayload.model_validate_json(data)
        transaction = SignedTransaction(
            envelopes=tuple(_envelope_from_model(envelope) for envelope in model.envelopes),
            signature=bytes.fromhex(model.signature),
        )
    except ValidationError as error:
        raise CodecError("transaction fields are invalid") from error
    except (TypeError, ValueError) as error:
        raise CodecError("transaction fields are invalid") from error

    if encode_transaction(transaction) != data:
        raise CodecError("transaction is not canonical")
    return transaction


def artifact_ref(envelope: SignedEnvelope) -> ArtifactRef:
    """Derive a canonical CIDv1 reference from the complete signed envelope."""

    digest = multihash.digest(encode_envelope(envelope), "sha2-256")
    return ArtifactRef(str(CID("base32", 1, "raw", digest)))


def _envelope_value(envelope: SignedEnvelope, *, include_signature: bool) -> JSONObject:
    artifact = decode_payload(envelope.payload_type, envelope.payload)
    payload_type, payload = encode_payload(artifact)
    payload_value: JSONObject = json.loads(payload)

    model = _EnvelopePayload(
        chain_id=envelope.chain_id,
        payload=payload_value,
        payload_type=payload_type,
        signature=envelope.signature.hex(),
        signer_public_key=envelope.signer_public_key.hex(),
    )
    value: JSONObject = {
        "chain_id": model.chain_id,
        "payload": model.payload,
        "payload_type": model.payload_type.value,
        "signer_public_key": model.signer_public_key,
    }
    if include_signature:
        value["signature"] = model.signature
    return value


def _transaction_value(
    transaction: SignedTransaction,
    *,
    include_signature: bool,
) -> JSONObject:
    value: JSONObject = {
        "envelopes": [
            _envelope_value(envelope, include_signature=True) for envelope in transaction.envelopes
        ]
    }
    if include_signature:
        value["signature"] = transaction.signature.hex()
    return value


def _envelope_from_model(model: _EnvelopePayload) -> SignedEnvelope:
    envelope = SignedEnvelope(
        chain_id=model.chain_id,
        payload_type=model.payload_type,
        payload=_canonical_json(model.payload),
        signer_public_key=bytes.fromhex(model.signer_public_key),
        signature=bytes.fromhex(model.signature),
    )
    decode_payload(envelope.payload_type, envelope.payload)
    return envelope


def _validate_lower_hex(value: str, field_name: str, byte_length: int) -> None:
    if len(value) != byte_length * 2 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be lowercase hexadecimal for {byte_length} bytes")
