# Implementation PR sequence: domains, identities, and canonical math topology

Integration branch: `codex/domain-topology-development`, starting at `652f4de`.
This document replaces the coarse sequence in `domain-topology-development.md`.
PR numbers below are sequence numbers, not GitHub issue numbers.

## Delivery rules and initial decisions

- Submit each PR against the integration branch, in the order below. Merge that PR
  before branching the next from the updated integration head. Main and live nodes
  remain on the existing release until the final release PR.
- Each PR includes focused tests for its behavior. The first compatibility fixture
  is immutable regression evidence, not something regenerated to make tests pass.
- The release exposes one canonical topology and `discovery-net math ...`. Candidate
  colors exist only in development tools. Preserve old signed envelopes and their
  decoders; do not add metadata to existing contributions or resign them.
- Consensus keys, operator governance keys, and research keys have separate roles.
  Full nodes execute the same rules as validators, even when they do not vote.
- Initial privileged grants require strictly more than two thirds of eligible
  validator voting power, bound to an electorate epoch. One effective approval per
  validator per proposal. Pending proposals expire on electorate changes. One
  validator-set change may be scheduled at a time; admission requires key-control
  proof and consent. Candidate power is bounded by the agreed admission policy.
- Human recognition, credential standing, ontology curation, and validator membership
  are independently revocable grants. Credentials alone never confer validator power.
- Identity verification is an attestation backed by reviewed evidence, not proof of
  unique humanity. Consensus never fetches an external profile or runs an LLM.
- Reject unauthorized operations; do not automatically ban their sender. Scoped
  revocation requires an authorized decision. IP rate limits remain local operations.
- First-release canonical area curation uses explicit scoped curator grants. Keep
  experimental trust scores out of consensus. This is a deliberate constrained
  implementation of #60, not its full reputation/anti-automation system.

## 01 — Freeze legacy wire, replay, and graph behavior

Branch: `codex/legacy-graph-contracts`. Depends on: none.

Files: `tests/fixtures/legacy_graph/`, `tests/test_legacy_graph_contract.py`.

Check in canonical signed transaction bytes generated once by the unmodified
baseline, a manifest of artifact IDs, per-block transaction result codes and state
hashes, and a representative GraphQL query with its expected result. Include two
authors, area/subarea relationships, research dependencies, third-party assertions,
same-transaction forward references, duplicate and invalid submissions, and an empty
block. Replay through the real callback handler and SQLite store, then restart and
query. No application changes.

Acceptance: exact byte round trips and signature verification; fixed IDs/results/
hashes through execution and restart; rejected transactions never enter the ledger;
incremental and rebuilt indexes give the fixed expected graph results.

## 02 — Export a verified offline baseline

Branch: `codex/offline-ledger-baseline`. Depends on: 01.

Files: new `src/discovery_net/development/ledger_baseline.py`, developer CLI module,
`tests/test_ledger_baseline.py`. Add a development-only module entry point.

Implement `python -m discovery_net.development baseline --ledger PATH --output DIR
--chain-id ID`. Read the source with SQLite `mode=ro`, use the backup API into a new
destination, and verify the copy through replay. Write a manifest with chain ID,
height, state hash, snapshot checksum, artifact counts, and source revision. Refuse
existing output or source/destination aliasing. Publish the completed output only
after verification; no source database writes or live submissions.

Acceptance: backup remains internally consistent with concurrent WAL writes; source
bytes/state are unmodified; corrupt/wrong-chain data and output collisions fail
cleanly. Capture a local real baseline after the command passes fixture tests.

## 03 — Extract the existing math domain without changing bytes

Branch: `codex/extract-math-domain`. Depends on: 02.

Files: new `src/discovery_net/domains/math/`, `knowledge_graph/{models,enums,
identifiers,__init__}.py`, affected imports, domain contract tests.

Move math vocabulary/models behind a domain package. Separate generic artifact
references from mathematical vocabulary. Preserve public compatibility imports and
legacy encoder/decoder behavior. Introduce a small domain interface for payload
decoding and structural validation, exercised by a second-domain test fixture.
Do not add production security contribution kinds yet.

Acceptance: 01 unchanged, existing tests pass, no new payload is accepted on the
network, no enum/string identity changes leak into existing APIs.

