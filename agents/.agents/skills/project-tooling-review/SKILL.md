---
name: project-tooling-review
description: "Review and fix repository tooling surfaces that define how maintainers run, validate, and update a project. Use for justfile recipe design, GitHub Actions workflows, CI command drift, tool-version and installer drift, uv tool and cargo-install managed CLI updates, Brewfile and uv/cargo/rustup tooling configuration, lint/format/type-check command surfaces, release/support scripts wiring, docs that describe project commands, and cross-language validation recipes. Use when the user asks to review project tooling, just recipes, CI workflows, GitHub Actions, tool versions, command consistency, or repository workflow ergonomics. Do not use for Rust or Python source review except where tooling invokes those validators; use the language orchestrators for code behavior. Do not use for requests to commit, stage, push, tag, or otherwise mutate git state."
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

## Scope Routing

After identifying changed files, load only the references that apply:

- [`references/justfile.md`](references/justfile.md) for `justfile`, command recipes, local validator tiers, recipe naming, and docs that describe `just` commands.
- [`references/github-actions.md`](references/github-actions.md) for `.github/workflows/**`, Actions permissions/triggers/caches/matrices, CI use of `just`, and workflow validation.
- [`references/tool-versions.md`](references/tool-versions.md) for `Brewfile`, `uv`, `cargo install`, `rustup`, lockfiles, action versions, language toolchains, and version drift.

If multiple surfaces changed, review them in this order:

1. Tool versions and installers, so commands use the intended tools.
2. `justfile` recipes and local command contracts.
3. GitHub Actions and remote CI wiring.
4. Docs and handoff summaries that describe the command surface.

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

### 4. Version And Update Discipline

Check that tool versions are intentional, documented where needed, and consistent across local installers, lockfiles, workflows, and docs. When latest-version claims matter, verify them live before recommending changes.

Start with the local installed version for tools that are invoked directly from the command surface, especially `uv`, `uv tool` managed CLIs, `cargo install` managed binaries, `rustup`, and Homebrew-managed CLIs. Then compare that local state against repository pins and authoritative latest-version sources. If a managed tool is stale and version updates are in scope, update it first, then update any matching repository pins, `justfile` install recipes, bootstrap scripts, docs, and GitHub Actions workflow versions.

### 5. Cross-Language Coordination

When tooling changes alter Rust or Python validation behavior, identify the affected language surface and call out whether `rust-review-orchestrator` or `python-review-orchestrator` should also run. Do not duplicate their source-code review inside this skill.

## Fix Loop

For each applicable tooling surface:

1. Read the relevant reference file.
2. Inspect changed files and nearby command owners.
3. Implement minimal fixes for real tooling drift, safety, or validation issues.
4. Run the focused validator for the surface when available.
5. If validation fails, fix and rerun the same validator before moving on.
6. Record changed files and commands for the final summary.

If a validator needs network, installation, or other approval, use the strongest read-only/local check available and document the remaining verification.

## Final Summary

End with a concise summary that helps the maintainer review unstaged changes by file. Include:

- each file changed and why
- tooling surfaces reviewed
- validators run and their results
- version checks performed and whether they were live or local-only
- managed tool updates performed, before/after versions, and `justfile` or GitHub Actions pins updated
- language orchestrators recommended or run, if any
- anything intentionally deferred or not run
- confirmation that no git state mutations were performed, if true

Lead with unresolved tooling risks if any remain.
