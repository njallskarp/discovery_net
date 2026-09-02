#!/usr/bin/env bash
#
# Bind one agent to a node already described by init-node.sh.
#
#   agent-setup/init-agent.sh
#
# Ends by running a dry firing, so setup either proves itself or tells you why
# not. Nothing here reads or copies a contributor key; it only records where one
# lives and checks its permissions.

set -eu
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/.." && pwd)"
SESSIONS="$REPO_ROOT/agent-sessions"
. "$SESSIONS/lib/paths.sh"
. "$HERE/lib/ask.sh"
require_tty "init-agent.sh"

say ""
say "  Discovery Net — bind an agent"
say "  -----------------------------"
say ""

# ------------------------------------------------------------------- the node
NODES="$(ls "$DN_BINDINGS_DIR/nodes"/*.env 2>/dev/null || true)"
[ -n "$NODES" ] || die "no node bindings yet. Run agent-setup/init-node.sh first."
say "  Nodes described so far:"
for f in $NODES; do
  n="$(basename "$f" .env)"
  c="$(env_get "$f" DN_CHAIN_ID)"
  note "$n  (chain $c)"
done
say ""
DEFAULT_NODE="$(basename "$(echo "$NODES" | head -1)" .env)"
while :; do
  ask NODE_NAME "Which node" "$DEFAULT_NODE"
  NODE_FILE="$DN_BINDINGS_DIR/nodes/$NODE_NAME.env"
  [ -f "$NODE_FILE" ] && break
  bad "no such node binding: $NODE_FILE"
done
set -a; . "$NODE_FILE"; set +a
ok "chain $DN_CHAIN_ID at $DN_RPC_URL"

# ------------------------------------------------------------------- identity
say ""
ask_choice ROLE   "Role"   "research review" "research"
ask_choice RUNNER "Runner" "claude codex"    "claude"
case "$RUNNER" in
  claude) command -v claude >/dev/null 2>&1 || note "'claude' is not on PATH here — fine if agents run elsewhere" ;;
  codex)  command -v codex  >/dev/null 2>&1 || note "'codex' is not on PATH here — fine if agents run elsewhere"
          note "the Codex runner is still a stub; see CODEX-CANARY.md" ;;
esac
ask AGENT "Agent name" "$([ "$ROLE" = review ] && echo reviewer || echo researcher-1)"

# ------------------------------------------------------------------ signing key
# Recorded, never read. An unattended agent with a world-readable key is a
# finding, not a detail.
say ""
while :; do
  ask KEY "Contributor key (PEM) path" "$DN_AGENTS_ROOT/$AGENT/contributor.pem"
  if [ ! -f "$KEY" ]; then
    bad "not found: $KEY"
    # The one step that had no script. Generating here means the key is born
    # mode 600 in the agent's own directory, rather than at the repo root where
    # a README line used to put it and a git add -A once swept it up.
    if confirm "  generate a new Ed25519 key there now?"; then
      mkdir -p "$(dirname "$KEY")"
      ( umask 077; openssl genpkey -algorithm ed25519 -out "$KEY" ) \
        && ok "generated $KEY (mode 600). This is a new on-chain identity; back it up." \
        || { bad "openssl failed"; continue; }
      break
    fi
    confirm "  record it anyway (you will create it before the first firing)?" && break
    continue
  fi
  MODE="$(stat -c '%a' "$KEY" 2>/dev/null || stat -f '%Lp' "$KEY" 2>/dev/null || echo '?')"
  case "$MODE" in
    600|400) ok "key present, mode $MODE" ;;
    *)       bad "key is mode $MODE — readable beyond its owner"
             confirm "  chmod 600 it now?" && { chmod 600 "$KEY"; ok "now mode 600"; } ;;
  esac
  break
done

# ---------------------------------------------------------------------- state
say ""
# Both default under DN_AGENTS_ROOT (lib/paths.sh). Under the systemd unit that
# is /srv/agent-sessions/agents -- the only tree the unit lets the agent write --
# so run this script with DN_AGENTS_ROOT set the same way on a host, or the
# worklog lands under a read-only \$HOME and the first paid firing ends in EROFS.
#
# The claims directory is asked for, not derived from the agent directory's
# parent: every agent on this box must resolve to the SAME one, or two of them
# coordinate through different directories without knowing it.
say ""
note "agents root $DN_AGENTS_ROOT   (set DN_AGENTS_ROOT to move everything below)"
ask STATE  "Working directory for this agent (worklog, notes clone)" "$DN_AGENTS_ROOT/$AGENT"
ask CLAIMS "Claims directory, shared by every agent on this box" "$DN_AGENTS_ROOT/claims.d"
WORKLOG="$STATE/worklog.md"
NOTES="$STATE/discovery-net-notes"
note "worklog     $WORKLOG"
note "claims dir  $CLAIMS   (one file per agent; must be the same for every agent here)"
note "notes clone $NOTES    (per agent, so concurrent git never collides)"

