# Evidence contract

Use the repository's independent measurement declaration as the acceptance
authority. A payload that agrees with its own manifest is not sufficient: both
can describe the wrong workload. Hashes establish integrity, not authenticity.

## Identity and completeness

Before accepting a run or cached evidence, establish:

| Surface | Required evidence |
| --- | --- |
| Source | Exact revision and effective source bytes, including relevant dirty/untracked inputs; measured identity stays distinct from report-generation identity |
| Harness and plan | Harness/helpers, fixture generator and seeds/data, command arguments, filters, features, profile/flags, instrumentation, metric definition and measurement-plan identity |
| Inventory | Independent required/allowed/excluded cases, native discovery for each phase, observed semantic IDs and counts, dimension/size/input-family coverage, and report/peer mappings |
| Toolchain | Compiler, target, dependency/lock identities, harness version and inherited tooling pins, with performance-relevant environment overrides |
| Host/session | OS, architecture, CPU and relevant runtime configuration, measurement session and completion time; distinguish collection host from publication host |
| Raw evidence | Retained per-case samples and iteration counts, units, declared sample counts, estimates/statistics/confidence levels, successful gates and completed workloads; verify bytes against recorded digests |

Compare observed cases with the declared discovery inventory, not merely the rows
selected for a plot. Missing required cases, duplicate IDs, unexpected observations,
truncated samples, stale files, or failed workloads reject the affected evidence.
Additional diagnostic cases are allowed only when the plan permits and accounts
for them; selecting fewer report rows cannot repair incomplete acquisition.
Per-case sample counts can legitimately differ. Do not pad, discard, or relabel
observations to make them match a uniform policy.

## Comparisons and metrics

Measure current and baseline on the same host/session with deterministic inputs
and equivalent work, using scientifically justified repeated samples. Source
revisions intentionally differ; harness/plan, fixtures, features, compiler,
dependencies, target and runtime settings must satisfy the explicit comparison
policy. Explain any deliberate difference and its effect on the claim. A common
case name, release tag, or CPU model alone does not prove compatibility.

If compatibility fails, preserve useful absolute results as such, report missing
or incomparable coverage, and withhold ratios or speedup claims. A methodology
change may require both sides to be measured again under a validated common
harness. Do not retain a defective plan to reuse expensive old results, weaken
eligibility gates for a release deadline, or invent provenance for historical
data. If baseline code cannot perform equivalent work, say so.

Keep three metric contracts distinct:

- **Timing:** retain samples, counts, statistic, units, uncertainty and host
  limitations. Marginal confidence intervals do not by themselves establish a
  ratio interval or statistical significance. Do not cherry-pick favorable cases
  or rerun until a favorable result appears. Predeclare justified repeat trials
  and retain all valid outcomes.
- **Allocations:** count operations/bytes with a defined allocator, scope,
  reset/snapshot boundary, and isolation from unrelated threads, fixtures, and
  reporting. A deterministic count for fixed inputs is not a timing distribution.
  Instrumented timings are not interchangeable with uninstrumented API timings.
- **RSS:** identify process scope, sampling method, units and platform; allocator
  retention, process startup and host noise can affect the observation. Do not
  convert RSS deltas into exact allocation counts or present one reading as a
  stable memory guarantee.

Independent correctness tests remain required even when all benchmark fixtures
pass. A successful process exit or `black_box` consumption proves neither
mathematical validity nor complete sampling.

## Rendering, retention and invalidation

Separate acquisition, acceptance, rendering and publication. Reports and plots
read explicitly selected validated evidence, retain its original source/host/time,
and can be regenerated without executing benchmark or preflight commands. A new
render timestamp may be recorded separately. No silent resampling, fallback to
older history, or relabeling old samples as current measurements is allowed.

Retain the raw data and provenance required by the consuming contract, not only
CSV tables or images. Validate before replacing outputs; use the shared engine's
repeatable/transactional publication behavior instead of rebuilding it locally.
Report rendering may be offline while uploads remain separately authorized.

Distinguish a presentation-only change from an acquisition change. Formatting,
axis or row selection within an already complete eligible run need not resample.
Changed inputs, harness behavior, instrumentation, sampling policy, workload
inventory or measurement semantics invalidate affected reuse. Resume partial
runs only when the existing engine proves exact compatible identities and
completeness; directory existence or an unchanged source commit is not a cache
key. Regenerate the necessary measurements when authorized, otherwise report
what prevents completion.
