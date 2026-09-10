# Submits signed validator-governance transactions through CometBFT.

from dataclasses import dataclass

from discovery_net.submission._cometbft_rpc_client import _CometBFTRPCClient
from discovery_net.submission.validator_governance_receipt import (
    ValidatorGovernanceReceipt,
)
from discovery_net.wire.validator_governance import (
    ValidatorGovernanceTransaction,
    ValidatorMembershipProposal,
)
from discovery_net.wire.validator_governance_codec import (
    encode_validator_governance_transaction,
)
from discovery_net.wire.validator_governance_signing import validator_proposal_id


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorGovernanceSubmitter:
    """Broadcasts signed governance actions to one chain-checked CometBFT node."""

    cometbft_rpc_url: str

    def chain_id(self) -> str:
        """Return the chain identifier reported by the configured node."""
        return self._client().fetch_chain_id()

    def submit(
        self,
        transaction: ValidatorGovernanceTransaction,
    ) -> ValidatorGovernanceReceipt:
        """Require the active chain, then broadcast one canonical transaction."""
        client = self._client()
        if transaction.chain_id != client.fetch_chain_id():
            raise ValueError("governance transaction does not match the active chain")
        response = client.broadcast_transaction(
            encode_validator_governance_transaction(transaction)
        )
        proposal_id = (
            validator_proposal_id(transaction)
            if isinstance(transaction, ValidatorMembershipProposal)
            else transaction.proposal_id
        )
        return ValidatorGovernanceReceipt(
            proposal_id=proposal_id,
            transaction_hash=response.transaction_hash,
            check_tx_code=response.check_tx_code,
        )

    def _client(self) -> _CometBFTRPCClient:
        return _CometBFTRPCClient(url=self.cometbft_rpc_url)
