# Creates and verifies validator-governance signatures.

from __future__ import annotations

from hashlib import sha256
from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.wire.validator_governance import (
    ConsensusValidatorNomination,
    SignedValidatorNomination,
    ValidatorMembershipOperation,
    ValidatorMembershipProposal,
    ValidatorOperator,
    ValidatorProposalApproval,
)
from discovery_net.wire.validator_governance_codec import (
    encode_approval_signing_payload,
    encode_nomination_signing_payload,
    encode_proposal_signing_payload,
    encode_validator_governance_transaction,
)

_NOMINATION_SIGNATURE_DOMAIN: Final = b"discovery-net:validator-nomination:\x00"
_PROPOSAL_SIGNATURE_DOMAIN: Final = b"discovery-net:validator-proposal:\x00"
_APPROVAL_SIGNATURE_DOMAIN: Final = b"discovery-net:validator-approval:\x00"
_PROPOSAL_ID_DOMAIN: Final = b"discovery-net:validator-proposal-id:\x00"


def nominate_validator(
    *,
    chain_id: str,
    consensus_private_key: Ed25519PrivateKey,
    governance_private_key: Ed25519PrivateKey,
) -> SignedValidatorNomination:
    """Create a nomination proving control of separate consensus and governance keys."""
    _require_private_key(consensus_private_key, "consensus_private_key")
    _require_private_key(governance_private_key, "governance_private_key")
    return complete_validator_nomination(
        nomination=nominate_validator_consensus(
            chain_id=chain_id,
            consensus_private_key=consensus_private_key,
            governance_public_key=_public_key(governance_private_key),
        ),
        governance_private_key=governance_private_key,
    )


def nominate_validator_consensus(
    *,
    chain_id: str,
    consensus_private_key: Ed25519PrivateKey,
    governance_public_key: bytes,
) -> ConsensusValidatorNomination:
    """Sign a nomination with the candidate key while governance remains offline."""
    _require_private_key(consensus_private_key, "consensus_private_key")
    operator = ValidatorOperator(
        consensus_public_key=_public_key(consensus_private_key),
        governance_public_key=governance_public_key,
    )
    message = _NOMINATION_SIGNATURE_DOMAIN + encode_nomination_signing_payload(
        chain_id=chain_id,
        operator=operator,
    )
    return ConsensusValidatorNomination(
        chain_id=chain_id,
        operator=operator,
        consensus_signature=consensus_private_key.sign(message),
    )


def complete_validator_nomination(
    *,
    nomination: ConsensusValidatorNomination,
    governance_private_key: Ed25519PrivateKey,
) -> SignedValidatorNomination:
    """Add the offline governance signature to a consensus-signed nomination."""
    if not isinstance(nomination, ConsensusValidatorNomination):
        raise TypeError("nomination must be a ConsensusValidatorNomination")
    _require_private_key(governance_private_key, "governance_private_key")
    if _public_key(governance_private_key) != nomination.operator.governance_public_key:
        raise ValueError("governance private key does not match the nominated operator")
    message = _NOMINATION_SIGNATURE_DOMAIN + encode_nomination_signing_payload(
        chain_id=nomination.chain_id,
        operator=nomination.operator,
    )
    try:
        Ed25519PublicKey.from_public_bytes(nomination.operator.consensus_public_key).verify(
            nomination.consensus_signature,
            message,
        )
    except (InvalidSignature, TypeError, ValueError) as error:
        raise ValueError("candidate consensus signature is invalid") from error
    return SignedValidatorNomination(
        chain_id=nomination.chain_id,
        operator=nomination.operator,
        consensus_signature=nomination.consensus_signature,
        governance_signature=governance_private_key.sign(message),
    )


