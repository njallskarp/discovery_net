#!/usr/bin/env bash
#
# One firing of one agent.
#
#   agent-sessions/run.sh <agent> [--dry-run]
#
# Portable on purpose: bash 3.2, no flock, no GNU timeout, no envsubst. Local
# testing happens on a macOS laptop where none of those exist, and the same
# script has to run under systemd on Debian. Anything needing real parsing is in
# lib/dnagent.py.
#
# The governing rule: every check that can be made without the model is made
# here, so a skipped or no-op firing costs nothing.

set -eu

HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/.." && pwd)"
DN="python3 $HERE/lib/dnagent.py"
CONFIG="${DN_CONFIG:-$HERE/budget.toml}"

AGENT="${1:-}"
[ -n "$AGENT" ] || { echo "usage: run.sh <agent> [--dry-run]" >&2; exit 2; }
DRY_RUN=0
[ "${2:-}" = "--dry-run" ] && DRY_RUN=1

. "$HERE/lib/binding.sh"
resolve_binding "$HERE" "$AGENT" || exit $?

STATE_ROOT="${DN_STATE_ROOT:-$HOME/.local/state/discovery-net-agents}"
STATE_DIR="$STATE_ROOT/$DN_AGENT"
mkdir -p "$STATE_DIR"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR="$STATE_DIR/runs/$RUN_ID"
mkdir -p "$RUN_DIR"

STARTED_ISO="$($DN now)"
STARTED_EPOCH="$(date +%s)"

EMPTY_TOKENS='{"in":0,"cached_in":0,"out":0}'

status() {                       # status <state> [extra json fragment]
  printf '{"agent":"%s","runner":"%s","role":"%s","node":"%s","state":"%s","run_id":"%s","started_at":"%s"%s}\n' \
    "$DN_AGENT" "$DN_RUNNER" "$DN_ROLE" "${DN_NODE:-}" "$1" "$RUN_ID" "$STARTED_ISO" "${2:-}" \
    | $DN write-status "$STATE_DIR"
}

END_H=""                         # set once the runner has finished; null before that

finish() {                       # finish <exit-reason> [cost] [tokens-json] [height] [note]
  reason="$1"; cost="${2:-0}"; toks="${3:-$EMPTY_TOKENS}"
  height="${4:-}"; note="${5:-}"
  # indexed_height stays the PREFLIGHT reading: the reviewer's no-new-work gate
  # compares one firing's preflight to the next, so redefining it would silently
  # change when a reviewer runs. indexed_height_end is the separate, additive
  # answer to "what did this firing leave behind" -- a research firing that moved
  # the chain 1 -> 9 logged 1 and looked like a stalled indexer.
  printf '{"agent":"%s","runner":"%s","role":"%s","node":"%s","run_id":"%s","started_at":"%s","started_epoch":%s,"ended_at":"%s","exit":"%s","cost_usd":%s,"tokens":%s,"indexed_height":%s,"indexed_height_end":%s,"note":"%s"}\n' \
    "$DN_AGENT" "$DN_RUNNER" "$DN_ROLE" "${DN_NODE:-}" "$RUN_ID" "$STARTED_ISO" "$STARTED_EPOCH" \
    "$($DN now)" "$reason" "$cost" "$toks" "${height:-null}" "${END_H:-null}" "$note" \
    | $DN append-run "$STATE_DIR"
  # The table shows where the chain actually is, so it reads the end height when
  # there is one. status.json is display only; no gate reads it.
  status "idle" ",\"last_exit\":\"$reason\",\"indexed_height\":${END_H:-${height:-null}},\"cycle\":$CYCLE"
  echo "$DN_AGENT: $reason${note:+ — $note}"
}

CYCLE="$(( $(grep -c '' "$STATE_DIR/runs.jsonl" 2>/dev/null || echo 0) + 1 ))"

# ---------------------------------------------------------------- gate: cadence
INTERVAL="$($DN config "$CONFIG" "mode.$($DN config "$CONFIG" mode.active cruise).${DN_ROLE}_interval" 30m)"
if [ "$DRY_RUN" -eq 0 ]; then
  if ! due="$($DN gate-cadence "$STATE_DIR" "$INTERVAL")"; then
    echo "$DN_AGENT: not due ($due)"; exit 0
  fi
fi

# ----------------------------------------------------------------- gate: budget
CAP="$($DN config "$CONFIG" budget.monthly_cap_usd 0)"
if ! mtd="$($DN gate-budget "$STATE_ROOT" "$CAP")"; then
  finish "budget-paused" 0 '{"in":0,"cached_in":0,"out":0}' "" "month to date \$$mtd of \$$CAP"
  exit 0
fi

# --------------------------------------------------------------- gate: preflight
# Liveness of the INDEXER, not of block production. This chain runs
# create_empty_blocks = false, so a static height is the normal idle state of a
# quiet chain and must never be read as a fault.
STATUS_JSON="$RUN_DIR/node-status.json"
if ! curl -sS -m 10 "${DN_RPC_URL}/status" -o "$STATUS_JSON" 2>"$RUN_DIR/curl.err"; then
  finish "preflight-abort" 0 '{"in":0,"cached_in":0,"out":0}' "" "node unreachable at $DN_RPC_URL"
  exit 0
fi
NET="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["result"]["node_info"]["network"])' "$STATUS_JSON" 2>/dev/null || echo "")"
CATCHUP="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["result"]["sync_info"]["catching_up"])' "$STATUS_JSON" 2>/dev/null || echo "")"
NODE_H="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["result"]["sync_info"]["latest_block_height"])' "$STATUS_JSON" 2>/dev/null || echo "")"

