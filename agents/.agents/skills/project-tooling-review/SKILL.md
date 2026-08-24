---
name: project-tooling-review
description: "Review and fix repository tooling: just recipes, GitHub Actions, CI command drift, repository-owned static analysis, tool versions, installers, linters, formatters, type checks, support scripts, and command documentation. Use for tooling workflow correctness and maintainer ergonomics; route application behavior to the appropriate language reviewer."
---

# project-tooling-review

Review the project command layer: the recipes, workflows, version pins, and docs that let maintainers run the right checks without remembering every underlying tool.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Do not install or uninstall unrelated tools unless the user explicitly asks. When the requested scope includes tool-version currentness, update drift, or "latest" tooling review, update stale tools through the repository's existing manager and reconcile tracked pins.
- Respect repository-local agent instructions before editing. If the repository documents development commands, read that guidance before changing recipes or workflows.
- Honor an exact scope supplied by a parent coordinator instead of rediscovering
  a narrower staged or worktree-only scope.

## Review-Graph Dispatch

When `review-graph` dispatches this skill as a review node in a worker or the
coordinator:

- honor its exact node scope, selection reasons, instructions, references,
  fingerprints, and authorization
- apply only `project-tooling-review`; do not create subagents or load another
  review skill
- keep audit and revalidation nodes read-only; edit only in an explicitly
  authorized fix node
- execute only the validation assigned to the node; report additional needs as
  catalog handoffs instead of broadening the dispatch
- return the exact Review Node Result required by the graph's node contract

For a direct tooling review outside `review-graph`, read
[`references/standalone-workflow.md`](references/standalone-workflow.md)
completely and follow its scope discovery, trace, fix, validation, and reporting
workflow.

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

### 4. Cross-Language Coordination

When tooling changes alter Rust or Python validation behavior, identify the affected language surface and call out whether `rust-review-orchestrator` or `python-review-orchestrator` should also run. Do not duplicate their source-code review inside this skill.

For Python packaging changes, own recipe, workflow, installer, validator, and tool-version mechanics here. Route wheel/sdist contents, package discovery, installed imports, entry points, extras, runtime/platform matrices, and external-consumer behavior through `python-review-orchestrator` to `python-build-portability`.

When command, release, or process changes affect a wider documentation suite, hand off navigation, cross-document consistency, generated-document ownership, and any applicable specialist documentation to `docs-review-orchestrator`. Keep command truth in this skill; do not absorb the broader documentation review here.
