#!/usr/bin/env bash
#
# Take down what init-node.sh, init-agent.sh and localnet.sh bootstrap set up.
#
#   agent-setup/teardown.sh [--dry-run]
#
# Shows an inventory first, then asks per category. Nothing is removed until you
# have seen exactly what it would remove.
#
# Contributor keys are asked about last, one at a time, behind a typed
# confirmation rather than a y/n. Deleting one destroys an on-chain identity
# that cannot be recovered, and the artifacts it signed outlive the key, so the
# default at every one of those prompts is to keep it.
#
# One thing it will not do: touch anything belonging to a node it did not start.
# It kills only the inspectors recorded in its own state directory, and removes
# only localnet state under this checkout's run/ directory.

set -eu
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/.." && pwd)"
SESSIONS="$REPO_ROOT/agent-sessions"
. "$SESSIONS/lib/paths.sh"
. "$HERE/lib/ask.sh"
require_tty "teardown.sh"

DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

# Both of these end up under rm -rf, so they are canonicalised and fenced
# before anything else: the localnet root must be inside this checkout's run/,
# and the state root must look like an agent state directory and not be a
# home, a root, or a parent of the checkout. DN_ROOT=/ with a y held down
# would otherwise be the end of the machine.
canon() { python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$1"; }
STATE_ROOT="$(canon "$DN_STATE_ROOT")"
LOCALNET_ROOT="$(canon "${DN_ROOT:-$REPO_ROOT/run/discovery-demo}")"
case "$LOCALNET_ROOT" in
  "$(canon "$REPO_ROOT")/run/"?*) ;;
  *) die "refusing: localnet root $LOCALNET_ROOT is not under $REPO_ROOT/run/" ;;
esac
case "$STATE_ROOT" in
  /|"$HOME"|"$(canon "$HOME")"|"$(canon "$REPO_ROOT")"|"$(canon "$REPO_ROOT")"/*) die "refusing: state root $STATE_ROOT is not an agent state directory" ;;
  */discovery-net-agents|*/discovery-net-agents/*|*/agent-sessions/state|*/agent-sessions/state/*) ;;
  *) die "refusing: state root $STATE_ROOT does not look like an agent state directory (…/discovery-net-agents or …/agent-sessions/state)" ;;
esac

# Never pull state out from under a firing. On a host the timers have to be
# stopped first; on a laptop a run.sh in another terminal shows as running.
if command -v systemctl >/dev/null 2>&1 && systemctl list-units --type=timer --state=active 2>/dev/null | grep -q 'dn-agent@'; then
  die "refusing: dn-agent timers are active. Stop them first:
    sudo systemctl stop 'dn-agent@*.timer' 'dn-agent@*.service'"
fi
for sf in "$STATE_ROOT"/*/status.json; do
  [ -f "$sf" ] || continue
  if python3 -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1])).get("state")=="running" else 1)' "$sf" 2>/dev/null; then
    die "refusing: $(basename "$(dirname "$sf")") is mid-firing ($sf says running). Wait for it or kill it, then re-run."
  fi
done

say ""
say "  Discovery Net — teardown"
say "  ------------------------"
[ "$DRY" = 1 ] && say "  DRY RUN. Nothing will be removed." && say ""

# A recorded pid is only ours while the process behind it is still an
# inspector; pids are reused, and a stale record must not kill a stranger.
is_inspector() { ps -o command= -p "$1" 2>/dev/null | grep -q 'discovery-inspector'; }

# ------------------------------------------------------------------ inventory
INSPECTORS="$(ls "$STATE_ROOT/inspectors"/*.json 2>/dev/null || true)"
NODE_BINDINGS="$(ls "$DN_BINDINGS_DIR/nodes"/*.env 2>/dev/null || true)"
AGENT_BINDINGS="$(ls "$DN_BINDINGS_DIR/agents"/*.env 2>/dev/null || true)"
LOCALNET_ENVS="$(ls "$LOCALNET_ROOT"/*.env 2>/dev/null || true)"

say "  What is here"
say ""
if [ -n "$INSPECTORS" ]; then
  say "  inspectors started by init-node.sh:"
  for f in $INSPECTORS; do
    n=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["node"])' "$f")
    pid=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["pid"])' "$f")
    url=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["url"])' "$f")
    alive="not running"; is_inspector "$pid" && alive="pid $pid"
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
    c=$(env_get "$f" DN_CHAIN_ID)
    note "node   $(basename "$f" .env)   chain $c"
  done
  for f in $AGENT_BINDINGS; do
    nb=$(env_get "$f" DN_NODE_BINDING)
    note "agent  $(basename "$f" .env)   -> node $nb"
  done
else
  note "bindings: none"
fi

# Collected now, while the bindings that name them still exist -- the bindings
# are removed further down. A key at the repo root is picked up as well: that is
# where the README's genpkey line puts one, so it is present on a host that has
# never run init-agent.sh and has no binding to name it.
KEYS=()
add_key() {
  [ -n "$1" ] && [ -f "$1" ] || return 0
  for __ak in ${KEYS[@]+"${KEYS[@]}"}; do [ "$__ak" = "$1" ] && return 0; done
  KEYS+=("$1")
  return 0
}
for f in $AGENT_BINDINGS; do
  add_key "$(env_get "$f" DN_KEY_PATH)"
done
# The repo root is swept for keys left by the old README flow, which generated
# one there before init-agent.sh could. Nothing puts a key there any more.
for f in "$REPO_ROOT"/*.pem; do add_key "$f"; done

if [ "${#KEYS[@]}" -gt 0 ]; then
  say ""
  say "  contributor keys:"
  for k in "${KEYS[@]}"; do note "$k"; done
fi

say ""
say "  ---"

# ------------------------------------------------------------------- actions
if [ -n "$INSPECTORS" ] && confirm "  Stop the inspectors listed above?"; then
  for f in $INSPECTORS; do
    pid=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["pid"])' "$f")
    n=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["node"])' "$f")
    if [ "$DRY" = 1 ]; then say "    would: kill $pid ($n) if it is still an inspector, and remove $f"; continue
    fi
    if is_inspector "$pid"; then kill "$pid" && ok "stopped inspector for $n"
    else note "inspector for $n is not running (pid $pid is not an inspector); record removed"; fi
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

# Last, and one key at a time. Everything above this point can be rebuilt from
# the repo; a key cannot be rebuilt from anything. The prompt asks for the
# filename typed back rather than a y/n so that holding down y through the whole
# script does not end with a destroyed identity.
if [ "${#KEYS[@]}" -gt 0 ]; then
  say ""
  say "  Contributor keys. Each one is an on-chain identity: what it signed stays"
  say "  on the chain whether or not you keep the key, but without the key you can"
  say "  never sign as that identity again. There is no recovery and no backup."
  for k in "${KEYS[@]}"; do
    b="$(basename "$k")"
    say ""
    note "$k"
    ask KEY_ANS "    type '$b' to remove it, anything else keeps it" "keep"
    if [ "$KEY_ANS" != "$b" ]; then note "kept $k"; continue; fi
    if [ "$DRY" = 1 ]; then say "    would: rm $k"
    else rm -f "$k" && ok "removed $k"; fi
  done
fi

say ""
say "  Done."
say ""
