# Describes a relation originating from a contribution being submitted.

from dataclasses import dataclass

from discovery_net.artifacts import ArtifactRef
from discovery_net.domains.math import RelationKind


@dataclass(frozen=True, slots=True, kw_only=True)
class OutgoingRelation:
    """Places the new contribution at the source of a relation."""

    kind: RelationKind
    to_contribution: ArtifactRef

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RelationKind):
            raise TypeError("kind must be a RelationKind")
        if not isinstance(self.to_contribution, str):
            raise TypeError("to_contribution must be an artifact reference")
        if not self.to_contribution:
            raise ValueError("to_contribution must not be blank")
