---
name: math-approach-formal-proof
description: Pursue a target through proof-assistant formalization to expose definitions, close logical bridges, and produce machine-checked theorems. Combine with math-research and an appropriate proof-assistant tool skill after selecting a problem.
---

# Formal Proof Approach

Use formalization as a research method, not merely a transcription step. Prefer targets where machine checking clarifies a disputed bridge, makes a reusable abstraction, or enables verified computation.

This skill specifies the mathematical role of formalization independently of proof assistant. Compose it with an appropriate `$math-tool-*` skill, such as `$math-tool-lean`, for concrete toolchain, build, axiom, and trust-boundary standards.

## Working mode

- State the intended informal theorem before encoding it.
- Reuse established library definitions when they match the mathematics; justify custom encodings and equivalence bridges.
- Decompose the proof around mathematically meaningful lemmas rather than tactic accidents.
- Distinguish a formally proved theorem from a formal checker applied to externally generated certificates.
- Export reusable definitions and lemmas when they can support later research.

## Pivot condition

If formalization stalls on infrastructure rather than mathematics, isolate the smallest missing library lemma or equivalence theorem. Do not claim research progress from boilerplate alone.

Report the exact theorem statements, formal proof architecture, remaining informal bridges, and what the formal result contributes mathematically. Report tool-specific evidence required by the selected proof-assistant skill separately.
