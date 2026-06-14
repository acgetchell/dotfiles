# delaunay Performance Invariants

Use this reference when applying `rust-invariant-performance` to the `delaunay`
crate or closely related computational-geometry code.

## Preserve

- Robust predicate sign behavior, including fast filters, exact fallback, and
  deterministic degeneracy handling.
- Delaunay, PL-manifold, adjacency, Euler characteristic, ridge-link, and
  topology-guarantee invariants.
- Validation layering: element/structure/topology checks must not be replaced by
  Level-4 predicate work or skipped for speed.
- Parse-don't-validate boundaries such as coordinate ranges, positive values,
  Hilbert bit depths, validated quantized batches, topology guarantees, and
  typed budgets.
- Deterministic construction behavior, including Hilbert ordering, retry policy,
  deduplication semantics, and reproducibility from seeds.
- Typed errors for non-convergence, invalid input, topology failure, predicate
  failure, and construction fallback context.

## Hot Paths

- Geometric predicates and exact-arithmetic cold paths.
- Incremental insertion, flips, local repair, and neighbor rebuilds.
- Hilbert ordering, quantization, deduplication, and construction preprocessing.
- Topology validation and Delaunay validation, especially when run during repair
  or construction retries.
- Query and locate traversal, adjacency/ridge/facet iteration, and boundary
  extraction.
- Benchmark fixture construction when it is inside measured closures.

## Performance Review Checks

- Prefer validating bounds, bit depths, domains, and budgets once, then passing
  proof-bearing values into inner loops.
- Precompute Hilbert keys, predicate inputs, facet keys, or sorted order when a
  comparison would otherwise recompute them.
- Check for repeated collection of simplices, facets, ridges, or vertex keys
  inside nested loops.
- Watch for heap allocation in predicate-adjacent paths, repair loops, and
  validation scans.
- Keep exact arithmetic, verbose diagnostics, and full topology validation out of
  fast filters unless they are the explicit validation being measured.
- Require typed work budgets for repair, flips, insertion retries, or rejection
  loops; do not use unbounded retry for speed or convenience.

## Benchmarks to Prefer

- For user-visible construction or whole-repo performance work, use
  `just perf-large-scale-smoke` as the acceptance proxy: run it before the
  change, make the change, rerun the same command, and report the before/after.
  If only one dimension is under investigation, the dimension-specific
  large-scale debug recipes can support diagnosis, but they do not replace the
  full smoke proxy when the claim is broad.
- Treat small dimension-by-dimension timing movement as statistical noise unless
  it is repeatable or large enough to matter. Do not add dimension-specific
  branches just to make the smoke table look cleaner; only specialize by
  dimension when Delaunay geometry/topology genuinely needs a different
  algorithmic path. Clear regressions in 3D or in the overall smoke proxy should
  block the change.
- Construction and topology-guarantee benchmarks for insertion/retry changes.
- Predicate cold-path benchmarks for numerical fallback changes.
- Hilbert/order benchmarks for preprocessing and deduplication changes.
- Validation benchmarks when changing topology, adjacency, manifold, or Euler
  checks.
- Allocation benchmarks for hot-path data-structure or buffer changes.

## Do Not Optimize Away

- Exact fallback correctness or deterministic degeneracy behavior.
- Validation that protects caller-observable topology or mutation invariants.
- Error context needed to diagnose failed construction or repair.
- Stable/reproducible ordering where public behavior or tests rely on it.
