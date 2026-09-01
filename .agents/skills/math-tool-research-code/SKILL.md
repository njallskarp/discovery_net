---
name: math-tool-research-code
description: Build reproducible mathematical experiments, proof computations, generators, and independent checkers in Python, C++, Julia, Rust, R, or another suitable language. Use as a concrete tool layer for math-research, not for ordinary application development.
---

# Research Code for Mathematics

Choose a language and implementation architecture from the mathematical workload and evidence required by the approach skill. Language choice is not itself a mathematical approach.

## Language routing

- Use Python for rapid exact prototypes, symbolic glue, combinatorial generation, array experiments, and compact independent checkers. When selected, read [Python research code](references/python.md).
- Use C++ for large deterministic enumerations, memory-sensitive state spaces, and high-performance exact verification. When selected, read [C++ research code](references/cpp.md).
- Consider Julia for numerical, optimization, or scientific-computing workloads where its ecosystem materially helps.
- Consider Rust for high-performance certificate tooling when memory safety and a small robust verifier matter.
- Consider R for statistical experiments when its modeling and diagnostic ecosystem is the actual research need.

Do not introduce a second language merely to appear independent. Independence requires a different algorithm, representation, derivation, or checker trust base.

When runtime, memory, or repeated computation materially affects the research, compose with `$math-tool-compute-intensive` to measure scaling, choose optimizations, design parallel or restartable execution, and validate optimized results against a reference implementation.

## Reproducibility contract

- Separate exploratory scripts, production proof computation, and independent verification.
- Provide deterministic entry points with documented inputs, outputs, and exit conditions.
- Pin interpreters, compilers, packages, and build flags sufficiently to reproduce the result.
- Prefer exact arithmetic for exact claims; document overflow bounds, precision, rounding, and tolerance otherwise.
- Preserve compact certificates, manifests, hashes, seeds, and summary outputs rather than bulky transient data.
- Test normalization, symmetry handling, decoding, boundary cases, and known small instances.
- Record time and memory cost when they affect reproducibility or completeness.
- Fail loudly on malformed inputs, incomplete searches, unexpected states, or certificate mismatches.

## Evidence discipline

Tie each output field to a mathematical claim. State which correctness properties follow from code inspection, tests, independent replay, a certificate checker, formal verification, or an external library.

Do not treat matching aggregate counts as full reproduction when entry-level comparison is feasible. Do not infer a universal theorem from an incomplete or heuristic run.

## Publication

Publish only source and compact artifacts authorized by the invoking prompt. Exclude keys, credentials, private node data, ledgers, logs, build products, caches, and large generated outputs.

Use `$github-math-research` when publishing these artifacts to an authorized GitHub repository.
