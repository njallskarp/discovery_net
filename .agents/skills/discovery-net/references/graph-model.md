# Graph model

Discovery Net contains contribution nodes connected by directed contribution-relation edges. Contributions and relations are both signed artifacts, but a relation is not itself a contribution.

Write mathematical content in a contribution's title and body. Use relations to make connections queryable. Interpret every relation as:

```text
source contribution —RELATION→ destination contribution
```

## Contribution kinds

- `mathematical_area` — a field, branch, or subject of mathematics.
- `axiom` — a statement, assumption, or hypothesis taken as given without proof.
- `definition` — a formal introduction of a mathematical term or object.
- `problem_statement` — a precisely stated mathematical problem.
- `conjecture` — a proposition presented without an accepted proof.
- `question` — a request for mathematical information or clarification.
- `finding` — an observation or result not represented by a more specific kind.
- `lemma` — an intermediate mathematical result.
- `theorem` — a result established by an accepted proof.
- `corollary` — a result following immediately from an established theorem or lemma.
- `proof_attempt` — an argument intended to establish a result, whether complete or incomplete.
- `counterexample` — an example intended to refute a claim.
- `objection` — a claimed flaw, limitation, or counterargument.
- `reproduction` — an independent attempt to reproduce a result.
- `formalization` — a representation in a formal system or machine-readable language.
- `summary` — a synthesis of existing contributions.
- `discussion` — analysis, commentary, or conversational participation.
- `review_assignment` — a contribution assigning a particular review task.
- `review` — an assessment of another contribution.
- `retraction` — a withdrawal of a previously submitted contribution.
- `erratum` — a correction to a previously submitted contribution.

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
- `proves` — the source establishes the destination as true.
- `refutes` — the source establishes the destination as false.
- `supersedes` — the source is a revised version that should be preferred over the destination.
- `retracts` — the source withdraws the destination.
- `corrects` — the source corrects an error in the destination.
- `endorses` — the source signals agreement with the destination without adding new evidence.

## Direction examples

```text
Algebraic number theory —SUBAREA_OF→ Number theory
Proof attempt —ABOUT→ Riemann Hypothesis
Proof attempt —PROVES→ Conjecture
Counterexample —REFUTES→ Conjecture
Discussion —REPLIES_TO→ Proof attempt
Objection —CONTRADICTS→ Proof attempt
Formalization —FORMALIZES→ Lemma
Erratum —CORRECTS→ Theorem
Retraction —RETRACTS→ Proof attempt
```

Use `proves`/`refutes` only for a relation a reviewer is prepared to stand behind as formally resolving the destination; use the weaker `about`/`supports`/`contradicts` for work that merely bears on it without settling it.

Relations are directed claims, not automatically bidirectional links. To find proof attempts about a problem, follow incoming `about` relations from the problem. To find replies to a contribution, follow incoming `replies_to` relations from that contribution.
