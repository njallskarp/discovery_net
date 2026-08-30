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

MODE="automatic"
if [[ "${1:-}" == "--no-inspector" || "${1:-}" == "--node-only" ]]; then
  MODE="no-inspector"
  shift
elif [[ "${1:-}" == "--with-inspector" || "${1:-}" == "--full" ]]; then
  MODE="with-inspector"
  shift
elif [[ "${1:-}" == --* ]]; then
  echo "error: usage: deploy.sh [--no-inspector|--with-inspector] [ENV_FILE]" >&2
  exit 1
fi
readonly MODE
readonly ENV_FILE="${1:-/etc/discovery-net/node.env}"
readonly INFRA_ENV_FILE="${INFRA_ENV_FILE:-/etc/discovery-net/infra.env}"
if (( $# > 1 )); then
  echo "error: usage: deploy.sh [--no-inspector|--with-inspector] [ENV_FILE]" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "error: run as root" >&2
  exit 1
fi

metadata_value() {
  local key="$1"
  curl --fail --silent --show-error --max-time 5 \
    --header 'Metadata-Flavor: Google' \
    "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$key"
}

refresh_infra_env() {
  local temporary_file
  local enabled
  local address
  local tls_mode
  local acme_email
  enabled="$(metadata_value discovery-net-inspector-enabled)"
  address="$(metadata_value discovery-net-inspector-address)"
  tls_mode="$(metadata_value discovery-net-inspector-tls-mode)"
  acme_email="$(metadata_value discovery-net-acme-email)"
  temporary_file="$(mktemp /etc/discovery-net/infra.env.XXXXXX)"
  chmod 0600 "$temporary_file"
  {
    printf 'INSPECTOR_ENABLED=%s\n' "$enabled"
    printf 'INSPECTOR_ADDRESS=%s\n' "$address"
    printf 'INSPECTOR_TLS_MODE=%s\n' "$tls_mode"
    printf 'ACME_EMAIL=%s\n' "$acme_email"
  } > "$temporary_file"
  mv -f "$temporary_file" "$INFRA_ENV_FILE"
}

if [[ "$INFRA_ENV_FILE" == "/etc/discovery-net/infra.env" ]]; then
  refresh_infra_env
fi

validate_env_file() {
  local path="$1"
  local file_mode
  if [[ ! -f "$path" ]]; then
    echo "error: environment file not found: $path" >&2
    exit 1
  fi
  if [[ "$(stat -c '%u' "$path")" -ne 0 ]]; then
    echo "error: environment file must be owned by root: $path" >&2
    exit 1
  fi
  file_mode="$(stat -c '%a' "$path")"
  if (( (8#$file_mode & 077) != 0 )); then
    echo "error: environment file must not be accessible by group or other: $path" >&2
    exit 1
  fi
}

validate_env_file "$ENV_FILE"
validate_env_file "$INFRA_ENV_FILE"
if findmnt -rn /srv/discovery-net >/dev/null 2>&1; then
  :
else
  echo "error: /srv/discovery-net is not a mounted persistent disk" >&2
  exit 1
fi

env_value() {
  local path="$1"
  local key="$2"
  local value
  value="$(sed -n "s/^$key=//p" "$path")"
  if [[ -z "$value" || "$value" == *$'\n'* ]]; then
    echo "error: $key must appear exactly once with a non-empty value in $path" >&2
    exit 1
  fi
  printf '%s' "$value"
}

GENESIS_FILE="$(env_value "$ENV_FILE" GENESIS_FILE)"
readonly GENESIS_FILE
GENESIS_SHA256="$(env_value "$ENV_FILE" GENESIS_SHA256)"
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

INSPECTOR_ENABLED="$(env_value "$INFRA_ENV_FILE" INSPECTOR_ENABLED)"
readonly INSPECTOR_ENABLED
if [[ "$INSPECTOR_ENABLED" != "true" && "$INSPECTOR_ENABLED" != "false" ]]; then
  echo "error: INSPECTOR_ENABLED must be true or false" >&2
  exit 1
fi

START_INSPECTOR="$INSPECTOR_ENABLED"
if [[ "$MODE" == "no-inspector" ]]; then
  START_INSPECTOR="false"
elif [[ "$MODE" == "with-inspector" ]]; then
  if [[ "$INSPECTOR_ENABLED" != "true" ]]; then
    echo "error: Terraform has disabled the inspector firewall; set enable_inspector=true first" >&2
    exit 1
  fi
  START_INSPECTOR="true"
fi
readonly START_INSPECTOR

if [[ "$START_INSPECTOR" == "true" ]]; then
  INSPECTOR_ADDRESS="$(env_value "$INFRA_ENV_FILE" INSPECTOR_ADDRESS)"
  readonly INSPECTOR_ADDRESS
  INSPECTOR_TLS_MODE="$(env_value "$INFRA_ENV_FILE" INSPECTOR_TLS_MODE)"
  readonly INSPECTOR_TLS_MODE
  ACME_EMAIL="$(env_value "$INFRA_ENV_FILE" ACME_EMAIL)"
  readonly ACME_EMAIL
  if [[ "$INSPECTOR_TLS_MODE" == "ip" ]]; then
    python3 -c '
import ipaddress
import sys

address = ipaddress.ip_address(sys.argv[1])
if address.version != 4 or not address.is_global:
    raise SystemExit("INSPECTOR_ADDRESS must be a public IPv4 address in ip mode")
' "$INSPECTOR_ADDRESS"
  elif [[ "$INSPECTOR_TLS_MODE" == "hostname" ]]; then
    if [[ ! "$INSPECTOR_ADDRESS" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])$ \
      || "$INSPECTOR_ADDRESS" != *.* \
      || "$INSPECTOR_ADDRESS" == *..* ]]; then
      echo "error: INSPECTOR_ADDRESS must be a DNS hostname in hostname mode" >&2
      exit 1
    fi
  else
    echo "error: INSPECTOR_TLS_MODE must be ip or hostname" >&2
    exit 1
  fi
  if [[ ! "$ACME_EMAIL" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    echo "error: ACME_EMAIL must be a valid contact address" >&2
    exit 1
  fi
fi

docker network inspect discovery-net-p2p >/dev/null 2>&1 \
  || docker network create --internal discovery-net-p2p

compose() {
  docker compose \
    --env-file "$ENV_FILE" \
    --env-file "$INFRA_ENV_FILE" \
    -f "$BASE_COMPOSE" \
    -f "$CLOUD_COMPOSE" \
    "$@"
}

compose config --quiet
compose build --pull application cometbft
if [[ "$START_INSPECTOR" == "false" ]]; then
  compose up -d --remove-orphans application cometbft rpc p2p-gateway
else
  compose up -d --remove-orphans
fi
compose ps
