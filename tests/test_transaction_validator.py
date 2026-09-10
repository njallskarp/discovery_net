from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import (
    Artifact,
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.node import (
    AppendOutcome,
    ArtifactLedgerEntry,
    LocalArtifactLedger,
    TransactionCode,
    TransactionResult,
    TransactionValidator,
)
from discovery_net.wire import (
    TRANSACTION_LIMITS,
    SignedEnvelope,
    SignedTransaction,
    artifact_ref,
    encode_transaction,
    sign_artifact,
    sign_transaction,
)

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
CREATED_AT = datetime(2026, 8, 24, 12, 30, tzinfo=UTC)


def contribution(title: str) -> Contribution:
    return Contribution(
        kind=ContributionKind.PROBLEM_STATEMENT,
        title=title,
        body=f"The body of {title}.",
        created_at=CREATED_AT,
    )


def envelope(artifact: Artifact, *, chain_id: str = CHAIN_ID) -> SignedEnvelope:
    return sign_artifact(chain_id=chain_id, artifact=artifact, private_key=PRIVATE_KEY)


def signed_transaction(
    artifacts: tuple[Artifact, ...],
    *,
    chain_id: str = CHAIN_ID,
) -> SignedTransaction:
    return sign_transaction(
        envelopes=tuple(envelope(artifact, chain_id=chain_id) for artifact in artifacts),
        private_key=PRIVATE_KEY,
    )


def validate(encoded: bytes, ledger: LocalArtifactLedger | None = None) -> TransactionResult:
    return TransactionValidator(expected_chain_id=CHAIN_ID).validate(
        encoded,
        ledger if ledger is not None else LocalArtifactLedger(),
    )


def transaction_with_size(encoded_size: int) -> bytes:
    base = Contribution(
        kind=ContributionKind.PROBLEM_STATEMENT,
        title="Boundary-sized contribution",
        body="",
        created_at=CREATED_AT,
    )
    base_size = len(encode_transaction(signed_transaction((base,))))
    return encode_transaction(
        signed_transaction((replace(base, body="x" * (encoded_size - base_size)),))
    )


def append(
    ledger: LocalArtifactLedger,
    transaction: SignedTransaction,
    *,
    transaction_index: int,
) -> LocalArtifactLedger:
    resulting, outcome = ledger.append_transaction(
        ArtifactLedgerEntry(
            transaction=transaction,
            height=1,
            transaction_index=transaction_index,
        )
    )
    assert outcome is AppendOutcome.ACCEPTED
    return resulting


def test_transaction_codes_are_stable() -> None:
    assert dict(TransactionCode.__members__) == {
        "ACCEPTED": TransactionCode(0),
        "INVALID_TRANSACTION": TransactionCode(1),
        "WRONG_CHAIN": TransactionCode(2),
        "INVALID_SIGNATURE": TransactionCode(3),
        "DUPLICATE": TransactionCode(4),
        "MISSING_REFERENCE": TransactionCode(5),
        "TRANSACTION_TOO_LARGE": TransactionCode(6),
        "TOO_MANY_ARTIFACTS": TransactionCode(7),
        "GOVERNANCE_DISABLED": TransactionCode(8),
        "UNAUTHORIZED": TransactionCode(9),
        "GOVERNANCE_BUSY": TransactionCode(10),
        "INVALID_VALIDATOR_CHANGE": TransactionCode(11),
        "DUPLICATE_GOVERNANCE_ACTION": TransactionCode(12),
        "UNKNOWN_VALIDATOR_PROPOSAL": TransactionCode(13),
    }


def test_accepts_a_canonical_signed_transaction_for_the_chain() -> None:
    transaction = signed_transaction((contribution("Riemann hypothesis"),))

    assert validate(encode_transaction(transaction)) == TransactionResult(
        code=TransactionCode.ACCEPTED
    )


def test_accepts_a_valid_transaction_at_the_encoded_byte_limit() -> None:
    encoded = transaction_with_size(TRANSACTION_LIMITS.maximum_encoded_bytes)

    assert len(encoded) == TRANSACTION_LIMITS.maximum_encoded_bytes
    assert validate(encoded).code is TransactionCode.ACCEPTED


def test_rejects_an_oversized_transaction_before_decoding() -> None:
    encoded = bytes(TRANSACTION_LIMITS.maximum_encoded_bytes + 1)

    with patch("discovery_net.node.transaction_validator.decode_transaction") as decode:
        result = validate(encoded)

    assert result.code is TransactionCode.TRANSACTION_TOO_LARGE
    decode.assert_not_called()


def test_accepts_the_maximum_number_of_artifacts() -> None:
    transaction = signed_transaction(
        tuple(
            contribution(f"Contribution {index}")
            for index in range(TRANSACTION_LIMITS.maximum_artifacts)
        )
    )

    assert len(transaction.envelopes) == TRANSACTION_LIMITS.maximum_artifacts
    assert validate(encode_transaction(transaction)).code is TransactionCode.ACCEPTED


def test_rejects_one_artifact_over_the_atomic_package_limit() -> None:
    transaction = signed_transaction(
        tuple(
            contribution(f"Contribution {index}")
            for index in range(TRANSACTION_LIMITS.maximum_artifacts + 1)
        )
    )

    encoded = encode_transaction(transaction)

    assert len(encoded) <= TRANSACTION_LIMITS.maximum_encoded_bytes
    assert validate(encoded).code is TransactionCode.TOO_MANY_ARTIFACTS


def test_accepts_a_relation_to_a_contribution_in_the_same_atomic_transaction() -> None:
    problem_envelope = envelope(contribution("Riemann hypothesis"))
    area_envelope = envelope(contribution("Number theory"))
    relation_envelope = envelope(
        ContributionRelation(
            from_contribution=artifact_ref(problem_envelope),
            to_contribution=artifact_ref(area_envelope),
            kind=RelationKind.ABOUT,
            created_at=CREATED_AT,
        )
    )
    transaction = sign_transaction(
        envelopes=(problem_envelope, relation_envelope, area_envelope),
        private_key=PRIVATE_KEY,
    )

    assert validate(encode_transaction(transaction)).code is TransactionCode.ACCEPTED


def test_accepts_a_post_hoc_relation_between_committed_contributions() -> None:
    source = signed_transaction((contribution("Source"),))
    target = signed_transaction((contribution("Target"),))
    ledger = append(LocalArtifactLedger(), source, transaction_index=0)
    ledger = append(ledger, target, transaction_index=1)
    relation = ContributionRelation(
        from_contribution=artifact_ref(source.envelopes[0]),
        to_contribution=artifact_ref(target.envelopes[0]),
        kind=RelationKind.CITES,
        created_at=CREATED_AT,
    )

    assert validate(encode_transaction(signed_transaction((relation,))), ledger).code is (
        TransactionCode.ACCEPTED
    )


@pytest.mark.parametrize(
    "encoded",
    (
        b"not-json",
        b" " + encode_transaction(signed_transaction((contribution("Problem"),))),
        encode_transaction(signed_transaction((contribution("Problem"),))) + b"\n",
    ),
)
def test_rejects_malformed_or_noncanonical_transactions(encoded: bytes) -> None:
    assert validate(encoded).code is TransactionCode.INVALID_TRANSACTION


def test_rejects_a_valid_transaction_for_another_chain() -> None:
    transaction = signed_transaction(
        (contribution("Problem"),),
        chain_id="discovery-net-mainnet",
    )

    assert validate(encode_transaction(transaction)).code is TransactionCode.WRONG_CHAIN


def test_rejects_invalid_inner_or_outer_signatures() -> None:
    transaction = signed_transaction((contribution("Problem"),))
    invalid_inner = replace(
        transaction,
        envelopes=(replace(transaction.envelopes[0], signature=bytes(64)),),
    )

    assert validate(encode_transaction(invalid_inner)).code is TransactionCode.INVALID_SIGNATURE
    assert (
        validate(encode_transaction(replace(transaction, signature=bytes(64)))).code
        is TransactionCode.INVALID_SIGNATURE
    )


def test_rejects_an_artifact_detached_from_an_already_signed_transaction() -> None:
    transaction = signed_transaction(
        (contribution("Contribution"), contribution("Attached artifact"))
    )
    detached = replace(transaction, envelopes=(transaction.envelopes[0],))

    assert validate(encode_transaction(detached)).code is TransactionCode.INVALID_SIGNATURE


def test_rejects_the_whole_transaction_when_any_artifact_is_a_duplicate() -> None:
    committed = signed_transaction((contribution("Committed"),))
    ledger = append(LocalArtifactLedger(), committed, transaction_index=0)
    duplicate_and_new = sign_transaction(
        envelopes=(committed.envelopes[0], envelope(contribution("New"))),
        private_key=PRIVATE_KEY,
    )

    assert validate(encode_transaction(duplicate_and_new), ledger).code is (
        TransactionCode.DUPLICATE
    )


def test_rejects_the_whole_transaction_when_a_relation_endpoint_is_missing() -> None:
    source_envelope = envelope(contribution("Source"))
    missing_target = artifact_ref(envelope(contribution("Not submitted")))
    relation_envelope = envelope(
        ContributionRelation(
            from_contribution=artifact_ref(source_envelope),
            to_contribution=missing_target,
            kind=RelationKind.CITES,
            created_at=CREATED_AT,
        )
    )
    transaction = sign_transaction(
        envelopes=(source_envelope, relation_envelope),
        private_key=PRIVATE_KEY,
    )

    assert validate(encode_transaction(transaction)).code is TransactionCode.MISSING_REFERENCE


def test_relation_endpoints_must_be_contributions_not_other_relation_artifacts() -> None:
    source = signed_transaction((contribution("Source"),))
    target = signed_transaction((contribution("Target"),))
    ledger = append(LocalArtifactLedger(), source, transaction_index=0)
    ledger = append(ledger, target, transaction_index=1)
    committed_relation = signed_transaction(
        (
            ContributionRelation(
                from_contribution=artifact_ref(source.envelopes[0]),
                to_contribution=artifact_ref(target.envelopes[0]),
                kind=RelationKind.CITES,
                created_at=CREATED_AT,
            ),
        )
    )
    ledger = append(ledger, committed_relation, transaction_index=2)
    invalid_relation = ContributionRelation(
        from_contribution=artifact_ref(committed_relation.envelopes[0]),
        to_contribution=artifact_ref(target.envelopes[0]),
        kind=RelationKind.SUPPORTS,
        created_at=CREATED_AT,
    )

    assert validate(encode_transaction(signed_transaction((invalid_relation,))), ledger).code is (
        TransactionCode.MISSING_REFERENCE
    )


@pytest.mark.parametrize("chain_id", ["", " "])
def test_validator_requires_a_nonblank_chain_id(chain_id: str) -> None:
    with pytest.raises(ValueError, match="expected_chain_id"):
        TransactionValidator(expected_chain_id=chain_id)
