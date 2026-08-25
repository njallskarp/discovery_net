# Projects committed artifacts into rebuildable graph indexes.

from collections.abc import Sequence
from typing import Protocol

from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry


class _GraphIndexer(Protocol):
    """Updates local query indexes from committed artifact-ledger entries."""

    def process(self, entries: Sequence[ArtifactLedgerEntry]) -> None: ...
