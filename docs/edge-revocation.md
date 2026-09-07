# Permanent edge revocation

`EdgeRevocation(target, reason, created_at)` is a signed, content-addressed record
with one effect: exclude the exact target edge from the default graph view.
The target must be an existing `ContributionRelation`. Contributions and revocation
records cannot be targets. A nonblank public reason is required.

Original edges, contributions, envelopes, hashes, signatures, timestamps, and ledger
positions remain unchanged. New taxonomy nodes and edges are ordinary artifacts.
There are no proposals, replacement pointers, versions, activation timestamps,
restore operations, or migration exceptions.

## Example

The following is a decoded illustration, with aliases in place of real artifact
hashes and signing wrappers omitted:

```json
{
  "height": 801,
  "artifacts_in_one_signed_transaction": [
    {
      "payload_type": "edge_revocation",
      "payload": {
        "target": "old-about-edge",
        "reason": "Classify the conjecture under Coloring instead of Mathematics.",
        "created_at": "2026-09-07T14:04:00Z"
      }
    },
    {
      "payload_type": "contribution_relation",
      "payload": {
        "from_contribution": "original-conjecture",
        "to_contribution": "coloring-area",
        "kind": "about",
        "created_at": "2026-09-07T14:04:00Z"
      }
    }
  ]
}
```

The original conjecture is not resubmitted. Its original inclusion height and
signed creation time remain intact. The new records have their own hashes and
inclusion positions. Author-supplied creation times are not consensus timestamps;
retain original CometBFT blocks and commits when preserving chain inclusion evidence.

## Permission and trust

`node.authorization.can_revoke` is the complete current permission policy:

```python
return voting_power.get(signer_public_key, 0) > 0
```

Every verifying application, including non-voting nodes, authenticates the chain
and signatures before applying this policy in CheckTx and again in FinalizeBlock.
Invalid revocations reject the whole transaction, including any bundled replacement.
Targets must exist before the transaction; an earlier transaction in the same
block can supply a target. A revocation never implicitly revokes other edges.

One validator can revoke another author's edge, of any relation kind. This is
explicit editorial authority, not a mathematical verdict or a quorum of editorial
approvals. Authorship alone and self-declared expertise grant no permission.
A non-validator may publish a new edge asserting the same relationship under the
ordinary submission rules. Revocation is not a permanent ban on that relationship.

The protocol emits no validator updates, so the hash-pinned genesis electorate is
currently active at every height. Applications load the same trusted public genesis
as CometBFT, compare it with InitChain, and reload it before replay. Missing authority
rejects revocations. Future membership or expert permissions must use authority
applicable at the original execution height, rather than today's membership or a
live RPC lookup. No such roles or grants are introduced here.

Queries consume the local ledger accepted by application validation. Neither a
remote GraphQL response nor an arbitrary SQLite copy is independently authenticated
by query filtering. Verified replay checks application rules against trusted genesis;
it does not itself prove consensus inclusion. A modified peer cannot grant itself
permission on honest nodes, but it can misrepresent its own query results.

## Permanent effect, independent new assertions

An edge is active if no accepted revocation targets its exact hash. Client timestamps
do not affect this test. Distinct revocations of the same edge add audit evidence
with the same idempotent effect. Exact duplicate artifacts remain rejected.

There is no way to restore that edge or revoke its revocation. To assert the same
relationship again, publish a new signed edge with its own identity and provenance.
This leaves the original revocation intact. A snapshot from before the revocation
still shows the original graph. Incremental indexing and replay produce the same view.

## Queries

The shared projection filters revoked edges from normal relation lists, directed
traversal, and derived graph counts. Contributions are unaffected. Explicit audit
listing includes revoked edges without changing default traversal:

```graphql
query Audit($edge: ID!) {
  relations { artifactRef kind }
  history: relations(includeRevoked: true) { artifactRef kind revoked }
  artifact(ref: $edge) {
    artifactRef signature signerPublicKey createdAt height transactionIndex
    ... on Relation { revoked }
  }
  revocations(target: $edge) {
    artifactRef targetRef reason signerPublicKey signature height
  }
}
```

`revoked` belongs to `Relation`, not contributions or the shared artifact interface.
Raw `artifact(ref:)` lookup returns the original edge. The inspector's graph uses
active edges while its transaction feed retains original records and signed reasons.

## Operation

```sh
discovery-node --chain-id CHAIN --ledger-path /data/artifact-ledger.sqlite \
  --genesis /config/genesis.json --genesis-sha256 TRUSTED_SHA256

discovery-net submit revocation --private-key /secure/signing-key.pem \
  --rpc-url http://127.0.0.1:26657 --target EDGE_CID --reason 'Incorrect placement'
discovery-net query --ledger-path /data/artifact-ledger.sqlite relations --include-revoked
discovery-net query --ledger-path /data/artifact-ledger.sqlite revocations --target EDGE_CID
```

Submission uses existing Ed25519 PEM input; its public key must match a validator.
Application containers mount only public genesis, never consensus private keys.
Separate curation-key delegation is not implemented. A successful CLI submission
means CheckTx accepted broadcast, not that the transaction has committed.

Offline snapshot replay/export requires the same `--genesis` and `--genesis-sha256`
arguments. The export records the genesis digest; retain that public file as evidence.
All nodes need compatible software and authority configuration before the first
edge revocation. Older decoders cannot read `edge_revocation`. This PR does not
upgrade live nodes, rebuild their ledger, or submit any migration transactions.
