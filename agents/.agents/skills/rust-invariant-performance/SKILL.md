---
name: rust-invariant-performance
description: "Audit performance-sensitive Rust while preserving invariants, boundary parsing, typed errors, safety, and API orthogonality. Use for hot numerical, geometric, topological, linear-algebra, probabilistic, construction, validation, and repair paths; allocation and complexity analysis; benchmark-guided optimization; and performance/correctness tradeoffs."
---

# rust-invariant-performance

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

Default changed-code mode:
- Review newly added or modified Rust code and nearby hot-path context.
- Ignore unrelated unchanged code unless it defines the invariant, benchmark, or
  performance contract the change relies on.

Pull-request mode:
- Use when the user says "PR", "this branch", "diff against main", or similar.
- Review changed hot paths first, then adjacent invariant boundaries and
  benchmarks needed to evaluate the change.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline
  audit", or similar.
- Audit public hot paths, core algorithms, allocation-heavy loops, validation
  layers, construction/sampling/repair paths, and benchmarks.
- Produce a prioritized performance plan; do not require every historical issue
  to be fixed in one patch.

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

### 2. Preserve Parse-Don't-Validate

Performance should improve the invariant model rather than bypass it.

Prefer:

- public/raw APIs that parse into refined values such as ranges, positive values,
  dimensions, bit depths, budgets, probabilities, matrix shapes, valid moves, or
  topology guarantees
- internal hot paths that accept those proof-bearing types and compute
  infallibly
- prevalidated batch wrappers for repeated operations over validated data
- fallible setters/builders that validate before mutation
- private fields and infallible getters for stored valid state

Flag:

- repeated validation inside loops when validation evidence could be carried by a
  type
- raw tuples, raw floats, raw counts, raw dimensions, raw indices, or string modes
  accepted by hot internals when a refined type exists or should exist
- `Result` in inner computation only because earlier validation proof was
  discarded
- public plain-value APIs that can panic on representable caller input

### 3. Allocation and Data Movement

Look for heap traffic and copies that matter at scale.

Check:

- repeated `Vec`, `HashMap`, `BTreeMap`, `String`, `Box`, or `collect`
  allocation in loops
- cloning large matrices, triangulations, point sets, samples, simplex lists, or
  adjacency data to appease borrowing
- formatting strings on hot paths or inside measured benchmark closures
- avoidable conversions between iterator, slice, array, small-buffer, and heap
  forms
- opportunities to preallocate, reuse buffers, stream iterators, or store compact
  keys

Flag:

- allocation introduced by error handling, logging, or instrumentation on the
  success path
- repeated construction of identical lookup tables, masks, neighborhoods,
  proposal distributions, sorted keys, or validation workspaces
- data layout that fights the dominant traversal order

### 4. Complexity and Algorithmic Shape

Prefer algorithmic wins over tiny local rewrites.

Check:

- accidental quadratic or worse behavior from nested scans, repeated sorting,
  repeated hashing, or repeated validation
- sort keys recomputed during comparison instead of precomputed once
- exact arithmetic, determinant work, topology validation, matrix factorizations,
  or probability calculations repeated when cached results remain valid
- unbounded retry, repair, construction, or sampling loops lacking typed budgets
- fallback paths that silently do expensive work on common inputs

Flag:

- changing algorithmic behavior without proving that invariants and public
  semantics are preserved
- caching that can become stale without an explicit invalidation story
- parallelism that makes result ordering, RNG streams, topology mutations, or
  floating-point reduction semantics nondeterministic

### 5. Numerical, Statistical, and Topological Constraints

Treat domain correctness as part of the performance contract.

Flag any optimization that changes these semantics unless the user explicitly
asked for a breaking correctness-preserving redesign and tests/benchmarks cover
the new contract.

### 6. Error Handling and Diagnostics

Fast code must still fail loudly and usefully.

Check:

- recoverable public failures return `Result<_, TypedError>`
- error variants preserve observed values, expected constraints, and enough
  context for debugging
- diagnostics use tracing or project-approved logging and stay out of measured
  hot loops
- failed operations do not partially mutate caller-visible state

Flag:

- replacing typed errors with `Option`, `bool`, sentinel values, strings, or
  panics for speed
- formatting or allocation-heavy diagnostics on the success path
- debug-only checks for conditions reachable from public inputs

### 7. Benchmark Accountability

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

## Common Recommendations

Use these when they fit the codebase:

- parse raw input once, then pass a refined value inward
- introduce a small proof-bearing type for validated ranges, dimensions, counts,
  probabilities, matrix shapes, budgets, or move sets
- split raw public APIs from `*_in_range`, `*_with_budget`, `*_for_batch`, or
  similar prevalidated APIs
- precompute sort/comparison keys once
- replace repeated allocation with reusable buffers where ownership remains
  clear
- keep cold exact arithmetic, validation, or diagnostic paths out of fast
  filters
- add typed budgets to retry, repair, or rejection-sampling loops
- make cache invalidation explicit before adding caches
- add or update benchmarks before claiming a win

## Output Format

### Scope
- State changed-code, pull-request, or whole-repo baseline mode.
- Name the likely hot paths reviewed.

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Correctness-Preserving Wins
- Concrete improvements that reduce cost while strengthening or preserving
  invariants.

### Hot-Path Allocation Issues
- Avoidable allocation, cloning, formatting, boxing, or data movement.

### Complexity / Algorithmic Issues
- Accidental complexity, repeated work, missing budgets, stale-cache risks, or
  opportunities for better algorithmic structure.

### Invariant and API Risks
- Any performance suggestion or implementation detail that weakens
  parse-don't-validate, typed errors, public semantics, or safety.

### Benchmark Gaps
- Benchmarks to run or add, and what each should measure.

### Benchmark Evidence
- For performance implementations or claims, list the representative command,
  before result, after result, and whether the same proxy improved, held steady,
  or regressed.
- If no representative benchmark or smoke test exists, say so explicitly and
  recommend adding one before claiming a performance win.

### Not Worth Optimizing
- Cold paths or cosmetic changes that should not distract from real hot paths.

### Do Not Change For Performance
- Explicit invariants, APIs, diagnostics, or semantics that must stay intact.
