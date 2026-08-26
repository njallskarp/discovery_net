# Projects committed artifacts into an in-memory knowledge graph.

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import final

from discovery_net.knowledge_graph import (
    Artifact,
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.wire import artifact_ref as envelope_artifact_ref
from discovery_net.wire import decode_payload


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexedArtifact:
    """A decoded artifact paired with its canonical ledger entry."""

    ledger_entry: ArtifactLedgerEntry
    artifact: Artifact = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.ledger_entry, ArtifactLedgerEntry):
            raise TypeError("ledger_entry must be an ArtifactLedgerEntry")
        object.__setattr__(
            self,
            "artifact",
            decode_payload(
                self.ledger_entry.envelope.payload_type,
                self.ledger_entry.envelope.payload,
            ),
        )

    @property
    def artifact_ref(self) -> ArtifactRef:
        """Derive the artifact reference from its signed envelope."""
        return envelope_artifact_ref(self.ledger_entry.envelope)


@dataclass(frozen=True, slots=True)
class _ContributionKindNode:
    kind: ContributionKind


@dataclass(frozen=True, slots=True)
class _RelationKindNode:
    kind: RelationKind


type _AdjacencyKey = ArtifactRef | _ContributionKindNode | _RelationKindNode


@dataclass(frozen=True, slots=True)
class _GraphState:
    height: int
    nodes: dict[ArtifactRef, IndexedArtifact]
    adjacency: dict[_AdjacencyKey, tuple[ArtifactRef, ...]]


@final
class KnowledgeGraphIndex:
    """Provides in-memory graph queries over a committed ledger snapshot."""

    __slots__ = ("_state",)

    def __init__(self) -> None:
        self._state = _GraphState(height=0, nodes={}, adjacency={})

    @property
    def indexed_height(self) -> int:
        """Return the committed height represented by this index."""
        return self._state.height

    def refresh(self, snapshot: ArtifactLedgerSnapshot) -> None:
        """Atomically rebuild the index from a committed ledger snapshot."""
        if not isinstance(snapshot, ArtifactLedgerSnapshot):
            raise TypeError("snapshot must be an ArtifactLedgerSnapshot")
        self._state = _build_state(snapshot)

    def get(self, artifact_ref: ArtifactRef) -> IndexedArtifact | None:
        """Return an indexed artifact by reference, if present."""
        return self._state.nodes.get(artifact_ref)

    def contributions(
        self,
        kind: ContributionKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions in canonical ledger order."""
        state = self._state
        if kind is None:
            return tuple(
                indexed
                for indexed in state.nodes.values()
                if isinstance(indexed.artifact, Contribution)
            )
        if not isinstance(kind, ContributionKind):
            raise TypeError("kind must be a ContributionKind")
        return _indexed_neighbors(state, _ContributionKindNode(kind))

    def relations(
        self,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contribution relations in canonical ledger order."""
        state = self._state
        if kind is None:
            return tuple(
                indexed
                for indexed in state.nodes.values()
                if isinstance(indexed.artifact, ContributionRelation)
            )
        if not isinstance(kind, RelationKind):
            raise TypeError("kind must be a RelationKind")
        return _indexed_neighbors(state, _RelationKindNode(kind))

    def children_of(self, parent: ArtifactRef) -> tuple[IndexedArtifact, ...]:
        """Return contributions that directly reply to a parent artifact."""
        return tuple(
            indexed
            for indexed in _indexed_neighbors(self._state, parent)
            if isinstance(indexed.artifact, Contribution) and indexed.artifact.parent == parent
        )

    def incoming_relations(
        self,
        artifact_ref: ArtifactRef,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return relations whose destination is the referenced artifact."""
        _require_relation_kind(kind)
        return tuple(
            indexed
            for indexed in _indexed_neighbors(self._state, artifact_ref)
            if isinstance(indexed.artifact, ContributionRelation)
            and indexed.artifact.to_contribution == artifact_ref
            and (kind is None or indexed.artifact.kind is kind)
        )

    def outgoing_relations(
        self,
        artifact_ref: ArtifactRef,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return relations whose source is the referenced artifact."""
        _require_relation_kind(kind)
        return tuple(
            indexed
            for indexed in _indexed_neighbors(self._state, artifact_ref)
            if isinstance(indexed.artifact, ContributionRelation)
            and indexed.artifact.from_contribution == artifact_ref
            and (kind is None or indexed.artifact.kind is kind)
        )


def _build_state(snapshot: ArtifactLedgerSnapshot) -> _GraphState:
    nodes: dict[ArtifactRef, IndexedArtifact] = {}
    adjacency: defaultdict[_AdjacencyKey, list[ArtifactRef]] = defaultdict(list)

    for ledger_entry in snapshot.entries:
        indexed = IndexedArtifact(ledger_entry=ledger_entry)
        reference = indexed.artifact_ref
        if reference in nodes:
            raise ValueError("snapshot must not contain duplicate artifacts")
        nodes[reference] = indexed
        _connect(indexed, reference, adjacency)

    return _GraphState(
        height=snapshot.height,
        nodes=nodes,
        adjacency={key: tuple(references) for key, references in adjacency.items()},
    )


def _connect(
    indexed: IndexedArtifact,
    reference: ArtifactRef,
    adjacency: defaultdict[_AdjacencyKey, list[ArtifactRef]],
) -> None:
    artifact = indexed.artifact
    if isinstance(artifact, Contribution):
        adjacency[_ContributionKindNode(artifact.kind)].append(reference)
        if artifact.parent is not None:
            adjacency[artifact.parent].append(reference)
        return

    adjacency[_RelationKindNode(artifact.kind)].append(reference)
    adjacency[artifact.from_contribution].append(reference)
    adjacency[artifact.to_contribution].append(reference)


def _indexed_neighbors(
    state: _GraphState,
    key: _AdjacencyKey,
) -> tuple[IndexedArtifact, ...]:
    return tuple(state.nodes[reference] for reference in state.adjacency.get(key, ()))


def _require_relation_kind(kind: RelationKind | None) -> None:
    if kind is not None and not isinstance(kind, RelationKind):
        raise TypeError("kind must be a RelationKind")
