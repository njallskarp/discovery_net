from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from discovery_net_poc.coordinator_app import CoordinatorConfig, create_coordinator_app
from discovery_net_poc.crypto import KeyPair
from discovery_net_poc.protocol import (
    ArtifactType,
    ContributionKind,
    ContributionPayload,
    ReviewPayload,
    ReviewVerdict,
)


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def register(client: TestClient, key_pair: KeyPair) -> None:
    response = client.post(
        "/agents",
        json={
            "agent_id": key_pair.agent_id,
            "public_key": key_pair.public_key_encoded,
            "node_url": "http://127.0.0.1:9",
        },
    )
    assert response.status_code == 200


def signed_review(
    reviewer: KeyPair, assignment: dict[str, Any], contribution_id: str
) -> dict[str, Any]:
    payload = ReviewPayload(
        review_id=str(uuid.uuid4()),
        assignment_id=assignment["assignment_id"],
        reviewer_id=reviewer.agent_id,
        target_contribution_id=contribution_id,
        verdict=ReviewVerdict.APPROVE,
        body="The contribution is coherent and not duplicated.",
        created_at=timestamp(),
    )
    return reviewer.sign_artifact(ArtifactType.REVIEW, payload.model_dump(mode="json")).model_dump(
        mode="json"
    )


def test_two_independent_reviews_publish_a_contribution(tmp_path: Path) -> None:
    app = create_coordinator_app(
        CoordinatorConfig(
            database_path=tmp_path / "coordinator.sqlite3",
            key_path=tmp_path / "coordinator-key.json",
            default_reviewer_count=2,
        )
    )

    async def skip_broadcast(_artifact: object) -> None:
        return None

    app.state.service.broadcast = skip_broadcast
    author, reviewer_a, reviewer_b = (KeyPair.generate() for _ in range(3))

    with TestClient(app) as client:
        for agent in (author, reviewer_a, reviewer_b):
            register(client, agent)

        contribution_id = str(uuid.uuid4())
        contribution = ContributionPayload(
            contribution_id=contribution_id,
            author_id=author.agent_id,
            kind=ContributionKind.PROBLEM_STATEMENT,
            title="A finite-field incidence problem",
            body="Determine the sharp upper bound.",
            thread_root_id=contribution_id,
            review_policy_version="v1",
            created_at=timestamp(),
        )
        artifact = author.sign_artifact(
            ArtifactType.CONTRIBUTION, contribution.model_dump(mode="json")
        )
        submitted = client.post("/submissions", json=artifact.model_dump(mode="json"))
        assert submitted.status_code == 200
        assert submitted.json()["state"]["status"] == "awaiting_review"

        self_assignment = client.post("/assignments/claim", json={"reviewer_id": author.agent_id})
        assert self_assignment.status_code == 404

        first_claim = client.post("/assignments/claim", json={"reviewer_id": reviewer_a.agent_id})
        first_assignment = first_claim.json()["assignment"]["payload"]["data"]
        first_review = client.post(
            "/reviews", json=signed_review(reviewer_a, first_assignment, contribution_id)
        )
        assert first_review.json()["state"]["status"] == "under_review"

        duplicate_claim = client.post(
            "/assignments/claim", json={"reviewer_id": reviewer_a.agent_id}
        )
        assert duplicate_claim.status_code == 404

        second_claim = client.post("/assignments/claim", json={"reviewer_id": reviewer_b.agent_id})
        second_assignment = second_claim.json()["assignment"]["payload"]["data"]
        second_review = client.post(
            "/reviews", json=signed_review(reviewer_b, second_assignment, contribution_id)
        )
        assert second_review.json()["state"]["status"] == "published"

        state = client.get(f"/states/{contribution_id}").json()
        feed = client.get("/feed").json()
        reputation = client.get(f"/agents/{reviewer_a.agent_id}/reputation").json()

    assert state["approvals"] == 2
    assert len(feed) == 1
    assert reputation["karma"] == 1
