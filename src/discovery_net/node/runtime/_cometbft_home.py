# Prepares one complete CometBFT home while preserving its durable identities.

from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import final

from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.genesis import _VerifiedGenesis
from discovery_net.node.runtime.node_launch_settings import NodeLaunchSettings

_REQUIRED_HOME_FILES = (
    Path("config/config.toml"),
    Path("config/node_key.json"),
    Path("config/priv_validator_key.json"),
    Path("data/priv_validator_state.json"),
)


@final
class _CometBFTHome:
    """Owns crash-safe initialization and verification of one persistent node home."""

    __slots__ = ("_config", "_path", "_process")

    def __init__(
        self,
        *,
        path: Path,
        config: _CometBFTConfig,
        process: _CometBFTProcess,
    ) -> None:
        self._path = path
        self._config = config
        self._process = process

    def prepare(self, *, genesis: _VerifiedGenesis, settings: NodeLaunchSettings) -> None:
        """Materialize or verify a complete home before CometBFT can start."""
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        lock_path = parent / f".{self._path.name}.initialize.lock"

        with _exclusive_lock(lock_path):
            if self._path.exists():
                self._prepare_existing(genesis=genesis, settings=settings)
                return
            self._prepare_new(genesis=genesis, settings=settings)

    def _prepare_new(self, *, genesis: _VerifiedGenesis, settings: NodeLaunchSettings) -> None:
        staging = Path(tempfile.mkdtemp(prefix=f".{self._path.name}.", dir=self._path.parent))
        try:
            self._process.initialize(home=staging)
            _require_complete_home(staging)
            generated_validator_key = _validator_public_key(
                staging / "config" / "priv_validator_key.json"
            )
            if generated_validator_key in genesis.document.validator_public_keys:
                raise ValueError("generated validator key is already in the genesis validator set")
            _replace_genesis(staging / "config" / "genesis.json", genesis.content)
            self._config.apply_and_verify(
                path=staging / "config" / "config.toml",
                settings=settings,
            )
            _require_complete_home(staging)
            _sync_tree(staging)
            staging.rename(self._path)
            _sync_directory(self._path.parent)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _prepare_existing(
        self,
        *,
        genesis: _VerifiedGenesis,
        settings: NodeLaunchSettings,
    ) -> None:
        if self._path.is_symlink() or not self._path.is_dir():
            raise ValueError("CometBFT home must be a real directory")
        _require_complete_home(self._path)
        installed_genesis = self._path / "config" / "genesis.json"
        try:
            installed_content = installed_genesis.read_bytes()
        except OSError as error:
            raise ValueError("installed CometBFT genesis could not be read") from error
        if installed_content != genesis.content:
            raise ValueError("CometBFT home belongs to a different genesis")
        self._config.apply_and_verify(
            path=self._path / "config" / "config.toml",
            settings=settings,
        )


def _require_complete_home(home: Path) -> None:
    missing = tuple(str(path) for path in _REQUIRED_HOME_FILES if not (home / path).is_file())
    if not (home / "config" / "genesis.json").is_file():
        missing += ("config/genesis.json",)
    if missing:
        raise ValueError("CometBFT home is incomplete: " + ", ".join(sorted(missing)))


def _validator_public_key(path: Path) -> tuple[str, str]:
    try:
        document: object = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("generated private-validator key could not be parsed") from error
    if not isinstance(document, dict):
        raise ValueError("generated private-validator key must be an object")
    public_key = document.get("pub_key")
    if not isinstance(public_key, dict):
        raise ValueError("generated private-validator key must contain pub_key")
    key_type = public_key.get("type")
    value = public_key.get("value")
    if not isinstance(key_type, str) or not isinstance(value, str):
        raise ValueError("generated private-validator public key is malformed")
    return key_type, value


def _replace_genesis(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        temporary_path.chmod(0o644)
        os.replace(temporary_path, path)
        _sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _sync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file():
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        elif path.is_dir():
            _sync_directory(path)
    _sync_directory(root)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
