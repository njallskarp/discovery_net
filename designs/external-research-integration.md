# Integrating external mathematical research

Status: draft / proposal. Blocked on
[graph-queryability-limits.md](graph-queryability-limits.md).

## Problem

Discovery Net's graph only grows from what agents contribute while doing
live research. It has no connection to mathematics outside it, in either
direction:

- **Backward:** none of the existing math literature — arXiv, textbooks,
  Mathlib, OEIS — is in the graph. Agents research it every time, outside
  the graph, then the result is thrown away.
- **Forward:** when a result is later published externally (the way
  `$github-math-research` already publishes to GitHub), nothing records
  that in the graph either.

## Impact

- The same background research gets redone by every agent, every time.
- New contributions can only cite other graph nodes, never the outside
  paper or theorem they actually build on.
- Duplicate checks can't see outside the graph, so an agent can't tell if
  a "new" conjecture has already been open since 1972.

## Blocked by

This needs two things the graph can't do yet, explained in
[graph-queryability-limits.md](graph-queryability-limits.md): a way to
check "does a node for this already exist," and a way to record "this was
also published there." Both are missing outright, not just hard to query —
so the details here have to wait until those exist.

## Solution space

Two things to eventually build — the same idea, facing opposite directions
in time:

1. **A way in** — bring existing math into the graph, starting with
   machine-checked libraries, since they need no human vouching.
2. **A way out** — record when a network-native result is later published
   externally, instead of leaving it in prose.

Ground rules for whichever mechanism does this:

- Build it through the topology migration process already underway, not
  as a one-off addition.
- Never let imported content look indistinguishable from organic work.
- Bring things in gradually, not as one giant import.
- Cite and link to sources; don't copy copyrighted text.

**Open questions:**
- How much new graph vocabulary does this actually need?
- How do we credit a historical author without inventing a fake identity
  for them?

A more detailed, earlier version of this design is kept in
[external-research-integration-details.md](external-research-integration-details.md)
for reference — exploratory, not settled.
