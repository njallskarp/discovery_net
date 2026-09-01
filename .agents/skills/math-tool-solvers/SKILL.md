---
name: math-tool-solvers
description: Encode mathematical claims for SAT, SMT, LP, MILP, SOS, constraint, or optimization solvers and extract reproducible witnesses or independently checkable certificates. Use as a concrete tool layer for math-research.
---

# Solvers for Mathematical Research

The approach skill determines why a symbolic or optimization certificate proves the target. This skill governs encoding, solver evidence, and checking.

## Encoding contract

- Define variables, domains, constraints, objectives, symmetries, and decoding mathematically.
- Prove soundness and completeness for the direction needed by the theorem.
- Audit symmetry breaking, preprocessing, integer bounds, tolerances, and omitted degenerate cases.
- Preserve generators and compact canonical instances rather than only generated files.

## Evidence by solver class

- SAT or SMT: preserve satisfying assignments for existence claims and proof traces for UNSAT when supported; check traces independently when feasible.
- LP or Farkas: reconstruct and verify exact rational primal or dual certificates. Floating solver output is discovery evidence until certified exactly.
- MILP: verify feasible witnesses directly. Treat optimality or infeasibility as requiring a checkable bound, proof log, exact dual argument, or separately justified solver trust.
- SOS or polynomial optimization: rationally reconstruct and verify the exact polynomial identity and positivity assumptions.

Solver agreement alone is not independent verification when systems share the same encoding bug. Prefer a small decoder and certificate checker tied directly to the mathematical definitions.

## Report

Publish solver and checker versions, generator and invocation commands, instance hashes, certificate format, exact verification result, resource limits, preprocessing, and remaining trust boundary.
