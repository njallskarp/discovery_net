"""Claude Code runner for the research-team controller.

The controller drives one headless ``claude -p`` process per pass. Each agent keeps a
Claude Code session ID so later passes resume the same conversation, mirroring the
Codex thread that the default runner keeps. The CLI is authenticated by the operator's
existing Claude Code login; no API key is read or written here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
WEB_SEARCH_MODES = frozenset({"disabled", "live"})
BINARY_ENVIRONMENT = "DISCOVERY_RESEARCH_TEAM_CLAUDE"
BINARY_CANDIDATES = (
    Path.home() / ".local" / "bin" / "claude",
    Path.home() / ".claude" / "local" / "claude",
)
# A parent Claude Code session exports CLAUDE* variables that a nested headless run must
# not inherit, or it would attach itself to the parent's transport and effort setting.
# CLAUDE_CONFIG_DIR is operator configuration rather than session state and is kept.
INHERITED_PREFIX = "CLAUDE"
PRESERVED_VARIABLES = frozenset({"CLAUDE_CONFIG_DIR"})
RESUME_FAILURE_MARKERS = ("no conversation found", "session not found", "could not find session")


class ClaudeCodeError(RuntimeError):
    """A user-facing Claude Code runner error."""


@dataclass(frozen=True)
class PassResult:
    response: str
    session_id: str
    input_tokens: int
    cached_input_tokens: int
    cache_creation_input_tokens: int
    output_tokens: int
    cost_usd: float
    num_turns: int
    resumed: bool


def find_claude() -> Path:
    configured = os.environ.get(BINARY_ENVIRONMENT)
    if configured:
        path = Path(configured).expanduser()
        if not (path.is_file() and os.access(path, os.X_OK)):
            raise ClaudeCodeError(f"{BINARY_ENVIRONMENT} is not an executable file: {path}")
        return path
    found = shutil.which("claude")
    if found:
        return Path(found)
    for candidate in BINARY_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise ClaudeCodeError(
        "Claude Code CLI is not available; put `claude` on PATH or set "
        f"{BINARY_ENVIRONMENT} to its absolute path"
    )


def runtime_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if base is None else base
    return {
        key: value
        for key, value in source.items()
        if key in PRESERVED_VARIABLES or not key.startswith(INHERITED_PREFIX)
    }


def new_session_id() -> str:
    return str(uuid.uuid4())


def build_command(
    *,
    binary: Path,
    model: str | None,
    effort: str,
    permissions: str,
    web_search: str,
    session_id: str,
    resume: bool,
    max_pass_usd: float | None,
) -> list[str]:
    if effort not in EFFORTS:
        raise ClaudeCodeError(f"unsupported effort for claude-code: {effort}")
    if web_search not in WEB_SEARCH_MODES:
        raise ClaudeCodeError(f"unsupported web-search mode for claude-code: {web_search}")
    command = [
        str(binary),
        "-p",
        "--output-format",
        "json",
        "--effort",
        effort,
        "--setting-sources",
        "project",
        "--strict-mcp-config",
    ]
    if model:
        command += ["--model", model]
    if permissions == "unrestricted":
        command += ["--permission-mode", "bypassPermissions"]
    elif permissions == "workspace-write":
        # File tools stay inside the workspace; shell and web tools run without prompts,
        # because a headless pass has nobody to answer one.
        command += ["--permission-mode", "acceptEdits", "--allowedTools", "Bash"]
        if web_search == "live":
            command += ["WebSearch", "WebFetch"]
    else:
        raise ClaudeCodeError(f"unsupported permissions for claude-code: {permissions}")
    if web_search == "disabled":
        command += ["--disallowedTools", "WebSearch", "WebFetch"]
    if max_pass_usd is not None:
        command += ["--max-budget-usd", f"{max_pass_usd:g}"]
    command += ["--resume", session_id] if resume else ["--session-id", session_id]
    return command


def parse_result(stdout: str) -> dict[str, Any]:
    """Return the final ``result`` object from ``--output-format json`` output."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("type") == "result":
            return value
    raise ClaudeCodeError("Claude Code produced no result object")


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _invoke(
    command: list[str], *, prompt: str, workspace: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=prompt,
        cwd=workspace,
        env=runtime_environment(),
        check=False,
        text=True,
        capture_output=True,
    )


