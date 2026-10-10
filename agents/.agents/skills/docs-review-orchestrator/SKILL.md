---
name: docs-review-orchestrator
description: "Coordinate documentation reviews spanning multiple concerns; use a focused documentation skill for one concern."
---

# Documentation Review Orchestrator

Coordinate a domain-neutral documentation review with the smallest applicable specialist set. Preserve each source owner's evidence and reconcile shared files only after the relevant reviewers establish technical truth.

## Ground Rules

Existing user authorization remains valid for the same operation and scope
across turns. A review is read-only; requested fixes include relevant local
edits and safe checks, but do not imply Git mutations or publication.

- Do not mutate git state unless explicitly authorized for that operation and scope.
- Read repository-local guidance and honor any supplied parent scope without
  narrowing it silently outside graph-routing mode.
- Preserve generated-file ownership and authoritative source data.
- Select scientific, citation, API, and academic skills from actual content, not repository labels.

## Graph-Routing Mode

When `review-graph` requests a declarative handoff, read
[`review-graph/references/routing-handoff.md`](../review-graph/references/routing-handoff.md)
and return its records instead of running this skill's standalone pass loop.
Assess every matched specialist explicitly, including justified
`not-applicable` decisions, and semantic additions beyond path matches. The planner
rejects unassessed matches and expands only unmatched omissions. Mark required documentation or citation
coverage and attach exact validators and static truth-owner references only to
selected records. Do not load specialist bodies, validate, synthesize, edit,
create subagents, or recursively invoke an orchestrator in graph-routing mode.

For a directly requested documentation orchestration outside graph-routing
mode, read
[`references/standalone-workflow.md`](references/standalone-workflow.md)
completely and follow its routing, trace, pass, validation, and reporting
workflow.
