---
name: project-tooling-review
description: "Review repository commands, CI, tool pins, and static-analysis policy; apply changes when maintenance or fixes are requested."
---

# project-tooling-review

Rust-orchestrator passes use the shared [execution-v1 contract](../rust-review-orchestrator/references/execution-v1.md).

Review repository commands, workflows, pins, and docs. Evaluate whether static
checks protect relevant policies, detect violations, and run on intended code.
Keep, add, adjust, or remove checks based on evidence and requested scope.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user has explicitly authorized that operation and scope.
- A currentness or "latest" review is read-only: report drift and recommended updates. Upgrade tools and reconcile pins only when updates or maintenance are requested, using the existing manager and the authorized scope.
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

For direct invocation without a parent scope and result contract, read
[`references/standalone-workflow.md`](references/standalone-workflow.md)
completely and follow its scope discovery, trace, fix, validation, and reporting
workflow.

## Scope Routing

Use the requested surface and scope to load only the references that apply:

- [`references/justfile.md`](references/justfile.md) for recipes, validator tiers, naming, and command docs.
- [`references/github-actions.md`](references/github-actions.md) for `.github/workflows/**`, Actions permissions/triggers/caches/matrices, CI use of `just`, and workflow validation.
- [`references/tool-versions.md`](references/tool-versions.md) for `Brewfile`, `uv`, `cargo install`, `rustup`, lockfiles, action versions, language toolchains, and version drift.
- [`references/static-analysis.md`](references/static-analysis.md) for Clippy/Semgrep selection, usefulness, retirement, suppressions, fixtures, and coverage, including policy audits without changed files.
- [`references/delaunay.md`](references/delaunay.md) in the `delaunay` repository for its Semgrep fixture harness, notebook execution policy, and generated-asset
  ownership.

If multiple surfaces changed, review them in this order:

1. Tool versions and installers, so commands use the intended tools.
2. `justfile` recipes and local command contracts.
3. Static-analysis policy, lint and rule effectiveness, fixtures, and scan scope.
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
selections, with an execution order. Check for avoidable late static failures
before expensive execution, preserving prerequisites and coalescing; see the
[Justfile example](references/justfile.md#fail-fast-dependency-order).
Fix canonical recipes; dispatched workers must not add out-of-scope checks or
reorder validator-owned commands.

Avoid redundant nested validation tiers. Reuse valid evidence where the required
contract permits it. Focused red/green tests during a fix may precede a required
final aggregate gate even when that gate repeats them. Run the required gate on
the final source state, record why coverage overlaps, and do not count repeated
checks as independent evidence. Composable recipes can reduce cost, but an
indivisible gate is not itself a defect or an approval blocker.

### 4. Cross-Language Coordination

When tooling changes alter Rust or Python validation behavior, identify the affected language surface and call out whether `rust-review-orchestrator` or `python-review-orchestrator` should also run. Do not duplicate their source-code review inside this skill.

For Python packaging, own tooling mechanics here. Route distribution contents,
package discovery, installed imports, entry points, extras, runtime/platform
matrices, and external-consumer behavior through `python-review-orchestrator`
to `python-build-portability`.

When command, release, or process changes affect a wider documentation suite, hand off navigation, cross-document consistency, generated-document ownership, and any applicable specialist documentation to `docs-review-orchestrator`. Keep command truth in this skill; do not absorb the broader documentation review here.
