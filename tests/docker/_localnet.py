# Controls independently owned Docker node deployments in live integration tests.

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from discovery_net.node import ArtifactLedgerSnapshot, SQLiteArtifactLedgerStore
from tests.integration._cometbft_rpc_client import CometBFTRPCClient

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = _ROOT / "localnet" / "compose.yaml"
_STARTUP_TIMEOUT_SECONDS = 30

# CometBFT's PEX reactor sweeps on a fixed 30s cycle -- measured straight out of a
# failing CI log, "Ensure peers" at 01:50:24.062 then 01:50:54.063. Discovery
# therefore lands on a tick, not on a smooth curve, and a budget of 45s admitted
# exactly ONE tick: anything that missed the first sweep needed the second at
# ~60s and failed. That is why the same commit passed and failed run to run.
#
# Measured locally on a fast machine with warm images, the PEX step (peer
# learning the validator through the bridge) took 24.8s -- 55% of the old budget
# already gone on the happy path.
#
# This has to clear several sweeps, not one. It is a ceiling, not a sleep: a
# healthy run still returns in well under a second once the tick lands.
_PEER_DISCOVERY_TIMEOUT_SECONDS = int(os.environ.get("DISCOVERY_NET_PEER_DISCOVERY_TIMEOUT", "120"))

# Container lifecycle calls -- run, rm, exec, network create. These should fail
# fast: if `docker rm` has not returned in three minutes, something is wedged and
# waiting longer tells us nothing.
_COMMAND_TIMEOUT_SECONDS = int(os.environ.get("DISCOVERY_NET_DOCKER_TIMEOUT", "180"))

# The image build is a different kind of operation and was sharing the number
# above, which is what made this job flake: localnet/Dockerfile pulls
# golang:1.25-bookworm, compiles CometBFT from source with `go install`, then
# pulls python:3.12-slim and pip-installs grpcio, cryptography and pydantic-core.
# On a cold CI runner with no layer cache that legitimately exceeds three minutes,
# and the build was killed mid-layer-download:
#
#   subprocess.TimeoutExpired: Command ('docker', 'build', ...) timed out after 180 seconds
#
# The same commit passed on an earlier run and failed on a later one, which is the
# signature of a marginal limit rather than a defect. The enclosing job already
# allows 20 minutes, so this bound was the binding constraint, not the budget.
_BUILD_TIMEOUT_SECONDS = int(os.environ.get("DISCOVERY_NET_DOCKER_BUILD_TIMEOUT", "900"))

type JSONObject = dict[str, object]


