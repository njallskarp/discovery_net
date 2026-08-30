# Single-node Google Cloud deployment

This deployment creates one non-validator Discovery Net node with:

- an `e2-small` VM, static IPv4, and persistent data disk;
- P2P port `26656` restricted to trusted public `/32` addresses;
- RPC bound to VM loopback and reached through Google IAP;
- a public, GET-only inspector on HTTPS by default, with an explicit disable switch;
- daily data-disk snapshots retained for seven days;
- unattended package security updates.

The ledger is derived from committed blocks. A new node can rebuild it by syncing the same
chain; do not copy a ledger database merely to move compute. This deployment does not add a
validator. Its generated validator key must have voting power zero.

| Port | Access | Destination |
|---|---|---|
| `80`, `443` | Public, when enabled | Caddy, then the GET-only inspector |
| `26656` | Trusted `/32` CIDRs | P2P gateway, then CometBFT |
| `22` | Google IAP only | OS Login SSH |
| `26657` | VM loopback only | Read and transaction-broadcast RPC |
| `26658`, `8765` | Container networks only | ABCI and inspector |

The default inspector URL is `https://STATIC_PUBLIC_IP/`; DNS is not required. Caddy 2.10.2
uses Let's Encrypt's `shortlived` profile for the public IPv4 certificate and automatically
renews the roughly six-day certificate. Supplying `inspector_hostname` switches to normal
hostname certificate issuance. Let's Encrypt is the only configured issuer: failed issuance
never falls back to HTTP, another CA, or a self-signed certificate.

The proxy permits GET only on the inspector's audited UI/API path allowlist. It rejects RPC,
broadcast, administration, and unknown paths. The inspector opens SQLite read-only; the
inspector, proxy, and certificate monitor receive no P2P, validator, or contributor keys or
node state. The UI exposes public graph data, signer public keys, and node/peer metadata.

## Runtime policy

The cloud overlay owns the complete production command so local testing defaults cannot leak
into this deployment.

| Setting | Cloud value | Reason |
|---|---|---|
| Peer exchange | enabled | Discover other reachable peers after bootstrap |
| Strict address book | enabled | Reject private or unroutable advertised addresses |
| Duplicate peer IPs | enabled | The P2P proxy gives inbound peers one container source IP; the GCP firewall still enforces approved public `/32` sources |
| Empty blocks | disabled | Avoid blocks without transactions |
| RPC unsafe methods, CORS, gRPC, pprof | disabled | Enforced by the launcher |

The Docker networks have distinct jobs:

| Network | Purpose |
|---|---|
| `private` | Internal ABCI and CometBFT RPC traffic |
| `p2p` | Internal CometBFT-to-P2P-gateway traffic |
| `p2p-edge` | P2P gateway ingress and CometBFT outbound peer dialing |
| `edge` | VM-loopback RPC publishing and inspector-to-Caddy traffic |

No container port is public unless Compose explicitly publishes it. The RPC proxy needs both
`private` and `edge`; without `edge`, Docker records the binding but cannot route it.
CometBFT needs `p2p-edge` to dial public persistent peers.

## 1. Provision Google Cloud

Prerequisites: Terraform, `gcloud`, a billing account, the trusted genesis and SHA-256, at
least one trusted peer public egress IP, and an IAM user or group for operations.

Create a dedicated project if one does not already exist:

```bash
gcloud projects create PROJECT_ID --name='Discovery Net node'
gcloud billing projects link PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
gcloud auth application-default login
gcloud config set project PROJECT_ID
```

Create the ignored local values file:

```bash
cd deploy/gcp/single-node/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set `project_id`, `name`, `operator_members`, `acme_email`, and one public IPv4 `/32` for
every peer or trusted NAT egress address. Leave `inspector_hostname = ""` to use the static
public IP directly. Do not use private, Tailscale, or changing client addresses unless that
is intentionally the peer's stable public egress.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
terraform output inspector_url
```

To disable the public inspector and its firewall rule, set `enable_inspector = false` before
applying. Terraform writes the chosen address, certificate mode, and enable state to instance
metadata. The idempotent deploy command refreshes its root-only infrastructure environment
from that metadata each run.

