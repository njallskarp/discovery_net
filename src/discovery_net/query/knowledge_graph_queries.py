# Provides transport-independent queries over indexed knowledge-graph data.

from collections.abc import Iterable
from typing import final

from discovery_net.artifacts import ArtifactRef
from discovery_net.domains.math import (
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.indexing import IndexedArtifact, KnowledgeGraphIndex


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

    def contributions_containing_title(
        self,
        text: str,
        *,
        kind: ContributionKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions whose titles contain text, ignoring case."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        contributions = self.contributions() if kind is None else self.contributions_by_kind(kind)
        text = text.casefold()
        return tuple(
            indexed
            for indexed in contributions
            if isinstance(indexed.artifact, Contribution)
            and text in indexed.artifact.title.casefold()
        )

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

    def outgoing_contributions_by_ref(
        self,
        artifact_ref: ArtifactRef,
        *,
        via: RelationKind,
        kind: ContributionKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions reached by following outgoing relations of one kind."""
        relations = self.outgoing_relations_by_ref(artifact_ref, kind=via)
        return _resolve_contributions(
            self._index,
            (
                relation.artifact.to_contribution
                for relation in relations
                if isinstance(relation.artifact, ContributionRelation)
            ),
            kind,
        )

    def incoming_contributions_by_ref(
        self,
        artifact_ref: ArtifactRef,
        *,
        via: RelationKind,
        kind: ContributionKind | None = None,
    ) -> tuple[IndexedArtifact, ...]:
        """Return contributions reached by following incoming relations of one kind."""
        relations = self.incoming_relations_by_ref(artifact_ref, kind=via)
        return _resolve_contributions(
            self._index,
            (
                relation.artifact.from_contribution
                for relation in relations
                if isinstance(relation.artifact, ContributionRelation)
            ),
            kind,
        )


def _resolve_contributions(
    index: KnowledgeGraphIndex,
    references: Iterable[ArtifactRef],
    kind: ContributionKind | None,
) -> tuple[IndexedArtifact, ...]:
    if kind is not None and not isinstance(kind, ContributionKind):
        raise TypeError("kind must be a ContributionKind")

    resolved: list[IndexedArtifact] = []
    seen: set[ArtifactRef] = set()
    for reference in references:
        indexed = index.get(reference)
        if (
            reference not in seen
            and indexed is not None
            and isinstance(indexed.artifact, Contribution)
            and (kind is None or indexed.artifact.kind is kind)
        ):
            seen.add(reference)
            resolved.append(indexed)
    return tuple(resolved)
