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

Return `compact-independent-review` JSON matching
`dispatch.payload_schema`; start from its linked blocked template. Record
`files_inspected`, branches, boundary cases, tests, findings, handoffs, observed
`before_state`/`after_state`, and truthful command/mutation attestations. For each
`dispatch.adversarial_check_ids` entry, supply `{check_id, evidence, inspected_paths}`
with substantive observations. Stable IDs are `fallback`, `platform`,
`parser-errors`, `unexpected-exceptions`, and `test-boundaries`; only dispatched
checks are required. Do not invent checks or observations.

Record test inspection, delegated or unexecuted validator commands, and pending
hosted/platform checks in `tests`. Record inspected source branches and
source-level platform observations in `branches` or the `platform` adversarial
check. List only commands actually run in `commands_executed`. Pending validation
does not imply passed checks or incomplete source inspection.

Reserve `limitations` for incomplete owned inspection, unresolved semantic
uncertainty, and unclassified caveats; these require `status: blocked`. Do not
move those blockers into `tests` or `branches`. When inspection is complete,
use `limitations: []` with `completed` if there are findings, or `no-findings`
otherwise. The digest-bound `dispatch.payload_schema.completed_example` shows
delegated validation and pending hosted checks in a schema-valid completed
payload. Its observations are illustrative; replace them with actual evidence.

Publish once through the dispatch's `publish_command` and return its receipt.
The compiler validates substantive evidence fields before publication, renders
the native headings/labels, and retains the canonical payload and exact bytes.
It cannot establish semantic correctness merely from nonblank evidence.

A no-findings result is inspection evidence, not a categorical claim derived
from a fixed example or denylist. Exercise the dispatched fallback, platform,
parser, error-branch, unexpected-exception, and test-boundary checks whenever
they are present.

Do not include a finding merely to make the result non-empty.
