from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from discovery_net.research_team import claude_code, controller

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
log = os.environ["FAKE_CLAUDE_LOG"]
inherited = sorted(k for k in os.environ if k.startswith("CLAUDE") and k != "CLAUDE_CONFIG_DIR")
own_session = os.getsid(0) != os.getsid(os.getppid())
with open(log, "a") as handle:
    record = {"argv": argv, "prompt": prompt, "cwd": os.getcwd(), "inherited": inherited,
              "own_session": own_session}
    handle.write(json.dumps(record) + "\\n")
if argv == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
if argv == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}))
    sys.exit(0)
marker = os.environ.get("FAKE_CLAUDE_LOSE_SESSION_ONCE")
if "--resume" in argv and marker and not os.path.exists(marker):
    open(marker, "w").close()
    lost = argv[argv.index("--resume") + 1]
    print("No conversation found with session ID: " + lost, file=sys.stderr)
    sys.exit(1)
flag = "--session-id" if "--session-id" in argv else "--resume"
session = argv[argv.index(flag) + 1]
if os.environ.get("FAKE_CLAUDE_LINGER"):
    import subprocess
    subprocess.Popen(["sleep", os.environ["FAKE_CLAUDE_LINGER"]])  # inherits stdout/stderr
if os.environ.get("FAKE_CLAUDE_HANG"):
    import time
    time.sleep(float(os.environ["FAKE_CLAUDE_HANG"]))
