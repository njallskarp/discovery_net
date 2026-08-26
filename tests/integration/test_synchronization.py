# Verifies transaction gossip and committed-state synchronization across nodes.

from pathlib import Path

from discovery_net.knowledge_graph import ContributionKind
from discovery_net.node import LocalArtifactLedger
from tests.integration._discovery_net_cli import DiscoveryNetCLI
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import private_key, signed_transaction


def test_late_joining_node_replays_committed_history(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: existing validator → late peer block sync → local app; guards history catch-up."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=1,
    ) as network:
        validator, late_node = network.nodes
        validator.start_application()
        validator.start_cometbft()
        transaction = signed_transaction(network.chain_id, "Before peer joined")
        height = validator.rpc.broadcast_commit(transaction)
        validator.wait_for_snapshot(minimum_height=height, minimum_entries=1)

        late_node.start_application()
        late_node.start_cometbft(peers=(validator.peer_address,))
        snapshots = network.wait_for_convergence(minimum_entries=1)

        assert snapshots[0] == snapshots[1]


def test_transaction_submitted_to_non_validator_gossips_and_commits_everywhere(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: non-validator RPC → peer gossip → validator → all apps; guards ingress routing."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=1,
    ) as network:
        network.start_all()
        non_validator = network.nodes[1]
        transaction = signed_transaction(network.chain_id, "Submitted through a peer")

        non_validator.rpc.broadcast_commit(transaction)
        snapshots = network.wait_for_convergence(minimum_entries=1)

        assert snapshots[0] == snapshots[1]


def test_cli_submission_to_non_validator_reaches_every_ledger(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: CLI → non-validator → peer gossip → both ledgers; guards the complete P2P path."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=1,
    ) as network:
        network.start_all()
        artifact_ref = DiscoveryNetCLI.with_private_key(
            rpc_url=network.nodes[1].rpc_url,
            directory=tmp_path,
            private_key=private_key(),
        ).submit(
            kind=ContributionKind.FINDING,
            title="A peer-to-peer finding",
            body="This contribution entered through a non-validator.",
        )

        snapshots = network.wait_for_convergence(minimum_entries=1)

        assert snapshots[0] == snapshots[1]
        for node, snapshot in zip(network.nodes, snapshots, strict=True):
            ledger = LocalArtifactLedger(entries=snapshot.entries)
            assert ledger.contains(artifact_ref)
            assert node.rpc.block_app_hash(height=snapshot.height) == ledger.state_hash()


def test_stopped_validator_catches_up_after_the_remaining_quorum_commits(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: validator outage → quorum commit → restart sync; guards recoverable peer lag."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=4,
    ) as network:
        network.start_all()
        stopped = network.validators[-1]
        stopped.stop_cometbft()
        stopped.stop_application()
        transaction = signed_transaction(network.chain_id, "Committed during outage")

        height = network.validators[0].rpc.broadcast_commit(transaction)
        for node in network.validators[:-1]:
            node.wait_for_snapshot(minimum_height=height, minimum_entries=1)

        stopped.start_application()
        stopped.start_cometbft(
            peers=tuple(node.peer_address for node in network.nodes if node is not stopped)
        )
        snapshots = network.wait_for_convergence(minimum_entries=1)

        assert all(snapshot == snapshots[0] for snapshot in snapshots[1:])
