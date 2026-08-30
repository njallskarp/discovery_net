#!/usr/bin/env bash
set -euo pipefail

readonly RPC_URL="${RPC_URL:-http://127.0.0.1:26657}"
readonly INSPECTOR_URL="${INSPECTOR_URL:-}"

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

if [[ -n "$INSPECTOR_URL" ]]; then
  curl --fail --silent --show-error --max-time 10 "$INSPECTOR_URL/api/node" >/dev/null
  printf 'Inspector healthy: %s\n' "$INSPECTOR_URL"
else
  printf 'Inspector check skipped; INSPECTOR_URL is unset.\n'
fi
