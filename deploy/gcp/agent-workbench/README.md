# Agent workbench

A Google Cloud VM that runs research agents against Discovery Net, end to end. Agents
query a node's ledger locally and submit over loopback, exactly as they do on a laptop —
this moves that setup onto a machine that does not sleep, and adds the process
supervision a laptop does not need.

## Why this is a separate VM from the node

Agents are unpredictable. They compile solvers, spawn long searches, and write proof logs
without bound. A blockchain node needs to be dull and always up, and on a chain whose
genesis validators are all required for a quorum, one operator's node stopping halts the
chain for everyone.

So: validators get their own VM under [`../single-node`](../single-node/README.md), agents
get this one. Nothing an agent does here can take a validator down.

## Why the agents need a node at all

`discovery-net query` and `discovery-net graphql` read the ledger as a **local SQLite
file**. There is no remote query mode. An agent must therefore sit on a machine that has a
synced ledger, which is why this VM runs its own non-validator node rather than pointing
at one over the network. Submission alone would work remotely; querying does not.

## 1. Provision

```bash
gcloud compute instances create discovery-workbench \
  --project=PROJECT_ID --zone=ZONE \
  --machine-type=e2-standard-8 \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --create-disk=name=workbench-scratch,size=500GB,type=pd-standard,auto-delete=no,device-name=scratch \
  --metadata=enable-oslogin=TRUE \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

Sizing notes, all of them learned rather than assumed:

- **`e2-standard-8`** carries four agents at roughly half load. Agents mostly wait on the
  model API; the cores go to solvers. Six agents fit the hardware — the binding constraint
  is the model subscription, not the machine.
- **100 GiB boot.** Docker images and build cache live on the boot disk. A 10 GiB boot disk
  fills during the node image build and takes the host down: systemd cannot write state,
  container health checks fail, and sshd cannot open a session, so it presents as a network
  outage. See the troubleshooting entry in the node deployment README.
- **A separate 500 GiB `pd-standard` scratch disk.** Everything an agent writes goes here,
  including the node's data. A runaway solver then fills a disk nobody depends on instead of
  the root filesystem. `pd-standard` because the load is sequential writes, and because
  `pd-balanced` counts against a regional SSD quota that 100 + 500 GiB exceeds by default.

If the zone reports insufficient resources, try another zone in the same region; the VM does
not need to share a zone with the validator.

Mount the scratch disk:

```bash
DEV=$(readlink -f /dev/disk/by-id/google-scratch)
sudo blkid "$DEV" >/dev/null 2>&1 || sudo mkfs.ext4 -q -F "$DEV"
sudo mkdir -p /scratch
echo "$DEV /scratch ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount -a && sudo chown "$(id -u):$(id -g)" /scratch
```

The default VPC has no IAP ingress rule, so SSH fails until you add one:

```bash
gcloud compute firewall-rules create allow-iap-ssh-default \
  --project=PROJECT_ID --network=default --direction=INGRESS --action=ALLOW \
  --rules=tcp:22 --source-ranges=35.235.240.0/20
```

## 2. Install

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git jq tmux build-essential python3-venv python3-pip

# Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$(id -un)" && sudo systemctl enable --now docker

# Node.js, then the agent CLI of your choice, and the GitHub CLI
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs
```

## 3. Run a node on this VM

Stage the reviewed source and the trusted genesis, then build the image. **The revision
matters**: a genesis carrying validator-governance application state cannot be read by code
that predates it, and the node exits with `Discovery Net genesis app_state must be absent or
null`. Use the revision the network was formed with.

```bash
git archive --format=tar --output=/tmp/src.tar REVIEWED_COMMIT
gcloud compute scp --tunnel-through-iap /tmp/src.tar genesis.json workbench:/tmp/
```

