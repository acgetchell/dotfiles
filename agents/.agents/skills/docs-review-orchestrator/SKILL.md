---
name: docs-review-orchestrator
description: "Coordinate documentation review and fixes across coupled scientific-crate docs, Rust API documentation, scientific citations, release metadata, and publication boundaries. Use for branch, staged, changed-file, release-readiness, or whole-repo documentation reviews that span README.md, REFERENCES.md, CITATION.cff, docs/**, Rust doc comments, algorithm provenance, DOI links, or paper/process material. Route single-surface work to crate-docs-update, rust-api-docs, scientific-citation-audit, or academic-authorship-boundary directly."
---

# Documentation Review Orchestrator

Coordinate documentation specialists without blending their ownership. Establish the documentation scope, select the smallest applicable skills, let each complete its focused pass, and reconcile cross-document validation.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Preserve generated-file ownership. In particular, do not hand-edit generated changelogs or benchmark artifacts.
- Prefer branch scope unless the user explicitly requests staged-only, changed-file-only, release-readiness, or whole-repo baseline scope.
- In release-readiness mode, inventory and inspect the scientific crate's complete tracked active documentation suite, including unchanged files; the branch diff is context, not the documentation boundary. Exclude `docs/archive/**` and equivalent designated archive trees unless archive maintenance is explicitly requested.
- When invoked by `repo-review`, honor its handed-off file list, diff, or tracked-file inventory instead of rediscovering a narrower scope.
- Fix actionable findings when requested; otherwise report them with file-level evidence.
- Keep manuscript prose under the academic authorship boundary.

## Review Trace

Before focused passes, report the scope mode, selected and skipped skills, why each applies, and the planned order. Before each selected skill, name the exact files or inventory slice handed to it. Record its loaded references, findings or no-finding result, fixes, and validators.

When invoked by `repo-review` or handling a broad multi-surface documentation review, end with a `Documentation Review Evidence` table:

| Skill | Status | Why selected or skipped | Scope handed off | References loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include one row for each of `crate-docs-update`, `rust-api-docs`, `scientific-citation-audit`, and `academic-authorship-boundary`. Use `selected`, `skipped`, or `blocked`. For a direct, narrowly scoped task, use a concise evidence summary instead.

## Required Routing

1. Read [`references/check-routing.md`](references/check-routing.md).
2. Select the smallest applicable set:
   - `crate-docs-update`
   - `rust-api-docs`
   - `scientific-citation-audit`
   - `academic-authorship-boundary`
3. Load every selected skill's `SKILL.md` completely before applying it.
4. Follow directly referenced resources when they apply.
5. Run each selected skill as a distinct blocking pass and retain its evidence.
6. Reconcile overlapping files according to the ownership rules below.

## Pass Order

1. Apply `academic-authorship-boundary` first when papers or manuscript prose are in scope; it constrains every later edit.
2. Run `crate-docs-update` for a scientific crate's coupled documentation suite and publication/release process metadata. In release-readiness mode, hand it the complete tracked documentation inventory rather than only changed files.
3. Run `rust-api-docs` for public Rust docs, module docs, feature visibility, and API-supporting helper docs. Skip duplicate work when `rust-review-orchestrator` already supplied a complete `rust-api-docs` pass for the same scope.
4. Run `scientific-citation-audit` when references, DOI/source links, algorithm provenance, scientific credit claims, or a whole-repo scientific citation baseline are in scope.
5. Reconcile cross-file consistency, then run the strongest focused documentation validators once.

## Ownership And Handoffs

- `crate-docs-update` owns consistency across README, REFERENCES, CITATION, active topic docs, release/process docs, and generated-file boundaries.
- `rust-api-docs` owns rendered Rust documentation quality and public API contracts.
- `scientific-citation-audit` owns DOI metadata, primary-source relevance, orphan references, and claim-to-credit alignment.
- `academic-authorship-boundary` governs whether paper or manuscript prose may be edited at all.
- Project tooling remains the authority for command truth; Rust and Python reviewers remain the authority for behavior described by docs.
- A routine version/date-only `CITATION.cff` update does not require a network citation audit unless other citation claims changed.

## Final Summary

Lead with unresolved documentation or citation risks. Include the required table or concise evidence summary, files changed, consistency checks, validators and results, generated work deliberately deferred, and confirmation that no git state mutations were performed.
