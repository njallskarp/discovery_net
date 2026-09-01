---
name: math-approach-probabilistic
description: Pursue a mathematical target using probabilistic constructions, concentration, alteration, entropy, random processes, local lemmas, or second-moment reasoning. Combine with math-research after selecting a problem.
---

# Probabilistic Approach

Use probability to prove existence, typical structure, thresholds, or quantitative bounds. A simulation alone is not a probabilistic proof.

State the probabilistic mechanism independently of software. Use suitable `$math-tool-*` skills for experiments, symbolic calculation, or rigorous numerical bounds when required.

## Working mode

- Define the probability space and random variables precisely.
- Identify the event or expectation whose bound implies the mathematical claim.
- Check dependence rather than assuming independence.
- Choose the appropriate tool: first or second moment, alteration, concentration, martingale, entropy, local lemma, random greedy process, or coupling.
- Track constants and parameter regimes needed for a nonvacuous conclusion.
- When derandomization matters, identify a conditional-expectation, pseudorandom, or certificate route.
- Use experiments only to locate thresholds, candidate distributions, or exceptional regimes.

Prefer a robust probabilistic mechanism or threshold theorem over empirical success rates.

## Pivot condition

If variance, dependence, or rare obstructions destroy the estimate, characterize that obstruction and test whether conditioning, alteration, or a different probability space repairs it.

Report the probability space, implication event, bound, dependencies, constants, and any derandomization gap.
