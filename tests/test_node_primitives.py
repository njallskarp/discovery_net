from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from discovery_net.node.codec import (
    BLOCK_HEADER_SIZE,
    BLOCK_MAGIC,
    CodecError,
    decode_block,
    decode_block_header,
    decode_transaction,
    encode_block,
    encode_block_header,
    encode_transaction,
    encode_transaction_signing_payload,
)
from discovery_net.node.hashing import block_hash, transaction_hash, transaction_merkle_root
from discovery_net.node.primitives import (
    DEVNET_GENESIS_BLOCK,
    DEVNET_TARGET,
    GENESIS_TIMESTAMP,
    MAX_UINT32,
    MAX_UINT64,
    ZERO_HASH,
    Block,
    BlockHeader,
    Hash256,
    PayloadKind,
    SignedTransaction,
)


def sample_transaction() -> SignedTransaction:
    return SignedTransaction(
        version=1,
        payload_kind=PayloadKind.CONTRIBUTION,
        payload=b"prime gaps",
        author_public_key=bytes(range(32)),
        signature=bytes(range(64)),
    )


def second_transaction() -> SignedTransaction:
    return SignedTransaction(
        version=1,
        payload_kind=PayloadKind.CONTRIBUTION_RELATION,
        payload=b"supports",
        author_public_key=bytes(range(31, -1, -1)),
        signature=bytes(range(63, -1, -1)),
    )


def sample_header() -> BlockHeader:
    transactions = (sample_transaction(), second_transaction())
    return BlockHeader(
        version=1,
        previous_block_hash=Hash256(bytes(range(32))),
        transaction_root=transaction_merkle_root(transactions),
        timestamp=GENESIS_TIMESTAMP + 600,
        target=DEVNET_TARGET,
        nonce=42,
    )


def sample_block() -> Block:
    return Block(
        header=sample_header(),
        transactions=(sample_transaction(), second_transaction()),
    )


@pytest.mark.parametrize("length", [0, 31, 33])
def test_hash_rejects_invalid_lengths(length: int) -> None:
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        Hash256(bytes(length))


def test_hash_hex_round_trip_is_exact() -> None:
    value = Hash256(bytes(range(32)))

    assert Hash256.from_hex(value.hex()) == value

    with pytest.raises(ValueError, match="exactly 64"):
        Hash256.from_hex("00")


