---
name: rust-scientific-correctness
description: "Audit Rust scientific and numerical code for mathematical validity, numerical robustness, independent validation, reproducibility, and truthful scientific claims on changed code or whole-repo baseline audits when explicitly requested. USE FOR: scientific Rust crates such as delaunay, la-stack, markov-chain-monte-carlo, and causal-triangulations; floating-point and exact arithmetic; linear algebra; computational geometry or topology; numerical predicates and solvers; probabilistic algorithms; tolerances and error bounds; scientific fixtures; and scientific benchmark validity. DO NOT USE FOR: general production review without a scientific correctness focus (use rust-production-review), performance optimization or benchmark mechanics (use rust-invariant-performance), test mechanics alone (use rust-test-quality), citation metadata or credit completeness (use scientific-citation-audit), or non-Rust scientific code (use python-scientific-review)."
---

# Rust Scientific Correctness

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

- `rust-production-review` for broad Rust readiness, API, safety, mutation, maintainability, and final severity synthesis
- `rust-invariant-performance` for hot-path cost, allocation, complexity, benchmark mechanics, and before/after performance evidence inside an established correctness envelope
- `rust-test-quality` for test organization, coverage mechanics, doctests, panic behavior, and assertion quality
- `scientific-citation-audit` for source existence, bibliographic accuracy, relevance, completeness, and credit
- `rust-error-variants` and `rust-parse-dont-validate` for typed error design and invariant-bearing boundary types

When these concerns conflict, preserve the scientific contract before optimizing or simplifying the implementation.

## Crate Guidance

Read repository-local instructions, public documentation, limitations, and current source first. Use them to establish the active contract; when they disagree, report a scientific-contract inconsistency rather than choosing one silently. Load only the matching crate reference, or the smallest set needed for an explicit cross-crate review:

- [`references/la-stack.md`](references/la-stack.md) for fixed-size linear algebra, determinant and solve paths, exact arithmetic, conversions, and numerical error contracts
- [`references/delaunay.md`](references/delaunay.md) for robust predicates, validation layers, geometric backends, topology, degeneracy, construction, and repair
- [`references/markov-chain-monte-carlo.md`](references/markov-chain-monte-carlo.md) for Metropolis-Hastings mechanics, proposal workflows, stochastic evidence, checkpoints, and diagnostics
- [`references/causal-triangulations.md`](references/causal-triangulations.md) for CDT foliation, topology, local moves, action conventions, ensembles, and simulation claims

When no reference matches, apply the portable workflow below and derive concrete invariants from the target repository. Keep API names, supported dimensions, model identities, fixture expectations, and repository commands in crate guidance rather than generalizing them here.

## Scope And Review Mode

Use changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for the repo, whole repo, entire repo, or equivalent.

Include nearby code that owns a scientific invariant even when it is outside the initial diff. Typical scope includes formulas, kernels, predicates, factorizations, solvers, exact-arithmetic paths, conversions, tolerances, random samplers, scientific fixtures, properties, examples, benchmarks, and documentation claims.

For review-only requests, report findings without editing. When the user asks to fix findings, make the smallest scientifically correct change, add independent evidence, and validate the affected regimes.

## Workflow

### 1. Establish The Scientific Contract

Before judging implementation details, state:

- the quantity, model, distribution, predicate, or transformation being computed
- its input domain, preconditions, units, scale, coordinate system, and conventions
- supported dimensions, precision backends, features, and exceptional or degenerate regimes
- whether the result is exact, correctly rounded, bounded, approximate, filtered, or statistical
- promised failure behavior for invalid, singular, non-finite, unrepresentable, or unsupported inputs
- the reference method and the assumptions required for its guarantees

Treat an absent, contradictory, or materially ambiguous contract as a finding. Do not silently choose a scientific convention when that choice changes public meaning.

### 2. Trace The Algorithm Against The Contract

