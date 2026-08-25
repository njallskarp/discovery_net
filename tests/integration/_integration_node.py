# Controls one paired Discovery Net application and CometBFT process.

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path
from typing import final
from urllib.error import URLError

from discovery_net.node import ArtifactLedgerSnapshot, SQLiteArtifactLedgerStore
from tests.integration._background_process import BackgroundProcess
from tests.integration._cometbft_rpc_client import CometBFTRPCClient

_STARTUP_TIMEOUT_SECONDS = 15


@final
class IntegrationNode:
    """Owns the application, consensus process, addresses, and local ledger for one node."""

    __slots__ = (
        "_application_address",
        "_application_generation",
        "_application_process",
        "_binary",
        "_chain_id",
        "_cometbft_generation",
        "_cometbft_process",
        "_home",
        "_ledger_path",
        "_log_directory",
        "_name",
        "_node_id",
        "_p2p_address",
        "_rpc",
        "_rpc_address",
    )

    def __init__(
        self,
        *,
        name: str,
        binary: Path,
        home: Path,
        ledger_path: Path,
        chain_id: str,
        node_id: str,
        application_address: str,
        rpc_address: str,
        p2p_address: str,
        log_directory: Path,
    ) -> None:
        self._name = name
        self._binary = binary
        self._home = home
        self._ledger_path = ledger_path
        self._chain_id = chain_id
        self._node_id = node_id
        self._application_address = application_address
        self._rpc_address = rpc_address
        self._p2p_address = p2p_address
        self._log_directory = log_directory
        self._rpc = CometBFTRPCClient(url=f"http://{rpc_address}")
        self._application_process: BackgroundProcess | None = None
        self._cometbft_process: BackgroundProcess | None = None
        self._application_generation = 0
        self._cometbft_generation = 0

    @property
    def name(self) -> str:
        """Return the stable test name for this node."""
        return self._name

    @property
    def home(self) -> Path:
        """Return this node's CometBFT home directory."""
        return self._home

    @property
    def ledger_path(self) -> Path:
        """Return this node's SQLite ledger path."""
        return self._ledger_path

    @property
    def rpc(self) -> CometBFTRPCClient:
        """Return the client for this node's CometBFT RPC endpoint."""
        return self._rpc

    @property
    def peer_address(self) -> str:
        """Return the persistent-peer address used by other CometBFT nodes."""
        return f"{self._node_id}@{self._p2p_address}"

    def start_application(self) -> None:
        """Start the Discovery Net process and wait for its ABCI listener."""
        if self._application_process is not None:
            raise RuntimeError("the Discovery Net application is already running")
        self._application_generation += 1
        process = BackgroundProcess(
            command=(
                sys.executable,
                "-m",
                "discovery_net.node.process",
                "--chain-id",
                self._chain_id,
                "--ledger-path",
                str(self._ledger_path),
                "--abci-listen-address",
                self._application_address,
            ),
            log_path=self._log_directory
            / f"{self._name}-application-{self._application_generation}.log",
        )
        self._application_process = process
        try:
            _wait_for_tcp(self._application_address, process)
        except BaseException:
            self.stop_application()
            raise

    def start_cometbft(
        self,
        *,
        peers: tuple[str, ...] = (),
        create_empty_blocks: bool = False,
        wait_until_ready: bool = True,
    ) -> None:
        """Start CometBFT, optionally waiting for its application handshake."""
        if self._application_process is None:
            raise RuntimeError("the Discovery Net application must be started first")
        if self._cometbft_process is not None:
            raise RuntimeError("CometBFT is already running")
        self._cometbft_generation += 1
        process = BackgroundProcess(
            command=(
                str(self._binary),
                "start",
                "--home",
                str(self._home),
                "--moniker",
                self._name,
                "--abci",
                "grpc",
                "--proxy_app",
                self._application_address,
                "--rpc.laddr",
                f"tcp://{self._rpc_address}",
                "--p2p.laddr",
                f"tcp://{self._p2p_address}",
                "--p2p.persistent_peers",
                ",".join(peers),
                "--p2p.pex=false",
                f"--consensus.create_empty_blocks={str(create_empty_blocks).lower()}",
                "--log_level",
                "error",
            ),
            log_path=self._log_directory / f"{self._name}-cometbft-{self._cometbft_generation}.log",
        )
        self._cometbft_process = process
        if not wait_until_ready:
            return
        try:
            self.wait_for_rpc()
            self.wait_for_consensus_ready()
        except BaseException:
            self.stop_cometbft()
            raise

    def wait_for_rpc(self) -> None:
        """Wait until the CometBFT JSON-RPC endpoint responds."""
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            self.assert_running()
            try:
                self._rpc.status()
                return
            except (OSError, URLError, ValueError):
                time.sleep(0.05)
        raise AssertionError(f"{self._name} RPC did not become ready\n{self.diagnostics()}")

    def wait_for_consensus_ready(self) -> None:
        """Wait until CometBFT finishes block sync and accepts transactions."""
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            self.assert_running()
            try:
                if not self._rpc.is_catching_up():
                    return
            except (OSError, URLError, ValueError):
                pass
            time.sleep(0.05)
        raise AssertionError(f"{self._name} did not finish catching up\n{self.diagnostics()}")

    def snapshot(self) -> ArtifactLedgerSnapshot | None:
        """Return the locally persisted ledger snapshot when it exists."""
        if not self._ledger_path.exists():
            return None
        return SQLiteArtifactLedgerStore(path=self._ledger_path).load()

    def wait_for_snapshot(
        self,
        *,
        minimum_height: int = 0,
        minimum_entries: int = 0,
        timeout_seconds: float = _STARTUP_TIMEOUT_SECONDS,
    ) -> ArtifactLedgerSnapshot:
        """Wait for the local ledger to reach the requested committed state."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self.assert_running()
            snapshot = self.snapshot()
            if (
                snapshot is not None
                and snapshot.height >= minimum_height
                and len(snapshot.entries) >= minimum_entries
            ):
                return snapshot
            time.sleep(0.05)
        raise AssertionError(
            f"{self._name} ledger did not reach height {minimum_height} "
            f"with {minimum_entries} entries\n{self.diagnostics()}"
        )

    def wait_for_cometbft_exit(self, *, timeout_seconds: float) -> bool:
        """Return whether CometBFT exited within the requested interval."""
        if self._cometbft_process is None:
            raise RuntimeError("CometBFT is not running")
        return self._cometbft_process.wait_for_exit(timeout_seconds=timeout_seconds)

    def assert_running(self) -> None:
        """Require every process currently owned by the node to be alive."""
        if self._application_process is not None:
            self._application_process.assert_running()
        if self._cometbft_process is not None:
            self._cometbft_process.assert_running()

    def stop_cometbft(self) -> None:
        """Stop this node's CometBFT process."""
        process = self._cometbft_process
        if process is None:
            return
        process.stop()
        self._cometbft_process = None

    def stop_application(self) -> None:
        """Stop this node's Discovery Net application process."""
        process = self._application_process
        if process is None:
            return
        process.stop()
        self._application_process = None

    def close(self) -> None:
        """Stop consensus before stopping the application it calls."""
        self.stop_cometbft()
        self.stop_application()

    def diagnostics(self) -> str:
        """Return captured output for every process currently owned by the node."""
        sections: list[str] = []
        if self._application_process is not None:
            sections.append(f"Discovery Net:\n{self._application_process.output()}")
        if self._cometbft_process is not None:
            sections.append(f"CometBFT:\n{self._cometbft_process.output()}")
        return "\n".join(sections)


def _wait_for_tcp(address: str, process: BackgroundProcess) -> None:
    host, encoded_port = address.rsplit(":", 1)
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        process.assert_running()
        try:
            with socket.create_connection(
                (host, int(encoded_port)),
                timeout=0.2,
            ):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"Discovery Net did not listen at {address}\n{process.output()}")
