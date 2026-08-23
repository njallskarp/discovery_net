"""Review coordinator HTTP service."""

from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import httpx
from fastapi import FastAPI, HTTPException

from discovery_net_poc.crypto import (
    ArtifactVerificationError,
    KeyPair,
    agent_id_from_public_key,
    verify_artifact,
)
from discovery_net_poc.protocol import (
    AgentRegistration,
    ArtifactType,
    ClaimRequest,
    ContributionKind,
    ContributionPayload,
    CoordinatorEventPayload,
    ReviewPayload,
    ReviewPolicy,
    SignedArtifact,
)
from discovery_net_poc.store import (
    CoordinatorStore,
    StoreConflictError,
    StoreNotFoundError,
    StorePermissionError,
)


def now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_RUBRICS: dict[ContributionKind, str] = {
    ContributionKind.MATHEMATICAL_AREA: (
        "Confirm that this is a real, non-duplicate area of mathematics."
    ),
    ContributionKind.PROBLEM_STATEMENT: (
        "Confirm that the problem is coherent, non-duplicate, and mathematically meaningful."
    ),
    ContributionKind.CONJECTURE: (
        "Confirm that the conjecture is coherent, relevant, and not an obvious duplicate."
    ),
    ContributionKind.QUESTION: "Confirm that the question is clear, relevant, and adds value.",
    ContributionKind.FINDING: (
        "Confirm that the finding is coherent, relevant, and supported by its explanation."
    ),
    ContributionKind.LEMMA: "Confirm that the lemma is clearly stated and useful in context.",
    ContributionKind.PROOF_ATTEMPT: (
        "Confirm that the proof attempt is coherent and merits mathematical scrutiny."
    ),
    ContributionKind.COUNTEREXAMPLE: (
        "Confirm that the counterexample is clearly specified and relevant."
    ),
    ContributionKind.OBJECTION: (
        "Confirm that the objection identifies a concrete mathematical concern."
    ),
    ContributionKind.REPRODUCTION: "Confirm that the reproduction describes an independent check.",
    ContributionKind.FORMALIZATION: (
        "Confirm that the formalization identifies its system and target precisely."
    ),
    ContributionKind.SUMMARY: (
        "Confirm that the summary accurately and usefully organizes the thread."
    ),
    ContributionKind.DISCUSSION: (
        "Confirm that the discussion is relevant and contributes substantive information."
    ),
}


@dataclass(frozen=True, slots=True)
class CoordinatorConfig:
    database_path: Path
    key_path: Path
    default_reviewer_count: int = 2


class CoordinatorService:
    def __init__(self, config: CoordinatorConfig) -> None:
        self.config = config
        self.store = CoordinatorStore(config.database_path)
        self.key_pair = KeyPair.load_or_create(config.key_path)
        for kind, rubric in DEFAULT_RUBRICS.items():
            self.store.put_policy(
                ReviewPolicy(
                    contribution_kind=kind,
                    policy_version="v1",
                    rubric=rubric,
                    reviewer_count=config.default_reviewer_count,
                    approval_threshold=config.default_reviewer_count,
                    rejection_threshold=1,
                )
            )

    @property
    def coordinator_id(self) -> str:
        return self.key_pair.agent_id

    def event(self, event_type: str, data: dict[str, Any]) -> SignedArtifact:
        timestamp = now()
        payload = CoordinatorEventPayload(
            event_id=str(uuid.uuid4()),
            coordinator_id=self.coordinator_id,
            event_type=event_type,
            data=data,
            created_at=timestamp,
        )
        artifact = self.key_pair.sign_artifact(
            ArtifactType.COORDINATOR_EVENT, payload.model_dump(mode="json")
        )
        self.store.add_event(artifact, event_type, timestamp)
        return artifact

    async def broadcast(self, artifact: SignedArtifact) -> None:
        urls = self.store.list_agent_urls()
        async with httpx.AsyncClient(timeout=2.0) as client:
            await asyncio.gather(
                *(
                    client.post(f"{url}/objects", json=artifact.model_dump(mode="json"))
                    for url in urls
                ),
                return_exceptions=True,
            )


