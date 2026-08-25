# Verifies validator agreement, duplicate convergence, and partition recovery.

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from discovery_net.node import LocalArtifactLedger, TransactionCode
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction

_PARTITION_OBSERVATION_SECONDS = 3


def test_several_validators_commit_identical_state(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: validator proposal → four local apps; guards deterministic entries and app hashes."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=4,
    ) as network:
        network.start_all()
        transaction = signed_transaction(network.chain_id, "Shared validator state")

        network.validators[0].rpc.broadcast_commit(transaction)
        snapshots = network.wait_for_convergence(minimum_entries=1)

        assert all(snapshot == snapshots[0] for snapshot in snapshots[1:])
        expected_hash = LocalArtifactLedger(entries=snapshots[0].entries).state_hash()
        assert all(
            node.rpc.block_app_hash(height=snapshot.height) == expected_hash
            for node, snapshot in zip(network.nodes, snapshots, strict=True)
        )


def test_concurrent_duplicate_submissions_produce_one_artifact(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: same transaction → every peer concurrently; guards network-wide idempotency."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=4,
    ) as network:
        network.start_all()
        transaction = signed_transaction(network.chain_id, "One shared artifact")

        with ThreadPoolExecutor(max_workers=len(network.nodes)) as executor:
            codes = tuple(
                executor.map(
                    lambda node: node.rpc.broadcast_sync(transaction),
                    network.nodes,
                )
            )

        assert TransactionCode.ACCEPTED in codes
        assert set(codes) <= {TransactionCode.ACCEPTED, TransactionCode.DUPLICATE}
        snapshots = network.wait_for_convergence(minimum_entries=1)
        assert all(len(snapshot.entries) == 1 for snapshot in snapshots)


def test_partition_prevents_commit_and_healed_network_converges(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: split validators → no quorum → full mesh; guards safety and recovery."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=4,
    ) as network:
        network.start_all(peer_groups=((0, 1), (2, 3)))
        partitioned = signed_transaction(network.chain_id, "Cannot reach quorum")

        assert network.validators[0].rpc.broadcast_sync(partitioned) == TransactionCode.ACCEPTED
        time.sleep(_PARTITION_OBSERVATION_SECONDS)
        partitioned_snapshots = tuple(node.snapshot() for node in network.nodes)
        assert all(snapshot is None or snapshot.entries == () for snapshot in partitioned_snapshots)

        network.stop_all_cometbft()
        network.start_all_cometbft()
        recovered = signed_transaction(network.chain_id, "Committed after healing", key_offset=1)
        network.validators[0].rpc.broadcast_commit(recovered)
        snapshots = network.wait_for_convergence(minimum_entries=1)

        assert all(snapshot == snapshots[0] for snapshot in snapshots[1:])
