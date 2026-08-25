# Public interface for the Discovery Net knowledge graph.
# Agent → CLI/MCP entrypoint → ArtifactSubmitter → local CometBFT
#                                               ↓
# Peers ↔ CometBFT → CometBFTCallbackHandler → LocalArtifactLedger

from discovery_net.knowledge_graph import (
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)

__all__ = [
    "ArtifactRef",
    "Contribution",
    "ContributionKind",
    "ContributionRelation",
    "RelationKind",
]
