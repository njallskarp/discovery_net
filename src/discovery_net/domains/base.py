"""The payload and reference contract implemented by a research domain."""

from typing import Protocol

from discovery_net.artifacts import ArtifactRef


class ArtifactDomain[ArtifactT](Protocol):
    """Deterministic structure validation and node reference extraction.

    Implementing this contract does not register a domain with the live protocol.
    The current wire layer explicitly uses only the legacy math implementation.
    """

    def encode(self, artifact: ArtifactT) -> tuple[str, bytes]: ...

    def decode(self, payload_type: str, data: bytes) -> ArtifactT: ...

    def is_node(self, artifact: ArtifactT) -> bool: ...

    def references(self, artifact: ArtifactT) -> tuple[ArtifactRef, ...]: ...
