---
name: rust-scientific-correctness
description: "Audit scientific Rust algorithms for mathematical validity, numerical robustness, stochastic semantics, and independent evidence."
---

# Rust Scientific Correctness

Rust-orchestrator passes use the shared [execution-v1 contract](../rust-review-orchestrator/references/execution-v1.md).

Audit whether Rust scientific software answers the scientific question it claims to answer. A clean build, plausible output, or agreement between two paths that share the same assumptions is not sufficient evidence of correctness.

## Ownership Boundary

This skill owns:

- the mathematical or scientific model implemented by the code
- domain assumptions, units, dimensions, sign/orientation/index conventions, and supported regimes
- exact, rounded, approximate, filtered, and stochastic result semantics
- conditioning, numerical stability, tolerances, and error-bound validity
- independent evidence that computed results are correct
- reproducibility and scientifically valid benchmark inputs and comparisons

Coordinate with, but do not duplicate:

- `rust-production-review` for standalone broad readiness or orchestrated final severity synthesis
- `rust-invariant-state-transitions` for coordinated mutation, rollback, caches, and operation-sequence atomicity
- `rust-build-portability` for feature, target, MSRV, generated-code, and consumer-matrix correctness
- `rust-invariant-performance` for hot-path cost, allocation, complexity, benchmark mechanics, and before/after performance evidence inside an established correctness envelope
- `rust-test-quality` for test organization, coverage mechanics, doctests, panic behavior, and assertion quality
- `scientific-citation-audit` for source existence, bibliographic accuracy, relevance, completeness, and credit
- `rust-error-variants` and `rust-parse-dont-validate` for typed error design and invariant-bearing boundary types

When these concerns conflict, preserve the scientific contract before optimizing or simplifying the implementation.

## Crate Guidance

Read applicable `AGENTS.md`, required reviewer guidance, and scientific assumptions for the reviewed contracts first. Select documentation, limitations, and source by changed contracts and nearby invariant owners. Report conflicting contracts rather than silently choosing one. Load only the matching crate reference, or the smallest set needed for an explicit cross-crate review:

- [`references/la-stack.md`](references/la-stack.md) for fixed-size linear algebra, determinant and solve paths, exact arithmetic, conversions, and numerical error contracts
- [`references/delaunay.md`](references/delaunay.md) for robust predicates, validation layers, geometric backends, topology, degeneracy, construction, and repair
- [`references/markov-chain-monte-carlo.md`](references/markov-chain-monte-carlo.md) for Metropolis-Hastings mechanics, proposal workflows, stochastic evidence, checkpoints, and diagnostics
- [`references/causal-triangulations.md`](references/causal-triangulations.md) for CDT foliation, topology, local moves, action conventions, ensembles, and simulation claims

When no reference matches, apply the portable workflow below and derive concrete invariants from the target repository. Keep API names, supported dimensions, model identities, fixture expectations, and repository commands in crate guidance rather than generalizing them here.

Select background without narrowing the checklist or independent-evidence requirements. Trace shared helpers, callers, and changed assumptions; broaden reads when contract boundaries are unclear and record why. Use the [fixture procedure](references/context-selection-fixtures.md) only when testing background-selection instructions.

## Scope And Review Mode

Include nearby code that owns a scientific invariant even when it is outside the initial diff. Typical scope includes formulas, kernels, predicates, factorizations, solvers, exact-arithmetic paths, conversions, tolerances, random samplers, scientific fixtures, properties, examples, benchmarks, and documentation claims.

For direct invocation, read [the standalone workflow](references/standalone-workflow.md).

## Workflow

### Establish The Scientific Contract

Before judging implementation details, state:

- the quantity, model, distribution, predicate, or transformation being computed
- its input domain, preconditions, units, scale, coordinate system, and conventions
- supported dimensions, precision backends, features, and exceptional or degenerate regimes
- whether the result is exact, correctly rounded, bounded, approximate, filtered, or statistical
- promised failure behavior for invalid, singular, non-finite, unrepresentable, or unsupported inputs
- the reference method and the assumptions required for its guarantees

Treat an absent, contradictory, or materially ambiguous contract as a finding. Do not silently choose a scientific convention when that choice changes public meaning.

### Trace The Algorithm Against The Contract

Verify the implemented formula and every branch, fallback, and feature backend. Check:

