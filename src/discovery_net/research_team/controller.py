#!/usr/bin/env python3
"""Cross-platform controller for a standing team of Codex or Claude Code research agents."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from discovery_net.research_team import claude_code
from discovery_net.research_team.impact import (
    ImpactContext,
    build_impact_context,
    impact_prompt,
    parse_impact_batch,
    record_impact_batch,
    rejection_note,
    run_identifier,
)

MINIMUM_SDK_VERSION = (0, 22, 0)
MAXIMUM_SDK_VERSION = (0, 23, 0)
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
ROLES = {"researcher", "reviewer", "principal", "orchestrator", "impact-assessor"}
MODES = {"continuous", "oneshot"}
RUNNERS = {"codex", "claude-code"}
CODEX_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
EFFORTS = CODEX_EFFORTS | claude_code.EFFORTS
TIERS = {"default", "flex"}
PERMISSIONS = {"workspace-write", "unrestricted"}
WEB_SEARCH_MODES = {"disabled", "cached", "live"}
GITHUB_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
GITHUB_ACCESS_TIMEOUT_SECONDS = 20
METADATA_KEYS = {
    "role",
    "mode",
    "effort",
    "tier",
    "restart-seconds",
    "permissions",
    "network-access",
    "web-search",
    "workspace",
    "github-repository",
    "ledger-path",
    "contract-confirmed",
    "max-passes",
    "max-total-tokens",
    "model",
    "runner",
    "max-pass-usd",
}
OPTIONAL_METADATA_KEYS = {"model", "ledger-path", "runner", "max-pass-usd"}
TESTING = os.environ.get("DISCOVERY_RESEARCH_TEAM_TESTING") == "1"


class ControllerError(RuntimeError):
    """A user-facing controller error."""


IMPACT_REJECTION_PREFIX = "invalid impact-assessor response: "


class WorkerStopped(Exception):
    """Raised inside a worker when the controller asks it to stop."""


def _handle_worker_signal(signum: int, frame: object) -> None:
    # Stop the CLI first: asyncio.run() only re-raises once its worker thread returns, and
    # that thread is blocked on the CLI process. Ending the CLI here lets the exception
    # reach the pass loop within seconds so the interruption is recorded as a failure.
    claude_code.terminate_active(grace_seconds=5.0)
    raise WorkerStopped(f"worker received signal {signum} while a pass was running")


def current_pass_path(name: str) -> Path:
    return state_path("work", name, "current-pass.json")


@dataclass(frozen=True)
class PromptConfig:
    role: str
    mode: str
    effort: str
    tier: str
    restart_seconds: int
    permissions: str
    network_access: bool
    web_search: str
    workspace: Path
    github_repository: str
    ledger_path: Path | None
    max_passes: int | None
    max_total_tokens: int | None
    model: str | None
    runner: str
    max_pass_usd: float | None
    text: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


def state_root() -> Path:
    configured = os.environ.get("DISCOVERY_RESEARCH_TEAM_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".discovery-research-team"


def state_path(*parts: str) -> Path:
    return state_root().joinpath(*parts)


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def iso_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def ensure_state() -> None:
    root = state_root()
    for relative in (
        "prompts",
        "prompts.history",
        "prompts.disabled",
        "keys",
        "followups",
        "work",
        "runtime",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    config = root / "config.json"
    if not config.exists():
        atomic_write(config, json.dumps({"agent_cap": 8}, indent=2) + "\n")


@contextmanager
def state_lock() -> Iterator[None]:
    ensure_state()
    lock_path = state_path("controller.lock")
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def append_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as output:
        output.write(json.dumps(record, sort_keys=True) + "\n")


def record_change(message: str) -> None:
    with state_path("changes.log").open("a") as log:
        log.write(f"{iso_timestamp()} {message}\n")


def validate_name(name: str) -> None:
    if not NAME_PATTERN.fullmatch(name):
        raise ControllerError(f"invalid agent name: {name}")


def parse_bool(value: str, key: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ControllerError(f"{key} must be true or false")


def parse_limit(value: str, key: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ControllerError(f"{key} must be a non-negative integer") from exc
    if parsed < 0:
        raise ControllerError(f"{key} must be a non-negative integer")
    return parsed or None


def parse_dollars(value: str, key: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ControllerError(f"{key} must be a non-negative number of US dollars") from exc
    if parsed < 0 or parsed != parsed:
        raise ControllerError(f"{key} must be a non-negative number of US dollars")
    return parsed or None


def parse_github_repository(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or len(parts) != 2
    ):
        raise ControllerError(
            "github-repository must be an https://github.com/OWNER/REPOSITORY URL"
        )
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not GITHUB_OWNER_PATTERN.fullmatch(owner) or not GITHUB_REPOSITORY_PATTERN.fullmatch(
        repository
    ):
        raise ControllerError(
            "github-repository must be an https://github.com/OWNER/REPOSITORY URL"
        )
    return f"https://github.com/{owner}/{repository}", f"git@github.com:{owner}/{repository}.git"


def verify_github_repository(value: str) -> str:
    web_url, ssh_url = parse_github_repository(value)
    git = shutil.which("git")
    if git is None:
        raise ControllerError("git is required to verify github-repository access")
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")
    failures: list[str] = []
    for remote in (ssh_url, f"{web_url}.git"):
        try:
            result = subprocess.run(
                [git, "ls-remote", "--exit-code", remote, "HEAD"],
                check=False,
                text=True,
                capture_output=True,
                timeout=GITHUB_ACCESS_TIMEOUT_SECONDS,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            failures.append("timed out")
            continue
        if result.returncode == 0 and result.stdout.strip():
            return web_url
        failures.append(f"git exited {result.returncode}")
    detail = ", ".join(failures)
    raise ControllerError(f"GitHub repository is not accessible: {web_url} ({detail})")


def parse_prompt(path: Path) -> PromptConfig:
    if not path.is_file():
        raise ControllerError(f"prompt file not found: {path}")
    text = path.read_text()
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    body_start = len(lines)
    for index, line in enumerate(lines):
        if not line.strip():
            body_start = index + 1
            break
        if ":" not in line:
            raise ControllerError("prompt metadata must end with a blank line")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key not in METADATA_KEYS:
            raise ControllerError(f"unsupported prompt metadata: {key}")
        if key in metadata:
            raise ControllerError(f"duplicate prompt metadata: {key}")
        metadata[key] = value

    required = METADATA_KEYS - OPTIONAL_METADATA_KEYS
    missing = sorted(required - metadata.keys())
    if missing:
        raise ControllerError(f"prompt is missing metadata: {', '.join(missing)}")
    if metadata["role"] not in ROLES:
        raise ControllerError(f"unsupported role: {metadata['role']}")
    if metadata["mode"] not in MODES:
        raise ControllerError(f"unsupported mode: {metadata['mode']}")
    runner = metadata.get("runner", "codex")
    if runner not in RUNNERS:
        raise ControllerError(f"unsupported runner: {runner}")
    if metadata["effort"] not in EFFORTS:
        raise ControllerError(f"unsupported effort: {metadata['effort']}")
    if metadata["tier"] not in TIERS:
        raise ControllerError(f"unsupported tier: {metadata['tier']}")
    max_pass_usd = parse_dollars(metadata.get("max-pass-usd", "0"), "max-pass-usd")
    if runner == "claude-code":
        if metadata["effort"] not in claude_code.EFFORTS:
            raise ControllerError(
                f"unsupported effort for claude-code: {metadata['effort']} "
                f"(use one of {', '.join(sorted(claude_code.EFFORTS))})"
            )
        if metadata["tier"] != "default":
            raise ControllerError("claude-code has no service tiers; use tier: default")
        if metadata["web-search"] not in claude_code.WEB_SEARCH_MODES:
            raise ControllerError("claude-code web-search must be disabled or live")
    else:
        if metadata["effort"] not in CODEX_EFFORTS:
            raise ControllerError(f"unsupported effort for codex: {metadata['effort']}")
        if max_pass_usd is not None:
            raise ControllerError("max-pass-usd is only supported by the claude-code runner")
    if metadata["permissions"] not in PERMISSIONS:
        raise ControllerError(f"unsupported permissions: {metadata['permissions']}")
    if metadata["web-search"] not in WEB_SEARCH_MODES:
        raise ControllerError(f"unsupported web-search mode: {metadata['web-search']}")
    if not parse_bool(metadata["contract-confirmed"], "contract-confirmed"):
        raise ControllerError("contract-confirmed must be true before an agent can be configured")
    workspace = Path(metadata["workspace"]).expanduser()
    if not workspace.is_absolute():
        raise ControllerError("workspace must be an absolute path")
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ControllerError(f"workspace directory not found: {workspace}")
    try:
        restart_seconds = int(metadata["restart-seconds"])
    except ValueError as exc:
        raise ControllerError("restart-seconds must be an integer") from exc
    if metadata["mode"] == "continuous" and restart_seconds < 60:
        raise ControllerError("continuous agents need restart-seconds of at least 60")
    if metadata["mode"] == "oneshot" and restart_seconds != 0:
        raise ControllerError("oneshot agents need restart-seconds: 0")
    if not "\n".join(lines[body_start:]).strip():
        raise ControllerError("prompt mandate is empty")
    network_access = parse_bool(metadata["network-access"], "network-access")
    if not network_access:
        raise ControllerError("network-access must be true for the required GitHub repository")
    github_repository, _ = parse_github_repository(metadata["github-repository"])
    ledger_path: Path | None = None
    if "ledger-path" in metadata:
        ledger_path = Path(metadata["ledger-path"]).expanduser()
        if not ledger_path.is_absolute():
            raise ControllerError("ledger-path must be an absolute path")
        ledger_path = ledger_path.resolve()
    if metadata["role"] == "impact-assessor":
        if ledger_path is None:
            raise ControllerError("impact-assessor prompts require ledger-path")
        if not ledger_path.is_file():
            raise ControllerError(f"artifact ledger does not exist: {ledger_path}")
    return PromptConfig(
        role=metadata["role"],
        mode=metadata["mode"],
        effort=metadata["effort"],
        tier=metadata["tier"],
        restart_seconds=restart_seconds,
        permissions=metadata["permissions"],
        network_access=network_access,
        web_search=metadata["web-search"],
        workspace=workspace,
        github_repository=github_repository,
        ledger_path=ledger_path,
        max_passes=parse_limit(metadata["max-passes"], "max-passes"),
        max_total_tokens=parse_limit(metadata["max-total-tokens"], "max-total-tokens"),
        model=metadata.get("model") or None,
        runner=runner,
        max_pass_usd=max_pass_usd,
        text=text,
    )


def prompt_path(name: str) -> Path:
    return state_path("prompts", f"{name}.md")


def require_agent(name: str) -> Path:
    validate_name(name)
    path = prompt_path(name)
    if not path.is_file():
        raise ControllerError(f"unknown agent: {name}")
    return path


def require_known_agent(name: str) -> None:
    validate_name(name)
    if not prompt_path(name).exists() and not state_path("work", name).is_dir():
        raise ControllerError(f"unknown agent: {name}")


def agent_names() -> list[str]:
    ensure_state()
    return sorted(path.stem for path in state_path("prompts").glob("*.md"))


def ensure_workspace_is_exclusive(name: str, workspace: Path) -> None:
    for other_name in agent_names():
        if other_name == name:
            continue
        other = parse_prompt(prompt_path(other_name))
        if other.workspace == workspace:
            raise ControllerError(
                f"workspace is already assigned to {other_name}; each agent needs its own workspace"
            )


def ensure_impact_assessor_is_unique(name: str, role: str) -> None:
    if role != "impact-assessor":
        return
    for other_name in agent_names():
        if other_name != name and parse_prompt(prompt_path(other_name)).role == "impact-assessor":
            raise ControllerError("only one active impact-assessor is allowed")


def config_value(key: str, default: Any) -> Any:
    ensure_state()
    try:
        config = json.loads(state_path("config.json").read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ControllerError("controller config is unreadable") from exc
    return config.get(key, default)


def generate_key(name: str) -> None:
    key_path = state_path("keys", f"{name}.pem")
    if key_path.exists():
        return
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise ControllerError("cryptography is required to generate agent identity keys") from exc
    private_key = Ed25519PrivateKey.generate()
    encoded = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    atomic_write(key_path, encoded.decode(), mode=0o600)


def codex_wrapper(tier: str) -> Path:
    """Create a Python shim that pins the requested service tier for SDK-launched Codex."""
    if tier not in TIERS:
        raise ControllerError(f"unsupported tier: {tier}")
    codex = shutil.which("codex")
    if codex is None:
        raise ControllerError("Codex CLI is not available on PATH")
    wrapper = state_path("bin", f"codex-{tier}-tier")
    source = (
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        f"codex = {codex!r}\n"
        f"os.execv(codex, [codex, '--config', 'service_tier=\"{tier}\"', *sys.argv[1:]])\n"
    )
    if not wrapper.exists() or wrapper.read_text() != source:
        atomic_write(wrapper, source, mode=0o755)
    return wrapper


def runtime_path(name: str) -> Path:
    return state_path("runtime", f"{name}.json")


def last_run_path(name: str) -> Path:
    return state_path("work", name, "last-run.json")


def write_last_run(name: str, record: dict[str, Any]) -> None:
    atomic_write(last_run_path(name), json.dumps(record, indent=2, sort_keys=True) + "\n")


def read_last_run(name: str) -> dict[str, Any] | None:
    try:
        value = json.loads(last_run_path(name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_runtime(name: str) -> dict[str, Any] | None:
    try:
        value = json.loads(runtime_path(name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def worker_lock_path(name: str) -> Path:
    return state_path("runtime", f"{name}.lock")


def worker_holds_lock(name: str) -> bool:
    with worker_lock_path(name).open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return False


@contextmanager
def hold_worker_lock(name: str) -> Iterator[None]:
    with worker_lock_path(name).open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def process_matches(name: str, runtime: dict[str, Any]) -> bool:
    try:
        pid = int(runtime["pid"])
        os.kill(pid, 0)
    except (KeyError, TypeError, ValueError, ProcessLookupError, PermissionError):
        return False
    return worker_holds_lock(name)


def running_runtime(name: str) -> dict[str, Any] | None:
    runtime = read_runtime(name)
    if runtime is not None and process_matches(name, runtime):
        return runtime
    runtime_path(name).unlink(missing_ok=True)
    return None


def spawn_worker(name: str) -> int | None:
    if running_runtime(name) is not None:
        raise ControllerError(f"agent is already running: {name}")
    last_run_path(name).unlink(missing_ok=True)
    current_pass_path(name).unlink(missing_ok=True)
    nonce = secrets.token_hex(16)
    if TESTING:
        with state_path("launches.log").open("a") as log:
            log.write(f"{name} {nonce}\n")
        return None
    preflight_runner(parse_prompt(require_agent(name)))
    work = state_path("work", name)
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "agent.log"
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "discovery_net.research_team.controller",
                "_worker",
                name,
                "--nonce",
                nonce,
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=work,
            start_new_session=True,
            close_fds=True,
            env=os.environ.copy(),
        )
    atomic_write(
        runtime_path(name),
        json.dumps({"pid": process.pid, "nonce": nonce, "started_at": iso_timestamp()}, indent=2)
        + "\n",
    )
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if worker_holds_lock(name):
            break
        if process.poll() is not None:
            raise ControllerError(f"agent worker exited during startup: {name}")
        time.sleep(0.02)
    return process.pid


def stop_worker(name: str, *, quiet: bool = False) -> bool:
    runtime = running_runtime(name)
    if runtime is None:
        if not quiet:
            print(f"{name} is not running")
        return False
    pid = int(runtime["pid"])
    if TESTING:
        runtime_path(name).unlink(missing_ok=True)
        return True
    try:
        process_group = os.getpgid(pid)
        if process_group == pid:
            os.killpg(process_group, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        runtime_path(name).unlink(missing_ok=True)
        return False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not process_matches(name, runtime):
            runtime_path(name).unlink(missing_ok=True)
            current_pass_path(name).unlink(missing_ok=True)
            return True
        time.sleep(0.1)
    with contextlib.suppress(ProcessLookupError):
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    runtime_path(name).unlink(missing_ok=True)
    current_pass_path(name).unlink(missing_ok=True)
    return True


def new_agent(name: str, source_prompt: Path) -> None:
    validate_name(name)
    config = parse_prompt(source_prompt)
    verify_github_repository(config.github_repository)
    with state_lock():
        if prompt_path(name).exists():
            raise ControllerError(f"agent already exists: {name}")
        names = agent_names()
        cap = int(config_value("agent_cap", 8))
        if len(names) >= cap:
            raise ControllerError(f"agent cap reached: {len(names)}/{cap}")
        ensure_workspace_is_exclusive(name, config.workspace)
        ensure_impact_assessor_is_unique(name, config.role)
        atomic_write(prompt_path(name), config.text)
        for relative in ("tmp", "reports"):
            state_path("work", name, relative).mkdir(parents=True, exist_ok=True)
        state_path("followups", name).mkdir(parents=True, exist_ok=True)
        generate_key(name)
        record_change(f"created {name} role={config.role} mode={config.mode}")
    if config.mode == "continuous":
        pid = spawn_worker(name)
        suffix = f", pid {pid}" if pid is not None else ""
        print(f"created and started {name} ({config.role}{suffix})")
    else:
        print(f"created {name} ({config.role}, oneshot)")


def start_agent(name: str) -> None:
    config = parse_prompt(require_agent(name))
    verify_github_repository(config.github_repository)
    pid = spawn_worker(name)
    record_change(f"started {name}")
    suffix = f" with pid {pid}" if pid is not None else ""
    print(f"started {name}{suffix}")


def continue_agent(name: str, source_note: Path) -> None:
    require_agent(name)
    if not source_note.is_file() or source_note.stat().st_size == 0:
        raise ControllerError(f"follow-up file is missing or empty: {source_note}")
    if source_note.stat().st_size > 65536:
        raise ControllerError("follow-up exceeds 64 KiB")
    queued = state_path("followups", name, f"followup.{timestamp()}.{secrets.token_hex(4)}.md")
    atomic_write(queued, source_note.read_text())
    record_change(f"queued follow-up for {name}")
    print(f"queued a one-pass follow-up for {name}")


def stop_agent(name: str) -> None:
    require_agent(name)
    stopped = stop_worker(name)
    if stopped:
        record_change(f"stopped {name}")
        print(f"stopped {name}; configuration retained")


def retarget_agent(name: str, source_prompt: Path) -> None:
    current = require_agent(name)
    replacement = parse_prompt(source_prompt)
    verify_github_repository(replacement.github_repository)
    with state_lock():
        ensure_workspace_is_exclusive(name, replacement.workspace)
        ensure_impact_assessor_is_unique(name, replacement.role)
        archived = state_path("prompts.history", f"{name}.{timestamp()}.md")
        atomic_write(archived, current.read_text())
        atomic_write(current, replacement.text)
        record_change(f"retargeted {name}; previous={archived.name}")
    print(f"retargeted {name}; takes effect on its next pass")


def retire_agent(name: str) -> None:
    current = require_agent(name)
    stop_worker(name, quiet=True)
    with state_lock():
        retired = state_path("prompts.disabled", f"{name}.{timestamp()}.md")
        current.replace(retired)
        record_change(f"retired {name}; prompt={retired.name}")
    print(f"retired {name}; prompt, key, work, reports, and usage retained")


def status_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for name in agent_names():
        config = parse_prompt(prompt_path(name))
        runtime = running_runtime(name)
        usage = usage_totals(name)
        records.append(
            {
                "name": name,
                "role": config.role,
                "mode": config.mode,
                "runner": config.runner,
                "state": "running" if runtime else "inactive",
                "pid": int(runtime["pid"]) if runtime is not None else None,
                "workspace": str(config.workspace),
                "github_repository": config.github_repository,
                "prompt": str(prompt_path(name)),
                "limits": {
                    "max_passes": config.max_passes or 0,
                    "max_total_tokens": config.max_total_tokens or 0,
                },
                "usage": usage,
                "limit_reason": limit_reason(name, config),
                "last_run": read_last_run(name),
                "stale_pass_marker": runtime is None and current_pass_path(name).exists(),
            }
        )
    return records


def show_status(*, as_json: bool = False) -> None:
    records = status_records()
    if as_json:
        print(json.dumps(records, indent=2, sort_keys=True))
        return
    print(f"{'AGENT':<20} {'ROLE':<13} {'STATE':<10} WORKSPACE")
    for record in records:
        print(
            f"{record['name']:<20} {record['role']:<13} {record['state']:<10} {record['workspace']}"
        )


def show_prompt(name: str) -> None:
    print(require_agent(name).read_text(), end="")


def show_report(name: str) -> None:
    require_known_agent(name)
    path = state_path("work", name, "last-message.md")
    if not path.is_file():
        raise ControllerError(f"no completed report for {name}")
    print(path.read_text(), end="")


def wait_for_agent(name: str, timeout_seconds: float) -> None:
    config = parse_prompt(require_agent(name))
    if config.mode != "oneshot":
        raise ControllerError("wait is supported only for oneshot agents")
    if timeout_seconds <= 0:
        raise ControllerError("wait timeout must be greater than zero")
    deadline = time.monotonic() + timeout_seconds
    while running_runtime(name) is not None:
        if time.monotonic() >= deadline:
            raise ControllerError(f"timed out waiting for {name}")
        time.sleep(0.2)
    result = read_last_run(name)
    if result is None:
        raise ControllerError(f"{name} stopped without recording a result")
    if result.get("status") != "completed":
        raise ControllerError(f"{name} failed: {result.get('error', 'unknown error')}")
    print(f"{name} completed")


def show_history(name: str) -> None:
    validate_name(name)
    paths = [
        *state_path("prompts.history").glob(f"{name}.*.md"),
        *state_path("prompts.disabled").glob(f"{name}.*.md"),
    ]
    for path in sorted(paths):
        print(path)


def tail_lines(path: Path, count: int) -> list[str]:
    if count < 1:
        raise ControllerError("LINES must be at least 1")
    if not path.exists():
        return []
    with path.open(errors="replace") as source:
        return source.readlines()[-count:]


def show_logs(name: str, lines: int) -> None:
    require_known_agent(name)
    log_path = state_path("work", name, "agent.log")
    content = tail_lines(log_path, lines)
    if not content:
        print(f"no logs recorded for {name}")
        return
    print("".join(content), end="")


def iter_usage(name: str | None) -> Iterator[dict[str, Any]]:
    ensure_state()
    names = (
        [name]
        if name is not None
        else sorted(path.name for path in state_path("work").iterdir() if path.is_dir())
    )
    for agent_name in names:
        validate_name(agent_name)
        path = state_path("work", agent_name, "usage.jsonl")
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value


def usage_totals(name: str | None) -> dict[str, int]:
    records = list(iter_usage(name))
    totals = {
        "passes": len(records),
        "input_tokens": sum(int(item.get("input_tokens", 0)) for item in records),
        "cached_input_tokens": sum(int(item.get("cached_input_tokens", 0)) for item in records),
        "output_tokens": sum(int(item.get("output_tokens", 0)) for item in records),
    }
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals


def limit_reason(name: str, config: PromptConfig) -> str | None:
    totals = usage_totals(name)
    if config.max_passes is not None and totals["passes"] >= config.max_passes:
        return f"max-passes reached ({totals['passes']}/{config.max_passes})"
    if config.max_total_tokens is not None and totals["total_tokens"] >= config.max_total_tokens:
        return f"max-total-tokens reached ({totals['total_tokens']}/{config.max_total_tokens})"
    return None


def show_usage(name: str | None) -> None:
    if name is not None:
        require_known_agent(name)
    totals = usage_totals(name)
    print(json.dumps(totals, indent=2))


def version_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    try:
        parsed = tuple(int(part) for part in parts[:3])
    except ValueError as exc:
        raise ControllerError(f"cannot parse OpenAI Agents SDK version: {version}") from exc
    if len(parsed) != 3:
        raise ControllerError(f"cannot parse OpenAI Agents SDK version: {version}")
    return parsed


def load_codex_sdk() -> tuple[Any, Any]:
    try:
        version = importlib.metadata.version("openai-agents")
        parsed = version_tuple(version)
        if not MINIMUM_SDK_VERSION <= parsed < MAXIMUM_SDK_VERSION:
            raise ControllerError(
                f"openai-agents must be at least 0.22 and below 0.23; found {version}"
            )
        codex_module = import_module("agents.extensions.experimental.codex")
        Codex = codex_module.Codex
        ThreadOptions = codex_module.ThreadOptions
    except importlib.metadata.PackageNotFoundError as exc:
        raise ControllerError(
            "OpenAI Agents SDK is missing; install this repository with "
            "python -m pip install -e '.[research-team]'"
        ) from exc
    except ImportError as exc:
        raise ControllerError("the installed OpenAI Agents SDK lacks the Codex extension") from exc
    return Codex, ThreadOptions


def doctor(runner: str = "codex") -> None:
    if runner not in RUNNERS:
        raise ControllerError(f"unsupported runner: {runner}")
    if runner == "claude-code":
        ensure_state()
        try:
            summary = claude_code.doctor()
        except claude_code.ClaudeCodeError as exc:
            raise ControllerError(str(exc)) from exc
        print(f"controller ready on {sys.platform}; {summary}; state {state_root()}")
        return
    try:
        sdk_version = importlib.metadata.version("openai-agents")
    except importlib.metadata.PackageNotFoundError as exc:
        raise ControllerError(
            "OpenAI Agents SDK is missing; install this repository with "
            "python -m pip install -e '.[research-team]'"
        ) from exc
    load_codex_sdk()
    codex = shutil.which("codex")
    if codex is None:
        raise ControllerError("Codex CLI is not available on PATH")
    version = subprocess.run([codex, "--version"], check=False, text=True, capture_output=True)
    if version.returncode != 0:
        raise ControllerError("Codex CLI could not start")
    login = subprocess.run([codex, "login", "status"], check=False, text=True, capture_output=True)
    if login.returncode != 0:
        raise ControllerError("Codex CLI is not authenticated")
    ensure_state()
    for tier in sorted(TIERS):
        codex_wrapper(tier)
    print(
        f"controller ready on {sys.platform}; openai-agents {sdk_version}; "
        f"{version.stdout.strip()}; state {state_root()}"
    )


def check_repository(repository: str) -> None:
    verified = verify_github_repository(repository)
    print(f"GitHub repository accessible: {verified}")


def next_followup(name: str) -> Path | None:
    paths = sorted(state_path("followups", name).glob("followup.*.md"))
    return paths[0] if paths else None


def pass_input(name: str, config: PromptConfig, thread_id: str | None) -> tuple[str, Path | None]:
    digest_path = state_path("work", name, "prompt.sha256")
    previous_digest = digest_path.read_text().strip() if digest_path.exists() else None
    if thread_id is None or previous_digest != config.digest:
        prompt = config.text
    else:
        prompt = (
            "Continue the autonomous campaign under your existing standing mandate. "
            "Inspect the current workspace and prior thread context, then pursue the "
            "highest-value concrete next step."
        )
    followup = next_followup(name)
    if followup is not None:
        prompt += "\n\n## Orchestrator follow-up for this pass\n" + followup.read_text()
    return prompt, followup


@dataclass(frozen=True)
class PassOutcome:
    response: str
    conversation_id: str | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    cost_usd: float | None


def preflight_runner(config: PromptConfig) -> None:
    if config.runner == "claude-code":
        claude_code.find_claude()
        return
    load_codex_sdk()
    codex_wrapper(config.tier)


def conversation_id_path(config: PromptConfig, name: str) -> Path:
    filename = "session-id" if config.runner == "claude-code" else "thread-id"
    return state_path("work", name, filename)


async def run_codex_pass(config: PromptConfig, prompt: str, thread_id: str | None) -> PassOutcome:
    Codex, ThreadOptions = load_codex_sdk()
    sandbox_mode = (
        "danger-full-access" if config.permissions == "unrestricted" else "workspace-write"
    )
    options = ThreadOptions(
        model=config.model,
        sandbox_mode=sandbox_mode,
        working_directory=str(config.workspace),
        skip_git_repo_check=True,
        model_reasoning_effort=config.effort,
        network_access_enabled=config.network_access,
        web_search_mode=config.web_search,
        approval_policy="never",
    )
    codex = Codex(codex_path_override=str(codex_wrapper(config.tier)))
    thread = codex.resume_thread(thread_id, options) if thread_id else codex.start_thread(options)
    result = await thread.run(prompt)
    usage = result.usage
    return PassOutcome(
        response=result.final_response,
        conversation_id=thread.id or thread_id,
        input_tokens=int(usage.input_tokens) if usage is not None else 0,
        cached_input_tokens=int(usage.cached_input_tokens) if usage is not None else 0,
        output_tokens=int(usage.output_tokens) if usage is not None else 0,
        cost_usd=None,
    )


def run_claude_code_pass(config: PromptConfig, prompt: str, session_id: str | None) -> PassOutcome:
    try:
        result = claude_code.run_pass(
            prompt=prompt,
            fresh_prompt=config.text if session_id else prompt,
            workspace=config.workspace,
            model=config.model,
            effort=config.effort,
            permissions=config.permissions,
            web_search=config.web_search,
            session_id=session_id,
            max_pass_usd=config.max_pass_usd,
        )
    except claude_code.ClaudeCodeError as exc:
        raise ControllerError(str(exc)) from exc
    return PassOutcome(
        response=result.response,
        conversation_id=result.session_id,
        input_tokens=result.input_tokens + result.cache_creation_input_tokens,
        cached_input_tokens=result.cached_input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )


def _last_jsonl_record(path: Path) -> dict[str, Any] | None:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return None
    for line in reversed(lines):
        if line.strip():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None
    return None


def last_impact_rejection(name: str) -> str | None:
    """Return the reason the assessor's latest pass was rejected, if nothing succeeded since.

    Read from the durable failure log rather than ``last-run.json``, which every worker
    start clears; a rejection must survive a restart or the assessor repeats it.
    """
    failure = _last_jsonl_record(state_path("work", name, "failures.jsonl"))
    if failure is None:
        return None
    error = str(failure.get("error") or "")
    if IMPACT_REJECTION_PREFIX not in error:
        return None
    success = _last_jsonl_record(state_path("work", name, "usage.jsonl"))
    if success is not None and str(success.get("finished_at") or "") >= str(
        failure.get("finished_at") or ""
    ):
        return None
    return error.split(IMPACT_REJECTION_PREFIX, 1)[1]


async def run_one_pass(name: str) -> PromptConfig:
    config = parse_prompt(require_agent(name))
    id_path = conversation_id_path(config, name)
    conversation_id = id_path.read_text().strip() if id_path.exists() else None
    prompt, followup = pass_input(name, config, conversation_id)
    impact_context: ImpactContext | None = None
    if config.role == "impact-assessor":
        if config.ledger_path is None:
            raise ControllerError("impact-assessor prompt has no ledger-path")
        impact_context = build_impact_context(state_root(), config.ledger_path)
        rejection = last_impact_rejection(name)
        if rejection is not None:
            prompt += rejection_note(rejection)
        prompt += impact_prompt(impact_context)
    started_at = iso_timestamp()
    if config.runner == "claude-code":
        outcome = await asyncio.to_thread(run_claude_code_pass, config, prompt, conversation_id)
    else:
        outcome = await run_codex_pass(config, prompt, conversation_id)
    finished_at = iso_timestamp()
    resolved_conversation_id = outcome.conversation_id
    if resolved_conversation_id:
        atomic_write(id_path, resolved_conversation_id + "\n")
    run_timestamp = timestamp()
    response = outcome.response.rstrip() + "\n"
    if impact_context is not None:
        try:
            impact_batch = parse_impact_batch(response, impact_context.run_ids)
        except ValueError as exc:
            raise ControllerError(f"{IMPACT_REJECTION_PREFIX}{exc}") from exc
        record_impact_batch(
            state_root(),
            name,
            impact_context,
            impact_batch,
            assessed_at=finished_at,
        )
    atomic_write(state_path("work", name, "last-message.md"), response)
    report_path = state_path("work", name, "reports", f"{run_timestamp}.md")
    atomic_write(report_path, response)
    usage_record: dict[str, Any] = {
        "run_id": run_identifier(name, started_at),
        "agent": name,
        "role": config.role,
        "runner": config.runner,
        "started_at": started_at,
        "finished_at": finished_at,
        "thread_id": resolved_conversation_id,
        "model": config.model,
        "effort": config.effort,
        "tier": config.tier,
        "report": str(report_path),
        "input_tokens": outcome.input_tokens,
        "cached_input_tokens": outcome.cached_input_tokens,
        "output_tokens": outcome.output_tokens,
        "total_tokens": outcome.input_tokens + outcome.output_tokens,
    }
    if outcome.cost_usd is not None:
        usage_record["cost_usd"] = outcome.cost_usd
    append_json(state_path("work", name, "usage.jsonl"), usage_record)
    atomic_write(state_path("work", name, "prompt.sha256"), config.digest + "\n")
    if followup is not None:
        followup.replace(state_path("work", name, "reports", f"followup-{run_timestamp}.md"))
    write_last_run(
        name,
        {
            "status": "completed",
            "started_at": started_at,
            "finished_at": finished_at,
            "thread_id": resolved_conversation_id,
            "report": str(report_path),
        },
    )
    return config


def runtime_belongs_to_worker(name: str, nonce: str) -> bool:
    runtime = read_runtime(name)
    return bool(
        runtime and runtime.get("nonce") == nonce and int(runtime.get("pid", -1)) == os.getpid()
    )


def worker(name: str, nonce: str) -> None:
    validate_name(name)
    for _ in range(50):
        if runtime_belongs_to_worker(name, nonce):
            break
        time.sleep(0.02)
    else:
        raise ControllerError("worker runtime registration is missing")
    signal.signal(signal.SIGTERM, _handle_worker_signal)
    with hold_worker_lock(name):
        try:
            _worker_loop(name)
        except WorkerStopped as exc:
            print(f"{iso_timestamp()} {exc}; exiting", flush=True)
        finally:
            if runtime_belongs_to_worker(name, nonce):
                runtime_path(name).unlink(missing_ok=True)


def _worker_loop(name: str) -> None:
    while True:
        config = parse_prompt(require_agent(name))
        reason = limit_reason(name, config)
        if reason is not None:
            record_change(f"stopped {name}; {reason}")
            print(f"{iso_timestamp()} stopping: {reason}", flush=True)
            return
        print(
            f"{iso_timestamp()} starting pass (runner={config.runner}, "
            f"effort={config.effort}, tier={config.tier}, mode={config.mode})",
            flush=True,
        )
        pass_started_at = iso_timestamp()
        stopped = False
        atomic_write(
            current_pass_path(name),
            json.dumps(
                {
                    "agent": name,
                    "role": config.role,
                    "started_at": pass_started_at,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        try:
            config = asyncio.run(run_one_pass(name))
            print(f"{iso_timestamp()} pass completed", flush=True)
        except Exception as exc:
            stopped = isinstance(exc, WorkerStopped)
            if stopped:
                claude_code.terminate_active()
            finished_at = iso_timestamp()
            append_json(
                state_path("work", name, "failures.jsonl"),
                {
                    "timestamp": iso_timestamp(),
                    "agent": name,
                    "role": config.role,
                    "started_at": pass_started_at,
                    "finished_at": finished_at,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            print(
                f"{iso_timestamp()} pass failed: {type(exc).__name__}: {exc}",
                flush=True,
            )
            write_last_run(
                name,
                {
                    "status": "failed",
                    "started_at": pass_started_at,
                    "finished_at": finished_at,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        finally:
            current_pass_path(name).unlink(missing_ok=True)
        if stopped:
            record_change(f"stopped {name} during a pass")
            return
        if config.mode == "oneshot":
            return
        reason = limit_reason(name, config)
        if reason is not None:
            record_change(f"stopped {name}; {reason}")
            print(f"{iso_timestamp()} stopping: {reason}", flush=True)
            return
        time.sleep(config.restart_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-team")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--runner", choices=sorted(RUNNERS), default="codex")
    repository = subparsers.add_parser("check-repository")
    repository.add_argument("repository")
    subparsers.add_parser("list")
    status = subparsers.add_parser("status")
    status.add_argument("--json", action="store_true")

    new = subparsers.add_parser("new")
    new.add_argument("name")
    new.add_argument("prompt_file", type=Path)

    start = subparsers.add_parser("start")
    start.add_argument("name")

    continued = subparsers.add_parser("continue")
    continued.add_argument("name")
    continued.add_argument("note_file", type=Path)

    stop = subparsers.add_parser("stop")
    stop.add_argument("name")

    retarget = subparsers.add_parser("retarget")
    retarget.add_argument("name")
    retarget.add_argument("prompt_file", type=Path)

    retire = subparsers.add_parser("retire")
    retire.add_argument("name")

    prompt = subparsers.add_parser("prompt")
    prompt.add_argument("name")

    report = subparsers.add_parser("report")
    report.add_argument("name")

    wait = subparsers.add_parser("wait")
    wait.add_argument("name")
    wait.add_argument("--timeout", type=float, default=3600)

    history = subparsers.add_parser("history")
    history.add_argument("name")

    logs = subparsers.add_parser("logs")
    logs.add_argument("name")
    logs.add_argument("lines", type=int, nargs="?", default=200)

    usage = subparsers.add_parser("usage")
    usage.add_argument("name", nargs="?")

    hidden = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    hidden.add_argument("name")
    hidden.add_argument("--nonce", required=True)
    return parser


def dispatch(arguments: argparse.Namespace) -> None:
    command = arguments.command
    if command == "doctor":
        doctor(arguments.runner)
    elif command == "check-repository":
        check_repository(arguments.repository)
    elif command == "list":
        print("\n".join(agent_names()))
    elif command == "status":
        show_status(as_json=arguments.json)
    elif command == "new":
        new_agent(arguments.name, arguments.prompt_file)
    elif command == "start":
        start_agent(arguments.name)
    elif command == "continue":
        continue_agent(arguments.name, arguments.note_file)
    elif command == "stop":
        stop_agent(arguments.name)
    elif command == "retarget":
        retarget_agent(arguments.name, arguments.prompt_file)
    elif command == "retire":
        retire_agent(arguments.name)
    elif command == "prompt":
        show_prompt(arguments.name)
    elif command == "report":
        show_report(arguments.name)
    elif command == "wait":
        wait_for_agent(arguments.name, arguments.timeout)
    elif command == "history":
        show_history(arguments.name)
    elif command == "logs":
        show_logs(arguments.name, arguments.lines)
    elif command == "usage":
        show_usage(arguments.name)
    elif command == "_worker":
        worker(arguments.name, arguments.nonce)
    else:
        raise ControllerError(f"unsupported command: {command}")


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        dispatch(build_parser().parse_args(arguments))
    except ControllerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
