# Single-node Google Cloud deployment

This deployment creates one non-validator Discovery Net node with:

- an `e2-small` VM, static IPv4, and persistent data disk;
- P2P port `26656` restricted to trusted public IPs;
- public read-only inspector on HTTPS;
- RPC bound to VM loopback and reached through IAP;
- daily data-disk snapshots retained for seven days;
- unattended package security updates.

The node generates its own P2P identity on the data disk. Contributor keys, validator
keys, ledger databases, and Terraform state must not be committed or passed to Terraform.

| Port | Access | Destination |
|---|---|---|
| `80`, `443` | Public | Caddy, then GET-only inspector |
| `26656` | Trusted `/32` CIDRs | P2P gateway, then CometBFT |
| `22` | Google IAP only | OS Login SSH |
| `26657` | VM loopback only | Read and transaction-broadcast RPC |
| `26658`, `8765` | Container networks only | ABCI and inspector |

## 1. Provision Google Cloud

Prerequisites: a billed Google Cloud project, Terraform, `gcloud`, a DNS hostname, the
trusted genesis file and SHA-256, and at least one reachable peer.

Authenticate and select the project:

```bash
gcloud auth application-default login
gcloud config set project PROJECT_ID
```

Create the local Terraform values file:

```bash
cd deploy/gcp/single-node/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set the project, operator IAM identity, and one `/32` CIDR for each peer. Then apply:

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
terraform output
```

Listed operators receive IAP tunnel access, OS Admin Login on this instance, and read-only
Compute Engine visibility required by `gcloud compute ssh`.

Create a DNS `A` record for the inspector hostname using the `public_ip` output. Wait for
DNS resolution before starting Caddy.

The instance and data disk have deletion protection. To intentionally remove them, first
set instance `deletion_protection = false` and remove the disk `prevent_destroy` lifecycle
rule in a reviewed change. Automatic snapshots incur standard snapshot storage charges.

## 2. Install the node

Connect through IAP using the `iap_ssh_command` Terraform output. Confirm host bootstrap:

```bash
sudo systemctl status google-startup-scripts.service --no-pager
sudo findmnt /srv/discovery-net
sudo docker version
```

Clone and pin the reviewed source revision:

```bash
sudo git clone https://github.com/njallskarp/discovery_net.git /opt/discovery-net
cd /opt/discovery-net
sudo git checkout REVIEWED_COMMIT
```

Copy the trusted genesis through IAP from the operator machine:

```bash
gcloud compute scp \
  --project PROJECT_ID \
  --zone ZONE \
  --tunnel-through-iap \
  ./genesis.json NODE_NAME:/tmp/genesis.json

gcloud compute ssh NODE_NAME \
  --project PROJECT_ID \
  --zone ZONE \
  --tunnel-through-iap \
  --command 'sudo install -o 10001 -g 10001 -m 0440 /tmp/genesis.json /srv/discovery-net/genesis.json && rm /tmp/genesis.json'
```

On the VM, create the environment file from the example:

```bash
sudo cp /opt/discovery-net/deploy/gcp/single-node/node.env.example \
  /etc/discovery-net/node.env
sudo chmod 0600 /etc/discovery-net/node.env
sudoedit /etc/discovery-net/node.env
```

Set these values exactly:

- `CHAIN_ID` and `GENESIS_SHA256` from the trusted genesis;
- `P2P_ADVERTISED_ENDPOINT` to `PUBLIC_IP:26656`;
- `PERSISTENT_PEERS` to comma-separated `node-id@public-ip:26656` entries;
- `INSPECTOR_HOSTNAME` to the DNS hostname;
- `ACME_EMAIL` to the certificate contact email.

Start the services:

```bash
cd /opt/discovery-net
sudo deploy/gcp/single-node/scripts/deploy.sh
```

The peer operators must allow this node's public IP and accept its node ID. Display it with:

```bash
sudo docker compose \
  --env-file /etc/discovery-net/node.env \
  -f localnet/compose.yaml \
  -f deploy/gcp/single-node/compose.cloud.yaml \
  exec -T cometbft \
  cometbft show-node-id --home /var/lib/discovery-net/cometbft
```

## 3. Verify and submit locally

On the VM:

```bash
cd /opt/discovery-net
sudo INSPECTOR_URL=https://INSPECTOR_HOSTNAME \
  deploy/gcp/single-node/scripts/verify.sh
```

Open the private RPC tunnel using the `rpc_tunnel_command` Terraform output. Keep that
process running. Local agents can then use the existing CLI without moving the key:

```bash
discovery-net submit contribution \
  --private-key /LOCAL/PATH/contributor.pem \
  --rpc-url http://127.0.0.1:26657 \
  --kind finding \
  --title 'Title' \
  --body 'Body'
```

Only the signed transaction crosses the tunnel. The contributor private key remains local.

## Operations

```bash
# Service status
sudo docker compose --env-file /etc/discovery-net/node.env \
  -f localnet/compose.yaml -f deploy/gcp/single-node/compose.cloud.yaml ps

# Recent logs
sudo docker compose --env-file /etc/discovery-net/node.env \
  -f localnet/compose.yaml -f deploy/gcp/single-node/compose.cloud.yaml \
  logs --tail=200

# Update trusted peer IPs
cd deploy/gcp/single-node/terraform
terraform plan -out=tfplan && terraform apply tfplan
```

Never expose ports `26657`, `26658`, or `8765`, copy a validator key to this node, or put
private material in Terraform variables, VM metadata, Compose environment files, or Git.
