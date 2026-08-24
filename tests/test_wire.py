from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import (
    Contribution,
    ContributionId,
    ContributionKind,
    ContributionRelation,
    RelationId,
    RelationKind,
)
from discovery_net.wire import (
    CodecError,
    PayloadType,
    decode_envelope,
    decode_payload,
    encode_envelope,
    encode_payload,
    encode_signing_payload,
    sign_artifact,
    transaction_id,
    verify_envelope,
)

PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC_KEY = bytes.fromhex("03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8")
CREATED_AT = datetime(2026, 8, 24, 12, 30, tzinfo=UTC)


def sample_contribution() -> Contribution:
    return Contribution(
        id=ContributionId("contribution-riemann-hypothesis"),
        thread_root_id=ContributionId("contribution-riemann-hypothesis"),
        kind=ContributionKind.PROBLEM_STATEMENT,
        title="Riemann hypothesis",
        body="All nontrivial zeros have real part one half.",
        created_at=CREATED_AT,
    )


def sample_relation() -> ContributionRelation:
    return ContributionRelation(
        id=RelationId("relation-rh-number-theory"),
        from_contribution_id=ContributionId("contribution-riemann-hypothesis"),
        to_contribution_id=ContributionId("area-number-theory"),
        kind=RelationKind.ABOUT,
        created_at=CREATED_AT,
    )


def test_contribution_payload_has_fixed_canonical_encoding() -> None:
    payload_type, payload = encode_payload(sample_contribution())

    assert payload_type is PayloadType.CONTRIBUTION
    assert payload == (
        b'{"body":"All nontrivial zeros have real part one half.",'
        b'"created_at":"2026-08-24T12:30:00Z",'
        b'"id":"contribution-riemann-hypothesis","kind":"problem_statement",'
        b'"parent_id":null,"thread_root_id":"contribution-riemann-hypothesis",'
        b'"title":"Riemann hypothesis"}'
    )
    assert decode_payload(payload_type, payload) == sample_contribution()


def test_relation_payload_round_trips() -> None:
    payload_type, payload = encode_payload(sample_relation())

    assert payload_type is PayloadType.CONTRIBUTION_RELATION
    assert decode_payload(payload_type, payload) == sample_relation()


def test_datetimes_are_normalized_to_utc() -> None:
    offset_time = CREATED_AT.astimezone(timezone(timedelta(hours=-4)))
    shifted = replace(sample_contribution(), created_at=offset_time)

    assert encode_payload(shifted) == encode_payload(sample_contribution())


def test_signed_envelope_has_fixed_signing_bytes_and_round_trips() -> None:
    envelope = sign_artifact(
        network_id="discovery-net-devnet",
        artifact=sample_contribution(),
        private_key=PRIVATE_KEY,
    )
    signing_payload = encode_signing_payload(envelope)
    encoded = encode_envelope(envelope)

    assert signing_payload == (
        b'{"network_id":"discovery-net-devnet","payload":'
        b'{"body":"All nontrivial zeros have real part one half.",'
        b'"created_at":"2026-08-24T12:30:00Z",'
        b'"id":"contribution-riemann-hypothesis","kind":"problem_statement",'
        b'"parent_id":null,"thread_root_id":"contribution-riemann-hypothesis",'
        b'"title":"Riemann hypothesis"},"payload_type":"contribution",'
        b'"signer_public_key":"03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"}'
    )
    assert envelope.signature.hex() == (
        "3848e5cba091d873d6635633b02fab14e48674d0807aa71a38b9c2d3b35afdb"
        "7bdf6d3b9655c306a374995cf2ae23fd8f60f99e66e94fc9633660b39499b7101"
    )
    assert decode_envelope(encoded) == envelope
    assert verify_envelope(envelope)
    assert transaction_id(envelope) == (
        "275863ac302e94987fc1fd177187195c6f3dab3fcf2747a229fff7d3c5f62fd6"
    )
    assert transaction_id(envelope) == sha256(encoded).hexdigest()


def test_envelope_is_immutable_and_validates_fixed_width_fields() -> None:
    envelope = sign_artifact(
        network_id="discovery-net-devnet",
        artifact=sample_contribution(),
        private_key=PRIVATE_KEY,
    )

    with pytest.raises(FrozenInstanceError):
        envelope.network_id = "other"  # type: ignore[misc]
    assert envelope.signer_public_key == PUBLIC_KEY
    with pytest.raises(ValueError, match="signer_public_key"):
        replace(envelope, signer_public_key=bytes(31))
    with pytest.raises(ValueError, match="signature"):
        replace(envelope, signature=bytes(63))
    with pytest.raises(ValueError, match="network_id"):
        replace(envelope, network_id=" ")


def test_signature_covers_network_and_payload() -> None:
    envelope = sign_artifact(
        network_id="discovery-net-devnet",
        artifact=sample_contribution(),
        private_key=PRIVATE_KEY,
    )
    _, changed_payload = encode_payload(replace(sample_contribution(), title="A different title"))

    assert not verify_envelope(replace(envelope, network_id="discovery-net-mainnet"))
    assert not verify_envelope(replace(envelope, payload=changed_payload))
    assert not verify_envelope(replace(envelope, signer_public_key=bytes(reversed(PUBLIC_KEY))))
    assert not verify_envelope(replace(envelope, signature=bytes(64)))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: b" " + data,
        lambda data: data + b"\n",
        lambda data: data.replace(b'"network_id"', b'"unknown"', 1),
    ],
)
def test_decoder_rejects_noncanonical_or_unknown_envelope_fields(
    mutate: Callable[[bytes], bytes],
) -> None:
    envelope = sign_artifact(
        network_id="discovery-net-devnet",
        artifact=sample_contribution(),
        private_key=PRIVATE_KEY,
    )
    encoded = encode_envelope(envelope)

    with pytest.raises(CodecError):
        decode_envelope(mutate(encoded))


def test_decoder_rejects_duplicate_json_keys() -> None:
    data = b'{"network_id":"one","network_id":"two"}'

    with pytest.raises(CodecError, match="valid JSON"):
        decode_envelope(data)


def test_payload_decoder_rejects_noncanonical_bytes() -> None:
    payload_type, payload = encode_payload(sample_contribution())

    with pytest.raises(CodecError, match="not canonical"):
        decode_payload(payload_type, payload.replace(b'":"', b'": "', 1))


def test_transaction_id_changes_with_the_signature() -> None:
    envelope = sign_artifact(
        network_id="discovery-net-devnet",
        artifact=sample_contribution(),
        private_key=PRIVATE_KEY,
    )

    assert transaction_id(envelope) != transaction_id(replace(envelope, signature=bytes(64)))
