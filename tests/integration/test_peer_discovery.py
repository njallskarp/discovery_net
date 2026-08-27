# Verifies that independently bootstrapped nodes become peers without a permanent intermediary.

from pathlib import Path

from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction


def test_peer_exchange_removes_the_bootstrap_node_as_a_liveness_dependency(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: A ← B ← C → PEX → A ↔ C; guards decentralized discovery after B stops."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=2,
    ) as network:
        validator, bootstrap, peer = network.nodes
        for node in network.nodes:
            node.start_application()

        validator.start_cometbft()
        bootstrap.start_cometbft(peers=(validator.peer_address,))
        peer.start_cometbft(peers=(bootstrap.peer_address,))
        validator.wait_for_peer(peer.node_id)

        bootstrap.stop_cometbft()
        bootstrap.stop_application()
        transaction = signed_transaction(network.chain_id, "Discovered without a coordinator")

        height = peer.rpc.broadcast_commit(transaction)
        validator_snapshot = validator.wait_for_snapshot(
            minimum_height=height,
            minimum_entries=1,
        )
        peer_snapshot = peer.wait_for_snapshot(
            minimum_height=height,
            minimum_entries=1,
        )

        assert peer_snapshot == validator_snapshot
