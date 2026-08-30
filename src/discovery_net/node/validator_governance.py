# Defines deterministic threshold governance over CometBFT validator membership.

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import Final

from discovery_net.cometbft_limits import (
    MAX_TOTAL_VOTING_POWER,
    MAX_VALIDATORS,
)
from discovery_net.wire.envelope import PUBLIC_KEY_LENGTH, _require_bytes
from discovery_net.wire.validator_governance import (
    SignedValidatorSetChange,
    ValidatorMembershipOperation,
)
from discovery_net.wire.validator_governance_signing import (
    verify_validator_set_change_approval,
)

_GOVERNANCE_HASH_DOMAIN: Final = b"discovery-net:validator-governance:\x00"


class GovernanceDecision(StrEnum):
    """The deterministic result of evaluating a validator-set change."""

    ACCEPTED = "accepted"
    WRONG_CHAIN = "wrong_chain"
    INVALID_SEQUENCE = "invalid_sequence"
    UNAUTHORIZED = "unauthorized"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_CHANGE = "invalid_change"


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorPowerUpdate:
    """The validator public key and power returned to CometBFT."""

    public_key: bytes
    voting_power: int

    def __post_init__(self) -> None:
        _require_bytes(self.public_key, "public_key", PUBLIC_KEY_LENGTH)
        _require_voting_power(self.voting_power, allow_zero=True)


@dataclass(frozen=True, slots=True, kw_only=True)
class _ValidatorGovernanceTransition:
    """The accepted next governance state and its CometBFT updates."""

    state: ValidatorGovernanceState
    validator_updates: tuple[ValidatorPowerUpdate, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceConfig:
    """The immutable threshold policy chosen while forming a new network."""

    member_public_keys: tuple[bytes, ...]
    approval_threshold: int
    validator_power: int

    def __post_init__(self) -> None:
        _require_public_key_set(self.member_public_keys, "member_public_keys")
        if not self.member_public_keys:
            raise ValueError("member_public_keys must not be empty")
        if not isinstance(self.approval_threshold, int) or isinstance(
            self.approval_threshold, bool
        ):
            raise TypeError("approval_threshold must be an integer")
        if not 1 <= self.approval_threshold <= len(self.member_public_keys):
            raise ValueError("approval_threshold must be supported by the governance members")
        _require_voting_power(self.validator_power)

    def initial_state(
        self,
        *,
        validator_public_keys: tuple[bytes, ...],
    ) -> ValidatorGovernanceState:
        """Bind this policy to the validator set placed in genesis."""
        return ValidatorGovernanceState(
            member_public_keys=self.member_public_keys,
            approval_threshold=self.approval_threshold,
            validator_power=self.validator_power,
            validator_public_keys=tuple(sorted(validator_public_keys)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceState:
    """The deterministic governance policy and current validator membership."""

    member_public_keys: tuple[bytes, ...]
    approval_threshold: int
    validator_power: int
    validator_public_keys: tuple[bytes, ...]
    sequence: int = 0

    def __post_init__(self) -> None:
        _require_public_key_set(self.member_public_keys, "member_public_keys")
        _require_public_key_set(self.validator_public_keys, "validator_public_keys")
        if not self.member_public_keys:
            raise ValueError("member_public_keys must not be empty")
        if not self.validator_public_keys:
            raise ValueError("validator_public_keys must not be empty")
        if not isinstance(self.approval_threshold, int) or isinstance(
            self.approval_threshold, bool
        ):
            raise TypeError("approval_threshold must be an integer")
        if not 1 <= self.approval_threshold <= len(self.member_public_keys):
            raise ValueError("approval_threshold must be supported by the governance members")
        _require_voting_power(self.validator_power)
        if len(self.validator_public_keys) > MAX_VALIDATORS:
            raise ValueError("validator_public_keys exceed the CometBFT validator limit")
        if len(self.validator_public_keys) * self.validator_power > MAX_TOTAL_VOTING_POWER:
            raise ValueError("validator voting power exceeds the CometBFT total-power limit")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise TypeError("sequence must be an integer")
        if not 0 <= self.sequence <= (1 << 63) - 1:
            raise ValueError("sequence must be a nonnegative signed 64-bit integer")

    def evaluate(
        self,
        transaction: SignedValidatorSetChange,
        *,
        expected_chain_id: str,
    ) -> tuple[GovernanceDecision, _ValidatorGovernanceTransition | None]:
        """Validate and, when accepted, derive one immutable membership transition."""
        if not isinstance(transaction, SignedValidatorSetChange):
            raise TypeError("transaction must be a SignedValidatorSetChange")
        if transaction.change.chain_id != expected_chain_id:
            return GovernanceDecision.WRONG_CHAIN, None
        if transaction.change.sequence != self.sequence + 1:
            return GovernanceDecision.INVALID_SEQUENCE, None

        members = set(self.member_public_keys)
        if any(approval.signer_public_key not in members for approval in transaction.approvals):
            return GovernanceDecision.UNAUTHORIZED, None
        if any(
            not verify_validator_set_change_approval(transaction.change, approval)
            for approval in transaction.approvals
        ):
            return GovernanceDecision.INVALID_SIGNATURE, None
        if len(transaction.approvals) < self.approval_threshold:
            return GovernanceDecision.UNAUTHORIZED, None

        validators = set(self.validator_public_keys)
        for change in transaction.change.changes:
            if change.operation is ValidatorMembershipOperation.ADD:
                if change.public_key in validators:
                    return GovernanceDecision.INVALID_CHANGE, None
                validators.add(change.public_key)
            else:
                if change.public_key not in validators:
                    return GovernanceDecision.INVALID_CHANGE, None
                validators.remove(change.public_key)

        if not validators or len(validators) > MAX_VALIDATORS:
            return GovernanceDecision.INVALID_CHANGE, None
        if len(validators) * self.validator_power > MAX_TOTAL_VOTING_POWER:
            return GovernanceDecision.INVALID_CHANGE, None

        state = replace(
            self,
            validator_public_keys=tuple(sorted(validators)),
            sequence=transaction.change.sequence,
        )
        updates = tuple(
            ValidatorPowerUpdate(
                public_key=change.public_key,
                voting_power=(
                    self.validator_power
                    if change.operation is ValidatorMembershipOperation.ADD
                    else 0
                ),
            )
            for change in transaction.change.changes
        )
        return (
            GovernanceDecision.ACCEPTED,
            _ValidatorGovernanceTransition(state=state, validator_updates=updates),
        )

    def state_hash(self) -> bytes:
        """Return the deterministic commitment to governance policy and membership."""
        from discovery_net.node.validator_governance_codec import (
            encode_validator_governance_state,
        )

        return sha256(_GOVERNANCE_HASH_DOMAIN + encode_validator_governance_state(self)).digest()


def _require_public_key_set(values: tuple[bytes, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for value in values:
        _require_bytes(value, field_name, PUBLIC_KEY_LENGTH)
    if values != tuple(sorted(values)):
        raise ValueError(f"{field_name} must be ordered")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicates")


def _require_voting_power(value: int, *, allow_zero: bool = False) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("voting power must be an integer")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= MAX_TOTAL_VOTING_POWER:
        raise ValueError("voting power is outside the CometBFT range")
