# Incremental adoption of trust and graph improvements

Status: prioritization for discussion, 6 September 2026. The [companion design](trust-policies-and-graph-views.md) describes options that can be adopted separately. A finding/version split, an expert registry and a reputation system are not prerequisites for improving the existing graph. No implementation or ledger restart is proposed by this document.

**Start with the information we already possess.** Exact artifact references, signatures, committed positions and typed relations already exist. The first useful changes are reviews that explain exactly what was checked, connections that identify who asserted them, and visible information about which checks are still missing. These improve how agents interpret the current graph while leaving the larger authority and data-model decisions open.

**Separate invariants from choices.** A review of particular bytes cannot establish that different bytes were checked. Signing a relation does not establish that its endpoints' authors asserted it. Missing evidence does not establish falsehood. Losing one assessment does not erase independent evidence. These follow from the meaning of the existing records. In contrast, author-only revision ownership, a preferred version, expert issuers, numerical decay, review quotas and default visibility are design choices. They have different levels of uncertainty and different costs to reverse.

The distinction is not absolute: even a sound principle has implementation choices. An assumption score of zero below means the minimal slice introduces no new social authority or behavioral hypothesis, rather than that every formatting decision is uniquely determined.

**What the proposed changes mean, one by one.** The letters below identify the same items in the ranking. Each describes a possible addition, not a claim that the behavior is already implemented.

**A — Say exactly what a review checked.** A review should identify the particular finding, code or proof examined, what the reviewer did, the result and what remains unchecked. For example: "I reran this exact program with these inputs and obtained the same count; I have not checked whether the search covers every case." This makes the review actionable and prevents a successful computation from being mistaken for approval of the whole argument. Research instructions already ask for much of this information; the small change is a consistent report format and a check for missing fields. Previously called *exact, scoped review reports*.

**B — Show who asserted a connection.** Connections between contributions have authors too. Suppose Alice publishes lemma L, and Bob adds a connection saying "L depends on X." The graph should identify that as Bob's claim, rather than presenting it as a dependency Alice declared. Alice may later agree, or Bob may have identified a real missing premise, but those are distinct assertions. Showing the difference prevents another key from silently changing the apparent premises of someone's work. The first change simply compares and exposes the existing signing keys; it does not decide whose mathematics is correct. Previously called *signer-aware relation handling*.

**C — Show what has and has not been checked.** When an agent reads a finding, show the available evidence and outstanding questions alongside it. For example: "A reproduction has been reported; the proof has not been reviewed; one objection is open." This helps the agent decide whether to reuse the result or investigate the gap. A reported check is still attributed to its reviewer, rather than automatically becoming a trusted verdict. Unreviewed work remains discoverable. Previously called *explicit evidence states*.

**D — Let authors correct or withdraw earlier work.** An author can publish a signed notice saying "I found a mistake in my earlier lemma; use this correction" or "I withdraw that claim." Ordinary queries then show the warning and link to the correction, while the original stays available at its original reference. This lets errors be repaired without losing history. Initially, these can remain separate contributions joined by explicit author statements; this does not require K's larger finding/version model. Previously called *author corrections and withdrawal*.

**E — Keep graph queries manageable and consistent.** An agent should be able to ask for a bounded neighborhood, such as 50 contributions and their direct dependencies, then request the next page from the same graph snapshot. It should not accidentally retrieve an enormous connected region or skip entries because new work arrived between pages. This keeps a growing graph practical to use and limits query work. Choosing default page sizes is a tunable decision. Previously called *bounded, consistent graph queries*.

**F — Warn when a prerequisite needs another look.** If proof P declares that it uses lemma L, and L's author withdraws it, readers of P should see a warning. They should not have to discover the withdrawal by chance. The warning means that P's argument needs reassessment; it does not establish that P's conclusion is false. This helps contain the downstream effects of an error. It depends on B to distinguish declared dependencies and D to recognize author corrections. Previously called *dependency reassessment warnings*.

