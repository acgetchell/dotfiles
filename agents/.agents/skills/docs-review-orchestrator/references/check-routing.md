# Documentation Check Routing

Use this reference after establishing the requested scope and before loading focused
skills.

## Scope Discovery

Default to branch scope and include committed branch changes plus staged, unstaged, and
untracked work. Use an explicit staged-only, changed-file-only, release-readiness, or
whole-repo baseline scope only when requested or handed off by `repo-review`.
Treat an explicit request to prepare, audit, or review a release as release-readiness
unless the user explicitly narrows the documentation surface.

Use read-only git discovery. In release-readiness or whole-suite mode, inventory every
tracked active document. Classify generated, template, archived, or otherwise excluded
files and record the reason. A diff supplies change context but does not bound a full
documentation suite review.

## Route by Actual Surface

### `repository-docs-review`

Select for any substantive repository documentation review, including:

- README, AGENTS, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, and support docs
- active `docs/**`, runbooks, architecture guides, ADRs, policies, and diagrams
- book/site navigation, cross-document consistency, and link structure
- generated Markdown ownership, source datasets, fixtures, or regeneration guidance
- release, migration, compatibility, operational, and maintainer documentation

This is the default documentation owner for scientific and non-scientific repositories.

### `scientific-crate-docs-review`

Add only when the scope materially includes a scientific Rust crate concern:

- Cargo/README/CITATION version, authorship, license, or repository metadata coupling
  that explicitly describes a scientific or research crate or artifact
- `CITATION.cff`, `REFERENCES.md`, or `cliff.toml` when coupled to scientific or
  research release metadata or provenance
- scientific algorithm, invariant, numerical, validation, benchmark, provenance, or
  research-artifact docs tied to Rust crate behavior

Do not select it for generic Rust docs, ordinary operational docs, or an infrastructure
repository without these surfaces.

### `rust-api-docs`

Add for Rust `///` or `//!` docs, public-item coverage, required sections, intra-doc
links, feature visibility, or private helpers that support public API docs. Skip a
duplicate pass when a parent Rust review already supplied complete evidence for the
same scope.

### `scientific-citation-audit`

Add for bibliographic existence or identity, DOI/source validity, algorithm provenance,
scientific claims, or scientific credit alignment. Do not select it for ordinary web
links, a generic source list, or a `CITATION.cff` version/date-only synchronization.

### `academic-authorship-boundary`

Apply before all editing when the scope includes substantive scholarly manuscript
prose, thesis/paper sections, reviewer responses, or publication text intended to
appear under a human author's name. Do not select it for operational docs, repository
policy, publication build tooling, bibliography wiring, or artifact freshness checks
that contain no substantive manuscript prose.

## Shared Ownership

- Docs containing commands: project tooling owns command truth;
  `repository-docs-review` owns placement, clarity, and suite consistency.
- Docs describing code or APIs: language reviewers own behavior truth;
  `repository-docs-review` owns downstream consistency.
- README in a scientific Rust crate: the generic reviewer owns its repository-doc role;
  the scientific overlay owns crate release and scientific metadata; Rust reviewers own
  examples and behavior.
- `CITATION.cff`: the scientific overlay owns cross-file release metadata; citation
  audit owns bibliographic/provenance validity.
- `REFERENCES.md`: the scientific overlay owns crate-doc coupling; citation audit owns
  bibliographic validity and credit.
- Paper directories: the academic boundary governs manuscript prose; generic docs and
  tooling reviewers may still own build or artifact instructions.
- Generated docs: when the authoritative change is within the user's requested scope,
  fix the declared source or generator and regenerate; never patch the generated region
  to hide drift. Preserve user-supplied or out-of-scope source values and report the
  discrepancy instead of changing them for consistency.

## Validation

Use repository-defined commands first. Select validators from actual files and edits:

- documentation or site build for navigation and rendering
- generated-output drift checks when source-backed docs changed
- Markdown, link, spelling, and configuration checks
- Rust doc tests or API-doc checks for Rust documentation
- CFF validation for citation metadata
- publication build or freshness checks for publication tooling

Run the narrowest focused checks first, then the repository-mandated aggregate command
when the changed surface requires it. Report unavailable network- or installation-bound
checks rather than claiming they passed.
