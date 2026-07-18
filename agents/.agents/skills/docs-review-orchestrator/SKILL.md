---
name: docs-review-orchestrator
description: "Coordinate multi-pass documentation reviews across active repository docs, generated-doc ownership, Rust API docs, scientific crate metadata, citations, and academic publication boundaries. Use for branch, staged, release-readiness, or repository-wide documentation work requiring more than one focused documentation skill."
---

# Documentation Review Orchestrator

Coordinate a domain-neutral repository documentation pass with the smallest applicable
specialist overlays. Keep ownership separate, preserve evidence from each pass, and
reconcile shared files only after their authoritative reviewers establish the facts.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Read repository-local guidance and honor a parent `repo-review` handoff without
  silently narrowing its scope.
- Default to branch scope unless the user explicitly requests staged-only,
  changed-file-only, release-readiness, or whole-repo baseline scope.
- Treat an explicit request to prepare, audit, or review a release as
  release-readiness mode unless the user names a narrower documentation scope.
- In release-readiness or whole-suite mode, inspect every tracked active document,
  including unchanged files; exclude designated archives unless requested.
- Preserve generated-file ownership and authoritative source data.
- Fix actionable findings when requested; otherwise report file-level evidence.
- Select scientific and academic specialists from content triggers, never from a broad
  repository category.

## Review Trace

Before focused passes, report the scope mode, selected and skipped skills, why each
applies, and the pass order. Before each selected skill, name the exact files or
inventory slice handed to it. Record loaded references, findings or an explicit
no-finding result, fixes, and validators.

For a broad or parent-orchestrated review, end with a `Documentation Review Evidence`
table:

| Skill | Status | Why selected or skipped | Scope handed off | References loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include one row for each of `repository-docs-review`,
`scientific-crate-docs-review`, `rust-api-docs`, `scientific-citation-audit`, and
`academic-authorship-boundary`. Use `selected`, `skipped`, or `blocked`.
Record a complete reused parent pass as `selected` and note that its evidence was
reused instead of running a duplicate pass. After the table, record any external
tooling, language, generator, data-owner, or scientific-code handoffs.

## Required Routing

1. Read [`references/check-routing.md`](references/check-routing.md).
2. Select the smallest applicable set from:
   - `repository-docs-review`
   - `scientific-crate-docs-review`
   - `rust-api-docs`
   - `scientific-citation-audit`
   - `academic-authorship-boundary`
3. Load every selected skill's `SKILL.md` completely before applying it.
4. Follow directly referenced resources only when they apply.
5. Run each selected skill as a distinct blocking pass and retain its evidence.
6. Reconcile overlapping files using the ownership rules below.

## Pass Order

1. Apply `academic-authorship-boundary` first when scholarly manuscript prose or
   reviewer responses are in scope; it constrains later edits.
2. Run `repository-docs-review` for the active documentation suite in any repository.
3. Run `scientific-crate-docs-review` when scientific Rust crate metadata, release
   coupling, or scientific topic docs are present.
4. Run `rust-api-docs` for Rust `///` and `//!` docs, intra-doc links, and public API
   coverage. Reuse complete evidence from a prior Rust orchestrator pass for the same
   scope rather than duplicating it, and record the skill as `selected` with reused
   evidence.
5. Run `scientific-citation-audit` for bibliographic validity, provenance, scientific
   claims, DOI/source identity, or credit alignment.
6. Reconcile shared files, then run the strongest applicable documentation validators.

## Ownership

- `repository-docs-review` owns suite inventory, navigation, generic cross-document
  consistency, operational clarity, and generated-document boundaries.
- `scientific-crate-docs-review` owns scientific Rust crate metadata and release
  coupling across Cargo, README, CITATION, references, and scientific topic docs.
- `rust-api-docs` owns Rust API documentation quality and coverage.
- `scientific-citation-audit` owns bibliographic and scientific provenance facts.
- `academic-authorship-boundary` constrains scholarly prose that will appear under a
  human author's name.
- Project tooling and language reviewers remain authoritative for commands and
  implementation behavior quoted by docs.

Project tooling and language reviewers are external source owners, not documentation
child passes. When a parent review already supplies their evidence, consume it. In a
direct docs review, hand off disputed command, generator, API, or behavior truth to the
focused owner before editing the downstream claim; if that owner cannot run, preserve
the authoritative source and report the unresolved discrepancy.

## Fix and Validation Loop

For each selected pass:

1. inspect the handed-off scope and its authoritative sources
2. record findings or an explicit no-finding result
3. make focused fixes when authorized; for a file shared by multiple selected owners,
   defer overlapping edits until every applicable owner establishes its facts
4. run the narrowest focused validator
5. fix and rerun failures before moving on
6. retain evidence for final synthesis

After all fact-establishing passes, reconcile deferred shared-file edits once and run
the applicable validators on the reconciled result.

End with files changed, discrepancies left for follow-up, specialist selections and
skips, validators and results, generated artifacts deferred, remaining risks, and a
confirmation of whether git state was left untouched.
