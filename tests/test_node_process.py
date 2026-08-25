from __future__ import annotations

import signal
import socket
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import grpc
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as abci
from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2_grpc as abci_grpc
from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import LocalArtifactLedger, SQLiteArtifactLedgerStore, TransactionCode
from discovery_net.wire import encode_envelope, sign_artifact

CHAIN_ID = "discovery-net-process-test"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def test_node_process_serves_abci_and_restores_committed_state(tmp_path: Path) -> None:
    ledger_path = tmp_path / "node" / "artifact-ledger.sqlite"
    address = _available_loopback_address()
    encoded = _transaction()

    process = _start_node(ledger_path=ledger_path, address=address)
    try:
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
            client = abci_grpc.ABCIStub(channel)
            initial_hash = LocalArtifactLedger().state_hash()

            assert client.InitChain(
                abci.RequestInitChain(chain_id=CHAIN_ID, initial_height=1)
            ) == abci.ResponseInitChain(app_hash=initial_hash)
            assert client.CheckTx(abci.RequestCheckTx(tx=encoded)).code == TransactionCode.ACCEPTED
            finalized = client.FinalizeBlock(abci.RequestFinalizeBlock(height=1, txs=(encoded,)))
            assert tuple(result.code for result in finalized.tx_results) == (
                TransactionCode.ACCEPTED,
            )
            assert client.Commit(abci.RequestCommit()) == abci.ResponseCommit()
    finally:
        _stop_node(process)

    snapshot = SQLiteArtifactLedgerStore(path=ledger_path).load()
    assert snapshot is not None
    assert snapshot.height == 1

    process = _start_node(ledger_path=ledger_path, address=address)
    try:
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=5)
            assert abci_grpc.ABCIStub(channel).Info(abci.RequestInfo()) == abci.ResponseInfo(
                last_block_height=1,
                last_block_app_hash=finalized.app_hash,
            )
    finally:
        _stop_node(process)


def _transaction() -> bytes:
    return encode_envelope(
        sign_artifact(
            chain_id=CHAIN_ID,
            artifact=Contribution(
                kind=ContributionKind.PROBLEM_STATEMENT,
                title="A process-level problem",
                body="A process-level body",
                created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
            ),
            private_key=PRIVATE_KEY,
        )
    )


def _available_loopback_address() -> str:
    with closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    return f"127.0.0.1:{port}"


def _start_node(*, ledger_path: Path, address: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        (
            sys.executable,
            "-m",
            "discovery_net.node.process",
            "--chain-id",
            CHAIN_ID,
            "--ledger-path",
            str(ledger_path),
            "--abci-listen-address",
            address,
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _stop_node(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        _stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        _stdout, stderr = process.communicate(timeout=5)
        raise AssertionError("node process did not stop after SIGINT") from None
    assert process.returncode == 0, stderr.decode()
