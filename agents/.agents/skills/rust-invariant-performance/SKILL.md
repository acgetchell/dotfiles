---
name: rust-invariant-performance
description: "Audit Rust code for best practical performance while preserving correctness invariants, parse-don't-validate boundaries, typed errors, safety, and API orthogonality. USE FOR: performance-sensitive Rust crates such as delaunay, la-stack, markov-chain-monte-carlo, and causal-triangulations; hot-path review for numerical, geometric, topological, linear-algebra, probabilistic, sampler, construction, validation, and repair code; allocation and complexity audits; benchmark-guided optimization reviews; PR or whole-repo performance baseline audits where correctness constraints must remain intact. DO NOT USE FOR: performance suggestions that ignore invariants, generic style/import cleanup (use rust-style-hygiene), general production correctness review without a performance focus (use rust-production-review), parse-don't-validate review without a performance focus (use rust-parse-dont-validate), or non-Rust code."
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

Every meaningful performance recommendation or implementation must be measured,
not inferred. Before changing performance-sensitive code, run the smallest
representative benchmark, smoke test, or allocation check that covers the
claimed hot path and record the command and result. After each bounded change,
rerun the same command before calling the change a performance improvement.

If the after measurement regresses, treat that as a failed optimization: revert,
retune, or narrow the change before moving on. Do not rely on subjective
complexity arguments, Criterion reports from unrelated benches, or "should be
faster" reasoning when a representative proxy exists.

Interpret benchmark evidence statistically and honestly. Small per-case timing
wobbles can be normal for local smoke tests, especially when the aggregate proxy
and correctness checks still look healthy. Clear regressions in a representative
case or in the aggregate proxy should block the change. Do not game mixed
benchmark evidence by adding dimension-, size-, or fixture-specific branches
unless the algorithm is genuinely different for that domain case and the code
would still be justified without the benchmark noise.

Prefer:

- naming an existing benchmark to run
- measuring before editing, changing one bounded performance surface, then
  measuring the same proxy afterward
- judging noisy local benchmark proxies by direction, size, and aggregate impact
  rather than demanding every subcase improve
- recommending a focused benchmark when no existing one covers the hot path
- checking allocation counts when heap traffic is the concern
- comparing invariant-preserving alternatives, not under-validated shortcuts
- considering realistic dimensions, sample counts, triangulation sizes, matrix
  shapes, or move counts for the crate
- using crate-specific smoke tests documented in `references/` when doing
  repo-wide or user-visible performance work; use analogous repo-local smoke
  tests when the exact command differs by crate

Flag:

- performance claims without before/after measurements from the same command
- dimension-, input-size-, seed-, or fixture-specific code paths added only to
  rescue mixed benchmark output rather than because the domain algorithm requires
  them
- clear representative-proxy regressions that are dismissed as noise without
  rerunning, reverting, or explaining why the benchmark is no longer relevant
- benchmark fixtures that are too clean, too small, or unrelated to the claimed
  improvement
- benchmark code that logs, allocates, parses config, or constructs heavy inputs
  inside the measured closure
- performance changes without regression tests for the invariant they rely on

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

## Command Taxonomy

When a repo provides standardized benchmark recipes, distinguish routine
correctness validation, performance evidence, release evidence, and docs
promotion. Do not recommend expensive release-comparison commands as a default
pre-commit step.

Prefer this order:

- Run the repo's normal correctness gate before committing or handing off work.
  In many Rust crates this is `just ci`, but defer to the repo's own
  development docs.
- For performance-sensitive code, run the smallest representative benchmark or
  smoke proxy before and after the change.
- For PR-ready performance work, run the repo's local regression guard when one
  exists.
- For release prep, run the curated release-signal suite and release-comparison
  report commands.
- For already-published releases, compare stored release benchmark artifacts
  instead of rerunning old code locally when the repo supports that workflow.

Common command roles:

- Correctness gate: compile, lint, test, doc, example, and benchmark-harness
  validation. This should be the routine pre-commit check.
- Focused benchmark: targeted Criterion or domain-specific benchmark for the
  hot path under review.
- Smoke proxy: broad but relatively cheap wall-clock or allocation proxy used
  before pushing performance-sensitive changes.
- Regression guard: local branch-vs-baseline comparison used for PR-ready
  performance evidence.
- Release-signal suite: curated benchmark set for release-to-release evidence,
  usually slower and not a routine commit gate.
- Release artifact comparison: compares benchmark data already attached to
  published releases.
- Release docs promotion: updates curated performance documentation and archives
  the previous report; this is a release-maintenance task, not an audit default.

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
