# Verifies operator-supplied genesis bytes against the configured network trust anchor.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from discovery_net.node.validator_governance import ValidatorGovernanceState
from discovery_net.node.validator_governance_codec import decode_genesis_application_state

_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True, slots=True, kw_only=True)
class GenesisTrustAnchor:
    """Contains the expected identity of one exact CometBFT genesis document."""

    expected_chain_id: str
    expected_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.expected_chain_id, str):
            raise TypeError("expected_chain_id must be a string")
        if not self.expected_chain_id.strip():
            raise ValueError("expected_chain_id must not be blank")
        if not isinstance(self.expected_sha256, str):
            raise TypeError("expected_sha256 must be a string")
        normalized_digest = self.expected_sha256.lower()
        if len(normalized_digest) != _SHA256_HEX_LENGTH or any(
            character not in "0123456789abcdef" for character in normalized_digest
        ):
            raise ValueError("expected_sha256 must be a 64-character hexadecimal digest")
        object.__setattr__(self, "expected_sha256", normalized_digest)


class _GenesisDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    chain_id: str
    initial_height: int = 0
    app_state: object | None = None
    validators: object = ()

    @field_validator("chain_id")
    @classmethod
    def _require_chain_id(cls, value: str) -> str:
        if not value:
            raise ValueError("chain_id must not be empty")
        return value

    @field_validator("initial_height", mode="before")
    @classmethod
    def _parse_initial_height(cls, value: object) -> int:
        if isinstance(value, bool):
            raise ValueError("initial_height must be an integer")
        if isinstance(value, int):
            return value
        if (
            isinstance(value, str)
            and value
            and (value.isdecimal() or (value.startswith("-") and value[1:].isdecimal()))
        ):
            return int(value)
        raise ValueError("initial_height must be an integer")

    @property
    def effective_initial_height(self) -> int:
        return self.initial_height or 1

    @property
    def validator_public_keys(self) -> frozenset[tuple[str, str]]:
        keys: set[tuple[str, str]] = set()
        if not isinstance(self.validators, list | tuple):
            return frozenset()
        for validator in self.validators:
            if not isinstance(validator, dict):
                continue
            public_key = validator.get("pub_key")
            if not isinstance(public_key, dict):
                continue
            key_type = public_key.get("type")
            value = public_key.get("value")
            if isinstance(key_type, str) and isinstance(value, str):
                keys.add((key_type, value))
        return frozenset(keys)

    @property
    def ed25519_validator_public_keys(self) -> tuple[bytes, ...]:
        public_keys: list[bytes] = []
        if not isinstance(self.validators, list | tuple):
            return ()
        for validator in self.validators:
            if not isinstance(validator, dict):
                return ()
            public_key = validator.get("pub_key")
            if not isinstance(public_key, dict):
                return ()
            if public_key.get("type") != "tendermint/PubKeyEd25519":
                return ()
            value = public_key.get("value")
            if not isinstance(value, str):
                return ()
            try:
                decoded = base64.b64decode(value, validate=True)
            except ValueError:
                return ()
            if len(decoded) != 32:
                return ()
            public_keys.append(decoded)
        return tuple(sorted(public_keys))

    @property
    def validator_powers(self) -> tuple[int, ...]:
        powers: list[int] = []
        if not isinstance(self.validators, list | tuple):
            return ()
        for validator in self.validators:
            if not isinstance(validator, dict):
                return ()
            value = validator.get("power")
            if isinstance(value, bool):
                return ()
            if isinstance(value, int):
                powers.append(value)
            elif isinstance(value, str) and value.isdecimal():
                powers.append(int(value))
            else:
                return ()
        return tuple(powers)


@dataclass(frozen=True, slots=True)
class _VerifiedGenesis:
    content: bytes
    document: _GenesisDocument

    @classmethod
    def from_path(cls, *, path: Path, trust_anchor: GenesisTrustAnchor) -> Self:
        """Read once and verify the exact genesis bytes that will be installed."""
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ValueError("genesis could not be read") from error

        actual_digest = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(actual_digest, trust_anchor.expected_sha256):
            raise ValueError("genesis SHA-256 does not match the trust anchor")
        try:
            document = _GenesisDocument.model_validate_json(content)
        except ValidationError as error:
            raise ValueError("genesis does not contain a supported JSON document") from error
        if document.chain_id != trust_anchor.expected_chain_id:
            raise ValueError("genesis chain ID does not match the trust anchor")
        if document.effective_initial_height != 1:
            raise ValueError("Discovery Net requires an effective initial height of 1")
        if document.app_state is not None:
            encoded_state = json.dumps(
                document.app_state,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            try:
                governance = decode_genesis_application_state(encoded_state)
            except (TypeError, ValueError) as error:
                raise ValueError("Discovery Net genesis app_state is not supported") from error
            if not isinstance(governance, ValidatorGovernanceState):
                raise AssertionError("decoded genesis state has an unexpected type")
            if governance.sequence != 0:
                raise ValueError("genesis validator-governance sequence must be zero")
            if governance.validator_public_keys != document.ed25519_validator_public_keys:
                raise ValueError("genesis governance must describe the genesis validator set")
            if any(power != governance.validator_power for power in document.validator_powers):
                raise ValueError("governed genesis validators must have equal configured power")
        return cls(content=content, document=document)
