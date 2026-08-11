---
name: repo-review
description: "Coordinate complete read-only or explicitly requested review-and-fix work across C++, Rust, Python, project tooling, and documentation. Use for branch, PR, staged, release-readiness, whole-repository baseline, fix-all, or review-and-fix requests spanning multiple surfaces. Run the grouped surface-orchestrator workflow by default so the user receives findings; use review-graph's isolated profile only when explicitly requested. Also provide repository-layer graph-routing records for isolated review-graph execution."
---

# Repo Review

Deliver a mixed-surface repository review through the supported grouped profile.
Use a focused skill directly for a single narrow surface.

## Graph-Routing Mode

When `review-graph` explicitly requests `graph-routing`:

1. Read [check routing](references/check-routing.md), then read
   [`review-graph` routing handoff](../review-graph/references/routing-handoff.md).
2. Use the repository entries in
   [`routing-catalog.json`](../review-graph/references/routing-catalog.json) and
   the planner's conservative repository classifier.
3. Return one decision for every repository catalog entry, including tooling,
   C++, Rust, Python, documentation, independent review, and repository
   synthesis.
4. Expand skill paths exactly and cite catalog rules, observed contracts,
   owners, and reasons for every disposition.
5. Select every classifier-signaled surface unless concrete semantic evidence
   resolves the conflict. Preserve every shared owner.
6. Select `repository-independent-review` for concrete change targets and
   `repository-production-review` for final synthesis.

Return records only. Do not load surface orchestrator or leaf bodies, create
subagents, review, validate, edit, or synthesize in graph-routing mode.

## Default Grouped Review

1. Read [check routing](references/check-routing.md) and
   [grouped review](references/legacy-grouped-review.md) completely.
2. Establish branch scope by default, including committed branch changes plus
   staged, unstaged, and untracked work. Honor explicit staged-only,
   changed-file-only, whole-repository baseline, or release-readiness scope.
3. Select and run the applicable surface orchestrators sequentially. Read each
   selected orchestrator's complete `SKILL.md`, give it the established scope,
   and let it run its grouped specialist sequence and focused validation.
4. Maintain one repository-wide validation ledger and resolve cross-surface
   handoffs before final reporting.
5. Apply fixes only when explicitly authorized, then rerun affected reviews and
   validation.

Do not load `review-graph` or inspect worker capacity for an ordinary grouped
review. Unavailable subagents are not a blocker.

## Explicit Isolated Review

When the user explicitly requests `isolated`, `isolated-graph`, or
`isolated-only`, read the complete [`review-graph` skill](../review-graph/SKILL.md)
and follow its matching profile. An isolation preference may fall back to
grouped delivery; an isolated-only request may not.

## Compatibility Report

Lead with findings and unresolved blockers. Include:

| Orchestrator | Status | Why selected or skipped | Scope handed off | Skills/references actually loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include exactly one row for `project-tooling-review`,
`cpp-review-orchestrator`, `rust-review-orchestrator`,
`python-review-orchestrator`, and `docs-review-orchestrator`. Also include
changed files, validation, unresolved risks, final repository state, and
confirmation of Git-state mutation or non-mutation.
