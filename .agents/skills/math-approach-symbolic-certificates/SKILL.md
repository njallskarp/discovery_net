---
name: math-approach-symbolic-certificates
description: Pursue a target through exact symbolic encodings and checkable certificates such as LP/Farkas duals, SAT/SMT proofs, MILP, SOS, Groebner bases, or rewrite systems. Combine with math-research after selecting a problem.
---

# Symbolic Certificate Approach

Turn the mathematical claim into an exact finite certificate whose soundness and interpretation are explicit.

## Working mode

- Prove the reduction from the original claim to the symbolic system.
- Specify variables, domains, constraints, symmetries, and decoding exactly.
- Prefer certificates independently checkable by a small trusted verifier.
- Use rational or exact arithmetic when the claim is exact; disclose any numerical optimization used only to discover a certificate.
- For LP or Farkas arguments, publish the dual multipliers and verify the resulting identity or inequality exactly.
- For SAT or SMT, preserve proof traces when feasible and distinguish solver UNSAT from independently checked UNSAT.
- For SOS or Groebner methods, state the coefficient domain, monomial order or degree bound, and exact identity.
- Audit symmetry breaking for completeness and ensure encoding conventions match the mathematical theorem.

The certificate is not the theorem unless the reduction, checker, and decoding are all justified.

## Pivot condition

If certificates remain huge or opaque, search for symmetry aggregation, a smaller dual obstruction, or a structural lemma explaining the solver output. Do not escalate parameter size by default.

Report the reduction theorem, encoding, certificate, checker, exact verification result, and remaining trust boundary.
