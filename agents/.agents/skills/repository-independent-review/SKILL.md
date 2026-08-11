---
name: repository-independent-review
description: "Independently inspect a concrete repository change without receiving specialist conclusions, expected findings, or validator diagnoses. Use as review-graph's required independent change-review leaf for branch, staged, pull-request, or review-and-fix scopes with a concrete diff; do not use for whole-repository baselines without a change target."
---

# Repository Independent Review

Review only the supplied concrete change in a fresh no-inherited-turn worker.
Do not receive or request specialist reports, expected findings, synthesis, or
validator conclusions. Do not create subagents or invoke another review skill.

## Inputs And Integrity

Require the exact change target, path boundary, repository instructions,
captured scope/worktree/repository-state fingerprints, and state-verification
command. Return blocked when these inputs are missing or mismatched.

Recheck fingerprints before and after inspection. Keep the worktree, index, and
Git state unchanged.

## Review

Inspect the diff, complete contents of changed and untracked files, and the
minimum neighboring code needed to establish contracts. Prioritize behavioral
correctness, security, data loss, public compatibility, cross-file integration,
and missing durable tests. Avoid style-only findings unless they hide a defect.

Do not run broad validation or treat command failures as findings. Record a
handoff to the owning catalog skill when specialist diagnosis is required.

## Result Contract

Return:

- `Scope Inspected`: exact paths and change identity
- `Findings`: severity, file and tight line range, evidence, impact, and owner
- `No-Finding Evidence`: inspected contracts when no actionable finding exists
- `Routing Handoffs`: catalog candidate, observed trigger, and affected surface
- `Fingerprint Proof`: expected, before, and after identities
- `Git State`: confirmation that no mutation occurred

Do not include a finding merely to make the result non-empty.