## 04 — Separate artifact indexing from graph projection

Branch: `codex/graph-projection-boundary`. Depends on: 03.

Files: `indexing/`, `query/`, legacy math projection module, graph query tests.

Keep one artifact/provenance lookup and let a projection choose domain nodes and
relationships. Make current queries use a legacy math projection preserving current
ordering and traversal behavior. Preserve atomic refresh and incremental append.
Raw artifact lookup must still expose assertions omitted from a projection.

Acceptance: 01 GraphQL result is unchanged; omitting an edge in a test projection
affects forward/reverse traversals and counts consistently without changing raw
artifacts, signatures, or the ledger hash.

## 05 — Build an unsigned candidate area hierarchy

Branch: `codex/math-topology-candidate`. Depends on: 04.

Files: `development/topology_plan.py`, `domains/math/topology.py`, candidate fixture
and development commands `topology build`, `topology inspect`, `topology compare`.

Define a strict local plan format containing source-baseline digest, retained
contribution IDs, proposed new area nodes, replacement edge records, and explicit
old-area mappings. Support a pinned local taxonomy input with provenance; no live
external lookup in generation. Use MSC-derived areas where reviewed mappings exist;
retain ambiguous/unmapped items as explicit unresolved decisions. Do not silently
map areas by title. Initially replace only organizational ABOUT/SUBAREA_OF assertions
selected by the plan; retain scientific and discussion relationships.

Acceptance: missing endpoints, area cycles, duplicate mappings, and baseline
mismatches fail. Repeated builds from the same inputs produce the same plan digest.
Contribution IDs do not change; all omitted/replaced edges are explained.

## 06 — Validate the candidate against research queries

Branch: `codex/math-topology-preview`. Depends on: 05.

Files: development-only inspector launch/configuration, topology query fixtures,
compact local comparison report (no bulk ledger in Git).

Render the candidate with existing contribution bodies and attribution. Exercise
problem-to-area, area-to-subarea, proof-to-problem, dependencies, and review queries.
Compare counts, reachability, orphaned research, duplicate organizational paths,
and bounded query cost. Record explicit decisions for unresolved mappings from 05.
Candidate labels are developer configuration only.

Acceptance: the concrete new graph has a reviewed plan and reproducible evidence.
Keep iterating here if the topology is unsuitable. Do not proceed to its durable
formats merely because a preview can render it.

## 07 — Add domain artifact formats with legacy decoding

Branch: `codex/domain-artifact-codec`. Depends on: 06.

Files: `wire/{envelope,codec,signing}.py`, generic graph models, domain resolver,
wire fixtures and transaction-validator tests.

Add explicit new-format node and assertion payloads carrying a domain/schema
identifier and typed data. Generic assertions may target node or assertion artifacts
where the registered schema permits; this supports individual attestation withdrawal.
Keep historical payload formats distinct and byte-for-byte stable. Domain rules
resolve legacy math nodes as valid endpoints. Separate signature/format verification
from stateful domain authorization. Keep new formats gated off in live acceptance
until the activation machinery in 10.

Acceptance: fixed signing vectors for new formats; unknown schemas fail predictably;
legacy refs resolve; invalid endpoint types fail; changing domain/schema changes the
signature/hash; 01 still passes unmodified.

## 08 — Encode governance proposals and explicit approvals

Branch: `codex/governance-wire`. Depends on: 07.

Files: `wire/governance{,_codec,_signing}.py`, signing vector tests.

Define a bounded proposal with chain, action, subject/payload digest, electorate
epoch, nonce, expiry height, and sponsor; define approvals referring to its ID.
Define validator candidate consent binding consensus and separate governance keys.
Use distinct signing contexts for approvals, candidate consent, and research.
Approvals are separately signed transactions, not multi-author envelopes forced
into the current single-signer transaction format. Audit the older governance branch
for reusable code; do not wholesale merge its outdated state/genesis assumptions.

Acceptance: fixed vectors, cross-chain/action replay rejection, candidate key mismatch
rejection, malformed fields/oversize rejection, and deterministic proposal IDs.

## 09 — Implement deterministic approval and grant state

Branch: `codex/governance-state`. Depends on: 08.

