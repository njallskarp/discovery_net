from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from discovery_net.research_team import controller


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".agents" / "skills" / "orchestrate-research-team"


def _controller_path() -> Path:
    return _skill_root() / "scripts" / "research-team"


def _write_prompt(
    path: Path,
    *,
    role: str = "researcher",
    mode: str = "continuous",
    effort: str = "xhigh",
    workspace: Path | None = None,
    contract_confirmed: bool = True,
    max_passes: int = 0,
    max_total_tokens: int = 0,
    body: str = "Work autonomously.",
) -> None:
    workspace = workspace or path.parent / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    restart_seconds = 1800 if mode == "continuous" else 0
    path.write_text(
        "\n".join(
            (
                f"role: {role}",
                f"mode: {mode}",
                f"effort: {effort}",
                "tier: default",
                f"restart-seconds: {restart_seconds}",
                "permissions: workspace-write",
                "network-access: true",
                "web-search: live",
                f"workspace: {workspace.resolve()}",
                f"contract-confirmed: {str(contract_confirmed).lower()}",
                f"max-passes: {max_passes}",
                f"max-total-tokens: {max_total_tokens}",
                "",
                body,
                "",
            )
        )
    )


def _controller_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    state_root = tmp_path / "state"
    environment = os.environ.copy()
    environment.update(
        {
            "DISCOVERY_RESEARCH_TEAM_TESTING": "1",
            "DISCOVERY_RESEARCH_TEAM_ROOT": str(state_root),
        }
    )
    source_root = Path(__file__).resolve().parents[1] / "src"
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(source_root)
    )
    return environment, state_root


def _run_controller(
    environment: dict[str, str], *arguments: object
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, _controller_path(), *(str(argument) for argument in arguments)],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )


def test_controller_preserves_visible_prompt_history_and_retired_state(tmp_path: Path) -> None:
    environment, state_root = _controller_environment(tmp_path)
    first_prompt = tmp_path / "first.md"
    second_prompt = tmp_path / "second.md"
    _write_prompt(first_prompt, body="First mandate.")
    _write_prompt(second_prompt, effort="high", body="Second mandate.")

    created = _run_controller(environment, "new", "researcher-1", first_prompt)
    assert "created and started" in created.stdout
    assert "researcher-1" in (state_root / "launches.log").read_text()

    shown = _run_controller(environment, "prompt", "researcher-1")
    assert "First mandate." in shown.stdout
    assert "effort: xhigh" in shown.stdout

    followup = tmp_path / "followup.md"
    followup.write_text("Stay in this area, but avoid duplicating the other lane.\n")
    _run_controller(environment, "continue", "researcher-1", followup)
    queued_followups = list((state_root / "followups/researcher-1").glob("followup.*.md"))
    assert len(queued_followups) == 1
    assert "avoid duplicating" in queued_followups[0].read_text()

    _run_controller(environment, "retarget", "researcher-1", second_prompt)
    history = list((state_root / "prompts.history").glob("researcher-1.*.md"))
    assert len(history) == 1
    assert "First mandate." in history[0].read_text()
    assert "Second mandate." in (state_root / "prompts/researcher-1.md").read_text()

    _run_controller(environment, "retire", "researcher-1")
    assert not (state_root / "prompts/researcher-1.md").exists()
    retired = list((state_root / "prompts.disabled").glob("researcher-1.*.md"))
    assert len(retired) == 1
    assert "Second mandate." in retired[0].read_text()
    assert (state_root / "keys/researcher-1.pem").stat().st_mode & 0o777 == 0o600