On a brand-new project, Google APIs can remain unavailable briefly after their enable calls
complete. If the first apply reports `SERVICE_DISABLED`, `accessNotConfigured`, or an API
403, wait 30–60 seconds, run a new `terraform plan`, and apply it. Terraform is idempotent;
do not delete the project or already-created resources.

Terraform state contains infrastructure identifiers and is required for safe future changes.
It is ignored by Git. Preserve it in an approved encrypted location or configure an approved
remote backend before multiple operators manage the node.

The instance and data disk have deletion protection. Intentional deletion requires a reviewed
change to both the instance deletion-protection setting and the disk `prevent_destroy` rule.

## 2. Stage reviewed source and trusted genesis

Use the `iap_ssh_command` output and confirm bootstrap:

```bash
sudo systemctl status google-startup-scripts.service --no-pager
sudo findmnt /srv/discovery-net
sudo docker version
```

Do not put a GitHub token or SSH key on the VM. A public checkout is acceptable, but an archive
of the exact reviewed commit works for public and private repositories. From a trusted checkout:

```bash
git archive --format=tar --output=/tmp/discovery-net.tar REVIEWED_COMMIT
printf '%s\n' REVIEWED_COMMIT > /tmp/discovery-net.revision
gcloud compute scp --project PROJECT_ID --zone ZONE --tunnel-through-iap \
  /tmp/discovery-net.tar /tmp/discovery-net.revision NODE_NAME:/tmp/
rm /tmp/discovery-net.tar /tmp/discovery-net.revision
```

On the VM:

```bash
sudo install -d -o root -g root -m 0755 /opt/discovery-net
sudo tar -xf /tmp/discovery-net.tar -C /opt/discovery-net
sudo install -o root -g root -m 0444 \
  /tmp/discovery-net.revision /opt/discovery-net/.source-revision
rm /tmp/discovery-net.tar /tmp/discovery-net.revision
```

Copy the trusted genesis through IAP, then install it read-only for the service account:

```bash
gcloud compute scp --project PROJECT_ID --zone ZONE --tunnel-through-iap \
  ./genesis.json NODE_NAME:/tmp/genesis.json
gcloud compute ssh NODE_NAME --project PROJECT_ID --zone ZONE \
  --tunnel-through-iap --command \
  'sudo install -o 10001 -g 10001 -m 0440 /tmp/genesis.json /srv/discovery-net/genesis.json && rm /tmp/genesis.json'
```

Create the root-only configuration:

```bash
sudo cp /opt/discovery-net/deploy/gcp/single-node/node.env.example \
  /etc/discovery-net/node.env
sudo chown root:root /etc/discovery-net/node.env
sudo chmod 0600 /etc/discovery-net/node.env
sudoedit /etc/discovery-net/node.env
```

Set these values exactly:

- tag `DISCOVERY_NET_IMAGE` with the reviewed commit;
- set `CHAIN_ID` and `GENESIS_SHA256` from the trusted genesis;
- set `P2P_ADVERTISED_ENDPOINT` to `PUBLIC_IP:26656`;
- list reachable public `node-id@ip:26656` values in `PERSISTENT_PEERS`;
- do not copy Terraform-managed inspector settings into `node.env`.

`PERSISTENT_PEERS` may be empty for the first node when every existing peer is behind NAT.
In that case, an allowlisted existing peer must dial this node after it starts.

## 3. Choose the P2P identity

For a new identity, skip this section. The launcher creates a complete CometBFT home and a new
non-validator identity on first start.

To retain a stopped node's P2P node ID, migrate only its `config/node_key.json`. Never copy
`priv_validator_key.json`, `priv_validator_state.json`, the ledger, or CometBFT block state.
The source and cloud nodes must never run concurrently with the same P2P key.

While the source node is still available but before the cloud node starts, copy its node key
through IAP without printing it:

```bash
gcloud compute scp --project PROJECT_ID --zone ZONE --tunnel-through-iap \
  /LOCAL/COMETBFT/HOME/config/node_key.json NODE_NAME:/tmp/node_key.json
gcloud compute ssh NODE_NAME --project PROJECT_ID --zone ZONE \
  --tunnel-through-iap --command \
  'sudo install -o root -g root -m 0600 /tmp/node_key.json /tmp/staged-node-key.json && rm /tmp/node_key.json'
```

