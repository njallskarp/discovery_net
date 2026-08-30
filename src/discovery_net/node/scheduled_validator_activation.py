# Defines one trusted validator activation applied at a deterministic chain height.

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError, field_validator

from discovery_net.node._cometbft_limits import MAX_TOTAL_VOTING_POWER, MAX_VALIDATORS

_ED25519_PUBLIC_KEY_BYTES = 32
_MAX_INT64 = (1 << 63) - 1
_SHA256_HEX_LENGTH = 64


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _ValidatorDocument(_WireModel):
    public_key: StrictStr
    voting_power: StrictInt

    @field_validator("public_key")
    @classmethod
    def _require_public_key(cls, value: str) -> str:
        _decode_public_key(value)
        return value


class _ActivationDocument(_WireModel):
    activation_height: StrictInt
    chain_id: StrictStr
    validators: tuple[_ValidatorDocument, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorPowerUpdate:
    """Assigns one Ed25519 validator its voting power."""

    public_key: bytes
    voting_power: int

    def __post_init__(self) -> None:
        if not isinstance(self.public_key, bytes):
            raise TypeError("public_key must be bytes")
        if len(self.public_key) != _ED25519_PUBLIC_KEY_BYTES:
            raise ValueError("public_key must contain one Ed25519 public key")
        if not isinstance(self.voting_power, int) or isinstance(self.voting_power, bool):
            raise TypeError("voting_power must be an integer")
        if not 1 <= self.voting_power <= MAX_TOTAL_VOTING_POWER:
            raise ValueError("voting_power is outside the CometBFT range")


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledValidatorActivation:
    """The equal-power validator assignments activated at one block height."""

    chain_id: str
    activation_height: int
    validators: tuple[ValidatorPowerUpdate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.chain_id, str):
            raise TypeError("chain_id must be a string")
        if not self.chain_id.strip():
            raise ValueError("chain_id must not be blank")
        if not isinstance(self.activation_height, int) or isinstance(self.activation_height, bool):
            raise TypeError("activation_height must be an integer")
        if not 1 <= self.activation_height <= _MAX_INT64:
            raise ValueError("activation_height is outside the CometBFT range")
        if not isinstance(self.validators, tuple):
            raise TypeError("validators must be a tuple")
        if not self.validators:
            raise ValueError("validators must not be empty")
        if any(not isinstance(validator, ValidatorPowerUpdate) for validator in self.validators):
            raise TypeError("validators must contain ValidatorPowerUpdate values")
        if len(self.validators) > MAX_VALIDATORS:
            raise ValueError("validators exceed the CometBFT validator limit")

        public_keys = tuple(validator.public_key for validator in self.validators)
        if public_keys != tuple(sorted(public_keys)):
            raise ValueError("validators must be ordered by public key")
        if len(set(public_keys)) != len(public_keys):
            raise ValueError("validators must not contain duplicate public keys")
        if len({validator.voting_power for validator in self.validators}) != 1:
            raise ValueError("validators must have equal voting power")
        if sum(validator.voting_power for validator in self.validators) > (MAX_TOTAL_VOTING_POWER):
            raise ValueError("total voting power exceeds the CometBFT limit")

    def updates_at(self, height: int) -> tuple[ValidatorPowerUpdate, ...]:
        """Return the assignments only at their deterministic activation height."""
        if not isinstance(height, int) or isinstance(height, bool):
            raise TypeError("height must be an integer")
        return self.validators if height == self.activation_height else ()

    def encode(self) -> bytes:
        """Encode the activation into its unique canonical JSON representation."""
        return json.dumps(
            {
                "activation_height": self.activation_height,
                "chain_id": self.chain_id,
                "validators": [
                    {
                        "public_key": base64.b64encode(validator.public_key).decode("ascii"),
                        "voting_power": validator.voting_power,
                    }
                    for validator in self.validators
                ],
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    @classmethod
    def from_trusted_file(
        cls,
        *,
        path: Path,
        expected_sha256: str,
        expected_chain_id: str,
    ) -> Self:
        """Read once and verify the exact activation bytes used by this node."""
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        digest = _sha256_digest(expected_sha256)
        if not isinstance(expected_chain_id, str):
            raise TypeError("expected_chain_id must be a string")
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ValueError("validator activation could not be read") from error
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), digest):
            raise ValueError("validator activation SHA-256 does not match")

        try:
            document = _ActivationDocument.model_validate_json(content)
            activation = cls(
                chain_id=document.chain_id,
                activation_height=document.activation_height,
                validators=tuple(
                    ValidatorPowerUpdate(
                        public_key=_decode_public_key(validator.public_key),
                        voting_power=validator.voting_power,
                    )
                    for validator in document.validators
                ),
            )
        except (ValidationError, TypeError, ValueError) as error:
            raise ValueError("validator activation is invalid") from error
        if activation.encode() != content:
            raise ValueError("validator activation is not canonical")
        if activation.chain_id != expected_chain_id:
            raise ValueError("validator activation belongs to a different chain")
        return activation


def _decode_public_key(value: str) -> bytes:
    try:
        public_key = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("public_key must be valid base64") from error
    if len(public_key) != _ED25519_PUBLIC_KEY_BYTES:
        raise ValueError("public_key must contain one Ed25519 public key")
    return public_key


def _sha256_digest(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("expected_sha256 must be a string")
    digest = value.lower()
    if len(digest) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError("expected_sha256 must be a 64-character hexadecimal digest")
    return digest
