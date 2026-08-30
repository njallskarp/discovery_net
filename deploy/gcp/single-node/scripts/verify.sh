#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIRECTORY
readonly RPC_URL="${RPC_URL:-http://127.0.0.1:26657}"
readonly INFRA_ENV_FILE="${INFRA_ENV_FILE:-/etc/discovery-net/infra.env}"

MODE="automatic"
if [[ "${1:-}" == "--no-inspector" ]]; then
  MODE="no-inspector"
  shift
elif [[ "${1:-}" == --* ]]; then
  echo "error: usage: verify.sh [--no-inspector]" >&2
  exit 1
fi
if (( $# != 0 )); then
  echo "error: usage: verify.sh [--no-inspector]" >&2
  exit 1
fi

env_value() {
  local key="$1"
  local value
  value="$(sed -n "s/^$key=//p" "$INFRA_ENV_FILE")"
  if [[ -z "$value" || "$value" == *$'\n'* ]]; then
    echo "error: $key must appear exactly once in $INFRA_ENV_FILE" >&2
    exit 1
  fi
  printf '%s' "$value"
}

STATUS="$(curl --fail --silent --show-error --max-time 15 "$RPC_URL/status")"
readonly STATUS
printf '%s' "$STATUS" | python3 -c '
import json
import sys

result = json.load(sys.stdin)["result"]
print(
    "RPC healthy: node_id={id} height={height} catching_up={catching_up} "
    "voting_power={voting_power}".format(
        id=result["node_info"]["id"],
        height=result["sync_info"]["latest_block_height"],
        catching_up=result["sync_info"]["catching_up"],
        voting_power=result["validator_info"]["voting_power"],
    )
)
'

RPC_LISTENERS="$(ss -H -ltn 'sport = :26657' | awk '{print $4}')"
readonly RPC_LISTENERS
if [[ -z "$RPC_LISTENERS" ]]; then
  echo "error: RPC responded but no host listener was found on port 26657" >&2
  exit 1
fi
while IFS= read -r listener; do
  if [[ "$listener" != 127.0.0.1:26657 && "$listener" != \[::1\]:26657 ]]; then
    echo "error: RPC is not loopback-only: $listener" >&2
    exit 1
  fi
done <<< "$RPC_LISTENERS"

for internal_port in 26658 8765; do
  if ss -H -ltn "sport = :$internal_port" | grep -q .; then
    echo "error: internal port is exposed on the host: $internal_port" >&2
    exit 1
  fi
done
printf 'Internal ports closed: 26658, 8765; RPC loopback-only: 26657\n'

if [[ "$MODE" == "no-inspector" ]]; then
  printf 'Inspector check disabled explicitly.\n'
  exit 0
fi
if [[ ! -f "$INFRA_ENV_FILE" ]]; then
  echo "error: infrastructure environment file not found: $INFRA_ENV_FILE" >&2
  exit 1
fi

INSPECTOR_ENABLED="$(env_value INSPECTOR_ENABLED)"
readonly INSPECTOR_ENABLED
if [[ "$INSPECTOR_ENABLED" == "false" ]]; then
  printf 'Inspector disabled by Terraform.\n'
  exit 0
fi
if [[ "$INSPECTOR_ENABLED" != "true" ]]; then
  echo "error: INSPECTOR_ENABLED must be true or false" >&2
  exit 1
fi

INSPECTOR_ADDRESS="$(env_value INSPECTOR_ADDRESS)"
readonly INSPECTOR_ADDRESS
INSPECTOR_TLS_MODE="$(env_value INSPECTOR_TLS_MODE)"
readonly INSPECTOR_TLS_MODE
readonly INSPECTOR_URL="https://$INSPECTOR_ADDRESS"
readonly CONNECT_RULE="$INSPECTOR_ADDRESS:443:127.0.0.1:443"

REDIRECT="$(
  curl --silent --show-error --max-time 10 \
    --output /dev/null \
    --write-out '%{http_code} %{redirect_url}' \
    --header "Host: $INSPECTOR_ADDRESS" \
    http://127.0.0.1/
)"
readonly REDIRECT
if [[ "$REDIRECT" != "308 $INSPECTOR_URL/" ]]; then
  echo "error: HTTP did not redirect to the expected HTTPS URL: $REDIRECT" >&2
  exit 1
fi

HEADERS="$(
  curl --silent --show-error --fail --max-time 15 \
    --connect-to "$CONNECT_RULE" \
    --dump-header - \
    --output /dev/null \
    "$INSPECTOR_URL/api/node"
)"
readonly HEADERS
for required_header in \
  'strict-transport-security: max-age=31536000' \
  "content-security-policy: default-src 'none'" \
  'x-content-type-options: nosniff' \
  'x-frame-options: DENY' \
  'referrer-policy: no-referrer'; do
  if ! printf '%s\n' "$HEADERS" | grep -Fqi "$required_header"; then
    echo "error: missing HTTPS response header: $required_header" >&2
    exit 1
  fi
done

for method in POST PUT PATCH DELETE OPTIONS; do
  code="$(
    curl --silent --show-error --max-time 10 \
      --connect-to "$CONNECT_RULE" \
      --request "$method" \
      --output /dev/null \
      --write-out '%{http_code}' \
      "$INSPECTOR_URL/api/node"
  )"
  if [[ "$code" != "405" ]]; then
    echo "error: $method was not rejected by the public inspector: HTTP $code" >&2
    exit 1
  fi
done

for blocked_path in /status '/broadcast_tx_commit?tx=00' /admin; do
  code="$(
    curl --silent --show-error --max-time 10 \
      --connect-to "$CONNECT_RULE" \
      --output /dev/null \
      --write-out '%{http_code}' \
      "$INSPECTOR_URL$blocked_path"
  )"
  if [[ "$code" != "404" ]]; then
    echo "error: unintended route was not blocked: $blocked_path returned HTTP $code" >&2
    exit 1
  fi
done

python3 "$SCRIPT_DIRECTORY/check-inspector-certificate.py" \
  --expected-address "$INSPECTOR_ADDRESS" \
  --connect-host 127.0.0.1 \
  --minimum-valid-seconds 86400 \
  --tls-mode "$INSPECTOR_TLS_MODE"

printf 'Inspector healthy and read-only: %s/\n' "$INSPECTOR_URL"
