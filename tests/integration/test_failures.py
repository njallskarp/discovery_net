# Verifies unsafe state mismatches and persistence errors fail without false commits.

import sqlite3
import time
from pathlib import Path

from discovery_net.node import TransactionCode
from discovery_net.wire import encode_transaction
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import signed_transaction

_EXPECTED_FAILURE_TIMEOUT_SECONDS = 15
_FAILED_COMMIT_OBSERVATION_SECONDS = 3


def test_application_ahead_of_fresh_cometbft_fails_the_handshake(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: newer SQLite state → fresh CometBFT; guards inconsistent heights from starting."""
    original_root = tmp_path / "original"
    with IntegrationNetwork.single(binary=cometbft_binary, root=original_root) as original:
        node = original.nodes[0]
        original.start_all()
        transaction = signed_transaction(original.chain_id, "Committed history")
        committed_height = node.rpc.broadcast_commit(transaction)
        committed = node.wait_for_snapshot(
            minimum_height=committed_height,
            minimum_entries=1,
        )
        genesis_path = node.home / "config" / "genesis.json"
        ledger_path = node.ledger_path

    with IntegrationNetwork.single(
        binary=cometbft_binary,
        root=tmp_path / "fresh-consensus",
        genesis_source=genesis_path,
        ledger_path=ledger_path,
    ) as mismatched:
        node = mismatched.nodes[0]
        node.start_application()
        node.start_cometbft(wait_until_ready=False)

        assert node.wait_for_cometbft_exit(timeout_seconds=_EXPECTED_FAILURE_TIMEOUT_SECONDS)
        assert node.snapshot() == committed


def test_sqlite_failure_during_commit_is_atomic_and_replayed_after_restart(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: failing Commit → restart replay; guards atomic storage and recoverable progress."""
    with IntegrationNetwork.single(binary=cometbft_binary, root=tmp_path) as network:
        node = network.nodes[0]
        node.start_application()
        with sqlite3.connect(node.ledger_path) as connection:
            connection.execute(
                """
                CREATE TRIGGER reject_artifact_commit
                BEFORE INSERT ON artifact_ledger_entries
                BEGIN
                    SELECT RAISE(ABORT, 'forced integration failure');
                END
                """
            )
        node.start_cometbft()
        transaction = signed_transaction(network.chain_id, "Cannot persist")

        assert node.rpc.broadcast_sync(transaction) == TransactionCode.ACCEPTED
        time.sleep(_FAILED_COMMIT_OBSERVATION_SECONDS)
        snapshot = node.snapshot()
        assert snapshot is None or snapshot.entries == ()

        node.stop_cometbft()
        node.stop_application()
        with sqlite3.connect(node.ledger_path) as connection:
            connection.execute("DROP TRIGGER reject_artifact_commit")
        node.start_application()
        node.start_cometbft()
        recovered = node.wait_for_snapshot(minimum_height=1, minimum_entries=1)

        assert len(recovered.entries) == 1
        assert encode_transaction(recovered.entries[0].transaction) == transaction
