# Adapts CometBFT protocol callbacks to the local callback handler.

from typing import final

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as _abci
from discovery_net.node.cometbft_callback_handler import CometBFTCallbackHandler


@final
class CometBFTABCIAdapter:
    """Translates ABCI protobuf messages into local callback operations."""

    __slots__ = ("_handler",)

    def __init__(self, *, handler: CometBFTCallbackHandler) -> None:
        self._handler = handler

    def info(self, request: _abci.RequestInfo) -> _abci.ResponseInfo:
        """Report the application state most recently persisted by Commit."""
        _require_message(request, _abci.RequestInfo)
        committed_head = self._handler.committed_head()
        return _abci.ResponseInfo(
            last_block_height=committed_head.height,
            last_block_app_hash=committed_head.state_hash,
        )

    def init_chain(self, request: _abci.RequestInitChain) -> _abci.ResponseInitChain:
        """Validate genesis configuration and return the initial application hash."""
        _require_message(request, _abci.RequestInitChain)
        app_hash = self._handler.initialize_chain(
            chain_id=request.chain_id,
            initial_height=request.initial_height,
            genesis_state=request.app_state_bytes,
        )
        return _abci.ResponseInitChain(app_hash=app_hash)

    def check_tx(self, request: _abci.RequestCheckTx) -> _abci.ResponseCheckTx:
        """Validate one mempool transaction without changing application state."""
        _require_message(request, _abci.RequestCheckTx)
        result = self._handler.check_tx(request.tx)
        return _abci.ResponseCheckTx(code=result.code)

    def prepare_proposal(
        self,
        request: _abci.RequestPrepareProposal,
    ) -> _abci.ResponsePrepareProposal:
        """Select the ordered transaction prefix that fits in the proposal."""
        _require_message(request, _abci.RequestPrepareProposal)
        transactions = self._handler.prepare_proposal(
            transactions=request.txs,
            maximum_transaction_bytes=request.max_tx_bytes,
        )
        return _abci.ResponsePrepareProposal(txs=transactions)

    def process_proposal(
        self,
        request: _abci.RequestProcessProposal,
    ) -> _abci.ResponseProcessProposal:
        """Accept a proposal for deterministic execution during FinalizeBlock."""
        _require_message(request, _abci.RequestProcessProposal)
        # TODO: Reject proposals that violate deterministic knowledge-graph policies.
        return _abci.ResponseProcessProposal(status=_abci.ResponseProcessProposal.ACCEPT)

    def finalize_block(
        self,
        request: _abci.RequestFinalizeBlock,
    ) -> _abci.ResponseFinalizeBlock:
        """Execute an agreed block and return its deterministic application hash."""
        _require_message(request, _abci.RequestFinalizeBlock)
        result = self._handler.finalize_block(
            height=request.height,
            transactions=request.txs,
        )
        return _abci.ResponseFinalizeBlock(
            tx_results=(
                _abci.ExecTxResult(code=tx_result.code) for tx_result in result.transaction_results
            ),
            app_hash=result.state_hash,
        )

    def commit(self, request: _abci.RequestCommit) -> _abci.ResponseCommit:
        """Persist the finalized block before acknowledging it to CometBFT."""
        _require_message(request, _abci.RequestCommit)
        self._handler.commit()
        return _abci.ResponseCommit()


def _require_message(message: object, message_type: type[object]) -> None:
    if not isinstance(message, message_type):
        raise TypeError(f"request must be a {message_type.__name__}")
