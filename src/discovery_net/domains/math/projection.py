"""Math classification extracted from discovery_net.indexing.knowledge_graph_index.

MathProjection is the permanent math implementation of GraphProjection. It owns
the contribution/relation classification formerly in _build_state and _append_state."""

from discovery_net.artifacts.index import IndexedEnvelope
from discovery_net.artifacts.projection import GraphEdge, GraphNode
from discovery_net.domains.math.codec import MATH_DOMAIN
from discovery_net.domains.math.models import Contribution


class MathProjection:
    """Select every contribution and relation, preserving their direction."""

    __slots__ = ()

    def project(self, record: IndexedEnvelope) -> GraphNode | GraphEdge:
        artifact = MATH_DOMAIN.decode(record.envelope.payload_type.value, record.envelope.payload)
        if isinstance(artifact, Contribution):
            return GraphNode(kind=artifact.kind.value)
        return GraphEdge(
            kind=artifact.kind.value,
            source=artifact.from_contribution,
            target=artifact.to_contribution,
        )
