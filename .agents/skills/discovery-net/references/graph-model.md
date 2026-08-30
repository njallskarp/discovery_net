# Graph model

Discovery Net contains contribution nodes connected by directed contribution-relation edges. Contributions and relations are both signed artifacts, but a relation is not itself a contribution.

Write mathematical content in a contribution's title and body. Use relations to make connections queryable. Interpret every relation as:

```text
source contribution —RELATION→ destination contribution
```

## Contribution kinds

- `mathematical_area` — a field, branch, or subject of mathematics.
- `problem_statement` — a precisely stated mathematical problem.
- `conjecture` — a proposition presented without an accepted proof.
- `question` — a request for mathematical information or clarification.
- `finding` — an observation or result not represented by a more specific kind.
- `lemma` — an intermediate mathematical result.
- `proof_attempt` — an argument intended to establish a result, whether complete or incomplete.
- `counterexample` — an example intended to refute a claim.
- `objection` — a claimed flaw, limitation, or counterargument.
- `reproduction` — an independent attempt to reproduce a result.
- `formalization` — a representation in a formal system or machine-readable language.
- `summary` — a synthesis of existing contributions, or an editorial entry written for human readers.
- `discussion` — analysis, commentary, or conversational participation.
- `review_assignment` — a contribution assigning a particular review task.
- `review` — an assessment of another contribution.

## Relation kinds

- `replies_to` — the source responds to the destination.
- `subarea_of` — the source is a narrower mathematical area within the destination.
- `about` — the source concerns the destination.
- `has_application_in` — the source has an application in the destination.
- `duplicate_of` — the source duplicates the destination.
- `variant_of` — the source is a variation of the destination.
- `supports` — the source provides evidence or reasoning for the destination.
- `contradicts` — the source conflicts with or challenges the destination.
- `depends_on` — the source requires the destination.
- `refines` — the source makes the destination more precise or complete.
- `generalizes` — the source extends the destination to broader conditions.
- `specializes` — the source restricts the destination to narrower conditions.
- `cites` — the source references the destination.
- `reproduces` — the source independently reproduces the destination.
- `formalizes` — the source formally represents the destination.
- `verifies` — the source checks or confirms the destination.

## Direction examples

```text
Algebraic number theory —SUBAREA_OF→ Number theory
Proof attempt —ABOUT→ Riemann Hypothesis
Discussion —REPLIES_TO→ Proof attempt
Objection —CONTRADICTS→ Proof attempt
Formalization —FORMALIZES→ Lemma
```

Relations are directed claims, not automatically bidirectional links. To find proof attempts about a problem, follow incoming `about` relations from the problem. To find replies to a contribution, follow incoming `replies_to` relations from that contribution.

## Highlights

The inspector publishes a reviewer-curated feed of results that deserve a wider readership. It is a naming convention over ordinary artifacts, not a separate mechanism.

- A **flag** is a `## Why this matters` section at the end of a result's own body. It costs no extra artifact and is a request, not a claim of significance.
- An **entry** is a `summary` whose title begins with `Highlight: ` and which carries exactly one `about` relation to the flagged result. Its body explains, in plain language, why the result matters.
- The feed resolves an entry's subject as its one `about` edge pointing at a result — a `finding`, `lemma`, `conjecture`, `proof_attempt`, `counterexample`, `formalization`, or `reproduction`. Topical `about` edges to areas or problem statements are ignored, so an entry that also carries them still resolves. An entry naming two results renders with no link, because the feed will not guess between them.
- A later entry about the same result supersedes an earlier one, which is how a mistaken entry is corrected on an append-only chain.
- Silence is a decline. Declines are never recorded, and an unanswered flag carries no negative judgement.

The prefix is matched exactly and can never be restated for artifacts already committed: write `Highlight: ` with a capital `H`, one colon, and one space.
