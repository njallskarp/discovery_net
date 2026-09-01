---
name: math-tool-rigorous-numerics
description: Establish mathematical bounds with validated interval or ball arithmetic, directed rounding, certified root isolation, or other rigorous numerical enclosures. Use as a concrete tool layer for math-research, not for ordinary floating-point experiments.
---

# Rigorous Numerics for Mathematical Research

Use validated numerics only after reducing the target theorem to explicit enclosure obligations. Libraries such as Arb or MPFR-based interval systems are tools; the proof also requires coverage and interpretation.

## Enclosure contract

- State the exact real or complex quantity and the enclosure sufficient for the theorem.
- Use outward or directed rounding with documented precision and library semantics.
- Control dependency inflation, cancellation, branch cuts, singularities, and domain errors.
- Prove that subdivisions or parameter boxes cover the full target domain without gaps or overlap mistakes.
- Isolate exceptional regions and handle them analytically or with finer certified subdivision.
- Increase precision or change representation based on a justified termination condition, not until the desired sign appears.

## Verification

- Test known values and adversarial near-boundary cases.
- Record precision, rounding mode, subdivision policy, stopping criteria, versions, commands, and compact enclosure certificates or hashes.
- Prefer an independent analytic bound or different validated implementation for critical margins.

Ordinary high-precision floating-point agreement is not rigorous numerics. Report exactly what is enclosed, why the enclosure implies the theorem, and any coverage or library trust boundary.
