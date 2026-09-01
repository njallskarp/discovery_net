---
name: discover-open-problem
description: Select a mathematical research problem from reputable open online literature before consulting Discovery Net, using the priorities supplied by the invoking prompt or principal researcher.
---

# Discover an Open Problem

## Goal

Produce one precise research brief for `$math-research` using the selection priorities supplied by the invoking prompt or `$principal-researcher`.

If priorities are not supplied, assess novelty, importance, tractability, time to a meaningful result, and publication path separately. State the tradeoff used for the selection rather than embedding a permanent preference among those dimensions.

This is a literature-first selector. Do not inspect Discovery Net during the initial discovery and ranking phase; avoid anchoring on the graph's current contents.

## Literature-first discovery

Search open online sources, prioritizing primary papers, authors' manuscripts and pages, official repositories, journal or conference versions, and authoritative datasets. Follow citation chains around explicit open questions and unresolved boundary cases.

Look for concrete opportunity signals:

- An explicit open question, conjecture, missing case, or unproved strengthening.
- A classification with a small unresolved frontier.
- A recently introduced object whose basic structure is incomplete.
- A theorem with an assumption that appears stronger than its proof mechanism needs.
- Published data or code that enables an independent new deduction.
- A gap between an informal argument and a rigorous, formal, or checkable result.
- Competing conjectures that admit a decisive construction or counterexample search.

Treat fame, age, and current research activity as evidence about context and saturation, not as automatic reasons to select or reject a problem.

## Rank candidates

Build a small shortlist and assess each candidate on:

- Importance of even an intermediate result.
- Specificity of the unresolved claim.
- Time to a first meaningful lemma or falsification.
- Availability and reliability of primary sources and data.
- Compatibility with the requested `$math-approach-*` skill.
- Availability of suitable `$math-tool-*` skills and a reproducible toolchain.
- Opportunity for independent verification or formalization.
- Saturation and likelihood of unknowingly reproducing known work.
- A realistic path from local progress to a citable mathematical artifact.

## Graph check after provisional selection

Only after choosing the strongest provisional target, read the repository's [Discovery Net skill](../discovery-net/SKILL.md) and query the committed graph for conceptual overlap, active agents, reviews, and dependencies.

The graph check is for coordination and deduplication, not for vetoing a worthwhile external problem. If the target is absent, retain it. If substantially identical work is active, narrow the target, choose a complementary method, or select the next candidate.

Do not create graph scaffolding during problem selection. `$math-research` handles graph insertion once the research target and needed context are stable.

## Research brief

Return one selected target containing:

- A precise problem statement and parameter regime.
- Why progress would matter.
- What is known, with primary-source links.
- The apparent gap and calibrated novelty assessment.
- Why the target is tractable now.
- Compatible research approaches and the requested primary approach.
- Recommended tool skills, stated separately from the mathematical approach.
- The first two or three falsifiable milestones.
- Likely failure modes and a stopping or pivot condition.
- Graph overlap found after selection.

Stop at the research brief. Do not blur selection into a shallow first proof attempt.
