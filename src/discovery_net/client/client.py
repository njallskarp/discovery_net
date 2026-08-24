# Provides a programmatic interface for network clients.

from dataclasses import dataclass
from typing import Protocol

from discovery_net.knowledge_graph import Artifact, ArtifactRef


@dataclass(frozen=True, slots=True, kw_only=True)
class BroadcastResult:
    """The response returned by a local CometBFT broadcast call."""

    transaction_hash: str
    check_tx_code: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Submission:
    """The immediate result of submitting an artifact to a local consensus node."""

    artifact_ref: ArtifactRef
    transaction_hash: str
    check_tx_code: int


class TransactionBroadcaster(Protocol):
    """Broadcasts encoded transactions to a local CometBFT node."""

    def broadcast(self, transaction: bytes) -> BroadcastResult: ...


class DiscoveryClient(Protocol):
    """Signs, encodes, and submits artifacts through a transaction broadcaster."""

    def submit(self, artifact: Artifact) -> Submission: ...
