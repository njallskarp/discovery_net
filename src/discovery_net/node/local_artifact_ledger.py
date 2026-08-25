# Defines deterministic transitions over the node-local artifact ledger.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Final, Protocol, final

from discovery_net.knowledge_graph import ArtifactRef
from discovery_net.wire import SignedEnvelope, artifact_ref, encode_envelope

_LEDGER_HASH_DOMAIN: Final = b"discovery-net:artifact-ledger:\x00"
_EMPTY_LEDGER_HASH: Final = sha256(_LEDGER_HASH_DOMAIN).digest()
_MAX_INT64: Final = (1 << 63) - 1
_MAX_UINT64: Final = (1 << 64) - 1


class AppendOutcome(StrEnum):
    """The consensus-visible outcome of appending a verified envelope."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactLedgerEntry:
    """A signed envelope paired with its consensus-assigned block position."""

    envelope: SignedEnvelope
    height: int
    transaction_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, SignedEnvelope):
            raise TypeError("envelope must be a SignedEnvelope")
        _require_integer(self.height, "height")
        if not 1 <= self.height <= _MAX_INT64:
            raise ValueError("height must be between 1 and the maximum signed 64-bit integer")
        _require_integer(self.transaction_index, "transaction_index")
        if not 0 <= self.transaction_index <= _MAX_UINT64:
            raise ValueError("transaction_index must be an unsigned 64-bit integer")


class ArtifactLedgerLookup(Protocol):
    """Looks up artifacts already recorded in committed ledger state."""

    def contains(self, artifact_ref: ArtifactRef) -> bool:
        """Return whether an artifact has already been recorded."""
        ...


@final
@dataclass(frozen=True, slots=True, init=False)
class LocalArtifactLedger(ArtifactLedgerLookup):
    """An immutable, ordered commitment to artifacts accepted by this node."""

    _entries: tuple[ArtifactLedgerEntry, ...] = field(repr=False)
    _artifact_refs: frozenset[ArtifactRef] = field(repr=False)
    _state_hash: bytes = field(repr=False)

    def __init__(self, *, entries: tuple[ArtifactLedgerEntry, ...] = ()) -> None:
        if not isinstance(entries, tuple):
            raise TypeError("entries must be a tuple")

        artifact_refs: set[ArtifactRef] = set()
        state_hash = _EMPTY_LEDGER_HASH
        previous_position: tuple[int, int] | None = None

        for entry in entries:
            if not isinstance(entry, ArtifactLedgerEntry):
                raise TypeError("entries must contain ArtifactLedgerEntry values")

            position = _position(entry)
            if previous_position is not None and position <= previous_position:
                raise ValueError("entries must be in increasing block position order")

            reference = artifact_ref(entry.envelope)
            if reference in artifact_refs:
                raise ValueError("entries must not contain duplicate artifacts")

            artifact_refs.add(reference)
            state_hash = _advance_state_hash(state_hash, entry)
            previous_position = position

        object.__setattr__(self, "_entries", entries)
        object.__setattr__(self, "_artifact_refs", frozenset(artifact_refs))
        object.__setattr__(self, "_state_hash", state_hash)

    def contains(self, artifact_ref: ArtifactRef) -> bool:
        """Return whether an artifact has already been recorded."""
        return artifact_ref in self._artifact_refs

    def append_artifact(
        self,
        entry: ArtifactLedgerEntry,
    ) -> tuple[LocalArtifactLedger, AppendOutcome]:
        """Return the resulting ledger and append outcome."""
        if not isinstance(entry, ArtifactLedgerEntry):
            raise TypeError("entry must be an ArtifactLedgerEntry")
        reference = artifact_ref(entry.envelope)
        if self.contains(reference):
            return self, AppendOutcome.DUPLICATE
        if self._entries and _position(entry) <= _position(self._entries[-1]):
            raise ValueError("entry must follow the current ledger position")
        return (
            self._from_state(
                entries=(*self._entries, entry),
                artifact_refs=self._artifact_refs | {reference},
                state_hash=_advance_state_hash(self._state_hash, entry),
            ),
            AppendOutcome.ACCEPTED,
        )

    def entries(self) -> tuple[ArtifactLedgerEntry, ...]:
        """Return entries in canonical ledger order."""
        return self._entries

    def state_hash(self) -> bytes:
        """Return the deterministic hash of the current ledger state."""
        return self._state_hash

    @classmethod
    def _from_state(
        cls,
        *,
        entries: tuple[ArtifactLedgerEntry, ...],
        artifact_refs: frozenset[ArtifactRef],
        state_hash: bytes,
    ) -> LocalArtifactLedger:
        ledger = object.__new__(cls)
        object.__setattr__(ledger, "_entries", entries)
        object.__setattr__(ledger, "_artifact_refs", artifact_refs)
        object.__setattr__(ledger, "_state_hash", state_hash)
        return ledger


def _require_integer(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")


def _position(entry: ArtifactLedgerEntry) -> tuple[int, int]:
    return entry.height, entry.transaction_index


def _advance_state_hash(previous_hash: bytes, entry: ArtifactLedgerEntry) -> bytes:
    envelope_hash = sha256(encode_envelope(entry.envelope)).digest()
    position = entry.height.to_bytes(8, "big") + entry.transaction_index.to_bytes(8, "big")
    return sha256(_LEDGER_HASH_DOMAIN + previous_hash + position + envelope_hash).digest()
