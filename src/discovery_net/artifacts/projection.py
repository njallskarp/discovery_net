"""Graph selection and traversal independent of domain vocabulary."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.index import ArtifactIndex, IndexedEnvelope
from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphNode:
    kind: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GraphEdge:
    kind: str
    source: ArtifactRef
    target: ArtifactRef


class GraphProjection(Protocol):
    """A fixed, deterministic policy for a view; changing policy requires a rebuild."""

    def project(self, record: IndexedEnvelope) -> GraphNode | GraphEdge | None: ...


class ProjectedGraph:
    """A read-only view over an immutable raw index; omitted records remain retrievable."""

    __slots__ = (
        "_edge_kinds",
        "_edges",
        "_incoming",
        "_node_kinds",
        "_nodes",
        "_outgoing",
        "_projection",
        "_raw",
        "_selected",
    )

    def __init__(self, *, raw: ArtifactIndex, projection: GraphProjection) -> None:
        self._initialize(
            raw=raw,
            projection=projection,
            selected={
                record.artifact_ref: projection.project(record) for record in raw.artifacts()
            },
        )

    @property
    def raw(self) -> ArtifactIndex:
        return self._raw

    def _initialize(
        self,
        *,
        raw: ArtifactIndex,
        projection: GraphProjection,
        selected: dict[ArtifactRef, GraphNode | GraphEdge | None],
    ) -> None:
        self._raw = raw
        self._projection = projection
        self._selected = selected
        self._nodes = {
            ref: shape for ref, shape in selected.items() if isinstance(shape, GraphNode)
        }
        # An edge cannot silently bring an excluded node back into a graph traversal.
        self._edges = {
            ref: shape
            for ref, shape in selected.items()
            if isinstance(shape, GraphEdge)
            and shape.source in self._nodes
            and shape.target in self._nodes
        }
        incoming: defaultdict[ArtifactRef, list[ArtifactRef]] = defaultdict(list)
        outgoing: defaultdict[ArtifactRef, list[ArtifactRef]] = defaultdict(list)
        for ref, edge in self._edges.items():
            outgoing[edge.source].append(ref)
            incoming[edge.target].append(ref)
        self._incoming = {ref: tuple(edges) for ref, edges in incoming.items()}
        self._outgoing = {ref: tuple(edges) for ref, edges in outgoing.items()}
        node_kinds: defaultdict[str, list[ArtifactRef]] = defaultdict(list)
        edge_kinds: defaultdict[str, list[ArtifactRef]] = defaultdict(list)
        for ref, node in self._nodes.items():
            node_kinds[node.kind].append(ref)
        for ref, edge in self._edges.items():
            edge_kinds[edge.kind].append(ref)
        self._node_kinds = {kind: tuple(refs) for kind, refs in node_kinds.items()}
        self._edge_kinds = {kind: tuple(refs) for kind, refs in edge_kinds.items()}

    def append(self, *, entries: tuple[ArtifactLedgerEntry, ...], height: int) -> ProjectedGraph:
        raw = self._raw.append(entries=entries, height=height)
        selected = dict(self._selected)
        for record in raw.artifacts():
            if record.artifact_ref not in selected:
                selected[record.artifact_ref] = self._projection.project(record)
        updated = object.__new__(ProjectedGraph)
        updated._initialize(raw=raw, projection=self._projection, selected=selected)
        return updated

    def nodes(self, kind: str | None = None) -> tuple[IndexedEnvelope, ...]:
        return self._records(tuple(self._nodes) if kind is None else self._node_kinds.get(kind, ()))

    def edges(self, kind: str | None = None) -> tuple[IndexedEnvelope, ...]:
        return self._records(tuple(self._edges) if kind is None else self._edge_kinds.get(kind, ()))

    def incoming(
        self, reference: ArtifactRef, kind: str | None = None
    ) -> tuple[IndexedEnvelope, ...]:
        return self._records(
            tuple(
                ref
                for ref in self._incoming.get(reference, ())
                if kind is None or self._edges[ref].kind == kind
            )
        )

    def outgoing(
        self, reference: ArtifactRef, kind: str | None = None
    ) -> tuple[IndexedEnvelope, ...]:
        return self._records(
            tuple(
                ref
                for ref in self._outgoing.get(reference, ())
                if kind is None or self._edges[ref].kind == kind
            )
        )

    def _records(self, references: tuple[ArtifactRef, ...]) -> tuple[IndexedEnvelope, ...]:
        records = tuple(self._raw.get(ref) for ref in references)
        assert all(record is not None for record in records)
        return tuple(record for record in records if record is not None)
