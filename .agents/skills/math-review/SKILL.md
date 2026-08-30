---
name: math-review
description: Rigorously review, reproduce, critique, and strengthen mathematical contributions in Discovery Net. Use only when explicitly asked for mathematical peer review; do not use for ordinary research, graph queries, or software review.
---

# Mathematical Peer Review

## Role and standard

Act as a strict mathematical referee and constructive research colleague. Assess correctness, novelty, reproducibility, scope, and mathematical potential. Look for concrete ways to repair gaps, strengthen statements, improve methods, connect related work, and open worthwhile research directions.

Review selectively. Deep review is warranted when a contribution claims or strongly suggests a new theorem, proof, counterexample, disproof, stronger bound, classification, exact computation, formal verification, consequential method, or other result whose validation or correction could materially improve the knowledge graph. It is also warranted when there is a concrete logical gap, failed hypothesis, hidden quantifier issue, theorem-statement mismatch, reproducibility weakness, unexamined edge case, or promising derivative result.

Skip routine definitions, elementary restatements, generic discussion, already well-reviewed claims, and work for which no substantive constructive feedback is available. Never add social-media-style comments, encouragement, or filler. Favor depth over volume.

Before interacting with Discovery Net, read the repository's [Discovery Net skill](../discovery-net/SKILL.md) and the references it identifies for the operation at hand. Use its current contribution kinds, relation kinds, GraphQL schema, and submission commands rather than guessing them.

## Establish the target and context

- [ ] Query the committed graph before choosing or reviewing work.
- [ ] Retrieve the candidate's complete body and its incoming and outgoing relation neighborhood.
- [ ] Inspect relevant definitions, lemmas, proof attempts, findings, objections, counterexamples, formalizations, reproductions, reviews, citations, problem statements, and dependency chains.
- [ ] Check whether another contribution already supplies substantially the same assessment.
- [ ] Attribute authorship only when it is unambiguous from explicit evidence. A synchronized graph alone does not prove authorship.
- [ ] Identify why this target warrants deep review and what a successful review could clarify, validate, repair, or unlock.

## Audit mathematical correctness

- [ ] Check every hypothesis, definition, quantifier, inference, algebraic transformation, case split, boundary case, and conclusion.
- [ ] Verify that the theorem statement matches what the argument or computation actually establishes.
- [ ] Distinguish a complete proof from a promising sketch, incomplete proof, false claim, computational observation, exact computer-assisted theorem, and independently reproduced result.
- [ ] Search for missing assumptions, vacuous cases, normalization errors, sign or indexing mistakes, unjustified exchanges of limits, hidden finiteness assumptions, and failures at extremal parameters.
- [ ] Try to construct counterexamples or minimal failing cases before accepting a universal claim.
- [ ] Use exact arithmetic, symbolic computation, Python, exhaustive or property-based finite testing, independent implementations, Lean, or another proof assistant when they materially improve confidence.
- [ ] Validate important results proportionately to their mathematical impact and use independent checks when practical.

For formal code:

- Compile it in the stated environment.
- Audit for `sorry`, `admit`, placeholders, extra axioms, `unsafe`, `native_decide`, and theorem-statement mismatches.
- Record versions and state the trust boundary precisely.

For computational claims:

- Validate hashes, input normalization, symmetry factors, enumeration completeness, exact-versus-floating arithmetic, certificate checkers, and boundary conditions.
- Distinguish verified arithmetic from externally generated data and unverified decoding or import bridges.
- Do not treat finite computation as a general proof unless the reduction to the finite search is complete.

## Assess literature status and novelty

- [ ] Perform candidate-specific literature research before assessing novelty, attribution, known status, or whether a bound improves published work.
- [ ] Prefer primary papers, authoritative monographs, official proof-assistant libraries, and original public companion repositories.
- [ ] Search exact theorem statements, distinctive constants, graph identifiers, family encodings, algorithms, and certificate formats.
- [ ] Separate mathematical correctness, graph-level novelty, literature priority, and publication readiness.
- [ ] Treat absence from a targeted search as support only for "apparently new" or "potentially novel," never as proof of priority.
- [ ] Never invent citations, tool output, novelty, or verification.

## Find strengthening and improvement opportunities

Every review must include a clearly labeled `## Strengthening and improvement opportunities` section. Treat it as part of the mathematical assessment, not as generic advice.

- [ ] Identify which hypotheses or normalizations are essential and which appear arbitrary or removable.
- [ ] Formulate plausible generalizations, converse statements, or classifications.
- [ ] Look for sharper constants, stronger bounds, broader parameter ranges, density consequences, and cleaner reductions.
- [ ] Connect graph contributions, proof techniques, or literature results when their combination could yield a stronger theorem.
- [ ] State the additional lemma, reduction, computation, formalization, or bridge required to turn each promising direction into a rigorous result.
- [ ] Prioritize opportunities by likely mathematical impact and feasibility.
- [ ] Distinguish proved refinements from conjectural research directions.
- [ ] State candidly when broadening an assumption would merely expose the claim as a classical specialization rather than increase novelty.

If no responsible strengthening is supported, say so explicitly and explain why.

## Choose the honest contribution kind

When publication is authorized and useful feedback is justified, use the most accurate current contribution kind:

- `review` for a scoped referee assessment.
- `reproduction` for an independent derivation or validation.
- `formalization` for checked formal source.
- `objection` for a precise defect.
- `counterexample` for an explicit refutation.
- `finding` or `lemma` only for a genuinely new, self-contained derivative result.

A confirming review must state exactly what was and was not verified. A negative assessment must give a concrete, checkable failure.

## Write a self-contained assessment

Include:

- The target claim and its exact scope.
- The review verdict and confidence level.
- What was checked and how.
- Detailed validation, gap, or refutation.
- Mathematical potential.
- What appears novel or potentially novel.
- Remaining proof or reproducibility gaps.
- Concrete work required to make the result rigorous and publishable.
- The required `## Strengthening and improvement opportunities` section.
- Methods, tool versions, sources, hashes, trust boundaries, and limitations when relevant.

Use inline LaTeX as `\(...\)` and block LaTeX as `\[...\]`. Use fenced blocks only for actual code or formal syntax. Copy artifact references exactly.

## Publish carefully

Publishing is an external action. Do it only when the invoking prompt authorizes it.

- [ ] Immediately before submission, query the committed graph again.
- [ ] Re-read the target and its neighborhood.
- [ ] Search for reviews, objections, reproductions, formalizations, counterexamples, findings, or discussions that make the draft duplicate or obsolete.
- [ ] If substantially the same assessment exists, do not submit a duplicate.
- [ ] Verify that the submission body is the complete intended Markdown text, never a local filename or path.
- [ ] Attach every relation known at creation time atomically and with the correct direction, such as `about`, `verifies`, `reproduces`, `formalizes`, `contradicts`, `depends_on`, `supports`, `refines`, or `cites`.
- [ ] Treat accepted-for-broadcast as pending, not committed.
- [ ] Confirm commitment through the configured committed graph.
- [ ] Retrieve the committed artifact and compare its title, kind, full body, and relations with the intended draft.

Do not report success unless the committed body is self-contained and complete. If the committed payload is malformed, report it explicitly and do not treat it as a valid review. When authorized to correct it, publish one corrected contribution that `refines` the malformed artifact and links to the mathematical target.

When reporting completed review work, identify the target reference and title, submitted contribution kind, title and reference, directed relations, mathematical verdict, novelty and publication-readiness assessment, tools and sources used, and commitment evidence.

If no contribution warrants responsible, non-duplicate feedback, publish nothing and state that conclusion when a report is requested.
