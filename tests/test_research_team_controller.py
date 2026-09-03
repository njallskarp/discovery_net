from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".agents" / "skills" / "orchestrate-research-team"


def _controller_path() -> Path:
    return _skill_root() / "scripts" / "research-team"


def _load_controller() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader(
        "research_team_controller", str(_controller_path())
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def _write_prompt(
    path: Path,
    *,
    role: str = "researcher",
    mode: str = "continuous",
    effort: str = "xhigh",
    body: str = "Work autonomously.",
) -> None:
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


def test_controller_rejects_non_default_tier_and_invalid_effort(tmp_path: Path) -> None:
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


def test_controller_is_python_and_old_linux_adapter_is_removed() -> None:
    source = _controller_path().read_text()
    assert source.startswith("#!/usr/bin/env python3")
    assert "systemctl" not in source
    assert not (_skill_root() / "scripts/run-agent").exists()
    assert not (_skill_root() / "assets/research-team-agent@.service").exists()
    compile(source, str(_controller_path()), "exec")


def test_sdk_pass_resumes_thread_records_usage_and_avoids_repeating_prompt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    controller = _load_controller()
    monkeypatch.setenv("DISCOVERY_RESEARCH_TEAM_ROOT", str(tmp_path / "state"))
    controller.ensure_state()
    prompt = controller.prompt_path("principal-1")
    _write_prompt(
        prompt,
        role="principal",
        mode="oneshot",
        effort="high",
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

    asyncio.run(controller.run_one_pass("principal-1"))
    asyncio.run(controller.run_one_pass("principal-1"))

    assert "Inspect the team independently." in observed["inputs"][0]
    assert "Focus on recent marginal progress." in observed["inputs"][0]
    assert observed["inputs"][1].startswith("Continue the autonomous campaign")
    assert observed["options"][0]["model_reasoning_effort"] == "high"
    assert observed["options"][0]["sandbox_mode"] == "workspace-write"
    assert observed["options"][0]["network_access_enabled"] is True
    assert observed["options"][0]["web_search_mode"] == "live"
    assert str(observed["codex_options"]["codex_path_override"]).endswith("codex-default-tier")
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