def test_controller_rejects_unconfirmed_contract_and_invalid_runtime(tmp_path: Path) -> None:
    environment, _ = _controller_environment(tmp_path)
    invalid_prompt = tmp_path / "invalid.md"
    _write_prompt(invalid_prompt, effort="ultra")

    result = subprocess.run(
        [sys.executable, _controller_path(), "new", "researcher-1", invalid_prompt],
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "unsupported effort" in result.stderr

    text = invalid_prompt.read_text().replace("effort: ultra", "effort: high")
    invalid_prompt.write_text(text.replace("tier: default", "tier: flex"))
    result = subprocess.run(
        [sys.executable, _controller_path(), "new", "researcher-1", invalid_prompt],
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "only tier: default" in result.stderr

    _write_prompt(invalid_prompt, contract_confirmed=False)
    result = subprocess.run(
        [sys.executable, _controller_path(), "new", "researcher-1", invalid_prompt],
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "contract-confirmed must be true" in result.stderr


def test_controller_is_packaged_and_old_linux_adapter_is_removed() -> None:
    wrapper = _controller_path().read_text()
    source = Path(controller.__file__).read_text()
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert wrapper.startswith("#!/usr/bin/env python3")
    assert "discovery_net.research_team.controller import main" in wrapper
    assert 'research-team = "discovery_net.research_team.controller:main"' in pyproject
    assert "systemctl" not in source
    assert not (_skill_root() / "scripts/run-agent").exists()
    assert not (_skill_root() / "assets/research-team-agent@.service").exists()
    compile(source, str(controller.__file__), "exec")


def test_sdk_pass_resumes_thread_records_usage_and_avoids_repeating_prompt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(tmp_path / "state"))
    controller.ensure_state()
    prompt = controller.prompt_path("principal-1")
    _write_prompt(
        prompt,
        role="principal",
        mode="oneshot",
        effort="high",
        workspace=tmp_path / "workspace",
        body="Inspect the team independently.",
    )
    controller.state_path("work", "principal-1", "reports").mkdir(parents=True)
    controller.state_path("followups", "principal-1").mkdir(parents=True)
    followup = controller.state_path("followups", "principal-1", "followup.1.md")
    followup.write_text("Focus on recent marginal progress.\n")

    observed: dict[str, Any] = {"inputs": [], "options": []}

    class FakeThreadOptions:
        def __init__(self, **values: Any) -> None:
            observed["options"].append(values)

    class FakeThread:
        def __init__(self, thread_id: str = "thread-123") -> None:
            self.id = thread_id

        async def run(self, prompt_text: str) -> SimpleNamespace:
            observed["inputs"].append(prompt_text)
            usage = SimpleNamespace(input_tokens=120, cached_input_tokens=40, output_tokens=30)
            return SimpleNamespace(final_response="completed", usage=usage)

    class FakeCodex:
        def __init__(self, **options: Any) -> None:
            observed["codex_options"] = options

        def start_thread(self, options: object) -> FakeThread:
            return FakeThread()

        def resume_thread(self, thread_id: str, options: object) -> FakeThread:
            assert thread_id == "thread-123"
            return FakeThread(thread_id)

    monkeypatch.setattr(controller, "load_codex_sdk", lambda: (FakeCodex, FakeThreadOptions))
    fake_codex = tmp_path / "codex-default-tier"
    monkeypatch.setattr(controller, "codex_wrapper", lambda: fake_codex)

    asyncio.run(controller.run_one_pass("principal-1"))
    asyncio.run(controller.run_one_pass("principal-1"))

    assert "Inspect the team independently." in observed["inputs"][0]
    assert "Focus on recent marginal progress." in observed["inputs"][0]
    assert observed["inputs"][1].startswith("Continue the autonomous campaign")
    assert observed["options"][0]["model_reasoning_effort"] == "high"
    assert observed["options"][0]["sandbox_mode"] == "workspace-write"
    assert observed["options"][0]["network_access_enabled"] is True
    assert observed["options"][0]["web_search_mode"] == "live"
    assert observed["options"][0]["working_directory"] == str((tmp_path / "workspace").resolve())
    assert observed["codex_options"]["codex_path_override"] == str(fake_codex)
    assert controller.state_path("work", "principal-1", "thread-id").read_text().strip() == (
        "thread-123"
    )
    usage_records = [
        json.loads(line)
        for line in controller.state_path("work", "principal-1", "usage.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(usage_records) == 2
    assert usage_records[0]["total_tokens"] == 150
    assert not list(controller.state_path("followups", "principal-1").iterdir())
    last_run = controller.read_last_run("principal-1")
    assert last_run is not None
    assert last_run["status"] == "completed"


def test_machine_readable_status_report_wait_and_limits(tmp_path: Path, monkeypatch: Any) -> None:
    environment, state_root = _controller_environment(tmp_path)
    prompt = tmp_path / "principal.md"
    _write_prompt(
        prompt,
        role="principal",
        mode="oneshot",
        max_passes=1,
        max_total_tokens=200,
    )
    _run_controller(environment, "new", "principal-1", prompt)

    status = json.loads(_run_controller(environment, "status", "--json").stdout)
    assert status[0]["name"] == "principal-1"
    assert status[0]["workspace"] == str((tmp_path / "workspace").resolve())
    assert status[0]["limits"] == {"max_passes": 1, "max_total_tokens": 200}

    report = state_root / "work/principal-1/last-message.md"
    report.write_text("Independent assessment.\n")
    (state_root / "work/principal-1/last-run.json").write_text(json.dumps({"status": "completed"}))
    assert (
        "principal-1 completed"
        in _run_controller(environment, "wait", "principal-1", "--timeout", "1").stdout
    )
    assert _run_controller(environment, "report", "principal-1").stdout == (
        "Independent assessment.\n"
    )

    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(state_root))
    usage = state_root / "work/principal-1/usage.jsonl"
    usage.write_text(json.dumps({"input_tokens": 150, "output_tokens": 50}) + "\n")
    config = controller.parse_prompt(state_root / "prompts/principal-1.md")
    assert controller.limit_reason("principal-1", config) == "max-passes reached (1/1)"


def test_controller_rejects_shared_agent_workspace(tmp_path: Path) -> None:
    environment, _ = _controller_environment(tmp_path)
    workspace = tmp_path / "shared-workspace"
    first_prompt = tmp_path / "first.md"
    second_prompt = tmp_path / "second.md"
    _write_prompt(first_prompt, workspace=workspace)
    _write_prompt(second_prompt, workspace=workspace)
    _run_controller(environment, "new", "researcher-1", first_prompt)

    result = subprocess.run(
        [sys.executable, _controller_path(), "new", "researcher-2", second_prompt],
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "each agent needs its own workspace" in result.stderr
