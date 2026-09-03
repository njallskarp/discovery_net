"""Incremental, advisory impact annotations for research-team runs."""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from discovery_net.entrypoints.graphql import GraphQLQueryExecutor
from discovery_net.indexing import KnowledgeGraphIndex
from discovery_net.inspector.sqlite_ledger_reader import SQLiteArtifactLedgerReader
from discovery_net.query import KnowledgeGraphQueries

MAX_PENDING_RUNS = 12
MAX_REPORT_CHARACTERS = 6_000
MAX_GRAPH_CONTRIBUTIONS = 16
INITIAL_LOOKBACK = timedelta(hours=2)
ARTIFACT_REFERENCE_PATTERN = re.compile(r"\bb[a-z2-7]{50,100}\b")
GIT_COMMIT_PATTERN = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)

_GRAPH_DOCUMENT = """
query ImpactContext {
  indexedHeight
  contributions(last: 16) {
    artifactRef
    kind
    title
    body
    height
    createdAt
    outgoingRelations {
      kind
      toContributionRef
      destination { artifactRef kind title }
    }
    incomingRelations {
      kind
      fromContributionRef
      source { artifactRef kind title }
    }
  }
}
"""

_ARTIFACT_DOCUMENT = """
query ImpactArtifact($ref: ID!) {
  artifact(ref: $ref) {
    ... on Contribution {
      artifactRef
      kind
      title
      body
      height
      createdAt
      outgoingRelations {
        kind
        toContributionRef
        destination { artifactRef kind title }
      }
      incomingRelations {
        kind
        fromContributionRef
        source { artifactRef kind title }
      }
    }
  }
}
"""


class ImpactAssessment(BaseModel):
    """One calibrated assessment of one completed research-team pass."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    lane_title: str = Field(min_length=1, max_length=120)
    change_type: Literal["continuation", "new_approach", "problem_pivot", "source_publication"]
    impact: Literal["routine", "meaningful", "substantial", "major"]
    novelty: Literal["not_assessed", "appears_known", "possibly_new", "strong_novelty_signal"]
    paper_potential: Literal["low", "medium", "high"]
    confidence: Literal["low", "medium", "high"]
    summary: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=1_500)
    evidence: tuple[str, ...] = Field(default=(), max_length=8)
    caveats: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("evidence", "caveats")
    @classmethod
    def _bound_list_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("items must contain 1 to 500 non-whitespace characters")
        return values


class ImpactBatch(BaseModel):
    """Validated JSON contract returned by an impact-assessor pass."""

    model_config = ConfigDict(extra="forbid")

    portfolio_summary: str = Field(min_length=1, max_length=1_500)
    assessments: tuple[ImpactAssessment, ...]


@dataclass(frozen=True, slots=True)
class ImpactContext:
    """Bounded incremental context supplied to one impact-assessor pass."""

    payload: dict[str, Any]
    run_ids: tuple[str, ...]
    latest_finished_at: str | None
    indexed_height: int


def run_identifier(agent: str, started_at: str) -> str:
    """Return the stable public identifier used to join runs and annotations."""
    return f"{agent}:{started_at}"


def build_impact_context(
    root: Path,
    ledger_path: Path,
    *,
    now: datetime | None = None,
) -> ImpactContext:
    """Collect only completed runs after the durable impact cursor."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cursor = _read_object(root / "impact" / "cursor.json")
    after_text = cursor.get("finished_at") if cursor is not None else None
    after = (
        _parse_timestamp(after_text) if isinstance(after_text, str) else current - INITIAL_LOOKBACK
    )
    runs = [run for run in _usage_runs(root) if after < _parse_timestamp(run["finished_at"])]
    runs.sort(key=lambda value: (value["finished_at"], value["run_id"]))
    runs = runs[:MAX_PENDING_RUNS]

    entry_refs = sorted(
        {
            reference
            for run in runs
            for reference in run.get("artifact_refs", [])
            if isinstance(reference, str)
        }
    )
    graph = _graphql_context(ledger_path, entry_refs)
    payload = {
        "window": {
            "after": after.isoformat(),
            "through": current.isoformat(),
            "pending_count": len(runs),
            "truncated": len(runs) == MAX_PENDING_RUNS,
        },
        "runs": runs,
        "graph": graph,
    }
    return ImpactContext(
        payload=payload,
        run_ids=tuple(str(run["run_id"]) for run in runs),
        latest_finished_at=str(runs[-1]["finished_at"]) if runs else None,
        indexed_height=int(graph["indexed_height"]),
    )


