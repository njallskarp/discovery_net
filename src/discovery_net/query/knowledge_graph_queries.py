# Provides transport-independent queries over indexed knowledge-graph data.

from typing import final

from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex
from discovery_net.knowledge_graph import (
    ArtifactRef,
    ContributionKind,
    ContributionRelation,
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

    def artifact(self, artifact_ref: ArtifactRef) -> IndexedArtifact | None:
        """Return an artifact by reference, if it is indexed."""
        return self._index.get(artifact_ref)

    def contributions(
        self,
        *,
        kind: ContributionKind | None = None,
        parent: ArtifactRef | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions matching the supplied filters."""
        if parent is None:
            return self._index.contributions(kind)

        children = self._index.children_of(parent)
        if kind is None:
            return children
        if not isinstance(kind, ContributionKind):
            raise TypeError("kind must be a ContributionKind")
        return tuple(child for child in children if child.artifact.kind is kind)

    def relations(
        self,
        *,
        kind: RelationKind | None = None,
        from_contribution: ArtifactRef | None = None,
        to_contribution: ArtifactRef | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return relations matching the supplied filters."""
        if from_contribution is not None:
            return _relations_from(
                self._index,
                from_contribution=from_contribution,
                to_contribution=to_contribution,
                kind=kind,
            )
        if to_contribution is not None:
            return self._index.incoming_relations(to_contribution, kind)
        return self._index.relations(kind)


def _relations_from(
    index: KnowledgeGraphIndex,
    *,
    from_contribution: ArtifactRef,
    to_contribution: ArtifactRef | None,
    kind: RelationKind | None,
) -> tuple[IndexedArtifact, ...]:
    outgoing = index.outgoing_relations(from_contribution, kind)
    if to_contribution is None:
        return outgoing
    return tuple(
        relation
        for relation in outgoing
        if isinstance(relation.artifact, ContributionRelation)
        and relation.artifact.to_contribution == to_contribution
    )
