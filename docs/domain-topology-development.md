# Domain separation and topology development plan

Status: initial design discussion. The actionable implementation sequence is now
in [domain-topology-pr-plan.md](domain-topology-pr-plan.md).

Development branch: `codex/domain-topology-development`, based on `652f4de`.

## Intended outcome

Expose `discovery-net math ...` and eventually `discovery-net security ...`, each
using its own domain model over a shared artifact graph. Users see one canonical
math topology. Candidate names such as blue or green are development conveniences,
not a public version-selection API or permanent protocol concept.

Preserve existing contribution envelopes, signatures, and identifiers exactly.
Build new organizing nodes and replacement relationships as new artifacts. Keep
old relationships in history while the canonical projection selects the adopted
relationships. Historical decoding remains necessary even after candidate names
and comparison interfaces are removed.

Validators and non-voting full nodes execute the same deterministic rules. Use
shared domain rule modules, not role-specific overrides of committed execution.
Separate startup profiles can configure voting keys and query services. A query
service consuming an upstream ledger is distinct from a full node that verifies it.

## Commit / PR sequence

Use the development branch as an integration branch. Each numbered group can be a
small PR into that branch, or a few reviewable commits on it. Release to main only
after the local rehearsal succeeds. These are planned groups, not opened PRs.

### 1. Capture the baseline and specify the topology change

- Take a consistent, read-only-derived ledger snapshot using SQLite backup support;
  record chain ID, committed height, state hash, and a snapshot digest. Do not edit
  the live SQLite file or commit a bulk production snapshot to Git.
- Specify concrete old/new graph examples: new node kinds, relationship meanings
  and direction, membership, allowed endpoints, and representative research queries.
- Decide whether the migration replaces all math relationships or only particular
  kinds/scopes. Specify how unrelated relationships and cross-domain links behave.
- Extend the fixed wire fixtures with representative historical signed artifacts
  and expected IDs. Record baseline query results for a small reviewable fixture.

Acceptance: the desired topology can be explained by fixtures, and historical
identity and query behavior have concrete regression evidence.

### 2. Separate core mechanics from the existing math implementation

- Extract math models and domain rules behind explicit interfaces. Keep the current
  model and wire behavior unchanged, with compatibility imports where useful.
- Separate envelope/identity/reference checks from domain payload and relation rules.
- Introduce a projection boundary between stored artifacts and domain query models.
- Prove the boundary is domain-independent with a small second-domain test fixture;
  do not invent a full production security ontology as part of this refactor.

Likely touchpoints: `knowledge_graph`, `wire`, `node/transaction_validator.py`,
`indexing`, and `query`.

Acceptance: fixed bytes, IDs, transaction outcomes, historical state hashes, and
existing public query behavior are unchanged.

### 3. Build and inspect a candidate topology entirely offline

- Build a reproducible candidate from the pinned snapshot using existing contribution
  IDs, proposed new nodes, and proposed relationships. Start with an unsigned plan
  and in-memory projection; no submission or consensus format is required yet.
- Keep any candidate selector in developer tooling. Compare baseline and candidate
  queries and inspect the resulting graph locally.
- Emit a migration report: retained/new nodes, selected/replaced/omitted edges,
  endpoint failures, coverage, and provenance of each migration decision.
- Evaluate topology-specific invariants from step 1; do not assume all relation
  types must be acyclic or that old/new query results must be identical.
- Preserve explicit curation decisions if edge generation uses human or model
  judgment, so reruns do not silently create a different topology.

Acceptance: the intended topology is useful on real data, with every deliberate
change explained. Iterate here before freezing its durable representation.

### 4. Implement the durable artifacts and deterministic domain validation

- Use the validated design to choose the minimum new artifact formats needed for
  nodes, relationships, and topology selection. Keep internal format identifiers
  where decoding requires them; do not encode temporary color names in the protocol.
- Decode historical envelopes without rewriting them. New relationships can point
  directly to legacy contribution IDs through the math compatibility adapter.
- Specify which domain rules are supported and when they become active. Every
  executing node must enforce the same rules; configuration cannot arbitrarily
  enable or disable a domain's consensus validation on individual full nodes.
- Pass historical execution context into replay, including snapshot reconstruction,
  if acceptance rules depend on activation height. Define mempool boundary behavior.
- Enforce rejection in committed execution as well as early submission checks.

Acceptance: malformed domain artifacts are rejected deterministically; historical
replay retains its original outcomes; cross-domain references follow explicit rules.

### 5. Package the migration and canonical domain queries

- Convert the reviewed plan into signed, append-only artifacts with stable recorded
  timestamps, signer identity, migration provenance, and expected IDs. New edges are
  claims by the migration signer, not retroactive signatures by original authors.
- Produce a resumable submission manifest and reconciliation report. A retry must
  recognize already committed artifacts rather than generate new identities.
- Define complete topology selection explicitly, including the treatment of old
  edges, new post-migration contributions, future edges, and conflicting assertions.
  Do not implement selection as simply all edges published after a timestamp.
- Stage artifacts before changing the canonical projection. The readiness decision
  must check the complete manifest even if publication spans multiple transactions.
- Choose and document who may promote or amend the canonical selection. For the
  first release this can be a pinned, release-controlled definition; if an on-chain
  activation artifact is used, its authority must be checked explicitly.
- Make CLI, GraphQL, inspector, traversals, counts, and derived results use the same
  canonical projection. Add `discovery-net math ...` without user-facing colors or
  version arguments. Decide legacy command aliases separately from wire compatibility.

