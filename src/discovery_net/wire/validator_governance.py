# Defines signed validator-membership changes authorized by network governance keys.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from discovery_net.wire.envelope import PUBLIC_KEY_LENGTH, SIGNATURE_LENGTH, _require_bytes


class ValidatorMembershipOperation(StrEnum):
    """A supported change to the CometBFT validator set."""

    ADD = "add"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorMembershipChange:
    """Adds or removes one Ed25519 validator public key."""

    public_key: bytes
    operation: ValidatorMembershipOperation

    def __post_init__(self) -> None:
        _require_bytes(self.public_key, "public_key", PUBLIC_KEY_LENGTH)
        if not isinstance(self.operation, ValidatorMembershipOperation):
            raise TypeError("operation must be a ValidatorMembershipOperation")


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorSetChange:
    """The validator-membership transition approved by governance members."""

    chain_id: str
    sequence: int
    changes: tuple[ValidatorMembershipChange, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, str):
            raise TypeError("chain_id must be a string")
        if not self.chain_id.strip():
            raise ValueError("chain_id must not be blank")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise TypeError("sequence must be an integer")
        if not 1 <= self.sequence <= (1 << 63) - 1:
            raise ValueError("sequence must be between 1 and the maximum signed 64-bit integer")
        if not isinstance(self.changes, tuple):
            raise TypeError("changes must be a tuple")
        if not self.changes:
            raise ValueError("changes must not be empty")
        if any(not isinstance(change, ValidatorMembershipChange) for change in self.changes):
            raise TypeError("changes must contain ValidatorMembershipChange values")
        public_keys = tuple(change.public_key for change in self.changes)
        if public_keys != tuple(sorted(public_keys)):
            raise ValueError("changes must be ordered by public key")
        if len(set(public_keys)) != len(public_keys):
            raise ValueError("changes must not contain duplicate public keys")


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernanceApproval:
    """One governance member's signature over a validator-set change."""

    signer_public_key: bytes
    signature: bytes

    def __post_init__(self) -> None:
        _require_bytes(self.signer_public_key, "signer_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.signature, "signature", SIGNATURE_LENGTH)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedValidatorSetChange:
    """A validator-set change carrying its threshold governance approvals."""

    change: ValidatorSetChange
    approvals: tuple[GovernanceApproval, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.change, ValidatorSetChange):
            raise TypeError("change must be a ValidatorSetChange")
        if not isinstance(self.approvals, tuple):
            raise TypeError("approvals must be a tuple")
        if not self.approvals:
            raise ValueError("approvals must not be empty")
        if any(not isinstance(approval, GovernanceApproval) for approval in self.approvals):
            raise TypeError("approvals must contain GovernanceApproval values")
        public_keys = tuple(approval.signer_public_key for approval in self.approvals)
        if public_keys != tuple(sorted(public_keys)):
            raise ValueError("approvals must be ordered by signer public key")
        if len(set(public_keys)) != len(public_keys):
            raise ValueError("approvals must not contain duplicate signers")
