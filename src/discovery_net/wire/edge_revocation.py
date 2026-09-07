"""Canonical wire representation of a permanent edge revocation."""

from datetime import UTC

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictStr, ValidationError

from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.artifacts.encoding import CodecError, canonical_json
from discovery_net.artifacts.identifiers import ArtifactRef


class _RevocationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target: StrictStr
    reason: StrictStr
    created_at: AwareDatetime


def encode_revocation(artifact: EdgeRevocation) -> bytes:
    return canonical_json(
        {
            "target": artifact.target,
            "reason": artifact.reason,
            "created_at": artifact.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        }
    )


def decode_revocation(data: bytes) -> EdgeRevocation:
    try:
        model = _RevocationPayload.model_validate_json(data)
        artifact = EdgeRevocation(
            target=ArtifactRef(model.target), reason=model.reason, created_at=model.created_at
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise CodecError("revocation fields are invalid") from error
    if encode_revocation(artifact) != data:
        raise CodecError("revocation is not canonical")
    return artifact
