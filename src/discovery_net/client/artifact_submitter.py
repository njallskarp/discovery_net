# Defines the agent-facing interface for submitting artifacts.

from typing import Protocol

from discovery_net.client.submission import Submission
from discovery_net.knowledge_graph import Artifact


class ArtifactSubmitter(Protocol):
    """Signs, encodes, and submits artifacts to the network."""

    def submit(self, artifact: Artifact) -> Submission: ...
