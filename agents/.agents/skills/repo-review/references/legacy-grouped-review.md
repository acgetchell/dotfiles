# Grouped Repository Review

Use this workflow for ordinary `repo-review` and `review-graph` requests. The
filename is retained for compatibility; this is the supported delivery-first
profile, not a fallback.

## Scope

Read `check-routing.md`. Default to branch scope against the explicit or
inferred default-branch base and include committed branch changes plus staged,
unstaged, and untracked work. Honor explicit staged-only or changed-file-only
scope. For a whole-repository baseline, inventory tracked files even when the
worktree is clean. For release readiness, expand documentation to every tracked
active document outside designated archives.

Do not mutate Git state unless explicitly requested. Apply fixes only when the
user authorized review-and-fix behavior.

## Dispatch

Select the smallest applicable set from:

1. `project-tooling-review`
2. `cpp-review-orchestrator`
3. `rust-review-orchestrator`
4. `python-review-orchestrator`
5. `docs-review-orchestrator`

Route shared files to every owner described by `check-routing.md`. Run tooling
first when recipes, workflows, pins, or command docs can change validator
meaning. Run documentation after source truth owners.

Before each grouped pass, read its complete `SKILL.md`, hand it the established
scope, and let it run its own specialist sequence, fix loop, and focused
validation. Do not flatten selected orchestrators into one blended pass.

Maintain one validation ledger keyed by source/build/environment state,
configuration, artifact, and exact test selection. Reuse valid evidence and do
not replay nested validator tiers merely to produce a broader summary.

## Evidence

Record selected and skipped orchestrators, exact scope, skills/references
loaded, findings, fixes, validators, unresolved handoffs, and Git-state status.
Return:

| Orchestrator | Status | Why selected or skipped | Scope handed off | Skills/references actually loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include one row for all five orchestrators. Use `selected`, `skipped`, or
`blocked`. Lead with unresolved blockers and label the result `grouped`; it is
not isolated graph evidence.
