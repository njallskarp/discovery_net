#!/usr/bin/env bash
set -euo pipefail

readonly RPC_URL="${RPC_URL:-http://127.0.0.1:26657}"
readonly INSPECTOR_URL="${INSPECTOR_URL:?Set INSPECTOR_URL to the public HTTPS URL}"

curl --fail --silent --show-error --max-time 5 "$RPC_URL/status" >/dev/null
curl --fail --silent --show-error --max-time 10 "$INSPECTOR_URL/api/node" >/dev/null
printf 'RPC and inspector are healthy.\n'