Acceptance: candidate and adopted queries agree on the fixture; partial migration
cannot become canonical; reruns are safe; existing contribution IDs are unchanged.

### 6. Rehearse the full upgrade locally and prepare release

- Run the historical replay and migration on an isolated copy. Test at least a
  validator and non-voting full node, restart/recovery, interrupted migration,
  rejection cases, and identical committed state hashes.
- For exact historical envelope tests retain their original chain context offline;
  a fresh chain ID changes artifact identities. Do not attach the rehearsal to live
  peers or copy production validator signing keys into a running test validator.
- Reconcile the plan with a fresh pre-release snapshot or explicit ledger delta.
  New submissions since the baseline need a defined migration treatment.
- Run the existing full suite and relevant multi-node integration checks once the
  implementation is stable. Compare representative graph queries and costs.
- Prepare an exact operator sequence: compatible node rollout, coordinated protocol
  activation where needed, migration publication, completeness check, canonical
  projection promotion, and query-service rollout.
- Record recovery boundaries. Before activation, discard the candidate. After new
  formats are committed, old binaries may not replay; changing the query projection
  back does not undo committed artifacts or make old node software compatible.
- Remove development candidate selectors and comparison UI from the release surface.
  Retain legacy decoders, migration evidence, and regression fixtures.

Acceptance: documented rehearsal evidence supports release of one canonical math
topology. Live publication and deployment are a later release action, not part of
this planning change.

## Open design inputs

The exact new math node/edge vocabulary, the replacement scope, and the authority
for future canonical selection changes remain to be defined. Start with concrete
graph examples rather than a generalized schema registry. A production security
model can follow once the core boundary is demonstrated.

## Follow-up: PR #60, identities, and topology authority

Design input: [PR #60](https://github.com/njallskarp/discovery_net/pull/60),
`Add human trust and reputation design doc` by sigtryggurk. This remains a proposal;
the following are recommendations for the development branch, not accepted policy
or implemented security guarantees.

Adopt its separation of human identity, area-scoped standing, and endorsed area
hierarchy changes. Identity belongs in a shared domain-independent layer; math
credentials and the area ontology belong in the math module. Validator membership
is an explicit governance grant and must not be inferred from research reputation.
The same person can hold several independently revocable grants.

Represent an identity claim separately from network recognition. Recognition needs
evidence review, candidate key-control/consent proof, and authorized attestations.
A threshold of signatures proves approval by the signers, not unique personhood or
mathematical expertise. Preserve historical author envelopes and link their signing
keys to identities through attributable bindings, with key rotation/recovery rules.

Use a shared proposal/approval mechanism with action-specific policies:

- Recognition of a human identity.
- Addition/removal of a validator and binding of a separate governance key.
- Delegation/revocation of identity-attester or area-curator authority.
- Adoption/revocation of a specific ontology assertion or migration manifest.

For initial validator-governed admission, recommend strictly more than two thirds
of eligible voting power: `3 * approving_power > 2 * eligible_power`. Equal-power
validators reduce this to `floor(2*N/3) + 1` distinct approvals. Each validator has
at most one effective approval per proposal. Approvals are explicit signed
transactions, not implicit endorsements inferred from signing a consensus block.
Bind the signed context to chain, action, exact subject/proposal, validator-set
epoch, and expiry. Serialize membership changes initially; expire and re-propose
unresolved decisions after an electorate change. Define bounded pending state and
require a current authorized sponsor for on-chain admission proposals.

Keep governance signatures separate from consensus and routine research keys.
Membership changes must update CometBFT as well as graph/query state. Test the
protocol activation delay, restart/replay, and restrictions on unsafe set changes.
The older `origin/codex/dynamic-validator-governance` branch has candidate consent,
separate keys, asynchronous approvals, and scheduled changes; audit and port useful
pieces rather than merging the old branch wholesale. It was built around genesis
governance configuration, so bootstrapping governance on the existing live chain
needs a separately reviewed upgrade and initial key-binding procedure.

Make ontology authority non-circular: proposed area placement must not grant the
standing needed to approve itself. Check authorization against prior committed
authority. Define any upward/downward standing rule explicitly and test it with
examples. Give attestations individual artifact identities so a withdrawal can
target a single assertion. Canonical topology selection does not delete old edges.

Reject invalid or unauthorized actions without automatic permanent punishment.
Unauthenticated input is not evidence against the claimed signer; relaying a
transaction is not endorsing it. Use bounded proposals and local ingress limits for
spam. Use explicit evidence and authorized, scoped revocation for misconduct. IP
blocking is local operational control, not global identity or consensus authority.
Removing a validator, revoking an attester, and restricting publication are separate
actions; historical research remains attributable and independently assessable.

For scale, reserve validator-wide decisions for membership, initial trust roots,
and delegation. A later authorized attester group can handle routine human checks;
math curators can handle ontology growth. Keep experimental reputation scoring in
query projections, not consensus or validator-admission rules. Delegation changes
who is trusted and needs explicit policy, limits, and revocation.

Sequence adjustment: include these role distinctions and threat cases in step 1;
extract shared identity/governance interfaces in step 2; pilot areas and subareas in
step 3. Split step 4 into reviewable governance-state and domain-validation changes.
Keep automated sanctions, sophisticated reputation scoring, and anti-automation
claims outside the first topology release.
