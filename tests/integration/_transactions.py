# Creates deterministic signed transactions for live integration scenarios.

from dataclasses import replace
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.wire import encode_envelope, sign_artifact


def signed_transaction(
    chain_id: str,
    title: str,
    *,
    key_offset: int = 0,
) -> bytes:
    """Return one deterministic valid transaction for the requested chain."""
    private_key = Ed25519PrivateKey.from_private_bytes(
        bytes((index + key_offset) % 256 for index in range(32))
    )
    return encode_envelope(
        sign_artifact(
            chain_id=chain_id,
            artifact=Contribution(
                kind=ContributionKind.PROBLEM_STATEMENT,
                title=title,
                body=f"Body for {title}",
                created_at=datetime(2026, 8, 25, 22, tzinfo=UTC),
            ),
            private_key=private_key,
        )
    )


def invalid_signature_transaction(chain_id: str) -> bytes:
    """Return a canonical envelope whose authorship signature is invalid."""
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    envelope = sign_artifact(
        chain_id=chain_id,
        artifact=Contribution(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title="Invalid signature",
            body="This signature has been replaced.",
            created_at=datetime(2026, 8, 25, 22, tzinfo=UTC),
        ),
        private_key=private_key,
    )
    return encode_envelope(replace(envelope, signature=bytes(64)))
