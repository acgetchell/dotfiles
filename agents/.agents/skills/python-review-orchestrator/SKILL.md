---
name: python-review-orchestrator
description: "Coordinate Python reviews spanning multiple contracts; use a focused skill for a single review concern."
---

# Python Review Orchestrator

Coordinate focused Python skills without copying their guidance. Select each skill independently from the changed behavior; selecting a pass does not imply loading every skill listed in that pass.

## Ground Rules

Existing user authorization remains valid for the same operation and scope
across turns. A review is read-only; requested fixes include relevant local
edits and safe checks, but do not imply Git mutations or publication.

- Do not mutate git state unless the user has explicitly authorized that operation and scope.
- Respect repository-local instructions before inspecting or editing files.
- Honor an exact parent scope instead of narrowing it silently.

## Graph-Routing Mode

When `review-graph` requests a declarative handoff, read
[`review-graph/references/routing-handoff.md`](../review-graph/references/routing-handoff.md)
and return its records instead of running this skill's standalone pass loop.
Return semantic decisions for every matched specialist, including justified
`not-applicable` decisions, and additions beyond path matches. The planner rejects
unassessed matches, expands unmatched omissions, and selects mandatory synthesis. Preserve the
build-portability requirement for package mode, build metadata, installed
modules, or entry points, and attach exact validation requirements only to
selected records. Do not load specialist bodies, validate, synthesize, edit,
create subagents, or recursively invoke an orchestrator in graph-routing mode.

For a directly requested Python orchestration outside graph-routing mode, read
[`references/standalone-workflow.md`](references/standalone-workflow.md)
completely and follow its scope, routing, trace, validation, and reporting
workflow.
