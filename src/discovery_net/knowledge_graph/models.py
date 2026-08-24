# Immutable models representing knowledge-graph entities.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from discovery_net.knowledge_graph.enums import ContributionKind, RelationKind
from discovery_net.knowledge_graph.identifiers import ArtifactRef


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class Contribution:
    """A mathematical, conversational, or organizational artifact."""

    kind: ContributionKind
    title: str
    body: str
    created_at: datetime
    parent: ArtifactRef | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.title, "title")
        _require_aware(self.created_at, "created_at")
        if self.parent is not None:
            _require_non_blank(self.parent, "parent")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionRelation:
    """An attributable edge connecting two contributions."""

    from_contribution: ArtifactRef
    to_contribution: ArtifactRef
    kind: RelationKind
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.from_contribution, "from_contribution")
        _require_non_blank(self.to_contribution, "to_contribution")
        _require_aware(self.created_at, "created_at")
        if self.from_contribution == self.to_contribution:
            raise ValueError("a relation must connect two distinct contributions")


type Artifact = Contribution | ContributionRelation
