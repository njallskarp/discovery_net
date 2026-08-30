# Forms one deterministic CometBFT genesis document from public validator descriptors.

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import final

from pydantic import BaseModel, ConfigDict, ValidationError

from discovery_net.node.runtime._cometbft_limits import (
    MAX_CHAIN_ID_CHARACTERS,
    MAX_TOTAL_VOTING_POWER,
    MAX_VALIDATORS,
)
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.genesis import GenesisTrustAnchor, _GenesisDocument
from discovery_net.node.runtime.genesis_validator import GenesisValidator

_PUBLIC_KEY_TYPE = "tendermint/PubKeyEd25519"


class _GenesisTemplate(BaseModel):
    model_config = ConfigDict(extra="allow")

    consensus_params: dict[str, object]


class _PublicKeyDocument(BaseModel):
    type: str
    value: str


class _GenesisValidatorDocument(BaseModel):
    address: str
    pub_key: _PublicKeyDocument
    power: str
    name: str


class _FormedGenesisDocument(BaseModel):
    genesis_time: str
    chain_id: str
    initial_height: str
    consensus_params: dict[str, object]
    validators: tuple[_GenesisValidatorDocument, ...]
    app_hash: str


@final
class CometBFTGenesisWriter:
    """Creates a shared genesis without ever receiving validator private keys."""

    __slots__ = ("_process",)

    def __init__(self, *, binary: Path = Path("cometbft")) -> None:
        if not isinstance(binary, Path):
            raise TypeError("binary must be a Path")
        self._process = _CometBFTProcess(binary=binary)

    def write(
        self,
        *,
        path: Path,
        chain_id: str,
        genesis_time: datetime,
        validators: tuple[GenesisValidator, ...],
    ) -> GenesisTrustAnchor:
        """Write one new genesis and return the trust anchor for its exact bytes."""
        _validate_inputs(
            path=path,
            chain_id=chain_id,
            genesis_time=genesis_time,
            validators=validators,
        )
        if path.exists():
            raise FileExistsError(f"genesis already exists: {path}")

        self._process.require_compatible_command_surface()
        path.parent.mkdir(parents=True, exist_ok=True)
        template_home = Path(tempfile.mkdtemp(prefix=f".{path.name}.template.", dir=path.parent))
        try:
            self._process.initialize(home=template_home)
            template = _read_template(template_home / "config" / "genesis.json")
            content = _render_genesis(
                template=template,
                chain_id=chain_id,
                genesis_time=genesis_time,
                validators=validators,
            )
            _GenesisDocument.model_validate_json(content)
            _write_new_file(path, content)
        except ValidationError as error:
            raise ValueError("formed genesis is not a supported CometBFT document") from error
        finally:
            shutil.rmtree(template_home, ignore_errors=True)

        return GenesisTrustAnchor(
            expected_chain_id=chain_id,
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )


def _validate_inputs(
    *,
    path: Path,
    chain_id: str,
    genesis_time: datetime,
    validators: tuple[GenesisValidator, ...],
) -> None:
    if not isinstance(path, Path):
        raise TypeError("path must be a Path")
    if not isinstance(chain_id, str):
        raise TypeError("chain_id must be a string")
    if not chain_id.strip():
        raise ValueError("chain_id must not be blank")
    if len(chain_id) > MAX_CHAIN_ID_CHARACTERS:
        raise ValueError("chain_id must not exceed 50 characters")
    if not isinstance(genesis_time, datetime):
        raise TypeError("genesis_time must be a datetime")
    if genesis_time.tzinfo is None or genesis_time.utcoffset() is None:
        raise ValueError("genesis_time must be timezone-aware")
    if not isinstance(validators, tuple) or not validators:
        raise ValueError("validators must be a nonempty tuple")
    if any(not isinstance(validator, GenesisValidator) for validator in validators):
        raise TypeError("validators must contain GenesisValidator values")
    if len(validators) > MAX_VALIDATORS:
        raise ValueError("validators exceed the CometBFT commit limit")
    if sum(validator.voting_power for validator in validators) > MAX_TOTAL_VOTING_POWER:
        raise ValueError("total voting power exceeds the CometBFT limit")
    if len({validator.voting_power for validator in validators}) != 1:
        raise ValueError("validators must have equal voting power")
    if len({validator.public_key for validator in validators}) != len(validators):
        raise ValueError("validators must not contain duplicate public keys")
    if len({validator.name for validator in validators}) != len(validators):
        raise ValueError("validators must not contain duplicate names")


def _read_template(path: Path) -> _GenesisTemplate:
    try:
        return _GenesisTemplate.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise ValueError("CometBFT did not generate a supported genesis template") from error


def _render_genesis(
    *,
    template: _GenesisTemplate,
    chain_id: str,
    genesis_time: datetime,
    validators: tuple[GenesisValidator, ...],
) -> bytes:
    document = _FormedGenesisDocument(
        genesis_time=_rfc3339(genesis_time),
        chain_id=chain_id,
        initial_height="1",
        consensus_params=template.consensus_params,
        validators=tuple(
            _GenesisValidatorDocument(
                address=validator.address,
                pub_key=_PublicKeyDocument(
                    type=_PUBLIC_KEY_TYPE,
                    value=validator.model_dump(mode="json")["public_key"],
                ),
                power=str(validator.voting_power),
                name=validator.name,
            )
            for validator in validators
        ),
        app_hash="",
    )
    return (json.dumps(document.model_dump(mode="json"), indent=2) + "\n").encode()


def _rfc3339(value: datetime) -> str:
    utc = value.astimezone(UTC)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write_new_file(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(0o644)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            raise FileExistsError(f"genesis already exists: {path}") from None
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
