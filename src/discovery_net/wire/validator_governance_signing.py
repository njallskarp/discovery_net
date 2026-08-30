# Creates and verifies threshold approvals for validator-set changes.

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.wire.validator_governance import GovernanceApproval, ValidatorSetChange
from discovery_net.wire.validator_governance_codec import (
    encode_validator_set_change_signing_payload,
)

_VALIDATOR_SET_CHANGE_SIGNATURE_DOMAIN = b"discovery-net:validator-set-change:\x00"


def approve_validator_set_change(
    change: ValidatorSetChange,
    private_key: Ed25519PrivateKey,
) -> GovernanceApproval:
    """Sign one validator-set change as a governance member."""
    if not isinstance(change, ValidatorSetChange):
        raise TypeError("change must be a ValidatorSetChange")
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return GovernanceApproval(
        signer_public_key=public_key,
        signature=private_key.sign(_approval_message(change)),
    )


def verify_validator_set_change_approval(
    change: ValidatorSetChange,
    approval: GovernanceApproval,
) -> bool:
    """Return whether an approval signs exactly the supplied change."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(approval.signer_public_key)
        public_key.verify(approval.signature, _approval_message(change))
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def _approval_message(change: ValidatorSetChange) -> bytes:
    return _VALIDATOR_SET_CHANGE_SIGNATURE_DOMAIN + encode_validator_set_change_signing_payload(
        change
    )
