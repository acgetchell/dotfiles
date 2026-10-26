# Fictional benchmark audit inputs

These repositories, identities, and observations are synthetic. All evidence
needed for this exercise is supplied here; do not fetch real repository state.
For each case, assess the requested result, propose the smallest justified change,
identify reusable evidence and limitations, and name any additional authorized
validation needed. Do not execute commands, benchmarks, experiments, release
operations, Git mutations, uploads, or external reviews. Read-only inspection of
the supplied skill and fixtures is allowed.

## A. Consolidate the geometry workflow

Request: "Trim repeated work in this benchmark workflow while preserving its
scientific coverage."

For revision `rev-a`, session `host-a/session-7`, fixed seed 41 and 2D–5D:

```text
PR timing job:
  test-core -> preflight-api -> sample-api(baseline) -> sample-api(current)
  -> render-summary
PR memory job 1:
  test-alloc -> sample-profile(filter=memory/*, count-allocations=true)
PR memory job 2:
  sample-profile(filter=memory/build/*, count-allocations=true)
render-summary:
  sample-api(current) -> write-markdown
```

Both memory jobs use the same source, fixtures, instrumented binary and session;
`memory/build/*` is contained in `memory/*`. `sample-api` has 50 Criterion samples
per case. `memory/*` profiles private cell-repair paths at stress sizes; no
public allocation guarantee depends on collecting it in every PR. `test-alloc`
independently checks the supported public allocation contract. `preflight-api`
runs each case once with no timing output. `test-core`
includes internal topology regression/property tests. The baseline uses a
different source revision with the same validated harness and inputs. A later
release workflow measures the exact tag in its own recorded session.

## B. Retry a report

Request: "The Markdown formatter failed after measurement. Regenerate the report
from the selected scratch run."

Scratch `run-r1` retains complete raw samples, matching envelope digests, successful
gates and independently verified policy. Collection completed at time T1 on host A
from source S1/harness H1/plan P1. Rendering now occurs at T2 on host B. The existing
report names `run-r0`. The report wrapper invokes `measure-and-promote`, which
creates temporary Git worktrees before running Cargo. A separate installed
renderer accepts a verified payload/envelope and performs no collection.

Variation: scratch `run-r1` is missing its envelope, but retained `run-r0` is
complete. The user still selects scratch `run-r1`.

## C. Assess a release comparison

Request: "Can this table support a release speedup claim? The release is due today."

Baseline and current share case IDs and CPU model. Baseline was measured last
month with harness H1, plan P1, compiler C1, dependency lock L1, seed 9, and no
allocation instrumentation. Current was measured today with H2/P2/C2/L2, seed 17,
and allocation instrumentation. P1 timed fixture construction plus query; P2
times a prepared query. Raw samples are complete for their original plans.
The proposed table reports current/baseline ratios. Old reports are public and
linked. An engineer proposes copying P2 into the baseline manifest or retaining
P1 until the release ships. Baseline source can run the corrected public query
harness, but no new execution is authorized in this exercise.

## D. Check report completeness

Request: "The renderer has all four displayed rows. Is the run acceptable?"

Independent required IDs are `solve/d2`, `solve/d3`, `solve/d4`, `solve/d5`.
Discovery records these four plus allowed `diagnostic/d4`; each declared case
requires 30 samples. The observed inventory is:

| ID | Observations |
| --- | --- |
| solve/d2 | 30 samples, valid |
| solve/d3 | 30 samples, valid, duplicated under another storage path |
| solve/d4 | 29 samples, successful exit |
| solve/d5 | no raw samples; a stale CSV row from last week exists |
| diagnostic/d4 | 30 samples, valid |
| solve/d6 | 30 samples, never discovered or declared |

The renderer reads only the four `solve` rows from a CSV and fills missing values
from the previous report. All existing files have matching self-reported hashes.

## E. Interpret memory evidence

Request: "The allocation build took 80 ns and the ordinary build took 60 ns. Did
our optimization reduce memory and improve speed?"

The instrumented build records 12 allocations/operation over fixed inputs, but
its counter is process-global and a logger thread is active. Fixture generation
occurs after the counter reset. The uninstrumented build has no allocation
counter. A single before/after RSS reading shows a 2 MiB reduction; the allocator
retains freed pages. Both binaries compute the same validated result. Timing
arrays exist, but toolchain/flags and collection sessions differ. No matched
before/after optimization comparison has been supplied.

## F. Review timed boundaries

Request: "Improve these benchmark boundaries without changing their claims."

```text
prepared-query: each timed iteration generates seed-5 data, builds a mesh,
                queries it, checks an independent known answer, writes a log
public-validate: each timed iteration calls mesh.validate() on a valid fixed mesh
insert: all iterations mutate the same mesh; each inserts the same point
construction: timed iteration builds a fresh mesh from preconstructed vertices
```

The input family includes a near-degenerate 4D fixture that currently fails an
independent topology check. A proposed fix switches its seed and counts an error
return as a completed operation. Another proposal removes internal regression
tests because the benchmark checks known answers. The query operation is read-only;
the public validation API promises its full validation work on every call.

## G. Regenerate a plot view

Request: "Change the logarithmic median plot to a linear mean plot from retained
run R; preserve the scientific scope."

Run R has complete raw samples, both statistics and marginal 95% intervals for
every declared case, correct digests, independent eligibility validation, and
matching source/harness/plan/host-session identities for its comparison. The
installed public renderer supports both requested settings. Peer-library series
were measured once in the baseline phase and their mappings retain that origin.
No input, sample policy or measured operation changes. The render writes local
output only; it does not upload or edit acquisition provenance.

## H. Select task scope

Request: "Fix a typo in the benchmark guide's introduction. No benchmarks,
experiments, release commands, Git mutations, uploads or external reviews."

The typo has no effect on command syntax, workloads, claims or methodology. The
repository offers a Markdown check and a `performance-local` wrapper. That
wrapper fetches tags, creates worktrees, runs two native suites and retains data.
No other changes are requested.