Prepare a complete home offline:

```bash
cd /opt/discovery-net
sudo deploy/gcp/single-node/scripts/prepare-p2p-identity.sh \
  /tmp/staged-node-key.json
sudo rm /tmp/staged-node-key.json
```

The script builds the reviewed image, initializes into an atomic staging directory with no
network, installs the trusted genesis and P2P key, retains a newly generated cloud validator
identity, verifies that validator is not in the genesis set, and prints only the public node
ID. Do not copy a node key into an otherwise empty home: an incomplete existing home fails
closed.

## 4. Configure the peer side

The GCP firewall admits P2P only from `trusted_p2p_cidrs`. The peer must also know the cloud
address. Append this value to the peer's persistent-peer configuration:

```text
CLOUD_NODE_ID@CLOUD_PUBLIC_IP:26656
```

If the existing peer is behind NAT, it initiates the connection to GCP; no home-router port
forward is required. If both nodes have public endpoints, either can dial. From an allowlisted
peer host, this should succeed after the cloud node starts:

```bash
nc -vz CLOUD_PUBLIC_IP 26656
```

## 5. Start and cut over

The normal idempotent command refreshes Terraform-managed inspector settings, builds the
reviewed image, and starts the node, loopback RPC, P2P gateway, inspector, HTTPS proxy, and
certificate monitor:

```bash
cd /opt/discovery-net
sudo deploy/gcp/single-node/scripts/deploy.sh
```

Initial HTTPS becomes available only after Let's Encrypt issues the trusted certificate.
Port 80 serves only the ACME challenge and HTTPS redirect. To suppress the inspector for one
run, use `--no-inspector`; to disable it persistently, set `enable_inspector = false`, apply
Terraform, then run the normal command again.

For a reused P2P identity, use this order:

1. Prepare the cloud identity offline and record its node ID.
2. Stop the source node without deleting its bind-mounted data.
3. Run the normal deploy command; use `--no-inspector` only when deliberately suppressing UI.
4. Restart or reconnect an allowlisted peer so it dials the cloud address.
5. Verify the peer ID, chain ID, and zero voting power.

If cutover fails, leave the source stopped while collecting evidence. Do not automatically
restart it: first stop the cloud CometBFT service or otherwise prove the cloud copy is offline.
Running both copies of one P2P identity creates duplicate-ID disconnects.

## 6. Verify and submit locally

On the VM:

```bash
cd /opt/discovery-net
sudo deploy/gcp/single-node/scripts/verify.sh
```

The verifier prints node ID, height, catch-up state, and voting power; proves RPC is
loopback-only; proves ports 26658/8765 are closed; checks HTTP-to-HTTPS redirection, the
public CA/SAN/expiry, required headers, allowed GET behavior, and rejection of writes, RPC,
broadcast, and administration paths. Use `verify.sh --no-inspector` only after intentionally
deploying without the inspector.

`catching_up=true` during first replay is expected and is not a deployment failure. On an
`e2-small`, application replay can make HTTP status requests slow; the production health
check tests the RPC TCP listener so active replay is not marked unhealthy.

Verify that an existing peer sees the cloud node:

```bash
curl -fsS http://127.0.0.1:26657/net_info \
  | jq -r '.result.peers[] | [.node_info.id,.node_info.moniker,.remote_ip,.is_outbound] | @tsv'
```

After catch-up, compare its height with a trusted peer and inspect the derived ledger:

```bash
sudo python3 - <<'PY'
import sqlite3

uri = "file:/srv/discovery-net/ledger-data/artifact-ledger.sqlite?mode=ro"
with sqlite3.connect(uri, uri=True) as connection:
    height = connection.execute(
        "SELECT committed_height FROM artifact_ledger_state WHERE singleton = 1"
    ).fetchone()[0]
    entries = connection.execute("SELECT count(*) FROM artifact_ledger_entries").fetchone()[0]
print(f"ledger_height={height} entries={entries}")
PY
```

