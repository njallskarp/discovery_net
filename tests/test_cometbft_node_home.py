# Verifies durable node initialization without replacing identity or genesis.

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from discovery_net.node import CometBFTNodeHome

CHAIN_ID = "discovery-net-test"
NODE_ID = "a" * 40


def test_initialization_installs_genesis_and_preserves_it_on_restart(tmp_path: Path) -> None:
    home = CometBFTNodeHome(path=tmp_path / "cometbft")
    genesis_path = _genesis(tmp_path, CHAIN_ID)
    calls: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...], **_options: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[1] == "init":
            config = home.path / "config"
            config.mkdir(parents=True)
            (config / "genesis.json").write_text("{}")
            (config / "node_key.json").write_text("{}")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, f"{NODE_ID}\n", "")

    with patch("discovery_net.node.cometbft_home.subprocess.run", side_effect=run):
        assert home.initialize(genesis_path=genesis_path, expected_chain_id=CHAIN_ID) == NODE_ID
        assert home.initialize(genesis_path=genesis_path, expected_chain_id=CHAIN_ID) == NODE_ID

    assert (home.path / "config" / "genesis.json").read_bytes() == genesis_path.read_bytes()
    assert sum(command[1] == "init" for command in calls) == 1


def test_existing_home_rejects_a_different_genesis(tmp_path: Path) -> None:
    home_path = tmp_path / "cometbft"
    config = home_path / "config"
    config.mkdir(parents=True)
    (config / "genesis.json").write_text(json.dumps({"chain_id": CHAIN_ID}))
    supplied = _genesis(tmp_path, CHAIN_ID, name="replacement.json", marker="different")

    with pytest.raises(ValueError, match="different genesis"):
        CometBFTNodeHome(path=home_path).initialize(
            genesis_path=supplied,
            expected_chain_id=CHAIN_ID,
        )


def test_initialization_rejects_a_mismatched_chain_before_creating_state(
    tmp_path: Path,
) -> None:
    home_path = tmp_path / "cometbft"

    with pytest.raises(ValueError, match="chain ID"):
        CometBFTNodeHome(path=home_path).initialize(
            genesis_path=_genesis(tmp_path, "another-chain"),
            expected_chain_id=CHAIN_ID,
        )

    assert not home_path.exists()


def _genesis(
    directory: Path,
    chain_id: str,
    *,
    name: str = "genesis.json",
    marker: str | None = None,
) -> Path:
    path = directory / name
    path.write_text(json.dumps({"chain_id": chain_id, "marker": marker}, separators=(",", ":")))
    return path
