"""SQLite persistence for peer nodes and the coordinator."""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discovery_net_poc.crypto import canonical_json
from discovery_net_poc.protocol import (
    AgentRegistration,
    AssignmentStatus,
    ContributionPayload,
    PublicationStatus,
    ReviewPayload,
    ReviewPolicy,
    ReviewVerdict,
    SignedArtifact,
)


class StoreConflictError(ValueError):
    """Raised when an operation conflicts with durable state."""


class StoreNotFoundError(LookupError):
    """Raised when an expected record does not exist."""


class StorePermissionError(PermissionError):
    """Raised when an agent is not eligible for an operation."""


def _json(value: Any) -> str:
    return canonical_json(value).decode("utf-8")


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class NodeStore(SQLiteStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    artifact_type TEXT NOT NULL,
                    signer_id TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS peers (
                    url TEXT PRIMARY KEY,
                    added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def put_artifact(self, artifact: SignedArtifact) -> bool:
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO artifacts (
                    artifact_id, artifact_type, signer_id, envelope_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.artifact_type.value,
                    artifact.signer_id,
                    artifact.model_dump_json(),
                ),
            )
            return cursor.rowcount == 1

    def get_artifact(self, artifact_id: str) -> SignedArtifact:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT envelope_json FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise StoreNotFoundError("artifact not found")
        return SignedArtifact.model_validate_json(row["envelope_json"])

    def list_artifacts(self) -> list[SignedArtifact]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT envelope_json FROM artifacts ORDER BY received_at, artifact_id"
            ).fetchall()
        return [SignedArtifact.model_validate_json(row["envelope_json"]) for row in rows]

    def add_peer(self, url: str) -> None:
        with self.connection() as connection:
            connection.execute("INSERT OR IGNORE INTO peers (url) VALUES (?)", (url.rstrip("/"),))

    def list_peers(self) -> list[str]:
        with self.connection() as connection:
            rows = connection.execute("SELECT url FROM peers ORDER BY url").fetchall()
        return [str(row["url"]) for row in rows]


@dataclass(frozen=True, slots=True)
class AssignmentRecord:
    assignment_id: str
    contribution_id: str
    reviewer_id: str
    issued_at: str
    contribution_artifact: SignedArtifact
    policy_version: str