def impact_prompt(context: ImpactContext) -> str:
    """Build the assessor-only instructions and bounded evidence packet."""
    return (
        "\n\n## Incremental impact-assessment packet\n"
        "Assess every run in `runs` exactly once and no other work. The graph data below was "
        "loaded through Discovery Net's read-only GraphQL schema and is bounded to the newest "
        "contributions. Treat novelty and paper potential as advisory signals, never established "
        "facts. `strong_novelty_signal` requires concrete comparison evidence and explicit "
        "caveats. "
        "A source-publication pass is delivery work, not new mathematics. Return only one JSON "
        "object matching this schema:\n"
        '{"portfolio_summary":"...","assessments":[{"run_id":"exact supplied id",'
        '"lane_title":"short problem or direction","change_type":"continuation|new_approach|'
        'problem_pivot|source_publication","impact":"routine|meaningful|substantial|major",'
        '"novelty":"not_assessed|appears_known|possibly_new|strong_novelty_signal",'
        '"paper_potential":"low|medium|high","confidence":"low|medium|high",'
        '"summary":"...","rationale":"...","evidence":["..."],"caveats":["..."]}]}\n'
        "Use `substantial` or `major` only when the evidence packet supports it. If there are no "
        "runs, return an empty "
        "assessments array and explain that there was no new completed work.\n\n"
        + json.dumps(context.payload, indent=2, sort_keys=True)
    )


def parse_impact_batch(response: str, expected_run_ids: tuple[str, ...]) -> ImpactBatch:
    """Validate an assessor response and require complete incremental coverage."""
    value = response.strip()
    if value.startswith("```") and value.endswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1])
    batch = ImpactBatch.model_validate_json(value)
    observed = [assessment.run_id for assessment in batch.assessments]
    if len(observed) != len(set(observed)):
        raise ValueError("impact response contains duplicate run_id values")
    if set(observed) != set(expected_run_ids):
        raise ValueError("impact response must assess every supplied run_id exactly once")
    return batch