Verify the implemented formula and every branch, fallback, and feature backend. Check:

- indices, loop bounds, dimensions, shapes, strides, permutations, pivot signs, orientation, and storage conventions
- base, boundary, degenerate, singular, rank-deficient, empty, and unsupported cases
- preservation of algebraic, geometric, topological, probabilistic, and dimensional invariants
- equivalence of specialized and general paths on their shared domain
- agreement of fast filters and exact or robust fallbacks where both are defined
- casts, integer ranges, rational reductions, and exact-arithmetic division preconditions
- whether a named algorithm actually matches the cited method and its required assumptions

Prefer a derivation, invariant trace, or counterexample over intuition. If a branch changes the scientific question, report that directly.

### 3. Audit Numerical Behavior

Distinguish a poorly conditioned problem from an unstable implementation. Identify whether a claimed bound is absolute, relative, forward, backward, or residual-based, and verify that its units and assumptions match the result.

Inspect:

- overflow, underflow, cancellation, absorption, rounding accumulation, and unsafe reassociation
- NaN, infinity, signed zero, subnormal values, and non-finite intermediates
- arithmetic order, fused multiply-add behavior, reduction order, and platform-dependent backends
- tolerance scale, units, monotonicity, validation, and behavior under rescaling
- whether computing an error bound can itself overflow, underflow, or round non-conservatively
- exact-to-inexact conversion, representability, rounding mode, and loss-of-precision contracts
- consistency between approximate classification and exact results near decision boundaries

Do not accept a numeric sentinel, panic, or silent rounding where the public contract requires a typed failure or exact result.

### 4. Require Independent Evidence

Choose an oracle that does not reuse the algorithm, representation, error-bound helper, conversion path, or core assumption under test. Strong evidence includes:

- analytically known values or independently derived closed forms
- exact rational or integer arithmetic for bounded inputs
- higher-precision arithmetic with a justified precision margin
- a genuinely different reference algorithm or independently implemented library
- algebraic, geometric, topological, or metamorphic identities
- published examples whose assumptions and expected values are checked independently

Agreement between two wrappers around the same implementation is supplementary evidence only. State shared-assumption risk when external libraries use the same underlying algorithm.

Cover the supported dimension and feature matrix, plus adversarial regimes such as degeneracy, near-degeneracy, ill-conditioning, extreme magnitudes, mixed scales, duplicate values, and conversion boundaries. Preserve discovered counterexamples as deterministic regression fixtures; use hexadecimal floats or bit patterns when exact IEEE-754 boundaries matter.

### 5. Review Stochastic Semantics And Reproducibility

For random or Monte Carlo code, establish the target distribution or transition contract, the assumptions required by any convergence claim, acceptance corrections, seed and stream semantics, statistical error model, and promised level of reproducibility. Require calibrated evidence rather than one lucky sample or an unexplained empirical threshold. Load the matching crate reference for concrete proposal, checkpoint, ensemble, or move invariants.

### 6. Validate Scientific Benchmarks And Claims

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

## Fix Rules

When fixes are authorized:

- repair the lowest layer that owns the violated invariant
- preserve typed scientific failures and diagnostic context
- keep exact paths exact and make approximation or rounding opt-in when the contract requires it
- add a deterministic regression test and an independent oracle or property for the corrected behavior
- update public claims, examples, fixtures, and benchmark coverage when their scientific meaning changes
- follow repository semver policy; do not preserve a compatibility alias that keeps a scientifically incorrect model alive
- rerun this audit if later refactoring changes formulas, arithmetic order, tolerances, precision or fallback behavior, RNG semantics, or scientific fixtures

Do not broaden scope into unrelated style cleanup. If correctness depends on a domain choice the repository does not establish, report the alternatives and request maintainer direction rather than inventing the model.

## Validation

Use repository-local commands when available. Select the narrowest checks that cover the corrected contract, then escalate when repository guidance or cross-cutting risk requires it.

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
