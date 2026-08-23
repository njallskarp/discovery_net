"""Peer node HTTP service."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import FastAPI, HTTPException

from discovery_net_poc.crypto import (
    ArtifactVerificationError,
    KeyPair,
    verify_artifact,
)
from discovery_net_poc.protocol import (
    AgentRegistration,
    ArtifactType,
    ClaimRequest,
    ContributionPayload,
    ContributionRequest,
    PeerRequest,
    ReviewPayload,
    ReviewRequest,
    SignedArtifact,
    SyncRequest,
)
from discovery_net_poc.store import NodeStore, StoreNotFoundError


def now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class NodeConfig:
    database_path: Path
    key_path: Path
    public_url: str
    coordinator_url: str | None = None
    peers: tuple[str, ...] = ()


class NodeService:
    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.store = NodeStore(config.database_path)
        self.key_pair = KeyPair.load_or_create(config.key_path)
        for peer in config.peers:
            self.store.add_peer(peer)

    @property
    def agent_id(self) -> str:
        return self.key_pair.agent_id

    async def register(self) -> dict[str, Any]:
        if self.config.coordinator_url is None:
            raise HTTPException(status_code=503, detail="node has no coordinator")
        registration = AgentRegistration(
            agent_id=self.agent_id,
            public_key=self.key_pair.public_key_encoded,
            node_url=self.config.public_url.rstrip("/"),
        )
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(
                    f"{self.config.coordinator_url.rstrip('/')}/agents",
                    json=registration.model_dump(mode="json"),
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"coordinator unavailable: {exc}") from exc

    async def _send_to_peer(self, peer: str, artifact: SignedArtifact) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.post(
                    f"{peer.rstrip('/')}/objects", json=artifact.model_dump(mode="json")
                )
            return {"peer": peer, "status": response.status_code}
        except httpx.HTTPError as exc:
            return {"peer": peer, "error": str(exc)}

    async def broadcast(self, artifact: SignedArtifact) -> list[dict[str, Any]]:
        peers = [
            peer
            for peer in self.store.list_peers()
            if peer.rstrip("/") != self.config.public_url.rstrip("/")
        ]
        if not peers:
            return []
        results = await asyncio.gather(*(self._send_to_peer(peer, artifact) for peer in peers))
        return list(results)

    async def coordinator_post(self, path: str, document: dict[str, Any]) -> dict[str, Any]:
        if self.config.coordinator_url is None:
            raise HTTPException(status_code=503, detail="node has no coordinator")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.config.coordinator_url.rstrip('/')}{path}", json=document
                )
            if response.status_code >= 400:
                detail = response.json().get("detail", response.text)
                raise HTTPException(status_code=response.status_code, detail=detail)
            return cast(dict[str, Any], response.json())
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"coordinator unavailable: {exc}") from exc


def create_node_app(config: NodeConfig) -> FastAPI:
    service = NodeService(config)
    app = FastAPI(title="Discovery Net Node", version="0.1.0")
    app.state.service = service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "agent_id": service.agent_id}

    @app.get("/identity")
    def identity() -> dict[str, str]:
        return {
            "agent_id": service.agent_id,
            "public_key": service.key_pair.public_key_encoded,
            "public_url": config.public_url,
        }

    @app.post("/coordinator/register")
    async def register() -> dict[str, Any]:
        return await service.register()

    @app.get("/peers")
    def peers() -> list[str]:
        return service.store.list_peers()

    @app.post("/peers")
    def add_peer(request: PeerRequest) -> dict[str, str]:
        service.store.add_peer(request.url)
        return {"status": "stored", "url": request.url.rstrip("/")}

    @app.get("/objects")
    def objects() -> list[dict[str, Any]]:
        return [artifact.model_dump(mode="json") for artifact in service.store.list_artifacts()]

    @app.get("/objects/{artifact_id}")
    def object_by_id(artifact_id: str) -> dict[str, Any]:
        try:
            return service.store.get_artifact(artifact_id).model_dump(mode="json")
        except StoreNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/objects")
    async def ingest(artifact: SignedArtifact) -> dict[str, Any]:
        try:
            verify_artifact(artifact)
        except ArtifactVerificationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        created = service.store.put_artifact(artifact)
        propagated: list[dict[str, Any]] = []
        if created:
            propagated = await service.broadcast(artifact)
        return {"created": created, "propagated": propagated}

    @app.post("/sync")
    async def sync(request: SyncRequest) -> dict[str, int]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{request.peer_url.rstrip('/')}/objects")
                response.raise_for_status()
            received = 0
            for document in response.json():
                artifact = SignedArtifact.model_validate(document)
                verify_artifact(artifact)
                if service.store.put_artifact(artifact):
                    received += 1
            service.store.add_peer(request.peer_url)
            return {"received": received}
        except (httpx.HTTPError, ArtifactVerificationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/contributions")
    async def create_contribution(request: ContributionRequest) -> dict[str, Any]:
        contribution_id = str(uuid.uuid4())
        thread_root_id = request.thread_root_id or contribution_id
        payload = ContributionPayload(
            contribution_id=contribution_id,
            author_id=service.agent_id,
            kind=request.kind,
            title=request.title,
            body=request.body,
            thread_root_id=thread_root_id,
            parent_id=request.parent_id,
            review_policy_version=request.review_policy_version,
            created_at=now(),
        )
        artifact = service.key_pair.sign_artifact(
            ArtifactType.CONTRIBUTION, payload.model_dump(mode="json")
        )
        service.store.put_artifact(artifact)
        await service.register()
        broadcast_result, coordinator_result = await asyncio.gather(
            service.broadcast(artifact),
            service.coordinator_post("/submissions", artifact.model_dump(mode="json")),
        )
        return {
            "artifact": artifact.model_dump(mode="json"),
            "coordinator": coordinator_result,
            "peers": broadcast_result,
        }

    @app.post("/assignments/claim")
    async def claim_assignment() -> dict[str, Any]:
        await service.register()
        result = await service.coordinator_post(
            "/assignments/claim", ClaimRequest(reviewer_id=service.agent_id).model_dump(mode="json")
        )
        for name in ("assignment", "contribution"):
            artifact = SignedArtifact.model_validate(result[name])
            verify_artifact(artifact)
            service.store.put_artifact(artifact)
        return result

    @app.post("/reviews")
    async def create_review(request: ReviewRequest) -> dict[str, Any]:
        payload = ReviewPayload(
            review_id=str(uuid.uuid4()),
            assignment_id=request.assignment_id,
            reviewer_id=service.agent_id,
            target_contribution_id=request.target_contribution_id,
            verdict=request.verdict,
            body=request.body,
            created_at=now(),
        )
        artifact = service.key_pair.sign_artifact(
            ArtifactType.REVIEW, payload.model_dump(mode="json")
        )
        service.store.put_artifact(artifact)
        broadcast_result, coordinator_result = await asyncio.gather(
            service.broadcast(artifact),
            service.coordinator_post("/reviews", artifact.model_dump(mode="json")),
        )
        event = SignedArtifact.model_validate(coordinator_result["event"])
        verify_artifact(event)
        service.store.put_artifact(event)
        return {
            "artifact": artifact.model_dump(mode="json"),
            "coordinator": coordinator_result,
            "peers": broadcast_result,
        }

    return app
