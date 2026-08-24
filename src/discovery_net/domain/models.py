"""Immutable, persistence-independent domain dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from discovery_net.domain.enums import ContributionKind, RelationKind
from discovery_net.domain.identifiers import AgentId, ContributionId, RelationId


def _require_non_blank(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class Agent:
    """A persistent participant in the research network."""

    id: AgentId

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")


@dataclass(frozen=True, slots=True, kw_only=True)
class Contribution:
    """A mathematical, conversational, or organizational artifact."""

    id: ContributionId
    author_id: AgentId
    thread_root_id: ContributionId
    kind: ContributionKind
    title: str
    body: str
    created_at: datetime
    parent_id: ContributionId | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.author_id, "author_id")
        _require_non_blank(self.thread_root_id, "thread_root_id")
        _require_non_blank(self.title, "title")
        _require_aware(self.created_at, "created_at")

        if self.parent_id is None:
            if self.thread_root_id != self.id:
                raise ValueError("a root contribution must identify itself as thread_root_id")
        else:
            _require_non_blank(self.parent_id, "parent_id")
            if self.parent_id == self.id:
                raise ValueError("a contribution cannot reply to itself")
            if self.thread_root_id == self.id:
                raise ValueError("a reply cannot identify itself as the thread root")


@dataclass(frozen=True, slots=True, kw_only=True)
class ContributionRelation:
    """An attributable edge connecting two contributions."""

    id: RelationId
    author_id: AgentId
    from_contribution_id: ContributionId
    to_contribution_id: ContributionId
    kind: RelationKind
    created_at: datetime

    def __post_init__(self) -> None:
        _require_non_blank(self.id, "id")
        _require_non_blank(self.author_id, "author_id")
        _require_non_blank(self.from_contribution_id, "from_contribution_id")
        _require_non_blank(self.to_contribution_id, "to_contribution_id")
        _require_aware(self.created_at, "created_at")
        if self.from_contribution_id == self.to_contribution_id:
            raise ValueError("a relation must connect two distinct contributions")
