---
name: crate-docs-update
description: "Update and release-audit documentation suites for scientific Rust crates, keeping README, REFERENCES, CITATION.cff, AGENTS, all active docs/**, and paper/process docs consistent. USE FOR: full documentation sweeps before releases; docs after code, algorithm, or release changes; version metadata synchronization; REFERENCES entries; active topic, API-design, invariant, scientific-basis, validation, benchmark, coverage, performance, roadmap, TODO, policy, and releasing docs. DO NOT USE FOR: commit messages (use changelog-commit-message); Rust /// docs (use rust-api-docs); Cargo/features/MSRV/lints (use rust-cargo-hygiene); generated CHANGELOG content (delegate to git-cliff); manuscript prose under Adam's name (use academic-authorship-boundary); code changes; non-documentation chores."
---

# crate-docs-update

Update the documentation suite for a scientific Rust crate so that the README, references, citation metadata, AGENTS guidance, and per-topic `docs/*.md` files stay consistent with the code and with each other.

These crates carry a coupled multi-file doc set. A new algorithm needs a citation in `REFERENCES.md`, a topic doc under `docs/`, and a feature mention in `README.md`. A release needs the version triple to match across `Cargo.toml`, `CITATION.cff`, `README.md`, and `CHANGELOG.md`. Drift is silent and shows up at release time.

## Scope

Use this skill to update existing documentation files, including:

