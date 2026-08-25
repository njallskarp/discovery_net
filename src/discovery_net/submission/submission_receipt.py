# Defines the immediate receipt returned after submitting an artifact.

from dataclasses import dataclass

from discovery_net.knowledge_graph import ArtifactRef


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmissionReceipt:
    """Reports whether a local node accepted an artifact for broadcast."""

    artifact_ref: ArtifactRef
    accepted: bool