@dataclass(frozen=True, slots=True, kw_only=True)
class DockerNode:
    """Owns one Compose project and its independent persistent state."""

    project: str
    image: str
    root: Path
    chain_id: str
    genesis_path: Path
    genesis_sha256: str
    p2p_alias: str
    p2p_network: str
    rpc_port: int
    persistent_peers: str = ""

    def __post_init__(self) -> None:
        self.cometbft_data_directory.mkdir(parents=True, exist_ok=True)
        self.ledger_data_directory.mkdir(parents=True, exist_ok=True)

    @property
    def cometbft_data_directory(self) -> Path:
        """Return the host directory containing only CometBFT state."""
        return self.root / "cometbft"

    @property
    def ledger_data_directory(self) -> Path:
        """Return the host directory containing only application state."""
        return self.root / "ledger"

    @property
    def ledger_path(self) -> Path:
        """Return the host-visible artifact ledger path."""
        return self.ledger_data_directory / "artifact-ledger.sqlite"

    @property
    def rpc(self) -> CometBFTRPCClient:
        """Return the host-local client for this node's RPC proxy."""
        return CometBFTRPCClient(url=f"http://127.0.0.1:{self.rpc_port}")

    def start(self) -> None:
        """Start this node independently and wait for host-local RPC."""
        self._compose("up", "-d", "--no-build")
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                self.rpc.status()
                return
            except (OSError, URLError, ValueError):
                time.sleep(0.1)
        raise AssertionError(f"{self.project} did not start\n{self.logs()}")

    def stop(self) -> None:
        """Stop only this node and remove its ephemeral project networks."""
        self._compose("down", "--remove-orphans", check=False)

    def node_id(self) -> str:
        """Return the node identity persisted in this project's CometBFT home."""
        result = self._compose(
            "exec",
            "-T",
            "cometbft",
            "cometbft",
            "show-node-id",
            "--home",
            "/var/lib/discovery-net/cometbft",
        )
        return result.stdout.strip()

    def peer_monikers(self) -> frozenset[str]:
        """Return the monikers currently connected through CometBFT P2P."""
        result = _rpc_call(self.rpc_port, "net_info")
        peers = result.get("peers")
        if not isinstance(peers, list):
            raise ValueError("CometBFT net_info peers must be a list")
        return frozenset(_peer_moniker(peer) for peer in peers)

    def wait_for_peers(self, expected: frozenset[str]) -> None:
        """Wait until every expected moniker is directly connected."""
        started = time.monotonic()
        deadline = started + _PEER_DISCOVERY_TIMEOUT_SECONDS
        observed: frozenset[str] = frozenset()
        while time.monotonic() < deadline:
            observed = self.peer_monikers()
            if expected <= observed:
                return
            time.sleep(0.1)
        # Say what was actually connected and for how long. The previous message
        # gave neither, so a failure meant reading a few hundred lines of
        # container log to learn that the node had simply dialled nobody.
        raise AssertionError(
            f"{self.project} did not connect to {sorted(expected)} "
            f"within {_PEER_DISCOVERY_TIMEOUT_SECONDS}s "
            f"(waited {time.monotonic() - started:.1f}s, connected to {sorted(observed)}, "
            f"missing {sorted(expected - observed)})\n{self.logs()}"
        )

    def snapshot(self) -> ArtifactLedgerSnapshot | None:
        """Load this node's committed application state from its isolated store."""
        if not self.ledger_path.exists():
            return None
        return SQLiteArtifactLedgerStore(path=self.ledger_path).load()

    def assert_remote_rpc_is_unreachable(self, remote_alias: str, remote_port: int) -> None:
        """Require both P2P-direct and Docker-host routes to reject remote RPC."""
        program = (
            "import socket\n"
            f"addresses = (({remote_alias!r}, 26657), ('host.docker.internal', {remote_port}))\n"
            "for address in addresses:\n"
            "    connection = socket.socket()\n"
            "    connection.settimeout(1)\n"
            "    try:\n"
            "        connection.connect(address)\n"
            "    except OSError:\n"
            "        continue\n"
            "    finally:\n"
            "        connection.close()\n"
            "    raise SystemExit(f'RPC unexpectedly reachable at {address}')\n"
        )
        self._compose("exec", "-T", "cometbft", "python", "-c", program)

    def inspect_service(self, service: str) -> JSONObject:
        """Return Docker's runtime description for one project service."""
        container_id = self._compose("ps", "-q", service).stdout.strip()
        if not container_id:
            raise AssertionError(f"{self.project} has no running {service} container")
        result = _run(("docker", "inspect", container_id))
        documents: object = json.loads(result.stdout)
        if not isinstance(documents, list) or len(documents) != 1:
            raise ValueError("docker inspect must return exactly one container")
        return _json_object(documents[0], "docker inspect result")

    def run_cometbft_once(self) -> subprocess.CompletedProcess[str]:
        """Run the configured consensus service once and return its exit result."""
        return self._compose("run", "--rm", "--no-deps", "cometbft", check=False)

    def logs(self) -> str:
        """Return bounded diagnostics for every service in this project."""
        return self._compose("logs", "--no-color", "--tail", "200", check=False).stdout

    def _compose(
        self,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return _run(
            ("docker", "compose", "-f", str(_COMPOSE_FILE), *arguments),
            environment=self.environment(),
            check=check,
        )

    def environment(self) -> dict[str, str]:
        """Return the complete explicit configuration for this Compose project."""
        return {
            **os.environ,
            "CHAIN_ID": self.chain_id,
            "COMETBFT_DATA_DIRECTORY": str(self.cometbft_data_directory.resolve()),
            "COMPOSE_PROJECT_NAME": self.project,
            "DISCOVERY_NET_GID": str(os.getgid()),
            "DISCOVERY_NET_IMAGE": self.image,
            "DISCOVERY_NET_UID": str(os.getuid()),
            "GENESIS_FILE": str(self.genesis_path.resolve()),
            "GENESIS_SHA256": self.genesis_sha256,
            "LEDGER_DATA_DIRECTORY": str(self.ledger_data_directory.resolve()),
            "NODE_NAME": self.project,
            "P2P_ALIAS": self.p2p_alias,
            "P2P_NETWORK": self.p2p_network,
            "PERSISTENT_PEERS": self.persistent_peers,
            "RPC_PORT": str(self.rpc_port),
        }


def build_image(image: str) -> None:
    """Build the exact runtime image used by every independent test node."""
    _run(
        (
            "docker",
            "build",
            "--tag",
            image,
            "--file",
            str(_ROOT / "localnet" / "Dockerfile"),
            str(_ROOT),
        ),
        timeout=_BUILD_TIMEOUT_SECONDS,
    )


def initialize_validator(*, image: str, data_directory: Path) -> None:
    """Create one test-only validator fixture without changing launcher scope."""
    data_directory.mkdir(parents=True)
    _run(
        (
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,source={data_directory.resolve()},target=/var/lib/discovery-net",
            image,
            "cometbft",
            "init",
            "--home",
            "/var/lib/discovery-net/cometbft",
        )
    )


def create_p2p_network(name: str) -> None:
    """Create the shared transport without granting a route to the Docker host."""
    _run(("docker", "network", "create", "--internal", name))


def remove_p2p_network(name: str) -> None:
    """Remove the exact transport created for this test run."""
    _run(("docker", "network", "rm", name), check=False)


def remove_image(image: str) -> None:
    """Remove the exact disposable image built for this test run."""
    _run(("docker", "image", "rm", image), check=False)


def available_ports(count: int) -> tuple[int, ...]:
    """Reserve and release host-loopback ports for independent RPC proxies."""
    listeners: list[socket.socket] = []
    try:
        for _ in range(count):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listeners.append(listener)
        return tuple(int(listener.getsockname()[1]) for listener in listeners)
    finally:
        for listener in listeners:
            listener.close()


def wait_for_matching_entries(nodes: tuple[DockerNode, ...], minimum_entries: int) -> None:
    """Wait until every supplied node has the same committed artifact history."""
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshots = tuple(node.snapshot() for node in nodes)
        if all(snapshot is not None for snapshot in snapshots):
            present = cast(tuple[ArtifactLedgerSnapshot, ...], snapshots)
            if (
                all(len(snapshot.entries) >= minimum_entries for snapshot in present)
                and len({snapshot.entries for snapshot in present}) == 1
            ):
                return
        time.sleep(0.1)
    diagnostics = "\n".join(f"{node.project}:\n{node.logs()}" for node in nodes)
    raise AssertionError(f"Docker nodes did not converge\n{diagnostics}")


def _rpc_call(port: int, method: str) -> JSONObject:
    request = Request(
        f"http://127.0.0.1:{port}",
        data=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}},
            separators=(",", ":"),
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        payload = _json_object(json.loads(response.read()), "CometBFT RPC response")
    if payload.get("error") is not None:
        raise ValueError(f"CometBFT RPC returned an error: {payload['error']!r}")
    return _json_object(payload.get("result"), "CometBFT RPC result")


def _peer_moniker(value: object) -> str:
    peer = _json_object(value, "CometBFT peer")
    node_info = _json_object(peer.get("node_info"), "CometBFT peer node_info")
    moniker = node_info.get("moniker")
    if not isinstance(moniker, str):
        raise ValueError("CometBFT peer moniker must be a string")
    return moniker


def _json_object(value: object, description: str) -> JSONObject:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{description} must be an object with string keys")
    return cast(JSONObject, value)


def _run(
    command: tuple[str, ...],
    *,
    environment: dict[str, str] | None = None,
    check: bool = True,
    timeout: int = _COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=check,
        env=environment,
        text=True,
        timeout=timeout,
    )
