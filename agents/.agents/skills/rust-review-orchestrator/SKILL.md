---
name: rust-review-orchestrator
description: "Coordinate Rust reviews spanning multiple contracts; use a focused skill for a single review concern."
---

# Rust Review Orchestrator

Coordinate focused Rust review skills without copying their content. Select skills individually, run them in logical groups, validate each affected contract, and finish with lean production synthesis.

Do not treat selecting a group as permission to load every skill listed in it. Load only skills whose trigger matches the scoped change and record explicit skips when a maintainer could reasonably expect a pass.

## Ground Rules

Existing user authorization remains valid for the same operation and scope
across turns. A review is read-only; requested fixes include relevant local
edits and safe checks, but do not imply Git mutations or publication.

- Do not stage, commit, push, tag, checkout, reset, or stash unless explicitly authorized for that operation and scope.
- Use read-only git commands to discover scope.
- Respect repository-local instructions and documented MSRV, edition, feature, target, safety, and validation policy.
- Prefer changed-file review. Use whole-repository baseline mode only when explicitly requested.
- Outside graph-routing mode, honor any parent file list or diff instead of
  rediscovering a narrower scope.
- When fixes are requested, implement verified findings within each selected skill before continuing.
- Select focused validators; do not run full CI merely because orchestration is ending.
- Maintain one cross-skill validation ledger keyed by source/build state,
  toolchain, target, features, instrumentation, and exact test selection. Reuse
  still-valid evidence instead of replaying it through broader recipes.

## Graph-Routing Mode

When `review-graph` requests a declarative handoff, read
[`review-graph/references/routing-handoff.md`](../review-graph/references/routing-handoff.md)
and return its records instead of running this skill's standalone pass loop.
Return semantic decisions for every matched specialist, including justified
`not-applicable` decisions, and additions beyond path matches. The planner rejects
unassessed matches, expands unmatched omissions, and selects mandatory synthesis. Attach
applicable static guidance such as `references/la-stack.md` and exact validation
requirements only to selected records. Do not load specialist bodies, validate,
synthesize, edit, create subagents, or recursively invoke an orchestrator in
graph-routing mode.

Otherwise read [standalone orchestration](references/standalone-orchestration.md)
for scope routing, applicable language guidance, pass receipts, and final synthesis.
