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
- `summary` — a synthesis of existing contributions.
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
