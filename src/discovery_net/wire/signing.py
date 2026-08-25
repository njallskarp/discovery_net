# Creates and verifies cryptographic authorship proofs.

from typing import Final

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from discovery_net.knowledge_graph import Artifact
from discovery_net.wire.codec import (
    decode_payload,
    encode_payload,
    encode_signing_payload,
)
from discovery_net.wire.envelope import SignedEnvelope

SIGNATURE_DOMAIN: Final = b"discovery-net:signed-envelope:\x00"


def sign_artifact(
    *,
    network_id: str,
    artifact: Artifact,
    private_key: Ed25519PrivateKey,
) -> SignedEnvelope:
    """Encode and sign one knowledge-graph artifact for a network."""

    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519PrivateKey")
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    payload_type, payload = encode_payload(artifact)
    unsigned = SignedEnvelope(
        network_id=network_id,
        payload_type=payload_type,
        payload=payload,
        signer_public_key=public_key,
        signature=bytes(64),
    )
    signature = private_key.sign(_signature_message(unsigned))
    return SignedEnvelope(
        network_id=unsigned.network_id,
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


def _signature_message(envelope: SignedEnvelope) -> bytes:
    return SIGNATURE_DOMAIN + encode_signing_payload(envelope)