Files: new `node/governance/` state/evaluator, grant and electorate models, pure
transition tests. No live RPC/network side effects in this evaluator.

Implement sponsor authorization, distinct approvals, `3*approved_power > 2*total_power`,
expiry, electorate changes, one scheduled membership change, bounded pending state,
and exact-once execution. Bind grants to subjects and scopes, with explicit revocation
and authorization from state preceding the action. Define deterministic per-sponsor
proposal bounds. A rejected proposal grants nothing and does not ban anyone.

Acceptance: unequal powers, duplicate votes, six-validator boundary (four fail/five
pass), removed voters, stale epochs, expired proposals, conflicting schedules, replay,
and restart-state serialization all have explicit cases.

## 10 — Bootstrap governance and activate the new application rules

Branch: `codex/governance-activation-replay`. Depends on: 09.

Files: `node/{application_state,cometbft_callback_handler,_ledger_from_snapshot}.py`,
store schema/queries, runtime upgrade configuration, upgrade/replay fixtures.

Define a chain-specific upgrade manifest binding activation height, old protocol
identity, domain-rule identifiers, and initial validator-to-governance-key bindings.
Require operator consent from the existing validator keys and a reviewed coordinated
node rollout. Keep old application hashes before activation; commit governance and
artifact state into a defined new application hash afterward. Replay selects rules
by original block height and persists all state atomically. Unknown upgrade/rule
identifiers fail startup or activation, never silently disable checks.

Acceptance: old history reproduces 01; nodes configured with the same upgrade derive
identical post-activation state; before/at/after activation, empty blocks, failed save,
restart and replay match. Back up store migrations and document old-binary boundaries.

## 11 — Connect approved membership to CometBFT

Branch: `codex/dynamic-validator-execution`. Depends on: 10.

Files: `node/abci.py`, callback result models, governance membership transition,
`tests/integration/test_dynamic_validator_governance.py`.

Emit validator additions/removals through `ResponseFinalizeBlock.validator_updates`.
Respect the pinned CometBFT activation delay and prevent overlapping scheduled
membership changes. Enforce configured power limits, unique keys, nonempty set, and
the agreed membership-change bounds. New members cannot vote on their own admission.

Acceptance: real multi-node test admits a synchronized non-validator after genesis,
observes the effective validator set at the correct height, removes a member, and
compares validator/full-node application hashes through restart and replay.

## 12 — Add operator governance commands and deployment profiles

Branch: `codex/governance-operator-cli`. Depends on: 11.

Files: CLI/submission governance modules, runtime identity provisioning, localnet
Compose profiles and operator documentation.

Implement candidate prepare, proposal submit, proposal inspect, approval sign/submit,
and membership status commands. Keep consensus/governance/research keys separate;
ordinary approvals never require exposing the consensus key. Allow a post-genesis
candidate to provision keys and synchronize before scheduled admission. Reuse one
node image for full nodes and validators with role-specific startup configuration.

Acceptance: CLI end-to-end admission using local test keys; wrong-chain and stale
proposal errors are actionable; private keys never enter receipts; full-node startup
does not require voting credentials. Do not execute live admission during this PR.

## 13 — Add human identity claims, recognition, and key lifecycle

Branch: `codex/recognized-identities`. Depends on: 12.

Files: shared identity domain, grant action handlers, identity submission/query API,
identity security and historical-attribution tests.

Add signed identity applications referencing evidence and candidate key consent.
Only threshold-approved recognition enters the recognized-identity projection;
pending claims remain distinguishable. Bind keys to stable identity subjects without
rewriting historical artifacts. Add key rotation, compromised-key revocation, and
threshold-governed recovery with explicit effective heights and key-control proofs.
Store reviewable evidence references/digests, not sensitive identity documents.

Acceptance: self-assertion cannot mint recognition, possession is required, double
counted attestations fail, key rotation preserves historical attribution, revoked
keys cannot authorize new privileged actions, and live HTTP is never consulted by
consensus. Existing research remains accessible without recognized-human status.

## 14 — Add scoped math credentials and ontology curation

Branch: `codex/math-credentials-curation`. Depends on: 13.

Files: math credential/assertion schemas, area-curator grants, effective ontology
projection, authorization/withdrawal tests.

