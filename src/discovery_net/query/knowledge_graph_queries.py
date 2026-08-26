# Provides transport-independent queries over indexed knowledge-graph data.

from typing import final

from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.knowledge_graph import (
    ArtifactRef,
    ContributionKind,
    RelationKind,
)


@final
class KnowledgeGraphQueries:
    """Composes user-facing queries over a knowledge-graph index."""

    __slots__ = ("_index",)

    def __init__(self, *, index: KnowledgeGraphIndex) -> None:
        if not isinstance(index, KnowledgeGraphIndex):
            raise TypeError("index must be a KnowledgeGraphIndex")
        self._index = index

    @property
    def indexed_height(self) -> int:
        """Return the committed height available to queries."""
        return self._index.indexed_height

    def artifact_by_ref(self, artifact_ref: ArtifactRef) -> IndexedArtifact | None:
        """Return an artifact by reference, if it is indexed."""
        return self._index.get(artifact_ref)

    def contributions(self) -> tuple[IndexedArtifact, ...]:
        """Return all indexed contributions."""
        return self._index.contributions()

    def contributions_by_kind(
        self,
        kind: ContributionKind,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions of one mathematical or organizational kind."""
        return self._index.contributions(kind)

    def children_by_parent_ref(
        self,
        parent_ref: ArtifactRef,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions whose parent has the supplied reference."""
        return self._index.children_of(parent_ref)

    def relations(self) -> tuple[IndexedArtifact, ...]:
        """Return all indexed contribution relations."""
        return self._index.relations()

    def relations_by_kind(
        self,
        kind: RelationKind,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contribution relations of one kind."""
        return self._index.relations(kind)

    def outgoing_relations_by_ref(
        self,
        artifact_ref: ArtifactRef,
        *,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return relations originating from the referenced artifact."""
        return self._index.outgoing_relations(artifact_ref, kind)

    def incoming_relations_by_ref(
        self,
        artifact_ref: ArtifactRef,
        *,
        kind: RelationKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return relations terminating at the referenced artifact."""
        return self._index.incoming_relations(artifact_ref, kind)