def record_impact_batch(
    root: Path,
    assessor: str,
    context: ImpactContext,
    batch: ImpactBatch,
    *,
    assessed_at: str,
) -> None:
    """Append validated annotations, then advance the durable cursor."""
    impact_root = root / "impact"
    impact_root.mkdir(parents=True, exist_ok=True)
    annotations = impact_root / "annotations.jsonl"
    run_lookup = {run["run_id"]: run for run in context.payload["runs"]}
    with annotations.open("a") as output:
        for assessment in batch.assessments:
            run = run_lookup[assessment.run_id]
            record = {
                **assessment.model_dump(mode="json"),
                "agent": run["agent"],
                "run_started_at": run["started_at"],
                "run_finished_at": run["finished_at"],
                "assessor": assessor,
                "assessed_at": assessed_at,
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")
    if context.latest_finished_at is not None:
        _atomic_write(
            impact_root / "cursor.json",
            json.dumps(
                {
                    "finished_at": context.latest_finished_at,
                    "indexed_height": context.indexed_height,
                    "assessed_at": assessed_at,
                    "assessor": assessor,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )


def read_annotations(root: Path) -> tuple[dict[str, Any], ...]:
    """Return the latest valid annotation for each run."""
    path = root / "impact" / "annotations.jsonl"
    latest: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return ()
    for line in path.read_text(errors="replace").splitlines():
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            value = json.loads(line)
            if isinstance(value, dict):
                assessment = ImpactAssessment.model_validate(
                    {key: value.get(key) for key in ImpactAssessment.model_fields}
                )
                latest[assessment.run_id] = value
    return tuple(sorted(latest.values(), key=lambda value: str(value["run_finished_at"])))


def _usage_runs(root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    work_root = root / "work"
    if not work_root.is_dir():
        return runs
    for agent_root in sorted(path for path in work_root.iterdir() if path.is_dir()):
        usage_path = agent_root / "usage.jsonl"
        if not usage_path.is_file():
            continue
        for line in usage_path.read_text(errors="replace").splitlines():
            with contextlib.suppress(json.JSONDecodeError, KeyError, ValueError):
                usage = json.loads(line)
                if not isinstance(usage, dict):
                    continue
                started_at = str(usage["started_at"])
                finished_at = str(usage["finished_at"])
                _parse_timestamp(started_at)
                finished = _parse_timestamp(finished_at)
                agent = str(usage.get("agent") or agent_root.name)
                role = str(usage.get("role") or _role_from_name(agent))
                if role != "researcher":
                    continue
                report = _safe_report(root, usage.get("report")) or _legacy_report(
                    agent_root, finished
                )
                text = report.read_text(errors="replace")[:MAX_REPORT_CHARACTERS] if report else ""
                runs.append(
                    {
                        "run_id": str(usage.get("run_id") or run_identifier(agent, started_at)),
                        "agent": agent,
                        "role": role,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "model": usage.get("model"),
                        "effort": usage.get("effort"),
                        "tier": usage.get("tier"),
                        "git_commits": sorted(set(GIT_COMMIT_PATTERN.findall(text))),
                        "artifact_refs": sorted(set(ARTIFACT_REFERENCE_PATTERN.findall(text))),
                        "report_excerpt": text,
                    }
                )
    return runs


def _graphql_context(ledger_path: Path, entry_refs: list[str]) -> dict[str, Any]:
    if not ledger_path.is_file():
        raise FileNotFoundError(f"artifact ledger does not exist: {ledger_path}")
    update = SQLiteArtifactLedgerReader(path=ledger_path).updates_after(0)
    index = KnowledgeGraphIndex()
    index.append(entries=update.entries, height=update.height)
    executor = GraphQLQueryExecutor(queries=KnowledgeGraphQueries(index=index))
    result = executor.execute(_GRAPH_DOCUMENT)
    if not result.succeeded or result.data is None:
        raise ValueError(f"GraphQL impact context failed: {result.errors}")
    contributions = result.data.get("contributions")
    recent = contributions if isinstance(contributions, list) else []
    entry_artifacts: list[Any] = []
    for reference in entry_refs[:MAX_GRAPH_CONTRIBUTIONS]:
        artifact_result = executor.execute(_ARTIFACT_DOCUMENT, variables={"ref": reference})
        if artifact_result.succeeded and artifact_result.data is not None:
            artifact = artifact_result.data.get("artifact")
            if artifact is not None:
                entry_artifacts.append(_truncate_contribution(artifact))
    return {
        "indexed_height": int(str(result.data.get("indexedHeight", "0"))),
        "recent_contributions": [_truncate_contribution(value) for value in recent],
        "entry_artifacts": entry_artifacts,
    }


def _truncate_contribution(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    copy = dict(value)
    body = copy.get("body")
    if isinstance(body, str) and len(body) > 4_000:
        copy["body"] = body[:4_000] + "\n[truncated]"
    return copy


def _safe_report(root: Path, value: Any) -> Path | None:
    if not isinstance(value, str):
        return None
    candidate = Path(value).resolve()
    work = (root / "work").resolve()
    if candidate.is_file() and candidate.is_relative_to(work):
        return candidate
    return None


def _legacy_report(agent_root: Path, finished_at: datetime) -> Path | None:
    reports = agent_root / "reports"
    if not reports.is_dir():
        return None
    candidates: list[tuple[float, Path]] = []
    for path in reports.glob("*.md"):
        if path.name.startswith("followup-"):
            continue
        with contextlib.suppress(ValueError):
            recorded_at = datetime.strptime(path.stem, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC)
            distance = abs((recorded_at - finished_at).total_seconds())
            if distance <= 120:
                candidates.append((distance, path))
    if not candidates:
        return None
    return min(candidates, key=lambda value: value[0])[1]


def _role_from_name(name: str) -> str:
    for role in ("researcher", "reviewer", "principal", "impact-assessor", "orchestrator"):
        if name.startswith(role):
            return role
    return "other"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)
