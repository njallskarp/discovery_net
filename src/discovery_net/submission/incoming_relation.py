# Describes a relation terminating at a contribution being submitted.

from dataclasses import dataclass

from discovery_net.knowledge_graph import ArtifactRef, RelationKind


@dataclass(frozen=True, slots=True, kw_only=True)
class IncomingRelation:
    """Places the new contribution at the destination of a relation."""

    from_contribution: ArtifactRef
    kind: RelationKind

    def __post_init__(self) -> None:
        if not isinstance(self.from_contribution, str):
            raise TypeError("from_contribution must be an artifact reference")
        if not self.from_contribution:
            raise ValueError("from_contribution must not be blank")
        if not isinstance(self.kind, RelationKind):
            raise TypeError("kind must be a RelationKind")