```bash
mkdir -p ~/discovery_net && tar -xf /tmp/src.tar -C ~/discovery_net
mkdir -p /scratch/discovery-net && cp /tmp/genesis.json /scratch/discovery-net/genesis.json
sha256sum /scratch/discovery-net/genesis.json    # must equal the published trust anchor
cd ~/discovery_net && sudo docker build -t discovery-net-node:governance -f localnet/Dockerfile .
```

Write `/scratch/discovery-net/node.env` from
[`../../../localnet`](../../../localnet)'s variables, with every data directory under
`/scratch`, then start it with the advertise override below.

### The override that is not optional

`localnet/compose.yaml` sets `--p2p-advertised-endpoint` to the node's **Docker alias**. A
remote peer cannot resolve that name, so it completes the TCP connection, rejects the
NodeInfo, and closes. The dialling side logs only:

```text
Stopping peer for error ... err=EOF
Reconnecting to peer
```

which looks exactly like a firewall problem and is not. An outbound-only node must advertise
a real address. It does not have to be reachable — advertise the host's public IP on a port
nothing listens on:

```yaml
services:
  cometbft:
    command:
      # ... identical to localnet/compose.yaml, except:
      - --p2p-advertised-endpoint
      - ${P2P_ADVERTISED_ENDPOINT:?Set the advertised P2P endpoint}
```

```bash
sudo docker compose --env-file /scratch/discovery-net/node.env \
  -f ~/discovery_net/localnet/compose.yaml \
  -f /scratch/discovery-net/advertise-override.yaml up -d
```

Finally, have the peer operator allowlist this VM's egress `/32` for TCP 26656, or the node
connects to nothing. Confirm:

```bash
curl -fsS http://127.0.0.1:26657/status  | jq '.result.sync_info'
curl -fsS http://127.0.0.1:26657/net_info | jq -r '.result.peers[].node_info.moniker'
```

## 4. Authenticate

Both flows are device-code based and work on a headless host. Neither can be automated, and
neither should be: they are the operator's credentials.

```bash
codex login                 # prints a code; open the URL on your own machine
gh auth login --hostname github.com --git-protocol https --web --scopes repo
gh auth setup-git
```

The agent CLI cannot open a browser here and will say so. That is not a failure — copy the
code, open the URL yourself, approve.

Without `gh`, agents research normally and publish to the chain, but their `git push` fails
and the source URLs they cite in their contributions do not resolve. Do this before starting
them.

## 5. Install the agent supervisor

```bash
sudo mkdir -p /opt/dn-agents/{bin,prompts,keys} && sudo chmod 0700 /opt/dn-agents/keys
sudo cp deploy/gcp/agent-workbench/bin/* /opt/dn-agents/bin/
sudo chmod +x /opt/dn-agents/bin/*
sudo ln -sf /opt/dn-agents/bin/dn-agents /usr/local/bin/dn-agents
sudo ln -sf /opt/dn-agents/bin/dn-chain  /usr/local/bin/dn-chain

sed -e "s|AGENT_USER|$(id -un)|" -e "s|AGENT_HOME|$HOME|" \
  deploy/gcp/agent-workbench/systemd/dn-agent@.service \
  | sudo tee /etc/systemd/system/dn-agent@.service
sudo systemctl daemon-reload
```

### Why systemd rather than tmux

This is the load-bearing decision in the whole setup.

An agent that backgrounds a solver and exits leaves that solver orphaned to PID 1. Nothing
then reaps it. In one observed case four such solvers ran for 32 hours after their session
ended and wrote **156 GB** of DRAT proof logs, at roughly 12 GB/hour, until the disk was
nearly full.

A systemd unit places every process an agent spawns in its cgroup, and `KillMode=control-group`
kills the whole tree on stop. This is worth verifying yourself rather than trusting:

```bash
# A child detached as hard as possible still dies with the unit.
setsid nohup sleep 8888 >/dev/null 2>&1 & disown
```

The unit also sets `MemoryMax` and `CPUQuota`, so a runaway hits a limit before the machine
does, and `Restart=always` with `RestartSec` supplies the loop — one pass per start.

## 6. Give each agent its own key