# The notes repo holds SOURCE ARTIFACTS -- code, datasets, formalisations -- that
# back an on-chain contribution and are too bulky for a body. It is not the chain
# and it is not optional scenery: the prompts tell the agent to commit there, and
# until now nothing ever created it, so every firing reported "nothing committed".
#
# The upstream is shared between collaborators, which is what makes reproduction
# possible. Leave it as 'none' on a node VM: deploy/gcp/single-node/README.md is
# explicit that a machine holding validator keys gets no GitHub credentials, which
# is why agents belong on a host of their own. A local-only repo still works --
# the prompts already say to leave a commit local when push has no credentials.
say ""
ask NOTES_UPSTREAM "Notes repo upstream git URL ('none' for a local-only repo)" "none"
# The worklog is created here, not left to the first firing: the prompts tell the
# agent to APPEND one line to it, and an append to a file that does not exist is
# a failed step at the end of a paid run. Never truncate an existing one.
if confirm "  create these now?"; then
  mkdir -p "$STATE" "$CLAIMS"

  if [ -d "$NOTES/.git" ]; then
    ok "notes clone already present, left alone"
  elif [ "$NOTES_UPSTREAM" = "none" ]; then
    mkdir -p "$NOTES"
    git init -q "$NOTES" && ok "initialised a local-only notes repo at $NOTES"
  else
    if git clone "$NOTES_UPSTREAM" "$NOTES"; then
      ok "cloned $NOTES_UPSTREAM"
    else
      bad "clone failed; leaving a local-only repo so firings are not blocked"
      mkdir -p "$NOTES"; git init -q "$NOTES"
    fi
  fi
  # A fresh repo on a host with no global git identity cannot commit at all, and
  # the agent would only discover that at the end of a paid firing. Set it per
  # repo so it never depends on the operator's own git config.
  if [ -d "$NOTES/.git" ]; then
    git -C "$NOTES" config user.name  "$AGENT"
    git -C "$NOTES" config user.email "$AGENT@discovery-net.invalid"
  fi
  if [ ! -f "$WORKLOG" ]; then
    printf '# Worklog — %s\n\nOne line per firing. Append only; never rewrite history here.\n\n' \
      "$AGENT" > "$WORKLOG"
    ok "created, including an empty $WORKLOG"
  else
    ok "created (left the existing worklog alone)"
  fi
fi

REVIEWED_LINE=""
if [ "$ROLE" = "review" ]; then
  REVIEWED_LINE="DN_REVIEWED=$(q "$STATE/reviewed.jsonl")"
  note "review ledger $STATE/reviewed.jsonl"
fi

OUT="$DN_BINDINGS_DIR/agents/$AGENT.env"
write_env "$OUT" <<EOF
# Agent binding for $AGENT — generated by init-agent.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Agent facts only; node facts come from ../nodes/$NODE_NAME.env.
# Outside the checkout: this names a key location on one machine, and it is
# sourced by every firing, so it must not be where the agent can write.

DN_AGENT=$(q "$AGENT")
DN_ROLE=$(q "$ROLE")
DN_RUNNER=$(q "$RUNNER")
DN_NODE_BINDING=$(q "$NODE_NAME")

DN_KEY_PATH=$(q "$KEY")
DN_WORKLOG=$(q "$WORKLOG")
DN_CLAIMS_DIR=$(q "$CLAIMS")
DN_NOTES_CLONE=$(q "$NOTES")
$REVIEWED_LINE
EOF

# ------------------------------------------------------------- prove it works
say "  Checking it end to end (gates and render only — spends nothing)..."
say ""
if "$SESSIONS/run.sh" "$AGENT" --dry-run; then
  say ""
  say "  Ready. One firing:        agent-sessions/run.sh $AGENT"
  say "  What the agents are doing: agent-sessions/agentctl status"
else
  say ""
  say "  The binding is written but a gate stopped the dry run. The line above"
  say "  says which one. Fix it and re-run: agent-sessions/run.sh $AGENT --dry-run"
fi
say ""
