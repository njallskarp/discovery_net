# Verifies that the inspector observes a running network and committed ledger.

from __future__ import annotations

import socket
import sys
import time
from contextlib import closing
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from discovery_net.inspector import InspectorSnapshot
from discovery_net.submission import ArtifactSubmitter
from tests.integration._background_process import BackgroundProcess
from tests.integration._integration_network import IntegrationNetwork
from tests.integration._transactions import private_key, problem_contribution

_OBSERVATION_TIMEOUT_SECONDS = 15


def test_inspector_observes_live_peers_and_newly_committed_knowledge(
    cometbft_binary: Path,
    tmp_path: Path,
) -> None:
    """Path: peers + commit → local RPC/SQLite → inspector HTTP; guards the live view."""
    with IntegrationNetwork.testnet(
        binary=cometbft_binary,
        root=tmp_path,
        validators=1,
        non_validators=1,
    ) as network:
        network.start_all()
        node = network.nodes[0]
        inspector_port = _available_loopback_port()
        inspector = BackgroundProcess(
            command=(
                sys.executable,
                "-m",
                "discovery_net.entrypoints.inspector",
                "--ledger-path",
                str(node.ledger_path),
                "--cometbft-rpc-url",
                node.rpc_url,
                "--listen-port",
                str(inspector_port),
            ),
            log_path=tmp_path / "logs" / "inspector.log",
        )
        try:
            inspector_url = f"http://127.0.0.1:{inspector_port}/api/snapshot"
            _wait_for_snapshot(inspector_url, inspector, minimum_peers=1)
            artifact = problem_contribution("Observed live through the inspector")
            receipt = ArtifactSubmitter(
                private_key=private_key(),
                cometbft_rpc_url=node.rpc_url,
            ).submit_contribution(artifact)
            committed = node.wait_for_snapshot(minimum_entries=1)

            observed = _wait_for_snapshot(
                inspector_url,
                inspector,
                minimum_height=committed.height,
                minimum_peers=1,
                contribution_title=artifact.title,
            )

            assert observed.node.chain_id == network.chain_id
            assert observed.node.latest_height >= committed.height
            assert observed.node.peers[0].moniker == network.nodes[1].name
            assert observed.node.peers[0].observed_address == "127.0.x.x"
            assert observed.knowledge_graph.indexed_height == committed.height
            assert (
                observed.knowledge_graph.contributions[0].artifact_ref == receipt.artifact_refs[0]
            )
        finally:
            inspector.stop()


def _wait_for_snapshot(
    url: str,
    process: BackgroundProcess,
    *,
    minimum_height: int = 0,
    minimum_peers: int = 0,
    contribution_title: str | None = None,
) -> InspectorSnapshot:
    deadline = time.monotonic() + _OBSERVATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        process.assert_running()
        try:
            with urlopen(url, timeout=1) as response:
                snapshot = InspectorSnapshot.model_validate_json(response.read())
            titles = {contribution.title for contribution in snapshot.knowledge_graph.contributions}
            if (
                snapshot.knowledge_graph.indexed_height >= minimum_height
                and len(snapshot.node.peers) >= minimum_peers
                and (contribution_title is None or contribution_title in titles)
            ):
                return snapshot
        except (URLError, ValueError):
            pass
        time.sleep(0.05)
    raise AssertionError(f"inspector did not expose live state\n{process.output()}")


def _available_loopback_port() -> int:
    with closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])
