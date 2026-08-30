# Defines validator-membership proposals and asynchronous operator approvals.

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from discovery_net.wire.envelope import PUBLIC_KEY_LENGTH, SIGNATURE_LENGTH, _require_bytes

PROPOSAL_ID_LENGTH = 32


class ValidatorMembershipOperation(StrEnum):
    """A supported change to the CometBFT validator set."""

    ADD = "add"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorOperator:
    """The separate consensus and governance identities of one validator operator."""

    consensus_public_key: bytes
    governance_public_key: bytes

    def __post_init__(self) -> None:
        _require_bytes(self.consensus_public_key, "consensus_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.governance_public_key, "governance_public_key", PUBLIC_KEY_LENGTH)
        if self.consensus_public_key == self.governance_public_key:
            raise ValueError("consensus and governance public keys must be distinct")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusValidatorNomination:
    """A candidate consensus key's approval of its proposed governance identity."""

    chain_id: str
    operator: ValidatorOperator
    consensus_signature: bytes

    def __post_init__(self) -> None:
        _require_chain_id(self.chain_id)
        if not isinstance(self.operator, ValidatorOperator):
            raise TypeError("operator must be a ValidatorOperator")
        _require_bytes(self.consensus_signature, "consensus_signature", SIGNATURE_LENGTH)


@dataclass(frozen=True, slots=True, kw_only=True)
class SignedValidatorNomination:
    """A candidate's dual-key proof that it consents to validator admission."""

    chain_id: str
    operator: ValidatorOperator
    consensus_signature: bytes
    governance_signature: bytes

    def __post_init__(self) -> None:
        _require_chain_id(self.chain_id)
        if not isinstance(self.operator, ValidatorOperator):
            raise TypeError("operator must be a ValidatorOperator")
        _require_bytes(self.consensus_signature, "consensus_signature", SIGNATURE_LENGTH)
        _require_bytes(self.governance_signature, "governance_signature", SIGNATURE_LENGTH)


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorMembershipProposal:
    """One current validator's sponsored membership proposal and first approval."""

    chain_id: str
    operation: ValidatorMembershipOperation
    operator: ValidatorOperator
    sponsor_public_key: bytes
    sponsor_signature: bytes
    nomination: SignedValidatorNomination | None = None

    def __post_init__(self) -> None:
        _require_chain_id(self.chain_id)
        if not isinstance(self.operation, ValidatorMembershipOperation):
            raise TypeError("operation must be a ValidatorMembershipOperation")
        if not isinstance(self.operator, ValidatorOperator):
            raise TypeError("operator must be a ValidatorOperator")
        _require_bytes(self.sponsor_public_key, "sponsor_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.sponsor_signature, "sponsor_signature", SIGNATURE_LENGTH)
        if self.operation is ValidatorMembershipOperation.ADD:
            if self.nomination is None:
                raise ValueError("an add proposal requires a signed nomination")
            if self.nomination.chain_id != self.chain_id:
                raise ValueError("nomination and proposal must use one chain")
            if self.nomination.operator != self.operator:
                raise ValueError("nomination and proposal must identify one operator")
        elif self.nomination is not None:
            raise ValueError("a remove proposal must not contain a nomination")


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorProposalApproval:
    """One current validator operator's approval of a committed proposal."""

    chain_id: str
    proposal_id: bytes
    signer_public_key: bytes
    signature: bytes

    def __post_init__(self) -> None:
        _require_chain_id(self.chain_id)
        _require_bytes(self.proposal_id, "proposal_id", PROPOSAL_ID_LENGTH)
        _require_bytes(self.signer_public_key, "signer_public_key", PUBLIC_KEY_LENGTH)
        _require_bytes(self.signature, "signature", SIGNATURE_LENGTH)


type ValidatorGovernanceTransaction = ValidatorMembershipProposal | ValidatorProposalApproval


def _require_chain_id(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError("chain_id must be a string")
    if not value.strip():
        raise ValueError("chain_id must not be blank")
