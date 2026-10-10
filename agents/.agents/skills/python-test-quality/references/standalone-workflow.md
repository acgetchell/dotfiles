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
Record the actual executor platform separately from any target platform and
classify each result as native execution or focused emulation. An unexecuted
target cell remains a gap even when its workflow is configured or its boundary
has been modeled elsewhere.

Avoid a ladder of overlapping test tiers solely for reassurance. Run focused
red/green checks when useful during a fix, then any required final aggregate gate
on the final source state even if it repeats those checks. Record the reason for
overlap without counting it as independent evidence. Reuse valid evidence where
the required validation contract permits it; overlap alone requires no approval
or command-surface escalation.

Beyond required final gates, rerun only after relevant source, fixture, dependency, environment, or
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
justified reruns, independent reproduction, native versus emulated platform
evidence, unexecuted matrix cells, and other limitations.
