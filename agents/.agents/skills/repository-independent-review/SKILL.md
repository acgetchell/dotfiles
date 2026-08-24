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

Return exactly `# Repository Independent Review` followed by these six level-2
sections, in order, with no preamble or machine-authored identifiers:

- `## Scope Inspected`: exactly one each of `Change target`, `Files`,
  `Branches`, `Boundary cases`, and `Tests`; paths and target match the dispatch
- `## Findings`: `No findings.` for a no-findings result; otherwise ordered
  `- Finding:` records with `Severity`, `Location`, `Summary`, `Evidence`,
  `Impact`, `Owner`, and `Remediation`
- `## No-Finding Evidence`: one `- Inspected:` record for every dispatched
  adversarial check and every material contract supporting a no-findings claim
- `## Routing Handoffs`: exact `none` or ordered `- Catalog ID:` records with
  `Observed trigger`, `Reason`, and comma-separated repository `Scope`
- `## Fingerprint Proof`: expected, before, and after identities
- `## Git State`: confirmation that no source or Git mutation occurred

The coordinator runs `compile-independent-review`. That compiler assigns
finding, handoff, evidence, and artifact identities; appends the canonical
review-graph envelope and Machine Evidence block; and verifies the result before
journaling. Do not append either compiler-owned section yourself.

A no-findings result is inspection evidence, not a categorical claim derived
from a fixed example or denylist. Exercise the dispatched fallback, platform,
parser, error-branch, unexpected-exception, and test-boundary checks whenever
they are present.

Do not include a finding merely to make the result non-empty.
