#!/usr/bin/env bash
#
# Take down what init-node.sh, init-agent.sh and localnet.sh bootstrap set up.
#
#   agent-setup/teardown.sh [--dry-run]
#
# Shows an inventory first, then asks per category. Nothing is removed until you
# have seen exactly what it would remove.
#
# Two things it will not do:
#   - touch a contributor key. Deleting one destroys an on-chain identity that
#     cannot be recovered, and the artifacts it signed outlive the key.
#   - touch anything belonging to a node it did not start. It kills only the
#     inspectors recorded in its own state directory, and removes only localnet
#     state under this checkout's run/ directory.

set -eu
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/.." && pwd)"
SESSIONS="$REPO_ROOT/agent-sessions"
. "$HERE/lib/ask.sh"
require_tty "teardown.sh"

DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
STATE_ROOT="${DN_STATE_ROOT:-$HOME/.local/state/discovery-net-agents}"
LOCALNET_ROOT="${DN_ROOT:-$REPO_ROOT/run/discovery-demo}"

say ""
say "  Discovery Net — teardown"
say "  ------------------------"
[ "$DRY" = 1 ] && say "  DRY RUN. Nothing will be removed." && say ""

# ------------------------------------------------------------------ inventory
INSPECTORS="$(ls "$STATE_ROOT/inspectors"/*.json 2>/dev/null || true)"
NODE_BINDINGS="$(ls "$SESSIONS/bindings/nodes"/*.env 2>/dev/null || true)"
AGENT_BINDINGS="$(ls "$SESSIONS/bindings/agents"/*.env 2>/dev/null || true)"
LOCALNET_ENVS="$(ls "$LOCALNET_ROOT"/*.env 2>/dev/null || true)"

say "  What is here"
say ""
if [ -n "$INSPECTORS" ]; then
  say "  inspectors started by init-node.sh:"
  for f in $INSPECTORS; do
    n=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["node"])' "$f")
    pid=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["pid"])' "$f")
    url=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["url"])' "$f")
    alive="not running"; kill -0 "$pid" 2>/dev/null && alive="pid $pid"
    note "$n  $url  ($alive)"
  done
else
  note "inspectors: none recorded"
fi

say ""
if [ -n "$LOCALNET_ENVS" ]; then
  say "  localnet nodes under $LOCALNET_ROOT:"
  for f in $LOCALNET_ENVS; do note "$(basename "$f" .env)"; done
else
  note "localnet: nothing under $LOCALNET_ROOT"
fi

# Chain IDs are shown because this is the moment to notice a binding that points
# at the real network rather than a throwaway local one.
say ""
if [ -n "$NODE_BINDINGS$AGENT_BINDINGS" ]; then
  say "  bindings:"
  for f in $NODE_BINDINGS; do
    c=$(grep -m1 '^DN_CHAIN_ID=' "$f" | cut -d= -f2-)
    note "node   $(basename "$f" .env)   chain $c"
  done
  for f in $AGENT_BINDINGS; do
    nb=$(grep -m1 '^DN_NODE_BINDING=' "$f" | cut -d= -f2-)
    note "agent  $(basename "$f" .env)   -> node $nb"
  done
else
  note "bindings: none"
fi

KEYS="$(for f in $AGENT_BINDINGS; do grep -m1 '^DN_KEY_PATH=' "$f" | cut -d= -f2-; done 2>/dev/null || true)"
if [ -n "$KEYS" ]; then
  say ""
  say "  contributor keys (NOT removed by this script):"
  for k in $KEYS; do note "$k"; done
fi

say ""
say "  ---"

# ------------------------------------------------------------------- actions
if [ -n "$INSPECTORS" ] && confirm "  Stop the inspectors listed above?"; then
  for f in $INSPECTORS; do
    pid=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["pid"])' "$f")
    n=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["node"])' "$f")
    if [ "$DRY" = 1 ]; then say "    would: kill $pid ($n) and remove $f"; continue
    fi
    kill "$pid" 2>/dev/null && ok "stopped inspector for $n" || note "inspector for $n was not running"
    rm -f "$f"
  done
fi

if [ -n "$LOCALNET_ENVS" ] && confirm "  Stop the localnet containers?"; then
  for f in $LOCALNET_ENVS; do
    n="$(basename "$f" .env)"
    if [ "$DRY" = 1 ]; then say "    would: localnet.sh down $n"; continue; fi
    "$REPO_ROOT/localnet/localnet.sh" down "$n" >/dev/null 2>&1 && ok "stopped $n" || bad "could not stop $n"
  done
  if docker network inspect discovery-net-p2p >/dev/null 2>&1; then
    if [ "$DRY" = 1 ]; then say "    would: remove the discovery-net-p2p docker network"
    else docker network rm discovery-net-p2p >/dev/null 2>&1 \
           && ok "removed the discovery-net-p2p network" \
           || note "left the p2p network (containers are still attached)"; fi
  fi
fi

# Chain state. Destructive and worth its own question: for a localnet this is
# throwaway, but the same directory shape holds a real node's blocks.
if [ -d "$LOCALNET_ROOT" ]; then
  say ""
  say "  $LOCALNET_ROOT holds genesis, CometBFT block data and the derived ledger."
  say "  Removing it means this local chain is gone for good."
  if confirm "  Remove it?"; then
    if [ "$DRY" = 1 ]; then say "    would: rm -rf $LOCALNET_ROOT"
    else rm -rf "$LOCALNET_ROOT" && ok "removed $LOCALNET_ROOT"; fi
  fi
fi

if [ -n "$NODE_BINDINGS$AGENT_BINDINGS" ] && confirm "  Remove the bindings listed above?"; then
  for f in $NODE_BINDINGS $AGENT_BINDINGS; do
    if [ "$DRY" = 1 ]; then say "    would: rm $f"; else rm -f "$f" && ok "removed $(basename "$f")"; fi
  done
  note "re-create them with agent-setup/init-node.sh and init-agent.sh"
fi

if [ -d "$STATE_ROOT" ]; then
  say ""
  say "  $STATE_ROOT holds each agent's run ledger and status — what a firing"
  say "  costs and what it did. Worklogs live beside the agents, not here."
  if confirm "  Remove agent run state?"; then
    if [ "$DRY" = 1 ]; then say "    would: rm -rf $STATE_ROOT"
    else rm -rf "$STATE_ROOT" && ok "removed $STATE_ROOT"; fi
  fi
fi

if docker image inspect discovery-net-node:local >/dev/null 2>&1; then
  say ""
  if confirm "  Remove the discovery-net-node:local image?"; then
    if [ "$DRY" = 1 ]; then say "    would: docker rmi discovery-net-node:local"
    else docker rmi discovery-net-node:local >/dev/null 2>&1 \
           && ok "removed the image" || note "image is still in use"; fi
  fi
fi

say ""
if [ -n "$KEYS" ]; then
  say "  Contributor keys were left in place. Each one is an on-chain identity;"
  say "  the contributions it signed stay on the chain whether or not you keep it."
  say "  Remove them yourself if you mean to, one at a time."
fi
say "  Done."
say ""
