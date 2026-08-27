from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from multiformats import CID

from discovery_net.knowledge_graph import (
    ArtifactRef,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.wire import (
    CodecError,
    PayloadType,
    SignedEnvelope,
    SignedTransaction,
    artifact_ref,
    decode_envelope,
    decode_payload,
    decode_transaction,
    encode_envelope,
    encode_payload,
    encode_signing_payload,
    encode_transaction,
    parse_artifact_ref,
    sign_artifact,
    sign_transaction,
    verify_envelope,
    verify_transaction,
)

PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
SECOND_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
PUBLIC_KEY = bytes.fromhex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
CREATED_AT = datetime(2026, 8, 24, 12, 30, tzinfo=UTC)


def sample_contribution() -> Contribution:
    return Contribution(
        kind=ContributionKind.PROBLEM_STATEMENT,
        title="Riemann hypothesis",
        body="All nontrivial zeros have real part one half.",
        created_at=CREATED_AT,
    )


def area_contribution() -> Contribution:
    return Contribution(
        kind=ContributionKind.MATHEMATICAL_AREA,
        title="Number theory",
        body="The study of integers and arithmetic structures.",
        created_at=CREATED_AT,
    )


def signed(artifact: Contribution | ContributionRelation | None = None) -> SignedEnvelope:
    return sign_artifact(
        chain_id="discovery-net-devnet",
        artifact=artifact if artifact is not None else sample_contribution(),
        private_key=PRIVATE_KEY,
    )


def sample_relation() -> ContributionRelation:
    return ContributionRelation(
        from_contribution=artifact_ref(signed(sample_contribution())),
        to_contribution=artifact_ref(signed(area_contribution())),
        kind=RelationKind.ABOUT,
        created_at=CREATED_AT,
    )


def test_contribution_payload_has_fixed_canonical_encoding() -> None:
    payload_type, payload = encode_payload(sample_contribution())

    assert payload_type is PayloadType.CONTRIBUTION
    assert payload == (
        b'{"body":"All nontrivial zeros have real part one half.",'
        b'"created_at":"2026-08-24T12:30:00Z","kind":"problem_statement",'
        b'"title":"Riemann hypothesis"}'
    )
    assert decode_payload(payload_type, payload) == sample_contribution()


def test_relation_payload_round_trips_with_content_references() -> None:
    relation = sample_relation()
    payload_type, payload = encode_payload(relation)

    assert payload_type is PayloadType.CONTRIBUTION_RELATION
    assert decode_payload(payload_type, payload) == relation
    assert parse_artifact_ref(relation.from_contribution) == relation.from_contribution
    assert parse_artifact_ref(relation.to_contribution) == relation.to_contribution


def test_datetimes_are_normalized_to_utc() -> None:
    offset_time = CREATED_AT.astimezone(timezone(timedelta(hours=-4)))
    shifted = replace(sample_contribution(), created_at=offset_time)

    assert encode_payload(shifted) == encode_payload(sample_contribution())


def test_signed_envelope_has_fixed_signing_bytes_and_round_trips() -> None:
    envelope = signed()
    signing_payload = encode_signing_payload(envelope)
    encoded = encode_envelope(envelope)

    assert signing_payload == (
        b'{"chain_id":"discovery-net-devnet","payload":'
        b'{"body":"All nontrivial zeros have real part one half.",'
        b'"created_at":"2026-08-24T12:30:00Z","kind":"problem_statement",'
        b'"title":"Riemann hypothesis"},"payload_type":"contribution",'
        b'"signer_public_key":"03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"}'
    )
    assert envelope.signature.hex() == (
        "9584f4f0a4a5ffbd3e82a8315b15013efeddbfcc12200e99542ede8f427a29a6"
        "0869b1a5dc3aa7a217930ac28e6e06cf13094bb31a77ec49f30272f54854200a"
    )
    assert decode_envelope(encoded) == envelope
    assert verify_envelope(envelope)


def test_artifact_reference_is_canonical_cid_for_the_signed_envelope() -> None:
    envelope = signed()
    encoded = encode_envelope(envelope)
    reference = artifact_ref(envelope)
    cid = CID.decode(reference)

    assert reference == "bafkreib4yjvxpcf3guleuc5d65bubag3x57etiz3ximbazly7qmj23ypdy"
    assert parse_artifact_ref(reference) == reference
    assert cid.version == 1
    assert cid.base.name == "base32"
    assert cid.codec.name == "raw"
    assert cid.hashfun.name == "sha2-256"
    assert cid.raw_digest == sha256(encoded).digest()


def test_artifact_reference_covers_signer_chain_payload_and_signature() -> None:
    envelope = signed()
    second_signer = sign_artifact(
        chain_id="discovery-net-devnet",
        artifact=sample_contribution(),
        private_key=SECOND_PRIVATE_KEY,
    )
    _, changed_payload = encode_payload(replace(sample_contribution(), title="A different title"))

    references = {
        artifact_ref(envelope),
        artifact_ref(second_signer),
        artifact_ref(replace(envelope, chain_id="discovery-net-mainnet")),
        artifact_ref(replace(envelope, payload=changed_payload)),
        artifact_ref(replace(envelope, signature=bytes(64))),
    }

    assert len(references) == 5


def test_envelope_is_immutable_and_validates_fixed_width_fields() -> None:
    envelope = signed()

    with pytest.raises(FrozenInstanceError):
        envelope.chain_id = "other"  # type: ignore[misc]
    assert envelope.signer_public_key == PUBLIC_KEY
    with pytest.raises(ValueError, match="signer_public_key"):
        replace(envelope, signer_public_key=bytes(31))
    with pytest.raises(ValueError, match="signature"):
        replace(envelope, signature=bytes(63))
    with pytest.raises(ValueError, match="chain_id"):
        replace(envelope, chain_id=" ")


def test_signature_covers_chain_signer_and_payload() -> None:
    envelope = signed()
    _, changed_payload = encode_payload(replace(sample_contribution(), title="A different title"))

    assert not verify_envelope(replace(envelope, chain_id="discovery-net-mainnet"))
    assert not verify_envelope(replace(envelope, payload=changed_payload))
    assert not verify_envelope(replace(envelope, signer_public_key=bytes(reversed(PUBLIC_KEY))))
    assert not verify_envelope(replace(envelope, signature=bytes(64)))


def test_signed_transaction_round_trips_and_binds_its_artifacts() -> None:
    envelopes = (signed(), signed(area_contribution()))
    transaction = sign_transaction(envelopes=envelopes, private_key=PRIVATE_KEY)
    encoded = encode_transaction(transaction)

    assert decode_transaction(encoded) == transaction
    assert verify_transaction(transaction)
    assert not verify_transaction(
        replace(transaction, envelopes=tuple(reversed(transaction.envelopes)))
    )
    assert not verify_transaction(replace(transaction, signature=bytes(64)))


def test_transaction_requires_artifacts_from_one_chain_and_signer() -> None:
    envelope = signed()
    other_signer = sign_artifact(
        chain_id=envelope.chain_id,
        artifact=area_contribution(),
        private_key=SECOND_PRIVATE_KEY,
    )

    with pytest.raises(ValueError, match="at least one"):
        SignedTransaction(envelopes=(), signature=bytes(64))
    with pytest.raises(ValueError, match="one chain"):
        SignedTransaction(
            envelopes=(envelope, replace(envelope, chain_id="another-chain")),
            signature=bytes(64),
        )
    with pytest.raises(ValueError, match="one signer"):
        SignedTransaction(envelopes=(envelope, other_signer), signature=bytes(64))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: b" " + data,
        lambda data: data + b"\n",
        lambda data: data.replace(b'"chain_id"', b'"unknown"', 1),
        lambda data: data.replace(b'"chain_id":', b'"chain_id":"duplicate","chain_id":', 1),
    ],
)
def test_decoder_rejects_noncanonical_duplicate_or_unknown_envelope_fields(
    mutate: Callable[[bytes], bytes],
) -> None:
    encoded = encode_envelope(signed())

    with pytest.raises(CodecError):
        decode_envelope(mutate(encoded))


