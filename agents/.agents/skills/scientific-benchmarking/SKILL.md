---
name: scientific-benchmarking
description: "Design or audit scientific benchmark workflows, remove duplicate measurements, and review performance evidence; not a benchmark campaign for ordinary code changes."
---

# Scientific Benchmarking

Use this skill for benchmark design, orchestration audits, duplicate-run removal,
or assessment of scientific performance evidence. Start with the requested
workload and claim; do not expand a focused task into a repository-wide review.

## Execution boundary

Separate inspecting or changing a workflow from executing it. Honor existing
authorization and explicit prohibitions on benchmarks, experiments, release
commands, Git mutations, uploads, and external reviews. A recipe can perform
several of these actions through dependencies. Inspect that chain before running
it; a report or preflight name does not establish its effects. If measurement is
prohibited, use static inspection or bounded mocks and identify the missing
measured evidence. Do not infer performance from those checks.

## Bounded workflow

1. **Trace ownership.** Follow repository guidance, canonical commands, workflow
   triggers/matrices, native harnesses, and report consumers for the requested
   scope. Record each workload's revision, phase, metric, input identity,
   measurement owner, raw output, and consumers. Repository docs own exact
   targets and commands; retain their small command vocabulary.
2. **Classify workloads.** Routine CI and release measurements should cover
   representative public API workflows. Internal microbenchmarks, implementation
   diagnostics, and large stress workloads stay opt-in. Public API methods can
   be small kernels; classify by the caller's contract, not runtime or file
   name. Unit, integration, property, and regression tests independently establish
   correctness, including tests of internals; preserve them.
3. **Inspect timed boundaries.** Put deterministic fixture generation, independent
   known-answer/invariant checks, and unrelated reporting outside timing unless
   they are the API behavior being measured. Retain validation required by that
   public API. Reuse immutable validated fixtures for read-only operations;
   mutations need isolated/reset state and construction benchmarks must construct
   afresh. Check batching, copying, destruction, lazy work, and result consumption
   against the stated metric. Failed or invalid work is never successful timing
   evidence; abort acceptance rather than substituting an easier fixture.
4. **Remove orchestration duplication.** Give each workload/configuration one
   measurement owner per revision/session. Trace actual case IDs and effects,
   not just recipe names. Criterion warmup, statistical repetitions, untimed
   preflight, distinct baseline/current phases, and justified repeat trials are
   intentional. Repeated jobs, overlapping filters, reconstruction for read-only
   consumers, or sampling again for a report are not. Preserve required exact
   release measurements and scientific coverage; record why a rerun is necessary.
5. **Validate evidence.** Before accepting reuse or comparisons, apply the
   [evidence contract](references/evidence-contract.md). Check the independent
   plan against discovered and observed cases, raw completeness, source/harness
   identity, and environment. Reject incompatible evidence. If methodology
   changes, regenerate affected measurements when authorized, including during
   release preparation; preserve old evidence under its original identity.
6. **Verify the change and report its limits.** Use the smallest relevant
   repository checks and required final gates. Validate command composition and
   report-only behavior without collecting samples when mocks suffice. Report
   the ownership trace, corrected or proposed behavior, correctness evidence,
   evidence accepted/rejected and why, actions actually run, and remaining
   coverage or comparability limits. Claim a speedup only from valid measurements
   with appropriate uncertainty; fewer invocations alone establish no speedup.

Read [verified repository examples](references/repository-examples.md) only for
Delaunay, la-stack, or a cross-repository design comparison. Recheck their source
revisions before applying them. When maintaining this skill, use the
[validation scenarios](references/validation-scenarios.md).

## Coordination and implementation ownership

- [project-tooling-review](../project-tooling-review/SKILL.md) owns command/CI
  wiring, trigger/cache policy, tool pins, and static tooling checks. This skill
  owns measurement ownership, workload classification, and evidence design.
- [rust-invariant-performance](../rust-invariant-performance/SKILL.md) owns Rust
  hot-path optimization, cost analysis, and measured improvement/regression
  interpretation. Use this skill when the harness or orchestration contract is
  the concern, without reopening unrelated implementation review.
- [rust-scientific-correctness](../rust-scientific-correctness/SKILL.md) owns
  mathematical validity, independent oracles, and equivalence of scientific work.
  Invalid work blocks performance conclusions even if timing is repeatable.
- `research-repo-tools` owns reusable execution, discovery, evidence validation,
  retention, and publication mechanics. Consumers own scientific workload
  declarations, native correctness gates, and command documentation. Inspect the
  installed public interfaces and inherited pins; do not copy its engine into a
  consumer, invent independent tool versions, or assume an unpublished upstream
  change is available. Report a bounded upstream gap when necessary.

These are ownership boundaries, not instructions to load every skill or launch
an exhaustive review. Under a parent dispatch, honor its scope and permissions;
return additional needs to that coordinator.
