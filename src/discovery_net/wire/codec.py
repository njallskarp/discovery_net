# Encodes and decodes application messages deterministically.

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

from discovery_net.knowledge_graph.enums import ContributionKind, RelationKind
from discovery_net.knowledge_graph.identifiers import ContributionId, RelationId
from discovery_net.knowledge_graph.models import Contribution, ContributionRelation
from discovery_net.wire.envelope import PayloadType, SignedEnvelope, TransactionId

type Artifact = Contribution | ContributionRelation
type JSONObject = dict[str, object]


class CodecError(ValueError):
    """Raised when application bytes do not follow the canonical wire format."""


def encode_payload(artifact: Artifact) -> tuple[PayloadType, bytes]:
    """Encode a supported knowledge-graph artifact into canonical JSON bytes."""

    if isinstance(artifact, Contribution):
        value: JSONObject = {
            "body": artifact.body,
            "created_at": _encode_datetime(artifact.created_at),
            "id": artifact.id,
            "kind": artifact.kind.value,
            "parent_id": artifact.parent_id,
            "thread_root_id": artifact.thread_root_id,
            "title": artifact.title,
        }
        return PayloadType.CONTRIBUTION, _canonical_json(value)

    if isinstance(artifact, ContributionRelation):
        value = {
            "created_at": _encode_datetime(artifact.created_at),
            "from_contribution_id": artifact.from_contribution_id,
            "id": artifact.id,
            "kind": artifact.kind.value,
            "to_contribution_id": artifact.to_contribution_id,
        }
        return PayloadType.CONTRIBUTION_RELATION, _canonical_json(value)

    raise TypeError("artifact must be a Contribution or ContributionRelation")


def decode_payload(payload_type: PayloadType, data: bytes) -> Artifact:
    """Decode one canonical knowledge-graph payload."""

    value = _load_object(data, "payload")

    try:
        if payload_type is PayloadType.CONTRIBUTION:
            _require_keys(
                value,
                {
                    "body",
                    "created_at",
                    "id",
                    "kind",
                    "parent_id",
                    "thread_root_id",
                    "title",
                },
            )
            artifact: Artifact = Contribution(
                id=ContributionId(_require_string(value, "id")),
                thread_root_id=ContributionId(_require_string(value, "thread_root_id")),
                kind=ContributionKind(_require_string(value, "kind")),
                title=_require_string(value, "title"),
                body=_require_string(value, "body"),
                created_at=_decode_datetime(_require_string(value, "created_at")),
                parent_id=_optional_contribution_id(value, "parent_id"),
            )
        elif payload_type is PayloadType.CONTRIBUTION_RELATION:
            _require_keys(
                value,
                {
                    "created_at",
                    "from_contribution_id",
                    "id",
                    "kind",
                    "to_contribution_id",
                },
            )
            artifact = ContributionRelation(
                id=RelationId(_require_string(value, "id")),
                from_contribution_id=ContributionId(_require_string(value, "from_contribution_id")),
                to_contribution_id=ContributionId(_require_string(value, "to_contribution_id")),
                kind=RelationKind(_require_string(value, "kind")),
                created_at=_decode_datetime(_require_string(value, "created_at")),
            )
        else:
            raise CodecError("payload type is not supported")
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

    return _canonical_json(_envelope_object(envelope, include_signature=False))


def encode_envelope(envelope: SignedEnvelope) -> bytes:
    """Encode a signed envelope into its unique wire representation."""

    return _canonical_json(_envelope_object(envelope, include_signature=True))


def decode_envelope(data: bytes) -> SignedEnvelope:
    """Decode one complete canonical signed envelope."""

    value = _load_object(data, "envelope")
    _require_keys(
        value,
        {"network_id", "payload", "payload_type", "signature", "signer_public_key"},
    )
    payload_value = value["payload"]
    if not isinstance(payload_value, dict):
        raise CodecError("payload must be a JSON object")

    try:
        envelope = SignedEnvelope(
            network_id=_require_string(value, "network_id"),
            payload_type=PayloadType(_require_string(value, "payload_type")),
            payload=_canonical_json(payload_value),
            signer_public_key=bytes.fromhex(_require_string(value, "signer_public_key")),
            signature=bytes.fromhex(_require_string(value, "signature")),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, CodecError):
            raise
        raise CodecError("envelope fields are invalid") from error

    decode_payload(envelope.payload_type, envelope.payload)
    if encode_envelope(envelope) != data:
        raise CodecError("envelope is not canonical")
    return envelope


def transaction_id(envelope: SignedEnvelope) -> TransactionId:
    """Derive the transaction identifier from the complete signed envelope."""

    return TransactionId(sha256(encode_envelope(envelope)).hexdigest())


def _envelope_object(envelope: SignedEnvelope, *, include_signature: bool) -> JSONObject:
    payload = _load_object(envelope.payload, "payload")
    decode_payload(envelope.payload_type, envelope.payload)
    value: JSONObject = {
        "network_id": envelope.network_id,
        "payload": payload,
        "payload_type": envelope.payload_type.value,
        "signer_public_key": envelope.signer_public_key.hex(),
    }
    if include_signature:
        value["signature"] = envelope.signature.hex()
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


def _load_object(data: bytes, label: str) -> JSONObject:
    if not isinstance(data, bytes):
        raise TypeError(f"{label} data must be bytes")

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, CodecError) as error:
        raise CodecError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise CodecError(f"{label} must be a JSON object")
    return cast(JSONObject, value)


def _unique_object(pairs: list[tuple[str, object]]) -> JSONObject:
    value: JSONObject = {}
    for key, item in pairs:
        if key in value:
            raise CodecError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise CodecError(f"invalid JSON constant: {value}")


def _require_keys(value: JSONObject, expected: set[str]) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing keys: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected keys: {', '.join(unexpected)}")
        raise CodecError("; ".join(details))


def _require_string(value: JSONObject, key: str) -> str:
    item = value[key]
    if not isinstance(item, str):
        raise CodecError(f"{key} must be a string")
    return item


def _optional_contribution_id(value: JSONObject, key: str) -> ContributionId | None:
    item = value[key]
    if item is None:
        return None
    if not isinstance(item, str):
        raise CodecError(f"{key} must be a string or null")
    return ContributionId(item)


def _encode_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decode_datetime(value: str) -> datetime:
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise CodecError("created_at must be an ISO 8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CodecError("created_at must include a UTC offset")
    return parsed
