# Defines dynamic equal-power governance over CometBFT validator membership.

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import Final

from discovery_net.cometbft_limits import MAX_TOTAL_VOTING_POWER, MAX_VALIDATORS
from discovery_net.wire.envelope import PUBLIC_KEY_LENGTH, _require_bytes
from discovery_net.wire.validator_governance import (
    PROPOSAL_ID_LENGTH,
    ValidatorGovernanceTransaction,
    ValidatorMembershipOperation,
    ValidatorMembershipProposal,
    ValidatorOperator,
    ValidatorProposalApproval,
)
from discovery_net.wire.validator_governance_signing import (
    validator_proposal_id,
    verify_validator_proposal,
    verify_validator_proposal_approval,
)

_GOVERNANCE_HASH_DOMAIN: Final = b"discovery-net:validator-governance:\x00"
_VALIDATOR_SET_HASH_DOMAIN: Final = b"discovery-net:validator-set:\x00"
_VALIDATOR_UPDATE_DELAY: Final = 2
_MAX_INT64: Final = (1 << 63) - 1


class GovernanceDecision(StrEnum):
    """The deterministic result of evaluating one governance transaction."""

    ACCEPTED = "accepted"
    WRONG_CHAIN = "wrong_chain"
    BUSY = "busy"
    UNAUTHORIZED = "unauthorized"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_CHANGE = "invalid_change"
    DUPLICATE = "duplicate"
    UNKNOWN_PROPOSAL = "unknown_proposal"


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorPowerUpdate:
    """The validator public key and power returned to CometBFT."""

    public_key: bytes
    voting_power: int

    def __post_init__(self) -> None:
        _require_bytes(self.public_key, "public_key", PUBLIC_KEY_LENGTH)
        _require_voting_power(self.voting_power, allow_zero=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorProposalRecord:
    """A sponsored proposal and its distinct asynchronous approvals."""

    proposal_id: bytes
    proposal: ValidatorMembershipProposal
    validator_set_hash: bytes
    approvals: tuple[bytes, ...]

    def __post_init__(self) -> None:
        _require_bytes(self.proposal_id, "proposal_id", PROPOSAL_ID_LENGTH)
        if not isinstance(self.proposal, ValidatorMembershipProposal):
            raise TypeError("proposal must be a ValidatorMembershipProposal")
        _require_bytes(self.validator_set_hash, "validator_set_hash", 32)
        _require_public_key_set(self.approvals, "approvals", allow_empty=False)
        if self.proposal.sponsor_public_key not in self.approvals:
            raise ValueError("proposal approvals must include the sponsor")


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledValidatorChange:
    """A threshold-approved change awaiting CometBFT's activation height."""

    proposal_id: bytes
    operation: ValidatorMembershipOperation
    operator: ValidatorOperator
    effective_height: int

    def __post_init__(self) -> None:
        _require_bytes(self.proposal_id, "proposal_id", PROPOSAL_ID_LENGTH)
        if not isinstance(self.operation, ValidatorMembershipOperation):
            raise TypeError("operation must be a ValidatorMembershipOperation")
        if not isinstance(self.operator, ValidatorOperator):
            raise TypeError("operator must be a ValidatorOperator")
        _require_height(self.effective_height, "effective_height")


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceTransition:
    """The accepted next governance state and any CometBFT power update."""

    state: ValidatorGovernanceState
    validator_updates: tuple[ValidatorPowerUpdate, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceConfig:
    """The equal-power validator operators embedded in a newly formed genesis."""

    operators: tuple[ValidatorOperator, ...]
    validator_power: int

    def __post_init__(self) -> None:
        _require_operator_set(self.operators)
        if not self.operators:
            raise ValueError("operators must not be empty")
        _require_voting_power(self.validator_power)
        _require_capacity(self.operators, self.validator_power)

    def initial_state(self) -> ValidatorGovernanceState:
        """Return the immutable dynamic-governance state placed in genesis."""
        return ValidatorGovernanceState(
            operators=self.operators,
            validator_power=self.validator_power,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceState:
    """The current operators, pending proposals, and one scheduled membership change."""

    operators: tuple[ValidatorOperator, ...]
    validator_power: int
    proposals: tuple[ValidatorProposalRecord, ...] = ()
    scheduled_change: ScheduledValidatorChange | None = None

    def __post_init__(self) -> None:
        _require_operator_set(self.operators)
        if not self.operators:
            raise ValueError("operators must not be empty")
        _require_voting_power(self.validator_power)
        _require_capacity(self.operators, self.validator_power)
        if not isinstance(self.proposals, tuple) or any(
            not isinstance(proposal, ValidatorProposalRecord) for proposal in self.proposals
        ):
            raise TypeError("proposals must contain ValidatorProposalRecord values")
        proposal_ids = tuple(proposal.proposal_id for proposal in self.proposals)
        if proposal_ids != tuple(sorted(proposal_ids)) or len(set(proposal_ids)) != len(
            proposal_ids
        ):
            raise ValueError("proposals must be uniquely ordered by proposal ID")
        if self.scheduled_change is not None and not isinstance(
            self.scheduled_change, ScheduledValidatorChange
        ):
            raise TypeError("scheduled_change must be a ScheduledValidatorChange or None")
        governance_keys = {operator.governance_public_key for operator in self.operators}
        validator_set_hash = self.validator_set_hash()
        for record in self.proposals:
            if record.proposal_id != validator_proposal_id(record.proposal):
                raise ValueError("stored proposal ID does not match its signed proposal")
            if not verify_validator_proposal(record.proposal):
                raise ValueError("stored validator proposal has an invalid signature")
            if record.validator_set_hash != validator_set_hash:
                raise ValueError("stored proposal is not bound to the current validator set")
            if not set(record.approvals).issubset(governance_keys):
                raise ValueError("stored proposal approvals must belong to current operators")
            if not self._valid_change(record.proposal):
                raise ValueError("stored validator proposal describes an invalid change")
        if self.scheduled_change is not None:
            scheduled_record = next(
                (
                    record
                    for record in self.proposals
                    if record.proposal_id == self.scheduled_change.proposal_id
                ),
                None,
            )
            if scheduled_record is None:
                raise ValueError("scheduled change must reference a pending proposal")
            if len(scheduled_record.approvals) < self.approval_threshold:
                raise ValueError("scheduled change must have a supermajority approval")
            if (
                scheduled_record.proposal.operation != self.scheduled_change.operation
                or scheduled_record.proposal.operator != self.scheduled_change.operator
            ):
                raise ValueError("scheduled change must match its approved proposal")

    @property
    def approval_threshold(self) -> int:
        """Return the strict greater-than-two-thirds threshold for the current set."""
        return (2 * len(self.operators)) // 3 + 1

    def validator_set_hash(self) -> bytes:
        """Commit to the exact consensus/governance operator mapping and equal power."""
        encoded = len(self.operators).to_bytes(8, "big") + self.validator_power.to_bytes(8, "big")
        for operator in self.operators:
            encoded += operator.consensus_public_key + operator.governance_public_key
        return sha256(_VALIDATOR_SET_HASH_DOMAIN + encoded).digest()

    def advance_to_height(self, height: int) -> ValidatorGovernanceState:
        """Activate a previously emitted update at CometBFT's deterministic height."""
        _require_height(height, "height")
        scheduled = self.scheduled_change
        if scheduled is None or height < scheduled.effective_height:
            return self
        operators = set(self.operators)
        if scheduled.operation is ValidatorMembershipOperation.ADD:
            operators.add(scheduled.operator)
        else:
            operators.remove(scheduled.operator)
        return ValidatorGovernanceState(
            operators=tuple(sorted(operators, key=_operator_sort_key)),
            validator_power=self.validator_power,
            proposals=(),
        )

    def evaluate(
        self,
        transaction: ValidatorGovernanceTransaction,
        *,
        expected_chain_id: str,
        height: int,
    ) -> tuple[GovernanceDecision, ValidatorGovernanceTransition | None]:
        """Validate and derive one proposal or approval transition."""
        _require_height(height, "height")
        if not isinstance(transaction, ValidatorMembershipProposal | ValidatorProposalApproval):
            raise TypeError("transaction must be a validator-governance transaction")
        if transaction.chain_id != expected_chain_id:
            return GovernanceDecision.WRONG_CHAIN, None
        if self.scheduled_change is not None:
            return GovernanceDecision.BUSY, None
        if isinstance(transaction, ValidatorMembershipProposal):
            return self._evaluate_proposal(transaction, height=height)
        return self._evaluate_approval(transaction, height=height)

    def state_hash(self) -> bytes:
        """Return the deterministic commitment to all governance state."""
        from discovery_net.node.validator_governance_codec import (
            encode_validator_governance_state,
        )

        return sha256(_GOVERNANCE_HASH_DOMAIN + encode_validator_governance_state(self)).digest()

    def _evaluate_proposal(
        self,
        proposal: ValidatorMembershipProposal,
        *,
        height: int,
    ) -> tuple[GovernanceDecision, ValidatorGovernanceTransition | None]:
        governance_keys = {operator.governance_public_key for operator in self.operators}
        if proposal.sponsor_public_key not in governance_keys:
            return GovernanceDecision.UNAUTHORIZED, None
        if not verify_validator_proposal(proposal):
            return GovernanceDecision.INVALID_SIGNATURE, None
        proposal_id = validator_proposal_id(proposal)
        if any(record.proposal_id == proposal_id for record in self.proposals):
            return GovernanceDecision.DUPLICATE, None
        if not self._valid_change(proposal):
            return GovernanceDecision.INVALID_CHANGE, None

        record = ValidatorProposalRecord(
            proposal_id=proposal_id,
            proposal=proposal,
            validator_set_hash=self.validator_set_hash(),
            approvals=(proposal.sponsor_public_key,),
        )
        state = replace(
            self,
            proposals=tuple(sorted((*self.proposals, record), key=lambda value: value.proposal_id)),
        )
        return GovernanceDecision.ACCEPTED, state._schedule_if_approved(record, height=height)

    def _evaluate_approval(
        self,
        approval: ValidatorProposalApproval,
        *,
        height: int,
    ) -> tuple[GovernanceDecision, ValidatorGovernanceTransition | None]:
        record = next(
            (value for value in self.proposals if value.proposal_id == approval.proposal_id),
            None,
        )
        if record is None:
            return GovernanceDecision.UNKNOWN_PROPOSAL, None
        governance_keys = {operator.governance_public_key for operator in self.operators}
        if approval.signer_public_key not in governance_keys:
            return GovernanceDecision.UNAUTHORIZED, None
        if approval.signer_public_key in record.approvals:
            return GovernanceDecision.DUPLICATE, None
        if not verify_validator_proposal_approval(approval):
            return GovernanceDecision.INVALID_SIGNATURE, None

        updated_record = replace(
            record,
            approvals=tuple(sorted((*record.approvals, approval.signer_public_key))),
        )
        state = replace(
            self,
            proposals=tuple(
                updated_record if value.proposal_id == updated_record.proposal_id else value
                for value in self.proposals
            ),
        )
        return GovernanceDecision.ACCEPTED, state._schedule_if_approved(
            updated_record,
            height=height,
        )

    def _schedule_if_approved(
        self,
        record: ValidatorProposalRecord,
        *,
        height: int,
    ) -> ValidatorGovernanceTransition:
        if len(record.approvals) < self.approval_threshold:
            return ValidatorGovernanceTransition(state=self)
        if height > _MAX_INT64 - _VALIDATOR_UPDATE_DELAY:
            raise ValueError("height is too large to schedule validator activation")
        scheduled = ScheduledValidatorChange(
            proposal_id=record.proposal_id,
            operation=record.proposal.operation,
            operator=record.proposal.operator,
            effective_height=height + _VALIDATOR_UPDATE_DELAY,
        )
        voting_power = (
            self.validator_power
            if record.proposal.operation is ValidatorMembershipOperation.ADD
            else 0
        )
        return ValidatorGovernanceTransition(
            state=replace(self, scheduled_change=scheduled),
            validator_updates=(
                ValidatorPowerUpdate(
                    public_key=record.proposal.operator.consensus_public_key,
                    voting_power=voting_power,
                ),
            ),
        )

    def _valid_change(self, proposal: ValidatorMembershipProposal) -> bool:
        operator = proposal.operator
        if proposal.operation is ValidatorMembershipOperation.REMOVE:
            return operator in self.operators and len(self.operators) > 1
        if proposal.nomination is None:
            return False
        if operator in self.operators or len(self.operators) >= MAX_VALIDATORS:
            return False
        if any(
            operator.consensus_public_key == current.consensus_public_key
            or operator.governance_public_key == current.governance_public_key
            for current in self.operators
        ):
            return False
        return (len(self.operators) + 1) * self.validator_power <= MAX_TOTAL_VOTING_POWER


def _operator_sort_key(operator: ValidatorOperator) -> tuple[bytes, bytes]:
    return operator.consensus_public_key, operator.governance_public_key


def _require_operator_set(operators: tuple[ValidatorOperator, ...]) -> None:
    if not isinstance(operators, tuple):
        raise TypeError("operators must be a tuple")
    if any(not isinstance(operator, ValidatorOperator) for operator in operators):
        raise TypeError("operators must contain ValidatorOperator values")
    if operators != tuple(sorted(operators, key=_operator_sort_key)):
        raise ValueError("operators must be ordered by consensus public key")
    consensus_keys = tuple(operator.consensus_public_key for operator in operators)
    governance_keys = tuple(operator.governance_public_key for operator in operators)
    if len(set(consensus_keys)) != len(consensus_keys):
        raise ValueError("operators must not repeat consensus public keys")
    if len(set(governance_keys)) != len(governance_keys):
        raise ValueError("operators must not repeat governance public keys")


def _require_capacity(operators: tuple[ValidatorOperator, ...], power: int) -> None:
    if len(operators) > MAX_VALIDATORS:
        raise ValueError("operators exceed the CometBFT validator limit")
    if len(operators) * power > MAX_TOTAL_VOTING_POWER:
        raise ValueError("validator voting power exceeds the CometBFT total-power limit")


def _require_public_key_set(
    values: tuple[bytes, ...],
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for value in values:
        _require_bytes(value, field_name, PUBLIC_KEY_LENGTH)
    if not allow_empty and not values:
        raise ValueError(f"{field_name} must not be empty")
    if values != tuple(sorted(values)) or len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be uniquely ordered")


def _require_voting_power(value: int, *, allow_zero: bool = False) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("voting power must be an integer")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= MAX_TOTAL_VOTING_POWER:
        raise ValueError("voting power is outside the CometBFT range")


def _require_height(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if not 1 <= value <= _MAX_INT64:
        raise ValueError(f"{field_name} must be a positive signed 64-bit integer")
