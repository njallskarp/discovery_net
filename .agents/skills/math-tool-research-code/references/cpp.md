# C++ Research Code

Read this reference only when C++ is selected for mathematical research.

## Arithmetic and correctness

- Prove bounds for fixed-width arithmetic or use checked and multiprecision types.
- Avoid relying on signed overflow, implementation-defined shifts, uninitialized storage, unstable hashing, or unspecified iteration order.
- Make bit layouts, canonical forms, endianness-dependent serialization, and symmetry conventions explicit.
- Use exact comparison for exact claims and a rigorous-numerics toolchain when floating-point enclosures are required.

## Build and verification

- Pin the compiler family and version, language standard, optimization flags, and material dependencies.
- Provide documented release and checking builds.
- Run warnings at a strict practical level and resolve relevant diagnostics.
- Run address and undefined-behavior sanitizers on representative coverage; use thread sanitization when concurrency affects the proof computation.
- Test small exhaustive instances against definitions or an independent implementation.
- Make incomplete search, allocation failure, decoding error, and certificate mismatch terminate visibly.

## Performance and independence

- Keep the verifier simpler than the generator when possible.
- Record threading, partitioning, determinism, time, and peak memory when they matter to completeness.
- Reimplementing Python loops in C++ is performance validation, not mathematical independence, unless the algorithm or representation is genuinely different.

Report compiler and library versions, complete build and run commands, sanitizer coverage, arithmetic bounds, deterministic outputs or hashes, and the trust boundary of imported libraries.
