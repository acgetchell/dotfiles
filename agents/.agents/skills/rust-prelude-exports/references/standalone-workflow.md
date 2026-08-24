# Standalone Prelude Export Workflow

Read this reference only when `rust-prelude-exports` is invoked directly
without an exact parent scope and result contract. Review-graph and
Rust-orchestrator dispatches already own scope and reporting.

## Scope Modes

In default mode, audit newly added or modified public APIs, preludes, `pub use`
exports, and downstream-style imports. Ignore unrelated unchanged exports
unless they define the boundary the changed API should follow.

Use whole-repository baseline mode only when explicitly requested. Audit the
complete public export surface, all prelude modules, doctest imports,
integration tests, examples, and benchmark imports. Prioritize accidental API
stabilization, bloated or overlapping preludes, missing ergonomic exports for
common workflows, and examples that require internal paths. Separate breaking
cleanup from additive ergonomic fixes; do not require every historical export
nit to be fixed in one pass.

## Standalone Report

Classify the result as `PASS`, `NEEDS IMPROVEMENT`, or `FAIL`. Report:

- concrete issues with file or module references and whether each is a missing
  export, excessive export, overlap, unclear scope, or downstream-usability
  problem
- required exports, removals, scoped-prelude moves, visibility tightenings,
  doctest/example/benchmark updates, and usage documentation
- optional non-blocking organization, naming, or documentation improvements
