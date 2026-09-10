# Describes CometBFT's immediate response to one validator-governance transaction.

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceReceipt:
    """The proposal identifier and immediate CheckTx result of one broadcast."""

    proposal_id: bytes
    transaction_hash: str
    check_tx_code: int

    @property
    def accepted(self) -> bool:
        """Return whether CometBFT accepted the transaction into its mempool."""
        return self.check_tx_code == 0
