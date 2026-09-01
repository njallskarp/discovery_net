#!/usr/bin/env bash
#
# localnet.sh — one-stop setup for discovery_net local nodes.
#
# Wraps the manual flow from README.md: image build, validator/genesis
# formation, the P2P network, per-node .env files, and compose. It drives the
# stock localnet/compose.yaml only; for a production GCP VM use
# deploy/gcp/single-node/ instead.
#
# Subcommands
#   build                       Build the node image.
#   bootstrap [NODE]            Create a brand-new one-validator network and
#                               start NODE (default: node-a). Prints the trust
#                               anchor + bootstrap peer that joiners need.
#   join NODE --peer P \        Start NODE and sync it against an existing
#        --genesis F \          network. A peer whose host is an IP/FQDN (e.g. a
#        --genesis-sha256 S     cloud node) auto-enables egress; see --egress.
#   node-id NODE                Print NODE's peer address (id@NODE:26656).
#   status NODE                 Curl NODE's RPC /status.
#   logs NODE [...]             Follow NODE's container logs.
#   up NODE                     Restart a node that already exists, at the height
#                               it stopped at. Use this after a Docker daemon
#                               restart -- bootstrap refuses on a started home.
#   restart NODE                down then up.
#   down NODE [-v]              Stop NODE (-v also removes anon volumes).
#
# Options (or environment)
#   --root DIR        (DN_ROOT)      state dir      default: <repo>/run/discovery-demo
#   --image NAME      (DN_IMAGE)     image tag      default: discovery-net-node:local
#   --chain-id ID     (DN_CHAIN_ID)  genesis chain  default: discovery-local-1
#   --p2p-network N   (DN_P2P_NET)   ext P2P net    default: discovery-net-p2p
#   --rpc-port N      (DN_RPC_PORT)  host RPC port  default: 26657 bootstrap / 26667 join
#   --egress / --no-egress          force the P2P network internet-reachable (or not);
#                    (DN_EGRESS=1)   default: internal, but 'join' auto-enables it for a
#                                    non-local peer. Egress nodes dial OUT only — they are
#                                    not reachable from the internet (no published P2P port).
#   --peer STR                       join: bootstrap peer  id@host:26656  (required)
#   --genesis FILE                   join: trusted genesis.json           (required)
#   --genesis-sha256 HEX             join: trusted digest                 (required)
#   --force                          bootstrap: redo validator/genesis even if present
#
# Examples
#   ./localnet/localnet.sh bootstrap
#   ./localnet/localnet.sh node-id node-a
#   # join another node on this Docker host:
#   ./localnet/localnet.sh join node-b --peer <id>@node-a:26656 \
#       --genesis run/discovery-demo/genesis.json --genesis-sha256 <sha> --rpc-port 26667
#   # join a cloud node (deploy/gcp/single-node): egress is auto-enabled, and the
#   # cloud operator must allowlist this host's public /32 for port 26656:
#   ./localnet/localnet.sh join cloud-peer --peer <cloud-id>@203.0.113.7:26656 \
#       --genesis ./genesis.json --genesis-sha256 <sha>
#
# Peers on other machines need a routable P2P path (egress mode here, or the
# deploy/gcp overlay on the far side), matching the network model in README.md.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

