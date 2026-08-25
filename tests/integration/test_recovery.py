# Verifies process restarts recover and extend committed application state.

from pathlib import Path

from discovery_net.wire import encode_envelope
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction


def test_application_and_cometbft_restart_then_commit_again(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: commit → full restart → commit; guards durable state and handshake recovery."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        first = signed_transaction(network.chain_id, "Before restart")
        first_height = node.rpc.broadcast_commit(first)
        node.wait_for_snapshot(minimum_height=first_height, minimum_entries=1)

        network.stop_all()
        network.start_all()
        second = signed_transaction(network.chain_id, "After restart", key_offset=1)
        second_height = node.rpc.broadcast_commit(second)
        snapshot = node.wait_for_snapshot(minimum_height=second_height, minimum_entries=2)

        assert tuple(encode_envelope(entry.envelope) for entry in snapshot.entries) == (
            first,
            second,
        )
        assert second_height > first_height


def test_cometbft_restart_reconnects_to_the_running_application(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: commit → consensus restart → commit; guards ABCI reconnection and height alignment."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        first = signed_transaction(network.chain_id, "Before consensus restart")
        first_height = node.rpc.broadcast_commit(first)
        node.wait_for_snapshot(minimum_height=first_height, minimum_entries=1)

        node.stop_cometbft()
        node.start_cometbft()
        second = signed_transaction(network.chain_id, "After consensus restart", key_offset=1)
        second_height = node.rpc.broadcast_commit(second)
        snapshot = node.wait_for_snapshot(minimum_height=second_height, minimum_entries=2)

        assert tuple(encode_envelope(entry.envelope) for entry in snapshot.entries) == (
            first,
            second,
        )
        assert second_height > first_height
