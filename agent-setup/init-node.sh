#!/usr/bin/env bash
#
# Describe one node, once. Every agent bound to it reuses this file, so the node
# facts live in exactly one place and cannot drift between agents.
#
#   agent-setup/init-node.sh
#
# Each answer is checked against the running node as you give it, so a mistake
# surfaces here rather than as a preflight-abort three hours into a schedule.

set -eu
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/.." && pwd)"
SESSIONS="$REPO_ROOT/agent-sessions"
. "$SESSIONS/lib/paths.sh"
. "$HERE/lib/ask.sh"
require_tty "init-node.sh"

say ""
say "  Discovery Net — describe a node"
say "  ------------------------------"
say "  Answers are verified against the node as you go. Ctrl-C to stop; nothing"
say "  is written until the end."
say ""

# ---------------------------------------------------------------- RPC endpoint
while :; do
  ask RPC "RPC URL (loopback only)" "http://127.0.0.1:26657"
  if ! STATUS="$(curl -sS -m 10 "$RPC/status" 2>/dev/null)"; then
    bad "no answer from $RPC/status"
    confirm "  try a different URL?" || die "stopped."
    continue
  fi
  MONIKER="$(printf '%s' "$STATUS" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["node_info"]["moniker"])' 2>/dev/null || echo)"
  CHAIN="$(printf  '%s' "$STATUS" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["node_info"]["network"])' 2>/dev/null || echo)"
  HEIGHT="$(printf '%s' "$STATUS" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["sync_info"]["latest_block_height"])' 2>/dev/null || echo)"
  CATCHUP="$(printf '%s' "$STATUS" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["sync_info"]["catching_up"])' 2>/dev/null || echo)"
  POWER="$(printf  '%s' "$STATUS" | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["validator_info"]["voting_power"])' 2>/dev/null || echo)"
  [ -n "$CHAIN" ] || { bad "that answered, but not like a CometBFT node"; continue; }
  ok "$MONIKER on chain '$CHAIN', height $HEIGHT, catching_up=$CATCHUP, voting power $POWER"
  [ "$POWER" != "0" ] && note "this node is a validator — agent load on it is load on consensus"
  break
done

ask NODE     "Node name"  "${MONIKER:-node-1}"
ask CHAIN_ID "Chain ID"   "$CHAIN"

# ------------------------------------------------------------ ledger read path
# The field that differs most between operators, so it is probed rather than
# trusted: a root-owned bind mount needs a docker exec, a user-owned one does not.
say ""
say "  Reading the committed ledger"
DEFAULT_CLI="$(command -v discovery-net 2>/dev/null || true)"
[ -z "$DEFAULT_CLI" ] && [ -x "$REPO_ROOT/.venv/bin/discovery-net" ] && DEFAULT_CLI="$REPO_ROOT/.venv/bin/discovery-net"
ask CLI    "discovery-net CLI path" "${DEFAULT_CLI:-$REPO_ROOT/.venv/bin/discovery-net}"
ask LEDGER "artifact-ledger.sqlite path (as this account sees it)" \
           "$REPO_ROOT/run/discovery-demo/${NODE}/ledger-data/artifact-ledger.sqlite"

GRAPHQL=""
try_graphql() {
  OUT="$(eval "$1 '{ indexedHeight }'" 2>&1)" || return 1
  H="$(printf '%s' "$OUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("data") or d)["indexedHeight"])' 2>/dev/null)" || return 1
  [ -n "$H" ] || return 1
  ok "indexedHeight = $H"
  return 0
}

CAND="$CLI graphql --ledger-path $LEDGER"
READ_MODE=""
say "    trying direct read..."
if try_graphql "$CAND"; then
  GRAPHQL="$CAND"; READ_MODE="direct"
else
  bad "direct read failed (usually a root-owned bind mount)"
  say "    a container exec can read it instead."
  DEFAULT_CTR="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i "${NODE}.*application" | head -1 || true)"
  ask CTR "application container name" "${DEFAULT_CTR:-discovery-node-${NODE}-application-1}"
  ask INNER "ledger path inside the container" "/var/lib/discovery-net/artifact-ledger.sqlite"
  CAND="docker exec $CTR discovery-net graphql --ledger-path $INNER"
  say "    trying container read..."
  if try_graphql "$CAND"; then
    GRAPHQL="$CAND"; READ_MODE="container"
  else
    bad "that failed too"
    say "    Both read paths failed. The binding would abort every firing at"
    say "    preflight, so it is not worth writing one yet. Fix the read path"
    say "    and run this again."
    die "stopped."
  fi
