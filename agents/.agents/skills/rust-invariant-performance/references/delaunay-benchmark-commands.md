# Delaunay Benchmark Commands

Load this reference only for Delaunay benchmark execution, PR regression checks,
release comparisons, or performance-document promotion. Read the current
repository's `benches/README.md`, `docs/dev/TUNING-PERFORMANCE.md`, and `justfile`
before selecting commands. They own the targets, arguments and required gates.

## Routine and Focused Work

- Keep correctness gates and untimed benchmark preflight distinct from sampling.
- Select representative public API measurements for the claimed dimensions and
  input families; internal diagnostics and large stress workloads remain opt-in.
- Preserve repository-required checks within the authorized scope. A focused
  diagnostic cannot establish a broad construction-performance claim.

Treat small dimension-by-dimension movement as noise unless repeatable or material. A clear 3D or aggregate proxy regression should block a broad construction-performance claim.

## Release Evidence

Distinguish acquisition, saved-baseline comparison, retained-artifact rendering,
and publication. Some aggregates measure before promoting; inspect dependencies
before using a command for a report-only request. Comparisons require compatible
source/harness/plan and environment evidence, not merely an existing baseline.

See the revision-bound
[Delaunay example](../../scientific-benchmarking/references/repository-examples.md#delaunay-one-plan-separate-diagnostics-and-rendering)
for the verified public API plan and separated command roles. Do not use release
commands as routine commit checks or treat historical skill command lists as
current repository authority.
