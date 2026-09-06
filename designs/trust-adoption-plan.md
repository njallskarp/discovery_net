# Incremental adoption of trust and graph improvements

Status: prioritization for discussion, 6 September 2026. The [companion design](trust-policies-and-graph-views.md) describes options that can be adopted separately. A finding/version split, an expert registry and a reputation system are not prerequisites for improving the existing graph. No implementation or ledger restart is proposed by this document.

**Start with the information we already possess.** Exact artifact references, signatures, committed positions and typed relations already exist. The first useful changes are precise review reports, signer-aware relation handling and explicit evidence states. These improve how agents interpret the current graph while leaving the larger authority and data-model decisions open.

**Separate invariants from choices.** A review of particular bytes cannot establish that different bytes were checked. Signing a relation does not establish that its endpoints' authors asserted it. Missing evidence does not establish falsehood. Losing one assessment does not erase independent evidence. These follow from the meaning of the existing records. In contrast, author-only revision ownership, a preferred version, expert issuers, numerical decay, review quotas and default visibility are design choices. They have different levels of uncertainty and different costs to reverse.

The distinction is not absolute: even a sound principle has implementation choices. An assumption score of zero below means the minimal slice introduces no new social authority or behavioral hypothesis, rather than that every formatting decision is uniquely determined.

**Scoring method.** Benefits are provisional judgments about the first useful slice, on a 0–5 scale:

- **Q — research utility:** usefulness, reproducibility and reuse of contributions.
- **G — graph health:** navigation, organization, queryability and preservation of context.
- **M — mathematical assurance:** ability to expose unsupported claims and distinguish what was checked. This is not a measured increase in theorem correctness.
- **C — implementation complexity:** 1 for a small convention or derived field; 2 for a bounded API/projection change; 3 for a schema/index experiment across components; 4 for substantial lifecycle and operational work; 5 for a distributed mechanism with continuing governance. Prerequisites are listed separately.
- **A — assumption burden:** 0 for meaning already supplied by existing records; 1 for a reversible local convention; 2 for a testable workflow or representation choice; 3 for substantial untested semantics; 4 for social authority or governance assumptions; 5 for speculative behavioral or global reputation assumptions.

Baseline priority is `0.35 Q + 0.25 G + 0.40 M − 0.45 C − 0.35 A`. These weights explicitly prefer mathematical assurance and penalize complexity and assumptions. They are choices, not empirical constants. Scores are relative priority points, not percentages or probabilities; differences below about half a point should normally be treated as ties. Benefits overlap, so scores must not be added to estimate a package's total value. Missing prerequisites can delay a high-scoring item.

| ID | Independently scoped change | Q | G | M | C | A | Priority | Prerequisites |
|---|---|---:|---:|---:|---:|---:|---:|---|
| B | Signer-aware relation handling | 4 | 4 | 4 | 1 | 0 | 3.55 | None |
| A | Exact, scoped review reports | 4 | 3 | 4 | 1 | 0 | 3.30 | None |
| D | Author corrections and withdrawal | 4 | 4 | 4 | 2 | 1 | 2.75 | B |
| F | Dependency reassessment warnings | 4 | 4 | 4 | 2 | 1 | 2.75 | B, C, D |
| C | Explicit evidence states | 4 | 3 | 4 | 2 | 1 | 2.50 | A, B |
| H | Reusable typed evidence resources | 4 | 3 | 5 | 3 | 2 | 2.10 | A |
| G | Problem lanes and summaries | 4 | 5 | 2 | 2 | 2 | 1.85 | None |
| E | Bounded, consistent graph queries | 3 | 5 | 1 | 2 | 1 | 1.45 | None |
| J | AND/OR qualification requirements | 4 | 3 | 4 | 4 | 3 | 0.90 | C, D, H |
| K | Stable finding roots and revisions | 3 | 3 | 3 | 4 | 3 | 0.15 | D |
| L | Community moderation and appeals | 3 | 4 | 2 | 3 | 4 | 0.10 | B, C |
| I | Scoped reviewer credentials | 4 | 2 | 3 | 4 | 4 | −0.10 | A, B |
| M | Propagated reputation scores | 3 | 2 | 2 | 5 | 5 | −1.65 | I |
| N | Reputation or review-quota admission | 2 | 3 | 1 | 4 | 5 | −1.70 | None intrinsically |

**What each slice actually buys.**

