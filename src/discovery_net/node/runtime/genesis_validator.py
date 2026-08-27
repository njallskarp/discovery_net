# Describes one validator whose public key and voting power belong in genesis.

from __future__ import annotations

import base64
import binascii
import hashlib

from pydantic import BaseModel, ConfigDict, PositiveInt, field_serializer, field_validator

from discovery_net.node.runtime._cometbft_limits import MAX_TOTAL_VOTING_POWER

_ED25519_PUBLIC_KEY_BYTES = 32


class GenesisValidator(BaseModel):
    """Contains only the public information needed to form a validator set."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    public_key: bytes
    voting_power: PositiveInt

    @field_validator("name")
    @classmethod
    def _require_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value

    @field_validator("public_key", mode="before")
    @classmethod
    def _decode_public_key(cls, value: object) -> bytes:
        if isinstance(value, bytes):
            decoded = value
        elif isinstance(value, str):
            try:
                decoded = base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("public_key must be valid base64") from error
        else:
            raise ValueError("public_key must be bytes or base64 text")
        if len(decoded) != _ED25519_PUBLIC_KEY_BYTES:
            raise ValueError("public_key must contain one Ed25519 public key")
        return decoded

    @field_validator("voting_power")
    @classmethod
    def _limit_voting_power(cls, value: int) -> int:
        if value > MAX_TOTAL_VOTING_POWER:
            raise ValueError("voting_power exceeds the CometBFT limit")
        return value

    @field_serializer("public_key")
    def _encode_public_key(self, value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @property
    def address(self) -> str:
        """Return the CometBFT address derived from this public key."""
        return hashlib.sha256(self.public_key).digest()[:20].hex().upper()
