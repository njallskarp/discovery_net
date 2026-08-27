# Defines the immediate receipt returned after submitting a transaction.

from dataclasses import dataclass

from discovery_net.knowledge_graph import ArtifactRef


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmissionReceipt:
    """Reports whether a local node accepted an atomic transaction for broadcast."""

    artifact_refs: tuple[ArtifactRef, ...]
    accepted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_refs, tuple):
            raise TypeError("artifact_refs must be a tuple")
        if not self.artifact_refs:
            raise ValueError("artifact_refs must not be empty")
        if any(not isinstance(reference, str) or not reference for reference in self.artifact_refs):
            raise ValueError("artifact_refs must contain nonblank references")
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be a boolean")
