# Verifies transaction acceptance, rejection, ordering, and state commitments.

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from discovery_net.node import LocalArtifactLedger, TransactionCode
from discovery_net.wire import encode_envelope
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import (
    invalid_signature_transaction,
    signed_transaction,
)


def test_signed_artifact_commits_through_live_cometbft(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: RPC → consensus → Commit → SQLite; guards durability and app-hash agreement."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        network.start_all()
        transaction = signed_transaction(network.chain_id, "A live network problem")

        height = node.rpc.broadcast_commit(transaction)
        snapshot = node.wait_for_snapshot(minimum_height=height, minimum_entries=1)

        assert snapshot.height == height
        assert len(snapshot.entries) == 1
        assert encode_envelope(snapshot.entries[0].envelope) == transaction
        assert (
            node.rpc.block_app_hash(height=height)
            == LocalArtifactLedger(entries=snapshot.entries).state_hash()
        )


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
            TransactionCode.INVALID_ENVELOPE,
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
        assert {encode_envelope(entry.envelope) for entry in entries} == set(transactions)
        assert (
            node.rpc.block_app_hash(height=snapshot.height)
            == LocalArtifactLedger(entries=entries).state_hash()
        )