Implement credentials attached to an identity and a specific area; keep recognition,
standing, and curator authority separate. Initial curator grants require governance
approval and explicitly enumerate their allowed scope. An area placement is proposed
first and becomes canonical only after an authorized approval. Top-level additions
require governance. A claim cannot manufacture the parent authority used to approve
it. Revocation targets an exact signed attestation, with issuer withdrawal and
governance revocation distinguished. No automatic broader-area authority from a
floating-point reputation score.

Acceptance: fabricated subarea paths, unauthorized third-party attestations,
self-authorizing cycles, scope escape, and withdrawal of another issuer's assertion
fail. Canonical hierarchy remains acyclic; unrelated independent endorsements and
research evidence survive a targeted revocation.

## 15 — Publish and adopt a complete topology migration

Branch: `codex/topology-migration-adoption`. Depends on: 14.

Files: migration manifest/builder/submission modules, adoption governance action,
canonical projection selector, migration/recovery tests.

Turn the reviewed plan into signed new nodes/assertions with fixed recorded
timestamps and provenance. Produce expected IDs and a resumable receipt map. Stage
across bounded transactions. A threshold-approved adoption proposal commits to the
complete manifest and replacement scope, and becomes effective only after required
artifacts are committed and verified. Define subsequent contributions to use approved
area links; keep unaffected legacy research edges. Reconcile changes since the pinned
baseline explicitly rather than silently excluding new work.

Acceptance: unchanged contribution IDs, idempotent retries, missing batches cannot
activate, snapshot drift is detected, future edges enter the intended projection,
and changing query selection never rewrites the ledger or attributes migration edges
to the original contribution author.

## 16 — Expose canonical domain commands and query surfaces

Branch: `codex/canonical-math-interface`. Depends on: 15.

Files: CLI, submission, GraphQL, inspector, help/docs and API integration tests.

Expose `discovery-net math submit/query/...` using the adopted model. Preserve old
command aliases where their meaning remains unambiguous. Route all normal graph
traversals, counts, area queries, credentials, and provenance through one canonical
projection. Keep raw history available for audit. Provide a domain registration
boundary for a later security implementation, with a second-domain test adapter;
do not ship a placeholder security command that cannot do useful work.

Acceptance: CLI/API/inspector agree on active topology and identity/credential status;
no public version/color switches; orphaned references and hidden-edge traversal leaks
fail tests; development candidate controls are absent from release surfaces.

## 17 — Rehearse the live-chain upgrade and migration

Branch: `codex/topology-release-rehearsal`. Depends on: 16.

Files: isolated rehearsal tooling, integration scenarios, compact evidence report,
operator rollout/recovery runbook.

Replay a fresh baseline offline under its original chain context, without production
validator signing keys or live peers. Separately exercise active voting in a local
network with test keys. Test activation, admission/removal, identity/key revocation,
partial migration, adoption, concurrent new research, restart, and a non-voting
full node. Record exact code/config/manifest hashes and query comparisons. Run full
CI including the pinned CometBFT and Docker checks. Bound changes to those needed
to address concrete failures; split any substantial fix into its own preceding PR.

Acceptance: complete reproducible evidence, no production-key use, consistent state
hashes, migration reconciliation, acceptable query/runtime costs, and an explicit
recovery procedure that does not promise old binaries can read new formats.

## 18 — Release the validated integration branch

Branch: integration branch; PR base: `main`. Depends on: 17.

One release PR contains the reviewed sequence and links its evidence/runbook. Rebase
or merge current main into integration before the final rehearsal if main has moved;
resolve changes and rerun affected evidence. Publish compatible node software first,
coordinate activation, stage migration artifacts, verify completeness, and promote
canonical queries according to the tested procedure. Live deployment/adoption is a
separate explicit operator action after the release PR, not automatic on merge.

Acceptance: reviewed release commit, reproducible builds and manifests, all executing
nodes prepared for activation, and a single canonical user-facing math topology.

## Deferred work

Production security ontology, delegated identity-attestation committees, adaptive
reputation/max-flow scoring, automatic bans/slashing, passkey-based human-review
claims, and fine-grained new research-lane node kinds are separate follow-ups. The
interfaces support extension without making these prerequisites for this release.
