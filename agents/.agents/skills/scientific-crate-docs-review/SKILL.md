---
name: scientific-crate-docs-review
description: "Review Rust-specific release documentation coupling for scientific crates across Cargo metadata, README installation and release claims, CITATION.cff synchronization, crates.io identity, docs.rs metadata, authorship, license, repository links, and generated changelogs. Use when scientific Rust crate release metadata is materially in scope; route language-neutral scientific claims and validation documentation to scientific-software-docs-review."
---

# Scientific Crate Documentation Review

Review the Rust ecosystem release layer for a scientific crate. Keep this pass narrow: establish consistency among Cargo, README, citation metadata, crates.io-facing identity, docs.rs configuration, and generated changelog ownership without repeating generic or scientific documentation reviews.

## Scope And Boundaries

Select this skill only when scientific Rust crate release metadata is material. Do not select it merely because the repository contains Rust or scientific documentation.

- Let `repository-docs-review` own suite navigation, operational clarity, and generic consistency.
- Let `scientific-software-docs-review` own scientific claims, validation methodology, benchmarks, reproducibility, limitations, and research artifacts.
- Let `rust-api-docs` own `///`, `//!`, public coverage, examples, links, and rendered API quality.
- Let `rust-cargo-hygiene` own manifest design, features, MSRV, dependency, and publishing correctness.
- Let `scientific-citation-audit` own DOI identity, bibliographic validity, provenance, and credit.
- Let `academic-authorship-boundary` constrain manuscript prose.

Use complete parent evidence rather than rerunning these passes.

## Applicable Surface

Inspect only files relevant to the release contract, such as:

- `Cargo.toml` package name, version, authors, license, repository, homepage, documentation, readme, keywords, categories, and published features
- README installation/version examples, compatibility statements, crate badges, and links
- `CITATION.cff` version, release date, repository identity, authors, ORCIDs, DOI, and preferred citation
- crates.io and docs.rs metadata or release configuration
- `cliff.toml` or another source for generated changelog sections
- release and migration guidance tied to the crate version

Use the parent inventory to exclude unrelated generic docs, manuscripts, archives, and generated build output.

## Review Workflow

1. Identify the release being prepared and the authoritative version source.
2. Inventory crate identity and release fields repeated across Cargo, README, CFF, release notes, and generated sites.
3. Classify each repeated value as authoritative, derived, or independently intentional.
4. Check generated changelog ownership and release-date/commit semantics.
5. Hand scientific claims, API docs, citation validity, and manifest design to their owners.
6. Run the narrowest crate documentation and metadata validators.

## Cross-File Release Consistency

Check, when applicable:

- package name and current version agree where exact values are intentionally repeated
- README installation snippets and feature names match the published Cargo surface
- MSRV or supported-platform statements come from established build evidence
- repository, homepage, documentation, license, and readme links resolve to intended release resources
- author names, ordering, roles, and ORCIDs are intentionally synchronized or explicitly different
- `CITATION.cff` release date, version, commit, and preferred citation describe the artifact actually being released
- docs.rs feature/configuration claims match the public API intended to render
- migration and compatibility guidance names the correct versions

Do not force every metadata file to have identical authorship semantics. Record deliberate differences between code authors, maintainers, paper authors, and citation credit.

Do not validate a DOI from memory. Select `scientific-citation-audit` when identity or provenance is in question. A version/date-only CFF synchronization does not require a full citation pass.

## Generated Changelogs

When `git-cliff` or another generator owns `CHANGELOG.md`, fix commit categorization, templates, or generator configuration and regenerate through the documented command. Do not hand-edit generated entries.

Check that release headings, versions, dates, comparison links, categories, and breaking-change notes correspond to the prepared release. Route upstream commit-message correction to `changelog-commit-message` when appropriate.

## Validation

Prefer repository commands. Relevant focused evidence includes:

- Cargo metadata and publish/package checks owned by Rust/tooling reviewers
- README examples or install snippets against the intended crate version
- CFF validation
- docs.rs configuration or local rustdoc build when release metadata affects rendering
- generated changelog preview/drift check
- link and documentation configuration validation

Do not run a broad citation, scientific, or API pass solely because these validators mention the same files.

## Output

Report the release identity, metadata authorities, files inspected, inconsistencies and deliberate differences, generated artifacts, specialist handoffs, validators, and unverified external release surfaces.
