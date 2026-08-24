---
name: python-review-orchestrator
description: "Coordinate multi-pass Python reviews by selecting individual specialists for packaging and portability, notebooks, CLI behavior, boundary parsing, scientific code, support tooling, tests, and production integration. Use for changed, staged, branch, PR, release-readiness, repository-wide, or fix-all Python work spanning multiple concerns. Use a focused Python skill directly for a single concern."
---

# Python Review Orchestrator

Coordinate focused Python skills without copying their guidance. Select each skill independently from the changed behavior; selecting a pass does not imply loading every skill listed in that pass.

## Ground Rules

- Do not mutate git state unless the user explicitly requests it in the current turn.
- Respect repository-local instructions before inspecting or editing files.
- Honor an exact parent scope instead of narrowing it silently.

## Graph-Routing Mode

When `review-graph` requests a declarative handoff, read
[`review-graph/references/routing-handoff.md`](../review-graph/references/routing-handoff.md)
and return its records instead of running this skill's standalone pass loop.
Return sparse semantic overrides only for selected, reused, excluded, or
blocked candidates. The planner derives catalog identity, expands omitted
candidates to `not-applicable`, and selects mandatory synthesis. Preserve the
build-portability requirement for package mode, build metadata, installed
modules, or entry points, and attach exact validation requirements only to
selected records. Do not load specialist bodies, validate, synthesize, edit,
create subagents, or recursively invoke an orchestrator in graph-routing mode.

For a directly requested Python orchestration outside graph-routing mode, read
[`references/standalone-workflow.md`](references/standalone-workflow.md)
completely and follow its scope, routing, trace, validation, and reporting
workflow.
