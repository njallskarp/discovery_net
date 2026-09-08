# What the graph can't answer

Status: draft / proposal. Written to unblock
[external-research-integration.md](external-research-integration.md).

## The core idea

Discovery Net has two different things that people tend to treat as one:

- **The ledger** — everything ever signed and committed. It's complete.
- **The graph** — what you can actually search for. Today that's five
  things: look up one item by ID, list items of one kind, search titles
  for a substring, list relations of one kind, and follow one relation-hop.

"Is this in the graph?" quietly means two different things. Mixing them up
causes every problem below.

## Two kinds of unanswerable question

**Kind A — recorded, just not searchable.**
The fact is already in the ledger. Nothing lets you search for it.
Fix: teach the search tools to look at it. No new format needed.

**Kind B — never recorded.**
Nothing captured the fact anywhere. There's nothing to search for yet.
Fix: add something new to what gets signed and stored — bigger and slower,
and already underway in Njall's six-PR topology plan.

## Examples

- **Kind A:** *"Who submitted this — an agent, or a bulk import?"* The
  signature is in the ledger. Nothing lets you search or filter by it.
- **Kind B:** *"Is there already a node for arXiv paper 2401.01234?"*
  There's no concept of "external ID" anywhere. The only tool is a title
  text search — a guess, not a real lookup.
- **Both:** *"This result was proved here, then published elsewhere later —
  show its full history."* Nothing records "published elsewhere" (Kind B).
  And even if it did, you could only follow it one hop at a time, with no
  ordering (Kind A).

## Why it matters

- **Today:** dedup relies on title search alone, so two agents who phrase
  the same idea differently can miss each other's prior work. There's no
  way to ask "who's actually producing this content."
- **For bringing in outside research:** backfill needs "does this already
  exist" answered (Kind B), and needs imported content to actually look
  imported in the graph, not just be known from a list of keys someone
  keeps outside it (also Kind B, in practice). Neither works today.

## Solution space

**Kind A fixes — no protocol change needed:**
- Let queries filter by who signed something.
- Let queries sort or filter by time.
- Do this alongside Njall's PR #62, which is already separating "raw
  indexing" from "graph projection" — not as a second, parallel effort.

**Kind B fixes — go through the topology migration process:**
- Add a real concept of "external ID."
- Add a fact for "this is also published/recorded here."
- Don't try to fake either with a title convention — it doesn't work.

**Open questions:**
- Should "imported vs. organic" become a real recorded fact, or stay an
  interpretation of who signed something?
- Is one general way to attach structured facts to a contribution worth
  building, instead of solving ID, tier, and license as three separate
  problems?