@pytest.mark.parametrize(
    "payload",
    [
        (
            b'{"body":1,"created_at":"2026-08-24T12:30:00Z",'
            b'"kind":"problem_statement","title":"Riemann hypothesis"}'
        ),
        (
            b'{"body":"x","created_at":"2026-08-24T12:30:00",'
            b'"kind":"problem_statement","title":"Riemann hypothesis"}'
        ),
        b'{"body":"x","created_at":"2026-08-24T12:30:00Z","kind":"problem_statement","title":"x","unknown":true}',
        b'{"body":"x","created_at":"2026-08-24T12:30:00Z","kind":"problem_statement"}',
    ],
)
def test_pydantic_rejects_wrong_types_naive_times_extra_and_missing_fields(
    payload: bytes,
) -> None:
    with pytest.raises(CodecError, match="payload fields are invalid"):
        decode_payload(PayloadType.CONTRIBUTION, payload)


def test_payload_decoder_rejects_noncanonical_bytes() -> None:
    payload_type, payload = encode_payload(sample_contribution())

    with pytest.raises(CodecError, match="not canonical"):
        decode_payload(payload_type, payload.replace(b'":"', b'": "', 1))


@pytest.mark.parametrize("value", ["riemann-hypothesis", "550e8400-e29b-41d4-a716-446655440000"])
def test_semantic_names_and_uuids_are_not_artifact_references(value: str) -> None:
    with pytest.raises(ValueError, match="valid CID"):
        parse_artifact_ref(value)


def test_noncanonical_cid_string_is_not_an_artifact_reference() -> None:
    reference = artifact_ref(signed())
    base58_reference = CID.decode(reference).encode("base58btc")

    with pytest.raises(ValueError, match="canonical CIDv1"):
        parse_artifact_ref(base58_reference)


def test_relation_encoding_rejects_a_non_cid_reference() -> None:
    relation = replace(
        sample_relation(),
        from_contribution=ArtifactRef("riemann-hypothesis"),
    )

    with pytest.raises(CodecError, match="artifact fields are invalid"):
        encode_payload(relation)
