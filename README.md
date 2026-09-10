Below is the shortest complete workflow supported today. It assumes commands are run from the repository root.

## Start a new one-validator network

Build the node image and prepare local directories:

```bash
docker build \
  -t discovery-net-node:local \
  -f localnet/Dockerfile \
  .

ROOT="$(pwd)/run/discovery-demo"
mkdir -p \
  "$ROOT/node-a/cometbft-data" \
  "$ROOT/node-a/ledger-data"
```

Create the validator home and export its public descriptor:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$ROOT,target=/work" \
  discovery-net-node:local \
  discovery-network initialize-validator \
  --home /work/node-a/cometbft-data/cometbft

openssl genpkey -algorithm ED25519 -out "$ROOT/node-a-governance.pem"
chmod 600 "$ROOT/node-a-governance.pem"
openssl pkey \
  -in "$ROOT/node-a-governance.pem" \
  -pubout \
  -out "$ROOT/node-a-governance.pub.pem"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$ROOT,target=/work" \
  discovery-net-node:local \
  discovery-network export-validator \
  --home /work/node-a/cometbft-data/cometbft \
  --output /work/validator-a.json \
  --name validator-a \
  --governance-public-key /work/node-a-governance.pub.pem
```

Create and install genesis:

```bash
CHAIN_ID="discovery-local-1"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$ROOT,target=/work" \
  discovery-net-node:local \
  discovery-network create-genesis \
  --output /work/genesis.json \
  --chain-id "$CHAIN_ID" \
  --genesis-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --validator /work/validator-a.json

GENESIS_SHA256="$(shasum -a 256 "$ROOT/genesis.json" | awk '{print $1}')"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$ROOT,target=/work" \
  discovery-net-node:local \
  discovery-network install-genesis \
  --home /work/node-a/cometbft-data/cometbft \
  --genesis /work/genesis.json \
  --chain-id "$CHAIN_ID" \
  --genesis-sha256 "$GENESIS_SHA256"
```

Create the local P2P transport:

```bash
docker network create --internal discovery-net-p2p
```

Create `$ROOT/node-a.env`:

```bash
cat > "$ROOT/node-a.env" <<EOF
COMPOSE_PROJECT_NAME=discovery-node-a
DISCOVERY_NET_IMAGE=discovery-net-node:local
DISCOVERY_NET_UID=$(id -u)
DISCOVERY_NET_GID=$(id -g)

NODE_NAME=node-a
CHAIN_ID=$CHAIN_ID
GENESIS_FILE=$ROOT/genesis.json
GENESIS_SHA256=$GENESIS_SHA256

COMETBFT_DATA_DIRECTORY=$ROOT/node-a/cometbft-data
LEDGER_DATA_DIRECTORY=$ROOT/node-a/ledger-data

P2P_NETWORK=discovery-net-p2p
P2P_ALIAS=node-a
PERSISTENT_PEERS=

RPC_PORT=26657
EOF
```

Start the node:

```bash
docker compose \
  --env-file "$ROOT/node-a.env" \
  -f localnet/compose.yaml \
  up -d
```

Verify it:

```bash
curl http://127.0.0.1:26657/status
```

Get its node ID for future peers:

```bash
docker compose \
  --env-file "$ROOT/node-a.env" \
  -f localnet/compose.yaml \
  exec -T cometbft \
  cometbft show-node-id \
  --home /var/lib/discovery-net/cometbft
```

The governance private key is separate from the CometBFT signing key and does not enter
genesis. Back it up securely. For multiple genesis validators, each operator runs
`initialize-validator` and `export-validator` with its own governance public key. Include
every descriptor in the single `create-genesis` command. All governed genesis validators
must have equal voting power. Omitting governance keys from every descriptor creates a
legacy fixed-validator network; mixing governed and ungoverned descriptors is rejected.

## Join an existing network

Obtain these values from the network operator:

```bash
CHAIN_ID="discovery-local-1"
GENESIS_FILE="/absolute/path/to/genesis.json"
GENESIS_SHA256="<trusted-sha256>"
BOOTSTRAP_PEER="<node-id>@node-a:26656"
P2P_NETWORK="discovery-net-p2p"
```

The bootstrap hostname, such as `node-a`, must be reachable through the specified Docker network.

Prepare the joining node:

```bash
ROOT="$(pwd)/run/discovery-demo"