if [ "$NET" != "${DN_CHAIN_ID}" ]; then
  finish "preflight-abort" 0 '{"in":0,"cached_in":0,"out":0}' "" "chain is '$NET', binding says '$DN_CHAIN_ID'"
  exit 0
fi
if [ "$CATCHUP" != "False" ] && [ "$CATCHUP" != "false" ]; then
  finish "preflight-abort" 0 '{"in":0,"cached_in":0,"out":0}' "" "node is catching up"
  exit 0
fi

IDX_H="$(eval "$DN_GRAPHQL_CMD '{ indexedHeight }'" 2>/dev/null \
        | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("data") or d)["indexedHeight"])' 2>/dev/null || echo "")"
if [ -z "$IDX_H" ]; then
  finish "preflight-abort" 0 '{"in":0,"cached_in":0,"out":0}' "" "could not read indexedHeight"
  exit 0
fi
LAG="$(( NODE_H - IDX_H ))"
MAX_LAG="$($DN config "$CONFIG" budget.max_indexer_lag 50)"
if [ "$LAG" -gt "$MAX_LAG" ]; then
  finish "preflight-abort" 0 '{"in":0,"cached_in":0,"out":0}' "$IDX_H" "indexer behind by $LAG blocks"
  exit 0
fi

# ------------------------------------------------------- gate: is there new work
# Reviewers only. A quiet chain means nothing landed, and that costs zero tokens
# to discover here instead of paying a model to find out.
if [ "$DN_ROLE" = "review" ]; then
  PREV_H="$($DN last-indexed-height "$STATE_DIR")"
  if [ -n "$PREV_H" ] && [ "$PREV_H" = "$IDX_H" ]; then
    finish "no-new-work" 0 '{"in":0,"cached_in":0,"out":0}' "$IDX_H" "indexedHeight unchanged at $IDX_H"
    exit 0
  fi
fi

# ------------------------------------------------------------------- the firing
PROMPT="$RUN_DIR/prompt.md"
# The agent reads node status from this file rather than curling for it. The
# preflight above already fetched it, and a loopback-scoped curl rule turned out
# to be unwritable -- Bash allow rules match on whole-argument prefixes, so
# `curl -s http://127.0.0.1` cuts into the URL argument and never matches. The
# alternative was granting curl to any host to an agent holding a signing key.
export DN_NODE_STATUS="$STATUS_JSON"
# The sandboxed interpreter the prompts tell the agent to use. Same path the
# runner allow-lists, so the prompt can never name a tool the agent cannot run.
export DN_COMPUTE="${DN_COMPUTE_BIN:-$REPO_ROOT/agent-sessions/tools/dn-compute}"
export DN_NODE_HEIGHT="$NODE_H"
DN_REPO="${DN_REPO:-$REPO_ROOT}" $DN render "$HERE/prompts/$DN_ROLE.md" "$PROMPT"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "$DN_AGENT: dry run — gates passed, prompt at $PROMPT (height $NODE_H, indexed $IDX_H)"
  exit 0
fi

MAX_SECONDS="$($DN config "$CONFIG" budget.max_firing_seconds 1500)"
RAW="$RUN_DIR/runner.out"

# SIGINT first: Claude Code ends the turn on INT and abandons it on TERM, so the
# gentle signal is the one that lets a firing bank its work. SIGKILL is the
# backstop, never the plan.
"$HERE/runners/$DN_RUNNER.sh" "$PROMPT" "$REPO_ROOT" "$RUN_DIR" >"$RAW" 2>"$RUN_DIR/runner.err" &
CHILD=$!
( sleep "$MAX_SECONDS"; kill -INT "$CHILD" 2>/dev/null || true
  sleep 20;             kill -KILL "$CHILD" 2>/dev/null || true ) &
WATCHDOG=$!
# Off the job table. It is killed on every normal firing, and bash announces that
# with a "Terminated: 15" line that looks like the firing failed when it did not.
disown "$WATCHDOG" 2>/dev/null || true

status "running" ",\"cycle\":$CYCLE,\"deadline_epoch\":$(( STARTED_EPOCH + MAX_SECONDS )),\"indexed_height\":$IDX_H"

RC=0; wait "$CHILD" || RC=$?
kill "$WATCHDOG" 2>/dev/null || true

# Where the chain ended up. A local sqlite read, so it costs nothing, and it is
# read after the runner so it includes whatever this firing submitted.
END_H="$(eval "$DN_GRAPHQL_CMD '{ indexedHeight }'" 2>/dev/null \
        | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("data") or d)["indexedHeight"])' 2>/dev/null || echo "")"

USAGE="$($DN parse-usage "$DN_RUNNER" "$RAW" "$CONFIG")"
COST="$(printf '%s' "$USAGE" | python3 -c 'import json,sys;print(json.load(sys.stdin)["cost_usd"])')"
TOKS="$(printf '%s' "$USAGE" | python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin)["tokens"]))')"

case "$RC" in
  0)         finish "completed"  "$COST" "$TOKS" "$IDX_H" "" ;;
  130|143|2) finish "killed"     "$COST" "$TOKS" "$IDX_H" "stopped at the deadline" ;;
  *)         finish "failed"     "$COST" "$TOKS" "$IDX_H" "runner exit $RC" ;;
esac
