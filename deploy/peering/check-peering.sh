#!/usr/bin/env bash
#
# Read-only peering report for one node.
#
#   deploy/peering/check-peering.sh [RPC_URL]
#   DN_PUBLIC_IP=203.0.113.7 deploy/peering/check-peering.sh
#
# Answers the two questions people conflate: am I on the chain, and can anyone
# else reach me. Changes nothing -- it prints the commands, it does not run them.
#
# Light and untested against a live multi-operator network. Read PEERING.md.

set -eu
RPC="${1:-${DN_RPC_URL:-http://127.0.0.1:26657}}"
PUBLIC_IP="${DN_PUBLIC_IP:-}"

j() { python3 -c "import json,sys;d=json.load(sys.stdin)
try:
    print(eval('d'+sys.argv[1]))
except Exception:
    print('')" "$1"; }

STATUS="$(curl -sS -m 10 "$RPC/status" 2>/dev/null)" || { echo "no answer from $RPC/status"; exit 1; }
NODE_ID=$(printf '%s' "$STATUS" | j '["result"]["node_info"]["id"]')
MONIKER=$(printf '%s' "$STATUS" | j '["result"]["node_info"]["moniker"]')
CHAIN=$(printf   '%s' "$STATUS" | j '["result"]["node_info"]["network"]')
LISTEN=$(printf  '%s' "$STATUS" | j '["result"]["node_info"]["listen_addr"]')
HEIGHT=$(printf  '%s' "$STATUS" | j '["result"]["sync_info"]["latest_block_height"]')
CATCH=$(printf   '%s' "$STATUS" | j '["result"]["sync_info"]["catching_up"]')
POWER=$(printf   '%s' "$STATUS" | j '["result"]["validator_info"]["voting_power"]')

echo
echo "identity"
echo "  moniker        $MONIKER"
echo "  node id        $NODE_ID"
echo "  chain          $CHAIN"
echo "  height         $HEIGHT   catching_up=$CATCH   voting power=$POWER"
echo "  advertised as  $LISTEN"

# Routable means a public IP or a dotted hostname. 0.0.0.0, loopback and the
# private ranges are what a misconfigured node advertises most often, and the
# old digit.digit test called every one of them routable.
ADVERTISED_ROUTABLE="$(python3 -c '
import ipaddress, re, sys
listen, public = sys.argv[1], sys.argv[2]
host = re.sub(r"^[a-z]+://", "", listen).rsplit(":", 1)[0].strip("[]")
if public and host == public:
    print(1); sys.exit()
try:
    ip = ipaddress.ip_address(host)
    print(0 if (ip.is_unspecified or ip.is_loopback or ip.is_private or ip.is_link_local) else 1)
except ValueError:
    print(1 if "." in host else 0)   # a dotted name may resolve; a bare alias cannot
' "$LISTEN" "$PUBLIC_IP")"
if [ "$ADVERTISED_ROUTABLE" = 0 ]; then
  echo "  NOTE: that is not an address anyone outside this host can dial -- a Docker"
  echo "        alias, 0.0.0.0, loopback or a private range. A node started by"
  echo "        localnet/localnet.sh advertises its alias, so other operators cannot"
  echo "        learn a usable address for it however hard they try."
fi

NET="$(curl -sS -m 10 "$RPC/net_info" 2>/dev/null)" || NET=""
if [ -n "$NET" ]; then
  IN=$(printf  '%s' "$NET" | python3 -c 'import json,sys;p=json.load(sys.stdin)["result"]["peers"];print(sum(1 for x in p if not x["is_outbound"]))')
  OUT=$(printf '%s' "$NET" | python3 -c 'import json,sys;p=json.load(sys.stdin)["result"]["peers"];print(sum(1 for x in p if x["is_outbound"]))')
  echo
  echo "peers"
  echo "  inbound  $IN     (other nodes that dialled you)"
  echo "  outbound $OUT     (nodes you dialled)"
  printf '%s' "$NET" | python3 -c '
import json,sys
for x in json.load(sys.stdin)["result"]["peers"]:
    print("    %-16s %-8s %s" % (x["node_info"]["moniker"],
          "inbound" if not x["is_outbound"] else "outbound", x["remote_ip"]))'
  if [ "$IN" = "0" ]; then
    echo
    echo "  Zero inbound peers. You are a leaf: you can sync and you can submit,"
    echo "  but nobody can reach you. That is sufficient for an agent and not"
    echo "  sufficient for a validator."
  fi
fi

echo
echo "to be reachable, all four have to be true"
echo "  1. a routable endpoint is published            $([ "$ADVERTISED_ROUTABLE" = 1 ] && echo 'looks ok' || echo 'MISSING — needs the cloud overlay, see PEERING.md')"
echo "  2. P2P_ADVERTISED_ENDPOINT is that address     $([ "$ADVERTISED_ROUTABLE" = 1 ] && echo 'looks ok' || echo 'MISSING')"
echo "  3. your firewall admits each peer's /32        cannot be checked from here"
echo "  4. THEIR firewall admits your /32              cannot be checked from here — ask them"
echo
echo "  3 and 4 are not scriptable from one side. 4 is a request to another"
echo "  operator, which is why PEERING.md is mostly a message to send."
echo
if [ -n "$PUBLIC_IP" ]; then
  echo "give the other operators exactly this line:"
  echo "  $NODE_ID@$PUBLIC_IP:26656"
else
  echo "give the other operators this, with your public IP in place of PUBLIC_IP:"
  echo "  $NODE_ID@PUBLIC_IP:26656"
  echo "  (set DN_PUBLIC_IP to have it printed ready to paste)"
fi
echo
echo "and admit their addresses on your side. Both flags REPLACE, never append,"
echo "so always pass the complete list:"
echo "  gcloud compute firewall-rules update discovery-net-p2p \\"
echo "    --source-ranges=PEER1/32,PEER2/32,PEER3/32 \\"
echo "    --rules=tcp:26656"
echo
