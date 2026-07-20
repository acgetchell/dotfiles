---
name: project-tooling-review
description: "Review and fix repository tooling: just recipes, GitHub Actions, CI command drift, repository-owned static analysis, tool versions, installers, linters, formatters, type checks, support scripts, and command documentation. Use for tooling workflow correctness and maintainer ergonomics; route application behavior to the appropriate language reviewer."
---

# project-tooling-review

Review the project command layer: the recipes, workflows, version pins, and docs that let maintainers run the right checks without remembering every underlying tool.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Do not install or uninstall unrelated tools unless the user explicitly asks. When the requested scope includes tool-version currentness, update drift, or "latest" tooling review, update stale tools through the repository's existing manager and reconcile tracked pins.
- Use read-only git commands to discover scope when needed: `git --no-pager status --short`, `git --no-pager diff --stat`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
- Respect repository-local agent instructions before editing. If the repository documents development commands, read that guidance before changing recipes or workflows.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for "repo", "whole repo", "entire repo", "baseline audit", or equivalent.
- When invoked by `repo-review` with a branch-scope file list or diff, honor that provided scope instead of rediscovering a narrower staged or worktree-only scope.
- When checking whether a tool is "latest" or current, verify against live authoritative sources or local package-manager metadata. Do not rely on model memory for current versions.
- For installed-tool drift, first record the resolved executable, installed version, and owning manager before comparing repo pins, docs, workflows, or remote latest metadata. A freshly upgraded local tool is evidence that must not be skipped just because no version file changed.

## Review Trace

When invoked by `repo-review`, begin with a handoff receipt that names:

- the parent branch scope and tooling-owned file list or file count handed off
- selected tooling surfaces and why they apply
- skipped tooling surfaces when a maintainer might reasonably expect them
- reference files that will be loaded

After loading each reference file, keep its name in the running trace for the final summary. This trace is required evidence that the tooling pass reviewed the intended command, workflow, or version surfaces rather than only describing them.

Evidence is grouped by tooling surface. A surface is complete only when the final summary can name the surface status (`selected` or `skipped`), reference files loaded for that surface, changed files or command owners inspected, findings or explicit no-finding result, fixes applied, and the focused validator run for that surface. Running a broad validator does not by itself count as reviewing every tooling surface.

When invoked by `repo-review`, provide table-ready evidence for the parent `Review Evidence` table: selected tooling surfaces, reference files loaded, validators run, version checks performed, and any skipped surfaces that might otherwise look missing.

## Scope Routing

After identifying changed files, load only the references that apply:

- [`references/justfile.md`](references/justfile.md) for `justfile`, command recipes, local validator tiers, recipe naming, and docs that describe `just` commands.
- [`references/github-actions.md`](references/github-actions.md) for `.github/workflows/**`, Actions permissions/triggers/caches/matrices, CI use of `just`, and workflow validation.
- [`references/tool-versions.md`](references/tool-versions.md) for `Brewfile`, `uv`, `cargo install`, `rustup`, lockfiles, action versions, language toolchains, and version drift.
- [`references/static-analysis.md`](references/static-analysis.md) for repository-owned Semgrep rules, fixtures, path scoping, and validation.
- [`references/delaunay.md`](references/delaunay.md) in the `delaunay` repository for its Semgrep fixture harness, notebook execution policy, and generated-asset
  ownership.

If multiple surfaces changed, review them in this order:

1. Tool versions and installers, so commands use the intended tools.
2. `justfile` recipes and local command contracts.
3. Repository-owned static-analysis rules, fixtures, and scan scope.
4. GitHub Actions and remote CI wiring.
5. Docs and handoff summaries that describe the command surface.

## Review Goals

### 1. Command Surface Coherence

The repository should expose a small, memorable command layer. Prefer canonical `just` recipes such as `check`, `fix`, `ci`, `test-*`, `lint-*`, `coverage`, `docs`, and release/performance recipes over duplicated command strings scattered through docs and workflows.

Flag drift between:

- `justfile`
- `.github/workflows/**`
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `docs/**`
- package/tool config files
- release or support scripts

### 2. Safety And Failure Behavior

