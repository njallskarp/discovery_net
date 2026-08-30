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
readonly ENV_FILE="${1:-/etc/discovery-net/node.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "error: run as root" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: environment file not found: $ENV_FILE" >&2
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
if findmnt -rn /srv/discovery-net >/dev/null 2>&1; then
  :
else
  echo "error: /srv/discovery-net is not a mounted persistent disk" >&2
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

GENESIS_FILE="$(env_value GENESIS_FILE)"
readonly GENESIS_FILE
GENESIS_SHA256="$(env_value GENESIS_SHA256)"
readonly GENESIS_SHA256
if [[ ! "$GENESIS_SHA256" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "error: GENESIS_SHA256 must be exactly 64 hexadecimal characters" >&2
  exit 1
fi
if [[ ! -f "$GENESIS_FILE" ]]; then
  echo "error: genesis file not found: $GENESIS_FILE" >&2
  exit 1
fi
printf '%s  %s\n' "$GENESIS_SHA256" "$GENESIS_FILE" | sha256sum --check --status

docker network inspect discovery-net-p2p >/dev/null 2>&1 \
  || docker network create --internal discovery-net-p2p

compose() {
  docker compose \
    --env-file "$ENV_FILE" \
    -f "$BASE_COMPOSE" \
    -f "$CLOUD_COMPOSE" \
    "$@"
}

compose config --quiet
compose build --pull
compose up -d --remove-orphans
compose ps