def _looks_like_lost_session(completed: subprocess.CompletedProcess[str]) -> bool:
    text = (completed.stderr + completed.stdout).lower()
    return any(marker in text for marker in RESUME_FAILURE_MARKERS)


def run_pass(
    *,
    prompt: str,
    fresh_prompt: str,
    workspace: Path,
    model: str | None,
    effort: str,
    permissions: str,
    web_search: str,
    session_id: str | None,
    max_pass_usd: float | None,
) -> PassResult:
    """Run one pass, resuming ``session_id`` when given.

    ``prompt`` is what the resumed session receives; ``fresh_prompt`` is the complete
    standing mandate used when a new session has to be started, including after a stored
    session can no longer be resumed.
    """
    binary = find_claude()
    resumed = session_id is not None
    active_session = session_id or new_session_id()
    active_prompt = prompt if resumed else fresh_prompt
    command = build_command(
        binary=binary,
        model=model,
        effort=effort,
        permissions=permissions,
        web_search=web_search,
        session_id=active_session,
        resume=resumed,
        max_pass_usd=max_pass_usd,
    )
    completed = _invoke(command, prompt=active_prompt, workspace=workspace)
    if completed.returncode != 0 and resumed and _looks_like_lost_session(completed):
        resumed = False
        active_session = new_session_id()
        command = build_command(
            binary=binary,
            model=model,
            effort=effort,
            permissions=permissions,
            web_search=web_search,
            session_id=active_session,
            resume=False,
            max_pass_usd=max_pass_usd,
        )
        completed = _invoke(command, prompt=fresh_prompt, workspace=workspace)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise ClaudeCodeError(f"Claude Code exited {completed.returncode}: {detail[-2000:]}")
    result = parse_result(completed.stdout)
    if result.get("is_error"):
        detail = str(result.get("result") or result.get("subtype") or "unknown error")
        raise ClaudeCodeError(f"Claude Code pass failed: {detail[:2000]}")
    usage = result.get("usage") or {}
    return PassResult(
        response=str(result.get("result") or ""),
        session_id=str(result.get("session_id") or active_session),
        input_tokens=_integer(usage.get("input_tokens")),
        cached_input_tokens=_integer(usage.get("cache_read_input_tokens")),
        cache_creation_input_tokens=_integer(usage.get("cache_creation_input_tokens")),
        output_tokens=_integer(usage.get("output_tokens")),
        cost_usd=float(result.get("total_cost_usd") or 0.0),
        num_turns=_integer(result.get("num_turns")),
        resumed=resumed,
    )


def doctor() -> str:
    binary = find_claude()
    environment = runtime_environment()
    version = subprocess.run(
        [str(binary), "--version"], check=False, text=True, capture_output=True, env=environment
    )
    if version.returncode != 0:
        raise ClaudeCodeError("Claude Code CLI could not start")
    status = subprocess.run(
        [str(binary), "auth", "status"],
        check=False,
        text=True,
        capture_output=True,
        env=environment,
    )
    try:
        parsed = json.loads(status.stdout) if status.returncode == 0 else {}
    except json.JSONDecodeError:
        parsed = {}
    if not parsed.get("loggedIn"):
        raise ClaudeCodeError("Claude Code CLI is not logged in; run `claude` and sign in")
    auth = parsed.get("authMethod", "unknown")
    subscription = parsed.get("subscriptionType")
    account = f"{auth} ({subscription})" if subscription else auth
    return f"{version.stdout.strip()} at {binary}; auth {account}"
