"""Project mathematical contributions and relations into graph structure."""

from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.artifacts.index import IndexedEnvelope
from discovery_net.artifacts.projection import GraphEdge, GraphEdgeRevocation, GraphNode
from discovery_net.domains.math.models import Contribution
from discovery_net.wire import decode_payload


class MathProjection:
    """Select every contribution and relation, preserving their direction."""

    __slots__ = ()

    def project(self, record: IndexedEnvelope) -> GraphNode | GraphEdge | GraphEdgeRevocation:
        artifact = decode_payload(record.envelope.payload_type, record.envelope.payload)
        if isinstance(artifact, EdgeRevocation):
            return GraphEdgeRevocation(target=artifact.target)
        if isinstance(artifact, Contribution):
            return GraphNode(kind=artifact.kind.value)
        return GraphEdge(
            kind=artifact.kind.value,
            source=artifact.from_contribution,
            target=artifact.to_contribution,
        )
