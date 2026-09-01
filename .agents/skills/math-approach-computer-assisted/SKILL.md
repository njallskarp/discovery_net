---
name: math-approach-computer-assisted
description: Prove a finite mathematical claim through exhaustive exact computation, canonical enumeration, interval arithmetic, or independently checkable computational certificates. Combine with math-research after selecting a problem.
---

# Computer-Assisted Approach

Use computation as part of the proof, not merely as an experiment. The mathematical reduction to the finite computation and the completeness of the implementation are first-class obligations.

This skill specifies the proof architecture independently of language or software. Compose it with the relevant `$math-tool-*` skills for research code, solvers, rigorous numerics, computer algebra, or formal checking.

## Working mode

- Prove that the enumerated search space is complete for the stated theorem.
- Define normalization, symmetry quotient, canonicalization, and multiplicity reconstruction precisely.
- Use exact arithmetic or justified interval bounds for exact claims.
- Preserve compact inputs, outputs, manifests, hashes, and deterministic reproduction commands.
- Validate boundary cases, overflow assumptions, solver limits, and enumeration coverage.
- Prefer an independent implementation with a genuinely different algorithm or representation.
- Build a small verifier or certificate format when rerunning the full search is expensive.
- Separate exploratory computation, production proof computation, and independent verification.

A larger frontier is not automatically a stronger mathematical result. Seek closure of a meaningful case, a reusable reduction, or a pattern that supports a structural theorem.

## Pivot condition

When successive runs only enlarge counts or thresholds, pause. Extract an invariant, recurrence, dual certificate, or structural conjecture, or move to a different approach skill.

Report the finite reduction, completeness argument, implementation trust boundary, independent checks, resource cost, certificate, and exact theorem scope.
