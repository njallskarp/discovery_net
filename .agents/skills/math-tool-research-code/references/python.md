# Python Research Code

Read this reference only when Python is selected for mathematical research.

## Exactness and representation

- Use Python integers, `fractions.Fraction`, exact symbolic objects, or finite-field libraries when the theorem is exact.
- Treat NumPy fixed-width integer overflow as a proof risk. Establish bounds, use checked conversions, or compare against arbitrary-precision calculations.
- Avoid floating-point equality as mathematical evidence. If approximation is intrinsic, report precision and error control or use the rigorous-numerics tool skill.
- Make canonicalization, indexing, bit ordering, graph labeling, and symmetry conventions explicit.

## Reproducible execution

- Provide one documented command or module entry point for each production result and checker.
- Pin the Python version and material dependencies with the repository's existing environment mechanism.
- Fix random seeds, but also record the generator and sampling protocol; a seed does not make a biased experiment representative.
- Stream or hash large enumerations rather than keeping opaque transient files.
- Write tests for small hand-checkable cases, exceptional inputs, serialization, and certificate rejection.

## Performance and independence

- Profile before replacing clarity with vectorization or native extensions.
- State whether parallel execution changes ordering or reproducibility.
- A NumPy rewrite of the same Python formulas is not an independent mathematical verifier. Prefer a direct definition-level checker or a substantially different decomposition.

Report Python and package versions, commands, deterministic output or hash, tests, exactness assumptions, and any native-library trust boundary.
