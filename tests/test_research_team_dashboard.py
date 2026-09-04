from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from discovery_net.research_team.dashboard import create_server, timeline_snapshot


def _campaign_state(root: Path) -> None:
    prompts = root / "prompts"
    reports = root / "work" / "researcher-1" / "reports"
    prompts.mkdir(parents=True)
    reports.mkdir(parents=True)
    (prompts / "researcher-1.md").write_text("role: researcher\n\nWork.\n")
    started = "2026-09-03T11:00:00+00:00"
    run_id = f"researcher-1:{started}"
    (reports.parent / "usage.jsonl").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "agent": "researcher-1",
                "role": "researcher",
                "started_at": started,
                "finished_at": "2026-09-03T11:20:00+00:00",
                "model": "gpt-5.6-sol",
                "effort": "xhigh",
                "tier": "flex",
                "total_tokens": 120,
            }
        )
        + "\n"
    )
    prompt_mtime = datetime(2026, 9, 3, 10, tzinfo=UTC).timestamp()
    (prompts / "researcher-1.md").touch()
    os.utime(prompts / "researcher-1.md", (prompt_mtime, prompt_mtime))
    impact = root / "impact"
    impact.mkdir()
    (impact / "annotations.jsonl").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "lane_title": "Sharp finite bound",
                "change_type": "new_approach",
                "impact": "substantial",
                "novelty": "possibly_new",
                "paper_potential": "high",
                "confidence": "medium",
                "summary": "A sharp bound has reproducible evidence.",
                "rationale": "The computation and graph neighborhood agree.",
                "evidence": ["public commit"],
                "caveats": ["No independent literature review yet."],
                "agent": "researcher-1",
                "run_started_at": started,
                "run_finished_at": "2026-09-03T11:20:00+00:00",
                "assessor": "impact-assessor-1",
                "assessed_at": "2026-09-03T11:40:00+00:00",
            }
        )
        + "\n"
    )


def test_timeline_snapshot_joins_impact_annotations_without_report_contents(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _campaign_state(root)
    snapshot = timeline_snapshot(root, now=datetime(2026, 9, 3, 12, tzinfo=UTC))

    assert snapshot["summary"]["completed_runs"] == 1
    assert snapshot["summary"]["impact_signals"]["substantial"] == 1
    assert snapshot["runs"][0]["lane"].endswith("sharp-finite-bound")
    assert snapshot["events"][0]["type"] == "new_approach"
    encoded = json.dumps(snapshot)
    assert "prompt" not in encoded
    assert "report_excerpt" not in encoded


def test_timeline_keeps_management_and_review_agents_visible_as_individual_lanes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "state"
    prompts = root / "prompts"
    prompts.mkdir(parents=True)
    for agent, role in (
        ("reviewer-1", "reviewer"),
        ("reviewer-2", "reviewer"),
        ("principal-1", "principal"),
        ("orchestrator-1", "orchestrator"),
    ):
        (prompts / f"{agent}.md").write_text(f"role: {role}\n\nWork.\n")
        prompt_mtime = datetime(2026, 9, 3, 10, tzinfo=UTC).timestamp()
        os.utime(prompts / f"{agent}.md", (prompt_mtime, prompt_mtime))
        work = root / "work" / agent
        work.mkdir(parents=True)
        started = "2026-09-03T11:00:00+00:00"
        (work / "usage.jsonl").write_text(
            json.dumps(
                {
                    "run_id": f"{agent}:{started}",
                    "agent": agent,
                    "role": role,
                    "started_at": started,
                    "finished_at": "2026-09-03T11:10:00+00:00",
                }
            )
            + "\n"
        )

    snapshot = timeline_snapshot(root, now=datetime(2026, 9, 3, 12, tzinfo=UTC))
    lanes = {lane["full"]: lane for lane in snapshot["lanes"]}

    assert set(lanes) == {"reviewer-1", "reviewer-2", "principal-1", "orchestrator-1"}
    assert {run["lane"] for run in snapshot["runs"]} == {
        "reviewer-1:reviewer-1",
        "reviewer-2:reviewer-2",
        "principal-1:principal-1",
        "orchestrator-1:orchestrator-1",
    }


def test_active_research_pass_keeps_latest_assessed_problem_lane(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _campaign_state(root)
    current = root / "work" / "researcher-1" / "current-pass.json"
    current.write_text(
        json.dumps(
            {
                "agent": "researcher-1",
                "role": "researcher",
                "started_at": "2026-09-03T11:30:00+00:00",
            }
        )
    )

    snapshot = timeline_snapshot(root, now=datetime(2026, 9, 3, 12, tzinfo=UTC))

    assert [lane["full"] for lane in snapshot["lanes"]] == [
        "researcher-1 · Sharp finite bound"
    ]
    assert len({run["lane"] for run in snapshot["runs"]}) == 1


def test_timeline_hides_retired_agents_and_pre_retarget_runs(tmp_path: Path) -> None:
    root = tmp_path / "state"
    prompts = root / "prompts"
    prompts.mkdir(parents=True)
    active_prompt = prompts / "researcher-new.md"
    active_prompt.write_text("role: researcher\n\nWork.\n")
    campaign_start = datetime(2026, 9, 3, 11, 30, tzinfo=UTC).timestamp()
    os.utime(active_prompt, (campaign_start, campaign_start))
    work = root / "work" / "researcher-new"
    work.mkdir(parents=True)
    work.joinpath("usage.jsonl").write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {
                    "agent": "researcher-new",
                    "role": "researcher",
                    "started_at": "2026-09-03T11:00:00+00:00",
                    "finished_at": "2026-09-03T11:20:00+00:00",
                },
                {
                    "agent": "researcher-new",
                    "role": "researcher",
                    "started_at": "2026-09-03T11:40:00+00:00",
                    "finished_at": "2026-09-03T11:50:00+00:00",
                },
            )
        )
        + "\n"
    )
    retired = root / "work" / "researcher-retired"
    retired.mkdir(parents=True)
    retired.joinpath("usage.jsonl").write_text(
        json.dumps(
            {
                "agent": "researcher-retired",
                "role": "researcher",
                "started_at": "2026-09-03T11:40:00+00:00",
                "finished_at": "2026-09-03T11:50:00+00:00",
            }
        )
        + "\n"
    )

    snapshot = timeline_snapshot(root, now=datetime(2026, 9, 3, 12, tzinfo=UTC))

    assert [run["agent"] for run in snapshot["runs"]] == ["researcher-new"]
    assert snapshot["summary"]["active_agents"] == 1


def test_timeline_includes_latest_resource_sample(tmp_path: Path) -> None:
    root = tmp_path / "state"
    monitor = root / "monitor"
    monitor.mkdir(parents=True)
    monitor.joinpath("resources.jsonl").write_text(
        '{"cpu_percent": 25.0}\n{"cpu_percent": 81.5}\n'
    )

    snapshot = timeline_snapshot(root, now=datetime(2026, 9, 3, 12, tzinfo=UTC))

    assert snapshot["resources"] == {"cpu_percent": 81.5}


def test_dashboard_serves_only_health_timeline_and_built_assets(tmp_path: Path) -> None:
    root = tmp_path / "state"
    _campaign_state(root)
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>timeline</title>")
    server = create_server("127.0.0.1", 0, root=root, static_root=static)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(f"{base}/api/health", timeout=2) as response:
            assert json.load(response) == {"status": "ok"}
        with urlopen(f"{base}/api/timeline", timeout=2) as response:
            assert json.load(response)["summary"]["completed_runs"] == 1
        with urlopen(base, timeout=2) as response:
            assert b"timeline" in response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
