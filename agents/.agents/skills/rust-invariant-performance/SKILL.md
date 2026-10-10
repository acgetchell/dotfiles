---
name: rust-invariant-performance
description: "Optimize or review Rust hot paths using representative cost evidence while preserving correctness and public contracts."
---

# rust-invariant-performance

Rust-orchestrator passes use the shared [execution-v1 contract](../rust-review-orchestrator/references/execution-v1.md).

Audit Rust code for performance while keeping the crate's correctness model
intact. The goal is to find the best practical performance inside the invariant
envelope, not to trade correctness, typed APIs, or diagnostics for speed.

## Core Rule

Optimize only after raw inputs have been parsed into invariant-bearing types.
Prefer moving validation outward and making inner hot paths infallible over
removing validation, replacing typed errors with sentinels, or relying on
debug-only checks.

Reject performance ideas that:

- weaken numerical, statistical, topological, shape, dimension, or API
  invariants
- replace parse-don't-validate boundaries with comments, `debug_assert!`,
  `Option`, `bool`, sentinel values, unchecked indexing, or stringly errors
- make invalid states easier to represent
- change public semantics, stochastic semantics, or reproducibility without an
  explicit API decision
- introduce `unsafe` in crates that forbid it
- remove diagnostics needed to debug correctness failures

Keep scientific validity under `rust-scientific-correctness`, coordinated mutation and rollback under `rust-invariant-state-transitions`, raw boundary modeling under `rust-parse-dont-validate`, typed failure taxonomy under `rust-error-variants`, build-matrix behavior under `rust-build-portability`, and durable regression strength under `rust-test-quality`. This skill owns cost, complexity, allocation, data movement, and benchmark evidence inside those contracts.

## References

Load the crate-specific reference only when working in that crate or when the
user asks for a cross-crate comparison:

- [`references/delaunay.md`](references/delaunay.md) for Delaunay triangulation,
  robust predicates, topology, construction, validation, Hilbert ordering, and
  repair paths.
- [`references/la-stack.md`](references/la-stack.md) for linear algebra,
  stack-oriented matrix storage, shape proofs, exact arithmetic, and numerical
  kernels.
- [`references/markov-chain-monte-carlo.md`](references/markov-chain-monte-carlo.md)
  for MCMC kernels, proposal/acceptance logic, RNG reproducibility, diagnostics,
  and statistical semantics.
- [`references/causal-triangulations.md`](references/causal-triangulations.md)
  for causal triangulation moves, topology constraints, slice structure, and
  Monte Carlo move performance.
- Read [`references/benchmark-evidence.md`](references/benchmark-evidence.md)
  only when implementing an optimization, evaluating a performance claim, or
  choosing between routine, PR, and release benchmark evidence.
- Read [`references/delaunay-benchmark-commands.md`](references/delaunay-benchmark-commands.md)
  only for Delaunay benchmark execution, PR regression checks, release
  comparisons, or performance-document promotion.

## Scope

Review performance-sensitive Rust paths in the supplied scope together with
nearby invariant and benchmark owners. When invoked directly without an exact
parent scope and result contract, read
[`references/standalone-workflow.md`](references/standalone-workflow.md).
Review-graph and Rust-orchestrator dispatches already own that information.

## Review Posture

Assume the author values correctness and already understands Rust. Be direct,
specific, and benchmark-oriented. Do not recommend micro-optimizations unless
they remove real cost from a hot path or protect a performance invariant.

When performance and correctness appear to conflict, preserve correctness and
look for a different design: proof-carrying types, prevalidated batches,
one-time parsing, cached keys, explicit budgets, or better data layout.

## Review Goals

### 1. Identify the Hot Path

Before suggesting changes, identify why the code is performance-sensitive.

Check:

- construction, insertion, repair, validation, query, predicate, sampling, matrix
  kernel, transition, scoring, or benchmark paths
- loops whose cost scales with vertices, simplices, samples, dimensions, matrix
  size, Markov steps, or triangulation moves
- code inside Criterion-measured closures or benchmark fixtures
- algorithms that repeat across many public calls

Flag:

- optimization work on cold error formatting, examples, tests, or one-time API
  parsing unless it blocks realistic workloads
- claims of speedup without a benchmark, profile, complexity argument, or
  plausible hot-path explanation

### 2. Select the relevant cost mechanism

Trace the observed cost through allocation, data movement, repeated work,
complexity, caches, or diagnostics. Read
[optimization mechanisms](references/optimization-mechanisms.md) when a concrete
candidate needs deeper review. Preserve the root's invariant and scientific
contracts for every candidate; moving detail does not relax them.

### 3. Benchmark Accountability

Require the smallest representative benchmark, smoke proxy, allocation check, or
complexity evidence before and after an implementation. Use the same command,
inputs, features, toolchain, and environment; keep fixture construction,
validation, logging, and parsing outside measured work.

Treat a clear regression as a failed optimization. Do not add
dimension-, size-, seed-, or fixture-specific branches merely to improve a noisy
table; specialization must follow a genuine domain algorithm boundary.

Load `references/benchmark-evidence.md` for detailed evidence selection,
before/after discipline, noise interpretation, and routine-versus-release command
roles.
