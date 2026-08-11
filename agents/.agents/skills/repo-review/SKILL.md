---
name: repo-review
description: "Provide the compatibility entry point for complete mixed C++/Rust/Python/tooling/documentation repository review by delegating branch, PR, staged, release-readiness, whole-repository baseline, fix-all, and review-and-fix requests to review-graph. Also act as review-graph's exhaustive repository-layer routing authority. Use a focused skill directly for a single narrow surface; use legacy-grouped only when explicitly requested."
---

# Repo Review

Use `review-graph` as the default execution engine for mixed repository review.
Preserve this skill as a compatibility entry point and repository-layer router;
do not run grouped reviewers in this context unless the user explicitly asks
for `legacy-grouped`.

## Graph-Routing Mode

When `review-graph` explicitly requests `graph-routing`:

1. Read [check routing](references/check-routing.md), then read
   [`review-graph` routing handoff](../review-graph/references/routing-handoff.md).
2. Use the repository entries in
   [`routing-catalog.json`](../review-graph/references/routing-catalog.json) and
   the planner's conservative repository path classifier.
3. Return one decision for every `repo-review` catalog entry: tooling, C++,
   Rust, Python, documentation, independent review, and repository synthesis.
4. Expand `$SKILLS_ROOT` catalog paths to exact absolute paths. Cite the exact
   catalog rule, observed paths/contracts, owners, and reason for every selected
   or non-applicable decision.
5. Select every classifier-signaled surface unless concrete semantic evidence
   resolves why it is not affected. Add semantic owners that deterministic path
   classification cannot prove.
6. Select `repository-independent-review` for concrete branch, staged, PR,
   changed-file, or fix targets. Mark it not applicable only for a pure baseline
   without a concrete diff.
7. Always select `repository-production-review` for final broad synthesis.

Return records only. Do not load surface orchestrator or leaf bodies, create
subagents, review, validate, edit, synthesize, or delegate to `review-graph` in
graph-routing mode.

## Default Graph Wrapper

For ordinary mixed repository review:

1. Read [check routing](references/check-routing.md) to normalize the requested
   scope without performing specialist selection.
2. Preserve these compatibility semantics:
   - default branch scope uses the explicit PR/base or inferred default branch
     and includes committed, staged, unstaged, and untracked work
   - staged-only and changed-file-only require explicit requests
   - whole-repository baseline inventories tracked files even when clean
   - release readiness expands the active documentation suite outside archives
   - shared files retain every tooling, language, and documentation owner
   - review-and-fix authorization is explicit and requires post-fix rerouting
3. Read the complete [`review-graph` skill](../review-graph/SKILL.md), announce
   that it is the execution engine, and follow it with the normalized scope.
4. Do not silently fall back when graph capability, a worker, routing,
   validation, or synthesis is blocked. Return the graph's resumable incomplete
   result.
5. Derive the compatibility `Review Evidence` table from graph records.

For a single narrow surface, route directly to its focused skill instead of
building a mixed graph.

## Explicit Legacy Mode

Use [legacy grouped review](references/legacy-grouped-review.md) only when the
user explicitly says `legacy-grouped`, requests the former same-context path,
or asks to compare it with the graph. Label its result clearly. Never represent
legacy evidence as isolated worker evidence and never switch to it after a
graph failure without a new explicit request.

## Compatibility Report

The final result must include:

| Orchestrator | Status | Why selected or skipped | Scope handed off | Skills/references actually loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include exactly one row for `project-tooling-review`,
`cpp-review-orchestrator`, `rust-review-orchestrator`,
`python-review-orchestrator`, and `docs-review-orchestrator`. In graph mode,
distinguish consulted routers from skills actually executed. Also include graph
completion, epochs/resume state, exact routing dispositions, changed files,
validation, unresolved risks, final repository state, and confirmation of Git
state mutation or non-mutation.
