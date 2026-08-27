# Owns shell-free invocation of the supported CometBFT command surface.

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import NoReturn, final

_COMMAND_TIMEOUT_SECONDS = 30
_REQUIRED_START_FLAGS = (
    "--abci",
    "--genesis_hash",
    "--p2p.external-address",
    "--p2p.laddr",
    "--p2p.persistent_peers",
    "--p2p.pex",
    "--proxy_app",
    "--rpc.laddr",
)


@final
class _CometBFTProcess:
    """Initializes and replaces the current process with a compatible CometBFT binary."""

    __slots__ = ("_binary",)

    def __init__(self, *, binary: Path) -> None:
        if not isinstance(binary, Path):
            raise TypeError("binary must be a Path")
        self._binary = binary

    def require_compatible_command_surface(self) -> None:
        """Verify the exact startup capabilities used by this launcher."""
        help_text = self._run((str(self._binary), "start", "--help"), "CometBFT inspection")
        missing = tuple(flag for flag in _REQUIRED_START_FLAGS if flag not in help_text)
        if missing:
            raise RuntimeError(
                "CometBFT does not expose the required startup flags: " + ", ".join(missing)
            )

    def initialize(self, *, home: Path) -> None:
        """Create a new CometBFT home using the configured binary."""
        self._run(
            (str(self._binary), "init", "--home", str(home)),
            "CometBFT initialization",
        )

    def exec(self, *, home: Path, genesis_sha256: str) -> NoReturn:
        """Replace this process while asking CometBFT to recheck the genesis digest."""
        command = (
            str(self._binary),
            "start",
            "--home",
            str(home),
            "--genesis_hash",
            genesis_sha256,
        )
        os.execvp(command[0], command)

    @staticmethod
    def _run(command: tuple[str, ...], description: str) -> str:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except OSError as error:
            raise RuntimeError(f"{description} could not start") from error
        if completed.returncode != 0:
            raise RuntimeError(
                f"{description} failed with code {completed.returncode}"
                f"\n{completed.stdout}{completed.stderr}"
            )
        return completed.stdout