print("[claude-code:telemetry] {\\"noise\\": true}")
print(json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 3,
    "session_id": session, "total_cost_usd": 1.25,
    "usage": {"input_tokens": 10, "cache_read_input_tokens": 40,
              "cache_creation_input_tokens": 100, "output_tokens": 30},
    "result": "pass complete: " + prompt.splitlines()[0],
}))
"""


def _install_fake_claude(tmp_path: Path, monkeypatch: Any) -> Path:
    script = tmp_path / "fake-claude"
    script.write_text(FAKE_CLAUDE)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "claude.log"
    monkeypatch.setenv(claude_code.BINARY_ENVIRONMENT, str(script))
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent")
    return log


def _calls(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text().splitlines()]


def _write_prompt(path: Path, workspace: Path, **overrides: str) -> None:
    metadata = {
        "role": "researcher",
        "mode": "continuous",
        "runner": "claude-code",
        "effort": "xhigh",
        "tier": "default",
        "restart-seconds": "1800",
        "permissions": "workspace-write",
        "network-access": "true",
        "web-search": "live",
        "workspace": str(workspace),
        "github-repository": "https://github.com/example/math-research",
        "contract-confirmed": "true",
        "max-passes": "0",
        "max-total-tokens": "0",
        "model": "claude-fable-5-1",
        "max-pass-usd": "40",
    }
    metadata.update(overrides)
    workspace.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}: {value}" for key, value in metadata.items() if value != ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n\nStanding mandate: work autonomously.\n")


def test_build_command_maps_contract_to_cli_flags(tmp_path: Path) -> None:
    binary = tmp_path / "claude"
    command = claude_code.build_command(
        binary=binary,
        model="claude-fable-5-1",
        effort="xhigh",
        permissions="workspace-write",
        web_search="live",
        session_id="abc",
        resume=False,
        max_pass_usd=12.5,
    )
    assert command[:2] == [str(binary), "-p"]
    assert "--output-format" in command and command[command.index("--output-format") + 1] == "json"
    assert command[command.index("--effort") + 1] == "xhigh"
    assert command[command.index("--model") + 1] == "claude-fable-5-1"
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    allowed = command[command.index("--allowedTools") + 1 :]
    assert allowed[:3] == ["Bash", "WebSearch", "WebFetch"]
    assert command[command.index("--max-budget-usd") + 1] == "12.5"
    assert command[-2:] == ["--session-id", "abc"]
    assert "--strict-mcp-config" in command
    assert command[command.index("--setting-sources") + 1] == "project"

    resumed = claude_code.build_command(
        binary=binary,
        model=None,
        effort="high",
        permissions="unrestricted",
        web_search="disabled",
        session_id="abc",
        resume=True,
        max_pass_usd=None,
    )
    assert "--model" not in resumed
    assert resumed[resumed.index("--permission-mode") + 1] == "bypassPermissions"
    assert resumed[resumed.index("--disallowedTools") + 1 : resumed.index("--resume")] == [
        "WebSearch",
        "WebFetch",
    ]
    assert "--max-budget-usd" not in resumed
    assert resumed[-2:] == ["--resume", "abc"]

    with pytest.raises(claude_code.ClaudeCodeError):
        claude_code.build_command(
            binary=binary,
            model=None,
            effort="minimal",
            permissions="workspace-write",
            web_search="live",
            session_id="abc",
            resume=False,
            max_pass_usd=None,
        )


def test_parse_result_ignores_log_noise_and_requires_result_object() -> None:
    stdout = (
        '[claude-code:unrecognized_model] {"model":"x"}\n'
        '{"type": "system", "subtype": "init"}\n'
        '{"type": "result", "subtype": "success", "result": "OK", "session_id": "s"}\n'
    )
    assert claude_code.parse_result(stdout)["result"] == "OK"
    with pytest.raises(claude_code.ClaudeCodeError):
        claude_code.parse_result('{"type": "system"}\nnot json\n')


def test_runtime_environment_drops_parent_session_variables(monkeypatch: Any) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    monkeypatch.setenv("CLAUDE_EFFORT", "high")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/tmp/claude-config")
    monkeypatch.setenv("HOME_MARKER", "kept")
    environment = claude_code.runtime_environment()
    assert "CLAUDECODE" not in environment
    assert "CLAUDE_CODE_ENTRYPOINT" not in environment
    assert "CLAUDE_EFFORT" not in environment
    assert environment["CLAUDE_CONFIG_DIR"] == "/tmp/claude-config"
    assert environment["HOME_MARKER"] == "kept"


def test_run_pass_starts_resumes_and_recovers_a_lost_session(
    tmp_path: Path, monkeypatch: Any
) -> None:
    log = _install_fake_claude(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    common: dict[str, Any] = {
        "fresh_prompt": "FULL MANDATE\nmore",
        "workspace": workspace,
        "model": "claude-fable-5-1",
        "effort": "xhigh",
        "permissions": "workspace-write",
        "web_search": "live",
        "max_pass_usd": None,
    }
    first = claude_code.run_pass(prompt="ignored", session_id=None, **common)
    assert first.resumed is False
    assert first.response == "pass complete: FULL MANDATE"
    assert first.input_tokens == 10 and first.cache_creation_input_tokens == 100
    assert first.cached_input_tokens == 40 and first.output_tokens == 30
    assert first.cost_usd == 1.25 and first.num_turns == 3

    second = claude_code.run_pass(prompt="CONTINUE", session_id=first.session_id, **common)
    assert second.resumed is True
    assert second.session_id == first.session_id
    assert second.response == "pass complete: CONTINUE"

    monkeypatch.setenv("FAKE_CLAUDE_LOSE_SESSION_ONCE", str(tmp_path / "lost"))
    third = claude_code.run_pass(prompt="CONTINUE", session_id=first.session_id, **common)
    assert third.resumed is False
    assert third.session_id != first.session_id
    assert third.response == "pass complete: FULL MANDATE"

    calls = _calls(log)
    assert calls[0]["argv"][-2] == "--session-id"
    assert calls[1]["argv"][-2:] == ["--resume", first.session_id]
    assert calls[2]["argv"][-2:] == ["--resume", first.session_id]
    assert calls[3]["argv"][-2] == "--session-id"
    assert all(call["cwd"] == str(workspace) for call in calls)
    assert all(call["inherited"] == [] for call in calls)


def test_controller_runs_claude_code_passes_and_records_cost(
    tmp_path: Path, monkeypatch: Any
) -> None:
    log = _install_fake_claude(tmp_path, monkeypatch)
    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(tmp_path / "state"))
    controller.ensure_state()
    prompt = controller.prompt_path("researcher-1")
    _write_prompt(prompt, tmp_path / "workspace")
    controller.state_path("work", "researcher-1", "reports").mkdir(parents=True)
    controller.state_path("followups", "researcher-1").mkdir(parents=True)
    followup = controller.state_path("followups", "researcher-1", "followup.1.md")
    followup.write_text("Avoid duplicating the other lane.\n")

    asyncio.run(controller.run_one_pass("researcher-1"))
    asyncio.run(controller.run_one_pass("researcher-1"))

    calls = _calls(log)
    assert len(calls) == 2
    assert "Standing mandate: work autonomously." in calls[0]["prompt"]
    assert "Avoid duplicating the other lane." in calls[0]["prompt"]
    assert calls[1]["prompt"].startswith("Continue the autonomous campaign")
    session_id = controller.state_path("work", "researcher-1", "session-id").read_text().strip()
    assert calls[0]["argv"][-2:] == ["--session-id", session_id]
    assert calls[1]["argv"][-2:] == ["--resume", session_id]
    assert calls[0]["argv"][calls[0]["argv"].index("--max-budget-usd") + 1] == "40"
    assert not controller.state_path("work", "researcher-1", "thread-id").exists()

    usage = [
        json.loads(line)
        for line in controller.state_path("work", "researcher-1", "usage.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(usage) == 2
    assert usage[0]["runner"] == "claude-code"
    assert usage[0]["thread_id"] == session_id
    assert usage[0]["input_tokens"] == 110
    assert usage[0]["cached_input_tokens"] == 40
    assert usage[0]["total_tokens"] == 140
    assert usage[0]["cost_usd"] == 1.25
    assert controller.usage_totals("researcher-1")["total_tokens"] == 280
    last_run = controller.read_last_run("researcher-1")
    assert last_run is not None and last_run["status"] == "completed"
    assert controller.status_records()[0]["runner"] == "claude-code"


def test_prompt_validation_is_runner_specific(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(tmp_path / "state"))
    prompt = tmp_path / "prompt.md"
    workspace = tmp_path / "workspace"

    _write_prompt(prompt, workspace)
    parsed = controller.parse_prompt(prompt)
    assert parsed.runner == "claude-code"
    assert parsed.max_pass_usd == 40.0

    _write_prompt(prompt, workspace, effort="max")
    assert controller.parse_prompt(prompt).effort == "max"

    for overrides, message in (
        ({"tier": "flex"}, "no service tiers"),
        ({"effort": "minimal"}, "unsupported effort for claude-code"),
        ({"web-search": "cached"}, "disabled or live"),
        ({"runner": "gemini"}, "unsupported runner"),
        ({"max-pass-usd": "-1"}, "non-negative"),
        ({"runner": "codex", "effort": "max", "max-pass-usd": ""}, "unsupported effort for codex"),
        ({"runner": "codex", "effort": "high"}, "only supported by the claude-code runner"),
    ):
        _write_prompt(prompt, workspace, **overrides)
        with pytest.raises(controller.ControllerError, match=message):
            controller.parse_prompt(prompt)

    _write_prompt(prompt, workspace, runner="", effort="high", max_pass_usd="")
    text = prompt.read_text().replace("max-pass-usd: 40\n", "")
    prompt.write_text(text)
    assert controller.parse_prompt(prompt).runner == "codex"


def test_doctor_reports_claude_code_login(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    _install_fake_claude(tmp_path, monkeypatch)
    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(tmp_path / "state"))
    controller.doctor("claude-code")
    output = capsys.readouterr().out
    assert "9.9.9 (Claude Code)" in output
    assert "claude.ai (max)" in output

    missing = tmp_path / "missing"
    monkeypatch.setenv(claude_code.BINARY_ENVIRONMENT, str(missing))
    with pytest.raises(controller.ControllerError, match="not an executable file"):
        controller.doctor("claude-code")
    assert not os.path.exists(missing)


def test_failure_detail_prefers_the_cli_error_result_over_log_noise() -> None:
    import subprocess

    limit = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "api_error_status": 429,
            "result": "You've hit your session limit \u00b7 resets 2:30am",
        }
    )
    completed = subprocess.CompletedProcess(
        ["claude"], 1, stdout=limit + "\n", stderr='[claude-code:unrecognized_model] {"m":1}\n'
    )
    detail = claude_code.failure_detail(completed)
    assert detail.startswith("You've hit your session limit")
    assert "api_error_status=429" in detail

    no_result = subprocess.CompletedProcess(["claude"], 1, stdout="", stderr="boom\n")
    assert claude_code.failure_detail(no_result) == "boom"


def test_invoke_returns_when_cli_exits_despite_lingering_background_child(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import time

    _install_fake_claude(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_LINGER", "8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    started = time.monotonic()
    result = claude_code.run_pass(
        prompt="ignored",
        fresh_prompt="FULL MANDATE",
        workspace=workspace,
        model=None,
        effort="high",
        permissions="workspace-write",
        web_search="live",
        session_id=None,
        max_pass_usd=None,
    )
    assert time.monotonic() - started < 4, "a lingering child held the pass open"
    assert result.response == "pass complete: FULL MANDATE"


def test_cli_runs_in_its_own_session_and_terminate_active_stops_it(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import threading
    import time

    log = _install_fake_claude(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    common: dict[str, Any] = {
        "prompt": "ignored",
        "fresh_prompt": "FULL MANDATE",
        "workspace": workspace,
        "model": None,
        "effort": "high",
        "permissions": "workspace-write",
        "web_search": "live",
        "session_id": None,
        "max_pass_usd": None,
    }
    claude_code.run_pass(**common)
    assert _calls(log)[-1]["own_session"] is True

    monkeypatch.setenv("FAKE_CLAUDE_HANG", "30")
    errors: list[BaseException] = []

    def run() -> None:
        try:
            claude_code.run_pass(**common)
        except BaseException as exc:  # the test inspects the error
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 5
    while not claude_code._ACTIVE and time.monotonic() < deadline:
        time.sleep(0.05)
    assert claude_code._ACTIVE, "the CLI pass did not start"
    started = time.monotonic()
    assert claude_code.terminate_active(grace_seconds=2) == 1
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert time.monotonic() - started < 8
    assert errors and "exited" in str(errors[0])


def test_impact_assessor_pass_feeds_the_previous_rejection_back(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from discovery_net.research_team.impact import ImpactContext

    _install_fake_claude(tmp_path, monkeypatch)
    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(tmp_path / "state"))
    controller.ensure_state()
    ledger = tmp_path / "ledger.sqlite"
    ledger.touch()
    _write_prompt(
        controller.prompt_path("impact-assessor-1"),
        tmp_path / "workspace",
        role="impact-assessor",
        model="claude-sonnet-5",
        **{"ledger-path": str(ledger), "restart-seconds": "3600"},
    )
    controller.state_path("work", "impact-assessor-1", "reports").mkdir(parents=True)
    context = ImpactContext(
        payload={
            "runs": [
                {
                    "run_id": "researcher-1:2026-09-05T17:56:56.728989+00:00",
                    "agent": "researcher-1",
                    "started_at": "2026-09-05T17:56:56.728989+00:00",
                    "finished_at": "2026-09-05T18:00:00+00:00",
                }
            ]
        },
        run_ids=("researcher-1:2026-09-05T17:56:56.728989+00:00",),
        latest_finished_at="2026-09-05T18:00:00+00:00",
        indexed_height=1,
    )
    monkeypatch.setattr(controller, "build_impact_context", lambda *args, **kwargs: context)
    prompts: list[str] = []

    def fake_pass(config: Any, prompt: str, session_id: str | None) -> controller.PassOutcome:
        prompts.append(prompt)
        run_id = "researcher-1:2026-09-05T17:56:56.728969+00:00"
        if len(prompts) > 1:
            run_id = "researcher-1:2026-09-05T17:56:56.728989+00:00"
        body = {
            "portfolio_summary": "One run.",
            "assessments": [
                {
                    "run_id": run_id,
                    "lane_title": "R(5,5)",
                    "change_type": "continuation",
                    "impact": "routine",
                    "novelty": "not_assessed",
                    "paper_potential": "low",
                    "confidence": "medium",
                    "summary": "Routine.",
                    "rationale": "Routine.",
                    "evidence": [],
                    "caveats": [],
                }
            ],
        }
        return controller.PassOutcome(
            response="Same run again.\n\n```json\n" + json.dumps(body) + "\n```",
            conversation_id="session",
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=1,
            cost_usd=0.1,
        )

    monkeypatch.setattr(controller, "run_claude_code_pass", fake_pass)

    with pytest.raises(controller.ControllerError) as excinfo:
        asyncio.run(controller.run_one_pass("impact-assessor-1"))
    assert "not in the packet: researcher-1:2026-09-05T17:56:56.728969+00:00" in str(excinfo.value)
    assert "## Previous pass rejected" not in prompts[0]
    controller.write_last_run(
        "impact-assessor-1", {"status": "failed", "error": f"ControllerError: {excinfo.value}"}
    )

    asyncio.run(controller.run_one_pass("impact-assessor-1"))
    assert "## Previous pass rejected" in prompts[1]
    assert "728969" in prompts[1]
    assert prompts[1].index("Previous pass rejected") < prompts[1].index("impact-assessment packet")
    annotations = controller.state_path("impact", "annotations.jsonl").read_text()
    assert "728989" in annotations
