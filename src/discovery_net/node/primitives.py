"""Consensus data structures shared by every discovery network node."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

HASH_LENGTH: Final = 32
PUBLIC_KEY_LENGTH: Final = 32
SIGNATURE_LENGTH: Final = 64
MAX_UINT32: Final = (1 << 32) - 1
MAX_UINT64: Final = (1 << 64) - 1
MAX_UINT256: Final = (1 << 256) - 1


def _require_bytes(value: bytes, field_name: str, length: int | None = None) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{field_name} must be bytes")
    if length is not None and len(value) != length:
        raise ValueError(f"{field_name} must be exactly {length} bytes")


def _require_uint(value: int, field_name: str, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if not 0 <= value <= maximum:
        raise ValueError(f"{field_name} must be between 0 and {maximum}")


class PayloadKind(IntEnum):
    """The protocol-level type of a transaction payload."""

    CONTRIBUTION = 1
    CONTRIBUTION_RELATION = 2


@dataclass(frozen=True, slots=True)
class Hash256:
    """An immutable 256-bit hash value."""

    value: bytes

    def __post_init__(self) -> None:
        _require_bytes(self.value, "value", HASH_LENGTH)

    def __bytes__(self) -> bytes:
        return self.value

    def hex(self) -> str:
        """Return the conventional hexadecimal representation."""

        return self.value.hex()

    @classmethod
    def from_hex(cls, value: str) -> Hash256:
        """Create a hash from exactly 64 hexadecimal characters."""

        if not isinstance(value, str):
            raise TypeError("value must be a string")
        if len(value) != HASH_LENGTH * 2:
            raise ValueError("a Hash256 hex value must contain exactly 64 characters")
        try:
            decoded = bytes.fromhex(value)
        except ValueError as error:
            raise ValueError(
                "a Hash256 hex value must contain only hexadecimal characters"
            ) from error
        return cls(decoded)


ZERO_HASH: Final = Hash256(bytes(HASH_LENGTH))


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedTransaction:
    """An opaque application payload with its author key and signature."""

    version: int
    payload_kind: PayloadKind
    payload: bytes
    author_public_key: bytes
    signature: bytes

    def __post_init__(self) -> None:
        _require_uint(self.version, "version", MAX_UINT32)
        if not isinstance(self.payload_kind, PayloadKind):
            raise TypeError("payload_kind must be a PayloadKind")
        _require_bytes(self.payload, "payload")
        if len(self.payload) > MAX_UINT32:
            raise ValueError(f"payload must not exceed {MAX_UINT32} bytes")
        _require_bytes(self.author_public_key, "author_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.signature, "signature", SIGNATURE_LENGTH)


@dataclass(frozen=True, slots=True, kw_only=True)
class BlockHeader:
    """The fixed-width fields whose encoding determines a block hash."""

    version: int
    previous_block_hash: Hash256
    transaction_root: Hash256
    timestamp: int
    target: int
    nonce: int

    def __post_init__(self) -> None:
        _require_uint(self.version, "version", MAX_UINT32)
        if not isinstance(self.previous_block_hash, Hash256):
            raise TypeError("previous_block_hash must be a Hash256")
        if not isinstance(self.transaction_root, Hash256):
            raise TypeError("transaction_root must be a Hash256")
        _require_uint(self.timestamp, "timestamp", MAX_UINT64)
        _require_uint(self.target, "target", MAX_UINT256)
        if self.target == 0:
            raise ValueError("target must be positive")
        _require_uint(self.nonce, "nonce", MAX_UINT64)


@dataclass(frozen=True, slots=True, kw_only=True)
class Block:
    """A block header and its ordered immutable transaction sequence."""

    header: BlockHeader
    transactions: tuple[SignedTransaction, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.header, BlockHeader):
            raise TypeError("header must be a BlockHeader")
        if not isinstance(self.transactions, tuple):
            raise TypeError("transactions must be a tuple")
        if len(self.transactions) > MAX_UINT32:
            raise ValueError(f"transactions must not exceed {MAX_UINT32} entries")
        if not all(isinstance(transaction, SignedTransaction) for transaction in self.transactions):
            raise TypeError("transactions must contain only SignedTransaction values")


PROTOCOL_VERSION: Final = 1
DEVNET_TARGET: Final = (1 << 252) - 1
GENESIS_TIMESTAMP: Final = 1_787_529_600

DEVNET_GENESIS_BLOCK: Final = Block(
    header=BlockHeader(
        version=PROTOCOL_VERSION,
        previous_block_hash=ZERO_HASH,
        transaction_root=ZERO_HASH,
        timestamp=GENESIS_TIMESTAMP,
        target=DEVNET_TARGET,
        nonce=1,
    ),
    transactions=(),
)