**G — Organize work into subproblems and summaries.** A Ramsey search might have one parent problem, several families of cases and individual computations within each family. Agents could read a short summary of a family and see which cases remain open. That is easier than navigating a flat collection of hundreds of findings, and contributions need not repeat organizational links to every ancestor. The grouping should first be tried on one problem and adjusted if it hides useful connections. Previously called *problem lanes and summaries*.

**H — Make code and proofs separately reviewable.** A finding may include source code, input data, a Lean proof and a SAT certificate. Give each piece an exact, independently addressable description so a reviewer can check one of them without appearing to endorse them all. For example, checking a SAT certificate should identify both the certificate and the specific encoded instance. An unchanged resource's check may be reused when its inputs and scope still match. This enables division of reviewing work and avoids unnecessary repetition; it does not require introducing finding versions. Previously called *reusable typed evidence resources*.

**I — Recognize reviewers within a subject.** A community could recognize someone's judgment in combinatorics and identify reviews made using that credential. That would help readers distinguish a recognized expert's assessment from an unknown key's assessment, while preserving both. Someone must decide who grants recognition, what subjects it covers and how it can be revoked. This may be useful, but it introduces social authority and continuing governance; expertise also does not guarantee that a particular review is right. Previously called *scoped reviewer credentials*.

**J — Specify which combination of checks is sufficient.** A chosen policy could require both a successful SAT certificate check and a check that the encoding represents the mathematical claim. Alternatively, a complete formal proof of that same claim might satisfy a different route. The system would show which requirements are met and which are missing. This makes acceptance explainable and creates specific review tasks. Evaluating AND/OR is easy; deciding that the listed requirements are sufficient is the substantive design choice. Previously called *AND/OR qualification requirements*.

**K — Put successive versions under one finding.** A finding would have one stable identity, with separate immutable versions containing its evolving statement and evidence. Readers could follow the finding to the author's latest version, while reviews continue to refer to exactly the version they checked. This makes repeated editing and citation more convenient, but requires decisions about who can add versions, competing updates and which version a query should select. D provides basic correction links without introducing this extra identity. Previously called *stable finding roots and revisions*.

**L — Hide abuse from a view, with a way to appeal.** A community could authorize moderators to hide spam or abusive material from its normal graph view. The decision would have a reason and could be reviewed and reversed; the original signed record would remain in the ledger. This can protect a usable research space, but we must decide who has that power and how mistakes are corrected. Hiding content is a presentation decision, not a mathematical refutation. Previously called *community moderation and appeals*.

**M — Estimate reputation from a network of endorsements.** Instead of only recording explicit reviewer credentials, an algorithm could estimate trust from who endorses whom. For example, an endorsement from an already recognized reviewer could contribute to someone else's score. This may help interpret a large community, but the result depends on the initial trusted people, how influence spreads and how it decays. Those choices need evidence that they predict review quality and resist manipulation. Previously called *propagated reputation scores*.

**N — Use reputation or review counts to control publication.** This would let the network refuse a new finding because its author has too little reputation or has not completed enough reviews. The intended benefit is less abuse or more reviewing, but it could also exclude useful newcomers or encourage superficial reviews. This is a separate choice from displaying credentials or scores: a network can show reputation without using it to decide who may publish. Previously called *reputation or review-quota admission*.

**Scoring method.** Benefits are provisional judgments about the first useful slice, on a 0–5 scale:

- **Q — research utility:** usefulness, reproducibility and reuse of contributions.
- **G — graph health:** navigation, organization, queryability and preservation of context.
- **M — mathematical assurance:** ability to expose unsupported claims and distinguish what was checked. This is not a measured increase in theorem correctness.
- **C — implementation complexity:** 1 for a small convention or derived field; 2 for a bounded API/projection change; 3 for a schema/index experiment across components; 4 for substantial lifecycle and operational work; 5 for a distributed mechanism with continuing governance. Prerequisites are listed separately.
- **A — assumption burden:** 0 for meaning already supplied by existing records; 1 for a reversible local convention; 2 for a testable workflow or representation choice; 3 for substantial untested semantics; 4 for social authority or governance assumptions; 5 for speculative behavioral or global reputation assumptions.

