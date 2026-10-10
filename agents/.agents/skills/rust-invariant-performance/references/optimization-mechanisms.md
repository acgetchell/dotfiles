# Optimization Mechanisms

Use the sections that explain an observed cost. These are candidate mechanisms,
not a requirement to optimize each category.

## Preserve Parse-Don't-Validate

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

## Allocation and Data Movement

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

## Complexity and Algorithmic Shape

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

## Numerical, Statistical, and Topological Constraints

Treat domain correctness as part of the performance contract.

Flag any optimization that changes these semantics unless the user explicitly
asked for a breaking correctness-preserving redesign and tests/benchmarks cover
the new contract.

## Error Handling and Diagnostics

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

## Candidate Improvements

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
