# Verifies capability checks and shell-free process replacement at the executable boundary.

from pathlib import Path
from unittest.mock import patch

import pytest

from discovery_net.node.runtime._cometbft_process import (
    _REQUIRED_START_FLAGS,
    _CometBFTProcess,
)


def test_process_accepts_the_complete_required_command_surface() -> None:
    process = _CometBFTProcess(binary=Path("cometbft"))

    with patch.object(
        _CometBFTProcess,
        "_run",
        return_value="\n".join(_REQUIRED_START_FLAGS),
    ):
        process.require_compatible_command_surface()


def test_process_reports_missing_required_capabilities() -> None:
    process = _CometBFTProcess(binary=Path("cometbft"))

    with (
        patch.object(_CometBFTProcess, "_run", return_value="--abci"),
        pytest.raises(RuntimeError, match="required startup flags"),
    ):
        process.require_compatible_command_surface()


def test_process_exec_rechecks_genesis_without_invoking_a_shell(tmp_path: Path) -> None:
    process = _CometBFTProcess(binary=Path("/opt/cometbft"))
    digest = "a" * 64

    with patch("discovery_net.node.runtime._cometbft_process.os.execvp") as execute:
        process.exec(home=tmp_path, genesis_sha256=digest)

    execute.assert_called_once_with(
        "/opt/cometbft",
        (
            "/opt/cometbft",
            "start",
            "--home",
            str(tmp_path),
            "--genesis_hash",
            digest,
        ),
    )
