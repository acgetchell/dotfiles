---
name: repository-docs-review
description: "Review and fix an active repository documentation suite for navigation, operational clarity, generated-file ownership, and cross-document consistency. Use for README, AGENTS, CONTRIBUTING, SECURITY, codes of conduct, docs/**, runbooks, architecture guides, and ADRs. Route command truth, language behavior, scientific claims, citations, C++ or Rust API docs, and scholarly prose to focused owners."
---

# Repository Documentation Review

Review the active documentation suite as a coherent product. Keep instructions,
navigation, operational claims, generated outputs, and source-owned facts aligned
without assuming that the repository is a Rust crate or scientific software.

## Ground Rules

- Read repository-local agent guidance, documentation configuration, and navigation
  files before editing.
- Do not mutate git state unless the user explicitly asks in the current turn.
- Preserve unrelated worktree changes and use read-only git discovery.
- Treat source code, configuration, inventories, fixtures, and generators as the
  authorities for facts they own. Do not silently change supplied data to make prose
  agree; preserve it and report discrepancies unless the user asks to change the
  authoritative source.
- Never hand-edit generated regions or build output. Update the declared source or
  generator, regenerate through the repository command, and include the output when
  repository guidance requires it.
- Select scientific, academic, Rust, or citation specialists from the content in
  scope, not from the repository label.

## Scope

Inventory the documentation surface that actually exists. Common active documents
include:

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

Default to the parent task's branch or changed-file scope. For an explicit whole-repo
baseline or documentation release-readiness review, inspect every tracked active
document, including unchanged files. A diff supplies context; it does not limit a
full-suite review.

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
- clear generated-file boundaries and reproducible regeneration instructions
- repository-consistent headings, code fences, line length, and Markdown style

Distinguish intentional historical examples, versioned migration notes, and archive
content from stale current guidance. Do not perform blind version or name replacement.

### 4. Fix and Validate

Make focused edits that preserve the repository's tone and structure. Prefer extending
the owning page over creating a competing page. Add new navigation entries whenever the
repository requires them.

Run the narrowest authoritative checks first, followed by the repository-mandated docs
or CI command. Typical checks include a docs/site build, generated-output drift check,
Markdown lint, link validation, spelling, and configuration parsing. Do not invent a
validator when the repository already defines one.

If a check needs unavailable network access or installation, run the strongest local
substitute and report the remaining gap.

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

## Output

Report:

- scope mode and the active/generated/archive classification
- documents inspected and the authority used for important claims
- findings or explicit no-finding results, with file-level evidence
- edits made and any discrepancy deliberately left for follow-up
- specialist handoffs selected or skipped and why
- validators run and their results
- remaining validation gaps or deferred work
