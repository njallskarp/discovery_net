"""Canonical math payload encoding, validation, and reference rules."""

from datetime import UTC, datetime
from typing import Final

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictStr,
    ValidationError,
    field_validator,
)

from discovery_net.artifacts.encoding import CodecError
from discovery_net.artifacts.encoding import canonical_json as _canonical_json
from discovery_net.artifacts.identifiers import ArtifactRef, parse_artifact_ref
from discovery_net.domains.base import ArtifactDomain
from discovery_net.domains.math.enums import ContributionKind, RelationKind
from discovery_net.domains.math.models import Artifact, Contribution, ContributionRelation

type JSONObject = dict[str, object]


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _ContributionPayload(_WireModel):
    body: StrictStr
    created_at: AwareDatetime
    kind: ContributionKind
    title: StrictStr


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


def encode_payload(artifact: Artifact) -> tuple[str, bytes]:
    """Encode a supported knowledge-graph artifact into canonical JSON bytes."""

    try:
        if isinstance(artifact, Contribution):
            model = _ContributionPayload(
                body=artifact.body,
                created_at=artifact.created_at,
                kind=artifact.kind,
                title=artifact.title,
            )
            return "contribution", _canonical_json(_contribution_value(model))

        if isinstance(artifact, ContributionRelation):
            relation = _RelationPayload(
                created_at=artifact.created_at,
                from_contribution=artifact.from_contribution,
                kind=artifact.kind,
                to_contribution=artifact.to_contribution,
            )
            return "contribution_relation", _canonical_json(_relation_value(relation))
    except ValidationError as error:
        raise CodecError("artifact fields are invalid") from error

    raise TypeError("artifact must be a Contribution or ContributionRelation")


def decode_payload(payload_type: str, data: bytes) -> Artifact:
    """Decode one canonical knowledge-graph payload."""

    if not isinstance(data, bytes):
        raise TypeError("payload data must be bytes")

    try:
        if payload_type == "contribution":
            model = _ContributionPayload.model_validate_json(data)
            artifact: Artifact = Contribution(
                kind=model.kind,
                title=model.title,
                body=model.body,
                created_at=model.created_at,
            )
        elif payload_type == "contribution_relation":
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


def _contribution_value(model: _ContributionPayload) -> JSONObject:
    return {
        "body": model.body,
        "created_at": _encode_datetime(model.created_at),
        "kind": model.kind.value,
        "title": model.title,
    }


def _relation_value(model: _RelationPayload) -> JSONObject:
    return {
        "created_at": _encode_datetime(model.created_at),
        "from_contribution": model.from_contribution,
        "kind": model.kind.value,
        "to_contribution": model.to_contribution,
    }


def _encode_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class MathDomain:
    """Canonical payload validation and graph reference rules for existing math artifacts."""

    __slots__ = ()

    def encode(self, artifact: Artifact) -> tuple[str, bytes]:
        return encode_payload(artifact)

    def decode(self, payload_type: str, data: bytes) -> Artifact:
        return decode_payload(payload_type, data)

    def is_node(self, artifact: Artifact) -> bool:
        return isinstance(artifact, Contribution)

    def references(self, artifact: Artifact) -> tuple[ArtifactRef, ...]:
        if isinstance(artifact, ContributionRelation):
            return artifact.from_contribution, artifact.to_contribution
        return ()


MATH_DOMAIN: Final[ArtifactDomain[Artifact]] = MathDomain()
