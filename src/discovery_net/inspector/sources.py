# Defines the read-only sources consumed by the inspector service.

from typing import Protocol

from discovery_net.inspector.models import NodeObservation
from discovery_net.node import ArtifactLedgerSnapshot


class NodeObservationSource(Protocol):
    """Observes the current state of one local consensus node."""

    def observe(self) -> NodeObservation: ...


class ArtifactLedgerSnapshotReader(Protocol):
    """Reads the latest committed artifact-ledger snapshot without mutation."""

    def load(self) -> ArtifactLedgerSnapshot | None: ...
