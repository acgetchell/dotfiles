# Standalone Test Validation

Read this reference only when `rust-test-quality` is invoked directly and no
parent dispatch supplies a validation ledger or result contract. Review-graph
and Rust-orchestrator execution own validation scheduling and reporting.

## Validation Ledger

Key evidence by source state, built artifact, toolchain, target, feature set,
profile, instrumentation, and exact test selection. Before executing a
repository recipe or Cargo command, inspect what it selects, decide whether
repository policy requires an indivisible full gate, and reuse still-valid
evidence.

Choose the smallest single selection that proves the touched risk: a named
test, doctest, property replay, fuzz regression, compile-fail target, model
check, affected package, or feature tier. Do not run that selection and then
its containing target, package, workspace, and full CI as successive tiers. If
a broader gate is independently required, select it initially or run only the
portion not already recorded as passing.

If an indivisible policy gate is discovered only after overlapping tests pass
and offers no reliable exclusion, report the conflict and route command-surface
ownership to `project-tooling-review`. Do not silently replay tests or count
duplicate execution as new evidence.

Rerun only after relevant source, fixture, build, or configuration changes
invalidate the result, or when diagnosing nondeterminism. Different
toolchains, targets, features, Miri or sanitizer modes, and material runtime
configurations are distinct evidence. Repeated property, fuzz, concurrency, or
benchmark samples are distinct only when repetition is part of the stated test
design; record the seed, schedule, or sample purpose.

## Standalone Handoff

Summarize risks and tests inspected, strengthened evidence, independent
oracles, seeds or counterexamples, compile and configuration contracts,
non-overlapping validation results, remaining gaps, files changed, and whether
Git state remained untouched.
