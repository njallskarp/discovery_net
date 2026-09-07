"""Immutable indexing of signed envelopes and their ledger provenance."""

from __future__ import annotations

from dataclasses import dataclass, field

from discovery_net.artifacts import ArtifactRef
from discovery_net.node.local_artifact_ledger import ArtifactLedgerEntry
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.wire import SignedEnvelope, artifact_ref


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexedEnvelope:
    """The original signed record and its canonical position."""

    ledger_entry: ArtifactLedgerEntry
    artifact_index: int
    _artifact_ref: ArtifactRef = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.ledger_entry, ArtifactLedgerEntry):
            raise TypeError("ledger_entry must be an ArtifactLedgerEntry")
        if not isinstance(self.artifact_index, int) or isinstance(self.artifact_index, bool):
            raise TypeError("artifact_index must be an integer")
        if not 0 <= self.artifact_index < len(self.ledger_entry.transaction.envelopes):
            raise ValueError("artifact_index must identify a transaction envelope")
        object.__setattr__(self, "_artifact_ref", artifact_ref(self.envelope))

    @property
    def envelope(self) -> SignedEnvelope:
        return self.ledger_entry.transaction.envelopes[self.artifact_index]

    @property
    def artifact_ref(self) -> ArtifactRef:
        return self._artifact_ref


@dataclass(frozen=True, slots=True, init=False)
class ArtifactIndex:
    """A persistent raw index; failed updates never mutate its previous state."""

    height: int
    _records: dict[ArtifactRef, IndexedEnvelope] = field(repr=False)

    def __init__(self, snapshot: ArtifactLedgerSnapshot | None = None) -> None:
        if snapshot is not None and not isinstance(snapshot, ArtifactLedgerSnapshot):
            raise TypeError("snapshot must be an ArtifactLedgerSnapshot")
        records: dict[ArtifactRef, IndexedEnvelope] = {}
        if snapshot is not None:
            _add_entries(records, snapshot.entries)
        object.__setattr__(self, "height", snapshot.height if snapshot is not None else 0)
        object.__setattr__(self, "_records", records)

    def artifacts(self) -> tuple[IndexedEnvelope, ...]:
        return tuple(self._records.values())

    def get(self, reference: ArtifactRef) -> IndexedEnvelope | None:
        return self._records.get(reference)

    def append(self, *, entries: tuple[ArtifactLedgerEntry, ...], height: int) -> ArtifactIndex:
        if not isinstance(entries, tuple):
            raise TypeError("entries must be a tuple")
        if any(not isinstance(entry, ArtifactLedgerEntry) for entry in entries):
            raise TypeError("entries must contain ArtifactLedgerEntry values")
        if not isinstance(height, int) or isinstance(height, bool):
            raise TypeError("height must be an integer")
        if height < self.height:
            raise ValueError("height must not precede the indexed height")
        if any(entry.height <= self.height for entry in entries):
            raise ValueError("entries must follow the indexed height")
        if any(entry.height > height for entry in entries):
            raise ValueError("entry height must not exceed the indexed height")
        if height == self.height and entries:
            raise ValueError("entries cannot change an already indexed height")
        records = dict(self._records)
        _add_entries(records, entries)
        updated = object.__new__(ArtifactIndex)
        object.__setattr__(updated, "height", height)
        object.__setattr__(updated, "_records", records)
        return updated


def _add_entries(
    records: dict[ArtifactRef, IndexedEnvelope],
    entries: tuple[ArtifactLedgerEntry, ...],
) -> None:
    for entry in entries:
        for artifact_index in range(len(entry.transaction.envelopes)):
            indexed = IndexedEnvelope(ledger_entry=entry, artifact_index=artifact_index)
            if indexed.artifact_ref in records:
                raise ValueError("entries must not contain duplicate artifacts")
            records[indexed.artifact_ref] = indexed
