import base64
import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import Request

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from discovery_net.knowledge_graph import (
    Contribution,
    ContributionKind,
    ContributionRelation,
    RelationKind,
)
from discovery_net.submission import (
    ArtifactSubmitter,
    IncomingRelation,
    OutgoingRelation,
    SubmissionError,
)
from discovery_net.submission._broadcast_response import _BroadcastResponse
from discovery_net.submission._cometbft_rpc_client import _CometBFTRPCClient
from discovery_net.wire import (
    artifact_ref,
    decode_payload,
    decode_transaction,
    sign_artifact,
    verify_transaction,
)

CHAIN_ID = "discovery-net-devnet"
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
RPC_URL = "http://127.0.0.1:26657"
ARTIFACT = Contribution(
    kind=ContributionKind.PROBLEM_STATEMENT,
    title="Riemann hypothesis",
    body="All nontrivial zeros have real part one half.",
    created_at=datetime(2026, 8, 25, 12, tzinfo=UTC),
)
AREA_REF = artifact_ref(
    sign_artifact(
        chain_id=CHAIN_ID,
        artifact=Contribution(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="The study of integers.",
            created_at=ARTIFACT.created_at,
        ),
        private_key=PRIVATE_KEY,
    )
)
QUESTION_REF = artifact_ref(
    sign_artifact(
        chain_id=CHAIN_ID,
        artifact=Contribution(
            kind=ContributionKind.QUESTION,
            title="What is known?",
            body="Collect the known results.",
            created_at=ARTIFACT.created_at,
        ),
        private_key=PRIVATE_KEY,
    )
)


def test_submitter_atomically_broadcasts_a_contribution_and_both_relation_directions() -> None:
    captured_transaction: bytes | None = None

    def broadcast(
        _client: _CometBFTRPCClient,
        transaction: bytes,
    ) -> _BroadcastResponse:
        nonlocal captured_transaction
        captured_transaction = transaction
        return _response(transaction)

    with (
        patch.object(
            _CometBFTRPCClient,
            "fetch_chain_id",
            autospec=True,
            return_value=CHAIN_ID,
        ),
        patch.object(_CometBFTRPCClient, "broadcast_transaction", autospec=True) as rpc,
    ):
        rpc.side_effect = broadcast
        receipt = _submitter().submit_contribution(
            ARTIFACT,
            relations=(
                OutgoingRelation(kind=RelationKind.ABOUT, to_contribution=AREA_REF),
                IncomingRelation(from_contribution=QUESTION_REF, kind=RelationKind.CITES),
            ),
        )

    assert captured_transaction is not None
    transaction = decode_transaction(captured_transaction)
    contribution_envelope, outgoing_envelope, incoming_envelope = transaction.envelopes
    contribution_ref = artifact_ref(contribution_envelope)
    assert transaction.chain_id == CHAIN_ID
    assert (
        decode_payload(contribution_envelope.payload_type, contribution_envelope.payload)
        == ARTIFACT
    )
    assert decode_payload(outgoing_envelope.payload_type, outgoing_envelope.payload) == (
        ContributionRelation(
            from_contribution=contribution_ref,
            to_contribution=AREA_REF,
            kind=RelationKind.ABOUT,
            created_at=ARTIFACT.created_at,
        )
    )
    assert decode_payload(incoming_envelope.payload_type, incoming_envelope.payload) == (
        ContributionRelation(
            from_contribution=QUESTION_REF,
            to_contribution=contribution_ref,
            kind=RelationKind.CITES,
            created_at=ARTIFACT.created_at,
        )
    )
    assert verify_transaction(transaction)
    assert receipt.artifact_refs == tuple(
        artifact_ref(envelope) for envelope in transaction.envelopes
    )
    assert receipt.transaction_hash == sha256(captured_transaction).hexdigest().upper()
    assert receipt.check_tx_code == 0
    assert receipt.accepted


def test_submitter_broadcasts_a_post_hoc_relation_as_one_artifact_transaction() -> None:
    captured_transaction: bytes | None = None

    def broadcast(
        _client: _CometBFTRPCClient,
        transaction: bytes,
    ) -> _BroadcastResponse:
        nonlocal captured_transaction
        captured_transaction = transaction
        return _response(transaction)

    relation = ContributionRelation(
        from_contribution=QUESTION_REF,
        to_contribution=AREA_REF,
        kind=RelationKind.CITES,
        created_at=ARTIFACT.created_at,
    )
    with (
        patch.object(_CometBFTRPCClient, "fetch_chain_id", autospec=True, return_value=CHAIN_ID),
        patch.object(
            _CometBFTRPCClient,
            "broadcast_transaction",
            autospec=True,
            side_effect=broadcast,
        ),
    ):
        receipt = _submitter().submit_relation(relation)

    assert captured_transaction is not None
    transaction = decode_transaction(captured_transaction)
    assert len(transaction.envelopes) == 1
    envelope = transaction.envelopes[0]
    assert decode_payload(envelope.payload_type, envelope.payload) == relation
    assert receipt.artifact_refs == (artifact_ref(envelope),)
    assert receipt.transaction_hash == sha256(captured_transaction).hexdigest().upper()
    assert receipt.check_tx_code == 0


