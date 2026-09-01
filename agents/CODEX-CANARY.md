# Codex runner — canary handoff

Everything except the Codex runner is either built or specified. This is what
is left, why it needs a person with Codex in front of them, and how to know
when it is done.

## What is already settled

- **Skills need no porting.** Codex reads `.agents/skills/` directly, which is
  where the three skills already live. Claude Code reads `.claude/skills/` and
  follows symlinks, so the same files serve both. Nothing to duplicate.
- **The prompts are runner-neutral.** They name a skill by *path*, not by
  Codex's `$math-research` token, so the same template renders for both.
- **Node layout is not baked in.** Everything operator-specific is in a binding
  file — see `bindings/TEMPLATE.env`. You should not need to edit the wrapper,
  the units, or the prompts.
- **The contract is fixed.** `README.md` → "Run record" defines the one JSON
  object per firing that the wrapper writes. Make `codex.sh` produce enough to
  fill it and you are done.

## What is open, and why

`runners/codex.sh` is a stub with five numbered TODOs. Two of them need
judgment rather than lookup:

**canary-1, the sandbox level.** `read-only` is the Codex default and is too
tight — the agent has to append to its worklog, run `discovery-net submit`
against loopback, and commit in its notes clone. `danger-full-access` is more
than it needs. Start at `workspace-write`, record exactly what fails, and
report back the minimum that works. This matters more than it looks: the box
holds a contributor signing key, and the whole fleet inherits whatever level
you land on.

**canary-5, the graceful bound.** Claude Code has `--max-turns`, so a run
normally stops itself before systemd's `RuntimeMaxSec` kills it. No equivalent
is documented for `codex exec`. If none exists, Codex firings will more often
be killed mid-turn and lose that turn's work, which changes how aggressively
the prompt should checkpoint into the worklog.

The other three are mechanical: confirm the working directory substitute
(canary-2), confirm the three skills load and their relative cross-references
resolve (canary-3), and map the `turn.completed` usage event into the run
record (canary-4).

## Usage reporting — the one real asymmetry

Claude Code's `--output-format json` reports `total_cost_usd`. Codex's `--json`
reports token counts only:

```json
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122}}
```

So Codex runs get priced by the wrapper from the table in `agents/budget.toml`.
Please confirm the event shape above against the version you are running and
say if it has changed — a wrong field name means Codex firings silently record
zero spend, and a shared monthly cap then only governs half the fleet.

## Done looks like

1. `agents/conformance/smoke.md` passes under Codex with your own binding, and
   its output matches what the Claude Code runner produces for the same node —
   same skills listed, same heights, same worklog line shape.
2. `codex.sh` emits enough for a complete run record, including token counts.
3. The five TODOs are answered in a PR description or a note back, especially
   the minimum working sandbox level.

Do not run a research firing until the smoke check passes. A misconfigured
runner that submits is worse than one that does not run: contributions land on
a shared chain under a signer key, and other operators' reviewers will spend
real effort refereeing them.
