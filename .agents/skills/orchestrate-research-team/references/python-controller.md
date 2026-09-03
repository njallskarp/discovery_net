# Python Codex controller

Use this adapter when the human has not supplied another fleet interface and
the selected host is macOS or Linux with Python 3.12 or newer and an
authenticated Codex CLI. The controller uses the Codex extension in the OpenAI
Agents SDK. It does not install a system service and does not require root.

## Prepare once

From the repository root, install the optional dependency into the Python
environment that will run the controller:

```bash
python -m pip install -e '.[research-team]'
research-team doctor
```

Dependency installation changes the Python environment and may require network
access, so obtain human authorization when it has not already been granted.
The controller uses the existing Codex CLI login by default. It does not require
an API key when the CLI is already authenticated.

State defaults to `~/.discovery-research-team`. Override it with
`DISCOVERY_RESEARCH_TEAM_ROOT` when the brief names another location. Always use
the same Python environment and state root for later commands.

## Prompt contract

The orchestrator writes each complete prompt to its own scratch directory and
passes that file to `new` or `retarget`. Begin every prompt with explicit
runtime metadata:

```text
role: researcher
mode: continuous
effort: xhigh
tier: default
restart-seconds: 1800
permissions: workspace-write
network-access: true
web-search: live
workspace: /absolute/path/to/researcher-1-worktree
contract-confirmed: true
max-passes: 0
max-total-tokens: 0
```

Allowed roles are `researcher`, `reviewer`, `principal`, and `orchestrator`.
Allowed modes are `continuous` and `oneshot`. Allowed reasoning efforts are
`minimal`, `low`, `medium`, `high`, and `xhigh`. Allowed tiers are `default`
and `flex`; record the human's choice explicitly so the fleet does not inherit
an ambient service-tier setting. Allowed permissions are `workspace-write` and
`unrestricted`.
`network-access` is `true` or `false`, and `web-search` is `disabled`, `cached`,
or `live`. `workspace` must be an existing absolute directory dedicated to
this agent. Use a separate checkout or Git worktree when the agent needs a
repository; this also makes that checkout's `.agents/skills` available to
Codex. The controller rejects sharing a workspace between active agents.
`contract-confirmed` must be `true` and records that the orchestrator crossed
the human confirmation gate. An optional `model:` line pins a model. Omit it to
use the authenticated Codex default.

`max-passes` and `max-total-tokens` are controller-enforced limits checked
between passes. Set either value to `0` for no controller limit. A token limit
can be exceeded by the final pass because usage is known only after that pass
finishes; use a conservative value when it is a hard spending boundary.

For a continuous agent, `restart-seconds` is the delay after each completed or
failed pass and must be at least 60. For a one-shot principal, set it to `0`.
The controller rejects missing or invalid metadata rather than choosing hidden
runtime settings.

Prepare every workspace before creating its prompt. Keep controller state and
reports under `DISCOVERY_RESEARCH_TEAM_ROOT`; `workspace` is only the directory
in which Codex performs the research. The rest of the file is the visible agent
mandate. Start it with a compact `Human-approved contract` section containing
the applicable roster, research scope, host and workspace, runtime choices,
cadences, resource limits, and stop condition. Include either the exact
authorized repository and push boundaries or the explicit statement
`publication: local-only`. Also include the selected skill composition,
authorized services, and scratch paths. Set a broad mandate rather than a
detailed research recipe. Do not create this prompt until the human has
confirmed the complete contract described in `SKILL.md`.

## Commands

Run the controller with the same Python environment used during setup:

```text
doctor                         verify Python, SDK, Codex, and state access
list                           list configured agent names
status [--json]                show roles, process state, and workspaces
new NAME PROMPT_FILE           create an agent; continuous agents start now
start NAME                     start a configured or one-shot agent
continue NAME NOTE_FILE        append a one-pass follow-up on the next pass
stop NAME                      stop the agent process and active Codex turn
retarget NAME PROMPT_FILE      archive and replace the operative prompt
retire NAME                    stop an agent and preserve all of its state
prompt NAME                    print the complete operative prompt
report NAME                    print the most recent completed response
wait NAME [--timeout SECONDS]  wait for a one-shot agent; default 3600 seconds
history NAME                   list archived prompt versions
logs NAME [LINES]              show recent logs; default 200 lines
usage [NAME]                   show measured token totals
```

`continue` queues one short instruction without changing the standing mandate.
`stop` is reversible. `retire` removes the agent from the active roster while
retaining its prompt history, key, workspace, reports, logs, Codex thread ID,
and usage data. Retargeting takes effect on the next pass and does not interrupt
a live pass automatically.

Each agent is a detached Python worker, so closing the launching terminal does
not stop it. The same implementation runs on macOS and Linux. It does not
register itself to start after a machine reboot; a later orchestrator wake must
reconcile and restart inactive agents.

The implementation is also installed as
`discovery_net.research_team.controller`, so another Python program may import
its parsing, status, usage, and lifecycle functions instead of scraping the
repository-local script. The `research-team` command and skill script are thin
entry points over that module.

The controller keeps each Codex thread ID and resumes it across passes and
process restarts. It sends the complete standing mandate only on the first pass
and whenever that mandate changes. Ordinary passes receive a short continuation
message, reducing repeated input tokens. Reports and per-pass token usage are
recorded under the agent workspace.

## Reconciliation

On every wake, use `status --json` before changing anything. Create only enough
agents to meet the standing count. Start the one-shot principal for a fresh
assessment, use `wait`, and read it with `report`. Apply an approved principal
recommendation with the smallest suitable operation: leave alone, retarget on
the next pass, stop temporarily, or retire and replace. Never use `stop` merely
to make a prompt change take effect sooner.
