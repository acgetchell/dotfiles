---
name: scientific-crate-docs-review
description: "Review and fix the scientific Rust crate documentation overlay that couples Cargo metadata, README release claims, CITATION.cff, REFERENCES.md, scientific topic docs, release guidance, and generated changelog ownership. Use with repository-docs-review for scientific Rust documentation suites, release-readiness checks, version and credit synchronization, algorithm provenance, or scientific validation documentation. Do not use for generic repository docs, ordinary operational runbooks, Rust /// docs, Cargo feature design, or scholarly manuscript prose."
---

# Scientific Crate Documentation Review

Review the scientific Rust-specific layer after the generic documentation surface is
known. This skill owns crate metadata, scientific credit and provenance handoffs, and
release coupling; `repository-docs-review` owns the general suite inventory,
navigation, style, operational clarity, and generated-document workflow.

## Ground Rules

- Do not mutate git state unless explicitly requested.
- Do not broaden a generic docs task into a scientific review merely because the
  repository is written in Rust or has research users.
- Use the parent review's inventory and findings when available instead of repeating
  the generic documentation pass.
- Treat `Cargo.toml`, source code, release configuration, and validated bibliographic
  records as authorities for the claims they own.
- Do not write substantive manuscript prose under a human author's name.
- Do not hand-edit generated changelog content or generated publication artifacts.

## Applicable Surface

Select this skill when one or more of these surfaces is materially in scope:

- scientific Rust crate release documentation and version synchronization
- `CITATION.cff`, `REFERENCES.md`, crate authorship, ORCIDs, licenses, or repository
  metadata
- scientific algorithm, invariant, numerical robustness, validation, benchmark, or
  provenance documentation tied to crate behavior
- `cliff.toml` ownership of generated `CHANGELOG.md` content
- scientific crate publication or artifact-build guidance outside manuscript prose

If invoked directly for a broad documentation review, pair it with
`repository-docs-review` or route through `docs-review-orchestrator`.

## Workflow

### 1. Inspect the Scientific and Release Authorities

Read the applicable files rather than assuming conventional names:

- `Cargo.toml` package version, authors, license, repository, documentation, homepage,
  and release-relevant feature metadata
- `CITATION.cff` version, release date, commit, DOI, authors, and ORCIDs
- `REFERENCES.md` or the repository's bibliography source
- README install/version claims and scientific feature descriptions
- active scientific topic, validation, benchmark, coverage, performance, and release
  docs
- `cliff.toml` or equivalent generated-changelog configuration

Use the parent inventory to exclude archives, generated build output, and unrelated
generic docs.

### 2. Map Scientific Changes Downstream

- new or changed algorithm/predicate/move -> owning topic and validation docs; request a
  citation audit when provenance or scientific credit is asserted
- new invariant or numerical guarantee -> invariant, robustness, and limitation docs
- changed benchmark or validation result -> methodology, environment, comparison, and
  reproducibility guidance
- crate release -> Cargo/README/CITATION version and release metadata consistency
- changed authorship, license, DOI, or repository identity -> all corresponding crate
  and citation metadata surfaces
- changed publication tooling -> artifact/build guidance, subject to the academic
  authorship boundary for manuscript prose

Ask the Rust or scientific-code owner to settle uncertain implementation claims before
editing documentation.

### 3. Check Cross-File Consistency

Verify, when applicable:

- Cargo, README install snippets, and `CITATION.cff` describe the same current release
- release dates and commit identifiers describe the release actually being prepared
- author names, ordering, and ORCIDs are intentional and consistent
- repository, documentation, homepage, and license metadata agree
- scientific features, invariants, limitations, and validation claims match the code
  and current evidence
- citations used by code or docs have bibliography entries, and bibliography entries
  are actually referenced or intentionally retained

Do not validate bibliographic existence or DOI resolution from memory. Hand those facts
to `scientific-citation-audit` when they are in scope. A `CITATION.cff` version-only edit
does not automatically require a full citation audit.

### 4. Respect Generated Ownership

When `git-cliff` owns `CHANGELOG.md`, preview or regenerate through the repository's
documented command. Fix upstream commit categorization or `cliff.toml` rather than
patching generated entries. The same rule applies to generated papers, figures, API
sites, and benchmark reports.

Validate `CITATION.cff` with the repository command or `cffconvert --validate` when
available. Run crate-specific documentation and release checks required by repository
guidance.

## Specialist Boundaries

- use `repository-docs-review` for generic documentation structure and consistency
- use `rust-api-docs` for Rust `///`, `//!`, intra-doc links, and public API coverage
- use `rust-cargo-hygiene` for feature, MSRV, lint, and manifest design
- use `scientific-citation-audit` for bibliographic validity, provenance, and credit
- use `academic-authorship-boundary` for manuscript prose and reviewer responses
- use `changelog-commit-message` when generated changelog output requires an upstream
  commit-message correction

## Output

Report:

- scientific and release files inspected
- cross-file metadata and scientific-claim checks performed
- findings, fixes, and deliberately preserved source discrepancies
- generated artifacts deferred to their owners
- specialist handoffs selected or skipped and why
- validators run and their results
