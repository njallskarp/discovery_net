from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import ArtifactRef, Contribution, ContributionKind
from discovery_net.node import TransactionCode, TransactionResult, TransactionValidator
from discovery_net.wire import SignedEnvelope, artifact_ref, encode_envelope, sign_artifact

NETWORK_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


@dataclass(slots=True)
class ArtifactLookup:
    references: set[ArtifactRef] = field(default_factory=set)

    def contains(self, artifact_ref: ArtifactRef) -> bool:
        return artifact_ref in self.references


def signed_envelope(*, network_id: str = NETWORK_ID) -> SignedEnvelope:
    contribution = Contribution(
        kind=ContributionKind.PROBLEM_STATEMENT,
        title="Riemann hypothesis",
        body="All nontrivial zeros have real part one half.",
        created_at=datetime(2026, 8, 24, 12, 30, tzinfo=UTC),
    )
    return sign_artifact(
        network_id=network_id,
        artifact=contribution,
        private_key=PRIVATE_KEY,
    )


def transaction(*, network_id: str = NETWORK_ID) -> bytes:
    return encode_envelope(signed_envelope(network_id=network_id))


def validate(encoded: bytes, artifacts: ArtifactLookup | None = None) -> TransactionResult:
    validator = TransactionValidator(expected_network_id=NETWORK_ID)
    return validator.validate(encoded, artifacts or ArtifactLookup())


def test_transaction_codes_are_stable() -> None:
    assert dict(TransactionCode.__members__) == {
        "ACCEPTED": TransactionCode(0),
        "INVALID_ENVELOPE": TransactionCode(1),
        "WRONG_NETWORK": TransactionCode(2),
        "INVALID_SIGNATURE": TransactionCode(3),
        "DUPLICATE": TransactionCode(4),
    }


def test_accepts_a_canonical_signed_transaction_for_the_network() -> None:
    assert validate(transaction()) == TransactionResult(code=TransactionCode.ACCEPTED)


@pytest.mark.parametrize(
    "encoded",
    [
        b"not-json",
        b" " + transaction(),
        transaction() + b"\n",
    ],
)
def test_rejects_malformed_or_noncanonical_envelopes(encoded: bytes) -> None:
    assert validate(encoded) == TransactionResult(code=TransactionCode.INVALID_ENVELOPE)


def test_rejects_a_valid_transaction_for_another_network() -> None:
    assert validate(transaction(network_id="discovery-net-mainnet")) == TransactionResult(
        code=TransactionCode.WRONG_NETWORK
    )


def test_rejects_an_invalid_signature() -> None:
    invalid = encode_envelope(replace(signed_envelope(), signature=bytes(64)))

    assert validate(invalid) == TransactionResult(code=TransactionCode.INVALID_SIGNATURE)


def test_rejects_an_artifact_already_present_in_committed_state() -> None:
    envelope = signed_envelope()
    artifacts = ArtifactLookup(references={artifact_ref(envelope)})

    assert validate(encode_envelope(envelope), artifacts) == TransactionResult(
        code=TransactionCode.DUPLICATE
    )


@pytest.mark.parametrize("network_id", ["", " "])
def test_validator_requires_a_nonblank_network_id(network_id: str) -> None:
    with pytest.raises(ValueError, match="expected_network_id"):
        TransactionValidator(expected_network_id=network_id)
