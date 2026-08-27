from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import closing
from http import HTTPStatus
from http.client import HTTPMessage
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from discovery_net.inspector import InspectorService, InspectorSnapshot
from discovery_net.inspector.models import NodeObservation
from discovery_net.inspector.seed import SeedArtifactLedgerReader, seeded_inspector_service
from discovery_net.inspector.server import InspectorServer
from discovery_net.node import ArtifactLedgerSnapshot


def test_server_exposes_the_browser_and_snapshot_without_write_routes() -> None:
    # One local server serves its UI and sanitized snapshot while refusing mutations.
    with InspectorServer(
        service=seeded_inspector_service(),
        listen_host="127.0.0.1",
        listen_port=0,
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://{server.listen_host}:{server.listen_port}"
            index, index_headers = _get(f"{base_url}/")
            stylesheet, _headers = _get(f"{base_url}/inspector.css")
            script, _headers = _get(f"{base_url}/inspector.js")
            snapshot_bytes, snapshot_headers = _get(f"{base_url}/api/snapshot")

            snapshot = InspectorSnapshot.model_validate_json(snapshot_bytes)
            assert b"Discovery Net Inspector" in index
            assert b".knowledge-stage" in stylesheet
            assert b'fetch("/api/snapshot"' in script
            assert snapshot.node.chain_id == "discovery-net-demo"
            assert len(snapshot.node.peers) == 4
            assert len(snapshot.knowledge_graph.contributions) == 8
            assert index_headers["Content-Security-Policy"].startswith("default-src 'none'")
            assert snapshot_headers["Cache-Control"] == "no-store"

            try:
                urlopen(Request(f"{base_url}/api/snapshot", data=b"{}"), timeout=2)
            except HTTPError as error:
                assert error.code == HTTPStatus.METHOD_NOT_ALLOWED
                assert json.loads(error.read()) == {"error": "read-only endpoint"}
            else:
                raise AssertionError("the read-only inspector accepted a POST request")
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_server_reports_an_unavailable_observation_without_leaking_details() -> None:
    # Source failures become a stable service response rather than exposing internals.
    service = InspectorService(
        node_source=_FailingNodeSource(),
        ledger_reader=SeedArtifactLedgerReader(
            snapshot=ArtifactLedgerSnapshot(height=0, entries=())
        ),
    )
    with InspectorServer(service=service, listen_host="127.0.0.1", listen_port=0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://{server.listen_host}:{server.listen_port}/api/snapshot"
            try:
                urlopen(url, timeout=2)
            except HTTPError as error:
                assert error.code == HTTPStatus.SERVICE_UNAVAILABLE
                assert json.loads(error.read()) == {"error": "inspector snapshot unavailable"}
            else:
                raise AssertionError("an unavailable source returned a successful snapshot")
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_inspector_process_starts_the_seeded_application() -> None:
    # The installed-style entrypoint composes the real service and HTTP server end to end.
    port = _available_loopback_port()
    root = Path(__file__).resolve().parents[1]
    environment = os.environ | {"PYTHONPATH": str(root / "src")}
    process = subprocess.Popen(
        (
            sys.executable,
            "-m",
            "discovery_net.entrypoints.inspector",
            "--demo",
            "--listen-port",
            str(port),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    try:
        snapshot = _wait_for_snapshot(f"http://127.0.0.1:{port}/api/snapshot")
        assert snapshot.node.application_height == 8
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        _stdout, stderr = process.communicate(timeout=5)

    assert process.returncode == 0, stderr.decode()


class _FailingNodeSource:
    def observe(self) -> NodeObservation:
        raise OSError("private source failure")


def _get(url: str) -> tuple[bytes, HTTPMessage]:
    with urlopen(url, timeout=2) as response:
        assert response.status == HTTPStatus.OK
        return response.read(), response.headers


def _available_loopback_port() -> int:
    with closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_snapshot(url: str) -> InspectorSnapshot:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:
                return InspectorSnapshot.model_validate_json(response.read())
        except URLError:
            time.sleep(0.05)
    raise AssertionError("inspector process did not start within five seconds")
