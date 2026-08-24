---
name: docs-review-orchestrator
description: "Coordinate multi-pass documentation reviews by selecting individual specialists for active repository docs, scientific software claims, Rust crate release metadata, C++ and Rust API docs, citations, and academic authorship boundaries. Use for branch, staged, release-readiness, or repository-wide documentation work spanning more than one documentation concern. Use a focused documentation skill directly for a single concern."
---

# Documentation Review Orchestrator

Coordinate a domain-neutral documentation review with the smallest applicable specialist set. Preserve each source owner's evidence and reconcile shared files only after the relevant reviewers establish technical truth.

## Ground Rules

- Do not mutate git state unless explicitly requested in the current turn.
- Read repository-local guidance and honor any supplied parent scope without
  narrowing it silently outside graph-routing mode.
- Preserve generated-file ownership and authoritative source data.
- Select scientific, citation, API, and academic skills from actual content, not repository labels.

## Graph-Routing Mode

When `review-graph` requests a declarative handoff, read
[`review-graph/references/routing-handoff.md`](../review-graph/references/routing-handoff.md)
and return its records instead of running this skill's standalone pass loop.
Return sparse semantic overrides only for selected, reused, excluded, or
blocked candidates. The planner derives catalog identity and expands omitted
candidates to `not-applicable`. Mark required documentation or citation
coverage and attach exact validators and static truth-owner references only to
selected records. Do not load specialist bodies, validate, synthesize, edit,
create subagents, or recursively invoke an orchestrator in graph-routing mode.

For a directly requested documentation orchestration outside graph-routing
mode, read
[`references/standalone-workflow.md`](references/standalone-workflow.md)
completely and follow its routing, trace, pass, validation, and reporting
workflow.