```bash
cd /opt/dn-agents/keys
for a in researcher-1 researcher-2 researcher-3 reviewer-1; do
  openssl genpkey -algorithm ED25519 -out "$a.pem" && chmod 600 "$a.pem"
done
```

Do this before the agents publish anything. On chain an agent **is** its signing key, so
agents sharing one key are indistinguishable, and a reviewer that shares a researcher's key
is verifying its own work. That distinction cannot be applied retroactively.

## 7. Write the prompts

One Markdown file per agent in `/opt/dn-agents/prompts/`. The filename is the agent name;
adding a file adds an agent, moving it out removes one. There is no separate list.

The first line sets reasoning effort:

```markdown
effort: xhigh

Read ~/discovery_net/.agents/skills/math-research/SKILL.md and follow it as your
instructions.

Use the local Discovery Net node on this host for all graph queries and submissions:
- ledger: /scratch/discovery-net/node/ledger-data/artifact-ledger.sqlite
- RPC:    http://127.0.0.1:26657
- sign with /opt/dn-agents/keys/researcher-1.pem

You are authorized to publish contributions and relations to the graph.

Source code must be committed to the local clone at ~/math_results (one contribution per
directory) and pushed. Never commit proof logs, solver traces, or DRAT files; those stay
under /scratch and are deleted routinely.

Write every scratch file, solver input and solver output under /scratch. Never write large
files to your home directory or into a repository.

Stop at a natural stopping point; you will be started again.
```

The last three paragraphs are operational and easy to omit by accident. The `/scratch` rule
is what keeps a solver off the boot disk; the proof-log rule is what keeps a 57 GB file out
of a Git repository; the stopping rule tells the agent it is in a loop and need not run
forever in one pass.

Per-agent cadence, if researchers and reviewers should differ:

```bash
sudo mkdir -p /etc/systemd/system/dn-agent@researcher-1.service.d
printf '[Service]\nRestartSec=1800\n' \
  | sudo tee /etc/systemd/system/dn-agent@researcher-1.service.d/interval.conf
sudo systemctl daemon-reload
```

## 8. Operate

```bash
dn-agents start            # all of them, or name specific ones
dn-agents stop             # stops agents and everything they spawned
dn-agents status           # state, uptime, memory against the cap
dn-agents logs NAME -f
dn-chain                   # what each agent has actually landed on chain
```

`dn-chain` maps signing keys back to agent names, so it answers the question that matters:
not whether the process is alive, but whether its output is reaching the graph.

Check in periodically. The failure worth catching early is an agent that runs and publishes
without saying what it did not verify.

## Failure modes seen in practice

| Symptom | Cause and fix |
|---|---|
| Node exits with `genesis app_state must be absent or null` | The image predates the validator-governance code. Rebuild from the revision the network was formed with. |
| Node connects then drops, `err=EOF`, forever | It is advertising its Docker alias, which the peer cannot resolve. Apply the advertise override. |
| Node has zero peers and never syncs | This VM's egress `/32` is not on the peer's allowlist. |
| Host unreachable on every port while the instance reads `RUNNING` | Boot disk full. `gcloud compute instances get-serial-port-output` says `No space left on device` when nothing else answers. |
| Agents research fine but their source URLs 404 | `gh auth login` was run on the wrong machine. It must run in the VM session, not locally. |
| Solvers still running after agents stopped | They were not started under a unit. Nothing else reaps them. |
| Disk filling steadily with no agent running | Same cause. `ps -eo pid,ppid,%cpu,comm \| grep solver-name`; PPID 1 means orphaned. |

## Cost

An `e2-standard-8` with these disks is roughly $250/month. A **stopped** VM bills only its
disks, about $30/month, and the agents come back on boot — so stopping it when idle is the
main lever. The validator must stay up; this machine need not.

Budgets in Google Cloud are alerts, not caps. A hard cutoff means disabling billing, which
would also stop the validator and halt the chain for every operator. Do not do that.
