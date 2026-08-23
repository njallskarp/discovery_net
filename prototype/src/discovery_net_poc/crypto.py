"""Canonical serialization and Ed25519 artifact signatures."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from discovery_net_poc.protocol import ArtifactType, SignedArtifact


class ArtifactVerificationError(ValueError):
    """Raised when a signed artifact fails validation."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ArtifactVerificationError("invalid base64 data") from exc


def agent_id_from_public_key(public_key: bytes) -> str:
    return hashlib.sha256(public_key).hexdigest()


def artifact_message(artifact_type: ArtifactType, signer_id: str, payload: dict[str, Any]) -> bytes:
    return canonical_json(
        {
            "artifact_type": artifact_type.value,
            "signer_id": signer_id,
            "payload": payload,
        }
    )


@dataclass(frozen=True, slots=True)
class KeyPair:
    private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> KeyPair:
        return cls(private_key=Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, path: Path) -> KeyPair:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                private_key=Ed25519PrivateKey.from_private_bytes(_decode(raw["private_key"]))
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        key_pair = cls.generate()
        private_bytes = key_pair.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        document = canonical_json({"private_key": _encode(private_bytes)})
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.write(descriptor, document)
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary_name, path)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        return key_pair

    @property
    def public_key_bytes(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @property
    def public_key_encoded(self) -> str:
        return _encode(self.public_key_bytes)

    @property
    def agent_id(self) -> str:
        return agent_id_from_public_key(self.public_key_bytes)

    def sign_artifact(self, artifact_type: ArtifactType, payload: dict[str, Any]) -> SignedArtifact:
        message = artifact_message(artifact_type, self.agent_id, payload)
        return SignedArtifact(
            artifact_id=hashlib.sha256(message).hexdigest(),
            artifact_type=artifact_type,
            signer_id=self.agent_id,
            public_key=self.public_key_encoded,
            payload=payload,
            signature=_encode(self.private_key.sign(message)),
        )


def verify_artifact(artifact: SignedArtifact) -> None:
    public_key_bytes = _decode(artifact.public_key)
    if len(public_key_bytes) != 32:
        raise ArtifactVerificationError("an Ed25519 public key must contain 32 bytes")
    if agent_id_from_public_key(public_key_bytes) != artifact.signer_id:
        raise ArtifactVerificationError("signer ID does not match the public key")

    message = artifact_message(artifact.artifact_type, artifact.signer_id, artifact.payload)
    if hashlib.sha256(message).hexdigest() != artifact.artifact_id:
        raise ArtifactVerificationError("artifact ID does not match its content")

    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            _decode(artifact.signature), message
        )
    except (InvalidSignature, ValueError) as exc:
        raise ArtifactVerificationError("invalid artifact signature") from exc
