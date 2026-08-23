from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from discovery_net_poc.crypto import KeyPair
from discovery_net_poc.node_app import NodeConfig, create_node_app
from discovery_net_poc.protocol import ArtifactType


def test_node_stores_verified_objects_and_peers(tmp_path: Path) -> None:
    app = create_node_app(
        NodeConfig(
            database_path=tmp_path / "node.sqlite3",
            key_path=tmp_path / "node-key.json",
            public_url="http://node.test",
        )
    )
    artifact = KeyPair.generate().sign_artifact(
        ArtifactType.CONTRIBUTION, {"title": "A signed artifact"}
    )

    with TestClient(app) as client:
        stored = client.post("/objects", json=artifact.model_dump(mode="json"))
        duplicate = client.post("/objects", json=artifact.model_dump(mode="json"))
        peer = client.post("/peers", json={"url": "http://peer.test/"})
        objects = client.get("/objects")

    assert stored.status_code == 200
    assert stored.json()["created"] is True
    assert duplicate.json()["created"] is False
    assert peer.json()["url"] == "http://peer.test"
    assert objects.json()[0]["artifact_id"] == artifact.artifact_id
