# Exposes committed mathematical knowledge through a read-only GraphQL schema.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast, final

import strawberry
from strawberry.types import Info

from discovery_net.indexing import IndexedArtifact
from discovery_net.knowledge_graph import (
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.query import KnowledgeGraphQueries
from discovery_net.wire import parse_artifact_ref

type JSONObject = dict[str, object]

strawberry.enum(ContributionKind, name="ContributionKind")
strawberry.enum(RelationKind, name="RelationKind")


@dataclass(frozen=True, slots=True)
class GraphQLResult:
    """The serializable result of one GraphQL operation."""

    data: JSONObject | None
    errors: tuple[JSONObject, ...]

    @property
    def succeeded(self) -> bool:
        """Return whether execution completed without GraphQL errors."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class _GraphQLContext:
    queries: KnowledgeGraphQueries


@strawberry.interface(name="Artifact")
class _ArtifactNode:
    _indexed: strawberry.Private[IndexedArtifact]

    @strawberry.field
    def artifact_ref(self) -> strawberry.ID:
        return strawberry.ID(self._indexed.artifact_ref)

    @strawberry.field
    def chain_id(self) -> str:
        return self._indexed.ledger_entry.envelope.chain_id

    @strawberry.field
    def signer_public_key(self) -> str:
        return self._indexed.ledger_entry.envelope.signer_public_key.hex()

    @strawberry.field
    def signature(self) -> str:
        return self._indexed.ledger_entry.envelope.signature.hex()

    @strawberry.field
    def height(self) -> str:
        return str(self._indexed.ledger_entry.height)

    @strawberry.field
    def transaction_index(self) -> str:
        return str(self._indexed.ledger_entry.transaction_index)

    @strawberry.field
    def created_at(self) -> datetime:
        return self._indexed.artifact.created_at


@strawberry.type(name="Contribution")
class _ContributionNode(_ArtifactNode):
    @property
    def _contribution(self) -> Contribution:
        artifact = self._indexed.artifact
        if not isinstance(artifact, Contribution):
            raise TypeError("indexed artifact must be a Contribution")
        return artifact

    @strawberry.field
    def kind(self) -> ContributionKind:
        return self._contribution.kind

    @strawberry.field
    def title(self) -> str:
        return self._contribution.title

    @strawberry.field
    def body(self) -> str:
        return self._contribution.body

    @strawberry.field
    def parent_ref(self) -> strawberry.ID | None:
        parent = self._contribution.parent
        return None if parent is None else strawberry.ID(parent)

    @strawberry.field
    def parent(self, info: Info[_GraphQLContext, None]) -> _ContributionNode | None:
        parent = self._contribution.parent
        if parent is None:
            return None
        return _contribution_node(info.context.queries.artifact_by_ref(parent))

    @strawberry.field
    def children(
        self,
        info: Info[_GraphQLContext, None],
        kind: ContributionKind | None = None,
    ) -> list[_ContributionNode]:
        children = info.context.queries.children_by_parent_ref(self._indexed.artifact_ref)
        return _contribution_nodes(children, kind)

    @strawberry.field
    def outgoing_relations(
        self,
        info: Info[_GraphQLContext, None],
        kind: RelationKind | None = None,
    ) -> list[_RelationNode]:
        relations = info.context.queries.outgoing_relations_by_ref(
            self._indexed.artifact_ref,
            kind=kind,
        )
        return _relation_nodes(relations)

    @strawberry.field
    def incoming_relations(
        self,
        info: Info[_GraphQLContext, None],
        kind: RelationKind | None = None,
    ) -> list[_RelationNode]:
        relations = info.context.queries.incoming_relations_by_ref(
            self._indexed.artifact_ref,
            kind=kind,
        )
        return _relation_nodes(relations)

    @strawberry.field
    def outgoing_contributions(
        self,
        info: Info[_GraphQLContext, None],
        via: RelationKind,
        kind: ContributionKind | None = None,
    ) -> list[_ContributionNode]:
        contributions = info.context.queries.outgoing_contributions_by_ref(
            self._indexed.artifact_ref,
            via=via,
            kind=kind,
        )
        return _contribution_nodes(contributions)

    @strawberry.field
    def incoming_contributions(
        self,
        info: Info[_GraphQLContext, None],
        via: RelationKind,
        kind: ContributionKind | None = None,
    ) -> list[_ContributionNode]:
        contributions = info.context.queries.incoming_contributions_by_ref(
            self._indexed.artifact_ref,
            via=via,
            kind=kind,
        )
        return _contribution_nodes(contributions)


@strawberry.type(name="Relation")
class _RelationNode(_ArtifactNode):
    @property
    def _relation(self) -> ContributionRelation:
        artifact = self._indexed.artifact
        if not isinstance(artifact, ContributionRelation):
            raise TypeError("indexed artifact must be a ContributionRelation")
        return artifact

    @strawberry.field
    def kind(self) -> RelationKind:
        return self._relation.kind

    @strawberry.field
    def from_contribution_ref(self) -> strawberry.ID:
        return strawberry.ID(self._relation.from_contribution)

    @strawberry.field
    def to_contribution_ref(self) -> strawberry.ID:
        return strawberry.ID(self._relation.to_contribution)

    @strawberry.field
    def source(self, info: Info[_GraphQLContext, None]) -> _ContributionNode | None:
        return _contribution_node(
            info.context.queries.artifact_by_ref(self._relation.from_contribution)
        )

    @strawberry.field
    def destination(self, info: Info[_GraphQLContext, None]) -> _ContributionNode | None:
        return _contribution_node(
            info.context.queries.artifact_by_ref(self._relation.to_contribution)
        )


@strawberry.type(name="Query")
class _Query:
    @strawberry.field
    def indexed_height(self, info: Info[_GraphQLContext, None]) -> str:
        return str(info.context.queries.indexed_height)

    @strawberry.field
    def artifact(
        self,
        info: Info[_GraphQLContext, None],
        ref: strawberry.ID,
    ) -> _ArtifactNode | None:
        indexed = info.context.queries.artifact_by_ref(parse_artifact_ref(str(ref)))
        return _artifact_node(indexed)

    @strawberry.field
    def contributions(
        self,
        info: Info[_GraphQLContext, None],
        kind: ContributionKind | None = None,
        title_contains: str | None = None,
    ) -> list[_ContributionNode]:
        if title_contains is not None:
            indexed = info.context.queries.contributions_containing_title(
                title_contains,
                kind=kind,
            )
        elif kind is not None:
            indexed = info.context.queries.contributions_by_kind(kind)
        else:
            indexed = info.context.queries.contributions()
        return _contribution_nodes(indexed)

    @strawberry.field
    def relations(
        self,
        info: Info[_GraphQLContext, None],
        kind: RelationKind | None = None,
    ) -> list[_RelationNode]:
        indexed = (
            info.context.queries.relations()
            if kind is None
            else info.context.queries.relations_by_kind(kind)
        )
        return _relation_nodes(indexed)


_SCHEMA = strawberry.Schema(
    query=_Query,
    types=(_ContributionNode, _RelationNode),
)


@final
class GraphQLQueryExecutor:
    """Executes read-only GraphQL operations against one knowledge-graph view."""

    __slots__ = ("_context",)

    def __init__(self, *, queries: KnowledgeGraphQueries) -> None:
        if not isinstance(queries, KnowledgeGraphQueries):
            raise TypeError("queries must be KnowledgeGraphQueries")
        self._context = _GraphQLContext(queries=queries)

    def execute(
        self,
        document: str,
        *,
        variables: JSONObject | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResult:
        """Execute one GraphQL operation and return its data and formatted errors."""
        if not isinstance(document, str):
            raise TypeError("document must be a string")
        if variables is not None and not isinstance(variables, dict):
            raise TypeError("variables must be an object")

        result = _SCHEMA.execute_sync(
            document,
            variable_values=variables,
            operation_name=operation_name,
            context_value=self._context,
        )
        data = None if result.data is None else cast(JSONObject, result.data)
        errors = tuple(cast(JSONObject, error.formatted) for error in result.errors or ())
        return GraphQLResult(data=data, errors=errors)


def _artifact_node(indexed: IndexedArtifact | None) -> _ArtifactNode | None:
    if indexed is None:
        return None
    if isinstance(indexed.artifact, Contribution):
        return _ContributionNode(_indexed=indexed)
    return _RelationNode(_indexed=indexed)


def _contribution_node(indexed: IndexedArtifact | None) -> _ContributionNode | None:
    if indexed is None or not isinstance(indexed.artifact, Contribution):
        return None
    return _ContributionNode(_indexed=indexed)


def _contribution_nodes(
    indexed: tuple[IndexedArtifact, ...],
    kind: ContributionKind | None = None,
) -> list[_ContributionNode]:
    return [
        _ContributionNode(_indexed=value)
        for value in indexed
        if isinstance(value.artifact, Contribution)
        and (kind is None or value.artifact.kind is kind)
    ]


def _relation_nodes(indexed: tuple[IndexedArtifact, ...]) -> list[_RelationNode]:
    return [
        _RelationNode(_indexed=value)
        for value in indexed
        if isinstance(value.artifact, ContributionRelation)
    ]
