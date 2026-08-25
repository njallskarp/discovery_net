# Owns the local gRPC server used by CometBFT to call the Discovery Net application.

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import Self, final

import grpc

from discovery_net._cometbft.v0_40.tendermint.abci import types_pb2_grpc as _abci_grpc
from discovery_net.node._abci_service import _CometBFTABCIService
from discovery_net.node.abci import CometBFTABCIAdapter


@final
class CometBFTABCIServer:
    """Runs the local CometBFT ABCI gRPC endpoint with explicit lifecycle ownership."""

    __slots__ = (
        "_bound_port",
        "_executor",
        "_server",
        "_started",
        "_stopped",
    )

    def __init__(
        self,
        *,
        adapter: CometBFTABCIAdapter,
        listen_address: str,
    ) -> None:
        if not isinstance(adapter, CometBFTABCIAdapter):
            raise TypeError("adapter must be a CometBFTABCIAdapter")
        if not isinstance(listen_address, str):
            raise TypeError("listen_address must be a string")
        if not listen_address.strip():
            raise ValueError("listen_address must not be blank")

        executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="discovery-net-abci",
        )
        server = grpc.server(executor)
        _abci_grpc.add_ABCIServicer_to_server(
            _CometBFTABCIService(adapter=adapter),
            server,
        )
        bound_port = server.add_insecure_port(listen_address)
        if bound_port == 0:
            executor.shutdown(wait=False)
            raise OSError(f"could not bind the ABCI server to {listen_address!r}")

        self._executor = executor
        self._server = server
        self._bound_port = bound_port
        self._started = False
        self._stopped = False

    @property
    def bound_port(self) -> int:
        """Return the TCP port selected while binding the server."""
        return self._bound_port

    def start(self) -> None:
        """Start accepting ABCI requests."""
        if self._stopped:
            raise RuntimeError("the ABCI server has already stopped")
        if self._started:
            raise RuntimeError("the ABCI server has already started")
        try:
            self._server.start()
        except BaseException:
            self._server.stop(None).wait()
            self._executor.shutdown(wait=True)
            self._stopped = True
            raise
        self._started = True

    def stop(self, *, grace_period_seconds: float | None = None) -> None:
        """Stop accepting requests and release the worker pool."""
        if grace_period_seconds is not None:
            if not isinstance(grace_period_seconds, int | float) or isinstance(
                grace_period_seconds, bool
            ):
                raise TypeError("grace_period_seconds must be a number or None")
            if grace_period_seconds < 0:
                raise ValueError("grace_period_seconds must not be negative")

        if self._stopped:
            return
        self._server.stop(grace_period_seconds if self._started else None).wait()
        self._executor.shutdown(wait=True)
        self._stopped = True

    def wait_for_termination(self, *, timeout_seconds: float | None = None) -> bool:
        """Wait until shutdown, returning whether the wait timed out."""
        if not self._started:
            raise RuntimeError("the ABCI server has not started")
        if timeout_seconds is not None:
            if not isinstance(timeout_seconds, int | float) or isinstance(timeout_seconds, bool):
                raise TypeError("timeout_seconds must be a number or None")
            if timeout_seconds < 0:
                raise ValueError("timeout_seconds must not be negative")
        return self._server.wait_for_termination(timeout_seconds)

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.stop()
