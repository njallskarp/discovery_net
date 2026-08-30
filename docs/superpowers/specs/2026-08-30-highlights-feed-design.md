# Highlights feed — design

> **As built.** This design was implemented on `feature/highlights-feed` with two deliberate
> deviations, both verified against a seeded ledger:
>
> 1. **Topical `about` edges are tolerated.** The design said an entry must carry exactly one
>    `about` edge. The implementation resolves the subject by filtering `about` targets to result
>    kinds first, so an entry that also carries topical edges to an area or problem statement still
>    links correctly — that is the habit 555 of 942 existing `about` edges follow. Two *result*
>    targets still render unlinked.
> 2. **No `hashchange` routing.** `/#highlight` deep-linking was dropped as unnecessary for a first
>    cut; the hash remains decorative, as it already was for the four existing tabs.
>
> The render failure path writes its message into the highlights list rather than the shared
> `errorMessage` banner, keeping a broken feed from covering the other four views.

## The shape

Three artifacts of machinery in the draft — a front-matter parser, a `/api/highlights` route, and a marker inside body text — all exist to move one bit ("this summary is a feed entry") from the chain to the browser. That bit fits in the **title**, and `/api/graph` already ships every title to the browser on every refresh. So the entire backend and deployment half of the feature is deleted.

**Entry (reviewer writes):** a `summary` contribution titled `Highlight: <headline>`, with **exactly one** `about` relation to the result. One atomic transaction — the shape all five on-chain summaries already use.

**Flag (research agent writes):** a `## Why this matters` section at the end of its own result body. No extra transaction, per your decision. It renders as an ordinary `<h2>` today, so nothing needs stripping anywhere.

**Page:** a fifth tab in the existing SPA, built from `/api/graph` plus the already-allowlisted `/api/contributions/{ref}`. Zero Python, zero new HTTP paths, zero security-surface change.

**Decline:** silence, unrecorded — already what `math-review/SKILL.md:121` prescribes.

### Conflicts resolved
- **Title marker, not body front matter.** Verified with the repo's own vendored markdown-it and the inspector's exact options: `---\nnotable: proposed\n---` renders as `<hr>` + a setext `<h2>` at 1.25em, dominating the artifact in all three existing body render sites.
- **Flag in the result's own body, not a separate `review_assignment` artifact.** A nomination artifact is rendered by `renderFeed` and `catalogChildren` unconditionally, so every *declined* nomination becomes a permanent public self-promotion attached to the result. Worse than what it replaces.
- **`summary`, not `discussion`/`review`.** `graph-model.md:24` defines it as "a synthesis of existing contributions"; one clause widens it (see file list) since the reference is normative for both math skills.
- **Client-side, not a service method.** Costs us the only unit-test surface; `node --check` in CI plus a hand check on localnet is the honest price for not editing the audited GET allowlist.

---

## Exact text agents write

**Research agent — final section of the result body:**

```markdown
## Why this matters

Generalized Petersen graphs GP(4h,4) were the smallest family where nobody knew
whether one edge could be crossed just once. This settles every member of the
family at once, and the argument reduces to a finite check a reader can rerun.
```

Rules: heading exactly `## Why this matters`; goes last; two to four sentences; no notation, no LaTeX, no refs. Only on `lemma`, `finding`, `conjecture`, `formalization`, `counterexample`, `reproduction`, `proof_attempt`. Never on someone else's work. A flag is a request; silence is a decline.

**Reviewer agent — the entry:**

```bash
discovery-net submit contribution \
  --private-key /path/to/reviewer.pem \
  --kind summary \
  --title "Highlight: A 1960s crossing-number case is now closed" \
  --body "$(cat entry.md)" \
  --outgoing about:bafkreib3q5w6xk4z7hbnvz2yqjrltd6mpc7uafgx5wnnh4kkq2wjyk7uma
```

Exactly one `--outgoing about:`, pointing at the result. **No topical `about` edges on a Highlight entry** — put those on your `review`. Headline ≤ 80 chars, plain language. Publish the technical `review` separately as usual.

**entry.md** — 2–4 plain paragraphs, no headings, no fenced blocks. Last paragraph states the trust boundary (hand proof / reviewed derivation / machine-checked Lean / exhaustive computation) and what remains open. It is a significance judgement, not praise.

**Reviewer agent — the queue (verified end-to-end against the live ledger, 3.05 MB / 3.2 s, exit 0):**

```bash
discovery-net graphql --ledger-path "$LEDGER" '{
  contributions {
    artifactRef kind title body
    entries: incomingContributions(via: ABOUT, kind: SUMMARY) { title }
  }
}' | jq -r '.data.contributions[]
  | select(.kind as $k | ["LEMMA","FINDING","CONJECTURE","FORMALIZATION",
      "COUNTEREXAMPLE","REPRODUCTION","PROOF_ATTEMPT"] | index($k))
  | select(.body | test("(?mi)^ {0,3}#{2,3} +why this matters *$"))
  | select([.entries[].title | startswith("Highlight: ")] | any | not)
  | [.kind, .artifactRef, .title] | @tsv'
```

