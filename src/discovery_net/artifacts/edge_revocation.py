"""A permanent withdrawal of one edge from graph views, preserving signed history."""

from dataclasses import dataclass
from datetime import datetime

from discovery_net.artifacts.identifiers import ArtifactRef, parse_artifact_ref


@dataclass(frozen=True, slots=True, kw_only=True)
class EdgeRevocation:
    target: ArtifactRef
    reason: str
    created_at: datetime

    def __post_init__(self) -> None:
        parse_artifact_ref(self.target)
        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
