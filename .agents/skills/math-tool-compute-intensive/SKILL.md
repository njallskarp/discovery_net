---
name: math-tool-compute-intensive
description: Design, optimize, validate, and run compute-intensive mathematical research without sacrificing correctness or reproducibility. Use with math-research and math-tool-research-code when runtime, memory, or repeated computation materially affects the research.
---

# Compute-Intensive Mathematical Research

Use this execution layer when a mathematical experiment, enumeration, certificate generator, verifier, or numerical procedure is becoming resource-intensive. It complements a mathematical approach and `$math-tool-research-code`; it is not itself a proof method.

Correct mathematics, complete coverage, and reproducible evidence take precedence over speed. Optimize to make the intended research feasible, not to maximize benchmark performance.

## Decide whether optimization is warranted

Start with a correct reference implementation or a direct definition-level prototype on small, hand-checkable instances. Measure elapsed time, peak memory, input size, and the dominant operation. Estimate the full run's cost from observed scaling rather than intuition alone.

Keep the simpler implementation when it will finish comfortably, is run only once, and optimization would create more correctness risk than useful savings. Optimize when measurement indicates hours or days of runtime, prohibitive memory, repeated production runs, or a clear bottleneck that materially delays mathematical feedback.

Before low-level tuning, look for mathematical and algorithmic reductions:

- Stronger pruning, bounds, invariants, or symmetry reduction.
- Canonicalization and elimination of duplicate states.
- Dynamic programming, memoization, caching, or reusable precomputation.
- Better asymptotic algorithms, data structures, and state representations.
- Batching, locality-aware layouts, reduced allocation, and less serialization or I/O.
- Deterministic partitioning across processes, threads, or machines.

If the computation remains infeasible, seek a sharper lemma, compact certificate, or different mathematical approach rather than only buying more compute.

## Language and library choice

Favor Python for simple research logic and fast iteration, especially when mature libraries perform the heavy work: NumPy or SciPy for array and scientific computation, pandas for tabular analysis, and appropriate domain libraries for graph, symbolic, or optimization tasks. Vectorized native-library operations can avoid the cost of Python loops while keeping the implementation clear.

Use C++ when profiling shows that compute-heavy loops, large deterministic enumerations, memory layout, or fine-grained parallelism dominate and Python or its libraries cannot meet the needed resource envelope. Workload-dependent speedups of roughly 10–1000x can be possible, but never assume or promise them; measure the actual implementation. Read `$math-tool-research-code`'s C++ reference and audit overflow, undefined behavior, determinism, and concurrency.

Do not rewrite in C++ merely because the computation sounds large. A better algorithm in Python can dominate a direct translation, while a Python front end calling optimized native libraries may already have the desired performance.

## Parallel and restartable execution

- Partition work deterministically and document how partitions cover the full domain without gaps or duplicate-counting errors.
- Make reductions and merges associative or otherwise specify a deterministic merge order.
- Control random seeds per partition and record the generator and derivation of each seed.
- Guard against races, nondeterministic iteration, integer overflow, partial writes, and silently dropped worker failures.
- For long runs, support resumable checkpoints locally and make interruption or incomplete coverage visible.
- Record commands, versions, thread or process counts, partition bounds, resource limits, and completion criteria.

Checkpoints, verbose logs, and bulky outputs are operational state, not default publication artifacts. Keep them outside the source repository unless `$github-math-research`'s explicit large-file authorization is satisfied.

## Preserve correctness across optimization

Freeze representative baseline inputs and the output schema before changing languages or algorithms. Compare the reference and optimized implementations on small and medium instances, including boundary, adversarial, and known cases.

- Compare entry-level or canonicalized results when feasible, not only totals.
- If parallelism changes ordering, canonicalize before comparison.
- Compare initial outputs and diagnostic logs locally to locate the first divergence.
- Preserve only a compact comparison summary, hashes, and relevant test fixtures for publication; do not commit verbose logs.
- Retain the simple reference implementation when it provides a useful definition-level checker.
- Add an independent checker or certificate verifier when the optimized computation becomes too complex to trust by inspection.
- Re-establish arithmetic bounds, completeness, normalization, and trust boundaries after every material optimization.

Matching output is necessary regression evidence, not proof that two implementations are independently correct when they share the same derivation or bug.

## Report

Report the baseline and optimized algorithms, workloads, versions, commands, runtime and memory measurements, observed speedup, partitioning, checkpoint behavior, validation cases, exact output or compact hash, and remaining trust boundary. State whether optimization changed only execution or also changed the mathematical reduction.
