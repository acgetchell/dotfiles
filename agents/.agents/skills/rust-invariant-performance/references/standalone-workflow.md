# Standalone Invariant Performance Workflow

Read this reference only when `rust-invariant-performance` is invoked directly
without an exact parent scope and result contract. Review-graph and
Rust-orchestrator dispatches already own scope and reporting.

## Scope Modes

In default mode, review newly added or modified Rust code and nearby hot-path
context. Ignore unrelated unchanged code unless it defines the invariant,
benchmark, or performance contract the change relies on.

For a pull request or branch review, examine changed hot paths first, then the
adjacent invariant boundaries and benchmarks needed to evaluate the change.

Use whole-repository baseline mode only when explicitly requested. Audit public
hot paths, core algorithms, allocation-heavy loops, validation layers,
construction, sampling and repair paths, and benchmarks. Produce a prioritized
performance plan; do not require every historical issue to be fixed in one
patch.

## Standalone Report

State the scope and likely hot paths, then classify the result as `PASS`,
`NEEDS IMPROVEMENT`, or `FAIL`. Report:

- correctness-preserving wins
- hot-path allocation, cloning, formatting, boxing, or data-movement issues
- complexity, repeated-work, missing-budget, and stale-cache risks
- invariant, typed-error, public-semantics, and safety risks
- benchmark gaps and the commands and measurements needed to close them
- representative before/after evidence for implemented performance work, or an
  explicit statement that no adequate benchmark or smoke proxy exists
- cold paths not worth optimizing and contracts that must not change for speed
