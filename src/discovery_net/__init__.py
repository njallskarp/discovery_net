# Public interface for the Discovery Net knowledge graph.
# Agent → CLI/MCP entrypoint → ArtifactSubmitter → local CometBFT
#                                               ↓
# Peers ↔ CometBFT → CometBFTABCIAdapter → CometBFTCallbackHandler → LocalArtifactLedger

from discovery_net.artifacts import ArtifactRef
from discovery_net.artifacts.edge_revocation import EdgeRevocation
from discovery_net.domains.math import (
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
    "EdgeRevocation",
    "RelationKind",
]
