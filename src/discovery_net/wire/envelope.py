# Defines signed application messages exchanged with the network.

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

PUBLIC_KEY_LENGTH: Final = 32
SIGNATURE_LENGTH: Final = 64


class PayloadType(StrEnum):
    """The application-level type of an envelope payload."""

    EDGE_REVOCATION = "edge_revocation"
    CONTRIBUTION = "contribution"
    CONTRIBUTION_RELATION = "contribution_relation"


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedEnvelope:
    """An independently signed and addressable application artifact."""

    chain_id: str
    payload_type: PayloadType
    payload: bytes
    signer_public_key: bytes
    signature: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, str):
            raise TypeError("chain_id must be a string")
        if not self.chain_id.strip():
            raise ValueError("chain_id must not be blank")
        if not isinstance(self.payload_type, PayloadType):
            raise TypeError("payload_type must be a PayloadType")
        _require_bytes(self.payload, "payload")
        if not self.payload:
            raise ValueError("payload must not be empty")
        _require_bytes(self.signer_public_key, "signer_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.signature, "signature", SIGNATURE_LENGTH)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedTransaction:
    """Artifacts authorized and committed as one atomic operation."""

    envelopes: tuple[SignedEnvelope, ...]
    signature: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.envelopes, tuple):
            raise TypeError("envelopes must be a tuple")
        if not self.envelopes:
            raise ValueError("transaction must contain at least one envelope")
        if any(not isinstance(envelope, SignedEnvelope) for envelope in self.envelopes):
            raise TypeError("envelopes must contain SignedEnvelope values")
        first = self.envelopes[0]
        if any(envelope.chain_id != first.chain_id for envelope in self.envelopes[1:]):
            raise ValueError("transaction envelopes must use one chain")
        if any(
            envelope.signer_public_key != first.signer_public_key for envelope in self.envelopes[1:]
        ):
            raise ValueError("transaction envelopes must have one signer")
        _require_bytes(self.signature, "signature", SIGNATURE_LENGTH)

    @property
    def chain_id(self) -> str:
        """Return the chain shared by every artifact."""
        return self.envelopes[0].chain_id

    @property
    def signer_public_key(self) -> bytes:
        """Return the public key authorizing the atomic transaction."""
        return self.envelopes[0].signer_public_key


def _require_bytes(value: bytes, field_name: str, length: int | None = None) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{field_name} must be bytes")
    if length is not None and len(value) != length:
        raise ValueError(f"{field_name} must be exactly {length} bytes")
