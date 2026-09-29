---
name: repository-docs-review
description: "Review and fix an active repository documentation suite for navigation, operational clarity, generated-file ownership, and cross-document consistency. Use for README, AGENTS, CONTRIBUTING, SECURITY, codes of conduct, docs/**, runbooks, architecture guides, and ADRs. Route command truth, language behavior, scientific claims, citations, C++ or Rust API docs, and scholarly prose to focused owners."
---

# Repository Documentation Review

Align active documentation's instructions, navigation, operational claims,
generated outputs, and source-owned facts without assuming Rust or scientific
software.

## Ground Rules

- Read repository-local agent guidance, documentation configuration, and navigation
  files before editing.
- Do not mutate git state unless the user explicitly asks in the current turn.
- Preserve unrelated worktree changes and use read-only git discovery.
- Treat source code, configuration, inventories, fixtures, and generators as
  authoritative. Preserve supplied data and report discrepancies unless the user
  asks to change its source.
- Never hand-edit generated regions or build output. Update the declared source or
  generator, regenerate through the repository command, and include the output when
  repository guidance requires it.
- Select scientific, academic, Rust, or citation specialists from the content in
  scope, not from the repository label.

## Scope

Inventory existing documentation, including:

- `README*`, `AGENTS.md`, `CONTRIBUTING*`, `SECURITY*`, and `CODE_OF_CONDUCT*`
- active `docs/**` content, including runbooks, architecture guides, ADRs, policies,
  diagrams, and release or migration guides
- book or site navigation such as `SUMMARY.md`, table-of-contents files, and sidebar
  configuration
- support documentation next to scripts, fixtures, infrastructure, examples, or
  deployment assets
- generated Markdown whose source and regeneration contract are documented

Treat this as examples, not an allowlist. Classify tracked documentation as active,
generated, template, archived, or otherwise out of scope. Exclude repository-designated
archives unless the user explicitly requests archive maintenance.

Read [`references/latex-validation.md`](references/latex-validation.md) only when LaTeX, TeX tooling, publication builds, PDF generation, `chktex`, or TeX-produced documentation is in scope.

When invoked directly without an exact parent scope, validation ledger, and
result contract, read
[`references/standalone-workflow.md`](references/standalone-workflow.md).
Review-graph and documentation-orchestrator dispatches already own that
information.

## Workflow

### 1. Establish Sources and Navigation

- identify repository instructions and the canonical docs build/check commands
- identify the navigation source of truth and confirm active pages are reachable
- find generated-file markers, source datasets, fixtures, templates, and generators
- note which commands, APIs, configuration, inventories, or external systems own the
  claims repeated in documentation

### 2. Map Changes to Documentation

Use the scoped diff or baseline inventory to find downstream effects:

- changed behavior, interfaces, or configuration -> user and operator guidance
- changed commands, recipes, workflows, or tool pins -> setup and validation docs
- changed infrastructure or security policy -> architecture, policy, and runbooks
- changed source data or generator output -> generated docs and their ownership notes
- renamed or removed paths -> navigation, links, examples, and handoff instructions
- changed release state -> current-version, migration, compatibility, and support docs

Ask the source-owning reviewer to settle uncertain behavior before rewriting a claim.

### 3. Review the Active Suite

Check each applicable document for:

- factual agreement with its authoritative source
- current commands, paths, filenames, workflow names, and prerequisites
- safe operational sequencing, rollback or failure guidance, and secret hygiene
- consistent terminology, scope, ownership, and cross-references
- accurate status, support, compatibility, and limitation statements
- reachable navigation, valid local links, and non-duplicative placement
- active documentation links independent of the library or package version;
  release automation must preserve stable destinations instead of rewriting them
  to release tags or version-specific API URLs
- clear generated-file boundaries and reproducible regeneration instructions
- repository-consistent headings, code fences, line length, and Markdown style

Use relative links within a documentation tree and stable default-branch or
published API aliases where absolute URLs are needed. Keep active navigation
working before a release tag exists. Preserve version-specific destinations for
historical evidence, changelogs, citations, and explicitly versioned documentation.
Distinguish these from stale current guidance; do not perform blind replacements.

When reviewing README entry points or links reused in generated documentation and
package pages, read [README navigation](references/readme-navigation.md).

## Specialist Handoffs

Keep ownership explicit and select only specialists required by the files and claims:

- `project-tooling-review`: command, CI, workflow, installer, and tool-version truth
- language reviewers: API, example, and behavior truth for the implementation language
- `cpp-api-docs`: C++ public comments, Doxygen/reference output, caller contracts, and canonical examples
- `rust-api-docs`: Rust `///` and `//!` documentation or API-supporting helper docs
- `scientific-software-docs-review`: scientific claims, validation evidence, reproducibility, limitations, and research artifacts
- `scientific-crate-docs-review`: Rust Cargo/README/CITATION release metadata and generated changelog coupling
- `scientific-citation-audit`: bibliographic identity, DOI/source validity, scientific
  provenance, scientific claims, and credit alignment
- `academic-authorship-boundary`: substantive scholarly manuscript prose or reviewer
  responses intended to appear under a human author's name

The presence of Markdown, an academic-sounding repository name, or ordinary source
links does not by itself justify the scientific or academic specialists.
