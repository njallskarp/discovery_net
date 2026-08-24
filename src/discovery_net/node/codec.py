"""Deterministic binary encoding and strict decoding of protocol data."""

from __future__ import annotations

from dataclasses import dataclass
from struct import Struct
from typing import Final

from discovery_net.node.primitives import (
    MAX_UINT32,
    Block,
    BlockHeader,
    Hash256,
    PayloadKind,
    SignedTransaction,
)

TRANSACTION_MAGIC: Final = b"DNTX"
BLOCK_HEADER_MAGIC: Final = b"DNBH"
BLOCK_MAGIC: Final = b"DNBL"

_UINT16: Final = Struct(">H")
_UINT32: Final = Struct(">I")
_UINT64: Final = Struct(">Q")
_UINT256_LENGTH: Final = 32
BLOCK_HEADER_SIZE: Final = 4 + 4 + 32 + 32 + 8 + _UINT256_LENGTH + 8
MIN_TRANSACTION_SIZE: Final = 4 + 4 + 2 + 4 + 32 + 64


class CodecError(ValueError):
    """Raised when protocol bytes are malformed or non-canonical."""


@dataclass(slots=True)
class _Reader:
    data: bytes
    position: int = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.position

    def read(self, length: int) -> bytes:
        if length < 0 or length > self.remaining:
            raise CodecError("protocol data ended unexpectedly")
        start = self.position
        self.position += length
        return self.data[start : self.position]

    def read_uint16(self) -> int:
        return int(_UINT16.unpack(self.read(_UINT16.size))[0])

    def read_uint32(self) -> int:
        return int(_UINT32.unpack(self.read(_UINT32.size))[0])

    def read_uint64(self) -> int:
        return int(_UINT64.unpack(self.read(_UINT64.size))[0])

    def require_end(self) -> None:
        if self.remaining:
            raise CodecError("protocol data contains trailing bytes")


def _require_bytes(data: bytes) -> None:
    if not isinstance(data, bytes):
        raise TypeError("protocol data must be bytes")


def _encode_uint256(value: int) -> bytes:
    return value.to_bytes(_UINT256_LENGTH, byteorder="big", signed=False)


def encode_transaction_signing_payload(transaction: SignedTransaction) -> bytes:
    """Encode the transaction fields covered by an author signature."""

    return b"".join(
        (
            TRANSACTION_MAGIC,
            _UINT32.pack(transaction.version),
            _UINT16.pack(transaction.payload_kind.value),
            _UINT32.pack(len(transaction.payload)),
            transaction.payload,
            transaction.author_public_key,
        )
    )


def encode_transaction(transaction: SignedTransaction) -> bytes:
    """Encode a signed transaction into its unique protocol representation."""

    return encode_transaction_signing_payload(transaction) + transaction.signature


def decode_transaction(data: bytes) -> SignedTransaction:
    """Decode one complete canonical transaction."""

    _require_bytes(data)
    reader = _Reader(data)
    if reader.read(len(TRANSACTION_MAGIC)) != TRANSACTION_MAGIC:
        raise CodecError("transaction magic is invalid")

    version = reader.read_uint32()
    payload_kind_value = reader.read_uint16()
    payload_length = reader.read_uint32()
    if payload_length > reader.remaining - 32 - 64:
        raise CodecError("transaction payload length exceeds the available data")
    payload = reader.read(payload_length)
    author_public_key = reader.read(32)
    signature = reader.read(64)
    reader.require_end()

    try:
        payload_kind = PayloadKind(payload_kind_value)
        return SignedTransaction(
            version=version,
            payload_kind=payload_kind,
            payload=payload,
            author_public_key=author_public_key,
            signature=signature,
        )
    except (TypeError, ValueError) as error:
        raise CodecError("transaction fields are invalid") from error


def encode_block_header(header: BlockHeader) -> bytes:
    """Encode a block header into its unique fixed-width representation."""

    return b"".join(
        (
            BLOCK_HEADER_MAGIC,
            _UINT32.pack(header.version),
            bytes(header.previous_block_hash),
            bytes(header.transaction_root),
            _UINT64.pack(header.timestamp),
            _encode_uint256(header.target),
            _UINT64.pack(header.nonce),
        )
    )


def decode_block_header(data: bytes) -> BlockHeader:
    """Decode one complete canonical block header."""

    _require_bytes(data)
    if len(data) != BLOCK_HEADER_SIZE:
        raise CodecError(f"a block header must be exactly {BLOCK_HEADER_SIZE} bytes")
    reader = _Reader(data)
    if reader.read(len(BLOCK_HEADER_MAGIC)) != BLOCK_HEADER_MAGIC:
        raise CodecError("block header magic is invalid")

    try:
        header = BlockHeader(
            version=reader.read_uint32(),
            previous_block_hash=Hash256(reader.read(32)),
            transaction_root=Hash256(reader.read(32)),
            timestamp=reader.read_uint64(),
            target=int.from_bytes(reader.read(_UINT256_LENGTH), byteorder="big"),
            nonce=reader.read_uint64(),
        )
    except (TypeError, ValueError) as error:
        raise CodecError("block header fields are invalid") from error
    reader.require_end()
    return header


def encode_block(block: Block) -> bytes:
    """Encode a block and its ordered transactions."""

    encoded_transactions = tuple(encode_transaction(item) for item in block.transactions)
    parts = [
        BLOCK_MAGIC,
        encode_block_header(block.header),
        _UINT32.pack(len(encoded_transactions)),
    ]
    for encoded_transaction in encoded_transactions:
        if len(encoded_transaction) > MAX_UINT32:
            raise ValueError(f"an encoded transaction must not exceed {MAX_UINT32} bytes")
        parts.extend((_UINT32.pack(len(encoded_transaction)), encoded_transaction))
    return b"".join(parts)


def decode_block(data: bytes) -> Block:
    """Decode one complete canonical block."""

    _require_bytes(data)
    reader = _Reader(data)
    if reader.read(len(BLOCK_MAGIC)) != BLOCK_MAGIC:
        raise CodecError("block magic is invalid")
    header = decode_block_header(reader.read(BLOCK_HEADER_SIZE))
    transaction_count = reader.read_uint32()
    if transaction_count > reader.remaining // (4 + MIN_TRANSACTION_SIZE):
        raise CodecError("block transaction count exceeds the available data")

    transactions: list[SignedTransaction] = []
    for _ in range(transaction_count):
        transaction_length = reader.read_uint32()
        transactions.append(decode_transaction(reader.read(transaction_length)))
    reader.require_end()
    return Block(header=header, transactions=tuple(transactions))
