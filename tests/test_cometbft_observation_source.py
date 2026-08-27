from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from discovery_net.inspector import CometBFTObservationSource
from discovery_net.inspector.models import ConnectionDirection

type JSONObject = dict[str, object]


def test_source_maps_typed_cometbft_observations() -> None:
    # Four local RPC views become one node observation with explicit units and direction.
    called_methods: list[str] = []
    with _rpc_server(_responses(), called_methods) as url:
        observation = CometBFTObservationSource(url=url).observe()

    assert tuple(called_methods) == (
        "status",
        "net_info",
        "num_unconfirmed_txs",
        "consensus_state",
    )
    assert observation.node_id == "a" * 40
    assert observation.moniker == "local-node"
    assert observation.chain_id == "test-chain"
    assert observation.version == "0.40.0"
    assert observation.latest_height == 12
    assert observation.application_height == 12
    assert observation.latest_block_time.isoformat() == "2026-08-27T01:02:03+00:00"
    assert not observation.catching_up
    assert observation.validator_power == 10
    assert observation.mempool_transactions == 3
    assert observation.consensus_round == 2
    assert observation.consensus_step == "precommit"
    assert len(observation.peers) == 1
    peer = observation.peers[0]
    assert peer.node_id == "b" * 40
    assert peer.moniker == "remote-node"
    assert peer.remote_ip == "203.0.113.17"
    assert peer.direction is ConnectionDirection.OUTBOUND
    assert peer.connected_seconds == 9
    assert peer.bytes_sent == 120
    assert peer.bytes_received == 130


def test_source_rejects_an_incomplete_peer_view() -> None:
    # A reported count that disagrees with the peer list cannot produce a misleading topology.
    responses = _responses()
    net_info = responses["net_info"]
    net_info["n_peers"] = "2"
    with (
        _rpc_server(responses, []) as url,
        pytest.raises(ValueError, match="invalid result"),
    ):
        CometBFTObservationSource(url=url).observe()


def test_source_surfaces_a_cometbft_rpc_error() -> None:
    # RPC failures remain distinguishable from valid empty node observations.
    responses = _responses()
    responses["status"] = {"_rpc_error": "node is stopping"}
    with (
        _rpc_server(responses, []) as url,
        pytest.raises(ValueError, match="node is stopping"),
    ):
        CometBFTObservationSource(url=url).observe()


@contextmanager
def _rpc_server(
    responses: dict[str, JSONObject],
    called_methods: list[str],
) -> Iterator[str]:
    handler = partial(
        _RPCRequestHandler,
        responses=responses,
        called_methods=called_methods,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        if not isinstance(host, str):
            raise TypeError("test RPC host must be a string")
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _RPCRequestHandler(BaseHTTPRequestHandler):
    def __init__(
        self,
        *args: object,
        responses: dict[str, JSONObject],
        called_methods: list[str],
        **kwargs: object,
    ) -> None:
        self._responses = responses
        self._called_methods = called_methods
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        request: object = json.loads(self.rfile.read(length))
        if not isinstance(request, dict):
            raise AssertionError("RPC request must be an object")
        method = request.get("method")
        if not isinstance(method, str):
            raise AssertionError("RPC request must contain a method")
        self._called_methods.append(method)
        result = self._responses[method]
        if "_rpc_error" in result:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"message": result["_rpc_error"]},
            }
        else:
            payload = {"jsonrpc": "2.0", "id": 1, "result": result}
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _responses() -> dict[str, JSONObject]:
    return {
        "status": {
            "node_info": {
                "id": "a" * 40,
                "network": "test-chain",
                "version": "0.40.0",
                "moniker": "local-node",
            },
            "sync_info": {
                "latest_block_height": "12",
                "latest_block_time": "2026-08-27T01:02:03Z",
                "catching_up": False,
            },
            "validator_info": {"voting_power": "10"},
        },
        "net_info": {
            "n_peers": "1",
            "peers": [
                {
                    "node_info": {
                        "id": "b" * 40,
                        "network": "test-chain",
                        "version": "0.40.0",
                        "moniker": "remote-node",
                    },
                    "is_outbound": True,
                    "connection_status": {
                        "Duration": "9000000001",
                        "SendMonitor": {"Bytes": "120"},
                        "RecvMonitor": {"Bytes": "130"},
                    },
                    "remote_ip": "203.0.113.17",
                }
            ],
        },
        "num_unconfirmed_txs": {"n_txs": "3"},
        "consensus_state": {"round_state": {"height/round/step": "13/2/6"}},
    }