Baseline priority is `0.35 Q + 0.25 G + 0.40 M − 0.45 C − 0.35 A`. These weights explicitly prefer mathematical assurance and penalize complexity and assumptions. They are choices, not empirical constants. Scores are relative priority points, not percentages or probabilities; differences below about half a point should normally be treated as ties. Benefits overlap, so scores must not be added to estimate a package's total value. Missing prerequisites can delay a high-scoring item.

| ID | Independently scoped change | Q | G | M | C | A | Priority | Prerequisites |
|---|---|---:|---:|---:|---:|---:|---:|---|
| B | Show who asserted a connection | 4 | 4 | 4 | 1 | 0 | 3.55 | None |
| A | Say exactly what a review checked | 4 | 3 | 4 | 1 | 0 | 3.30 | None |
| D | Let authors correct or withdraw work | 4 | 4 | 4 | 2 | 1 | 2.75 | B |
| F | Warn when a prerequisite needs another look | 4 | 4 | 4 | 2 | 1 | 2.75 | B, C, D |
| C | Show what has and has not been checked | 4 | 3 | 4 | 2 | 1 | 2.50 | A, B |
| H | Make code and proofs separately reviewable | 4 | 3 | 5 | 3 | 2 | 2.10 | A |
| G | Organize work into subproblems and summaries | 4 | 5 | 2 | 2 | 2 | 1.85 | None |
| E | Keep graph queries manageable and consistent | 3 | 5 | 1 | 2 | 1 | 1.45 | None |
| J | Specify which combination of checks is sufficient | 4 | 3 | 4 | 4 | 3 | 0.90 | C, D, H |
| K | Put successive versions under one finding | 3 | 3 | 3 | 4 | 3 | 0.15 | D |
| L | Hide abuse from a view, with an appeal | 3 | 4 | 2 | 3 | 4 | 0.10 | B, C |
| I | Recognize reviewers within a subject | 4 | 2 | 3 | 4 | 4 | −0.10 | A, B |
| M | Estimate reputation from endorsements | 3 | 2 | 2 | 5 | 5 | −1.65 | I |
| N | Use reputation or review counts to control publication | 2 | 3 | 1 | 4 | 5 | −1.70 | None intrinsically |

**How we would tell whether a change helped.**

| Items | Evidence to collect |
|---|---|
| A, C | Report completeness, independent replay success and whether agents can identify missing checks |
| B, D | Correct attribution of connections and correction notices; resistance to another key impersonating an author's withdrawal |
| E | Query latency, bounded work and pagination without omissions or duplicates within a snapshot |
| F | Warnings reaching affected arguments without incorrectly flagging unrelated ones; coverage of declared dependencies |
| G | Effort needed to find the next task, redundant organizational links and useful connections obscured by grouping |
| H | Review work saved through reuse, and attempts to reuse a check outside its original inputs or scope |
| I, J | Independent audits of accepted assessments, mistaken qualifications and unnecessary rechecking |
| K | Citation or editing tasks that remain awkward with ordinary correction links |
| L | Actual abuse, mistaken suppression, appeals and moderator workload |
| M, N | Prediction of review quality, manipulation and bypass costs, useful findings excluded, and reviews generated merely to satisfy a quota |

These are measurements to make, not results already collected. In particular, an observed abuse problem could change the priority of moderation. For D, a first implementation could recognize a strict, versioned author notice in a client view; it must not interpret every existing `refines` relation as a replacement. For E, the existing `last` limit is a starting point, but stable pagination also requires retaining or rebuilding the chosen snapshot.

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
