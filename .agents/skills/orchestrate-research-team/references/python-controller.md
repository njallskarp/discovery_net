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
python .agents/skills/orchestrate-research-team/scripts/research-team doctor
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
```

Allowed roles are `researcher`, `reviewer`, `principal`, and `orchestrator`.
Allowed modes are `continuous` and `oneshot`. Allowed reasoning efforts are
`minimal`, `low`, `medium`, `high`, and `xhigh`. The controller accepts only
`tier: default`; this prevents the fleet contract from silently selecting Flex
or Priority. Allowed permissions are `workspace-write` and `unrestricted`.
`network-access` is `true` or `false`, and `web-search` is `disabled`, `cached`,
or `live`. An optional `model:` line pins a model. Omit it to use the
authenticated Codex default.

For a continuous agent, `restart-seconds` is the delay after each completed or
failed pass and must be at least 60. For a one-shot principal, set it to `0`.
The controller rejects missing or invalid metadata rather than choosing hidden
runtime settings.

The rest of the file is the visible agent mandate. Include the selected skill
composition, authorized repositories and services, scratch paths, publication
boundaries, and stopping condition. Set a broad mandate rather than a detailed
research recipe.

## Commands

Run the controller with the same Python environment used during setup:

```text
doctor                         verify Python, SDK, Codex, and state access
list                           list configured agent names
status                         show roles, process state, and prompt paths
new NAME PROMPT_FILE           create an agent; continuous agents start now
start NAME                     start a configured or one-shot agent
continue NAME NOTE_FILE        append a one-pass follow-up on the next pass
stop NAME                      stop the agent process and active Codex turn
retarget NAME PROMPT_FILE      archive and replace the operative prompt
retire NAME                    stop an agent and preserve all of its state
prompt NAME                    print the complete operative prompt
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

The controller keeps each Codex thread ID and resumes it across passes and
process restarts. It sends the complete standing mandate only on the first pass
and whenever that mandate changes. Ordinary passes receive a short continuation
message, reducing repeated input tokens. Reports and per-pass token usage are
recorded under the agent workspace.

## Reconciliation

On every wake, use `status` before changing anything. Create only enough agents
to meet the standing count. Start the one-shot principal for a fresh assessment
and wait for it to finish. Apply an approved principal recommendation with the
smallest suitable operation: leave alone, retarget on the next pass, stop
temporarily, or retire and replace. Never use `stop` merely to make a prompt
change take effect sooner.
