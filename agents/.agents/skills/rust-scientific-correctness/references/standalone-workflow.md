# Standalone Scientific Review Workflow

Read this reference only when `rust-scientific-correctness` is invoked directly
without an exact parent scope and result contract. Review-graph and
Rust-orchestrator dispatches already own scope and reporting.

## Scope Modes

Use changed-file review by default. Use whole-repository baseline mode only
when the user explicitly requests a whole-repository audit.

For review-only requests, report findings without editing. When the user asks
to fix findings, load the fix workflow, make the smallest scientifically
correct change, add independent evidence, and validate the affected regimes.

## Standalone Report

Classify the overall result as `PASS`, `NEEDS IMPROVEMENT`, or `FAIL`. Present
findings in priority order using the scientific evidence requirements in the
main skill, and state whether the review was read-only or changed files.
