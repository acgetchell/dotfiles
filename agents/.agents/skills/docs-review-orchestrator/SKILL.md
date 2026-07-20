---
name: docs-review-orchestrator
description: "Coordinate multi-pass documentation reviews by selecting individual specialists for active repository docs, scientific software claims, Rust crate release metadata, C++ and Rust API docs, citations, and academic authorship boundaries. Use for branch, staged, release-readiness, or repository-wide documentation work spanning more than one documentation concern. Use a focused documentation skill directly for a single concern."
---

# Documentation Review Orchestrator

Coordinate a domain-neutral documentation review with the smallest applicable specialist set. Preserve each source owner's evidence and reconcile shared files only after the relevant reviewers establish technical truth.

## Ground Rules

- Do not mutate git state unless explicitly requested in the current turn.
- Read repository-local guidance and honor a parent `repo-review` scope without narrowing it silently.
- Default to branch scope. Use staged-only, changed-file-only, release-readiness, or whole-repository scope when explicitly requested or handed off.
- Treat an explicit release-readiness or release documentation audit as release-readiness. A request to review a named release patch, diff, or changed-file set remains bounded to that supplied surface unless the user asks to expand it.
- In release-readiness or whole-suite mode, inspect every tracked active document and classify generated, template, archived, or excluded material.
- Preserve generated-file ownership and authoritative source data.
- Select scientific, citation, API, and academic skills from actual content, not repository labels.

## Establish Scope And Routing

1. Inspect the supplied scope or use read-only git discovery.
2. Read [`references/check-routing.md`](references/check-routing.md).
3. Select individual skills from the documented surface and claims.
4. State selected and meaningfully skipped skills before loading their bodies.
5. Load repository-specific references only when both repository and concern match.

## Review Trace

For each selected skill, record why it applies, exact scope handed off, skill and references loaded, findings or explicit no-finding result, fixes, and validators.

Also record each external language, scientific-correctness, build, or tooling truth owner actually consulted: the disputed claim, evidence reused or requested, and status. Do not load external specialists merely to populate this record.

For a broad or parent-orchestrated review, return a `Documentation Review Evidence` table with one row for each:

- `repository-docs-review`
- `scientific-software-docs-review`
- `scientific-crate-docs-review`
- `cpp-api-docs`
- `rust-api-docs`
- `scientific-citation-audit`
- `academic-authorship-boundary`

Use `selected`, `skipped`, or `blocked`. Record reused evidence as `selected` and explain its source rather than running a duplicate pass.

## Pass Order

Use the routing reference as the single source for individual selection and shared ownership. Run the selected passes in this order:

1. academic boundary, so its constraints govern later edits
2. repository documentation
3. scientific software documentation
4. ecosystem release metadata
5. C++ and/or Rust API documentation
6. citations and provenance
7. reconciliation of shared files and focused validation

Reuse complete C++ or Rust API-documentation evidence from the corresponding language orchestrator for the same scope. Record the documentation skill as selected with reused evidence.

Project tooling and language reviewers remain authoritative for commands, generators, build support, APIs, and implementation behavior quoted by docs. Consume existing evidence when supplied; otherwise hand disputed facts to the focused owner before editing downstream claims.

## Per-Skill Fix Loop

For each selected skill:

1. Announce the skill and handed-off scope.
2. Read its `SKILL.md` completely and only directly relevant references.
3. Inspect authorities and record findings or an explicit no-finding result.
4. Defer overlapping shared-file edits until all owners establish facts.
5. Implement focused fixes when authorized.
6. Run the narrowest authoritative validator. When fixes are explicitly
   authorized, repair in-scope failures and rerun the validator; otherwise
   record the failure and report it as deferred or blocked without editing the
   worktree.

Do not report one blended pass as orchestrated evidence.

## Final Summary

Lead with unresolved factual, safety, scientific, citation, or authorship blockers. Include files changed, discrepancies preserved for source owners, the evidence table, references loaded, validators and results, generated artifacts deferred, remaining limitations, and git-state status.
