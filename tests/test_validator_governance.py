# Verifies dynamic validator admission, asynchronous approvals, and canonical encoding.

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.node import (
    GovernanceDecision,
    ValidatorGovernanceConfig,
    ValidatorGovernanceState,
)
from discovery_net.node.validator_governance_codec import (
    decode_validator_governance_state,
    encode_validator_governance_state,
)
from discovery_net.wire import (
    CodecError,
    ValidatorMembershipOperation,
    ValidatorMembershipProposal,
    ValidatorOperator,
    approve_validator_proposal,
    complete_validator_nomination,
    decode_consensus_validator_nomination,
    decode_validator_governance_transaction,
    encode_consensus_validator_nomination,
    encode_validator_governance_transaction,
    nominate_validator,
    nominate_validator_consensus,
    propose_validator_membership,
    validator_proposal_id,
)

CHAIN_ID = "discovery-governance-test"


def _key(value: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([value]) * 32)


CONSENSUS_KEYS = tuple(_key(value) for value in (11, 12, 13, 14, 15))
GOVERNANCE_KEYS = tuple(_key(value) for value in (31, 32, 33, 34, 35))


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _operators(count: int = 4) -> tuple[ValidatorOperator, ...]:
    return tuple(
        sorted(
            (
                ValidatorOperator(
                    consensus_public_key=_public_key(CONSENSUS_KEYS[index]),
                    governance_public_key=_public_key(GOVERNANCE_KEYS[index]),
                )
                for index in range(count)
            ),
            key=lambda operator: operator.consensus_public_key,
        )
    )


def _state(count: int = 4) -> ValidatorGovernanceState:
    return ValidatorGovernanceConfig(
        operators=_operators(count),
        validator_power=10,
    ).initial_state()


def _governance_private_key(public_key: bytes) -> Ed25519PrivateKey:
    return next(key for key in GOVERNANCE_KEYS if _public_key(key) == public_key)


def _addition(*, sponsor_public_key: bytes | None = None) -> ValidatorMembershipProposal:
    nomination = nominate_validator(
        chain_id=CHAIN_ID,
        consensus_private_key=CONSENSUS_KEYS[4],
        governance_private_key=GOVERNANCE_KEYS[4],
    )
    sponsor = next(
        operator
        for operator in _operators()
        if sponsor_public_key is None or operator.governance_public_key == sponsor_public_key
    )
    return propose_validator_membership(
        chain_id=CHAIN_ID,
        operation=ValidatorMembershipOperation.ADD,
        operator=nomination.operator,
        sponsor_private_key=_governance_private_key(sponsor.governance_public_key),
        nomination=nomination,
    )


def test_addition_requires_async_supermajority_and_activates_two_heights_later() -> None:
    state = _state()
    proposal = _addition()
    proposal_id = validator_proposal_id(proposal)

    decision, transition = state.evaluate(proposal, expected_chain_id=CHAIN_ID, height=10)

    assert decision is GovernanceDecision.ACCEPTED
    assert transition is not None
    assert transition.validator_updates == ()
    assert transition.state.approval_threshold == 3
    assert transition.state.proposals[0].approvals == (proposal.sponsor_public_key,)

    state = transition.state
    remaining = tuple(
        operator
        for operator in state.operators
        if operator.governance_public_key != proposal.sponsor_public_key
    )
    first = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=proposal_id,
        private_key=_governance_private_key(remaining[0].governance_public_key),
    )
    decision, transition = state.evaluate(first, expected_chain_id=CHAIN_ID, height=11)
    assert decision is GovernanceDecision.ACCEPTED
    assert transition is not None
    assert transition.validator_updates == ()

    second = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=proposal_id,
        private_key=_governance_private_key(remaining[1].governance_public_key),
    )
    decision, transition = transition.state.evaluate(
        second,
        expected_chain_id=CHAIN_ID,
        height=12,
    )

    assert decision is GovernanceDecision.ACCEPTED
    assert transition is not None
    assert transition.validator_updates[0].public_key == proposal.operator.consensus_public_key
    assert transition.validator_updates[0].voting_power == 10
    assert transition.state.scheduled_change is not None
    assert transition.state.scheduled_change.effective_height == 14
    assert len(transition.state.operators) == 4
    assert len(transition.state.advance_to_height(13).operators) == 4
    active = transition.state.advance_to_height(14)
    assert len(active.operators) == 5
    assert proposal.operator in active.operators
    assert active.approval_threshold == 4
    assert active.proposals == ()


def test_only_current_operators_can_sponsor_or_approve_once() -> None:
    state = _state()
    proposal = _addition()
    _, transition = state.evaluate(proposal, expected_chain_id=CHAIN_ID, height=1)
    assert transition is not None
    state = transition.state

    duplicate, no_transition = state.evaluate(proposal, expected_chain_id=CHAIN_ID, height=2)
    assert duplicate is GovernanceDecision.DUPLICATE
    assert no_transition is None

    sponsor_approval = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=validator_proposal_id(proposal),
        private_key=_governance_private_key(proposal.sponsor_public_key),
    )
    duplicate, no_transition = state.evaluate(
        sponsor_approval,
        expected_chain_id=CHAIN_ID,
        height=2,
    )
    assert duplicate is GovernanceDecision.DUPLICATE
    assert no_transition is None

    outsider = approve_validator_proposal(
        chain_id=CHAIN_ID,
        proposal_id=validator_proposal_id(proposal),
        private_key=_key(99),
    )
    unauthorized, no_transition = state.evaluate(
        outsider,
        expected_chain_id=CHAIN_ID,
        height=2,
    )
    assert unauthorized is GovernanceDecision.UNAUTHORIZED
    assert no_transition is None


