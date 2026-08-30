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
from discovery_net.inspector.models import (
    InspectorContribution,
    InspectorFeedPage,
    InspectorKnowledgeGraph,
    InspectorNodeSnapshot,
    NodeObservation,
)
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
            markdown, markdown_headers = _get(f"{base_url}/vendor/markdown-it/markdown-it.min.js")
            purifier, _headers = _get(f"{base_url}/vendor/dompurify/purify.min.js")
            katex, _headers = _get(f"{base_url}/vendor/katex/katex.min.js")
            cytoscape, _headers = _get(f"{base_url}/vendor/cytoscape/cytoscape.min.js")
            font, font_headers = _get(f"{base_url}/vendor/katex/fonts/KaTeX_Main-Regular.woff2")
            snapshot_bytes, snapshot_headers = _get(f"{base_url}/api/snapshot")
            node_bytes, _headers = _get(f"{base_url}/api/node")
            graph_bytes, _headers = _get(f"{base_url}/api/graph")
            unchanged_graph_bytes, _headers = _get(f"{base_url}/api/graph?after_height=8")
            feed_bytes, _headers = _get(f"{base_url}/api/feed?limit=2")

            snapshot = InspectorSnapshot.model_validate_json(snapshot_bytes)
            node = InspectorNodeSnapshot.model_validate_json(node_bytes)
            graph = InspectorKnowledgeGraph.model_validate_json(graph_bytes)
            unchanged_graph = InspectorKnowledgeGraph.model_validate_json(unchanged_graph_bytes)
            feed = InspectorFeedPage.model_validate_json(feed_bytes)
            contribution_bytes, _headers = _get(
                f"{base_url}/api/contributions/{graph.contributions[0].artifact_ref}"
            )
            contribution = InspectorContribution.model_validate_json(contribution_bytes)
            assert b"Discovery Net Inspector" in index
            assert b".knowledge-stage" in stylesheet
            assert b"api.node()" in script
            assert b"api.graph()" in script
            assert b"api.feed()" in script
            assert b"api.contribution(ref)" in script
            assert b"markdownit" in markdown
            assert b"DOMPurify" in purifier
            assert b"katex" in katex
            assert b"cytoscape" in cytoscape
            assert font
            assert snapshot.node.chain_id == "discovery-net-demo"
            assert node.node.chain_id == "discovery-net-demo"
            assert len(snapshot.node.peers) == 4
            assert len(snapshot.knowledge_graph.contributions) == 8
            assert len(graph.contributions) == 8
            assert unchanged_graph.contributions == ()
            assert unchanged_graph.relations == ()
            assert len(feed.transactions) == 2
            assert feed.next_before is not None
            assert contribution.artifact_ref == graph.contributions[0].artifact_ref
            assert contribution.body
            assert index_headers["Content-Security-Policy"].startswith("default-src 'none'")
            assert "font-src 'self'" in index_headers["Content-Security-Policy"]
            assert "'unsafe-inline'" not in index_headers["Content-Security-Policy"]
            assert markdown_headers["Content-Type"] == "text/javascript; charset=utf-8"
            assert font_headers["Content-Type"] == "font/woff2"
            assert snapshot_headers["Cache-Control"] == "no-store"

            for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"):
                try:
                    urlopen(
                        Request(
                            f"{base_url}/api/snapshot",
                            data=b"{}",
                            method=method,
                        ),
                        timeout=2,
                    )
                except HTTPError as error:
                    assert error.code == HTTPStatus.METHOD_NOT_ALLOWED
                    assert json.loads(error.read()) == {"error": "read-only endpoint"}
                else:
                    raise AssertionError(f"the read-only inspector accepted a {method} request")

            try:
                urlopen(f"{base_url}/api/feed?limit=0", timeout=2)
            except HTTPError as error:
                assert error.code == HTTPStatus.BAD_REQUEST
                assert json.loads(error.read()) == {"error": "limit must be between 1 and 50"}
            else:
                raise AssertionError("an invalid feed page size was accepted")
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
                assert json.loads(error.read()) == {"error": "inspector data unavailable"}
            else:
                raise AssertionError("an unavailable source returned a successful snapshot")
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_inspector_ui_uses_safe_local_renderers_and_consensus_ordering() -> None:
    # The dependency-free frontend keeps rich rendering local, sanitized, and consensus ordered.
    root = Path(__file__).resolve().parents[1]
    static = root / "src" / "discovery_net" / "inspector" / "static"
    index = (static / "index.html").read_text()
    script = (static / "inspector.js").read_text()

    assert "https://" not in index
    assert "markdown-it 15.0.1" in index
    assert "DOMPurify 3.4.14" in index
    assert "KaTeX 0.18.4" in index
    assert "Cytoscape.js 3.34.2" in index
    assert "/vendor/markdown-it/markdown-it.min.js" in index
    assert "/vendor/dompurify/purify.min.js" in index
    assert "/vendor/katex/auto-render.min.js" in index
    assert "/vendor/cytoscape/cytoscape.min.js" in index
    assert "html: false" in script
    assert 'FORBID_ATTR: ["style"]' in script
    assert "trust: false" in script
    assert "throwOnError: false" in script
    assert 'roots: "#mathematics-root"' in script
    assert "nodeDimensionsIncludeLabels: true" in script
    assert "artifact.artifact_index" in script


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
