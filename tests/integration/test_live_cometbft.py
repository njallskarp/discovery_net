from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import cast, final
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import (
    ArtifactLedgerSnapshot,
    LocalArtifactLedger,
    SQLiteArtifactLedgerStore,
    TransactionCode,
)
from discovery_net.wire import encode_envelope, sign_artifact

type JSONObject = dict[str, object]

_COMETBFT_BINARY_ENV = "DISCOVERY_NET_COMETBFT_BINARY"
_PROCESS_STOP_TIMEOUT_SECONDS = 10
_STARTUP_TIMEOUT_SECONDS = 15


def test_signed_artifact_commits_through_live_cometbft(tmp_path: Path) -> None:
    cometbft_binary = _cometbft_binary()
    cometbft_home = tmp_path / "cometbft"
    chain_id = _initialize_cometbft(cometbft_binary, cometbft_home)
    ledger_path = tmp_path / "artifact-ledger.sqlite"
    application_port, rpc_port = _available_ports(2)
    application_address = f"127.0.0.1:{application_port}"
    rpc_url = f"http://127.0.0.1:{rpc_port}"

    with _BackgroundProcess(
        command=_discovery_node_command(chain_id, ledger_path, application_address),
        log_path=tmp_path / "discovery-node.log",
    ) as discovery_node:
        _wait_for_tcp(application_address, discovery_node)

        with _BackgroundProcess(
            command=_cometbft_command(
                cometbft_binary,
                cometbft_home,
                application_address,
                rpc_port,
            ),
            log_path=tmp_path / "cometbft.log",
        ) as cometbft:
            _wait_for_rpc(rpc_url, discovery_node, cometbft)
            transaction = _signed_transaction(chain_id)
            committed = _rpc(
                rpc_url,
                "broadcast_tx_commit",
                {"tx": base64.b64encode(transaction).decode("ascii")},
            )

            assert _integer_field(_object_field(committed, "check_tx"), "code") == (
                TransactionCode.ACCEPTED
            )
            assert _integer_field(_object_field(committed, "tx_result"), "code") == (
                TransactionCode.ACCEPTED
            )
            committed_height = int(_string_field(committed, "height"))

            snapshot = _wait_for_snapshot(
                ledger_path,
                committed_height,
                discovery_node,
                cometbft,
            )
            assert snapshot.height == committed_height
            assert len(snapshot.entries) == 1
            assert encode_envelope(snapshot.entries[0].envelope) == transaction

            block_result = _rpc(
                rpc_url,
                "block_results",
                {"height": str(committed_height)},
            )
            assert _string_field(block_result, "height") == str(committed_height)
            committed_state_hash = base64.b64decode(
                _string_field(block_result, "app_hash"),
                validate=True,
            )
            assert (
                committed_state_hash == LocalArtifactLedger(entries=snapshot.entries).state_hash()
            )


@final
class _BackgroundProcess:
    """Owns one subprocess and preserves its output for integration diagnostics."""

    __slots__ = ("_closed", "_command", "_log", "_log_path", "_process")

    def __init__(self, *, command: tuple[str, ...], log_path: Path) -> None:
        self._command = command
        self._log_path = log_path
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
                    self._process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECONDS)
        finally:
            self._log.close()
            self._closed = True

    def __enter__(self) -> _BackgroundProcess:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.stop()


def _cometbft_binary() -> Path:
    configured = os.environ.get(_COMETBFT_BINARY_ENV)
    if configured is not None:
        binary = Path(configured)
        if not binary.is_file():
            raise AssertionError(f"configured CometBFT binary does not exist: {binary}")
        return binary

    discovered = shutil.which("cometbft")
    if discovered is None:
        pytest.skip(f"CometBFT is not installed and {_COMETBFT_BINARY_ENV} is not configured")
    return Path(discovered)


def _initialize_cometbft(binary: Path, home: Path) -> str:
    completed = subprocess.run(
        (str(binary), "init", "--home", str(home)),
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"CometBFT initialization failed with code {completed.returncode}"
            f"\n{completed.stdout}{completed.stderr}"
        )
    genesis = _json_object(
        json.loads((home / "config" / "genesis.json").read_bytes()),
        "CometBFT genesis",
    )
    return _string_field(genesis, "chain_id")


