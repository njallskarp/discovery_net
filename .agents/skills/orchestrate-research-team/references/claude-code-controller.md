# Claude Code runner for the Python controller

Use this adapter when the fleet should run on Claude Code instead of Codex. It is the
same controller described in [the Python controller guide](python-controller.md): the
state layout, commands, prompt versioning, follow-ups, limits, impact assessor, and
dashboard are unchanged. Only the process that performs each pass differs.

Select it per agent with `runner: claude-code` in the prompt metadata. Agents without a
`runner:` line keep using Codex, so one campaign may mix both.

## Prepare once

Requirements on the host that runs the controller:

- macOS or Linux with Python 3.12 or newer and this repository installed
  (`python -m pip install -e .` or `uv sync`; the `research-team` extra is not needed).
- The Claude Code CLI, signed in. Passes run under the operator's existing login, so a
  claude.ai subscription or an API-key login both work; nothing here reads or stores a
  key. Put `claude` on `PATH` or point `DISCOVERY_RESEARCH_TEAM_CLAUDE` at the binary.

```bash
research-team doctor --runner claude-code
```

The doctor verifies the binary starts and reports its version, the login method, and the
subscription type. Run it in the same environment and state root that will run agents.

## Prompt contract

Everything in the Codex prompt contract applies, with these runner-specific rules:

```text
role: researcher
mode: continuous
runner: claude-code
model: claude-fable-5-1
effort: xhigh
tier: default
restart-seconds: 1800
permissions: workspace-write
network-access: true
web-search: live
workspace: /absolute/path/to/researcher-1
github-repository: https://github.com/OWNER/REPOSITORY
contract-confirmed: true
max-passes: 0
max-total-tokens: 0
max-pass-usd: 60
```

- `effort` is one of `low`, `medium`, `high`, `xhigh`, or `max`; `minimal` is rejected.
- `tier` must be `default`. Claude Code has no service tiers.
- `web-search` is `disabled` or `live`. `disabled` removes the `WebSearch` and `WebFetch`
  tools; there is no cached mode.
- `permissions: workspace-write` runs with Claude Code's `acceptEdits` permission mode:
  the file tools stay inside the workspace, while the shell and web tools run without a
  prompt because a headless pass has nobody to answer one. This is a policy boundary,
  not a sandbox; the shell can reach anything the operator's account can. Keep every
  workspace dedicated and keep credentials out of it. `unrestricted` uses
  `bypassPermissions`.
- `model` is optional and, when set, is passed to `--model`; use an exact model ID such
  as `claude-fable-5-1` or `claude-opus-5`. Omit it to use the CLI's own default.
- `max-pass-usd` is an optional per-pass ceiling passed to `--max-budget-usd`. Claude
  Code stops the pass when its own cost estimate reaches it. Under a subscription the
  estimate is not a bill, but it still stops a runaway pass. Set `0` or omit it for
  no per-pass ceiling. It is rejected on Codex agents.

The controller strips the `CLAUDE*` variables a parent Claude Code session exports, except
`CLAUDE_CONFIG_DIR`, so an orchestrator running inside Claude Code can create agents
without the workers attaching to its session.

## Sessions

Each agent keeps one Claude Code session per workspace. The first pass sends the complete
mandate with a fresh `--session-id`; later passes `--resume` it with a short continuation
message, as the Codex runner does with its thread. The session ID is recorded in
`work/NAME/session-id`. If Claude Code reports that the stored session no longer exists,
the controller starts a new session with the full mandate and records the new ID.

Passes run with `--setting-sources project` and `--strict-mcp-config`: the agent sees
only settings and skills under its workspace, and no MCP server from the operator's
configuration. Session transcripts are stored by Claude Code under the operator's own
Claude configuration directory, keyed by workspace.

## Workspaces and skills

Claude Code discovers skills from `.claude/skills/` in the working directory. Prepare
each workspace with the bundled script, which clones the authorized repository into
`notes/`, links this repository's `.agents/skills` tree as `skills/` and into
`.claude/skills/`, and creates `scratch/`:

```bash
.agents/skills/orchestrate-research-team/scripts/prepare-workspace \
  /absolute/path/to/researcher-1 git@github.com:OWNER/REPOSITORY.git ~/.ssh/deploy-key
```

Give the deploy key when the publication repository should be pushed with a dedicated
key rather than the operator's default identity; the clone records it in
`core.sshCommand`. Prompts should name skills by path (`skills/math-research/SKILL.md`)
as well as by their `$name`, and give the absolute paths of the Discovery Net CLI, the
node's ledger, and the agent's signing key under the controller's `keys/` directory.

## Usage records

Each pass appends the usual usage record plus `runner: claude-code` and `cost_usd`, the
CLI's own cost estimate for that pass. `input_tokens` includes cache-creation tokens and
`cached_input_tokens` counts cache reads, so `max-total-tokens` and the dashboard treat
both runners alike. The `usage` command reports token totals; sum `cost_usd` from
`work/NAME/usage.jsonl` for an estimated spend.

## Dashboard

The Docker dashboard is runner-agnostic. Start it exactly as the Codex guide describes;
it reads the same state root and needs no Claude Code access.