mkdir -p \
  "$ROOT/node-b/cometbft-data" \
  "$ROOT/node-b/ledger-data"
```

Create `$ROOT/node-b.env`:

```bash
cat > "$ROOT/node-b.env" <<EOF
COMPOSE_PROJECT_NAME=discovery-node-b
DISCOVERY_NET_IMAGE=discovery-net-node:local
DISCOVERY_NET_UID=$(id -u)
DISCOVERY_NET_GID=$(id -g)

NODE_NAME=node-b
CHAIN_ID=$CHAIN_ID
GENESIS_FILE=$GENESIS_FILE
GENESIS_SHA256=$GENESIS_SHA256

COMETBFT_DATA_DIRECTORY=$ROOT/node-b/cometbft-data
LEDGER_DATA_DIRECTORY=$ROOT/node-b/ledger-data

P2P_NETWORK=$P2P_NETWORK
P2P_ALIAS=node-b
PERSISTENT_PEERS=$BOOTSTRAP_PEER

RPC_PORT=26667
EOF
```

Start and verify it:

```bash
docker compose \
  --env-file "$ROOT/node-b.env" \
  -f localnet/compose.yaml \
  up -d

curl http://127.0.0.1:26667/status
```

The joining node needs no manual validator initialization. On its first start, the launcher
creates a persistent node and validator identity, verifies the supplied genesis, connects to
the bootstrap peer, and synchronizes the chain.

## Promote a synchronized node to validator

Admission is asynchronous and does not pause artifact transactions. Each validator has equal
power. A proposal passes at `floor(2N/3)+1` approvals from the current `N` validators; its
CometBFT update becomes active two block heights later.

First create the candidate's governance key outside the node and give only its public key to
the candidate host:

```bash
openssl genpkey -algorithm ED25519 -out node-b-governance.pem
chmod 600 node-b-governance.pem
openssl pkey -in node-b-governance.pem -pubout -out node-b-governance.pub.pem
```

After node B is caught up, have its consensus key sign the nomination. The consensus private
key never leaves its CometBFT home and the governance private key is not present:

```bash
discovery-net validator nominate-consensus \
  --home "$ROOT/node-b/cometbft-data/cometbft" \
  --chain-id "$CHAIN_ID" \
  --governance-public-key node-b-governance.pub.pem \
  --output node-b-consensus-nomination.json
```

Move that public JSON file back to the governance-key holder and complete it offline:

```bash
discovery-net validator complete-nomination \
  --consensus-nomination node-b-consensus-nomination.json \
  --governance-private-key node-b-governance.pem \
  --output node-b-nomination.json
```

One current validator sponsors the nomination. Its signed proposal counts as the first
approval and prints the proposal ID:

```bash
discovery-net validator propose-add \
  --nomination node-b-nomination.json \
  --governance-private-key node-a-governance.pem \
  --rpc-url http://127.0.0.1:26657
```

After that proposal commits, other current validator operators approve the printed ID in
later transactions:

```bash
discovery-net validator approve PROPOSAL_ID \
  --governance-private-key operator-governance.pem \
  --rpc-url http://127.0.0.1:26657
```

Inspect committed progress directly from any node's ledger:

```bash
discovery-net validator status \
  --ledger-path "$ROOT/node-a/ledger-data/artifact-ledger.sqlite"
```

Do not approve a candidate until it is caught up, reachable by the validator peers, and
configured to keep running. Candidate consent, sponsor authorization, every approval, the
current validator-set binding, and the delayed equal-power update are consensus-validated.

This Docker workflow currently supports peers sharing a Docker host and external Docker P2P network. Connecting nodes on different physical machines still needs a deliberate P2P port exposure or gateway increment. A node that dials a cloud peer from behind NAT can still join as an outbound-only leaf with `localnet.sh join ... --advertise <public IP>` (`P2P_ADVERTISED` in the env file), because a peer with a strict address book rejects an advertised Docker alias it cannot resolve.
