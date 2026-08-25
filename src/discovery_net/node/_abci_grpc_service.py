# Exposes the ABCI adapter through CometBFT's generated gRPC service contract.

from typing import final

import grpc

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2 as _abci
from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2_grpc as _abci_grpc
from discovery_net.node.abci import CometBFTABCIAdapter


@final
class _ABCIGRPCService(_abci_grpc.ABCIServicer):
    """Delegates supported CometBFT RPCs to the local ABCI adapter."""

    __slots__ = ("_adapter",)

    def __init__(self, *, adapter: CometBFTABCIAdapter) -> None:
        if not isinstance(adapter, CometBFTABCIAdapter):
            raise TypeError("adapter must be a CometBFTABCIAdapter")
        self._adapter = adapter

    def Echo(
        self,
        request: _abci.RequestEcho,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseEcho:
        """Echo a message to confirm transport connectivity."""
        return _abci.ResponseEcho(message=request.message)

    def Flush(
        self,
        _request: _abci.RequestFlush,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseFlush:
        """Acknowledge completion of preceding synchronous RPCs."""
        return _abci.ResponseFlush()

    def Info(
        self,
        request: _abci.RequestInfo,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseInfo:
        """Report the latest committed application state."""
        return self._adapter.info(request)

    def CheckTx(
        self,
        request: _abci.RequestCheckTx,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseCheckTx:
        """Validate a transaction for mempool admission."""
        return self._adapter.check_tx(request)

    def Commit(
        self,
        request: _abci.RequestCommit,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseCommit:
        """Persist the finalized application state."""
        return self._adapter.commit(request)

    def InitChain(
        self,
        request: _abci.RequestInitChain,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseInitChain:
        """Initialize the application from the chain genesis configuration."""
        return self._adapter.init_chain(request)

    def PrepareProposal(
        self,
        request: _abci.RequestPrepareProposal,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponsePrepareProposal:
        """Select transactions when this node proposes a block."""
        return self._adapter.prepare_proposal(request)

    def ProcessProposal(
        self,
        request: _abci.RequestProcessProposal,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseProcessProposal:
        """Evaluate a proposed block before this node votes on it."""
        return self._adapter.process_proposal(request)

    def FinalizeBlock(
        self,
        request: _abci.RequestFinalizeBlock,
        _context: grpc.ServicerContext,
    ) -> _abci.ResponseFinalizeBlock:
        """Execute a block decided by consensus into pending state."""
        return self._adapter.finalize_block(request)
