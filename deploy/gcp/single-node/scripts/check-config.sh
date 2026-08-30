#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIRECTORY
DEPLOY_DIRECTORY="$(cd -- "$SCRIPT_DIRECTORY/.." && pwd)"
readonly DEPLOY_DIRECTORY
REPOSITORY_ROOT="$(cd -- "$DEPLOY_DIRECTORY/../../.." && pwd)"
readonly REPOSITORY_ROOT
readonly TERRAFORM_DIRECTORY="$DEPLOY_DIRECTORY/terraform"
readonly CADDY_IMAGE="caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d"

terraform -chdir="$TERRAFORM_DIRECTORY" fmt -check
terraform -chdir="$TERRAFORM_DIRECTORY" init -backend=false -input=false >/dev/null
terraform -chdir="$TERRAFORM_DIRECTORY" validate

docker compose \
  --env-file "$DEPLOY_DIRECTORY/node.env.example" \
  --env-file "$DEPLOY_DIRECTORY/infra.env.example" \
  -f "$REPOSITORY_ROOT/localnet/compose.yaml" \
  -f "$DEPLOY_DIRECTORY/compose.cloud.yaml" \
  config --format json \
  | python3 "$SCRIPT_DIRECTORY/check-compose-security.py"

if [[ "$(docker run --rm "$CADDY_IMAGE" caddy version | awk '{print $1}')" != "v2.10.2" ]]; then
  echo "error: pinned Caddy image is not version 2.10.2" >&2
  exit 1
fi
BUILD_INFO="$(docker run --rm "$CADDY_IMAGE" caddy build-info)"
readonly BUILD_INFO
for dependency in \
  $'github.com/caddyserver/caddy/v2\tv2.10.2' \
  $'github.com/caddyserver/certmagic\tv0.24.0' \
  $'github.com/mholt/acmez/v3\tv3.1.2'; do
  if ! printf '%s\n' "$BUILD_INFO" | grep -Fq "$dependency"; then
    echo "error: pinned Caddy build is missing dependency: $dependency" >&2
    exit 1
  fi
done

for mode in ip hostname; do
  if [[ "$mode" == "ip" ]]; then
    address="203.0.113.30"
  else
    address="inspector.example.com"
  fi
  docker run --rm \
    --env ACME_EMAIL=operator@example.com \
    --env INSPECTOR_ADDRESS="$address" \
    --env INSPECTOR_TLS_MODE="$mode" \
    --volume "$DEPLOY_DIRECTORY/Caddyfile:/etc/caddy/Caddyfile:ro" \
    "$CADDY_IMAGE" \
    caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile \
    | python3 "$SCRIPT_DIRECTORY/check-caddy-config.py" \
      --mode "$mode" --address "$address"
done

python3 -m py_compile \
  "$SCRIPT_DIRECTORY/check-caddy-config.py" \
  "$SCRIPT_DIRECTORY/check-compose-security.py" \
  "$SCRIPT_DIRECTORY/check-inspector-certificate.py"
bash -n \
  "$SCRIPT_DIRECTORY/deploy.sh" \
  "$SCRIPT_DIRECTORY/prepare-p2p-identity.sh" \
  "$SCRIPT_DIRECTORY/verify.sh"

printf 'GCP single-node deployment contract valid.\n'