def test_signatures_chain_binding_and_candidate_consent_are_enforced() -> None:
    state = _state()
    proposal = _addition()

    tampered = replace(proposal, sponsor_signature=bytes(64))
    decision, transition = state.evaluate(tampered, expected_chain_id=CHAIN_ID, height=1)
    assert decision is GovernanceDecision.INVALID_SIGNATURE
    assert transition is None

    assert proposal.nomination is not None
    wrong_chain = replace(
        proposal,
        chain_id="another-chain",
        nomination=replace(proposal.nomination, chain_id="another-chain"),
    )
    decision, transition = state.evaluate(wrong_chain, expected_chain_id=CHAIN_ID, height=1)
    assert decision is GovernanceDecision.WRONG_CHAIN
    assert transition is None

    bad_nomination = replace(proposal.nomination, consensus_signature=bytes(64))
    tampered = replace(proposal, nomination=bad_nomination)
    decision, transition = state.evaluate(tampered, expected_chain_id=CHAIN_ID, height=1)
    assert decision is GovernanceDecision.INVALID_SIGNATURE
    assert transition is None


def test_scheduled_change_serializes_membership_updates_without_blocking_blocks() -> None:
    state = _state(count=1)
    proposal = _addition(sponsor_public_key=state.operators[0].governance_public_key)
    decision, transition = state.evaluate(proposal, expected_chain_id=CHAIN_ID, height=7)
    assert decision is GovernanceDecision.ACCEPTED
    assert transition is not None
    assert transition.state.scheduled_change is not None

    decision, no_transition = transition.state.evaluate(
        proposal,
        expected_chain_id=CHAIN_ID,
        height=8,
    )
    assert decision is GovernanceDecision.BUSY
    assert no_transition is None


def test_removal_needs_the_same_supermajority_and_cannot_remove_the_last_validator() -> None:
    state = _state(count=3)
    target = state.operators[-1]
    sponsor = state.operators[0]
    proposal = propose_validator_membership(
        chain_id=CHAIN_ID,
        operation=ValidatorMembershipOperation.REMOVE,
        operator=target,
        sponsor_private_key=_governance_private_key(sponsor.governance_public_key),
    )
    _, transition = state.evaluate(proposal, expected_chain_id=CHAIN_ID, height=20)
    assert transition is not None
    state = transition.state
    for operator in state.operators:
        if operator.governance_public_key == sponsor.governance_public_key:
            continue
        approval = approve_validator_proposal(
            chain_id=CHAIN_ID,
            proposal_id=validator_proposal_id(proposal),
            private_key=_governance_private_key(operator.governance_public_key),
        )
        decision, transition = state.evaluate(
            approval,
            expected_chain_id=CHAIN_ID,
            height=21,
        )
        assert decision is GovernanceDecision.ACCEPTED
        assert transition is not None
        state = transition.state
    assert transition.validator_updates[0].public_key == target.consensus_public_key
    assert transition.validator_updates[0].voting_power == 0
    assert target not in state.advance_to_height(23).operators

    singleton = _state(count=1)
    only = singleton.operators[0]
    invalid = propose_validator_membership(
        chain_id=CHAIN_ID,
        operation=ValidatorMembershipOperation.REMOVE,
        operator=only,
        sponsor_private_key=_governance_private_key(only.governance_public_key),
    )
    decision, no_transition = singleton.evaluate(
        invalid,
        expected_chain_id=CHAIN_ID,
        height=1,
    )
    assert decision is GovernanceDecision.INVALID_CHANGE
    assert no_transition is None


def test_governance_transactions_and_state_are_canonical() -> None:
    proposal = _addition()
    encoded = encode_validator_governance_transaction(proposal)

    assert decode_validator_governance_transaction(encoded) == proposal
    with pytest.raises(CodecError, match="canonical"):
        decode_validator_governance_transaction(encoded + b" ")

    state = _state()
    _, transition = state.evaluate(proposal, expected_chain_id=CHAIN_ID, height=1)
    assert transition is not None
    encoded_state = encode_validator_governance_state(transition.state)
    assert decode_validator_governance_state(encoded_state) == transition.state
    with pytest.raises(CodecError, match="canonical"):
        decode_validator_governance_state(encoded_state + b" ")


def test_candidate_keys_can_sign_a_nomination_without_private_key_colocation() -> None:
    consensus_nomination = nominate_validator_consensus(
        chain_id=CHAIN_ID,
        consensus_private_key=CONSENSUS_KEYS[4],
        governance_public_key=_public_key(GOVERNANCE_KEYS[4]),
    )
    encoded = encode_consensus_validator_nomination(consensus_nomination)
    decoded = decode_consensus_validator_nomination(encoded)

    completed = complete_validator_nomination(
        nomination=decoded,
        governance_private_key=GOVERNANCE_KEYS[4],
    )

    assert completed.consensus_signature == consensus_nomination.consensus_signature
    assert completed.operator == consensus_nomination.operator
    with pytest.raises(ValueError, match="does not match"):
        complete_validator_nomination(
            nomination=decoded,
            governance_private_key=_key(99),
        )
