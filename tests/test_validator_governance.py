# Verifies threshold authorization and canonical validator-governance transactions.

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.node import (
    GovernanceDecision,
    ValidatorGovernanceConfig,
    ValidatorGovernanceState,
)
from discovery_net.wire import (
    CodecError,
    SignedValidatorSetChange,
    ValidatorMembershipChange,
    ValidatorMembershipOperation,
    ValidatorSetChange,
    approve_validator_set_change,
    decode_validator_set_change,
    encode_validator_set_change,
)

CHAIN_ID = "discovery-governance-test"
GOVERNANCE_KEYS = tuple(
    Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32) for value in (1, 2, 3)
)
VALIDATOR_KEYS = tuple(
    Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32) for value in (11, 12, 13)
)


def public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def governance_state() -> ValidatorGovernanceState:
    return ValidatorGovernanceConfig(
        member_public_keys=tuple(sorted(public_key(key) for key in GOVERNANCE_KEYS)),
        approval_threshold=2,
        validator_power=10,
    ).initial_state(validator_public_keys=(public_key(VALIDATOR_KEYS[0]),))


def signed_change(
    *,
    sequence: int = 1,
    operation: ValidatorMembershipOperation = ValidatorMembershipOperation.ADD,
    validator_key: Ed25519PrivateKey = VALIDATOR_KEYS[1],
    governance_keys: tuple[Ed25519PrivateKey, ...] = GOVERNANCE_KEYS[:2],
    chain_id: str = CHAIN_ID,
) -> SignedValidatorSetChange:
    change = ValidatorSetChange(
        chain_id=chain_id,
        sequence=sequence,
        changes=(
            ValidatorMembershipChange(
                public_key=public_key(validator_key),
                operation=operation,
            ),
        ),
    )
    return SignedValidatorSetChange(
        change=change,
        approvals=tuple(
            sorted(
                (approve_validator_set_change(change, key) for key in governance_keys),
                key=lambda approval: approval.signer_public_key,
            )
        ),
    )


def test_threshold_change_round_trips_and_adds_equal_power() -> None:
    state = governance_state()
    transaction = signed_change()

    encoded = encode_validator_set_change(transaction)
    decoded = decode_validator_set_change(encoded)
    decision, transition = state.evaluate(decoded, expected_chain_id=CHAIN_ID)

    assert decoded == transaction
    assert decision is GovernanceDecision.ACCEPTED
    assert transition is not None
    assert transition.state.sequence == 1
    assert transition.state.validator_public_keys == tuple(
        sorted((public_key(VALIDATOR_KEYS[0]), public_key(VALIDATOR_KEYS[1])))
    )
    assert transition.validator_updates[0].voting_power == 10


def test_removal_emits_zero_power_and_never_allows_an_empty_set() -> None:
    state = governance_state()
    remove = signed_change(
        operation=ValidatorMembershipOperation.REMOVE,
        validator_key=VALIDATOR_KEYS[0],
    )

    decision, transition = state.evaluate(remove, expected_chain_id=CHAIN_ID)

    assert decision is GovernanceDecision.INVALID_CHANGE
    assert transition is None


@pytest.mark.parametrize(
    ("transaction", "expected"),
    [
        (signed_change(governance_keys=GOVERNANCE_KEYS[:1]), GovernanceDecision.UNAUTHORIZED),
        (signed_change(sequence=2), GovernanceDecision.INVALID_SEQUENCE),
        (signed_change(chain_id="another-chain"), GovernanceDecision.WRONG_CHAIN),
    ],
)
def test_governance_rejects_insufficient_or_misbound_approval(
    transaction: SignedValidatorSetChange,
    expected: GovernanceDecision,
) -> None:
    decision, transition = governance_state().evaluate(
        transaction,
        expected_chain_id=CHAIN_ID,
    )

    assert decision is expected
    assert transition is None


def test_governance_rejects_a_tampered_approval() -> None:
    transaction = signed_change()
    approvals = (
        replace(transaction.approvals[0], signature=bytes(64)),
        transaction.approvals[1],
    )
    tampered = replace(
        transaction,
        approvals=tuple(sorted(approvals, key=lambda item: item.signer_public_key)),
    )

    decision, transition = governance_state().evaluate(tampered, expected_chain_id=CHAIN_ID)

    assert decision is GovernanceDecision.INVALID_SIGNATURE
    assert transition is None


def test_governance_wire_format_rejects_noncanonical_json() -> None:
    encoded = encode_validator_set_change(signed_change())

    with pytest.raises(CodecError, match="canonical"):
        decode_validator_set_change(encoded + b" ")
