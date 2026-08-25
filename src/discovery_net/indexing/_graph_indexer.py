# Projects committed artifacts into rebuildable graph indexes.

from collections.abc import Sequence
from typing import Protocol

from discovery_net.ledger import CommittedArtifact


class _GraphIndexer(Protocol):
    """Updates local query indexes from committed ledger artifacts."""

    def process(self, artifacts: Sequence[CommittedArtifact]) -> None: ...
