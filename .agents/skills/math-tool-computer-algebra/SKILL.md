---
name: math-tool-computer-algebra
description: Use a computer algebra system for exact symbolic derivation, factorization, elimination, group computation, or identity verification with explicit domains and reproducible commands. Use as a concrete tool layer for math-research.
---

# Computer Algebra for Mathematical Research

Choose a system for its required algebraic domain and algorithms, not convenience alone. Examples include SageMath, SymPy, PARI/GP, GAP, Magma, Singular, and domain-specific libraries.

## Algebraic contract

- Specify coefficient domain, characteristic, extensions, variable order, quotient relations, monomial order, and normalization.
- Distinguish exact symbolic output from heuristic simplification, modular guessing, numerical root finding, and reconstructed rationals.
- Record exceptional parameters where division, factorization, rank, or specialization changes.
- Verify important identities by substitution, normal form, coefficient comparison, or an independent small checker.
- When using modular images or interpolation, justify reconstruction bounds and bad-prime handling.
- When using proprietary software, provide a portable certificate or independent verification whenever practical.

## Reproducibility

Publish system and package versions, complete scripts and commands, deterministic inputs, compact outputs or hashes, and all options affecting normal forms or algorithms.

A CAS transcript is not a proof of the surrounding theorem. State the mathematical reduction, what the CAS establishes, and which interpretation steps remain external.
