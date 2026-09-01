---
name: math-approach-formal-proof
description: Pursue a target through proof-assistant formalization, using Lean or another formal system to expose definitions, close logical bridges, and produce machine-checked theorems. Combine with math-research after selecting a problem.
---

# Formal Proof Approach

Use formalization as a research method, not merely a transcription step. Prefer targets where machine checking clarifies a disputed bridge, makes a reusable abstraction, or enables verified computation.

## Working mode

- State the intended informal theorem before encoding it.
- Reuse established library definitions when they match the mathematics; justify custom encodings and equivalence bridges.
- Decompose the proof around mathematically meaningful lemmas rather than tactic accidents.
- Pin toolchain and library versions and run the complete relevant build.
- Use no `sorry`, `admit`, or undeclared custom axioms in claimed proofs.
- Inspect axioms of important theorems and disclose `native_decide`, unsafe code, external oracles, generated data, and import bridges.
- Distinguish a formally proved theorem from a formal checker applied to externally generated certificates.
- Export reusable definitions and lemmas when they can support later research.

## Pivot condition

If formalization stalls on infrastructure rather than mathematics, isolate the smallest missing library lemma or equivalence theorem. Do not claim research progress from boilerplate alone.

Report the exact theorem statements, versions, build commands, axioms, trust boundary, and what the formal result contributes mathematically.