Open the private RPC tunnel using the Terraform `rpc_tunnel_command`. Local agents can submit
through the existing CLI while the contributor key remains local:

```bash
discovery-net submit contribution \
  --private-key /LOCAL/PATH/contributor.pem \
  --rpc-url http://127.0.0.1:26657 \
  --kind finding \
  --title 'Title' \
  --body 'Body'
```

Only the signed transaction crosses the IAP tunnel.

## Troubleshooting

| Symptom | Cause and action |
|---|---|
| First Terraform apply returns API 403 | Fresh-project API propagation. Wait 30–60 seconds, re-plan, and re-apply. |
| VM cannot clone the repository | Do not install GitHub credentials. Transfer `git archive` for the reviewed commit through IAP. |
| Launcher reports an incomplete CometBFT home | A key was copied into an empty home. Remove only the unstarted partial home after verifying its exact path, then use `prepare-p2p-identity.sh`. Never delete a started home as a repair. |
| Peer reports duplicate/self node ID | Both copies of a migrated P2P key are running. Stop one immediately. |
| Cloud logs `network is unreachable` for a public peer | The CometBFT service lacks `p2p-edge` or the deployed overlay is stale. Update and recreate CometBFT. |
| Cloud has no peers | Check the GCP `/32`, the peer's actual public egress IP, both node IDs, the peer's persistent-peer list, and port `26656`. A NAT peer must dial outbound. |
| RPC binding exists but `curl 127.0.0.1:26657/status` fails | The RPC proxy lacks `edge` or is stale. Check `docker compose config`, recreate `rpc`, and confirm `ss -ltnp` shows loopback only. |
| CometBFT is marked unhealthy while blocks execute | An older overlay used a 2-second HTTP health probe. Deploy the TCP-listener health check in the current overlay. |
| Caddy cannot obtain the IP certificate | Confirm `INSPECTOR_TLS_MODE=ip` in `/etc/discovery-net/infra.env`, the address equals `terraform output -raw public_ip`, ports 80/443 are reachable, and the VM clock is correct. Inspect Caddy logs; do not enable HTTP or a self-signed fallback. |
| Caddy cannot obtain a hostname certificate | Confirm the hostname resolves only to the static IP and ports 80/443 are reachable. Inspect Caddy logs. |
| `inspector-cert-monitor` is unhealthy | Run `verify.sh`, then inspect Caddy and monitor logs. Fewer than 24 hours remaining is a renewal failure; preserve `/srv/discovery-net/caddy-data` and fix ACME reachability before expiry. |
| Ledger height trails CometBFT | The application is still replaying committed blocks. Do not copy or edit the SQLite database. |

## Operations

```bash
# Service status
sudo docker compose --env-file /etc/discovery-net/node.env \
  --env-file /etc/discovery-net/infra.env \
  -f localnet/compose.yaml -f deploy/gcp/single-node/compose.cloud.yaml ps

# Recent logs
sudo docker compose --env-file /etc/discovery-net/node.env \
  --env-file /etc/discovery-net/infra.env \
  -f localnet/compose.yaml -f deploy/gcp/single-node/compose.cloud.yaml \
  logs --tail=200

# Re-run all source-only Terraform, Compose, and Caddy policy checks
deploy/gcp/single-node/scripts/check-config.sh

# Update trusted peer IPs from the operator checkout
cd deploy/gcp/single-node/terraform
terraform plan -out=tfplan && terraform apply tfplan
```

The pinned Caddy image reports Caddy 2.10.2, CertMagic 0.24.0, and acmez 3.1.2. This exact
combination supports Let's Encrypt IPv4 identifiers and ACME profiles, so Certbot is not
needed. References: [Let's Encrypt IP/short-lived GA](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability.html),
[profile definitions](https://letsencrypt.org/docs/profiles/), and
[Caddy 2.10 ACME profiles](https://github.com/caddyserver/caddy/releases/tag/v2.10.0).

Never expose ports `26657`, `26658`, or `8765`; run two nodes with one P2P key; copy a
validator key into this non-validator; or put private keys, ledger files, credentials,
Terraform state, or secrets in Git, Terraform variables, VM metadata, or Compose environment
files.
