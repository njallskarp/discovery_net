"""Cryptographic hashes and Merkle roots derived from canonical protocol bytes."""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

from discovery_net.node.codec import encode_block_header, encode_transaction
from discovery_net.node.primitives import ZERO_HASH, BlockHeader, Hash256, SignedTransaction


def sha256d(data: bytes) -> Hash256:
    """Return Bitcoin-style double SHA-256 over immutable bytes."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return Hash256(sha256(sha256(data).digest()).digest())


def transaction_hash(transaction: SignedTransaction) -> Hash256:
    """Hash the complete canonical signed transaction."""

    return sha256d(encode_transaction(transaction))


def merkle_root_from_hashes(hashes: Sequence[Hash256]) -> Hash256:
    """Build a Bitcoin-style Merkle root, duplicating an odd final node."""

    if not all(isinstance(value, Hash256) for value in hashes):
        raise TypeError("hashes must contain only Hash256 values")
    if not hashes:
        return ZERO_HASH

    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            sha256d(bytes(level[index]) + bytes(level[index + 1]))
            for index in range(0, len(level), 2)
        ]
    return level[0]


def transaction_merkle_root(transactions: Sequence[SignedTransaction]) -> Hash256:
    """Build the Merkle root for an ordered transaction sequence."""

    return merkle_root_from_hashes(tuple(transaction_hash(item) for item in transactions))


def block_hash(header: BlockHeader) -> Hash256:
    """Hash a block header without storing the result inside the block."""

    return sha256d(encode_block_header(header))
