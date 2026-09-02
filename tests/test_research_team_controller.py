from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1] / ".agents" / "skills" / "orchestrate-research-team"


def _write_prompt(path: Path, *, effort: str = "xhigh", body: str = "Work autonomously.") -> None:
    path.write_text(
        "\n".join(
            (
                "role: researcher",
                "mode: continuous",
                f"effort: {effort}",
                "tier: default",
                "restart-seconds: 1800",
                "permissions: workspace-write",
                "",
                body,
                "",
            )
        )
    )


def _controller_environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    state_root = tmp_path / "state"
    for relative in (
        "bin",
        "prompts",
        "prompts.history",
        "prompts.disabled",
        "keys",
        "followups",
        "work",
    ):
        (state_root / relative).mkdir(parents=True, exist_ok=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {systemctl_log}\n"
        'if [[ "${1:-}" == is-active ]]; then echo inactive; fi\n'
    )
    fake_systemctl.chmod(0o755)

    config_file = tmp_path / "controller.conf"
    config_file.write_text(
        f"OPERATOR={os.environ.get('USER', 'nobody')}\n"
        f"CODEX_BINARY={shutil.which('true') or '/usr/bin/true'}\n"
        "AGENT_CAP=8\n"
    )
    unit_file = tmp_path / "research-team-agent@.service"
    unit_file.write_text("[Service]\n")

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "DISCOVERY_RESEARCH_TEAM_TESTING": "1",
            "DISCOVERY_RESEARCH_TEAM_ROOT": str(state_root),
            "DISCOVERY_RESEARCH_TEAM_CONFIG": str(config_file),
            "DISCOVERY_RESEARCH_TEAM_COMMAND": str(_skill_root() / "scripts" / "research-team"),
            "DISCOVERY_RESEARCH_TEAM_UNIT": str(unit_file),
            "DISCOVERY_RESEARCH_TEAM_OPERATOR": os.environ.get("USER", "nobody"),
        }
    )
    return environment, state_root, systemctl_log


def test_controller_preserves_visible_prompt_history_and_retired_state(tmp_path: Path) -> None:
    controller = _skill_root() / "scripts" / "research-team"
    environment, state_root, systemctl_log = _controller_environment(tmp_path)
    first_prompt = tmp_path / "first.md"
    second_prompt = tmp_path / "second.md"
    _write_prompt(first_prompt, body="First mandate.")
    _write_prompt(second_prompt, effort="high", body="Second mandate.")

    subprocess.run(
        [controller, "new", "researcher-1", first_prompt],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    shown = subprocess.run(
        [controller, "prompt", "researcher-1"],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    assert "First mandate." in shown.stdout
    assert "effort: xhigh" in shown.stdout

    followup = tmp_path / "followup.md"
    followup.write_text("Stay in this area, but avoid duplicating the other lane.\n")
    subprocess.run(
        [controller, "continue", "researcher-1", followup],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    queued_followups = list((state_root / "followups/researcher-1").glob("followup.*"))
    assert len(queued_followups) == 1
    assert "avoid duplicating" in queued_followups[0].read_text()

    subprocess.run(
        [controller, "retarget", "researcher-1", second_prompt],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    history = list((state_root / "prompts.history").glob("researcher-1.*.md"))
    assert len(history) == 1
    assert "First mandate." in history[0].read_text()
    assert "Second mandate." in (state_root / "prompts/researcher-1.md").read_text()

    subprocess.run(
        [controller, "retire", "researcher-1"],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    assert not (state_root / "prompts/researcher-1.md").exists()
    retired = list((state_root / "prompts.disabled").glob("researcher-1.*.md"))
    assert len(retired) == 1
    assert "Second mandate." in retired[0].read_text()
    systemctl_calls = systemctl_log.read_text()
    assert "enable --now discovery-research-agent@researcher-1.service" in systemctl_calls
    assert "disable --now discovery-research-agent@researcher-1.service" in systemctl_calls


def test_controller_rejects_implicit_or_invalid_runtime_settings(tmp_path: Path) -> None:
    controller = _skill_root() / "scripts" / "research-team"
    environment, _, _ = _controller_environment(tmp_path)
    invalid_prompt = tmp_path / "invalid.md"
    invalid_prompt.write_text(
        "role: researcher\n"
        "mode: continuous\n"
        "tier: default\n"
        "restart-seconds: 30\n"
        "permissions: workspace-write\n"
    )

    result = subprocess.run(
        [controller, "new", "researcher-1", invalid_prompt],
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "unsupported effort" in result.stderr


def test_controller_scripts_are_valid_bash() -> None:
    for script_name in ("research-team", "run-agent"):
        subprocess.run(
            ["bash", "-n", _skill_root() / "scripts" / script_name],
            check=True,
        )


def test_runner_applies_explicit_metadata_and_archives_a_oneshot_report(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"
    prompt_directory = state_root / "prompts"
    work_directory = state_root / "work/principal-1"
    followup_directory = state_root / "followups/principal-1"
    prompt_directory.mkdir(parents=True)
    work_directory.mkdir(parents=True)
    followup_directory.mkdir(parents=True)
    prompt = prompt_directory / "principal-1.md"
    prompt.write_text(
        "role: principal\n"
        "mode: oneshot\n"
        "effort: high\n"
        "tier: default\n"
        "restart-seconds: 0\n"
        "permissions: workspace-write\n"
        "\nInspect the team independently.\n"
    )
    (followup_directory / "followup.000001").write_text(
        "Focus the assessment on recent marginal progress.\n"
    )
    config = tmp_path / "controller.conf"
    config.write_text("CODEX_BINARY=/unused\n")
    argument_log = tmp_path / "codex-arguments.txt"
    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" > {argument_log}\n"
        "while [[ $# -gt 0 ]]; do\n"
        '  if [[ "$1" == -o ]]; then shift; printf \'completed\\n\' > "$1"; fi\n'
        "  shift\n"
        "done\n"
    )
    fake_codex.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "DISCOVERY_RESEARCH_TEAM_ROOT": str(state_root),
            "DISCOVERY_RESEARCH_TEAM_CONFIG": str(config),
            "DISCOVERY_RESEARCH_TEAM_CODEX": str(fake_codex),
        }
    )

    subprocess.run(
        [_skill_root() / "scripts/run-agent", "principal-1"],
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )

    arguments = argument_log.read_text()
    assert "model_reasoning_effort=high" in arguments
    assert "service_tier=default" in arguments
    assert "--full-auto" in arguments
    assert "Inspect the team independently." in arguments
    assert "Focus the assessment on recent marginal progress." in arguments
    reports = [
        path
        for path in (work_directory / "reports").glob("*.md")
        if not path.name.startswith("followup-")
    ]
    assert len(reports) == 1
    assert reports[0].read_text() == "completed\n"
    archived_followups = list((work_directory / "reports").glob("followup-*.md"))
    assert len(archived_followups) == 1
    assert not list(followup_directory.iterdir())
