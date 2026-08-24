# Standalone Error Review Workflow

Read this reference only when `rust-error-variants` is invoked directly without
an exact parent scope and result contract. A review-graph or Rust-orchestrator
dispatch already owns this information.

## Scope Modes

In default mode, audit newly added or modified error types, fallible paths, and
error conversions. Ignore unrelated unchanged errors unless they define the
convention the changed code should follow.

Use whole-repository baseline mode only when the user explicitly requests a
whole-repository or baseline audit. Cover public error types, fallible public
APIs, validation paths, backend or library mappings, and common internal
conversion boundaries. Prioritize caller-visible ambiguity, lost typed
context, misleading variants, missing `#[non_exhaustive]`, and tests unable to
assert structured errors. Separate API-breaking fixes from internal cleanup;
do not require every historical issue to be fixed in one pass.

## Standalone Report

Classify the result as `PASS`, `NEEDS IMPROVEMENT`, or `FAIL`. Report:

- concrete findings with file and function references
- the current error path and the more accurate variant or conversion
- required new or reused variants, conversion changes, diagnostic improvements,
  and tests
- optional naming, field, or message refinements
