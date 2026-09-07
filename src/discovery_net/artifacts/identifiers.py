"""Artifact identifiers and canonical CID validation."""

from functools import lru_cache
from typing import NewType

from multiformats import CID

ArtifactRef = NewType("ArtifactRef", str)


def parse_artifact_ref(value: str) -> ArtifactRef:
    """Validate and return a canonical Discovery Net artifact reference."""

    if not isinstance(value, str):
        raise TypeError("artifact reference must be a string")
    return _parse_artifact_ref(value)


@lru_cache(maxsize=8192)
def _parse_artifact_ref(value: str) -> ArtifactRef:
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