fi

# ------------------------------------------------------------------- inspector
# The inspector opens the SQLite ledger directly, so it can only run on the host
# when the DIRECT read path worked. If we fell back to a container exec, the
# ledger is root-owned and a host-side inspector cannot open it either -- the
# cloud deployment runs the inspector in a container for exactly this reason.
say ""
say "  Inspector"
INSPECTOR_URL=""
if [ "$READ_MODE" = "direct" ]; then
  if confirm "  Start a read-only inspector for this node?"; then
    PORT="$(python3 - <<'PYPORT'
import socket
for p in range(8765, 8800):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p)); print(p); break
    except OSError:
        continue
    finally:
        s.close()
PYPORT
)"
    ask INSPECTOR_PORT "Port" "${PORT:-8765}"
    STATE_ROOT="$DN_STATE_ROOT"
    mkdir -p "$STATE_ROOT/inspectors"
    LOG="$STATE_ROOT/inspectors/$NODE.log"

    INSPECTOR_BIN="$(dirname "$CLI")/discovery-inspector"
    [ -x "$INSPECTOR_BIN" ] || INSPECTOR_BIN="$(command -v discovery-inspector || true)"
    if [ -z "$INSPECTOR_BIN" ]; then
      bad "discovery-inspector not found next to $CLI or on PATH"
      note "install the package (pip install -e .) and re-run, or start it yourself:"
      note "discovery-inspector --ledger-path $LEDGER --cometbft-rpc-url $RPC --listen-port $INSPECTOR_PORT"
    else
      nohup "$INSPECTOR_BIN" \
        --ledger-path "$LEDGER" \
        --cometbft-rpc-url "$RPC" \
        --listen-port "$INSPECTOR_PORT" >"$LOG" 2>&1 &
      INSPECTOR_PID=$!
      sleep 2
      if kill -0 "$INSPECTOR_PID" 2>/dev/null &&
         curl -sS -m 5 "http://127.0.0.1:$INSPECTOR_PORT/api/node" >/dev/null 2>&1; then
        INSPECTOR_URL="http://127.0.0.1:$INSPECTOR_PORT"
        ok "inspector up at $INSPECTOR_URL (pid $INSPECTOR_PID)"
        printf '{"node":"%s","pid":%s,"port":%s,"url":"%s","ledger":"%s","rpc":"%s","log":"%s"}\n' \
          "$NODE" "$INSPECTOR_PID" "$INSPECTOR_PORT" "$INSPECTOR_URL" "$LEDGER" "$RPC" "$LOG" \
          > "$STATE_ROOT/inspectors/$NODE.json"
        note "teardown: agent-setup/teardown.sh"
      else
        bad "it did not come up; last lines of $LOG:"
        tail -5 "$LOG" 2>/dev/null | sed 's/^/      /'
        kill "$INSPECTOR_PID" 2>/dev/null || true
      fi
    fi
  fi
else
  note "skipped: this node's ledger is read through a container, so a host-side"
  note "inspector cannot open the SQLite file. The cloud overlay runs one in a"
  note "container instead -- see deploy/gcp/single-node/."
fi

# ---------------------------------------------------------------- submit prefix
# No key here on purpose. The key belongs to an agent, not to a node, and having
# it in one place stops DN_KEY_PATH and the submit command disagreeing.
SUBMIT_BASE="$CLI submit contribution --rpc-url $RPC"

# Outside the checkout on purpose: the agent's write scope includes the
# checkout, and this file is sourced and eval'd by every tick.
OUT_DIR="$DN_BINDINGS_DIR/nodes"
ask OUT "Write to" "$OUT_DIR/$NODE.env"

write_env "$OUT" <<EOF
# Node binding for $NODE — generated by init-node.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Node facts only. Agents that use this node live in ../agents/.
# Outside the checkout: absolute paths here describe one machine, and the file
# is sourced by every firing, so it must not be where the agent can write.

DN_NODE=$(q "$NODE")
DN_CHAIN_ID=$(q "$CHAIN_ID")
DN_RPC_URL=$(q "$RPC")

# Verified against the running node at generation time.
DN_GRAPHQL_CMD=$(q "$GRAPHQL")

# The agent's key is joined to this by tools/dn-submit, never written here.
DN_SUBMIT_BASE=$(q "$SUBMIT_BASE")

# Read-only inspector for this node, if one is running.
DN_INSPECTOR_URL=$(q "$INSPECTOR_URL")
EOF

say "  Next: agent-setup/init-agent.sh to bind an agent to this node."
say ""
