# Defines the immediate receipt returned after submitting an artifact.

from dataclasses import dataclass

from discovery_net.knowledge_graph import ArtifactRef


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmissionReceipt:
    """The immediate receipt returned by a local consensus node."""

    artifact_ref: ArtifactRef
    transaction_hash: str
    check_tx_code: int
