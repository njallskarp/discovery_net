"""Read-only HTTP dashboard for research-team timelines and impact signals."""

from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from discovery_net.research_team.impact import read_annotations, run_identifier

ROLE_ORDER = {
    "researcher": 0,
    "reviewer": 1,
    "principal": 2,
    "impact-assessor": 3,
    "orchestrator": 4,
}
SAFE_ASSET_PATH = re.compile(r"^/assets/[A-Za-z0-9._-]+$")


def timeline_snapshot(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Build the dashboard payload without exposing prompts or report contents."""
    snapshot_at = now or datetime.now(UTC)
    if snapshot_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    roles, campaign_starts = _active_agent_roles(root)
    all_annotations = {str(item["run_id"]): item for item in read_annotations(root)}
    runs = _completed_runs(root, roles, campaign_starts, all_annotations)
    runs.extend(_failed_runs(root, roles, campaign_starts))
    runs.extend(_active_runs(root, roles, campaign_starts, snapshot_at))
    runs.sort(key=lambda value: (str(value["started_at"]), str(value["agent"])))

    visible_run_ids = {str(run["run_id"]) for run in runs}
    annotations = {
        run_id: annotation
        for run_id, annotation in all_annotations.items()
        if run_id in visible_run_ids
    }

    lanes, events = _lanes_and_events(runs)
    role_counts: dict[str, int] = {}
    for run in runs:
        role = str(run["role"])
        role_counts[role] = role_counts.get(role, 0) + 1
    signal_counts = {"substantial": 0, "major": 0, "high_paper_potential": 0}
    for annotation in annotations.values():
        impact = str(annotation.get("impact"))
        if impact in signal_counts:
            signal_counts[impact] += 1
        if annotation.get("paper_potential") == "high":
            signal_counts["high_paper_potential"] += 1

    return {
        "snapshot_at": snapshot_at.isoformat(),
        "runs": runs,
        "lanes": lanes,
        "events": events,
        "annotations": list(annotations.values()),
        "resources": _latest_resource_sample(root),
        "summary": {
            "active_agents": len(roles),
            "completed_runs": sum(1 for run in runs if run["state"] == "completed"),
            "running_runs": sum(1 for run in runs if run["state"] == "running"),
            "failed_runs": sum(1 for run in runs if run["state"] == "failed"),
            "annotations": len(annotations),
            "role_runs": role_counts,
            "impact_signals": signal_counts,
        },
    }


def _completed_runs(
    root: Path,
    roles: dict[str, str],
    campaign_starts: dict[str, datetime],
    annotations: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for agent_root in _agent_workspaces(root, roles):
        usage_path = agent_root / "usage.jsonl"
        if not usage_path.is_file():
            continue
        pass_number = 0
        for line in usage_path.read_text(errors="replace").splitlines():
            with contextlib.suppress(json.JSONDecodeError, KeyError, ValueError):
                record = json.loads(line)
                if not isinstance(record, dict):
                    continue
                started_at = str(record["started_at"])
                finished_at = str(record["finished_at"])
                _parse_timestamp(started_at)
                _parse_timestamp(finished_at)
                pass_number += 1
                agent = str(record.get("agent") or agent_root.name)
                if _parse_timestamp(started_at) < campaign_starts[agent]:
                    continue
                run_id = str(record.get("run_id") or run_identifier(agent, started_at))
                annotation = annotations.get(run_id)
                runs.append(
                    {
                        "run_id": run_id,
                        "agent": agent,
                        "role": str(record.get("role") or roles.get(agent) or _role(agent)),
                        "pass": pass_number,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "state": "completed",
                        "model": record.get("model"),
                        "effort": record.get("effort"),
                        "tier": record.get("tier"),
                        "total_tokens": int(record.get("total_tokens", 0)),
                        "annotation": annotation,
                    }
                )
    return runs


def _failed_runs(
    root: Path,
    roles: dict[str, str],
    campaign_starts: dict[str, datetime],
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for agent_root in _agent_workspaces(root, roles):
        path = agent_root / "failures.jsonl"
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            with contextlib.suppress(json.JSONDecodeError, KeyError, ValueError):
                value = json.loads(line)
                if not isinstance(value, dict):
                    continue
                agent = str(value.get("agent") or agent_root.name)
                finished_at = str(value.get("finished_at") or value["timestamp"])
                started_at = str(value.get("started_at") or finished_at)
                _parse_timestamp(started_at)
                _parse_timestamp(finished_at)
                if _parse_timestamp(started_at) < campaign_starts[agent]:
                    continue
                runs.append(
                    {
                        "run_id": run_identifier(agent, started_at),
                        "agent": agent,
                        "role": str(value.get("role") or roles.get(agent) or _role(agent)),
                        "pass": None,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "state": "failed",
                        "error": str(value.get("error", "unknown failure"))[:500],
                        "annotation": None,
                    }
                )
    return runs


def _active_runs(
    root: Path,
    roles: dict[str, str],
    campaign_starts: dict[str, datetime],
    snapshot_at: datetime,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for agent_root in _agent_workspaces(root, roles):
        value = _read_object(agent_root / "current-pass.json")
        if value is None:
            continue
        with contextlib.suppress(KeyError, ValueError):
            agent = str(value.get("agent") or agent_root.name)
            started_at = str(value["started_at"])
            if _parse_timestamp(started_at) < campaign_starts[agent]:
                continue
            runs.append(
                {
                    "run_id": run_identifier(agent, started_at),
                    "agent": agent,
                    "role": str(value.get("role") or roles.get(agent) or _role(agent)),
                    "pass": None,
                    "started_at": started_at,
                    "finished_at": snapshot_at.isoformat(),
                    "state": "running",
                    "annotation": None,
                }
            )
    return runs


def _lanes_and_events(
    runs: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    lanes: dict[str, dict[str, str]] = {}
    events: list[dict[str, Any]] = []
    previous_lane: dict[str, str] = {}
    previous_title: dict[str, str] = {}
    for run in runs:
        role = str(run["role"])
        agent = str(run["agent"])
        annotation = run.get("annotation")
        annotated_title = (
            str(annotation["lane_title"])
            if isinstance(annotation, dict) and annotation.get("lane_title")
            else None
        )
        lane_title = (
            annotated_title
            or previous_title.get(agent)
            or _default_lane_title(agent, role)
        )
        lane_id = _lane_id(agent, role, lane_title)
        run["lane"] = lane_id
        display_title = (
            f"{agent} · {lane_title}"
            if role == "researcher" and lane_title != agent
            else lane_title
        )
        lanes.setdefault(
            lane_id,
            {
                "id": lane_id,
                "full": display_title,
                "short": _short_title(display_title),
                "role": role,
            },
        )
        if isinstance(annotation, dict):
            change_type = str(annotation.get("change_type", "continuation"))
            if change_type != "continuation":
                event = {
                    "lane": lane_id,
                    "time": run["finished_at"],
                    "type": change_type,
                    "role": role,
                    "label": annotation.get("summary"),
                    "annotation": annotation,
                }
                old_lane = previous_lane.get(agent)
                if change_type == "problem_pivot" and old_lane and old_lane != lane_id:
                    event["from"] = old_lane
                events.append(event)
        previous_lane[agent] = lane_id
        previous_title[agent] = lane_title
    ordered = sorted(
        lanes.values(),
        key=lambda lane: (ROLE_ORDER.get(lane["role"], 9), _first_lane_index(runs, lane["id"])),
    )
    return ordered, events


def _active_agent_roles(root: Path) -> tuple[dict[str, str], dict[str, datetime]]:
    roles: dict[str, str] = {}
    starts: dict[str, datetime] = {}
    folder = root / "prompts"
    if not folder.is_dir():
        return roles, starts
    for path in sorted(folder.glob("*.md")):
        metadata = _prompt_metadata(path)
        role = metadata.get("role")
        if not role:
            continue
        name = path.stem
        roles[name] = role
        starts[name] = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return roles, starts


def _prompt_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    with path.open(errors="replace") as source:
        for line in source:
            if not line.strip():
                break
            if ":" not in line:
                break
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata


def _agent_workspaces(root: Path, roles: dict[str, str]) -> tuple[Path, ...]:
    work = root / "work"
    if not work.is_dir():
        return ()
    return tuple(work / agent for agent in sorted(roles) if (work / agent).is_dir())


def _latest_resource_sample(root: Path) -> dict[str, Any] | None:
    monitor_root = Path(os.environ.get("DISCOVERY_RESEARCH_TEAM_MONITOR", root / "monitor"))
    path = monitor_root / "resources.jsonl"
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        with contextlib.suppress(json.JSONDecodeError):
            value = json.loads(line)
            if isinstance(value, dict):
                return value
    return None


def _role(agent: str) -> str:
    for role in ("researcher", "reviewer", "principal", "impact-assessor", "orchestrator"):
        if agent.startswith(role):
            return role
    return "other"


def _default_lane_title(agent: str, role: str) -> str:
    if role == "impact-assessor":
        return "Impact assessor"
    return agent


def _lane_id(agent: str, role: str, title: str) -> str:
    if role == "impact-assessor":
        return role
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    return f"{agent}:{slug or 'research'}"


def _short_title(title: str) -> str:
    return title if len(title) <= 28 else title[:27].rstrip() + "…"


def _first_lane_index(runs: list[dict[str, Any]], lane_id: str) -> int:
    return next(index for index, run in enumerate(runs) if run.get("lane") == lane_id)


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


class ResearchTeamDashboardServer(ThreadingHTTPServer):
    """HTTP server carrying immutable dashboard configuration."""

    state_root: Path
    static_root: Path


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve a minimal static application and read-only JSON endpoints."""

    server: ResearchTeamDashboardServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json({"status": "ok"})
            return
        if path == "/api/timeline":
            self._json(timeline_snapshot(self.server.state_root))
            return
        if path == "/" or path == "/index.html":
            self._file(self.server.static_root / "index.html")
            return
        if SAFE_ASSET_PATH.fullmatch(path):
            self._file(self.server.static_root / path.removeprefix("/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, value: dict[str, Any]) -> None:
        body = json.dumps(value, sort_keys=True).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file() or not path.resolve().is_relative_to(
            self.server.static_root.resolve()
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        media_type, _ = mimetypes.guess_type(path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", media_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(
    host: str,
    port: int,
    *,
    root: Path,
    static_root: Path,
) -> ResearchTeamDashboardServer:
    """Create a configured server without starting its loop."""
    if not static_root.joinpath("index.html").is_file():
        raise FileNotFoundError(f"dashboard build not found: {static_root}")
    server = ResearchTeamDashboardServer((host, port), DashboardRequestHandler)
    server.state_root = root.resolve()
    server.static_root = static_root.resolve()
    return server


def _default_static_root() -> Path:
    packaged = Path(__file__).with_name("static")
    if packaged.joinpath("index.html").is_file():
        return packaged
    repository_build = Path(__file__).resolve().parents[3] / "research-team-ui" / "dist"
    return repository_build


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-team-dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--state-root",
        type=Path,
        default=Path(os.environ.get("DISCOVERY_RESEARCH_TEAM_ROOT", "~/.discovery-research-team"))
        .expanduser()
        .resolve(),
    )
    parser.add_argument("--static-root", type=Path, default=_default_static_root())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    server = create_server(
        cast(str, options.host),
        cast(int, options.port),
        root=cast(Path, options.state_root),
        static_root=cast(Path, options.static_root),
    )
    print(f"research-team dashboard listening on http://{options.host}:{options.port}")
    with server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
