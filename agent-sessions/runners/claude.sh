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

# Skills do NOT auto-load under --bare, and --add-dir is not an exception to
# that: its own help text says "--add-dir (CLAUDE.md dirs)". Measured three ways
# against this CLI version, all reporting zero skills -- --add-dir alone, a
# .claude/skills symlink in the working directory, and --setting-sources project.
#
# This is not a defect to work around. The prompts name each skill by PATH
# (prompts/research.md: "Apply the math-research skill at
# ${DN_REPO}/.agents/skills/math-research/SKILL.md ... in full"), so the agent
# reads them as files. That is what makes one skill tree serve both runners, and
# it is why bare mode costs us nothing here. Do not trade --bare away for skill
# auto-loading: bare is what stops an unattended agent holding a signing key from
# running whatever hooks land in the repo's .claude/settings.json.

# --permission-mode dontAsk denies anything outside the allow rules and the
# read-only command set -- the locked-down posture for unattended runs.
# --allowedTools uses permission rule syntax; the space before * matters.
#
# These rules are prefix matches against the literal command line, so they have
# to match what the prompts actually tell the agent to type. Both original rules
# failed on the first real firing and the agent could do nothing but read:
#
# The rule form is `Bash(<prefix>:*)`, NOT `Bash(<prefix> *)`. Every rule here
# used the second form and every one of them silently matched nothing: the first
# real firing denied `curl` and `discovery-net` alike and the agent could only
# read. Measured directly against this CLI version:
#
#     Bash(curl -s http://127.0.0.1:*)   denied
#     Bash(curl:*)                       allowed
#     Bash(curl -s:*)                    allowed
#     Bash(<abs path to CLI>:*)          allowed
#
# The prefix also has to end on a whole argument. `curl -s http://127.0.0.1`
# cuts into the middle of the URL argument, which is why the loopback-scoped
# rule never matched and cannot be written this way.
#
# `discovery-net *` additionally assumed the CLI is on PATH, but init-node.sh
# probes for it and records an ABSOLUTE path in the node binding. Derive it
# rather than assume; DN_SUBMIT_BASE is exported by lib/binding.sh.
# Write, and ls, because the design assumes both and the first real firing had
# neither. Without Write the agent cannot create its claim file, write a body
# file, or add a source artifact; without a way to list a directory it cannot
# read the claims of agents it has never met -- it reported claims.d as absent
# when the directory was there and merely empty. Rules are checked per component
# of a compound command, so granting `ls` grants only `ls`: `ls x && rm y` still
# dies on `rm`. Notes-clone git uses `git -C <dir>`, which needs no `cd` rule.
DN_CLI="${DN_SUBMIT_BASE%% *}"
ALLOWED="Read,Edit,Write"
ALLOWED="$ALLOWED,Bash(ls:*)"
ALLOWED="$ALLOWED,Bash(mkdir:*)"
# echo grants nothing, and without it agents lose whole probes: they use it as a
# separator, and one disallowed component fails the entire compound. Not cat --
# Read already covers reading, and `cat` inside a compound is the short path to a
# signing key in a transcript.
ALLOWED="$ALLOWED,Bash(echo:*)"

# Computation, sandboxed. Never Bash(python:*) -- an interpreter has sockets,
# subprocess and open(), so it hands back the network, every denied command, and
# the signing key in one grant. dn-compute runs a script under --network none as
# nobody, with no key mounted and a hard timeout; agent-sessions/tools/tests/
# isolation.sh asserts each of those and must pass before this rule is trusted.
#
# The allow-listed path must be somewhere the agent CANNOT write, or it simply
# rewrites the file and executes whatever it likes. --add-dir puts this checkout
# in the agent's write scope, so on an agent host set DN_COMPUTE_BIN to a
# root-owned path outside it. The in-repo default is for a trusted laptop.
DN_COMPUTE="${DN_COMPUTE_BIN:-$REPO_ROOT/agent-sessions/tools/dn-compute}"
[ -x "$DN_COMPUTE" ] && ALLOWED="$ALLOWED,Bash($DN_COMPUTE:*)"
ALLOWED="$ALLOWED,Bash($DN_CLI:*)"
ALLOWED="$ALLOWED,Bash(git:*)"
# The prompts ask for an ISO8601 UTC stamp on the worklog line. Without this the
# agent has no clock: the first passing conformance run substituted the block-1
# timestamp out of node-status.json and said so, which is the honest failure
# mode but still the wrong value. Reading a clock grants nothing.
ALLOWED="$ALLOWED,Bash(date:*)"

# Model. Unset means Claude Code's own default, which is what the first cost
# measurement was taken on -- do not give this a default here, or the number in
# runs.jsonl stops meaning what the ledger says it means. Set DN_MODEL in an
# agent binding to run one agent cheaper than another: the research agent is the
# obvious candidate, since a reviewer refereeing someone else's proof is the
# firing you least want underpowered.
MODEL_ARGS=()
[ -n "${DN_MODEL:-}" ] && MODEL_ARGS=(--model "$DN_MODEL")

exec claude --bare -p "$(cat "$PROMPT_FILE")" \
  --add-dir "$REPO_ROOT" \
  --permission-mode dontAsk \
  --allowedTools "$ALLOWED" \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  --max-turns "${DN_MAX_TURNS:-60}" \
  --output-format json