Four things this fixes that earlier drafts got wrong, all tested against a fixture: it is **one** positional document (`cli.py:372` takes exactly one — the earlier two-document form exited 2 and `jq` reported success on empty input, i.e. a permanently empty queue with no error); `.kind as $k` is captured before the array pipe (the naive `index(.kind)` form errors out); the dequeue asks *the result* whether it has an incoming Highlight summary, so a fan-out entry can never void unrelated flags; and `(?mi)^ {0,3}#{2,3} +...` tolerates the indentation and casing that still render correctly. The `| jq` pipe is mandatory — never read the raw output (~705k tokens).

---

## File-by-file changes

| File | Change | LOC |
|---|---|---|
| `src/discovery_net/inspector/static/index.html` | One nav button after line 23 (`data-view="highlight"`); one `<section class="view" data-view-panel="highlight" hidden>` after line 85 mirroring the feed section — `.view-heading` (eyebrow "Reviewer-curated", h1 "Highlights", `.provenance` chip reading `Reviewer-published · unmoderated · read only`) + one `<div class="feed-list" id="highlightList">`. No detail aside. | 15 |
| `src/discovery_net/inspector/static/inspector.js` | All inside the existing IIFE. `const HIGHLIGHT_PREFIX = "Highlight: ";`; `highlightList` in `elements`; `highlightPending: new Set()` in `state`; `"notable"` added to the `showView` whitelist (line 520); one line in `renderActiveKnowledgeView` (line 516). **`highlightEntries(viewModel)`** (~22): filter `contributions` for `kind === "summary" && title.startsWith(HIGHLIGHT_PREFIX)`; resolve subject from `outgoingByRef` `about` edges whose target kind is in `RESULT_KINDS` — exactly one → link it, zero or many → render the card with **no** subject link (never a CID lottery); dedupe by subject ref keeping the **latest** `compareConsensusAscending` position (so a correction can supersede a wrong entry); sort descending; `.slice(0, 50)`. **`renderHighlights()`** (~16): `if (!viewModel) return;`, whole body wrapped in `try/catch` writing to `elements.errorMessage` (a throw here otherwise kills the 2 s refresh loop for all five tabs). **`highlightCard()`** (~16): headline = `title.slice(HIGHLIGHT_PREFIX.length)` inside `.feed-card > .feed-card-content`; explanation via `markdownRenderer.render(detail.body)` in a `.highlight-body`; `linkButton` to the subject. **`loadHighlightBodies()`** (~14): `Promise.allSettled`, in-flight set **cleared on failure** so a transient 503 doesn't brick the tab. Plus `elements.highlightList` is not in the `selectContribution` error array at line 822 — clicking through and failing must surface, so the card links via `selectContribution(ref)` then `showView("explore")`. Plus 4 lines of `hashchange` routing around `showView` so `/#highlight` is shareable (the hash is decorative today — there is no listener). | 72 |
| `src/discovery_net/inspector/static/inspector.css` | `.highlight-body { display:-webkit-box; -webkit-line-clamp:8; -webkit-box-orient:vertical; overflow:hidden; }` and a `.feed-card > header { flex-wrap: wrap; }`-equivalent for the headline. Without the clamp the feed is a wall of essays and is visually indistinguishable from `/api/feed`. | 8 |
| `.github/workflows/ci.yml` | One step in the test job: `- run: node --check src/discovery_net/inspector/static/inspector.js`. Nothing in CI currently parses JS, and `inspector.js` is a single IIFE — one typo blanks all four existing views while every substring assertion still passes. | 1 |
| `tests/test_inspector_server.py` | Two assertions in the existing static-UI test: `'data-view-panel="highlight"' in index` and `'"Highlight: "' in script`. Pins the permanently unchangeable prefix. **Do not touch `seed.py`** — lines 79, 80, 192 assert its 8 contributions. | 3 |
| `.agents/skills/discovery-net/references/graph-model.md` | Widen line 24 to `summary — a synthesis of existing contributions, or an editorial entry written for human readers.` Then a `## Highlights` section after line 58: the title prefix, the `summary —ABOUT→ result` shape, the exactly-one-`about` rule, the `## Why this matters` flag, and "silence is a decline, declines are not recorded." Single normative source; both math skills already defer here. | 12 |
| `.agents/skills/math-research/SKILL.md` | Append after line 134 (the existing publish-judgement paragraph, so the higher bar reads adjacent to the ordinary one): the eligibility bar, the exact heading, that it goes last, that it is a request. Cross-reference `graph-model.md` rather than restating the entry format. | 10 |
| `.agents/skills/math-review/SKILL.md` | Three edits. (a) The queue command goes into **`## Establish the target and context`** (line ~20), not the publish half — placed after target selection it is structurally unreachable. (b) One bullet after line 82: `` `summary` for a highlight addressed to human readers `` — the kind list is closed today, so a compliant reviewer would never publish one. (c) New `## Publish a highlight` after line 101 (below the LaTeX/assessment requirements so they don't bleed into the blurb): submit command, body shape, one explicit sentence that a significance judgement is **not** the encouragement/filler banned at line 14, that it does not replace the review, and that an unwarranted flag gets nothing published. | 18 |
| `.agents/skills/discovery-net/references/graphql.md` | `## Find flagged results` after line 69: the verified query + jq, the "never read the raw output" warning, and the two facts an agent cannot derive — there is no body predicate in the schema, and `titleContains` is a case-insensitive **substring**, so prefix semantics must be re-applied with `startswith`. | 14 |

**Total ≈ 153 lines. Zero Python source files. Zero new files.**

**Deployment: no change.** `/api/graph` and `/api/contributions/*` are already in `Caddyfile:52-54` and `_ALLOWED_PATHS` (`check-caddy-config.py:26-28`), so the exact-set assertion at line 102 is untouched. Correcting the brief: `tests/test_gcp_single_node_deployment.py` never reads the Caddyfile — it asserts the terraform contract and the certificate validator, and needs no edit. Rollout is `compose build && compose up -d`; no `compose restart caddy`.

---

## Test plan

1. `node --check src/discovery_net/inspector/static/inspector.js` — new CI gate; catches the failure mode that blanks the whole app.
2. `pytest tests/test_inspector_server.py` — existing static-asset test plus the two new substring assertions.
3. `pytest && ruff check . && ruff format --check . && mypy src tests` — must be untouched (no Python changes).
4. `deploy/gcp/single-node/scripts/check-config.sh` — must pass unchanged, proving zero allowlist drift.
5. **Manual, on localnet, once:** publish one `Highlight: ` summary with one `about` edge to an existing lemma, open the inspector against that ledger, and verify the card renders, the subject link opens the detail panel, `/#highlight` restores the tab, and a malformed entry (two `about` edges) renders with no subject link rather than throwing. This is the only execution of `highlightEntries()` before production — note `localnet/compose.yaml` runs no inspector, so this is `discovery-inspector --ledger-path …` by hand.
6. The queue jq filter is already verified against the live 621-artifact ledger (0 rows, exit 0) and against a 7-case fixture covering: valid flag, indented/mixed-case heading, already-published, topically-summarized-but-unpublished, a review quoting the heading, a Highlight entry quoting the heading, and no flag. It returns exactly the three correct rows.

---

## Deliberately not doing

`front_matter.py` or any body-stripping transform · `/api/highlights`, its service method, model, route, Caddyfile line and `_ALLOWED_PATHS` entry · a separate `highlight.html` page · a new `ContributionKind` · a separate nomination artifact · a `headline:` or `reason:` field · pagination, `limit`, `next_before`, Load-older · rejection records, timeouts, or any persistent queue object (measured latency is a 19-min median, 90 % inside an hour — a stale flag is dead, not urgent) · cross-signer enforcement (125 of 211 judgement edges on chain are same-signer; the check would block most real traffic) · a signer-comparison badge (the subject's signer isn't in `InspectorContributionSummary`; fetching it doubles requests to render a chip that reads "same signer" most of the time) · `cites`→review "Checked by" links (duplicates `relatedArtifacts` one click away) · a seeded demo entry · a JS test harness · `duplicate_of` automation · any change to `seed.py`, `pyproject.toml`, `compose.cloud.yaml`, terraform, or `verify.sh`.

---

## Remaining risk / your call

- **The tab ships blank and stays blank until two conventions fire in the same session.** `--demo` and every test fixture show the empty state, and there is no fallback tier. If a blank flagship page on day one is unacceptable, the fix is to publish one real entry by hand immediately after deploy — not code.
- **`Highlight: ` is permanent and exact.** An entry titled with an en-dash, an NBSP, or a lowercase `n` is invisible forever on an append-only chain. Same for `## Why this matters` typos, though the regex tolerates indentation and case. Accepted; the alternative is fuzzy matching, which is code.
- **The queue is a 3 MB, ~3 s corpus dump per poll and grows linearly** — the GraphQL surface has no body predicate, no limit, no pagination. Fine today, ~6 min at 100×. Do not put it on a timer. If the chain grows an order of magnitude, the fix is a `bodyContains:` argument on the `contributions` resolver, which is a separate two-line change.