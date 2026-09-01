---
name: math-tool-lean
description: Implement, check, and report mathematical research in Lean with explicit theorem alignment, reproducible builds, axiom audits, and external-data trust boundaries. Use as the concrete tool layer with math-research and a suitable math-approach skill.
---

# Lean for Mathematical Research

Use Lean as the concrete proof-assistant toolchain. The problem selector chooses the target and the approach skill explains why formalization advances the mathematics; this skill governs the implementation and evidence.

## Theorem alignment

- State the intended informal theorem before formalization.
- Ensure the Lean statement has the same quantifiers, domains, hypotheses, normalizations, and conclusion.
- Prefer existing Mathlib definitions when they match the mathematics; prove explicit equivalence lemmas for custom encodings.
- Separate reusable mathematical lemmas from certificate decoding, finite evaluation, and infrastructure.

## Proof and build standards

- Pin and report Lean, Lake, and Mathlib versions or exact revisions.
- Use no `sorry` or `admit` in claimed proofs.
- Do not add custom axioms to claim machine-checked proof of the target.
- Run the complete relevant build from a clean, documented command.
- Run `#print axioms` on the important exported theorems and report the result.
- Disclose `native_decide`, `unsafe`, external oracles, generated code, and nonstandard kernels or plugins.

## External computation

Do not claim Lean verified an external computation merely because it checked arithmetic involving its output. State separately:

- What Lean proves about the checker or certificate format.
- What generated the data or certificate.
- Whether completeness, decoding, parsing, or import remains outside Lean.
- Which hashes or manifests bind the formal input to the published artifact.

Prefer a small verified checker or a formally proved reduction over importing a large opaque result.

## Report

Publish the exact theorem names and statements, source revision, build command, versions, axiom audit, trust boundary, and the mathematical role of the formalization.