- indices, loop bounds, dimensions, shapes, strides, permutations, pivot signs, orientation, and storage conventions
- base, boundary, degenerate, singular, rank-deficient, empty, and unsupported cases
- preservation of algebraic, geometric, topological, probabilistic, and dimensional invariants
- equivalence of specialized and general paths on their shared domain
- agreement of fast filters and exact or robust fallbacks where both are defined
- casts, integer ranges, rational reductions, and exact-arithmetic division preconditions
- whether a named algorithm actually matches the cited method and its required assumptions

Prefer a derivation, invariant trace, or counterexample over intuition. If a branch changes the scientific question, report that directly.

### Numerical behavior

For changed arithmetic, tolerances, predicates, or numerical representations,
read [numerical behavior](references/numerical-behavior.md).

### Require Independent Evidence

Choose an oracle that does not reuse the algorithm, representation, error-bound helper, conversion path, or core assumption under test. Strong evidence includes:

- analytically known values or independently derived closed forms
- exact rational or integer arithmetic for bounded inputs
- higher-precision arithmetic with a justified precision margin
- a genuinely different reference algorithm or independently implemented library
- algebraic, geometric, topological, or metamorphic identities
- published examples whose assumptions and expected values are checked independently

Agreement between two wrappers around the same implementation is supplementary evidence only. State shared-assumption risk when external libraries use the same underlying algorithm.

Cover the supported dimension and feature matrix, plus adversarial regimes such as degeneracy, near-degeneracy, ill-conditioning, extreme magnitudes, mixed scales, duplicate values, and conversion boundaries. Preserve discovered counterexamples as deterministic regression fixtures; use hexadecimal floats or bit patterns when exact IEEE-754 boundaries matter.

### Stochastic semantics

For stochastic algorithms, RNG ownership, checkpoints, or reproducibility, read
[stochastic semantics](references/stochastic-semantics.md).

### Validate Scientific Benchmarks And Claims

A benchmark is valid scientific evidence only when it measures a supported operation on valid inputs and checks that each implementation computes the same mathematical result.

Verify that:

- every reported dimension, regime, and feature is actually supported; omit unsupported rows rather than timing an error or placeholder path
- competitors perform equivalent mathematical work under equivalent precision and validation assumptions
- representative inputs are accompanied by adversarial cases relevant to the claimed scope
- correctness is checked outside the timed region with an independent or justified oracle
- before/after runs use the same command, inputs, features, toolchain, and environment
- documentation distinguishes guarantees and theorems from empirical observations
- exact, robust, bounded, and approximate claims are not used interchangeably

Verify the prerequisites for comparable measurements, but defer benchmark execution, optimization, harness tuning, noise analysis, and speedup classification to `rust-invariant-performance`. If the scientific workload is invalid, its timing is not performance evidence.

## Fixes

When fixes are explicitly authorized, read
[`references/fix-workflow.md`](references/fix-workflow.md) before editing. Do not
load it for review-only work.

Do not broaden scope into unrelated style cleanup. If correctness depends on a domain choice the repository does not establish, report the alternatives and request maintainer direction rather than inventing the model.

## Validation

Use repository-local commands and focused checks that cover the corrected
scientific contract. Reuse valid evidence where the workflow accepts it. Run a
required final aggregate gate even if it repeats focused checks, recording the
overlap without counting it as independent evidence. Relevant changes, distinct
configurations, and deliberate statistical or nondeterminism checks also justify
reruns; avoid repetition solely for reassurance.

Typical evidence includes:

- focused unit and integration tests for known values and exact error variants
- property or metamorphic tests across supported dimensions and regimes
- exact, high-precision, or independently implemented reference comparisons
- feature/backend parity tests and doctests for public scientific claims
- deterministic adversarial fixtures for every fixed counterexample
- Clippy and compile checks for all affected feature combinations
- the repository's full CI command for core numerical behavior when required

Performance validation comes only after correctness validation and must use the same representative benchmark command for before/after comparison.

## Report Findings

For each finding, include:

- severity and affected file or API
- the violated scientific contract or assumption
- a derivation, counterexample, independent result, or other evidence
- the practical consequence and affected domain
- the smallest correct fix and the validation that would prove it

Separate optional strengthening suggestions from correctness defects. When no actionable defect is found, state which contracts, adversarial regimes, and independent evidence were actually checked.