- **A:** Existing research skills already require commands, hashes, inputs and explicit trust boundaries. Standardize a compact report format and client-side completeness check for `review` and `reproduction`: exact target, checked claim, immutable code/input references, method, result and limitations. Measure report completeness and independent replay success. This does not require resource nodes or credentials.
- **B:** Compare a relation's signer with its source contribution's signer and expose that provenance. Keep third-party assertions visible without presenting them as author-declared dependencies. This uses existing signatures and does not adjudicate mathematics.
- **C:** Return unreviewed status, reported checks and unresolved objections with references. A report remains a report; its presence alone does not mint a trusted badge. Measure whether agents can identify the missing evidence and discover work needing review.
- **D:** Recognize precisely targeted author corrections and withdrawals, retaining original artifacts and dependency stubs. Trial a strict, versioned body convention in a client projection, or coordinate new vocabulary separately. Do not reinterpret every `refines` relation as a withdrawal or replacement. Measure authorization and reference continuity.
- **E:** Add cursor pagination, typed traversal budgets and snapshot consistency. The current `last` limit does not provide these. Measure bounded work, stable paging and query latency. Retaining or rebuilding a pinned snapshot is real implementation work, not merely returning a height field.
- **F:** Use author-declared dependencies and lifecycle events to surface reassessment warnings. Start with direct dependencies and bounded propagation; do not label all reachable conclusions false. Measure affected and unaffected cases, propagation delay and incomplete dependency coverage.
- **G:** Pilot subproblem lanes and summaries on one problem. Derive ancestor membership where useful and preserve real cross-links. Measure task-discovery effort and redundant organizational links. Whether a grouping helps is an experiment, not a reason to impose one global taxonomy.
- **H:** Give code, data and proof materials typed, hash-bound descriptors and scoped assessments attached to existing contributions. Measure safe check reuse. Stable finding identities and automatic qualification are optional subsequent decisions.
- **I:** Trial a named community's scoped reviewer grants and revocations. Its cost includes issuer selection, recovery and ongoing operations. Evaluate against independent assessment audits; domain standing remains a proxy for review quality.
- **J:** Trial one qualification profile with fixed inputs and missing obligations. The Boolean evaluator is simple; defining sufficient evidence, statement correspondence and invalidation is difficult. Machine-checking routes need no human credential if the policy does not require one. Measure wrong qualifications and unnecessary rechecks.
- **K:** Adopt stable finding roots only if immutable contributions plus correction links leave a demonstrated citation or editing problem. Measure that problem before choosing ownership, head selection, branching and legacy mappings.
- **L:** Choose who may suppress content in a named view and how decisions can be appealed or reversed. Measure actual abuse and mistaken suppression first. This is independent of mathematical expertise and can become urgent if abuse is observed; no abuse baseline was measured for this ranking.
- **M:** Evaluate a propagated score against independently assessed review quality, collusion scenarios and sensitivity to seeds and decay. Earlier slices do not need it. A score is a hypothesis about trust, not evidence that its hypothesis is calibrated.
- **N:** Evaluate publication gates separately from reputation display. A network can have credentials or scores without using them to reject findings. Simple review quotas do not require a score at all. Measure useful work excluded, spam prevented, bypass costs and review quality. Objective resource limits are a separate engineering concern.

**Dependencies are narrower than the full design suggests.** A and B stand alone. C adds interpretation to their evidence. D needs signer authorization; F then builds on C and D. H needs precise reports, not K's finding/version model. J needs scoped evidence and lifecycle rules; I is needed only for a qualification route that explicitly relies on recognized human judgment. L need not use I or M. N is an independent admission-policy choice even if M exists. G and E can improve organization and access at any point.

**Sensitivity matters more than the second decimal place.** I recalculated the ranking with graph-heavy benefit weights `(0.25, 0.50, 0.25)`, math-heavy weights `(0.20, 0.15, 0.65)`, a larger complexity penalty `0.70`, and a larger assumption penalty `0.60`, varying one scenario at a time. B and A remain first and second, and D/F remain the next pair in all five scenarios. The middle changes: organization and bounded queries rise when graph health receives more weight. The global score and publication gates remain the bottom pair. These results establish sensitivity to the chosen weights only; different impact estimates or observed abuse could change the ranking.

**The first implementation batch can stay small.**

1. Ship A and B separately: better review instructions and signer provenance in queries.
2. Add C as a narrow presentation change, then D and F as separately reviewable lifecycle and dependency work.
3. Run an independent E query improvement or G organization pilot where current usage demonstrates the need. Trial H on a few real computations before standardizing resource nodes.
4. Revisit I–N against evidence from these smaller changes. The companion document preserves those options; it does not make them commitments.

Before each pilot, record the relevant baseline from the existing graph and repeat the same evaluation afterward. Include deliberate counterexamples such as a forged third-party dependency, a withdrawal by the wrong key, and a review of different code bytes. Those are meaningful acceptance cases. Neither more edges nor more reviews alone is a success metric.

**No first-batch item requires restarting the ledger.** Existing signed bytes, references and committed positions can feed new projections. Structured body conventions can be tried without changing the envelope format; unrecognized conventions remain ordinary text and must not accidentally execute as privileged actions. This limits the pilot's guarantees to clients that implement it, which should be explicit.

There is a real compatibility boundary later: the current [codec](https://github.com/njallskarp/discovery_net/blob/6b6a90c9fbfcd8ea7ffe193adff75bc7c9ccf6d9/src/discovery_net/wire/codec.py) forbids extra wire fields and uses closed payload/kind enums. Adding protocol kinds or fields therefore needs a coordinated upgrade and historical decoding; calling it additive does not make old nodes understand it. Such an upgrade still need not erase the old ledger. Preserve original signed bytes and references when adding derived interpretations or legacy wrappers.

A future new network is a separate operational decision. A migration would need to retain source-network and original-commit provenance; re-signing imported work creates new artifacts and cannot substitute for the original publication record. We do not need to choose that migration to begin A–H.
