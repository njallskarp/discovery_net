from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from discovery_net.node.store.sqlite_store import SQLiteArtifactLedgerStore
from discovery_net.research_team.impact import (
    build_impact_context,
    parse_impact_batch,
    read_annotations,
    record_impact_batch,
    run_identifier,
)


def test_impact_context_is_incremental_bounded_and_validated(tmp_path: Path) -> None:
    root = tmp_path / "state"
    report = root / "work" / "researcher-1" / "reports" / "pass.md"
    report.parent.mkdir(parents=True)
    report.write_text("Proved the finite case. Commit 0123456789abcdef0123456789abcdef01234567.\n")
    started = "2026-09-03T11:00:00+00:00"
    finished = "2026-09-03T11:20:00+00:00"
    usage = {
        "run_id": run_identifier("researcher-1", started),
        "agent": "researcher-1",
        "role": "researcher",
        "started_at": started,
        "finished_at": finished,
        "report": str(report),
        "model": "gpt-5.6-sol",
        "effort": "xhigh",
        "tier": "flex",
    }
    (report.parents[1] / "usage.jsonl").write_text(json.dumps(usage) + "\n")
    ledger = tmp_path / "ledger.sqlite"
    SQLiteArtifactLedgerStore(path=ledger)

    # The live node can hold a reserved write lock while the assessor reads its
    # committed snapshot. Building context must not initialize a writer store.
    with sqlite3.connect(ledger) as writer:
        writer.execute("BEGIN IMMEDIATE")
        context = build_impact_context(
            root,
            ledger,
            now=datetime(2026, 9, 3, 12, tzinfo=UTC),
        )
    assert context.run_ids == (usage["run_id"],)
    assert context.payload["runs"][0]["git_commits"] == ["0123456789abcdef0123456789abcdef01234567"]
    assert context.payload["graph"] == {
        "indexed_height": 0,
        "recent_contributions": [],
        "entry_artifacts": [],
    }

    response = json.dumps(
        {
            "portfolio_summary": "One bounded result needs independent checking.",
            "assessments": [
                {
                    "run_id": usage["run_id"],
                    "lane_title": "Finite extremal case",
                    "change_type": "new_approach",
                    "impact": "meaningful",
                    "novelty": "possibly_new",
                    "paper_potential": "medium",
                    "confidence": "low",
                    "summary": "A finite case was reportedly closed.",
                    "rationale": "The report contains a reproducible commit but no review.",
                    "evidence": ["Commit 0123456789abcdef0123456789abcdef01234567"],
                    "caveats": ["Correctness and literature novelty are unverified."],
                }
            ],
        }
    )
    batch = parse_impact_batch(response, context.run_ids)
    record_impact_batch(
        root,
        "impact-assessor-1",
        context,
        batch,
        assessed_at="2026-09-03T12:01:00+00:00",
    )
    annotations = read_annotations(root)
    assert len(annotations) == 1
    assert annotations[0]["impact"] == "meaningful"
    assert annotations[0]["agent"] == "researcher-1"

    next_context = build_impact_context(
        root,
        ledger,
        now=datetime(2026, 9, 3, 13, tzinfo=UTC),
    )
    assert next_context.run_ids == ()


def test_impact_response_must_cover_exact_pending_run_ids() -> None:
    response = json.dumps({"portfolio_summary": "Nothing supplied.", "assessments": []})
    with pytest.raises(ValueError, match="every supplied run_id"):
        parse_impact_batch(response, ("researcher-1:run",))
