"""The existing math topology expressed through the domain-independent view contract."""

from discovery_net.artifacts.index import IndexedEnvelope
from discovery_net.artifacts.projection import GraphEdge, GraphNode
from discovery_net.domains.math.codec import MATH_DOMAIN
from discovery_net.domains.math.models import Contribution


class LegacyMathProjection:
    """Select every legacy contribution and relation, preserving their direction."""

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
