# Reconstructs local artifact-ledger state from persisted snapshots.

from discovery_net.node.local_artifact_ledger import AppendOutcome, LocalArtifactLedger
from discovery_net.node.store.artifact_ledger_store import ArtifactLedgerSnapshot
from discovery_net.node.transaction_validator import TransactionCode, TransactionValidator
from discovery_net.wire import encode_transaction


def ledger_from_snapshot(
    snapshot: ArtifactLedgerSnapshot,
    validator: TransactionValidator,
) -> LocalArtifactLedger:
    """Reconstruct a verified local ledger from a persisted snapshot."""
    ledger = LocalArtifactLedger()
    for entry in snapshot.entries:
        try:
            transaction = encode_transaction(entry.transaction)
        except (TypeError, ValueError) as error:
            raise ValueError("stored snapshot contains an invalid transaction") from error

        result = validator.validate(transaction, ledger)
        if result.code is not TransactionCode.ACCEPTED:
            raise ValueError(f"stored snapshot contains an invalid transaction: {result.code.name}")
        ledger, outcome = ledger.append_transaction(entry)
        if outcome is not AppendOutcome.ACCEPTED:
            raise ValueError("stored snapshot contains a duplicate artifact")
    return ledger