def _discovery_node_command(
    chain_id: str,
    ledger_path: Path,
    application_address: str,
) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "discovery_net.node.process",
        "--chain-id",
        chain_id,
        "--ledger-path",
        str(ledger_path),
        "--abci-listen-address",
        application_address,
    )


def _cometbft_command(
    binary: Path,
    home: Path,
    application_address: str,
    rpc_port: int,
) -> tuple[str, ...]:
    return (
        str(binary),
        "start",
        "--home",
        str(home),
        "--abci",
        "grpc",
        "--proxy_app",
        application_address,
        "--rpc.laddr",
        f"tcp://127.0.0.1:{rpc_port}",
        "--p2p.laddr",
        "tcp://127.0.0.1:0",
        "--p2p.pex=false",
        "--consensus.create_empty_blocks=false",
        "--log_level",
        "error",
    )


def _signed_transaction(chain_id: str) -> bytes:
    return encode_envelope(
        sign_artifact(
            chain_id=chain_id,
            artifact=Contribution(
                kind=ContributionKind.PROBLEM_STATEMENT,
                title="A live network problem",
                body="Submitted through a real CometBFT process.",
                created_at=datetime(2026, 8, 25, 22, tzinfo=UTC),
            ),
            private_key=Ed25519PrivateKey.from_private_bytes(bytes(range(32))),
        )
    )


def _wait_for_tcp(address: str, process: _BackgroundProcess) -> None:
    host, encoded_port = address.rsplit(":", 1)
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        process.assert_running()
        try:
            with socket.create_connection((host, int(encoded_port)), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"Discovery Net did not listen at {address}\n{process.output()}")


def _wait_for_rpc(
    rpc_url: str,
    discovery_node: _BackgroundProcess,
    cometbft: _BackgroundProcess,
) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        discovery_node.assert_running()
        cometbft.assert_running()
        try:
            _rpc(rpc_url, "status")
            return
        except (OSError, URLError, ValueError):
            time.sleep(0.05)
    raise AssertionError(
        "CometBFT RPC did not become ready"
        f"\nDiscovery Net:\n{discovery_node.output()}"
        f"\nCometBFT:\n{cometbft.output()}"
    )


def _wait_for_snapshot(
    ledger_path: Path,
    height: int,
    discovery_node: _BackgroundProcess,
    cometbft: _BackgroundProcess,
) -> ArtifactLedgerSnapshot:
    store = SQLiteArtifactLedgerStore(path=ledger_path)
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        discovery_node.assert_running()
        cometbft.assert_running()
        snapshot = store.load()
        if snapshot is not None and snapshot.height >= height:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(
        f"artifact ledger did not reach height {height}"
        f"\nDiscovery Net:\n{discovery_node.output()}"
        f"\nCometBFT:\n{cometbft.output()}"
    )


def _rpc(
    rpc_url: str,
    method: str,
    parameters: JSONObject | None = None,
) -> JSONObject:
    request = Request(
        rpc_url,
        data=json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": parameters or {},
            },
            separators=(",", ":"),
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=_STARTUP_TIMEOUT_SECONDS) as response:
        payload = _json_object(json.loads(response.read()), "CometBFT RPC response")
    if payload.get("error") is not None:
        raise ValueError(f"CometBFT RPC returned an error: {payload['error']!r}")
    return _object_field(payload, "result")


def _available_ports(count: int) -> tuple[int, ...]:
    listeners: list[socket.socket] = []
    try:
        for _ in range(count):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listeners.append(listener)
        return tuple(int(listener.getsockname()[1]) for listener in listeners)
    finally:
        for listener in listeners:
            listener.close()


def _json_object(value: object, description: str) -> JSONObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{description} must be an object with string keys")
    return cast(JSONObject, value)


def _object_field(value: JSONObject, field_name: str) -> JSONObject:
    return _json_object(value.get(field_name), field_name)


def _string_field(value: JSONObject, field_name: str) -> str:
    field = value.get(field_name)
    if not isinstance(field, str):
        raise ValueError(f"{field_name} must be a string")
    return field


def _integer_field(value: JSONObject, field_name: str) -> int:
    field = value.get(field_name)
    if not isinstance(field, int) or isinstance(field, bool):
        raise ValueError(f"{field_name} must be an integer")
    return field
