# Agent orchestration

Unattended Discovery Net agents: a systemd timer fires a wrapper, the wrapper
renders a prompt from a template plus a binding, hands it to a runner, and
records what it cost.

Nothing here is specific to one operator. Everything that *is* specific to an
operator lives in a binding file under `bindings/`.

## The five pieces

| Piece | Where | Varies by |
|---|---|---|
| Skills | `.agents/skills/` (Codex) + `.claude/skills/` symlinks (Claude Code) | nobody — one source of truth |
| Prompt templates | `agent-sessions/prompts/` | role: research or review |
| Setup | `agent-setup/` | nobody — it writes the two below |
| Node bindings | `agent-sessions/bindings/nodes/*.env` | **the machine and its node** |
| Agent bindings | `agent-sessions/bindings/agents/*.env` | **the agent: role, runner, key** |
| Runners | `agent-sessions/runners/*.sh` | runner: claude or codex |
| Budget and cadence | `agent-sessions/budget.toml` | operator |
| Wrapper | `agent-sessions/run.sh` + `lib/dnagent.py` | nobody |
| Scheduling | `agent-sessions/systemd/` (Linux) or any cron/loop | host |

## Skills are one tree, reachable two ways

Codex scans `.agents/skills/`. Claude Code reads `.claude/skills/`, follows
symlinks, and loads each target once. `.claude/skills/` therefore holds three
symlinks into `.agents/skills/` and no content of its own:

```
.claude/skills/discovery-net -> ../../.agents/skills/discovery-net
.claude/skills/math-research -> ../../.agents/skills/math-research
.claude/skills/math-review   -> ../../.agents/skills/math-review
```

Git stores symlinks, so a fresh clone gets them; there is nothing to recreate.
Link all three, not just the two role skills — `math-research` and `math-review`
both open by referencing `../discovery-net/SKILL.md`, and that relative path has
to resolve from whichever tree the runner is reading.

The bodies are 559 lines and not one of them is runner-specific. The only
runner-specific files are the two `agents/openai.yaml` sidecars, which Claude Code
ignores because they are files rather than frontmatter. If either runner ever
needs a metadata key the other rejects, generate both trees from one source
rather than forking the bodies — see `CODEX-CANARY.md`, canary-6.

## Rendering a prompt

A prompt template is a role (`prompts/research.md`, `prompts/review.md`) plus a
binding. The wrapper substitutes only the `DN_*` names, so a `$` inside a code
fence in the prompt survives:

```bash
set -a; . "agent-sessions/bindings/$BINDING.env"; set +a
envsubst "$(printf '${%s} ' $(grep -o 'DN_[A-Z_]*' agent-sessions/prompts/$DN_ROLE.md | sort -u))" \
  < "agent-sessions/prompts/$DN_ROLE.md" > "$RUN_DIR/prompt.md"
```

Two researchers on the same box differ only by their binding file. Nothing about
a node, a path, or an operator appears in a template.

## Running one firing

```bash
agent-sessions/run.sh <agent> [--dry-run]
```

`run.sh` is the whole thing: it resolves the binding, runs the gates, renders the
prompt, invokes the runner under a deadline, and writes the run record. systemd
is only a way to call it on a schedule — the units in `systemd/` fire it at the
shortest cadence any mode uses and let the wrapper decide whether a given tick is
a firing. Nothing about it needs systemd, which is what makes it testable on a
laptop.

`--dry-run` runs every gate and renders the prompt but never invokes a runner or
spends anything. It is the fastest way to check a new binding.

The gates, in order, each exiting cleanly with a recorded reason:

| Gate | Skips the firing when |
|---|---|
| cadence | the current mode's interval has not elapsed since the last run |
| budget | month-to-date spend has reached `monthly_cap_usd` |
| preflight | node unreachable, wrong chain, catching up, or indexer lag over `max_indexer_lag` |
| new work | review role only: `indexedHeight` has not moved since the last firing |

All four are bash and JSON. A skipped tick costs nothing, which is the only
reason a reviewer can afford to tick every fifteen minutes.

`agentctl status` prints the table; `agentctl watch` refreshes it; `agentctl runs`
tails the ledger.

## Testing locally before any of this touches a VM

