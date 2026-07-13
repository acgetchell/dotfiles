# Documentation Check Routing

Use this reference after the parent scope is established.

## Scope Selection

- Branch mode: include committed branch changes plus staged, unstaged, and untracked documentation work handed off by `repo-review`.
- Narrow modes: honor explicit staged-only or changed-file-only requests.
- Release-readiness mode: inventory every tracked active documentation file and inspect the complete active suite even when individual files are unchanged. Exclude `docs/archive/**` and equivalent designated archive trees unless explicitly requested; classify generated or otherwise excluded non-archive material and require a recorded outcome for each active file.
- Whole-repo baseline mode: inventory tracked active docs, Rust documentation, citation surfaces, and publication/process material. Exclude archives unless requested.

## Skill Matrix

Select `crate-docs-update` for README, REFERENCES, CITATION, AGENTS, CONTRIBUTING, SECURITY, every active `docs/**` file, support documentation elsewhere in the repository, release metadata, version synchronization, benchmark/coverage docs, roadmaps, and process guidance. In release-readiness mode, its scope is the full tracked active documentation inventory, not the changed-file list.

Select `rust-api-docs` for `///` and `//!` comments, crate/module overviews, public API contracts, intra-doc links, docs.rs feature visibility, or API-supporting private helper docs. When a parent Rust orchestrator already completed this pass for the same files, record it as skipped with that evidence instead of rerunning it.

Select `scientific-citation-audit` for changed bibliography entries, DOI or source links, provenance claims, algorithm/data-structure credit, citation metadata beyond routine version/date synchronization, or an explicit whole-repo scientific citation baseline. Network DOI validation is part of a selected citation pass; request approval if needed.

Select `academic-authorship-boundary` whenever papers, manuscripts, reviewer responses, publication drafts, or substantive scholarly prose are in scope. Apply its constraints before any other documentation edit.

## Shared Files

- `README.md`: crate docs for suite consistency; Rust API docs for copyable Rust examples and API claims; citation audit for scientific provenance claims; tooling for commands.
- `REFERENCES.md`: crate docs for bibliography ownership and local consistency; citation audit for correctness, relevance, and credit.
- `CITATION.cff`: crate docs for release metadata/schema consistency; citation audit when identifiers, authorship credit, or cited-work metadata changes.
- Rust source: Rust API docs for rendered comments; citation audit for provenance claims; Rust reviewers for implementation truth.
- `docs/RELEASING.md`, `AGENTS.md`, and `CONTRIBUTING.md`: crate docs for process-suite consistency; tooling for command truth.

## Validation

Choose validators proportionally and avoid duplicate broad runs:

- repository Markdown, spell, and link checks for Markdown changes
- `cffconvert --validate` or the repository equivalent for `CITATION.cff`
- `cargo doc`/doctest validation for Rust API documentation changes
- DOI metadata checking plus manual relevance inspection for citation audits
- repository-generated-file checks without hand-editing generated outputs
