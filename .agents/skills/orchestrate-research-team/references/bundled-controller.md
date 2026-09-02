# Bundled Linux controller

Use this adapter when the human has not supplied another fleet interface and
the selected host has Linux, systemd, and an authenticated Codex CLI. It turns
the repository skill into a complete host implementation rather than requiring
an undocumented VM script.

## Install once

From the repository root, inspect the script, verify `codex` is authenticated
for the intended operator account, and obtain approval for the privileged
installation. Then run:

```bash
sudo .agents/skills/orchestrate-research-team/scripts/research-team install OPERATOR
```

Installation copies a root-owned controller and runner, installs a constrained
systemd template, creates `/opt/discovery-research-team`, and grants OPERATOR
passwordless access only to the installed controller. It does not create an
agent. Run `sudo discovery-research-team doctor` afterward.

Do not install this adapter on a non-systemd host. Use a host-supplied control
interface or native task controls instead.

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
permissions: unrestricted
```

Allowed roles are `researcher`, `reviewer`, `principal`, and `orchestrator`.
Allowed modes are `continuous` and `oneshot`. Allowed tiers are `default`,
`flex`, and `priority`. Allowed permissions are `workspace-write` and
`unrestricted`. Use `unrestricted` only when the human has authorized the agent
to perform unattended external writes or other work that needs it. An optional
`model:` line pins a model. Omit it to use the authenticated Codex default.

For a continuous agent, `restart-seconds` is the delay after a successful pass.
For a one-shot principal, set it to `0`. The controller rejects missing or
invalid metadata rather than silently choosing different runtime settings.

The rest of the file is the visible agent mandate. Include the selected skill
composition, authorized repositories and services, scratch paths, publication
boundaries, and stopping condition. Set a broad mandate rather than a detailed
research recipe.

## Commands

The installed command is `sudo discovery-research-team`:

```text
doctor                         verify the installation
list                           list configured agents and roles
status                         show configured agents and service state
new NAME PROMPT_FILE           create an agent; continuous agents start now
start NAME                     start a configured or one-shot agent
continue NAME NOTE_FILE        append a one-pass follow-up on the next pass
stop NAME                      stop the run and its complete process group
retarget NAME PROMPT_FILE      archive and replace the operative prompt
retire NAME                    stop and disable an agent, preserving its state
prompt NAME                    print the complete operative prompt
history NAME                   list archived prompt versions
logs NAME [SINCE]              read logs; SINCE defaults to "3 hours ago"
```

`continue` queues one short instruction for the next pass without changing the
standing mandate. `stop` is reversible and retains the active prompt. `retire`
removes the agent from the active roster by moving its prompt to
`prompts.disabled`; its key, workspace, reports, and prompt remain available.
Retargeting takes effect at the next pass and never interrupts a live pass
automatically.

The operative prompts are readable under
`/opt/discovery-research-team/prompts`, archived versions are under
`/opt/discovery-research-team/prompts.history`, and `prompt NAME` prints the
exact text. Run reports are archived under each agent's work directory.

## Reconciliation

On every wake, use `status` before changing anything. Create only enough agents
to meet the standing count. Start the one-shot principal for a fresh assessment
and wait for it to finish. Apply an approved principal recommendation with the
smallest suitable operation: leave alone, retarget on the next pass, stop
temporarily, or retire and replace. Never use `stop` merely to make a prompt
change take effect sooner.
