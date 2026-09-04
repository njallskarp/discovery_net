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
  file — see the `*.env.example` files under `bindings/`. You should not need
  to edit the wrapper, the units, or the prompts.
- **The contract is fixed.** `README.md` → "Run record" defines the one JSON
  object per firing that the wrapper writes. Make `codex.sh` produce enough to
  fill it and you are done.

## What is open, and why

`runners/codex.sh` is a stub with five numbered TODOs, a sixth question about
skills that does not live in the script, and a seventh about model selection
that came out of the first real Claude firing. Three need judgment rather than
lookup:

**canary-1, the sandbox level.** `read-only` is the Codex default and is too
tight — the agent has to append to its worklog, run `tools/dn-submit` (which
talks to loopback RPC) and `tools/dn-notes` (git in its notes clone), and run
`tools/dn-compute` (docker). Bare `git` and the bare CLI are not on the Claude
runner's list any more and should not be on Codex's either. `danger-full-access` is more
than it needs. Start at `workspace-write`, record exactly what fails, and
report back the minimum that works. This matters more than it looks: the box
holds a contributor signing key, and the whole fleet inherits whatever level
you land on.

**canary-5, the graceful bound.** Claude Code has `--max-turns`, so a run
normally stops itself before systemd's `RuntimeMaxSec` kills it. No equivalent
is documented for `codex exec`. If none exists, Codex firings will more often
be killed mid-turn and lose that turn's work, which changes how aggressively
the prompt should checkpoint into the worklog.

**canary-6, unknown frontmatter keys.** Claude Code tolerates unknown SKILL.md
frontmatter keys and puts its behaviour knobs there (`disable-model-invocation`,
`allowed-tools`, `context: fork`). Codex puts the equivalent in the
`agents/openai.yaml` sidecar, and OpenAI's skill-creator guide says of
frontmatter: *"Do not include any other fields."* What is **not** documented is
whether Codex *rejects* an unknown key or simply ignores it.

Settle it in about a minute: add a junk key to a scratch skill's frontmatter and
see whether the skill still loads. The answer decides how the three skills are
maintained long-term. If unknown keys are ignored, one symlinked tree keeps
working even after Claude Code needs a frontmatter knob. If they are rejected,
the bodies have to be generated from a common source with per-runner metadata
before that day arrives, because the alternative is two hand-maintained copies
of the same mathematical policy drifting apart unnoticed.

**canary-7, model selection.** `runners/claude.sh` now takes an optional
`DN_MODEL` from the agent binding and passes it as `--model`; unset means the
runner's own default. Codex needs the same lever, and the equivalent flag on
`codex exec` should be wired to the same `DN_MODEL` key so one binding field
means the same thing for both runners. Do not invent a second key name.

This is not a tidiness question. The first real Claude firing cost **$0.13 for
41 seconds** of a conformance check that did almost nothing, because the runner
pinned no model and got the strongest one by default. Whatever Codex's default
is, a fleet on a shared monthly cap cannot have half of it silently running at
the top of the price list. Report what `codex exec` defaults to and what the
flag is called.

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

So Codex runs get priced by the wrapper from the table in `agent-sessions/budget.toml`.
Please confirm the event shape above against the version you are running and
say if it has changed — a wrong field name means Codex firings silently record
zero spend, and a shared monthly cap then only governs half the fleet.

The pricing table is per-runner, not per-model, so it silently assumes every
Codex firing uses one model. If canary-7 lands a `DN_MODEL` that agents actually
vary, say so: the table needs a model dimension before that happens, or the
ledger prices a cheap firing at the expensive rate and the cap misfires in the
direction that stops work.

## Done looks like

1. `agent-sessions/conformance/smoke.md` passes under Codex with your own binding, and
   its output matches what the Claude Code runner produces for the same node —
   same skills listed, same heights, same worklog line shape.
2. `codex.sh` emits enough for a complete run record, including token counts.
3. The seven open questions are answered in a PR description or a note back,
   especially the minimum working sandbox level and whether Codex rejects
   unknown frontmatter keys.

Do not run a research firing until the smoke check passes. A misconfigured
runner that submits is worse than one that does not run: contributions land on
a shared chain under a signer key, and other operators' reviewers will spend
real effort refereeing them.
