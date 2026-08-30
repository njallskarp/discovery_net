#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIRECTORY
DEPLOY_DIRECTORY="$(cd -- "$SCRIPT_DIRECTORY/.." && pwd)"
readonly DEPLOY_DIRECTORY
REPOSITORY_ROOT="$(cd -- "$DEPLOY_DIRECTORY/../../.." && pwd)"
readonly REPOSITORY_ROOT
readonly BASE_COMPOSE="$REPOSITORY_ROOT/localnet/compose.yaml"
readonly CLOUD_COMPOSE="$DEPLOY_DIRECTORY/compose.cloud.yaml"
readonly SOURCE_NODE_KEY="${1:?usage: prepare-p2p-identity.sh STAGED_NODE_KEY [ENV_FILE]}"
readonly ENV_FILE="${2:-/etc/discovery-net/node.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "error: run as root" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" || -L "$ENV_FILE" ]]; then
  echo "error: environment file must be a regular file: $ENV_FILE" >&2
  exit 1
fi
if [[ "$(stat -c '%u' "$ENV_FILE")" -ne 0 ]]; then
  echo "error: environment file must be owned by root: $ENV_FILE" >&2
  exit 1
fi
ENV_MODE="$(stat -c '%a' "$ENV_FILE")"
readonly ENV_MODE
if (( (8#$ENV_MODE & 077) != 0 )); then
  echo "error: environment file must not be accessible by group or other: $ENV_FILE" >&2
  exit 1
fi
if [[ ! -f "$SOURCE_NODE_KEY" || -L "$SOURCE_NODE_KEY" ]]; then
  echo "error: staged P2P node key must be a regular file" >&2
  exit 1
fi
SOURCE_MODE="$(stat -c '%a' "$SOURCE_NODE_KEY")"
readonly SOURCE_MODE
if (( (8#$SOURCE_MODE & 077) != 0 )); then
  echo "error: staged P2P node key must have mode 0600" >&2
  exit 1
fi

env_value() {
  local key="$1"
  local value
  value="$(sed -n "s/^$key=//p" "$ENV_FILE")"
  if [[ -z "$value" || "$value" == *$'\n'* ]]; then
    echo "error: $key must appear exactly once in $ENV_FILE" >&2
    exit 1
  fi
  printf '%s' "$value"
}

readonly IMAGE="$(env_value DISCOVERY_NET_IMAGE)"
readonly SERVICE_UID="$(env_value DISCOVERY_NET_UID)"
readonly SERVICE_GID="$(env_value DISCOVERY_NET_GID)"
readonly COMETBFT_DATA_DIRECTORY="$(env_value COMETBFT_DATA_DIRECTORY)"
readonly GENESIS_FILE="$(env_value GENESIS_FILE)"
readonly GENESIS_SHA256="$(env_value GENESIS_SHA256)"
readonly HOME_DIRECTORY="$COMETBFT_DATA_DIRECTORY/cometbft"

if [[ ! "$SERVICE_UID" =~ ^[0-9]+$ || ! "$SERVICE_GID" =~ ^[0-9]+$ ]]; then
  echo "error: service UID and GID must be decimal integers" >&2
  exit 1
fi
if [[ "$COMETBFT_DATA_DIRECTORY" != /srv/discovery-net/* ]]; then
  echo "error: COMETBFT_DATA_DIRECTORY must be below /srv/discovery-net" >&2
  exit 1
fi
if [[ -e "$HOME_DIRECTORY" ]]; then
  echo "error: refusing to replace an existing CometBFT home: $HOME_DIRECTORY" >&2
  exit 1
fi
if [[ ! -f "$GENESIS_FILE" || ! "$GENESIS_SHA256" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "error: trusted genesis file or SHA-256 is invalid" >&2
  exit 1
fi
printf '%s  %s\n' "$GENESIS_SHA256" "$GENESIS_FILE" | sha256sum --check --status

python3 - "$SOURCE_NODE_KEY" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    document = json.loads(path.read_bytes())
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"error: staged P2P node key is invalid JSON: {error}") from error
private_key = document.get("priv_key") if isinstance(document, dict) else None
if not isinstance(private_key, dict):
    raise SystemExit("error: staged P2P node key has no private key object")
if not all(isinstance(private_key.get(field), str) for field in ("type", "value")):
    raise SystemExit("error: staged P2P private key is malformed")
PY

compose() {
  docker compose \
    --env-file "$ENV_FILE" \
    -f "$BASE_COMPOSE" \
    -f "$CLOUD_COMPOSE" \
    "$@"
}

if [[ -n "$(compose ps --status running -q cometbft)" ]]; then
  echo "error: stop the cloud CometBFT service before preparing its identity" >&2
  exit 1
fi

compose config --quiet
compose build --pull cometbft
install -d -o "$SERVICE_UID" -g "$SERVICE_GID" -m 0750 "$COMETBFT_DATA_DIRECTORY"

readonly STAGING_DIRECTORY="$COMETBFT_DATA_DIRECTORY/.cometbft.prepare.$$"
cleanup() {
  rm -rf -- "$STAGING_DIRECTORY"
}
trap cleanup EXIT

docker run --rm --network none \
  --user "$SERVICE_UID:$SERVICE_GID" \
  --mount "type=bind,source=$COMETBFT_DATA_DIRECTORY,target=/var/lib/discovery-net" \
  "$IMAGE" \
  cometbft init --home "/var/lib/discovery-net/$(basename "$STAGING_DIRECTORY")"

install -o "$SERVICE_UID" -g "$SERVICE_GID" -m 0440 \
  "$GENESIS_FILE" "$STAGING_DIRECTORY/config/genesis.json"
install -o "$SERVICE_UID" -g "$SERVICE_GID" -m 0600 \
  "$SOURCE_NODE_KEY" "$STAGING_DIRECTORY/config/node_key.json"
chmod 0600 \
  "$STAGING_DIRECTORY/config/priv_validator_key.json" \
  "$STAGING_DIRECTORY/data/priv_validator_state.json"

python3 - \
  "$STAGING_DIRECTORY/config/priv_validator_key.json" \
  "$GENESIS_FILE" <<'PY'
import json
import pathlib
import sys

validator_key = json.loads(pathlib.Path(sys.argv[1]).read_bytes())["pub_key"]
genesis = json.loads(pathlib.Path(sys.argv[2]).read_bytes())
if any(validator.get("pub_key") == validator_key for validator in genesis.get("validators", [])):
    raise SystemExit("error: generated validator key unexpectedly belongs to the genesis set")
PY

NODE_ID="$(
  docker run --rm --network none \
    --user "$SERVICE_UID:$SERVICE_GID" \
    --mount "type=bind,source=$COMETBFT_DATA_DIRECTORY,target=/var/lib/discovery-net" \
    "$IMAGE" \
    cometbft show-node-id --home "/var/lib/discovery-net/$(basename "$STAGING_DIRECTORY")"
)"
readonly NODE_ID
if [[ ! "$NODE_ID" =~ ^[[:xdigit:]]{40}$ ]]; then
  echo "error: CometBFT returned an invalid P2P node ID" >&2
  exit 1
fi

mv "$STAGING_DIRECTORY" "$HOME_DIRECTORY"
trap - EXIT
printf 'Prepared non-validator P2P identity: %s\n' "$NODE_ID"
