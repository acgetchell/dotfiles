# Test Runtime And Selection

Use this reference when test runtime, expensive fixtures, or test selection is
material. Match the cost of obtaining evidence to the behavior being proved.
Honor analysis-only requests: inspect source and retained measurements without
executing tests or collection, and distinguish inferred costs from observations.

## Choose The Owning Boundary

Separate pure parsing, invariants, and decision logic from acquisition,
provenance verification, and publication. Keep finite rejection matrices at the
smallest stable seam that owns their diagnostics. A malformed string should not
require a complete repository capture or successful workflow unless that
interaction is the contract. Retain representative integration coverage proving
that the outer entry point invokes the same boundary and propagates rejection.

Use real Git, files, child processes, installed artifacts, and services when
their behavior owns the risk. A deterministic fake can provide inputs to
downstream logic; assertions should still prove outcomes, not merely mocked
calls. Do not replace byte transport, concurrent-change detection, provenance,
cleanup, or failure-atomic publication evidence with in-memory approximations.

Keep complete workflow scenarios for meaningful interactions such as recovery
and handoff. Preserve distinct failure categories and necessary combinations;
reduce incidental setup rather than deleting behavioral coverage. Do not impose
a universal test pyramid or a fixed number of integration tests.

## Control Preparation Cost

Trace fixtures and helper calls through subprocesses, repository scans,
environment creation, source capture, serialization, and publication. Count
parametrized cases and fixture expansion when estimating repeated work. A
cached initial fixture does not eliminate recapture inside the action under
test.

Make large inventories explicit when input size is the contract. Keep their
boundary and scaling scenarios, while using small representative inputs for
unrelated rejection matrices. Exercise generated capture commands against an
isolated repository whose contents the test owns; verify their returned state
instead of scanning the developer's checkout merely to assert success.

Reuse immutable templates or prepared read-only inputs where their identity is
stable. Give each test fresh mutable documents, repositories, journals, and
output stores. Do not reuse serialized evidence across different roots or
source states without the applicable identity checks. Keep shared builders in
support modules rather than importing unrelated test modules for setup.

Inspect already pinned tooling for supported fixture and inspection APIs before
duplicating process wrappers or metadata parsers. Keep domain assertions and
repository-specific gate policy in the consumer tests; a shared fixture is
useful only when its contract fits the behavior being exercised.

## Select And Measure Deliberately

Inspect canonical recipes, collection boundaries, markers, and required gates.
Marker filtering can still collect the entire inventory; an independently
selectable module or directory can make an early guard cheaper. Keep aggregate
partitions complete and disjoint, with regression evidence for failure
propagation and argument forwarding. Prefer the current run's collected
inventory and bounded collector fixtures over nested full-suite collection.

Use focused selections during fixes and run the required final aggregate on the
final source state. Apply the existing validation ledger and rerun policy; do
not create overlapping reassurance tiers or weaken required platform checks.

When execution is authorized and useful, distinguish collection, setup, call,
and teardown costs. Add duration reporting to an already planned run where
possible. Record selection, environment, instrumentation, and cache state;
historical timings do not prove the current bottleneck or speedup.

For stable complexity contracts, consider deterministic resource evidence such
as bounded subprocess counts or input-scaling assertions instead of fragile
wall-clock thresholds. Check isolation and per-worker preparation before
parallelizing; additional workers can multiply collection and setup costs.
