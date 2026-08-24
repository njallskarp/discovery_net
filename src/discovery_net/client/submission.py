# Defines the immediate result of submitting an artifact.

from dataclasses import dataclass

from discovery_net.knowledge_graph import ArtifactRef


@dataclass(frozen=True, slots=True, kw_only=True)
class Submission:
    """The immediate result of submitting an artifact to a local consensus node."""

    artifact_ref: ArtifactRef
    transaction_hash: str
    check_tx_code: int
