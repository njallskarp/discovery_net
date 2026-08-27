# Verifies transaction acceptance, rejection, ordering, and state commitments.

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from discovery_net.indexing import KnowledgeGraphIndex
from discovery_net.knowledge_graph import ContributionKind, RelationKind
from discovery_net.node import LocalArtifactLedger, TransactionCode
from discovery_net.submission import ArtifactSubmitter
from discovery_net.wire import encode_transaction
from tests.integration._discovery_net_cli import DiscoveryNetCLI
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import (
    invalid_signature_transaction,
    private_key,
    problem_contribution,
    signed_transaction,
)


def test_artifact_submitter_reaches_committed_state_through_live_cometbft(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: submitter → RPC → consensus → SQLite; guards the production outbound path."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        artifact = problem_contribution("A live network problem")
        submitter = ArtifactSubmitter(
            private_key=private_key(),
            cometbft_rpc_url=node.rpc_url,
        )

        receipt = submitter.submit_contribution(artifact)
        snapshot = node.wait_for_snapshot(minimum_entries=1)

        assert receipt.accepted
        assert len(snapshot.entries) == 1
        ledger = LocalArtifactLedger(entries=snapshot.entries)
        assert ledger.contains(receipt.artifact_refs[0])
        assert node.rpc.block_app_hash(height=snapshot.height) == ledger.state_hash()


def test_cli_reaches_committed_state_through_live_cometbft(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: CLI process → submitter → consensus → SQLite; guards the complete user path."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        artifact_ref = DiscoveryNetCLI.with_private_key(
            rpc_url=node.rpc_url,
            directory=tmp_path,
            private_key=private_key(),
        ).submit(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title="Submitted from the CLI",
            body="This contribution traverses the complete local node boundary.",
        )[0]
        snapshot = node.wait_for_snapshot(minimum_entries=1)
        ledger = LocalArtifactLedger(entries=snapshot.entries)
        assert ledger.contains(artifact_ref)


def test_initial_and_post_hoc_relations_converge_across_two_nodes(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: atomic initial edges + later edge → gossip → graph; guards both workflows."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=1,
    ) as network:
        network.start_all()
        cli = DiscoveryNetCLI.with_private_key(
            rpc_url=network.nodes[1].rpc_url,
            directory=tmp_path,
            private_key=private_key(),
        )
        area_ref = cli.submit(
            kind=ContributionKind.MATHEMATICAL_AREA,
            title="Number theory",
            body="The study of integers.",
        )[0]
        network.wait_for_convergence(minimum_entries=1)

        problem_ref, about_ref, generalizes_ref = cli.submit(
            kind=ContributionKind.PROBLEM_STATEMENT,
            title="Riemann hypothesis",
            body="All nontrivial zeros have real part one half.",
            outgoing=((RelationKind.ABOUT, area_ref),),
            incoming=((RelationKind.GENERALIZES, area_ref),),
        )
        network.wait_for_convergence(minimum_entries=2)
        cites_ref = cli.submit_relation(
            kind=RelationKind.CITES,
            from_contribution=problem_ref,
            to_contribution=area_ref,
        )
        snapshots = network.wait_for_convergence(minimum_entries=3)

        for snapshot in snapshots:
            index = KnowledgeGraphIndex()
            index.refresh(snapshot)
            assert tuple(
                relation.artifact_ref for relation in index.outgoing_relations(problem_ref)
            ) == (about_ref, cites_ref)
            assert tuple(
                relation.artifact_ref for relation in index.incoming_relations(problem_ref)
            ) == (generalizes_ref,)
            assert len(snapshot.entries[1].transaction.envelopes) == 3


def test_duplicate_resubmission_is_rejected_without_a_second_entry(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: committed artifact → CheckTx; guards duplicate artifacts entering the ledger twice."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        transaction = signed_transaction(network.chain_id, "Submit once")

        height = node.rpc.broadcast_commit(transaction)
        node.wait_for_snapshot(minimum_height=height, minimum_entries=1)

        with pytest.raises(ValueError, match="tx already exists in cache"):
            node.rpc.broadcast_sync(transaction)
        snapshot = node.snapshot()
        assert snapshot is not None
        assert len(snapshot.entries) == 1


@pytest.mark.parametrize(
    ("transaction_factory", "expected_code"),
    (
        pytest.param(
            lambda _chain_id: b"not-an-envelope",
            TransactionCode.INVALID_TRANSACTION,
            id="malformed",
        ),
        pytest.param(
            lambda _chain_id: signed_transaction("another-chain", "Wrong chain"),
            TransactionCode.WRONG_CHAIN,
            id="wrong-chain",
        ),
        pytest.param(
            invalid_signature_transaction,
            TransactionCode.INVALID_SIGNATURE,
            id="invalid-signature",
        ),
    ),
)
def test_invalid_transactions_are_rejected_by_check_tx(
    cometbft_binary: Path,
    tmp_path: Path,
    transaction_factory: Callable[[str], bytes],
    expected_code: TransactionCode,
) -> None:
    """Path: hostile transaction → CheckTx; guards malformed, foreign, and forged input."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()

        assert node.rpc.broadcast_sync(transaction_factory(network.chain_id)) == expected_code
        snapshot = node.snapshot()
        assert snapshot is None or not snapshot.entries


def test_empty_block_advances_height_without_changing_artifact_state(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: empty proposal → Commit; guards height progress from mutating artifact state."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all(create_empty_blocks=True)

        snapshot = node.wait_for_snapshot(minimum_height=1)

        assert snapshot.entries == ()
        expected_hash = LocalArtifactLedger().state_hash()
        assert LocalArtifactLedger(entries=snapshot.entries).state_hash() == expected_hash
        assert node.rpc.block_app_hash(height=snapshot.height) == expected_hash


def test_several_transactions_share_one_ordered_block_and_state_hash(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: concurrent RPCs → one proposal → Commit; guards block order and aggregate hash."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        transactions = tuple(
            signed_transaction(network.chain_id, f"Problem {index}", key_offset=index)
            for index in range(5)
        )

        with ThreadPoolExecutor(max_workers=len(transactions)) as executor:
            codes = tuple(executor.map(node.rpc.broadcast_sync, transactions))

        assert codes == (TransactionCode.ACCEPTED,) * len(transactions)
        snapshot = node.wait_for_snapshot(minimum_entries=len(transactions))
        entries = snapshot.entries
        assert len(entries) == len(transactions)
        assert {entry.height for entry in entries} == {snapshot.height}
        assert tuple(entry.transaction_index for entry in entries) == tuple(range(len(entries)))
        assert {encode_transaction(entry.transaction) for entry in entries} == set(transactions)
        assert (
            node.rpc.block_app_hash(height=snapshot.height)
            == LocalArtifactLedger(entries=entries).state_hash()
        )