@pytest.mark.parametrize(
    ("public_key_length", "signature_length", "message"),
    [(31, 64, "author_public_key"), (32, 63, "signature")],
)
def test_transaction_rejects_invalid_key_and_signature_lengths(
    public_key_length: int,
    signature_length: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SignedTransaction(
            version=1,
            payload_kind=PayloadKind.CONTRIBUTION,
            payload=b"payload",
            author_public_key=bytes(public_key_length),
            signature=bytes(signature_length),
        )


@pytest.mark.parametrize("version", [-1, MAX_UINT32 + 1])
def test_transaction_rejects_out_of_range_version(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        SignedTransaction(
            version=version,
            payload_kind=PayloadKind.CONTRIBUTION,
            payload=b"payload",
            author_public_key=bytes(32),
            signature=bytes(64),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", MAX_UINT32 + 1),
        ("timestamp", MAX_UINT64 + 1),
        ("target", 0),
        ("target", 1 << 256),
        ("nonce", MAX_UINT64 + 1),
    ],
)
def test_header_rejects_invalid_integer_ranges(field: str, value: int) -> None:
    values = {
        "version": 1,
        "previous_block_hash": ZERO_HASH,
        "transaction_root": ZERO_HASH,
        "timestamp": GENESIS_TIMESTAMP,
        "target": DEVNET_TARGET,
        "nonce": 0,
    }
    values[field] = value

    with pytest.raises(ValueError, match=field):
        BlockHeader(**values)  # type: ignore[arg-type]


def test_primitives_are_immutable() -> None:
    transaction = sample_transaction()

    with pytest.raises(FrozenInstanceError):
        transaction.version = 2  # type: ignore[misc]

    with pytest.raises(TypeError, match="tuple"):
        Block(header=sample_header(), transactions=[])  # type: ignore[arg-type]


def test_transaction_has_fixed_golden_encoding_and_hash() -> None:
    transaction = sample_transaction()

    assert encode_transaction_signing_payload(transaction).hex() == (
        "444e54580000000100010000000a7072696d652067617073"
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    )
    assert encode_transaction(transaction).hex() == (
        "444e54580000000100010000000a7072696d652067617073"
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
        "202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f"
    )
    assert transaction_hash(transaction).hex() == (
        "36a67feb47f58c72a3fd3b309c8957ba746b0f03950da248ed9e3549aace1feb"
    )


def test_signature_is_excluded_only_from_the_signing_payload() -> None:
    transaction = sample_transaction()
    changed_signature = replace(transaction, signature=bytes(reversed(transaction.signature)))

    assert encode_transaction_signing_payload(changed_signature) == (
        encode_transaction_signing_payload(transaction)
    )
    assert encode_transaction(changed_signature) != encode_transaction(transaction)
    assert transaction_hash(changed_signature) != transaction_hash(transaction)


def test_transaction_codec_is_strict_and_round_trips() -> None:
    encoded = encode_transaction(sample_transaction())

    assert decode_transaction(encoded) == sample_transaction()

    with pytest.raises(CodecError, match="trailing"):
        decode_transaction(encoded + b"\x00")
    with pytest.raises(CodecError, match="magic"):
        decode_transaction(b"BAD!" + encoded[4:])
    with pytest.raises(CodecError, match="available data"):
        decode_transaction(encoded[:-1])

    unknown_kind = bytearray(encoded)
    unknown_kind[8:10] = b"\x00\x00"
    with pytest.raises(CodecError, match="fields are invalid"):
        decode_transaction(bytes(unknown_kind))


def test_merkle_root_has_fixed_vectors_and_depends_on_order() -> None:
    first = sample_transaction()
    second = second_transaction()

    assert transaction_merkle_root(()).hex() == ZERO_HASH.hex()
    assert transaction_merkle_root((first,)).hex() == transaction_hash(first).hex()
    assert transaction_merkle_root((first, second)).hex() == (
        "759eec68238a2eb4a16a50a72d3aa110266fd4af845f2a936e8031ae66b2f316"
    )
    assert transaction_merkle_root((second, first)).hex() == (
        "9e2acc58b93750bbae8c0e490c9da8c4a9725bef1c6315ae6398c643a2117b34"
    )


def test_header_has_fixed_golden_encoding_and_hash() -> None:
    header = sample_header()
    encoded = encode_block_header(header)

    assert len(encoded) == BLOCK_HEADER_SIZE
    assert encoded.hex() == (
        "444e424800000001"
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
        "759eec68238a2eb4a16a50a72d3aa110266fd4af845f2a936e8031ae66b2f316"
        "000000006a8b8bd8"
        "0fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "000000000000002a"
    )
    assert block_hash(header).hex() == (
        "496e7e0f0d1ad2962d596ac51d25073c37c08249fa69dbcf5fd68c2c0b816622"
    )
    assert decode_block_header(encoded) == header


def test_every_header_field_affects_the_derived_hash() -> None:
    header = sample_header()
    changed_headers = (
        replace(header, version=header.version + 1),
        replace(header, previous_block_hash=ZERO_HASH),
        replace(header, transaction_root=ZERO_HASH),
        replace(header, timestamp=header.timestamp + 1),
        replace(header, target=header.target - 1),
        replace(header, nonce=header.nonce + 1),
    )

    original_hash = block_hash(header)
    changed_hashes = {block_hash(value) for value in changed_headers}

    assert original_hash not in changed_hashes
    assert len(changed_hashes) == len(changed_headers)


def test_block_codec_is_deterministic_and_round_trips() -> None:
    block = sample_block()
    encoded = encode_block(block)

    assert decode_block(encoded) == block
    assert sha256(encoded).hexdigest() == (
        "73074fc9e9d4e3c92895ff5159c5152ab260a67701451eb9b96e341df7603754"
    )
    assert not hasattr(block, "current_hash")
    assert not hasattr(block, "index")

    with pytest.raises(CodecError, match="trailing"):
        decode_block(encoded + b"\x00")


def test_block_decoder_rejects_an_impossible_transaction_count() -> None:
    encoded = (
        BLOCK_MAGIC + encode_block_header(sample_header()) + MAX_UINT32.to_bytes(4, byteorder="big")
    )

    with pytest.raises(CodecError, match="transaction count"):
        decode_block(encoded)


def test_devnet_genesis_block_and_hash_are_fixed() -> None:
    encoded_header = encode_block_header(DEVNET_GENESIS_BLOCK.header)
    digest = block_hash(DEVNET_GENESIS_BLOCK.header)

    assert DEVNET_GENESIS_BLOCK.transactions == ()
    assert DEVNET_GENESIS_BLOCK.header.previous_block_hash == ZERO_HASH
    assert DEVNET_GENESIS_BLOCK.header.transaction_root == transaction_merkle_root(())
    assert encoded_header.hex() == (
        "444e424800000001"
        "0000000000000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000"
        "000000006a8b8980"
        "0fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "0000000000000001"
    )
    assert digest.hex() == "06c3eebc62c149e5f48b170f523d566c9433e3d51fbe6ec24fe091dd9a09fee1"
    assert int.from_bytes(bytes(digest), byteorder="big") <= DEVNET_TARGET
