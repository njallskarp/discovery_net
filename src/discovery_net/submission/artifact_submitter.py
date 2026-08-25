# Defines the agent-facing interface for submitting artifacts.

from typing import Protocol

from discovery_net.knowledge_graph import Artifact
from discovery_net.submission.submission_receipt import SubmissionReceipt


class ArtifactSubmitter(Protocol):
    """Signs, encodes, and submits artifacts to the network."""

    def submit(self, artifact: Artifact) -> SubmissionReceipt: ...
