---
name: repo-review
description: "Coordinate a branch-scoped repo review-and-fix workflow by routing current-branch changes to rust-review-orchestrator, python-review-orchestrator, and project-tooling-review as needed, then synthesizing cross-surface validation. Use when the user asks for branch, PR, repo-wide, staged, changed, or mixed Rust/Python/tooling review; repository review suites; or fix-all work across code and tooling. Do not use for single-surface requests that clearly name only Rust, Python, notebooks, Justfile, GitHub Actions, or tool-version review; use the focused orchestrator directly. Do not use for commit, stage, push, tag, checkout, reset, stash, or other git-state mutations."
---

# repo-review

Route mixed repository review work to the focused orchestrators. This skill establishes the current branch as the review scope, decides which review surfaces apply, loads the selected orchestrator skills, lets each one run its own fix loop, and then reconciles cross-surface validation.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Prefer branch review by default: compare the current branch to its PR/default-branch base, and include staged, unstaged, and untracked work on top of that branch.
- Use staged-only, changed-file-only, or whole-repo baseline scope only when the user explicitly asks for that narrower or broader scope.
- If the request clearly targets one surface, use the focused orchestrator directly instead of this meta-skill.
- When the user asks to fix issues, implement actionable findings as each selected orchestrator discovers them. Do not merely collect findings unless the fix is blocked or unsafe.
- Keep this skill thin. Do not duplicate the detailed review rules from Rust, Python, or tooling skills; load those skills and follow them.

## Required Skill Loading

This meta-orchestrator must actually load every selected orchestrator's `SKILL.md` completely before applying it.

After establishing branch scope:

1. Read [`references/check-routing.md`](references/check-routing.md).
2. Select the smallest set of orchestrators that covers the changed surfaces:
   - `project-tooling-review`
   - `rust-review-orchestrator`
   - `python-review-orchestrator`
3. For each selected orchestrator, open and read its `SKILL.md` completely.
4. Follow that orchestrator's directly referenced files when they apply.
5. Give the orchestrator the established branch file list and diff as its scope. This branch-scope handoff overrides a focused orchestrator's changed-file default for the current meta-review.
6. Let the orchestrator run its own pass order, fix loop, and focused validation before moving to the next selected orchestrator.
7. Record validators, changes, unresolved risks, and any cross-surface handoffs for the final summary.

## Review Order

Use this order unless the changed files make a different order clearly safer:

1. Run `project-tooling-review` first when tool versions, `justfile`, workflows, or command docs changed enough to affect which validators should run.
2. Run `rust-review-orchestrator` when Rust source, tests, examples, benches, Cargo metadata, Rust docs, or Rust-facing workflows changed.
3. Run `python-review-orchestrator` when Python source, notebooks, pytest fixtures, Python config, lockfiles, or Python-facing workflows changed.
4. Revisit tooling only when language fixes require recipe, workflow, lockfile, or command-doc updates.
5. Synthesize final validation across all surfaces, preferring the strongest focused validator already justified by the touched files.

## Cross-Surface Handling

Treat build and validation files as shared ownership:

- `Cargo.toml`, `Cargo.lock`, `pyproject.toml`, `uv.lock`, and toolchain files can require both language and tooling review.
- `justfile` and `.github/workflows/**` belong to project tooling, but route to Rust or Python too when they change the language checks that run.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `docs/**` belong to project tooling when they describe commands, CI, tool versions, or maintainer workflow. Route to language orchestrators when they document public API, examples, notebooks, or behavior.
- Generated files, fixtures, benchmarks, and support scripts should be reviewed by the language orchestrator that owns their behavior plus project tooling when command wiring changed.

## Final Summary

End with a concise summary that helps the maintainer review unstaged changes by surface. Include:

- orchestrators selected and why
- files changed and what was fixed
- validators run and their results
- cross-surface risks resolved or deferred
- anything intentionally not run
- confirmation that no git state mutations were performed, if true

Lead with unresolved blockers if any remain.
