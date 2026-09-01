# Making a node visible to the other validators

Light, and not yet exercised against the live multi-operator network. Written to
be followed by a person, not run unattended.

## The short answer

**No, the localnet setup script does not do this.** It gets a node onto a chain.
It does not make the node reachable, and for `bootstrap` it does not even put you
on the right chain.

Two questions get conflated constantly, and they have different answers:

| Question | Answered by |
|---|---|
| Am I on the same chain as everyone else? | genesis + chain ID + one reachable peer to dial |
| Can the other validators reach *me*? | a published port, a routable advertised endpoint, and **their** firewalls |

An agent only needs the first. A validator needs both.

## What each script actually gives you

`localnet/localnet.sh bootstrap` creates a **new network**: it runs
`create-genesis` with its own chain ID (`discovery-local-1` by default) and its
own single validator. It is not `discovery-net` and never will be. Correct for
local testing, wrong if you expected to join the real chain.

`localnet/localnet.sh join` does put you on an existing chain, given the trusted
genesis, its SHA-256, and a bootstrap peer. It auto-enables egress when the peer
host is an IP or FQDN, so the node can dial out.

But the base compose advertises the wrong thing and publishes nothing:

```yaml
- --p2p-advertised-endpoint
- ${P2P_ALIAS}:26656          # a Docker alias, meaningless off this host
ports:
- published: ${RPC_PORT}      # RPC only; 26656 is not published
```

So a joined node is a **leaf**: it dials out, syncs, and can submit. Nobody can
dial it, and nobody can even learn an address to try. That is fine for an agent
host and not fine for a validator.

`deploy/gcp/single-node/` is what makes a node reachable. Its overlay adds a
`p2p-gateway` — an nginx stream proxy publishing host port 26656 into
`comet-p2p:26656` — and *requires* `P2P_ADVERTISED_ENDPOINT`, which you set to
`PUBLIC_IP:26656`.

## The four conditions

All four have to hold, and only the first two are yours alone:

1. **A published, routable endpoint.** The cloud overlay's p2p-gateway, on a
   static IP. An ephemeral IP changes on stop/start and silently invalidates
   every allowlist entry that names it.
2. **`P2P_ADVERTISED_ENDPOINT` set to that address.** Advertising a Docker alias
   is the default failure.
3. **Your firewall admits each peer's `/32`** on `tcp:26656`.
4. **Their firewall admits your `/32`.** Not scriptable from here. This is a
   request to another human.

`check-peering.sh` reports 1 and 2 from a running node, counts inbound versus
outbound peers, and prints the exact strings for 3 and 4. It changes nothing.

```bash
DN_PUBLIC_IP=203.0.113.7 deploy/peering/check-peering.sh
```

Zero inbound peers with healthy outbound is the signature of a leaf — it means
3 or 4 is missing, not that anything is broken.

## Joining: the message to send

Peering is mutual, so it is an exchange. Send the other operators:

```
node id     <from check-peering.sh>
address     <YOUR_PUBLIC_IP>:26656
peer line   <node-id>@<YOUR_PUBLIC_IP>:26656
chain       discovery-net
```

Ask each of them to append your peer line to their `PERSISTENT_PEERS` and add
your `/32` to their P2P firewall. Collect the same four fields back from each.

Then, on your side:

```bash
gcloud compute firewall-rules update discovery-net-p2p \
  --source-ranges=PEER1/32,PEER2/32,PEER3/32 \
  --rules=tcp:26656
```

**Both flags replace rather than append.** Pass the complete list every time —
omitting an existing peer silently removes it. Use `gcloud` and not the console:
its "Source IPv4 ranges" chip input has corrupted entries on three consecutive
attempts, concatenating two CIDRs into one (`34.29.139.172/3234.63.77.28/32`).

If you run more than one node on the box, the rule needs every P2P port, not
just the first: `--rules=tcp:26656,tcp:26666,tcp:26676`.

## Verifying

From an allowlisted peer, before anything else:

```bash
nc -vz YOUR_PUBLIC_IP 26656
```

Then on your node, `check-peering.sh` again: inbound should be non-zero and the
new peers should appear by moniker. Expect a few minutes, not seconds.

Inbound peers may all show the same source IP. That is the p2p-gateway, which
gives every inbound connection one container source address; the GCP firewall is
still enforcing the real `/32` list in front of it. It is not a sign that
something is misconfigured.

## Two things not to do

Do not run two copies of one P2P identity. Migrating a node key means moving only
`config/node_key.json`, and never while the source node is running — both copies
online produces duplicate-ID disconnects across the whole network.

Do not stop/start an instance whose external IP is ephemeral. The address changes,
and every peer and firewall rule that names it is silently wrong. Reset instead.
