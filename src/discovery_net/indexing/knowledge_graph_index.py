"""Compatibility math queries over separate raw artifact and projected graph indexes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.index import ArtifactIndex, IndexedEnvelope
from discovery_net.artifacts.projection import GraphProjection, ProjectedGraph
from discovery_net.domains.math import Artifact, ContributionKind, RelationKind
from discovery_net.domains.math.projection import LegacyMathProjection
from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.wire import SignedEnvelope, decode_payload
from discovery_net.wire import artifact_ref as envelope_artifact_ref


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexedArtifact:
    """A decoded artifact and its position within a committed transaction."""

    ledger_entry: ArtifactLedgerEntry
    artifact_index: int
    artifact: Artifact = field(init=False)
    _artifact_ref: ArtifactRef = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.ledger_entry, ArtifactLedgerEntry):
            raise TypeError("ledger_entry must be an ArtifactLedgerEntry")
        if not isinstance(self.artifact_index, int) or isinstance(self.artifact_index, bool):
            raise TypeError("artifact_index must be an integer")
        if not 0 <= self.artifact_index < len(self.ledger_entry.transaction.envelopes):
            raise ValueError("artifact_index must identify a transaction envelope")
        object.__setattr__(
            self,
            "artifact",
            decode_payload(
                self.envelope.payload_type,
                self.envelope.payload,
            ),
        )
        object.__setattr__(self, "_artifact_ref", envelope_artifact_ref(self.envelope))

    @property
    def envelope(self) -> SignedEnvelope:
        """Return the signed envelope containing this artifact."""
        return self.ledger_entry.transaction.envelopes[self.artifact_index]

    @property
    def artifact_ref(self) -> ArtifactRef:
        """Return the artifact reference derived from the signed envelope."""
        return self._artifact_ref

    @classmethod
    def from_record(cls, record: IndexedEnvelope) -> IndexedArtifact:
        """Decode once for math queries, sharing the original envelope and cached ID."""
        indexed = object.__new__(cls)
        object.__setattr__(indexed, "ledger_entry", record.ledger_entry)
        object.__setattr__(indexed, "artifact_index", record.artifact_index)
        object.__setattr__(indexed, "_artifact_ref", record.artifact_ref)
        object.__setattr__(
            indexed,
            "artifact",
            decode_payload(record.envelope.payload_type, record.envelope.payload),
        )
        return indexed


@dataclass(frozen=True, slots=True)
class _GraphState:
    graph: ProjectedGraph
    decoded: dict[ArtifactRef, IndexedArtifact]


@final
class KnowledgeGraphIndex:
    """Preserves legacy query APIs while allowing an explicit development projection."""

    __slots__ = ("_projection", "_state")

    def __init__(self, *, projection: GraphProjection | None = None) -> None:
        self._projection = projection if projection is not None else LegacyMathProjection()
        self._state = _GraphState(
            graph=ProjectedGraph(raw=ArtifactIndex(), projection=self._projection),
            decoded={},
        )

    @property
    def indexed_height(self) -> int:
        return self._state.graph.raw.height

    @property
    def raw_index(self) -> ArtifactIndex:
        """Immutable raw records, including artifacts omitted by the selected projection."""
        return self._state.graph.raw

    def refresh(self, snapshot: ArtifactLedgerSnapshot) -> None:
        if not isinstance(snapshot, ArtifactLedgerSnapshot):
            raise TypeError("snapshot must be an ArtifactLedgerSnapshot")
        graph = ProjectedGraph(raw=ArtifactIndex(snapshot), projection=self._projection)
        decoded = {
            record.artifact_ref: IndexedArtifact.from_record(record)
            for record in graph.raw.artifacts()
        }
        self._state = _GraphState(graph=graph, decoded=decoded)

    def append(self, *, entries: tuple[ArtifactLedgerEntry, ...], height: int) -> None:
        state = self._state
        graph = state.graph.append(entries=entries, height=height)
        decoded = dict(state.decoded)
        for record in graph.raw.artifacts():
            if record.artifact_ref not in decoded:
                decoded[record.artifact_ref] = IndexedArtifact.from_record(record)
        self._state = _GraphState(graph=graph, decoded=decoded)

    def artifacts(self) -> tuple[IndexedArtifact, ...]:
        """Return all raw artifacts in ledger order, independent of view selection."""
        return tuple(self._state.decoded.values())

    def get(self, artifact_ref: ArtifactRef) -> IndexedArtifact | None:
        """Retrieve raw provenance even for an artifact excluded from the view."""
        return self._state.decoded.get(artifact_ref)

    def contributions(self, kind: ContributionKind | None = None) -> tuple[IndexedArtifact, ...]:
        if kind is not None and not isinstance(kind, ContributionKind):
            raise TypeError("kind must be a ContributionKind")
        state = self._state
        return _decoded(state, state.graph.nodes(kind.value if kind is not None else None))

    def relations(self, kind: RelationKind | None = None) -> tuple[IndexedArtifact, ...]:
        _require_relation_kind(kind)
        state = self._state
        return _decoded(state, state.graph.edges(kind.value if kind is not None else None))

    def incoming_relations(
        self,
        artifact_ref: ArtifactRef,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        _require_relation_kind(kind)
        state = self._state
        return _decoded(
            state, state.graph.incoming(artifact_ref, kind.value if kind is not None else None)
        )

    def outgoing_relations(
        self,
        artifact_ref: ArtifactRef,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        _require_relation_kind(kind)
        state = self._state
        return _decoded(
            state, state.graph.outgoing(artifact_ref, kind.value if kind is not None else None)
        )


def _decoded(
    state: _GraphState, records: tuple[IndexedEnvelope, ...]
) -> tuple[IndexedArtifact, ...]:
    return tuple(state.decoded[record.artifact_ref] for record in records)


def _require_relation_kind(kind: RelationKind | None) -> None:
    if kind is not None and not isinstance(kind, RelationKind):
        raise TypeError("kind must be a RelationKind")
