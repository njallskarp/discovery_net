# `discovery-net` genesis

This directory contains the immutable trust anchor for the `discovery-net` chain.
Genesis is public by design: it contains only consensus parameters, validator names,
validator consensus public keys, governance public keys, and voting power. Never share a
validator private key, governance private key, P2P private key, contributor key, node state,
or ledger database.

The genesis was formed with source commit
`5fb8186e2448fb5509ab7a8b58ea9150797ce69b` from
[PR #44](https://github.com/njallskarp/discovery_net/pull/44). Operators must use that
validator-governance implementation or a reviewed descendant. This launch-package PR is
stacked on PR #44 so its diff contains only the public trust anchor and these instructions.

## Trust anchor

```text
chain_id:       discovery-net
genesis_time:   2026-08-30T21:38:10.000000Z
genesis_sha256: 3e3c8f1ca6e402b0ec2574ee17fe878339526913358f1a8d4ac3216ffea1c30a
```

Verify the file before installing it:

```bash
printf '%s  %s\n' \
  3e3c8f1ca6e402b0ec2574ee17fe878339526913358f1a8d4ac3216ffea1c30a \
  networks/discovery-net/genesis.json \
  | sha256sum --check
```

## Genesis validators

| Name | Consensus public key | Governance public key | Power |
|---|---|---|---:|
| `node-njall-1` | `BWBDfPkN++J/OAoudAFehktUOa9CQdd5Cr9Ugk41kr8=` | `7DGDKg+LVWfUqf+kcR3r/L48FFFuOP7s0zjWy/kslwA=` | 10 |
| `node-abu-1` | `R6GeCaNU8jGzgy6sLI8/QnLsstP//Bya0N+7E4Fgyb0=` | `JRZebfG1oLWwtv8+ElCWhJvE97XN/Ip5LrJNBgyE8pc=` | 10 |
| `node-helgi-1` | `zPgeEXkVp3P1FFovl0oTWFZaQAx0bGOimLykUiQ2ixE=` | `uPNV+MVx5nNZ0HiOJdNjf6MnECq77upkH7Z9IgYsYSU=` | 10 |

These validators are admitted directly by genesis. They do not need a nomination,
proposal, or governance approval. Each operator must still run the matching consensus
private key and retain the separate matching governance private key offline.

With total power 30, CometBFT requires more than 20 power to commit. Consequently, all
three genesis validators must be online and connected until the validator set changes.

## Peer bootstrap

The live bootstrap node is:

```text
node-njall-1
d3fec047e0d258b60baa61de6229a565e8366973@34.172.207.3:26656
```

`node-helgi-1` has announced:

```text
83a8d08afc461216071a433504c5f3cfcf79d549@207.175.38.45:26656
```

Consensus public keys and P2P node IDs are different identities. `node-abu-1` must publish
its P2P node ID, stable public endpoint, and public egress IP separately. Every cloud
firewall must allow TCP `26656` only from trusted peer `/32` egress addresses. A peer behind
an inbound firewall can instead dial `node-njall-1` outbound after its egress IP is
allowlisted there.

## Validator onboarding

Use the reviewed source containing asynchronous validator governance and the hardened GCP
deployment. Do not start CometBFT before installing this genesis into the pristine validator
home.

First verify that the existing unstarted home contains the expected validator public key:

```bash
IMAGE='discovery-net-node:REVIEWED_COMMIT'
COMETBFT_DATA_DIRECTORY='/srv/discovery-net/cometbft-data'

sudo docker run --rm --network none \
  --user 10001:10001 \
  --mount \
    type=bind,source="$COMETBFT_DATA_DIRECTORY",target=/var/lib/discovery-net,readonly \
  "$IMAGE" \
  cometbft show-validator --home /var/lib/discovery-net/cometbft
```

The returned `value` must exactly match the consensus public key in the table. A mismatch
means this is not the admitted validator identity; do not start it and do not copy another
operator's private key.

Install the verified genesis into that unstarted home:

```bash
sudo install -o 10001 -g 10001 -m 0440 \
  networks/discovery-net/genesis.json \
  /srv/discovery-net/genesis.json

sudo docker run --rm --network none \
  --user 10001:10001 \
  --mount \
    type=bind,source="$COMETBFT_DATA_DIRECTORY",target=/var/lib/discovery-net \
  --mount \
    type=bind,source=/srv/discovery-net/genesis.json,target=/run/discovery-net/genesis.json,readonly \
  "$IMAGE" \
  discovery-network install-genesis \
  --home /var/lib/discovery-net/cometbft \
  --genesis /run/discovery-net/genesis.json \
  --chain-id discovery-net \
  --genesis-sha256 3e3c8f1ca6e402b0ec2574ee17fe878339526913358f1a8d4ac3216ffea1c30a
```

Set the production node environment to these trust values:

```text
CHAIN_ID=discovery-net
GENESIS_FILE=/srv/discovery-net/genesis.json
GENESIS_SHA256=3e3c8f1ca6e402b0ec2574ee17fe878339526913358f1a8d4ac3216ffea1c30a
PERSISTENT_PEERS=d3fec047e0d258b60baa61de6229a565e8366973@34.172.207.3:26656
```

Also set `NODE_NAME`, the node's own `P2P_ADVERTISED_ENDPOINT`, and the remaining values
specified by [`deploy/gcp/single-node`](../../deploy/gcp/single-node/README.md). Then run the
normal idempotent deployment command:

```bash
cd /opt/discovery-net
sudo deploy/gcp/single-node/scripts/deploy.sh
sudo deploy/gcp/single-node/scripts/verify.sh
```

Finally, inspect the private loopback RPC through IAP:

```bash
curl -fsS http://127.0.0.1:26657/status \
  | jq '.result | {
      chain_id: .node_info.network,
      moniker: .node_info.moniker,
      height: .sync_info.latest_block_height,
      validator: .validator_info
    }'

curl -fsS http://127.0.0.1:26657/net_info \
  | jq '.result | {n_peers, peers: [.peers[].node_info.moniker]}'
```

Require chain ID `discovery-net`, the operator's exact consensus public key, voting power
`10`, and the expected peer before treating the validator as ready. Height `0` is expected
until all three genesis validators are connected.
