# Encodes and decodes application messages deterministically.

from __future__ import annotations

import json
from datetime import UTC, datetime

from multiformats import CID, multihash
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictStr,
    ValidationError,
    field_validator,
)

from discovery_net.knowledge_graph.enums import ContributionKind, RelationKind
from discovery_net.knowledge_graph.identifiers import ArtifactRef
from discovery_net.knowledge_graph.models import Artifact, Contribution, ContributionRelation
from discovery_net.wire.envelope import PayloadType, SignedEnvelope

type JSONObject = dict[str, object]


class CodecError(ValueError):
    """Raised when application bytes do not follow the canonical wire format."""


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _ContributionPayload(_WireModel):
    body: StrictStr
    created_at: AwareDatetime
    kind: ContributionKind
    parent: StrictStr | None
    title: StrictStr

    @field_validator("parent")
    @classmethod
    def validate_parent(cls, value: str | None) -> str | None:
        if value is not None:
            parse_artifact_ref(value)
        return value


class _RelationPayload(_WireModel):
    created_at: AwareDatetime
    from_contribution: StrictStr
    kind: RelationKind
    to_contribution: StrictStr

    @field_validator("from_contribution", "to_contribution")
    @classmethod
    def validate_contribution_ref(cls, value: str) -> str:
        parse_artifact_ref(value)
        return value


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


def encode_payload(artifact: Artifact) -> tuple[PayloadType, bytes]:
    """Encode a supported knowledge-graph artifact into canonical JSON bytes."""

    try:
        if isinstance(artifact, Contribution):
            model = _ContributionPayload(
                body=artifact.body,
                created_at=artifact.created_at,
                kind=artifact.kind,
                parent=artifact.parent,
                title=artifact.title,
            )
            return PayloadType.CONTRIBUTION, _canonical_json(_contribution_value(model))

        if isinstance(artifact, ContributionRelation):
            relation = _RelationPayload(
                created_at=artifact.created_at,
                from_contribution=artifact.from_contribution,
                kind=artifact.kind,
                to_contribution=artifact.to_contribution,
            )
            return PayloadType.CONTRIBUTION_RELATION, _canonical_json(_relation_value(relation))
    except ValidationError as error:
        raise CodecError("artifact fields are invalid") from error

    raise TypeError("artifact must be a Contribution or ContributionRelation")


def decode_payload(payload_type: PayloadType, data: bytes) -> Artifact:
    """Decode one canonical knowledge-graph payload."""

    if not isinstance(data, bytes):
        raise TypeError("payload data must be bytes")

    try:
        if payload_type is PayloadType.CONTRIBUTION:
            model = _ContributionPayload.model_validate_json(data)
            artifact: Artifact = Contribution(
                kind=model.kind,
                title=model.title,
                body=model.body,
                created_at=model.created_at,
                parent=ArtifactRef(model.parent) if model.parent is not None else None,
            )
        elif payload_type is PayloadType.CONTRIBUTION_RELATION:
            relation = _RelationPayload.model_validate_json(data)
            artifact = ContributionRelation(
                from_contribution=ArtifactRef(relation.from_contribution),
                to_contribution=ArtifactRef(relation.to_contribution),
                kind=relation.kind,
                created_at=relation.created_at,
            )
        else:
            raise CodecError("payload type is not supported")
    except ValidationError as error:
        raise CodecError("payload fields are invalid") from error
    except (TypeError, ValueError) as error:
        if isinstance(error, CodecError):
            raise
        raise CodecError("payload fields are invalid") from error

    _, canonical = encode_payload(artifact)
    if canonical != data:
        raise CodecError("payload is not canonical")
    return artifact


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
        envelope = SignedEnvelope(
            chain_id=model.chain_id,
            payload_type=model.payload_type,
            payload=_canonical_json(model.payload),
            signer_public_key=bytes.fromhex(model.signer_public_key),
            signature=bytes.fromhex(model.signature),
        )
    except ValidationError as error:
        raise CodecError("envelope fields are invalid") from error
    except (TypeError, ValueError) as error:
        raise CodecError("envelope fields are invalid") from error

    decode_payload(envelope.payload_type, envelope.payload)
    if encode_envelope(envelope) != data:
        raise CodecError("envelope is not canonical")
    return envelope


def artifact_ref(envelope: SignedEnvelope) -> ArtifactRef:
    """Derive a canonical CIDv1 reference from the complete signed envelope."""

    digest = multihash.digest(encode_envelope(envelope), "sha2-256")
    return ArtifactRef(str(CID("base32", 1, "raw", digest)))


def parse_artifact_ref(value: str) -> ArtifactRef:
    """Validate and return a canonical Discovery Net artifact reference."""

    if not isinstance(value, str):
        raise TypeError("artifact reference must be a string")
    try:
        cid = CID.decode(value)
    except (KeyError, ValueError) as error:
        raise ValueError("artifact reference must be a valid CID") from error
    if (
        cid.version != 1
        or cid.base.name != "base32"
        or cid.codec.name != "raw"
        or cid.hashfun.name != "sha2-256"
        or str(cid) != value
    ):
        raise ValueError("artifact reference must be canonical CIDv1 raw sha2-256 base32")
    return ArtifactRef(value)


def _contribution_value(model: _ContributionPayload) -> JSONObject:
    return {
        "body": model.body,
        "created_at": _encode_datetime(model.created_at),
        "kind": model.kind.value,
        "parent": model.parent,
        "title": model.title,
    }


def _relation_value(model: _RelationPayload) -> JSONObject:
    return {
        "created_at": _encode_datetime(model.created_at),
        "from_contribution": model.from_contribution,
        "kind": model.kind.value,
        "to_contribution": model.to_contribution,
    }


def _envelope_value(envelope: SignedEnvelope, *, include_signature: bool) -> JSONObject:
    artifact = decode_payload(envelope.payload_type, envelope.payload)
    if isinstance(artifact, Contribution):
        payload_type, payload = encode_payload(artifact)
        payload_model = _ContributionPayload.model_validate_json(payload)
        payload_value = _contribution_value(payload_model)
    else:
        payload_type, payload = encode_payload(artifact)
        relation_model = _RelationPayload.model_validate_json(payload)
        payload_value = _relation_value(relation_model)

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


def _canonical_json(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise CodecError("value cannot be represented as canonical JSON") from error
    return encoded.encode("utf-8")


def _validate_lower_hex(value: str, field_name: str, byte_length: int) -> None:
    if len(value) != byte_length * 2 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be lowercase hexadecimal for {byte_length} bytes")


def _encode_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
