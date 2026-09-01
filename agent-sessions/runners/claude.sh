#!/usr/bin/env bash
# Claude Code runner.  Contract: ../README.md ("Run record").
#   $1 rendered prompt file   $2 repo root   $3 working directory
set -euo pipefail
PROMPT_FILE="$1"; REPO_ROOT="$2"; RUN_DIR="$3"

# --bare skips auto-discovery of hooks, custom commands, subagents, plugins,
# MCP servers, auto memory, CLAUDE.md -- AND skills.  --add-dir is the
# documented exception: bare mode still loads skills from <dir>/.claude/skills/.
# The pair is what makes an unattended run both reproducible and skill-aware.
#
# Why bare matters here: without it, a -p session runs the hooks in the repo's
# .claude/settings.json and connects the servers in its .mcp.json, with no trust
# dialog and no approval prompt.  This repo has several contributors; an
# unattended agent holding a signing key should not execute whatever lands in it.
#
# Cost of bare: it never reads OAuth credentials or the keychain, so it does NOT
# use a Claude subscription.  ANTHROPIC_API_KEY must be set and the run bills as
# API usage.  See ../README.md and the plan's budget section.
: "${ANTHROPIC_API_KEY:?--bare does not use subscription login; set ANTHROPIC_API_KEY}"

cd "$RUN_DIR"

# --permission-mode dontAsk denies anything outside the allow rules and the
# read-only command set -- the locked-down posture for unattended runs.
# --allowedTools uses permission rule syntax; the space before * matters.
exec claude --bare -p "$(cat "$PROMPT_FILE")" \
  --add-dir "$REPO_ROOT" \
  --permission-mode dontAsk \
  --allowedTools "Read,Edit,Bash(curl http://127.0.0.1:*),Bash(discovery-net *),Bash(git *)" \
  --max-turns "${DN_MAX_TURNS:-60}" \
  --output-format json
