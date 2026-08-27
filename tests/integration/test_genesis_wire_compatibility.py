# Records the exact InitChain values emitted by the pinned CometBFT binary.

from __future__ import annotations

import json
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import grpc
import pytest

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as abci
from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2_grpc as abci_grpc

_INIT_CHAIN_TIMEOUT_SECONDS = 10


class _OmittedType:
    pass


_Omitted = _OmittedType()


class _InitChainRecorder(abci_grpc.ABCIServicer):
    """Captures the genesis request before the test stops the consensus process."""

    def __init__(self) -> None:
        self.request: abci.RequestInitChain | None = None
        self.received = Event()

    def Echo(
        self,
        request: abci.RequestEcho,
        _context: grpc.ServicerContext,
    ) -> abci.ResponseEcho:
        return abci.ResponseEcho(message=request.message)

    def Flush(
        self,
        _request: abci.RequestFlush,
        _context: grpc.ServicerContext,
    ) -> abci.ResponseFlush:
        return abci.ResponseFlush()

    def Info(
        self,
        _request: abci.RequestInfo,
        _context: grpc.ServicerContext,
    ) -> abci.ResponseInfo:
        return abci.ResponseInfo()

    def InitChain(
        self,
        request: abci.RequestInitChain,
        _context: grpc.ServicerContext,
    ) -> abci.ResponseInitChain:
        self.request = request
        self.received.set()
        return abci.ResponseInitChain()


@pytest.mark.parametrize(
    ("initial_height", "expected_height"),
    ((None, 1), ("0", 1), ("1", 1)),
)
def test_cometbft_normalizes_supported_genesis_heights(
    cometbft_binary: Path,
    tmp_path: Path,
    initial_height: str | None,
    expected_height: int,
) -> None:
    request = _observe_init_chain(
        binary=cometbft_binary,
        home=tmp_path / "cometbft",
        initial_height=initial_height,
        app_state=_Omitted,
    )

    assert request.initial_height == expected_height


@pytest.mark.parametrize(
    ("app_state", "expected_bytes"),
    ((_Omitted, b""), (None, b""), ({}, b"{}")),
)
def test_cometbft_preserves_genesis_application_state_bytes(
    cometbft_binary: Path,
    tmp_path: Path,
    app_state: object,
    expected_bytes: bytes,
) -> None:
    request = _observe_init_chain(
        binary=cometbft_binary,
        home=tmp_path / "cometbft",
        initial_height="0",
        app_state=app_state,
    )

    assert request.app_state_bytes == expected_bytes


def _observe_init_chain(
    *,
    binary: Path,
    home: Path,
    initial_height: str | None,
    app_state: object,
) -> abci.RequestInitChain:
    _run((str(binary), "init", "--home", str(home)))
    genesis_path = home / "config" / "genesis.json"
    decoded: object = json.loads(genesis_path.read_bytes())
    if not isinstance(decoded, dict) or any(not isinstance(key, str) for key in decoded):
        raise AssertionError("CometBFT generated an invalid genesis object")
    document: dict[str, object] = decoded
    if initial_height is None:
        document.pop("initial_height", None)
    else:
        document["initial_height"] = initial_height
    if app_state is _Omitted:
        document.pop("app_state", None)
    else:
        document["app_state"] = app_state
    genesis_path.write_text(json.dumps(document))

    recorder = _InitChainRecorder()
    executor = ThreadPoolExecutor(max_workers=2)
    server = grpc.server(executor)
    abci_grpc.add_ABCIServicer_to_server(recorder, server)
    application_port = server.add_insecure_port("127.0.0.1:0")
    if application_port == 0:
        executor.shutdown(wait=False)
        raise OSError("could not bind the compatibility ABCI server")
    server.start()
    process = subprocess.Popen(
        (
            str(binary),
            "start",
            "--home",
            str(home),
            "--abci",
            "grpc",
            "--proxy_app",
            f"127.0.0.1:{application_port}",
            "--rpc.laddr",
            "tcp://127.0.0.1:0",
            "--p2p.laddr",
            "tcp://127.0.0.1:0",
            "--consensus.create_empty_blocks=false",
            "--log_level",
            "error",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        if not recorder.received.wait(_INIT_CHAIN_TIMEOUT_SECONDS):
            process.send_signal(signal.SIGINT)
            output, _ = process.communicate(timeout=5)
            raise AssertionError(f"CometBFT did not call InitChain\n{output}")
        request = recorder.request
        if request is None:
            raise AssertionError("InitChain signal arrived without a request")
        return request
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=5)
        server.stop(None).wait()
        executor.shutdown(wait=True)


def _run(command: tuple[str, ...]) -> None:
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {completed.stdout}{completed.stderr}")
