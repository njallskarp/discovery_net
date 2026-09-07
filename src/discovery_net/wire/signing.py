# Creates and verifies cryptographic authorship proofs.

from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.domains.math import Artifact
from discovery_net.wire.codec import (
    decode_payload,
    encode_payload,
    encode_signing_payload,
    encode_transaction_signing_payload,
)
from discovery_net.wire.envelope import SignedEnvelope, SignedTransaction

SIGNATURE_DOMAIN: Final = b"discovery-net:signed-envelope:\x00"
TRANSACTION_SIGNATURE_DOMAIN: Final = b"discovery-net:signed-transaction:\x00"


def sign_artifact(
    *,
    chain_id: str,
    artifact: Artifact,
    private_key: Ed25519PrivateKey,
) -> SignedEnvelope:
    """Encode and sign one knowledge-graph artifact for a chain."""

    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    payload_type, payload = encode_payload(artifact)
    unsigned = SignedEnvelope(
        chain_id=chain_id,
        payload_type=payload_type,
        payload=payload,
        signer_public_key=public_key,
        signature=bytes(64),
    )
    signature = private_key.sign(_signature_message(unsigned))
    return SignedEnvelope(
        chain_id=unsigned.chain_id,
        payload_type=unsigned.payload_type,
        payload=unsigned.payload,
        signer_public_key=unsigned.signer_public_key,
        signature=signature,
    )


def verify_envelope(envelope: SignedEnvelope) -> bool:
    """Verify the envelope signature and decode its artifact payload."""

    try:
        decode_payload(envelope.payload_type, envelope.payload)
        public_key = Ed25519PublicKey.from_public_bytes(envelope.signer_public_key)
        public_key.verify(envelope.signature, _signature_message(envelope))
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def sign_transaction(
    *,
    envelopes: tuple[SignedEnvelope, ...],
    private_key: Ed25519PrivateKey,
) -> SignedTransaction:
    """Authorize signed artifacts as one atomic transaction."""
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    unsigned = SignedTransaction(envelopes=envelopes, signature=bytes(64))
    if unsigned.signer_public_key != public_key:
        raise ValueError("transaction signer must match every envelope signer")
    return SignedTransaction(
        envelopes=envelopes,
        signature=private_key.sign(_transaction_signature_message(unsigned)),
    )


def verify_transaction(transaction: SignedTransaction) -> bool:
    """Verify every artifact signature and the atomic transaction signature."""
    try:
        if any(not verify_envelope(envelope) for envelope in transaction.envelopes):
            return False
        public_key = Ed25519PublicKey.from_public_bytes(transaction.signer_public_key)
        public_key.verify(
            transaction.signature,
            _transaction_signature_message(transaction),
        )
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def _signature_message(envelope: SignedEnvelope) -> bytes:
    return SIGNATURE_DOMAIN + encode_signing_payload(envelope)


def _transaction_signature_message(transaction: SignedTransaction) -> bytes:
    return TRANSACTION_SIGNATURE_DOMAIN + encode_transaction_signing_payload(transaction)