Tooling should fail loudly and safely.

Check:

- destructive recipes require explicit arguments and clear names
- shell snippets do not swallow failures
- commands have stable working directories and path assumptions
- CI logs preserve enough context to diagnose failures
- secrets, tokens, local paths, and private data are not printed

### 3. Validation Tiers

Keep fast local checks, full CI, slow/performance checks, release checks, and fixers distinct. Do not make every local workflow run the slowest path unless the repository explicitly wants that.

Treat each aggregate recipe as a set of underlying validators and test
selections. Do not run overlapping tiers in sequence when they would replay
tests whose source/build/configuration state has not changed. Choose the
broader tier initially or add only the evidence missing from completed focused
checks. Post-fix reruns, materially different configurations, nondeterminism
diagnosis, and deliberately repeated measurements remain justified.

Require policy-mandated aggregate gates to expose enough component recipes or
selection/exclusion controls for an orchestrator to add missing evidence
without replaying completed tests. Treat an indivisible gate that forces
duplicate execution as a command-surface defect and make the overlap visible
rather than counting it twice.

### 4. Version And Update Discipline

Check that tool versions are intentional, documented where needed, and consistent across local installers, lockfiles, workflows, and docs. When latest-version claims matter, verify them live before recommending changes.

When a `justfile` is the repository's pin source, resolve its declared values with
`just --evaluate <variable>` in consumers that already have `just`; do not duplicate
the literal or scrape the file with ad hoc text parsing. Treat bootstrapping `just`
itself as the explicit exception because that pin must be read before `just` exists.
When several workflows need that bootstrap, prefer one repository-local composite
action or helper that validates the declaration, installs `just`, and exposes the
resolved version over repeated workflow parsers.

Start with the local installed version for tools that are invoked directly from the command surface, especially `uv`, `uv tool` managed CLIs, `cargo install` managed binaries, `rustup`, and Homebrew-managed CLIs. Then compare that local state against repository pins and authoritative latest-version sources. If a managed tool is stale and version updates are in scope, update it first, then update any matching repository pins, `justfile` install recipes, bootstrap scripts, docs, and GitHub Actions workflow versions.

### 5. Cross-Language Coordination

When tooling changes alter Rust or Python validation behavior, identify the affected language surface and call out whether `rust-review-orchestrator` or `python-review-orchestrator` should also run. Do not duplicate their source-code review inside this skill.

For Python packaging changes, own recipe, workflow, installer, validator, and tool-version mechanics here. Route wheel/sdist contents, package discovery, installed imports, entry points, extras, runtime/platform matrices, and external-consumer behavior through `python-review-orchestrator` to `python-build-portability`.

When command, release, or process changes affect a wider documentation suite, hand off navigation, cross-document consistency, generated-document ownership, and any applicable specialist documentation to `docs-review-orchestrator`. Keep command truth in this skill; do not absorb the broader documentation review here.

## Fix Loop

For each applicable tooling surface:

1. Read the relevant reference file.
2. Inspect changed files and nearby command owners.
3. Record explicit findings or a no-finding result for that surface.
4. Implement minimal fixes for real tooling drift, safety, or validation issues.
5. Run the focused validator for the surface when available.
6. If validation fails, fix and rerun the same validator before moving on.
7. Record changed files, commands, and the surface outcome for the final summary.

Do not report a tooling review as complete if command recipes, workflow wiring, docs, and version surfaces were blended into one undifferentiated pass. Group them logically using the order above, skipping surfaces that do not apply.

If a validator needs network, installation, or other approval, use the strongest read-only/local check available and document the remaining verification.

## Final Summary

End with a concise summary that helps the maintainer review unstaged changes by file. Include:

- each file changed and why
- tooling surfaces reviewed
- reference files actually loaded
- table-ready evidence for `repo-review` when invoked by the meta-orchestrator
- validators run and their results
- version checks performed and whether they were live or local-only
- managed tool updates performed, before/after versions, and `justfile` or GitHub Actions pins updated
- language orchestrators recommended or run, if any
- anything intentionally deferred or not run
- confirmation that no git state mutations were performed, if true

Lead with unresolved tooling risks if any remain.
