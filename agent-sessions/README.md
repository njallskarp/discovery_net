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
| Prompt templates | `agents/prompts/` | role: research or review |
| Bindings | `agents/bindings/*.env` | **operator and node** |
| Runners | `agents/runners/*.sh` | runner: claude or codex |
| Budget | `agents/budget.toml` | operator |

## Rendering a prompt

A prompt template is a role (`prompts/research.md`, `prompts/review.md`) plus a
binding. The wrapper substitutes only the `DN_*` names, so a `$` inside a code
fence in the prompt survives:

```bash
set -a; . "agents/bindings/$BINDING.env"; set +a
envsubst "$(printf '${%s} ' $(grep -o 'DN_[A-Z_]*' agents/prompts/$DN_ROLE.md | sort -u))" \
  < "agents/prompts/$DN_ROLE.md" > "$RUN_DIR/prompt.md"
```

Two researchers on the same box differ only by their binding file. Nothing about
a node, a path, or an operator appears in a template.

## Onboarding a new operator

An operator running their own nodes does not edit the wrapper, the units, or
the prompts. They write one binding per agent and run the conformance check:

1. Copy `bindings/TEMPLATE.env` to `bindings/<your-node>.env`.
2. Fill in the RPC URL, key path, worklog path, and — the part that genuinely
   differs between layouts — `DN_GRAPHQL_CMD` and `DN_SUBMIT_CMD`.
3. Run the conformance check in `conformance/smoke.md`. It is read-only and
   submits nothing.
4. If it passes, enable the timer for that agent.

`DN_GRAPHQL_CMD` is the field that catches people out. How you read a ledger
depends on who owns the bind mount: a root-owned ledger needs a `docker exec`
into the node's application container, a user-owned one can be read directly
with the CLI. `bindings/node-abu-1.env` shows the first form and the template
documents both. The prompt template never names either — it calls the binding.

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
