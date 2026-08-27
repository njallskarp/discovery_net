# Initializes and verifies the durable CometBFT home owned by one node.

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast, final


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class CometBFTNodeHome:
    """Owns the identity, genesis, and consensus data persisted by one node."""

    path: Path

    def initialize(
        self,
        *,
        genesis_path: Path,
        expected_chain_id: str,
        binary: Path = Path("cometbft"),
    ) -> str:
        """Initialize an empty home or verify an existing home without overwriting it."""
        genesis = genesis_path.read_bytes()
        _require_chain_id(genesis, expected_chain_id)
        existing_genesis_path = self.path / "config" / "genesis.json"

        if self.path.exists() and any(self.path.iterdir()):
            if not existing_genesis_path.is_file():
                raise ValueError("CometBFT home contains data but no genesis")
            if existing_genesis_path.read_bytes() != genesis:
                raise ValueError("CometBFT home belongs to a different genesis")
            return self.node_id(binary=binary)

        self.path.mkdir(parents=True, exist_ok=True)
        _run((str(binary), "init", "--home", str(self.path)), "CometBFT initialization")
        _replace(existing_genesis_path, genesis)
        return self.node_id(binary=binary)

    def node_id(self, *, binary: Path = Path("cometbft")) -> str:
        """Return the P2P identity derived from the home's persistent node key."""
        node_id = _run(
            (str(binary), "show-node-id", "--home", str(self.path)),
            "CometBFT node ID lookup",
        ).strip()
        if len(node_id) != 40 or any(character not in "0123456789abcdef" for character in node_id):
            raise RuntimeError("CometBFT returned an invalid node ID")
        return node_id


def _require_chain_id(genesis: bytes, expected_chain_id: str) -> None:
    if not isinstance(expected_chain_id, str) or not expected_chain_id.strip():
        raise ValueError("expected_chain_id must not be blank")
    try:
        value: object = json.loads(genesis)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("genesis must contain valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("genesis must be a JSON object")
    fields = cast(dict[object, object], value)
    if fields.get("chain_id") != expected_chain_id:
        raise ValueError("genesis chain ID does not match the configured chain")


def _replace(path: Path, value: bytes) -> None:
    temporary_path = path.with_suffix(".json.pending")
    temporary_path.write_bytes(value)
    temporary_path.replace(path)


def _run(command: tuple[str, ...], description: str) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except OSError as error:
        raise RuntimeError(f"{description} could not start") from error
    if completed.returncode != 0:
        raise RuntimeError(
            f"{description} failed with code {completed.returncode}"
            f"\n{completed.stdout}{completed.stderr}"
        )
    return completed.stdout
