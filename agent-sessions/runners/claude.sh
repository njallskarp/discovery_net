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
# Write, and ls, because the design assumes both and the first real firing had
# neither. Without Write the agent cannot create its claim file, write a body
# file, or add a source artifact; without a way to list a directory it cannot
# read the claims of agents it has never met -- it reported claims.d as absent
# when the directory was there and merely empty. Rules are checked per component
# of a compound command, so granting `ls` grants only `ls`: `ls x && rm y` still
# dies on `rm`.
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
# Every allow-listed path must be somewhere the agent CANNOT write, or it simply
# rewrites the file and executes whatever it likes. --add-dir puts this checkout
# in the agent's write scope, so on an agent host set the *_BIN overrides to
# root-owned paths outside it. The in-repo defaults are for a trusted laptop.
# Under the systemd unit ProtectSystem=strict makes the checkout read-only.
DN_COMPUTE="${DN_COMPUTE_BIN:-$REPO_ROOT/agent-sessions/tools/dn-compute}"
[ -x "$DN_COMPUTE" ] && ALLOWED="$ALLOWED,Bash($DN_COMPUTE:*)"

# Submitting, through dn-submit and never the raw CLI. The CLI takes
# --private-key and --body-file from argv, so Bash(<cli>:*) let an agent that
# knew the key path publish the key with one flag. dn-submit owns the key path,
# refuses --private-key, --rpc-url and --body, and refuses a body file that is
# or contains the key. tools/tests/wrappers.sh asserts each refusal.
: "${DN_SUBMIT:?run.sh exports DN_SUBMIT}"
ALLOWED="$ALLOWED,Bash($DN_SUBMIT:*)"

# Reading the graph. The prefix is the whole read command including the ledger
# path, so the agent can append a query and nothing else: `<cli> graphql
# --ledger-path <p>` for a direct read, `docker exec <ctr> discovery-net graphql
# --ledger-path <p>` for a container read. Neither form grants the bare CLI or
# bare docker. NOT YET MEASURED against this CLI version: the rule forms that
# were measured had one or two words before the colon, not a whole command
# line. Confirm with one run before trusting it; if it silently matches nothing
# the agent will report the graphql read as denied.
ALLOWED="$ALLOWED,Bash($DN_GRAPHQL_CMD:*)"

# Git, through dn-notes and never bare. `git -c alias.x='!sh' x` is a shell,
# so Bash(git:*) was an allow rule on everything else on this list -- the
# network, docker, the key. dn-notes pins -C to the notes clone, admits a fixed
# set of subcommands, and refuses the options git would exec through.
: "${DN_NOTES:?run.sh exports DN_NOTES}"
ALLOWED="$ALLOWED,Bash($DN_NOTES:*)"

# The prompts ask for an ISO8601 UTC stamp on the worklog line. Without this the
# agent has no clock: the first passing conformance run substituted the block-1
# timestamp out of node-status.json and said so, which is the honest failure
# mode but still the wrong value. Reading a clock grants nothing.
ALLOWED="$ALLOWED,Bash(date:*)"

# Literature. The skills require candidate-specific literature research before
# any novelty claim and forbid invented citations, and the research prompt says
# to find problems in the literature rather than in the graph. Without these
# the agent can only fabricate that step or discover it cannot do it. WebSearch
# sends queries to the search provider; WebFetch is scoped to the mathematical
# sources below and nowhere else, so neither is a channel an attacker can read
# back from -- and the agent no longer knows the key path in any case.
# Add a domain here rather than granting WebFetch unscoped.
ALLOWED="$ALLOWED,WebSearch"
for domain in arxiv.org mathoverflow.net math.stackexchange.com oeis.org zbmath.org \
              mathscinet.ams.org ams.org springer.com sciencedirect.com jstor.org \
              wikipedia.org en.wikipedia.org ncatlab.org mathworld.wolfram.com \
              leanprover-community.github.io github.com; do
  ALLOWED="$ALLOWED,WebFetch(domain:$domain)"
done

# The key is readable by this account -- it has to be, dn-submit runs as it --
# so the blanket Read grant above would let the agent read it by path. Deny
# that path explicitly for every file tool. The prompt no longer names the
# path, but a deny rule is not a request. NOT YET MEASURED: the Read(<path>)
# deny form is documented but has not been exercised here; confirm with one
# run that `Read` of DN_KEY_PATH is refused.
: "${DN_KEY_PATH:?lib/binding.sh exports DN_KEY_PATH}"
DISALLOWED="Read($DN_KEY_PATH),Edit($DN_KEY_PATH),Write($DN_KEY_PATH)"

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
  --disallowedTools "$DISALLOWED" \
  ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} \
  --max-turns "${DN_MAX_TURNS:-60}" \
  --output-format json