class CoordinatorStore(SQLiteStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL,
                    node_url TEXT NOT NULL,
                    karma INTEGER NOT NULL DEFAULT 0,
                    registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS policies (
                    contribution_kind TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    rubric TEXT NOT NULL,
                    reviewer_count INTEGER NOT NULL,
                    approval_threshold INTEGER NOT NULL,
                    rejection_threshold INTEGER NOT NULL,
                    minimum_author_karma INTEGER NOT NULL,
                    minimum_reviewer_karma INTEGER NOT NULL,
                    PRIMARY KEY (contribution_kind, policy_version)
                );

                CREATE TABLE IF NOT EXISTS contributions (
                    contribution_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL UNIQUE,
                    author_id TEXT NOT NULL REFERENCES agents(agent_id),
                    kind TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    submitted_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assignments (
                    assignment_id TEXT PRIMARY KEY,
                    contribution_id TEXT NOT NULL REFERENCES contributions(contribution_id),
                    reviewer_id TEXT NOT NULL REFERENCES agents(agent_id),
                    status TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    resolved_at TEXT,
                    event_artifact_id TEXT,
                    UNIQUE (contribution_id, reviewer_id)
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL UNIQUE,
                    assignment_id TEXT NOT NULL UNIQUE REFERENCES assignments(assignment_id),
                    contribution_id TEXT NOT NULL REFERENCES contributions(contribution_id),
                    reviewer_id TEXT NOT NULL REFERENCES agents(agent_id),
                    verdict TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    submitted_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    artifact_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def register_agent(self, registration: AgentRegistration) -> None:
        with self.connection() as connection:
            existing = connection.execute(
                "SELECT public_key FROM agents WHERE agent_id = ?", (registration.agent_id,)
            ).fetchone()
            if existing is not None and existing["public_key"] != registration.public_key:
                raise StoreConflictError("an agent ID cannot be registered with a different key")
            connection.execute(
                """
                INSERT INTO agents (agent_id, public_key, node_url)
                VALUES (?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET node_url = excluded.node_url
                """,
                (registration.agent_id, registration.public_key, registration.node_url.rstrip("/")),
            )

    def list_agent_urls(self) -> list[str]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT node_url FROM agents ORDER BY node_url"
            ).fetchall()
        return [str(row["node_url"]) for row in rows]

    def agent_reputation(self, agent_id: str) -> int:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT karma FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            raise StoreNotFoundError("agent not found")
        return int(row["karma"])

    def put_policy(self, policy: ReviewPolicy) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO policies (
                    contribution_kind, policy_version, rubric, reviewer_count,
                    approval_threshold, rejection_threshold, minimum_author_karma,
                    minimum_reviewer_karma
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contribution_kind, policy_version) DO UPDATE SET
                    rubric = excluded.rubric,
                    reviewer_count = excluded.reviewer_count,
                    approval_threshold = excluded.approval_threshold,
                    rejection_threshold = excluded.rejection_threshold,
                    minimum_author_karma = excluded.minimum_author_karma,
                    minimum_reviewer_karma = excluded.minimum_reviewer_karma
                """,
                (
                    policy.contribution_kind.value,
                    policy.policy_version,
                    policy.rubric,
                    policy.reviewer_count,
                    policy.approval_threshold,
                    policy.rejection_threshold,
                    policy.minimum_author_karma,
                    policy.minimum_reviewer_karma,
                ),
            )

    def list_policies(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM policies
                ORDER BY contribution_kind, policy_version
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def put_submission(self, artifact: SignedArtifact, payload: ContributionPayload) -> bool:
        with self.connection() as connection:
            agent = connection.execute(
                "SELECT karma FROM agents WHERE agent_id = ?", (payload.author_id,)
            ).fetchone()
            if agent is None:
                raise StorePermissionError("the author must register before submitting")
            policy = connection.execute(
                """
                SELECT minimum_author_karma FROM policies
                WHERE contribution_kind = ? AND policy_version = ?
                """,
                (payload.kind.value, payload.review_policy_version),
            ).fetchone()
            if policy is None:
                raise StoreNotFoundError("review policy not found")
            if int(agent["karma"]) < int(policy["minimum_author_karma"]):
                raise StorePermissionError("the author does not have enough karma")

            existing = connection.execute(
                "SELECT artifact_id FROM contributions WHERE contribution_id = ?",
                (payload.contribution_id,),
            ).fetchone()
            if existing is not None:
                if existing["artifact_id"] != artifact.artifact_id:
                    raise StoreConflictError("contribution ID already contains different content")
                return False

            connection.execute(
                """
                INSERT INTO contributions (
                    contribution_id, artifact_id, author_id, kind, policy_version,
                    title, status, envelope_json, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.contribution_id,
                    artifact.artifact_id,
                    payload.author_id,
                    payload.kind.value,
                    payload.review_policy_version,
                    payload.title,
                    PublicationStatus.AWAITING_REVIEW.value,
                    artifact.model_dump_json(),
                    payload.created_at,
                ),
            )
            return True

    def claim_assignment(self, reviewer_id: str, issued_at: str) -> AssignmentRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            reviewer = connection.execute(
                "SELECT karma FROM agents WHERE agent_id = ?", (reviewer_id,)
            ).fetchone()
            if reviewer is None:
                raise StorePermissionError("the reviewer must register before claiming work")

            rows = connection.execute(
                """
                SELECT c.*, p.reviewer_count, p.minimum_reviewer_karma
                FROM contributions AS c
                JOIN policies AS p
                  ON p.contribution_kind = c.kind AND p.policy_version = c.policy_version
                WHERE c.status IN (?, ?)
                  AND c.author_id <> ?
                  AND p.minimum_reviewer_karma <= ?
                  AND NOT EXISTS (
                      SELECT 1 FROM assignments AS mine
                      WHERE mine.contribution_id = c.contribution_id
                        AND mine.reviewer_id = ?
                  )
                  AND (
                      SELECT COUNT(*) FROM assignments AS occupied
                      WHERE occupied.contribution_id = c.contribution_id
                        AND occupied.status IN (?, ?)
                  ) < p.reviewer_count
                """,
                (
                    PublicationStatus.AWAITING_REVIEW.value,
                    PublicationStatus.UNDER_REVIEW.value,
                    reviewer_id,
                    int(reviewer["karma"]),
                    reviewer_id,
                    AssignmentStatus.ASSIGNED.value,
                    AssignmentStatus.COMPLETED.value,
                ),
            ).fetchall()
            if not rows:
                raise StoreNotFoundError("no eligible contribution is available")

            selected = secrets.choice(rows)
            assignment_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO assignments (
                    assignment_id, contribution_id, reviewer_id, status, issued_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    assignment_id,
                    selected["contribution_id"],
                    reviewer_id,
                    AssignmentStatus.ASSIGNED.value,
                    issued_at,
                ),
            )
            connection.execute(
                "UPDATE contributions SET status = ? WHERE contribution_id = ?",
                (PublicationStatus.UNDER_REVIEW.value, selected["contribution_id"]),
            )
            connection.commit()
            return AssignmentRecord(
                assignment_id=assignment_id,
                contribution_id=str(selected["contribution_id"]),
                reviewer_id=reviewer_id,
                issued_at=issued_at,
                contribution_artifact=SignedArtifact.model_validate_json(selected["envelope_json"]),
                policy_version=str(selected["policy_version"]),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def attach_assignment_event(self, assignment_id: str, artifact_id: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE assignments SET event_artifact_id = ? WHERE assignment_id = ?",
                (artifact_id, assignment_id),
            )

    def put_review(
        self, artifact: SignedArtifact, payload: ReviewPayload, resolved_at: str
    ) -> dict[str, Any]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT contribution_id FROM reviews WHERE artifact_id = ?",
                (artifact.artifact_id,),
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._state_with_connection(connection, str(existing["contribution_id"]))

            assignment = connection.execute(
                "SELECT * FROM assignments WHERE assignment_id = ?", (payload.assignment_id,)
            ).fetchone()
            if assignment is None:
                raise StoreNotFoundError("review assignment not found")
            if assignment["status"] != AssignmentStatus.ASSIGNED.value:
                raise StoreConflictError("review assignment is no longer active")
            if assignment["reviewer_id"] != payload.reviewer_id:
                raise StorePermissionError("reviewer does not own this assignment")
            if assignment["contribution_id"] != payload.target_contribution_id:
                raise StoreConflictError("review target does not match its assignment")

            connection.execute(
                """
                INSERT INTO reviews (
                    review_id, artifact_id, assignment_id, contribution_id,
                    reviewer_id, verdict, envelope_json, submitted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.review_id,
                    artifact.artifact_id,
                    payload.assignment_id,
                    payload.target_contribution_id,
                    payload.reviewer_id,
                    payload.verdict.value,
                    artifact.model_dump_json(),
                    payload.created_at,
                ),
            )
            connection.execute(
                """
                UPDATE assignments SET status = ?, resolved_at = ?
                WHERE assignment_id = ?
                """,
                (AssignmentStatus.COMPLETED.value, resolved_at, payload.assignment_id),
            )
            connection.execute(
                "UPDATE agents SET karma = karma + 1 WHERE agent_id = ?",
                (payload.reviewer_id,),
            )

            counts = connection.execute(
                """
                SELECT
                  SUM(CASE WHEN verdict = ? THEN 1 ELSE 0 END) AS approvals,
                  SUM(CASE WHEN verdict = ? THEN 1 ELSE 0 END) AS rejections
                FROM reviews WHERE contribution_id = ?
                """,
                (
                    ReviewVerdict.APPROVE.value,
                    ReviewVerdict.REJECT.value,
                    payload.target_contribution_id,
                ),
            ).fetchone()
            policy = connection.execute(
                """
                SELECT p.* FROM policies AS p
                JOIN contributions AS c
                  ON c.kind = p.contribution_kind AND c.policy_version = p.policy_version
                WHERE c.contribution_id = ?
                """,
                (payload.target_contribution_id,),
            ).fetchone()
            if policy is None:
                raise StoreNotFoundError("review policy not found")

            approvals = int(counts["approvals"] or 0)
            rejections = int(counts["rejections"] or 0)
            status = PublicationStatus.UNDER_REVIEW
            if approvals >= int(policy["approval_threshold"]):
                status = PublicationStatus.PUBLISHED
            elif rejections >= int(policy["rejection_threshold"]):
                status = PublicationStatus.REJECTED

            connection.execute(
                "UPDATE contributions SET status = ? WHERE contribution_id = ?",
                (status.value, payload.target_contribution_id),
            )
            if status in {PublicationStatus.PUBLISHED, PublicationStatus.REJECTED}:
                connection.execute(
                    """
                    UPDATE assignments SET status = ?, resolved_at = ?
                    WHERE contribution_id = ? AND status = ?
                    """,
                    (
                        AssignmentStatus.CANCELLED.value,
                        resolved_at,
                        payload.target_contribution_id,
                        AssignmentStatus.ASSIGNED.value,
                    ),
                )
            state = self._state_with_connection(connection, payload.target_contribution_id)
            connection.commit()
            return state
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _state_with_connection(
        self, connection: sqlite3.Connection, contribution_id: str
    ) -> dict[str, Any]:
        contribution = connection.execute(
            "SELECT * FROM contributions WHERE contribution_id = ?", (contribution_id,)
        ).fetchone()
        if contribution is None:
            raise StoreNotFoundError("contribution not found")
        counts = connection.execute(
            """
            SELECT
              COUNT(*) AS review_count,
              SUM(CASE WHEN verdict = ? THEN 1 ELSE 0 END) AS approvals,
              SUM(CASE WHEN verdict = ? THEN 1 ELSE 0 END) AS rejections
            FROM reviews WHERE contribution_id = ?
            """,
            (
                ReviewVerdict.APPROVE.value,
                ReviewVerdict.REJECT.value,
                contribution_id,
            ),
        ).fetchone()
        return {
            "contribution_id": contribution_id,
            "artifact_id": contribution["artifact_id"],
            "author_id": contribution["author_id"],
            "kind": contribution["kind"],
            "title": contribution["title"],
            "status": contribution["status"],
            "review_count": int(counts["review_count"] or 0),
            "approvals": int(counts["approvals"] or 0),
            "rejections": int(counts["rejections"] or 0),
        }

    def contribution_state(self, contribution_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            return self._state_with_connection(connection, contribution_id)

    def published_feed(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT envelope_json FROM contributions
                WHERE status = ? ORDER BY submitted_at, contribution_id
                """,
                (PublicationStatus.PUBLISHED.value,),
            ).fetchall()
        return [json.loads(row["envelope_json"]) for row in rows]

    def add_event(self, artifact: SignedArtifact, event_type: str, created_at: str) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO events (
                    artifact_id, event_type, envelope_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (artifact.artifact_id, event_type, artifact.model_dump_json(), created_at),
            )

    def list_events(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT envelope_json FROM events ORDER BY created_at, artifact_id"
            ).fetchall()
        return [json.loads(row["envelope_json"]) for row in rows]
