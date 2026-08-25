from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import grpc
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as abci
from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2_grpc as abci_grpc
from discovery_net.knowledge_graph import Contribution, ContributionKind
from discovery_net.node import (
    CometBFTABCIAdapter,
    CometBFTABCIServer,
    CometBFTCallbackHandler,
    LocalArtifactLedger,
    SQLiteArtifactLedgerStore,
    TransactionCode,
    TransactionValidator,
)
from discovery_net.wire import encode_envelope, sign_artifact

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


def transaction(title: str) -> bytes:
    return encode_envelope(
        sign_artifact(
            chain_id=CHAIN_ID,
            artifact=Contribution(
                kind=ContributionKind.PROBLEM_STATEMENT,
                title=title,
                body=f"Body for {title}",
                created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
            ),
            private_key=PRIVATE_KEY,
        )
    )


def adapter(path: Path) -> tuple[CometBFTABCIAdapter, SQLiteArtifactLedgerStore]:
    store = SQLiteArtifactLedgerStore(path=path)
    handler = CometBFTCallbackHandler(
        validator=TransactionValidator(expected_chain_id=CHAIN_ID),
        store=store,
    )
    return CometBFTABCIAdapter(handler=handler), store


@pytest.fixture
def abci_client(
    tmp_path: Path,
) -> Iterator[tuple[abci_grpc.ABCIStub, SQLiteArtifactLedgerStore]]:
    application, store = adapter(tmp_path / "artifact-ledger.sqlite")
    server = CometBFTABCIServer(
        adapter=application,
        listen_address="127.0.0.1:0",
    )

    with server, grpc.insecure_channel(f"127.0.0.1:{server.bound_port}") as channel:
        grpc.channel_ready_future(channel).result(timeout=5)
        yield abci_grpc.ABCIStub(channel), store


def test_transport_echoes_and_flushes(abci_client: tuple[abci_grpc.ABCIStub, object]) -> None:
    client, _ = abci_client

    assert client.Echo(abci.RequestEcho(message="ready")) == abci.ResponseEcho(message="ready")
    assert client.Flush(abci.RequestFlush()) == abci.ResponseFlush()


def test_transport_runs_the_supported_consensus_lifecycle(
    abci_client: tuple[abci_grpc.ABCIStub, SQLiteArtifactLedgerStore],
) -> None:
    client, store = abci_client
    encoded = transaction("First")
    initial_hash = LocalArtifactLedger().state_hash()

    assert client.InitChain(
        abci.RequestInitChain(chain_id=CHAIN_ID, initial_height=1)
    ) == abci.ResponseInitChain(app_hash=initial_hash)
    assert client.Info(abci.RequestInfo()) == abci.ResponseInfo(
        last_block_height=0,
        last_block_app_hash=initial_hash,
    )
    assert client.CheckTx(abci.RequestCheckTx(tx=encoded)) == abci.ResponseCheckTx(
        code=TransactionCode.ACCEPTED
    )
    assert client.CheckTx(abci.RequestCheckTx(tx=b"not-an-envelope")) == abci.ResponseCheckTx(
        code=TransactionCode.INVALID_ENVELOPE
    )
    assert tuple(
        client.PrepareProposal(
            abci.RequestPrepareProposal(
                txs=(encoded, b"later"),
                max_tx_bytes=len(encoded),
            )
        ).txs
    ) == (encoded,)
    assert (
        client.ProcessProposal(
            abci.RequestProcessProposal(
                height=1,
                txs=(encoded,),
            )
        ).status
        == abci.ResponseProcessProposal.ACCEPT
    )

    finalized = client.FinalizeBlock(
        abci.RequestFinalizeBlock(
            height=1,
            txs=(encoded,),
        )
    )

    assert tuple(result.code for result in finalized.tx_results) == (TransactionCode.ACCEPTED,)
    assert store.load() is None
    assert client.Commit(abci.RequestCommit()) == abci.ResponseCommit()
    snapshot = store.load()
    assert snapshot is not None
    assert snapshot.height == 1
    assert len(snapshot.entries) == 1
    assert client.Info(abci.RequestInfo()) == abci.ResponseInfo(
        last_block_height=1,
        last_block_app_hash=finalized.app_hash,
    )


def test_transport_reports_unimplemented_callbacks(
    abci_client: tuple[abci_grpc.ABCIStub, object],
) -> None:
    client, _ = abci_client

    with pytest.raises(grpc.RpcError) as error:
        client.Query(abci.RequestQuery())

    assert isinstance(error.value, grpc.Call)
    assert error.value.code() is grpc.StatusCode.UNIMPLEMENTED


def test_server_owns_one_explicit_lifecycle(tmp_path: Path) -> None:
    application, _ = adapter(tmp_path / "artifact-ledger.sqlite")
    server = CometBFTABCIServer(
        adapter=application,
        listen_address="127.0.0.1:0",
    )

    server.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            server.start()
        assert server.wait_for_termination(timeout_seconds=0.01)
    finally:
        server.stop()

    server.stop()
    with pytest.raises(RuntimeError, match="already stopped"):
        server.start()


def test_server_can_stop_before_starting(tmp_path: Path) -> None:
    application, _ = adapter(tmp_path / "artifact-ledger.sqlite")
    server = CometBFTABCIServer(
        adapter=application,
        listen_address="127.0.0.1:0",
    )

    server.stop()

    with pytest.raises(RuntimeError, match="already stopped"):
        server.start()


@pytest.mark.parametrize(
    ("listen_address", "error_type", "message"),
    [
        (None, TypeError, "listen_address must be a string"),
        (" ", ValueError, "listen_address must not be blank"),
    ],
)
def test_server_rejects_an_invalid_listen_address(
    tmp_path: Path,
    listen_address: object,
    error_type: type[Exception],
    message: str,
) -> None:
    application, _ = adapter(tmp_path / "artifact-ledger.sqlite")

    with pytest.raises(error_type, match=message):
        CometBFTABCIServer(
            adapter=application,
            listen_address=listen_address,  # type: ignore[arg-type]
        )
