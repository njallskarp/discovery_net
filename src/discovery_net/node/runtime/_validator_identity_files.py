# Verifies and installs one private validator key together with its signing state.

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from discovery_net.node.runtime.genesis_validator import GenesisValidator
from discovery_net.node.runtime.validator_identity import ValidatorIdentity

_PUBLIC_KEY_TYPE = "tendermint/PubKeyEd25519"
_PRIVATE_KEY_TYPE = "tendermint/PrivKeyEd25519"
_PUBLIC_KEY_BYTES = 32
_PRIVATE_KEY_BYTES = 64


class _EncodedKey(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: str
    value: str


class _PrivateValidatorKey(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    address: str
    pub_key: _EncodedKey
    priv_key: _EncodedKey

    @field_validator("address")
    @classmethod
    def _require_address(cls, value: str) -> str:
        if len(value) != 40 or any(character not in "0123456789ABCDEF" for character in value):
            raise ValueError("address must be an uppercase CometBFT address")
        return value

    @model_validator(mode="after")
    def _require_ed25519(self) -> Self:
        if self.pub_key.type != _PUBLIC_KEY_TYPE or self.priv_key.type != _PRIVATE_KEY_TYPE:
            raise ValueError("validator identity must use Ed25519 keys")
        return self


class _PrivateValidatorState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    height: int
    round: int
    step: int
    signature: str | None = None
    signbytes: str | None = None

    @field_validator("height", mode="before")
    @classmethod
    def _parse_height(cls, value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("height must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdecimal():
            return int(value)
        raise ValueError("height must be an integer")

    @model_validator(mode="after")
    def _require_pristine_state(self) -> Self:
        if (self.height, self.round, self.step) != (0, 0, 0):
            raise ValueError("validator signing state is not pristine")
        if self.signature is not None or self.signbytes is not None:
            raise ValueError("validator signing state already contains a signature")
        return self


@dataclass(frozen=True, slots=True)
class _VerifiedValidatorIdentity:
    public_key: bytes

    @classmethod
    def from_identity(cls, identity: ValidatorIdentity) -> Self:
        """Read once and verify the exact private files that will be installed."""
        if identity.directory.is_symlink() or not identity.directory.is_dir():
            raise ValueError("validator identity must be a real directory")
        key_content = _read_private_file(identity.key_path, "private-validator key")
        state_content = _read_private_file(identity.state_path, "private-validator state")
        try:
            key = _PrivateValidatorKey.model_validate_json(key_content)
            _PrivateValidatorState.model_validate_json(state_content)
        except ValidationError as error:
            raise ValueError("validator identity is not a supported pristine identity") from error

        public_key = _decode_key(key.pub_key.value, _PUBLIC_KEY_BYTES, "public key")
        private_key = _decode_key(key.priv_key.value, _PRIVATE_KEY_BYTES, "private key")
        derived_public_key = (
            Ed25519PrivateKey.from_private_bytes(private_key[:32])
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
        if private_key[32:] != public_key or derived_public_key != public_key:
            raise ValueError("validator private key does not match its public key")
        expected_address = hashlib.sha256(public_key).digest()[:20].hex().upper()
        if key.address != expected_address:
            raise ValueError("validator address does not match its public key")
        return cls(public_key=public_key)

    def genesis_validator(self, *, name: str, voting_power: int) -> GenesisValidator:
        """Return the public genesis descriptor for this identity."""
        return GenesisValidator(
            name=name,
            public_key=self.public_key,
            voting_power=voting_power,
        )

def _decode_key(value: str, expected_length: int, description: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"validator {description} is not valid base64") from error
    if len(decoded) != expected_length:
        raise ValueError(f"validator {description} has the wrong length")
    return decoded


def _read_private_file(path: Path, description: str) -> bytes:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise ValueError(f"{description} could not be read") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{description} must be a regular file")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError(f"{description} must not be accessible by group or other users")
        with os.fdopen(descriptor, "rb", closefd=False) as private_file:
            return private_file.read()
    finally:
        os.close(descriptor)
