# Observes live node, consensus, mempool, and peer state through CometBFT JSON-RPC.

from __future__ import annotations

from typing import Final, TypeVar, final
from urllib.request import urlopen

from pydantic import BaseModel

from discovery_net.inspector._cometbft_rpc_messages import (
    _ConsensusStateResult,
    _MempoolResult,
    _NetInfoResult,
    _PeerResult,
    _RPCMethod,
    _RPCRequest,
    _RPCResponse,
    _StatusResult,
)
from discovery_net.inspector.models import (
    ConnectionDirection,
    NodeObservation,
    PeerObservation,
)

_RPC_TIMEOUT_SECONDS: Final = 2
_NANOSECONDS_PER_SECOND: Final = 1_000_000_000
_CONSENSUS_STEPS: Final = {
    1: "new height",
    2: "new round",
    3: "propose",
    4: "prevote",
    5: "prevote wait",
    6: "precommit",
    7: "precommit wait",
    8: "commit",
}
_ResultModel = TypeVar("_ResultModel", bound=BaseModel)


@final
class CometBFTObservationSource:
    """Reads the current state reported by one local CometBFT RPC endpoint."""

    __slots__ = ("_rpc",)

    def __init__(self, *, url: str) -> None:
        self._rpc = _CometBFTObservationClient(url=url)

    def observe(self) -> NodeObservation:
        """Return one current observation assembled from CometBFT's local RPC views."""
        status = self._rpc.fetch("status", _StatusResult)
        network = self._rpc.fetch("net_info", _NetInfoResult)
        mempool = self._rpc.fetch("num_unconfirmed_txs", _MempoolResult)
        consensus = self._rpc.fetch("consensus_state", _ConsensusStateResult)
        consensus_round, consensus_step = consensus.round_state.round_and_step()

        return NodeObservation(
            node_id=status.node_info.node_id,
            moniker=status.node_info.moniker,
            chain_id=status.node_info.network,
            version=status.node_info.version,
            latest_height=status.sync_info.latest_block_height,
            application_height=status.sync_info.latest_block_height,
            latest_block_time=status.sync_info.latest_block_time,
            catching_up=status.sync_info.catching_up,
            validator_power=status.validator_info.voting_power,
            mempool_transactions=mempool.transaction_count,
            consensus_round=consensus_round,
            consensus_step=_consensus_step(consensus_step),
            peers=tuple(_peer_observation(peer) for peer in network.peers),
        )


@final
class _CometBFTObservationClient:
    """Fetches typed read-only observations from one CometBFT JSON-RPC endpoint."""

    __slots__ = ("_url",)

    def __init__(self, *, url: str) -> None:
        if not isinstance(url, str):
            raise TypeError("url must be a string")
        self._url = url

    def fetch(
        self,
        method: _RPCMethod,
        result_type: type[_ResultModel],
    ) -> _ResultModel:
        """Call one observation method and decode its typed result."""
        request = _RPCRequest(method=method).to_http_request(self._url)
        try:
            with urlopen(request, timeout=_RPC_TIMEOUT_SECONDS) as response:
                return _RPCResponse.decode(response.read()).result_as(result_type)
        except OSError as error:
            raise OSError("CometBFT RPC could not be reached") from error


def _peer_observation(peer: _PeerResult) -> PeerObservation:
    status = peer.connection_status
    return PeerObservation(
        node_id=peer.node_info.node_id,
        moniker=peer.node_info.moniker,
        remote_ip=peer.remote_ip,
        direction=(
            ConnectionDirection.OUTBOUND if peer.is_outbound else ConnectionDirection.INBOUND
        ),
        connected_seconds=status.duration_nanoseconds // _NANOSECONDS_PER_SECOND,
        bytes_sent=status.send_monitor.transferred_bytes,
        bytes_received=status.receive_monitor.transferred_bytes,
    )


def _consensus_step(value: int) -> str:
    return _CONSENSUS_STEPS.get(value, f"step {value}")
