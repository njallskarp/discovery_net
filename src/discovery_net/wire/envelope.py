# Defines signed application messages exchanged with the network.

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

PUBLIC_KEY_LENGTH: Final = 32
SIGNATURE_LENGTH: Final = 64


class PayloadType(StrEnum):
    """The application-level type of an envelope payload."""

    CONTRIBUTION = "contribution"
    CONTRIBUTION_RELATION = "contribution_relation"


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedEnvelope:
    """A signed application payload ready for consensus ordering."""

    network_id: str
    payload_type: PayloadType
    payload: bytes
    signer_public_key: bytes
    signature: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.network_id, str):
            raise TypeError("network_id must be a string")
        if not self.network_id.strip():
            raise ValueError("network_id must not be blank")
        if not isinstance(self.payload_type, PayloadType):
            raise TypeError("payload_type must be a PayloadType")
        _require_bytes(self.payload, "payload")
        if not self.payload:
            raise ValueError("payload must not be empty")
        _require_bytes(self.signer_public_key, "signer_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.signature, "signature", SIGNATURE_LENGTH)


def _require_bytes(value: bytes, field_name: str, length: int | None = None) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{field_name} must be bytes")
    if length is not None and len(value) != length:
        raise ValueError(f"{field_name} must be exactly {length} bytes")
