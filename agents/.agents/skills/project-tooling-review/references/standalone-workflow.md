# Standalone Project Tooling Workflow

Read this reference completely only for a direct tooling review outside
`review-graph`. The main skill owns surface routing and tooling correctness.

## Scope Discovery

Use read-only git commands to discover scope when needed. Prefer changed-file
review by default and whole-repository baseline mode only when explicitly
requested. Honor a supplied parent scope rather than rediscovering a narrower
staged or worktree-only surface.

## Review Trace

When a caller supplies an established scope, begin with a handoff receipt
naming the branch scope and tooling-owned files, selected tooling surfaces and
reasons, meaningful skips, and references to load.

Keep each loaded reference in the running trace. Group evidence by tooling
surface. A surface is complete only when the final summary names its status,
references, files or command owners inspected, findings or explicit no-finding
result, fixes, and focused validator. A broad validator alone does not prove
that every tooling surface was reviewed.

For a parent handoff, provide table-ready `Review Evidence` naming selected
surfaces, references, validators, version checks, and meaningful skips.

## Fix Loop

For each applicable tooling surface:

1. Read the relevant reference.
2. Inspect scoped files and nearby command owners.
3. Record findings or an explicit no-finding result.
4. Apply minimal fixes only when authorized; otherwise record remediation.
5. Run the focused validator when available.
6. Fix failures and rerun that validator before moving on.
7. Record changed files, commands, and the surface outcome.

Do not blend recipes, workflow wiring, documentation, and version surfaces into
one undifferentiated pass. If validation needs network, installation, or other
approval, use the strongest read-only local check and report the remaining gap.

## Final Summary

Lead with unresolved tooling risks. Then report files changed and why, surfaces
reviewed, references loaded, parent-handoff evidence, validators and results,
the actual platform for each native or emulated check, unexecuted matrix cells,
live or local-only version checks, managed tool updates and before/after
versions, pins reconciled, language-orchestrator handoffs, deferred work, and
git-state status. Reconcile any available native CI result for the reviewed
source state instead of presenting a narrower local pass as matrix coverage.
