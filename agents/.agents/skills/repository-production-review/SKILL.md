---
name: repository-production-review
description: "Synthesize accepted isolated repository-review reports, exhaustive routing evidence, validation mappings, source-state fingerprints, and cross-surface disagreements into one production-readiness result. Use only as the final repository-level synthesis node of review-graph; do not use it for primary source review or standalone specialist analysis."
---

# Repository Production Review

Act only as a fresh synthesis worker for `review-graph`. Reconcile supplied
accepted evidence without capturing scope, selecting skills, creating workers,
running validators, editing files, or repeating specialist analysis.

## Inputs

Require:

- captured scope, worktree, and repository-state fingerprints
- exhaustive repository and surface routing ledgers
- every accepted leaf, independent-review, validation, and language-synthesis
  report with stable IDs
- requirement-to-node and validation-reuse mappings
- explicit user exclusions, exact evidence reuse, and remaining blockers

Return a blocked result when an input is missing, stale, malformed, or refers to
an unresolved applicability handoff. Never infer that omitted work passed.

## Reconciliation

1. Map every selected requirement to one accepted report or exact verified
   reuse record.
2. Verify that every consulted routing catalog is exhaustive and no
   completion-blocking disposition remains.
3. Preserve raw disagreements. Deduplicate only findings with the same cause,
   affected contract, evidence, and required action.
4. Assign each canonical finding one owner and one final disposition: `fixed`,
   `remaining`, `accepted-risk`, or `blocked`.
5. Treat validator failures as evidence until an owning reviewer diagnoses
   them; do not manufacture findings from command output.
6. Require accepted independent review for a concrete change target.
7. Classify production readiness only after all required evidence and
   fingerprints reconcile.

## Result Contract

Return:

- `Predecessor Coverage`: every requirement, node/report, and disposition
- `Routing Closure`: consulted routers, exhaustive-ledger status, exclusions,
  reuse, and unresolved handoffs
- `Canonical Findings`: severity, owner, evidence, duplicates, and disposition
- `Validation Reconciliation`: each requirement and its accepted validator or
  exact reuse evidence
- `Cross-Surface Risks`: conflicts, shared-file ownership, and residual gaps
- `Repository Verdict`: `ready`, `not-ready`, or `blocked`, with exact reasons

Do not create subagents or recursively invoke `review-graph`.
