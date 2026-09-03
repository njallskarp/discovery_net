from __future__ import annotations

import json
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