def verify_validator_nomination(nomination: SignedValidatorNomination) -> bool:
    """Return whether both candidate keys signed the same canonical nomination."""
    try:
        message = _NOMINATION_SIGNATURE_DOMAIN + encode_nomination_signing_payload(
            chain_id=nomination.chain_id,
            operator=nomination.operator,
        )
        Ed25519PublicKey.from_public_bytes(nomination.operator.consensus_public_key).verify(
            nomination.consensus_signature, message
        )
        Ed25519PublicKey.from_public_bytes(nomination.operator.governance_public_key).verify(
            nomination.governance_signature, message
        )
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def propose_validator_membership(
    *,
    chain_id: str,
    operation: ValidatorMembershipOperation,
    operator: ValidatorOperator,
    sponsor_private_key: Ed25519PrivateKey,
    nomination: SignedValidatorNomination | None = None,
) -> ValidatorMembershipProposal:
    """Create one current validator's signed membership proposal and first approval."""
    _require_private_key(sponsor_private_key, "sponsor_private_key")
    unsigned = ValidatorMembershipProposal(
        chain_id=chain_id,
        operation=operation,
        operator=operator,
        sponsor_public_key=_public_key(sponsor_private_key),
        sponsor_signature=bytes(64),
        nomination=nomination,
    )
    return ValidatorMembershipProposal(
        chain_id=unsigned.chain_id,
        operation=unsigned.operation,
        operator=unsigned.operator,
        sponsor_public_key=unsigned.sponsor_public_key,
        sponsor_signature=sponsor_private_key.sign(
            _PROPOSAL_SIGNATURE_DOMAIN + encode_proposal_signing_payload(unsigned)
        ),
        nomination=unsigned.nomination,
    )


def verify_validator_proposal(proposal: ValidatorMembershipProposal) -> bool:
    """Return whether the sponsor and, for admission, candidate signatures are valid."""
    try:
        Ed25519PublicKey.from_public_bytes(proposal.sponsor_public_key).verify(
            proposal.sponsor_signature,
            _PROPOSAL_SIGNATURE_DOMAIN + encode_proposal_signing_payload(proposal),
        )
    except (InvalidSignature, TypeError, ValueError):
        return False
    return proposal.nomination is None or verify_validator_nomination(proposal.nomination)


def validator_proposal_id(proposal: ValidatorMembershipProposal) -> bytes:
    """Return the stable SHA-256 identifier of a complete signed proposal."""
    if not isinstance(proposal, ValidatorMembershipProposal):
        raise TypeError("proposal must be a ValidatorMembershipProposal")
    return sha256(_PROPOSAL_ID_DOMAIN + encode_validator_governance_transaction(proposal)).digest()


def approve_validator_proposal(
    *,
    chain_id: str,
    proposal_id: bytes,
    private_key: Ed25519PrivateKey,
) -> ValidatorProposalApproval:
    """Sign an explicit approval referencing one committed proposal."""
    _require_private_key(private_key, "private_key")
    unsigned = ValidatorProposalApproval(
        chain_id=chain_id,
        proposal_id=proposal_id,
        signer_public_key=_public_key(private_key),
        signature=bytes(64),
    )
    return ValidatorProposalApproval(
        chain_id=unsigned.chain_id,
        proposal_id=unsigned.proposal_id,
        signer_public_key=unsigned.signer_public_key,
        signature=private_key.sign(
            _APPROVAL_SIGNATURE_DOMAIN + encode_approval_signing_payload(unsigned)
        ),
    )


def verify_validator_proposal_approval(approval: ValidatorProposalApproval) -> bool:
    """Return whether an approval carries a valid signature by its named operator."""
    try:
        Ed25519PublicKey.from_public_bytes(approval.signer_public_key).verify(
            approval.signature,
            _APPROVAL_SIGNATURE_DOMAIN + encode_approval_signing_payload(approval),
        )
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def _public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _require_private_key(value: object, field_name: str) -> None:
    if not isinstance(value, Ed25519PrivateKey):
        raise TypeError(f"{field_name} must be an Ed25519PrivateKey")
