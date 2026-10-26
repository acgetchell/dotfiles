# Verified repository examples

These are source-inspection examples checked on 2026-10-26, not new measurements
or proof that every repository path satisfies this skill. Delaunay and la-stack
checkouts were clean and matched their GitHub default-branch heads below.
Recheck the current implementation before applying a role or example. Repository
docs own exact commands and versions; do not copy the inventories into this skill.

## Delaunay: one plan, separate diagnostics and rendering

Inspected revision: `3fa8a9907101c523574a0d17991a1f652b5419dc`.

- The [benchmark guide](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/benches/README.md)
  and [measurement owner](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/tooling/python/benchmark_utils.py)
  define a three-target public API plan: `ci_performance_suite`,
  `circumsphere_containment`, and `locate`. `RELEASE_SIGNAL_MEASUREMENT_PLAN`,
  `run_release_signal_measurement_plan`, and `_sample_delaunay_targets` trace
  acquisition; `preflight_release_signal` exercises fixtures without statistical
  samples. The independent sampling policy preserves per-group counts.
- The [native API harness](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/benches/ci_performance_suite.rs)
  reuses prepared triangulations among validation operations in
  `bench_validation_dimension`. `bench_insert_case` clones mutation state in
  batched setup. Validation itself remains timed in `bench_validate_case`, because
  it is the public API being measured. These are different timing contracts.
- The [PR workflow](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/.github/workflows/benchmarks.yml)
  measures current and baseline in one job. It does not repeat that comparison
  on every merge; the separate release workflow owns exact tagged evidence.
  Neither correctness CI nor justified release measurements are redundant merely
  because the PR already ran.
- The [profiling workflow](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/.github/workflows/profiling-benchmarks.yml)
  is manual-only and chooses timing or instrumented allocations in one job.
  Allocation mode checks its API tests and selects `memory_profiling`; it does
  not publish a release baseline. Its timings are not comparable to ordinary
  uninstrumented timings.
- The [Justfile](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/justfile)
  separates `bench-latest` acquisition from strict `bench-perf-summary` rendering.
  `performance-release` measures and promotes; `performance-doc` consumes retained
  artifacts. A report-only request must not call the acquisition aggregate.
  [Measurement tests](https://github.com/acgetchell/delaunay/blob/3fa8a9907101c523574a0d17991a1f652b5419dc/tests/tooling/test_performance_measurement.py)
  reject duplicate targets, changed raw/policy/gate inputs, and successful
  processes with incomplete samples.

This is the post-refactor design, not the obsolete broad release plan. Old
reports remain historical; they do not authorize reusing incompatible timings.

## la-stack: declarative phases and independent report eligibility

Inspected revision: `110b7e5fba4a38fb856ac4509e8b094ad19442af`.

- [Benchmarking](https://github.com/acgetchell/la-stack/blob/110b7e5fba4a38fb856ac4509e8b094ad19442af/docs/BENCHMARKING.md)
  distinguishes measurement, scratch promotion, retained report rendering and
  README publication. The [adoption record](https://github.com/acgetchell/la-stack/blob/110b7e5fba4a38fb856ac4509e8b094ad19442af/docs/dev/performance-tooling-adoption.md)
  explains which mechanics moved to the installed `research-repo-tools` package
  and which historical runs are frozen rather than eligible for regeneration.
- The [full declaration](https://github.com/acgetchell/la-stack/blob/110b7e5fba4a38fb856ac4509e8b094ad19442af/tooling/measurements/full.toml)
  records required IDs, per-phase discovery, gates, toolchain/environment,
  compatibility and series mappings. The [native commands](https://github.com/acgetchell/la-stack/blob/110b7e5fba4a38fb856ac4509e8b094ad19442af/tooling/performance.just)
  run all comparison implementations in the baseline phase and filter to
  `la_stack` in the current phase; exact workloads run in both. nalgebra/faer
  series retain their baseline origin rather than being sampled again for each
  view or labeled as current-phase data.
- [Exact benchmarks](https://github.com/acgetchell/la-stack/blob/110b7e5fba4a38fb856ac4509e8b094ad19442af/benches/exact.rs)
  validate fixed inputs and the deterministic random corpus before registering
  timed operations. The native gate covers `vs_linalg_inputs` and
  `exact_bench_config`. Supported determinant filters have explicit registration
  boundaries; timing an unsupported error path would not fill a coverage gap.
- Native discovery can include additional diagnostics beyond required report
  rows. Those observations still need complete validation; omitting them from a
  chart does not remove acquisition cost. This is an audit consideration, not a
  claim that every discovered case belongs in routine release measurements.

## Shared tooling boundary

The inspected [research-repo-tools declaration guide](https://github.com/acgetchell/research-repo-tools/blob/e5a9120e13376352bc7d6705346c1d592343d6c6/docs/DECLARING_PERFORMANCE.md)
describes discovery before gates/sampling, retained acquisition declarations,
independent policy verification, and report eligibility. This is a source
snapshot, not a new dependency pin or an assertion of registry availability.
Use the consumer's installed public API and declared version. Keep its native
commands, scientific catalogs and gates local; request reusable engine changes
upstream instead of duplicating execution or provenance validation.
