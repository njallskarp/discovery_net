#!/usr/bin/env bash
# Codex runner -- CANARY STUB.  Read ../CODEX-CANARY.md before editing.
#   $1 rendered prompt file   $2 repo root   $3 working directory
set -euo pipefail
PROMPT_FILE="$1"; REPO_ROOT="$2"; RUN_DIR="$3"

cd "$RUN_DIR"

# TODO(canary-1) sandbox level.  read-only is the default and is too tight --
#   the agent has to append to its worklog, run the submit CLI against loopback,
#   and commit in its notes clone.  danger-full-access is more than it needs.
#   Start at workspace-write, record exactly what fails, and report the minimum
#   that works.  This box holds a contributor signing key, so tighter is better.
CODEX_SANDBOX="${CODEX_SANDBOX:-workspace-write}"

# TODO(canary-2) working directory.  codex exec has no documented flag for it;
#   this cd is the substitute.  Confirm the agent resolves the skill paths named
#   in the prompt from here.

# TODO(canary-3) skills.  Codex reads .agents/skills/ directly, so no symlink
#   step should be needed -- confirm the three skills load and that the relative
#   cross-reference ../discovery-net/SKILL.md resolves.

exec codex exec - \
  --sandbox "$CODEX_SANDBOX" \
  --json \
  < "$PROMPT_FILE"

# TODO(canary-4) usage.  --json emits JSON Lines; usage arrives on the
#   turn.completed event as
#     {"type":"turn.completed","usage":{"input_tokens":N,"cached_input_tokens":N,"output_tokens":N}}
#   Tokens only -- no cost field.  The wrapper prices them from agent-sessions/budget.toml.
#
# TODO(canary-5) graceful bound.  No documented equivalent to Claude Code's
#   --max-turns, so RuntimeMaxSec is currently the only stop.  Find out whether a
#   turn or token cap exists; being killed mid-turn loses that turn's work.
