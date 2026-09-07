# Six-PR implementation plan: domains and canonical math topology

Integration branch: `codex/domain-topology-development`, rebased onto main at
`673c8b8` (including Siggi’s PR #58).
This supersedes the earlier eighteen-PR sequence. The smaller implementation steps
are commits inside the six PRs below, not separate review requests.

PRs 1–5 target the integration branch in order. PR 6 is the release PR from that
branch to main, including the final rehearsal evidence and rollout instructions.
Main and live nodes remain on the existing release during development. Keep the
integration branch current with main and rebase each pending PR onto it. PR 6 is
reviewed as one cumulative diff and squash-merged into main after validation.

Development isolation belongs in Git branches. Packages and class names describe
their lasting responsibilities. A temporary parallel implementation must use a
`V2` suffix and a nearby comment of this form:

```python
# TODO: remove versioning once migration is complete. Temporary replacement for
# ClassName in discovery_net.module_name; promote this implementation and remove
# the superseded implementation before the integration branch merges to main.
```

Use the actual class/module references in each comment. Record whether each new
class is moved, refactored, or new in the PR description. PR 1 introduces permanent
boundaries and needs no parallel V2 implementations.

## Fixed boundaries

- Preserve existing contribution envelopes, signatures, and hashes exactly.
- Users see one canonical math topology. Candidate colors are development-only.
- Validators and non-voting full nodes execute identical deterministic rules.
- Separate human recognition, area standing, curator authority, and validator membership.
- Initial governance requires strictly more than two thirds of eligible voting
  power, explicit proposal approvals, candidate consent, and separate governance keys.
- Reject unauthorized actions; do not automatically ban senders or use IP addresses
  as global identities. Reputation scoring does not govern consensus.
- Implement math and a second-domain contract test. A production security ontology,
  automated sanctions, and advanced reputation are later work.

## PR 1 — Separate core and math, with compatibility and snapshot tooling

Review: [#62](https://github.com/njallskarp/discovery_net/pull/62).
Branch: `codex/legacy-graph-contracts`. Depends on: none.

Commit order:

1. Freeze existing bytes, signatures, IDs, transaction results, replay hashes, and
   representative graph queries.
2. Add an offline baseline export command: SQLite read-only connection,
   backup to a new destination, replay verification, and a manifest containing
   chain, height, state hash, checksum, artifact counts, and source revision.
3. Move mathematical models and vocabulary into `domains/math`, retaining
   compatibility imports and exact payload codecs.
4. Separate raw artifact/provenance indexing from graph projection. Route existing
   queries through `MathProjection` and exercise the domain boundary with
   a small second-domain test fixture.

Primary files: `knowledge_graph/`, new `domains/math/` and `snapshots/`,
`indexing/`, `query/`, compatibility and snapshot tests.

Merge gate: historical fixtures stay unchanged; source ledger is untouched; backup
works with concurrent WAL writes; rebuilt/incremental indexes agree; current CLI
and GraphQL behavior remains identical. No new live protocol behavior.

## PR 2 — Build and validate the candidate math topology locally

Branch: `codex/math-topology-candidate`. Depends on: PR 1.

Commit order:

1. Define an unsigned topology plan with a pinned baseline digest, retained
   contribution IDs, new area nodes, explicit old-area mappings, and selected
   replacement organizational edges. Use reviewed taxonomy input with provenance.
2. Implement deterministic build/inspect/compare commands. Reject missing endpoints,
   cycles, duplicate mappings, and baseline mismatches. Report ambiguous mappings
   as unresolved; do not infer identity from matching titles.
3. Add a development preview using the existing inspector and the new projection
   boundary. Compare area navigation, problem placement, dependencies, objections,
   orphaned research, and bounded query cost.
4. Record and resolve mapping decisions against the real copied ledger. Retain
   scientific and discussion edges while replacing the organizational links named
   in the plan.

Primary files: `domains/math/topology.py`, snapshot tooling,
inspector configuration, candidate fixtures and comparison tests.

Merge gate: the concrete candidate topology works on real data; reruns produce
the same plan digest; unchanged contributions retain their IDs; every omitted or
replacement edge has provenance. No signed publication or consensus upgrade yet.

## PR 3 — Implement threshold governance and post-genesis validators

Branch: `codex/validator-governance`. Depends on: PR 2.

Commit order:

1. Add proposal, approval, and candidate-consent formats with separate signing
   contexts. Bind chain, action, exact subject, electorate epoch, nonce, and expiry.
   Review and selectively port the old dynamic-governance branch.
2. Implement the pure governance state machine: authorized sponsorship, distinct
   weighted votes, strictly greater-than-two-thirds threshold, bounded pending
   proposals, expiration, exactly-once execution, and one scheduled membership
   change at a time. Expire unresolved proposals when the electorate changes.
3. Add a coordinated activation manifest and initial validator/governance-key
   bindings. Persist governance with artifact state atomically; replay historical
   rules by original block height and define the application-hash transition.
4. Emit actual CometBFT validator updates at the correct activation height. Enforce
   unique keys, a nonempty validator set, power limits, and candidate consent.
5. Add candidate preparation, proposal, approval, and status CLI commands plus
   full-node/validator startup profiles using the same image and separate keys.

Primary files: `wire/governance*`, `node/governance/`, callback handler, ABCI,
snapshot replay/store, runtime provisioning, CLI and submission modules.

Merge gate: signature replay/substitution tests, unequal voting power, duplicate
approvals, stale epochs, activation/restart tests, and a real multi-node test that
adds and removes validators while full nodes derive the same application hash.
Operator commands use test keys during development; no live admission.

## PR 4 — Add identities, scoped credentials, and approved area relationships

Branch: `codex/identity-and-math-authority`. Depends on: PR 3.

Commit order:

1. Add the minimum new domain node/assertion formats needed by identities and math.
   Keep existing wire formats untouched. Allow individually identifiable attestations
   and withdrawal targets; validate endpoint types through registered domain rules.
2. Add identity applications, evidence references, candidate key consent, and
   threshold-approved recognition. Separate pending claims from recognized identities.
3. Implement key bindings, rotation, revocation, and governed recovery, preserving
   historical authorship. Consensus checks signed evidence references, never live
   web pages or claims of unique humanity.
4. Add area-scoped credentials and separately governed curator grants. New area
   placements remain provisional until approved by an authorized curator; top-level
   structural changes require governance.
5. Add individual issuer withdrawal and governed revocation. Derive authorization
   from previously committed authority so a proposed edge cannot approve itself.

Primary files: shared identity domain, `domains/math/`, domain wire resolver,
governance grant handlers, identity/credential queries, authorization tests.

Merge gate: self-issued claims cannot create recognition or authority; key rotation
does not change old contribution IDs; forged subarea paths and scope escape fail;
targeted revocation preserves independent attestations and research evidence.
Ordinary research remains possible without human recognition.

## PR 5 — Publish the migration and expose one canonical math interface

Branch: `codex/canonical-math-migration`. Depends on: PR 4.

Commit order:

1. Convert the reviewed offline plan to signed new nodes/assertions with fixed
   timestamps, provenance, expected artifact IDs, and a resumable receipt manifest.
2. Stage migration artifacts across bounded transactions. Add a threshold-approved
   adoption action committing to the complete manifest and replacement scope.
   Adoption cannot activate while required artifacts are missing.
3. Reconcile submissions since the baseline and define how subsequent area links
   enter the adopted graph. Canonical selection is explicit, not a timestamp filter.
4. Expose `discovery-net math ...`; route CLI, GraphQL, inspector, counts, and
   traversals through the same canonical projection. Preserve raw historical lookup
   and compatible old command aliases.
5. Remove candidate color/version controls from the release-facing UI and CLI.

Primary files: migration builder/submitter, adoption governance handler, canonical
projection selector, CLI, GraphQL, inspector, migration and interface tests.

Merge gate: unchanged contribution IDs, safe repeated/interrupted publication,
complete adoption checks, baseline-delta reconciliation, correct future edges, and
agreement across every query surface. Old edges remain attributable in history.

## PR 6 — Rehearse and release the complete change to main

PR: `codex/domain-topology-development` → `main`. Depends on: PRs 1–5.

Commit order:

1. Reconcile integration with current main. Capture a fresh baseline and replay it
   offline with its original chain context, without production validator keys or
   connections to live peers.
2. Run active consensus separately with test keys: upgrade activation, validator
   admission/removal, identity/key revocation, interrupted migration, adoption,
   concurrent research, restart, and non-voting full-node verification.
3. Record exact source/config/manifest hashes, topology comparisons, query costs,
   and full test results, including pinned CometBFT and Docker integration checks.
4. Add the operator rollout and recovery runbook: compatible software first,
   coordinated activation, migration staging, completeness checks, then canonical
   query promotion. Document that old binaries may not replay new formats.
5. Remove temporary V2 replacements, version selectors, migration-only scaffolding,
   and their removal TODOs. Promote the validated topology under canonical names.
   Preserve historical decoding and intentional public import aliases as needed.
6. Present the cumulative release diff with links to PRs 1–5 and their evidence;
   squash-merge the validated integration branch into main.

Merge gate: reproducible full rehearsal, passing required checks, reconciled
migration, and an exact rollout/recovery procedure. Live activation and publication
remain explicit operator actions after release, not automatic effects of merging.

## Mapping from the previous plan

| New PR | Former implementation steps |
|---|---|
| 1 — Core/math separation | 01–04 |
| 2 — Local topology | 05–06 |
| 3 — Governance/validators | 08–12 |
| 4 — Identity/math authority | 07, 13–14 |
| 5 — Migration/interfaces | 15–16 |
| 6 — Rehearsal/release | 17–18 |

Governance transaction formats in PR 3 are independent of domain assertion formats
in PR 4. This ordering lets the approval engine be tested before it is used to
recognize humans or authorize topology changes.
