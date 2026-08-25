# Owns subprocess lifecycle and diagnostics for live integration tests.

from __future__ import annotations

import shlex
import signal
import subprocess
from pathlib import Path
from typing import final

_STOP_TIMEOUT_SECONDS = 10


@final
class BackgroundProcess:
    """Runs one subprocess and retains its output for failure diagnostics."""

    __slots__ = ("_closed", "_command", "_log", "_log_path", "_process")

    def __init__(self, *, command: tuple[str, ...], log_path: Path) -> None:
        self._command = command
        self._log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("w+b")
        self._closed = False
        try:
            self._process = subprocess.Popen(
                command,
                stdout=self._log,
                stderr=subprocess.STDOUT,
            )
        except BaseException:
            self._log.close()
            self._closed = True
            raise

    def assert_running(self) -> None:
        """Fail with captured diagnostics if the process exited unexpectedly."""
        return_code = self._process.poll()
        if return_code is not None:
            raise AssertionError(
                f"process exited with code {return_code}: {shlex.join(self._command)}"
                f"\n{self.output()}"
            )

    def wait_for_exit(self, *, timeout_seconds: float) -> bool:
        """Wait for an expected exit and return whether it occurred in time."""
        try:
            self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            return False
        return True

    def output(self) -> str:
        """Return all process output written so far."""
        if not self._closed:
            self._log.flush()
        return self._log_path.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        """Interrupt the process and release its diagnostic log."""
        if self._closed:
            return
        try:
            if self._process.poll() is None:
                self._process.send_signal(signal.SIGINT)
                try:
                    self._process.wait(timeout=_STOP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=_STOP_TIMEOUT_SECONDS)
        finally:
            self._log.close()
            self._closed = True