abspath() { case "$1" in /*) printf '%s\n' "$1";; *) printf '%s/%s\n' "$(pwd)" "$1";; esac; }

sha256_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'
  fi
}

die() { echo "error: $*" >&2; exit 1; }

usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"; }

# ---- option pre-pass ---------------------------------------------------------
ROOT_OPT=""; PEER=""; GENESIS=""; GENESIS_SHA256=""; RPC_PORT=""; FORCE=0
EGRESS="${DN_EGRESS:-}"
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --root)           ROOT_OPT="$2"; shift 2;;
    --image)          DN_IMAGE="$2"; shift 2;;
    --chain-id)       DN_CHAIN_ID="$2"; shift 2;;
    --p2p-network)    DN_P2P_NET="$2"; shift 2;;
    --rpc-port)       RPC_PORT="$2"; shift 2;;
    --egress)         EGRESS=1; shift;;
    --no-egress)      EGRESS=0; shift;;
    --peer)           PEER="$2"; shift 2;;
    --genesis)        GENESIS="$(abspath "$2")"; shift 2;;
    --genesis-sha256) GENESIS_SHA256="$2"; shift 2;;
    --force)          FORCE=1; shift;;
    -h|--help)        usage; exit 0;;
    --)               shift; while [ $# -gt 0 ]; do ARGS+=("$1"); shift; done;;
    *)                ARGS+=("$1"); shift;;
  esac
done
set -- ${ARGS[@]+"${ARGS[@]}"}

IMAGE="${DN_IMAGE:-discovery-net-node:local}"
CHAIN_ID="${DN_CHAIN_ID:-discovery-local-1}"
P2P_NETWORK="${DN_P2P_NET:-discovery-net-p2p}"
ROOT="${ROOT_OPT:-${DN_ROOT:-$REPO_ROOT/run/discovery-demo}}"
mkdir -p "$ROOT"

# ---- helpers ---------------------------------------------------------------
image_exists() { docker image inspect "$IMAGE" >/dev/null 2>&1; }

dn_run() {
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$ROOT,target=/work" \
    "$IMAGE" "$@"
}

compose() {  # compose NODE <compose args...>
  local node="$1"; shift
  [ -f "$ROOT/$node.env" ] || die "no env for '$node' at $ROOT/$node.env — run bootstrap/join first"
  if docker compose version >/dev/null 2>&1; then
    docker compose --env-file "$ROOT/$node.env" -f "$COMPOSE_FILE" "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose --env-file "$ROOT/$node.env" -f "$COMPOSE_FILE" "$@"
  else
    die "need 'docker compose' (v2 plugin) or 'docker-compose'"
  fi
}

peer_host() { local hp="${1#*@}"; printf '%s\n' "${hp%:*}"; }

# Resolve egress intent: explicit --egress/--no-egress wins, else infer from the
# peer host (an IP or dotted FQDN needs internet egress; a bare Docker alias does not).
resolve_egress() {  # $1 = peer (may be empty)
  if [ -n "$EGRESS" ]; then echo "$EGRESS"; return; fi
  case "$(peer_host "${1:-}")" in
    *.*|*:*) echo 1;;   # dotted IPv4/FQDN or bracketless IPv6 → egress
    *)       echo 0;;
  esac
}

ensure_p2p_network() {  # $1 = 1 for egress (non-internal), else internal
  local want_internal=true; [ "${1:-0}" = 1 ] && want_internal=false
  if docker network inspect "$P2P_NETWORK" >/dev/null 2>&1; then
    local have_internal
    have_internal="$(docker network inspect -f '{{.Internal}}' "$P2P_NETWORK")"
    [ "$have_internal" = "$want_internal" ] || die \
"P2P network '$P2P_NETWORK' has Internal=$have_internal but this node needs Internal=$want_internal.
       Stop the nodes still on it, then recreate it:  docker network rm $P2P_NETWORK"
  elif [ "$want_internal" = false ]; then
    docker network create "$P2P_NETWORK" >/dev/null
  else
    docker network create --internal "$P2P_NETWORK" >/dev/null
  fi
}

write_env() {  # write_env NODE GENESIS_FILE GENESIS_SHA PEERS RPC_PORT
  local node="$1" genesis_file="$2" genesis_sha="$3" peers="$4" rpc_port="$5"
  cat > "$ROOT/$node.env" <<EOF
COMPOSE_PROJECT_NAME=discovery-$node
DISCOVERY_NET_IMAGE=$IMAGE
DISCOVERY_NET_UID=$(id -u)
DISCOVERY_NET_GID=$(id -g)

NODE_NAME=$node
CHAIN_ID=$CHAIN_ID
GENESIS_FILE=$genesis_file
GENESIS_SHA256=$genesis_sha

COMETBFT_DATA_DIRECTORY=$ROOT/$node/cometbft-data
LEDGER_DATA_DIRECTORY=$ROOT/$node/ledger-data

P2P_NETWORK=$P2P_NETWORK
P2P_ALIAS=$node
PERSISTENT_PEERS=$peers

RPC_PORT=$rpc_port
EOF
}

node_id() {  # bare id, read straight from the on-disk node key
  dn_run cometbft show-node-id --home "/work/$1/cometbft-data/cometbft" | tr -d '\r\n'
}

# ---- subcommands ---------------------------------------------------------------
cmd_build() {
  docker build -t "$IMAGE" -f "$SCRIPT_DIR/Dockerfile" "$REPO_ROOT"
}

cmd_bootstrap() {
  local node="${1:-node-a}"
  local rpc_port="${RPC_PORT:-26657}"
  local home="/work/$node/cometbft-data/cometbft"
  local home_fs="$ROOT/$node/cometbft-data/cometbft"

  image_exists || cmd_build
  mkdir -p "$ROOT/$node/cometbft-data" "$ROOT/$node/ledger-data"

  if [ "$FORCE" = 1 ] || [ ! -d "$home_fs" ]; then
    dn_run discovery-network initialize-validator --home "$home"
    dn_run discovery-network export-validator --home "$home" \
      --output "/work/validator-$node.json" --name "validator-$node"
  else
    echo "validator home present; skipping init (--force to redo)"
  fi

  if [ "$FORCE" = 1 ] || [ ! -f "$ROOT/genesis.json" ]; then
    dn_run discovery-network create-genesis \
      --output /work/genesis.json --chain-id "$CHAIN_ID" \
      --genesis-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --validator "/work/validator-$node.json"
  else
    echo "genesis.json present; skipping create (--force to redo)"
  fi

  local sha; sha="$(sha256_of "$ROOT/genesis.json")"
  dn_run discovery-network install-genesis --home "$home" \
    --genesis /work/genesis.json --chain-id "$CHAIN_ID" --genesis-sha256 "$sha"

  ensure_p2p_network "${EGRESS:-0}"
  write_env "$node" "$ROOT/genesis.json" "$sha" "" "$rpc_port"
  compose "$node" up -d

  cat <<EOF

Network up. Give joiners:
  CHAIN_ID        = $CHAIN_ID
  GENESIS_FILE    = $ROOT/genesis.json
  GENESIS_SHA256  = $sha
  BOOTSTRAP_PEER  = $(node_id "$node")@$node:26656
  P2P_NETWORK     = $P2P_NETWORK

RPC: http://127.0.0.1:$rpc_port/status
EOF
}

cmd_join() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: join NODE --peer P --genesis F --genesis-sha256 S"
  local rpc_port="${RPC_PORT:-26667}"
  [ -n "$PEER" ]           || die "--peer is required"
  [ -n "$GENESIS" ]        || die "--genesis is required"
  [ -n "$GENESIS_SHA256" ] || die "--genesis-sha256 is required"
  [ -f "$GENESIS" ]        || die "genesis file not found: $GENESIS"

  local egress; egress="$(resolve_egress "$PEER")"

  image_exists || cmd_build
  mkdir -p "$ROOT/$node/cometbft-data" "$ROOT/$node/ledger-data"
  ensure_p2p_network "$egress"
  write_env "$node" "$GENESIS" "$GENESIS_SHA256" "$PEER" "$rpc_port"
  compose "$node" up -d

  echo "Joined. RPC: http://127.0.0.1:$rpc_port/status"
  if [ "$egress" = 1 ]; then
    cat <<EOF

Egress P2P enabled: '$node' dials OUT to $(peer_host "$PEER") but is not itself
reachable from the internet (no published P2P port, advertises its Docker alias).
The remote operator must allowlist this host's public egress /32 for TCP 26656
(deploy/gcp/single-node/README.md, "Configure the peer side").
EOF
  fi
}

cmd_node_id() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: node-id NODE"
  echo "$(node_id "$node")@$node:26656"
}

cmd_status() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: status NODE"
  local port; port="$(awk -F= '/^RPC_PORT=/{print $2}' "$ROOT/$node.env")"
  curl -sS "http://127.0.0.1:$port/status"
}

cmd_logs() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: logs NODE [...]"
  shift
  compose "$node" logs -f "$@"
}

# Restart a node that already exists. bootstrap cannot do this: it runs
# install-genesis, and a home that has produced blocks refuses with
#   ValueError: validator home has already created runtime state
# which is correct -- re-installing genesis under a live chain is how you lose it.
# So a stopped node had no way back other than driving compose by hand, which is
# exactly the moment someone reaches for --force and destroys the chain.
#
# Nothing here touches genesis or the validator home. The state is bind-mounted
# under $ROOT, so a node comes back at the height it stopped at.
cmd_up() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: up NODE"
  shift
  [ -f "$ROOT/$node.env" ] || die \
"no env for '$node' at $ROOT/$node.env.
       'up' restarts a node that already exists; a new one needs bootstrap or join."
  # The P2P network is not recreated by compose and disappears with the daemon.
  local egress; egress="$(resolve_egress "$(grep -m1 '^PERSISTENT_PEERS=' "$ROOT/$node.env" | cut -d= -f2-)")"
  ensure_p2p_network "$egress"
  compose "$node" up -d "$@"
  echo "started $node — RPC: http://127.0.0.1:$(grep -m1 '^RPC_PORT=' "$ROOT/$node.env" | cut -d= -f2-)/status"
}

cmd_restart() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: restart NODE"
  cmd_down "$node"
  cmd_up "$node"
}

cmd_down() {
  local node="${1:-}"; [ -n "$node" ] || die "usage: down NODE [-v]"
  shift
  compose "$node" down "$@"
}

# ---- dispatch ---------------------------------------------------------------
SUBCMD="${1:-}"; [ $# -gt 0 ] && shift || true
case "$SUBCMD" in
  build)     cmd_build "$@";;
  bootstrap) cmd_bootstrap "$@";;
  join)      cmd_join "$@";;
  node-id)   cmd_node_id "$@";;
  status)    cmd_status "$@";;
  logs)      cmd_logs "$@";;
  up)        cmd_up "$@";;
  restart)   cmd_restart "$@";;
  down)      cmd_down "$@";;
  ""|-h|--help) usage;;
  *) die "unknown subcommand: $SUBCMD (try --help)";;
esac
