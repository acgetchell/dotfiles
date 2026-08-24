# Standalone Python Test Review Workflow

Read this reference only when `python-test-quality` is invoked directly without
an exact parent scope, validation ledger, and result contract. Review-graph and
Python-orchestrator dispatches already own this information.

## Scope Modes

Use changed-code mode by default and whole-repository mode only when requested.

## Validation

Maintain a ledger keyed by source and environment state, built artifact, Python
version, platform, dependency/configuration set, instrumentation, and exact
test selection. Inspect repository recipes before execution, decide whether
policy or scope requires an indivisible full gate, and reuse valid evidence.

Choose the smallest single selection proving the touched risk. Do not run a
named case followed by its class, module, suite, and full CI as successive
tiers. If a broader validator is independently required, choose it initially
or run only its uncovered portion.

If a mandatory indivisible gate is discovered only after overlapping tests
passed and offers no reliable exclusion, report the command-surface conflict
to `project-tooling-review`; do not replay tests or count duplicate execution
as new evidence.

Rerun only after relevant source, fixture, dependency, environment, or
configuration changes invalidate a result, or to diagnose nondeterminism. A
different Python version, platform, optional dependency, subprocess
environment, async backend, or instrumentation mode is distinct evidence.
Repeated Hypothesis, stochastic, concurrency, or benchmark samples are
distinct only when repetition is part of the test design; record the seed or
purpose.

## Standalone Report

Classify the result as `PASS`, `NEEDS IMPROVEMENT`, or `FAIL`. Order findings
by behavioral risk. Identify the unproven contract, why current evidence can
pass incorrectly, and a concrete Given/When/Then scenario or property. Report
the non-overlapping ledger, seeds or counterexamples, skipped environments,
justified reruns, independent reproduction, and other limitations.