```bash
./localnet/localnet.sh bootstrap                 # a one-validator chain on this machine
openssl genpkey -algorithm ed25519 -out contributor.pem && chmod 600 contributor.pem

agent-setup/init-node.sh                         # point it at the localnet's RPC
agent-setup/init-agent.sh                        # bind an agent to it

agent-sessions/run.sh <agent> --dry-run          # gates + render, spends nothing
agent-sessions/conformance/run-smoke.sh <agent>  # read-only, proves the runner works
agent-sessions/run.sh <agent>                    # a real firing
agent-sessions/agentctl status
```

A localnet is the *other* ledger read path: the bind mount is owned by whoever
started the stack, so `init-node.sh` should find the direct CLI read and never
fall back to a container exec. Getting a `docker exec` binding out of a localnet
means something is off.

macOS has no `flock`, no GNU `timeout` and no `envsubst`, so none are used: the
deadline is a watchdog subshell that sends SIGINT before SIGKILL, and rendering
is python. The only hard requirements are bash, curl and python3.

## Why there is no lock

An earlier draft had the wrapper `flock` a shared `claims.md`. Two problems: the
lock would have to be held for the whole firing, which serialises agents that
should run concurrently, and `flock` does not exist on macOS where this gets
tested.

Removing the shared mutable file is better than guarding it. `DN_CLAIMS_DIR` is a
directory of per-agent files; an agent appends only to its own and reads all of
them. Nothing to lock, no lost appends, and it works unchanged across operators
and machines. The notes clone is per-agent for the same reason, so concurrent
`git pull --rebase` in one working tree never arises.

## Onboarding a new operator

Two scripts, both interactive, both verifying as they go. Nobody edits a file by
hand and nobody edits the wrapper, the units, or the prompts.

```bash
agent-setup/init-node.sh     # once per node
agent-setup/init-agent.sh    # once per agent on that node
```

`init-node.sh` describes a node. It curls the RPC endpoint and reads back the
moniker, chain, height and voting power before accepting the URL; then it *probes*
the ledger read path rather than asking you to know it, trying a direct CLI read
first and falling back to a container exec, testing each and keeping whichever
returns an `indexedHeight`. If neither works it refuses to write a binding at all,
because one that cannot read the ledger would abort every firing at preflight.

That probe is the point of the script. `DN_GRAPHQL_CMD` is the field that differs
most between operators — a root-owned bind mount needs `docker exec`, a
user-owned one does not — and it is the field most likely to be wrong.

`init-agent.sh` binds an agent to a node already described: role, runner, key
location, working directories. It records where the signing key lives and checks
its permissions; it never reads or copies one. It finishes by running a dry
firing, so setup either proves itself or tells you which gate stopped it.

The split matters when an operator runs several agents against one node. Node
facts are written once and reused, so they cannot drift between agents — the same
failure the prompt templates had before they became templates. And because a
contributor key belongs to an agent rather than to a node, the node file carries
`DN_SUBMIT_BASE` with no key in it and `run.sh` appends `--private-key` at run
time. The key path then exists in exactly one place instead of two that can
disagree.

Generated bindings are gitignored: they hold absolute paths and the location of a
signing key, so they describe one machine. The committed `*.env.example` files
show the shapes — two node shapes, direct read and container read, and two agent
shapes, researcher and reviewer.

## Run record

Every firing appends one JSON object to `runs.jsonl`. Both runners must
produce enough for the wrapper to fill it:

```json
{"agent":"researcher-1","runner":"claude","node":"node-abu-1",
 "run_id":"...","started_at":"...","ended_at":"...",
 "exit":"completed|killed|preflight-abort|budget-paused|no-new-work",
 "tokens":{"in":0,"cached_in":0,"out":0},"cost_usd":0.0,
 "indexed_height":0,"refs":[]}
```

Claude Code reports `total_cost_usd` directly. Codex reports token counts only,
so the wrapper prices them from `budget.toml`. Whichever runner produced a row,
the `cost_usd` field must be populated, or the monthly cap only governs half
the fleet.

## Runner status

- `runners/claude.sh` — written against the documented flags; unverified on
  real hardware until phase 2.
- `runners/codex.sh` — **stub.** See `CODEX-CANARY.md`.