def test_submitter_reports_a_rejected_check_tx_without_claiming_commitment() -> None:
    def reject(
        _client: _CometBFTRPCClient,
        transaction: bytes,
    ) -> _BroadcastResponse:
        return _response(transaction, check_tx_code=2)

    with (
        patch.object(_CometBFTRPCClient, "fetch_chain_id", autospec=True, return_value=CHAIN_ID),
        patch.object(
            _CometBFTRPCClient, "broadcast_transaction", autospec=True, side_effect=reject
        ),
    ):
        receipt = _submitter().submit_contribution(ARTIFACT)

    assert receipt.check_tx_code == 2
    assert not receipt.accepted


def test_submitter_rejects_a_response_for_another_transaction() -> None:
    response = _BroadcastResponse(transaction_hash="0" * 64, check_tx_code=0)
    with (
        patch.object(
            _CometBFTRPCClient,
            "fetch_chain_id",
            autospec=True,
            return_value=CHAIN_ID,
        ),
        patch.object(
            _CometBFTRPCClient,
            "broadcast_transaction",
            autospec=True,
            return_value=response,
        ),
        pytest.raises(SubmissionError, match="different transaction"),
    ):
        _submitter().submit_contribution(ARTIFACT)


def test_submitter_requires_an_ed25519_private_key() -> None:
    with pytest.raises(TypeError, match="private_key must be an Ed25519PrivateKey"):
        ArtifactSubmitter(
            private_key=object(),  # type: ignore[arg-type]
            cometbft_rpc_url=RPC_URL,
        )


def test_rpc_client_encodes_broadcast_tx_sync_and_decodes_check_tx() -> None:
    transaction = b"canonical transaction"
    transaction_hash = sha256(transaction).hexdigest().upper()
    response = _http_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"hash": transaction_hash, "code": 3, "log": "wrong chain"},
        }
    )

    with patch(
        "discovery_net.submission._cometbft_rpc_client.urlopen",
        return_value=response,
    ) as open_rpc:
        result = _CometBFTRPCClient(url=RPC_URL).broadcast_transaction(transaction)

    request = cast(Request, open_rpc.call_args.args[0])
    assert request.data is not None
    assert json.loads(cast(bytes, request.data)) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "broadcast_tx_sync",
        "params": {"tx": base64.b64encode(transaction).decode("ascii")},
    }
    assert request.get_header("Content-type") == "application/json"
    assert result == _BroadcastResponse(
        transaction_hash=transaction_hash,
        check_tx_code=3,
    )


def test_rpc_client_discovers_the_active_chain() -> None:
    response = _http_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "node_info": {
                    "network": CHAIN_ID,
                    "moniker": "local-node",
                },
                "sync_info": {"catching_up": False},
            },
        }
    )

    with patch(
        "discovery_net.submission._cometbft_rpc_client.urlopen",
        return_value=response,
    ) as open_rpc:
        chain_id = _CometBFTRPCClient(url=RPC_URL).fetch_chain_id()

    request = cast(Request, open_rpc.call_args.args[0])
    assert request.data is not None
    assert json.loads(cast(bytes, request.data)) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "status",
        "params": {},
    }
    assert chain_id == CHAIN_ID


def test_rpc_client_translates_transport_and_rpc_failures() -> None:
    client = _CometBFTRPCClient(url=RPC_URL)
    with (
        patch(
            "discovery_net.submission._cometbft_rpc_client.urlopen",
            side_effect=URLError("offline"),
        ),
        pytest.raises(SubmissionError, match="could not be reached"),
    ):
        client.broadcast_transaction(b"transaction")

    response = _http_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32603, "message": "mempool unavailable"},
        }
    )
    with (
        patch(
            "discovery_net.submission._cometbft_rpc_client.urlopen",
            return_value=response,
        ),
        pytest.raises(SubmissionError, match="mempool unavailable"),
    ):
        client.broadcast_transaction(b"transaction")


@pytest.mark.parametrize(
    "payload",
    (
        pytest.param(b"not-json", id="invalid-json"),
        pytest.param(
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "result": {"hash": "0" * 64, "code": 0}}
            ).encode(),
            id="wrong-response-id",
        ),
        pytest.param(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"hash": "invalid", "code": 0}}
            ).encode(),
            id="invalid-transaction-hash",
        ),
        pytest.param(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"hash": "0" * 64, "code": True}}
            ).encode(),
            id="invalid-check-tx-code",
        ),
        pytest.param(
            json.dumps({"jsonrpc": "2.0", "id": 1}).encode(),
            id="missing-outcome",
        ),
        pytest.param(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"hash": "0" * 64, "code": 0},
                    "error": {"message": "ambiguous"},
                }
            ).encode(),
            id="multiple-outcomes",
        ),
    ),
)
def test_rpc_client_rejects_malformed_responses(payload: bytes) -> None:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = payload
    with (
        patch(
            "discovery_net.submission._cometbft_rpc_client.urlopen",
            return_value=response,
        ),
        pytest.raises(SubmissionError, match="invalid response"),
    ):
        _CometBFTRPCClient(url=RPC_URL).broadcast_transaction(b"transaction")


def _submitter() -> ArtifactSubmitter:
    return ArtifactSubmitter(
        private_key=PRIVATE_KEY,
        cometbft_rpc_url=RPC_URL,
    )


def _response(transaction: bytes, *, check_tx_code: int = 0) -> _BroadcastResponse:
    return _BroadcastResponse(
        transaction_hash=sha256(transaction).hexdigest().upper(),
        check_tx_code=check_tx_code,
    )


def _http_response(payload: object) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response
