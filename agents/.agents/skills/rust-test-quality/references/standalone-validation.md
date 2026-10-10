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

Avoid a ladder of overlapping test tiers solely for reassurance. Run focused
red/green checks when useful during a fix, then any required final aggregate gate
on the final source state even if it repeats those checks. Record the reason for
overlap without counting it as independent evidence. Reuse valid evidence where
the required validation contract permits it; overlap alone requires no approval
or command-surface escalation.

Beyond required final gates, rerun only after relevant source, fixture, build, or configuration changes
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
