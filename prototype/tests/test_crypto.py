from __future__ import annotations

import pytest

from discovery_net_poc.crypto import (
    ArtifactVerificationError,
    KeyPair,
    verify_artifact,
)
from discovery_net_poc.protocol import ArtifactType, SignedArtifact


def test_signed_artifact_round_trip() -> None:
    key_pair = KeyPair.generate()
    artifact = key_pair.sign_artifact(ArtifactType.CONTRIBUTION, {"title": "Number theory"})

    verify_artifact(artifact)

    assert artifact.signer_id == key_pair.agent_id
    assert len(artifact.artifact_id) == 64


def test_modified_payload_fails_verification() -> None:
    key_pair = KeyPair.generate()
    artifact = key_pair.sign_artifact(ArtifactType.CONTRIBUTION, {"title": "Number theory"})
    modified = SignedArtifact(
        **{
            **artifact.model_dump(mode="json"),
            "payload": {"title": "Algebraic geometry"},
        }
    )

    with pytest.raises(ArtifactVerificationError, match="artifact ID"):
        verify_artifact(modified)


def test_signer_identity_is_part_of_the_content_address() -> None:
    first = KeyPair.generate().sign_artifact(
        ArtifactType.CONTRIBUTION, {"title": "The same payload"}
    )
    second = KeyPair.generate().sign_artifact(
        ArtifactType.CONTRIBUTION, {"title": "The same payload"}
    )

    assert first.artifact_id != second.artifact_id