def _raise_http(exc: Exception) -> NoReturn:
    if isinstance(exc, StoreNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, StorePermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, StoreConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ArtifactVerificationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def create_coordinator_app(config: CoordinatorConfig) -> FastAPI:
    service = CoordinatorService(config)
    app = FastAPI(title="Discovery Net Coordinator", version="0.1.0")
    app.state.service = service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "coordinator_id": service.coordinator_id}

    @app.get("/identity")
    def identity() -> dict[str, str]:
        return {
            "coordinator_id": service.coordinator_id,
            "public_key": service.key_pair.public_key_encoded,
        }

    @app.post("/agents")
    def register_agent(registration: AgentRegistration) -> dict[str, str]:
        try:
            public_key = base64.urlsafe_b64decode(registration.public_key.encode("ascii"))
            if agent_id_from_public_key(public_key) != registration.agent_id:
                raise ArtifactVerificationError("agent ID does not match the public key")
            service.store.register_agent(registration)
        except Exception as exc:
            _raise_http(exc)
        return {"status": "registered", "agent_id": registration.agent_id}

    @app.get("/policies")
    def policies() -> list[dict[str, Any]]:
        return service.store.list_policies()

    @app.put("/policies")
    def put_policy(policy: ReviewPolicy) -> dict[str, str]:
        service.store.put_policy(policy)
        return {
            "status": "stored",
            "kind": policy.contribution_kind.value,
            "version": policy.policy_version,
        }

    @app.post("/submissions")
    async def submit(artifact: SignedArtifact) -> dict[str, Any]:
        try:
            verify_artifact(artifact)
            if artifact.artifact_type is not ArtifactType.CONTRIBUTION:
                raise ArtifactVerificationError("submission must contain a contribution")
            payload = ContributionPayload.model_validate(artifact.payload)
            if payload.author_id != artifact.signer_id:
                raise ArtifactVerificationError("contribution author does not match its signer")
            created = service.store.put_submission(artifact, payload)
            state = service.store.contribution_state(payload.contribution_id)
            if created:
                event = service.event(
                    "submission_accepted",
                    {
                        "contribution_id": payload.contribution_id,
                        "artifact_id": artifact.artifact_id,
                        "status": state["status"],
                    },
                )
                await service.broadcast(event)
            return {"created": created, "state": state}
        except Exception as exc:
            _raise_http(exc)

    @app.post("/assignments/claim")
    async def claim(request: ClaimRequest) -> dict[str, Any]:
        try:
            issued_at = now()
            record = service.store.claim_assignment(request.reviewer_id, issued_at)
            assignment = service.event(
                "review_assigned",
                {
                    "assignment_id": record.assignment_id,
                    "target_contribution_id": record.contribution_id,
                    "reviewer_id": record.reviewer_id,
                    "review_policy_version": record.policy_version,
                    "contribution_artifact_id": record.contribution_artifact.artifact_id,
                    "issued_at": record.issued_at,
                },
            )
            service.store.attach_assignment_event(record.assignment_id, assignment.artifact_id)
            await service.broadcast(assignment)
            return {
                "assignment": assignment.model_dump(mode="json"),
                "contribution": record.contribution_artifact.model_dump(mode="json"),
            }
        except Exception as exc:
            _raise_http(exc)

    @app.post("/reviews")
    async def review(artifact: SignedArtifact) -> dict[str, Any]:
        try:
            verify_artifact(artifact)
            if artifact.artifact_type is not ArtifactType.REVIEW:
                raise ArtifactVerificationError("review endpoint requires a review artifact")
            payload = ReviewPayload.model_validate(artifact.payload)
            if payload.reviewer_id != artifact.signer_id:
                raise ArtifactVerificationError("reviewer does not match the artifact signer")
            state = service.store.put_review(artifact, payload, now())
            event = service.event(
                "review_recorded",
                {
                    "review_artifact_id": artifact.artifact_id,
                    "reviewer_id": payload.reviewer_id,
                    "state": state,
                },
            )
            await service.broadcast(event)
            return {"state": state, "event": event.model_dump(mode="json")}
        except Exception as exc:
            _raise_http(exc)

    @app.get("/states/{contribution_id}")
    def state(contribution_id: str) -> dict[str, Any]:
        try:
            return service.store.contribution_state(contribution_id)
        except Exception as exc:
            _raise_http(exc)

    @app.get("/feed")
    def feed() -> list[dict[str, Any]]:
        return service.store.published_feed()

    @app.get("/agents/{agent_id}/reputation")
    def reputation(agent_id: str) -> dict[str, Any]:
        try:
            return {"agent_id": agent_id, "karma": service.store.agent_reputation(agent_id)}
        except Exception as exc:
            _raise_http(exc)

    @app.get("/events")
    def events() -> list[dict[str, Any]]:
        return service.store.list_events()

    return app
