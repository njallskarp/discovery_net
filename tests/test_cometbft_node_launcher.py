# Verifies the launcher owns trust checks, atomic preparation, restart, and execution order.

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import cast
from unittest.mock import patch

import pytest

from discovery_net.node.runtime import CometBFTNodeLauncher
from discovery_net.node.runtime._cometbft_config import _CometBFTConfig
from discovery_net.node.runtime._cometbft_home import _CometBFTHome
from discovery_net.node.runtime._cometbft_process import _CometBFTProcess
from discovery_net.node.runtime.genesis import _VerifiedGenesis
from tests.runtime_test_support import launch_settings, write_generated_home, write_genesis


class _ExecCalled(Exception):
    pass


def _initialize(_process: _CometBFTProcess, *, home: Path) -> None:
    write_generated_home(home)


def _exec(
    _process: _CometBFTProcess,
    *,
    home: Path,
    genesis_sha256: str,
) -> None:
    raise _ExecCalled((home, genesis_sha256))


def test_launcher_initializes_once_and_preserves_identity_on_restart(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        patch.object(
            _CometBFTProcess,
            "initialize",
            autospec=True,
            side_effect=_initialize,
        ) as initialize,
        patch.object(_CometBFTProcess, "exec", autospec=True, side_effect=_exec),
    ):
        with pytest.raises(_ExecCalled):
            CometBFTNodeLauncher(binary=Path("cometbft")).start(settings)
        node_key = (settings.home / "config" / "node_key.json").read_bytes()
        validator_key = (settings.home / "config" / "priv_validator_key.json").read_bytes()

        with pytest.raises(_ExecCalled):
            CometBFTNodeLauncher(binary=Path("cometbft")).start(settings)

    assert initialize.call_count == 1
    assert (settings.home / "config" / "node_key.json").read_bytes() == node_key
    assert (settings.home / "config" / "priv_validator_key.json").read_bytes() == validator_key
    assert (
        settings.home / "config" / "genesis.json"
    ).read_bytes() == settings.genesis_path.read_bytes()


def test_invalid_genesis_fails_before_binary_or_home_mutation(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)
    settings.genesis_path.write_bytes(b"different")

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ) as inspect,
        pytest.raises(ValueError, match="SHA-256"),
    ):
        CometBFTNodeLauncher(binary=Path("missing-cometbft")).start(settings)

    inspect.assert_not_called()
    assert not settings.home.exists()


def test_existing_partial_home_is_rejected_without_reinitialization(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)
    settings.home.mkdir()

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        patch.object(_CometBFTProcess, "initialize", autospec=True) as initialize,
        pytest.raises(ValueError, match="incomplete"),
    ):
        CometBFTNodeLauncher(binary=Path("cometbft")).start(settings)

    initialize.assert_not_called()


def test_existing_home_with_foreign_genesis_is_rejected_before_configuration(
    tmp_path: Path,
) -> None:
    settings = launch_settings(tmp_path)

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        patch.object(
            _CometBFTProcess,
            "initialize",
            autospec=True,
            side_effect=_initialize,
        ),
        patch.object(_CometBFTProcess, "exec", autospec=True, side_effect=_exec),
        pytest.raises(_ExecCalled),
    ):
        CometBFTNodeLauncher(binary=Path("cometbft")).start(settings)

    config_path = settings.home / "config" / "config.toml"
    expected_config = config_path.read_bytes()
    (settings.home / "config" / "genesis.json").write_bytes(b"foreign genesis")

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        pytest.raises(ValueError, match="different genesis"),
    ):
        CometBFTNodeLauncher(binary=Path("cometbft")).start(settings)

    assert config_path.read_bytes() == expected_config


def test_failed_initialization_never_publishes_a_partial_home(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)

    def fail_after_partial_write(_process: _CometBFTProcess, *, home: Path) -> None:
        home.mkdir(exist_ok=True)
        (home / "partial").write_text("incomplete")
        raise RuntimeError("interrupted")

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        patch.object(
            _CometBFTProcess,
            "initialize",
            autospec=True,
            side_effect=fail_after_partial_write,
        ),
        pytest.raises(RuntimeError, match="interrupted"),
    ):
        CometBFTNodeLauncher(binary=Path("cometbft")).start(settings)

    assert not settings.home.exists()
    assert not tuple(path for path in tmp_path.glob(f".{settings.home.name}.*") if path.is_dir())


def test_concurrent_preparation_initializes_the_home_once(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)
    verified = _VerifiedGenesis.from_path(
        path=settings.genesis_path,
        trust_anchor=settings.genesis_trust_anchor,
    )
    count_lock = Lock()
    initialization_count = 0

    class _ConcurrentInitializer:
        def initialize(self, *, home: Path) -> None:
            nonlocal initialization_count
            with count_lock:
                initialization_count += 1
            time.sleep(0.05)
            write_generated_home(home)

    process = cast(_CometBFTProcess, _ConcurrentInitializer())

    def prepare(_index: int) -> None:
        _CometBFTHome(
            path=settings.home,
            config=_CometBFTConfig(),
            process=process,
        ).prepare(genesis=verified, settings=settings)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(prepare, range(2)))

    assert initialization_count == 1
    assert (
        settings.home / "config" / "genesis.json"
    ).read_bytes() == settings.genesis_path.read_bytes()


def test_new_home_rejects_a_generated_key_in_the_genesis_validator_set(tmp_path: Path) -> None:
    settings = launch_settings(tmp_path)
    genesis_content = (
        b'{"chain_id":"discovery-test-chain","validators":[{"pub_key":'
        b'{"type":"tendermint/PubKeyEd25519","value":"generated"}}]}'
    )
    trust_anchor = write_genesis(settings.genesis_path, genesis_content)
    configured = replace(settings, genesis_trust_anchor=trust_anchor)

    with (
        patch.object(
            _CometBFTProcess,
            "require_compatible_command_surface",
            autospec=True,
        ),
        patch.object(
            _CometBFTProcess,
            "initialize",
            autospec=True,
            side_effect=_initialize,
        ),
        pytest.raises(ValueError, match="already in the genesis validator set"),
    ):
        CometBFTNodeLauncher(binary=Path("cometbft")).start(configured)

    assert not settings.home.exists()