- **Top-level**: `README.md`, `REFERENCES.md`, `CITATION.cff`, `AGENTS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- **`docs/` topic files**: `api_design.md`, `invariants.md`, `numerical_robustness_guide.md`, `topology.md`, `validation.md`, `code_organization.md`, `scientific_basis.md`, `foliation.md`, `metropolis.md`, `moves.md`, `proposal_validation.md`, `roadmap.md`, `KNOWN_ISSUES_*.md`, `TODO.md`, `BENCHMARKING.md`, `COVERAGE.md`, `PERFORMANCE.md`, `ORIENTATION_SPEC.md`, etc.
- **`docs/RELEASING.md`** when the release process itself changes
- **Paper/process docs** such as `docs/dev/docs.md`, paper build workflows, and paper artifact guidance, while respecting the academic authorship boundary for manuscript prose.

Treat these examples as common owners, not a closed allowlist. Inventory every tracked active documentation file, including less prominent `docs/**` files and support documentation outside `docs/`. Exclude `docs/archive/**` and equivalent repository-designated archive trees from release review unless the user explicitly requests archive maintenance.

Do not hand-edit `CHANGELOG.md`. These crates use `git-cliff` (`cliff.toml`) to generate it from commit history. See [Changelog handling](#changelog-handling).

If the user only asked for a commit message, defer to `changelog-commit-message`. If the issue is `///` doc quality on the Rust public API, defer to `rust-api-docs`. If the issue is `Cargo.toml`/feature flags/MSRV/lint setup, defer to `rust-cargo-hygiene`.

## Workflow

### 1. Discover the doc suite that actually exists

Each repo has a different active documentation surface. Inspect first; do not assume or limit the review to familiar filenames.

- inventory tracked active documentation across the repository, including top-level files, non-archived `docs/**`, and support docs such as `scripts/README.md`
- exclude `docs/archive/**` and equivalent designated archive trees by policy; do not read, update, or validate their intentionally historical content unless archive maintenance is explicitly requested
- classify remaining tracked documents as active, generated, template, or otherwise out of scope; record the reason for every non-archive exclusion
- read `cliff.toml` to confirm changelog generation is delegated to `git-cliff`
- read `CITATION.cff` to capture authors, ORCIDs, version, and date
- read the top of `README.md` to capture install snippets, badges, and feature lists

Prefer `git ls-files '*.md' '*.cff' ':(exclude)docs/archive/**'` plus repository-specific documentation extensions and archive exclusions so ignored build output and intentional history stay outside the active review without hiding tracked active files.

### 2. Expand release-readiness reviews to the full active suite

For release preparation or release-readiness review, the change diff identifies likely downstream effects but does not define the documentation scope. Read every tracked active document, including unchanged files, and give each one an explicit outcome: updated, verified current, intentionally historical, generated from a named source, or deferred with a reason.

Check every active document for:

- current crate version, prior-release comparisons, tag arguments, install snippets, badges, and release dates
- renamed, removed, deprecated, newly added, or feature-gated APIs and behavior
- commands, recipes, workflow names, paths, artifact names, and generated-file ownership
- guarantees, limitations, invariants, supported dimensions/features, and scientific claims
- benchmark, performance, coverage, compatibility, roadmap, TODO, and known-issue state
- navigation links and claims duplicated or summarized in another active document

Distinguish intentional historical references, compatibility notes, archived reports, baseline tags, and tool versions from stale current guidance. Do not bulk-replace version strings without classifying their meaning.

### 3. Map the change to affected docs

Use the staged or recent change as the source of truth and decide which docs are downstream of it.

- **New public API or behavior** → `README.md` (feature list, examples), `docs/api_design.md` (or equivalent), `lib.rs` `//!` overview if it summarizes the surface
- **New algorithm, predicate, or move type** → `REFERENCES.md` (academic citation), the matching topic doc (e.g., `metropolis.md`, `moves.md`, `scientific_basis.md`, `foliation.md`), `README.md` if user-visible
- **New invariant or safety property** → `docs/invariants.md`, `docs/numerical_robustness_guide.md`, `ORIENTATION_SPEC.md`, or whichever topic doc owns that property
- **Release** → `CITATION.cff` (`version`, `date-released`, `commit`), `Cargo.toml` (`[package].version`), `README.md` (install snippets, version badges if present); `CHANGELOG.md` is regenerated by `git-cliff`, not edited
- **Breaking change** → migration notes in `README.md` and `docs/api_design.md`; the CHANGELOG entry is produced by `git-cliff` from commit messages
- **Roadmap progress** → `docs/roadmap.md`, `KNOWN_ISSUES_*.md`, `TODO.md` as appropriate
- **Performance, benchmark, or coverage shifts** → `docs/PERFORMANCE.md`, `BENCHMARKING.md`, `COVERAGE.md` if they exist
- **Process or policy changes** → `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `AGENTS.md`, `docs/RELEASING.md`

If the relevant topic doc does not exist, prefer extending a related existing doc over creating a new file. Only add a new doc when the topic is genuinely new and persistent.

If the change touches manuscript or publication material under `papers/`, use `academic-authorship-boundary` as the governing constraint. You may update paper build tooling, artifact freshness checks, bibliography wiring, outline/TODO scaffolds, and repository guidance, but do not write substantive paper prose for Adam.

### 4. Maintain cross-document consistency

These checks save release-day surprises.

- **Version triple** in `Cargo.toml`, `CITATION.cff`, `README.md` (install snippets, badges), and the most recent release section of `CHANGELOG.md` (which `git-cliff` produces) all agree.
- **Authors and ORCIDs** in `CITATION.cff` match `Cargo.toml` `[package].authors` and any author block in `README.md`.
- **`date-released`** in `CITATION.cff` matches the actual release date being prepared.
- **References**: every entry in `REFERENCES.md` is cited from at least one doc or from code comments; every citation in code/docs has a corresponding `REFERENCES.md` entry. Treat orphans on either side as bugs.
- **Repository links**: `repository`/`documentation`/`homepage` in `Cargo.toml` and `CITATION.cff` agree.
- **License**: the `license` field in `Cargo.toml` matches `CITATION.cff` and the `LICENSE` file.

### 5. Respect tooling boundaries

#### Changelog handling

These crates use `git-cliff` driven by `cliff.toml`. Do not hand-edit changelog content that `git-cliff` owns.

- preview unreleased entries: `git cliff --unreleased`
- render a release section for tag `vX.Y.Z`: `git cliff --tag vX.Y.Z`
- if a wrong or missing entry would result, fix the upstream commit message (via `changelog-commit-message`) or `cliff.toml` configuration; do not patch `CHANGELOG.md` directly
- parts of `CHANGELOG.md` that `git-cliff` does not own (header above its template, footer/links, notes the `cliff.toml` template explicitly preserves) may be edited

#### `CITATION.cff`

- preserve the schema; validate with `cffconvert --validate` when available
- update `version`, `date-released`, `commit`, and `doi` when known
- keep author ordering stable across releases unless the team agrees otherwise

#### Auto-generated content

- never edit files marked auto-generated (e.g., `cargo-readme` output, `mdbook` build artifacts, generated API docs)
- if a generated file looks wrong, fix the source instead
- when a workflow checks generated paper/PDF/figure artifacts, document the source command and freshness check rather than patching generated outputs by hand

### 6. Per-repo convention sensitivity

Read the existing docs before editing. Common patterns observed across these crates:

- **Invariant-heavy crates** keep dedicated docs for invariants, orientation, and numerical robustness; new public behavior often needs an entry there.
- **MCMC-style crates** separate scientific basis from move/proposal validation; new moves or proposals usually touch both.
- **CDT-style crates** have per-concept topic docs (foliation, metropolis, moves); add to the matching one rather than mixing.
- **Linear-algebra/perf crates** lean on `BENCHMARKING.md`/`PERFORMANCE.md`/`COVERAGE.md`; performance-relevant changes belong there.
- **`AGENTS.md`** captures the project's agent guidance; update it only when agent instructions actually change, not on every code change.

### 7. Editing discipline

- prefer surgical edits to the relevant section; do not rewrite whole files for a small change
- preserve existing tone, heading style, and link conventions
- match the existing reference format in `REFERENCES.md` (numbered, BibTeX, plain academic) instead of mixing styles
- keep the doc set ASCII-clean unless the file already uses Unicode for math
- update the table of contents only if the file has one and the change adds or removes a heading
- avoid trailing-whitespace, line-ending, or formatting churn unrelated to the change

## Output Format

### Doc surface inspected
- complete tracked documentation inventory with active/archive/generated classification
- per-file release-readiness outcome for every active document
- tooling files inspected (`cliff.toml`, `CITATION.cff`)

### Mapped updates
- file → reason it changed (algorithm, version, invariant, roadmap, etc.)

### Changes made
- per file, the section(s) updated and the substantive content added or changed
- cross-document consistency checks performed (version triple, authors, references) and their result

### Deferred to tooling
- changelog regeneration commands the user should run (`git cliff --unreleased`, `git cliff --tag vX.Y.Z`)
- any commit-message fixes recommended (route via `changelog-commit-message`)

### Validation
- `cffconvert --validate` when available
- markdown link/format check if the project runs one
- spell/typo check if `typos.toml` is present

### Follow-ups
- docs deliberately not updated and why
- topic docs that should be created in a future change
