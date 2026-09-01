# Localnet by hand

`localnet/localnet.sh` wraps every step below into `bootstrap` and `join`, and is
what you should normally use. This is the long form: the same flow written out,
so the formation steps are inspectable and so a step can be run on its own when
something needs unpicking.

Kept in sync with the script. If they disagree, the script is what runs.

---

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

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$ROOT,target=/work" \
  discovery-net-node:local \
  discovery-network export-validator \
  --home /work/node-a/cometbft-data/cometbft \
  --output /work/validator-a.json \
  --name validator-a
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

For multiple genesis validators, each operator runs `initialize-validator` and `export-validator`. Include every resulting descriptor in the single `create-genesis` command.

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

The joining node needs no validator initialization. On its first start, the launcher creates a persistent node identity, verifies the supplied genesis, connects to the bootstrap peer, and synchronizes the chain.

This Docker workflow currently supports peers sharing a Docker host and external Docker P2P network. Connecting nodes on different physical machines still needs a deliberate P2P port exposure or gateway increment.
