---
name: repo-review
description: "Coordinate a repo review-and-fix workflow by routing branch changes or explicit whole-repo baseline checkpoints to rust-review-orchestrator, python-review-orchestrator, project-tooling-review, and docs-review-orchestrator as needed, then synthesizing cross-surface validation. Use when the user asks for branch, PR, repo-wide, staged, changed, clean-repo checkpoint, full repo review as-is, whole-repo baseline, or mixed Rust/Python/tooling/documentation review; repository review suites; release-readiness reviews; or fix-all work across code, tooling, and documentation. Do not use for single-surface requests that clearly name only Rust, Python, notebooks, documentation, citations, Justfile, GitHub Actions, or tool-version review; use the focused skill directly. Do not use for commit, stage, push, tag, checkout, reset, stash, or other git-state mutations."
---

# repo-review

Route mixed repository review work to the focused orchestrators. This skill establishes either the current branch or an explicit whole-repo baseline as the review scope, decides which review surfaces apply, loads the selected orchestrator skills, lets each one run its grouped fix loop, and then reconciles cross-surface validation.

The intent is to replace the maintainer running the selected orchestrators manually. Do not substitute one blended whole-repo pass for child orchestrator runs with grouped evidence.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Prefer branch review by default: compare the current branch to its PR/default-branch base, and include staged, unstaged, and untracked work on top of that branch.
- Use staged-only, changed-file-only, or whole-repo baseline scope only when the user explicitly asks for that narrower or broader scope.
- In whole-repo baseline mode, review the repository as it exists now, even when the worktree is clean and no branch diff exists. Select orchestrators from tracked repository surfaces, not from changed files.
- In release-readiness mode, expand the documentation handoff to the scientific crate's complete tracked active documentation suite, including unchanged files; do not infer documentation completeness from the branch diff. Exclude `docs/archive/**` and equivalent designated archive trees unless explicitly requested.
- If the request clearly targets one surface, use the focused orchestrator directly instead of this meta-skill.
- When the user asks to fix issues, implement actionable findings as each selected orchestrator discovers them. Do not merely collect findings unless the fix is blocked or unsafe.
- Keep this skill thin. Do not duplicate the detailed review rules from Rust, Python, or tooling skills; load those skills and follow them.

## Review Trace

Make orchestration visible while working. Before running focused orchestrators, emit a compact dispatch note with:

- scope mode: branch, staged-only, changed-file-only, or whole-repo baseline; for branch mode include base and staged/unstaged/untracked state; for baseline mode include tracked-file inventory counts by surface
- selected orchestrators, each with one reason tied to changed files or, in baseline mode, repository surfaces present
- skipped orchestrators, each with one reason
- planned run order

Before each selected orchestrator starts, emit a handoff note naming the orchestrator and the scope being handed to it: branch file list/diff slice for branch review, explicit file list for staged or changed-file review, or repository inventory for whole-repo baseline review. After each orchestrator finishes, record the focused skill groups or tooling surfaces, skill files, reference files, fixes, and validators it actually used. Treat this trace as the user's audit trail that the child skill was really run, not as optional narration.

Each selected child orchestrator is a blocking grouped review. Prior context can inform it, but it is complete only when it supplies grouped evidence from its own pass order. If work was performed as a blended cross-surface review, report it as preliminary context and rerun the selected child orchestrators; do not mark them complete in the evidence table.

The final summary must include a Markdown table headed `Review Evidence` with these columns:

| Orchestrator | Status | Why selected or skipped | Scope handed off | Skills/references actually loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include one row for each of `project-tooling-review`, `rust-review-orchestrator`, `python-review-orchestrator`, and `docs-review-orchestrator`. Use `selected`, `skipped`, or `blocked` in the Status column. For selected orchestrators, do not leave the skills/references cell blank; name the loaded files, or write `none loaded` only with a reason.

## Required Skill Loading

This meta-orchestrator must actually load every selected orchestrator's `SKILL.md` completely before applying it.

After establishing review scope:

1. Read [`references/check-routing.md`](references/check-routing.md).
2. Select the smallest set of orchestrators that covers the requested scope:
   - `project-tooling-review`
   - `rust-review-orchestrator`
   - `python-review-orchestrator`
   - `docs-review-orchestrator`
3. Emit the review dispatch note from [Review Trace](#review-trace), including selected and skipped orchestrators.
4. For each selected orchestrator, open and read its `SKILL.md` completely.
5. Follow that orchestrator's directly referenced files when they apply.
6. Give the orchestrator the established file list, diff, or whole-repo inventory as its scope. This handoff overrides a focused orchestrator's changed-file default for the current meta-review.
7. Let the orchestrator run its own pass order, fix loop, and focused validation before moving to the next selected orchestrator.
8. Record validators, changes, unresolved risks, and any cross-surface handoffs for the final summary.

Do not flatten selected child orchestrators into a single review. The parent may coordinate scope and final synthesis, but Rust, Python, tooling, and documentation evidence must come from the applicable child orchestrator passes.

## Review Order

Use this order unless the requested scope makes a different order clearly safer:

1. Run `project-tooling-review` first when tool versions, `justfile`, workflows, or command docs changed enough to affect which validators should run, or when baseline inventory contains tooling surfaces.
2. Run `rust-review-orchestrator` when Rust source, tests, examples, benches, Cargo metadata, Rust docs, or Rust-facing workflows changed or are present in baseline scope.
3. Run `python-review-orchestrator` when Python source, notebooks, pytest fixtures, Python config, lockfiles, or Python-facing workflows changed or are present in baseline scope.
4. Run `docs-review-orchestrator` after the source-owning passes whenever release-readiness mode is active, or when coupled scientific-crate documentation, Rust API docs, release metadata, scientific claims, references, or publication/release process docs changed or are present in baseline scope.
5. Revisit tooling only when language or documentation fixes require recipe, workflow, lockfile, or command-doc updates.
6. Synthesize final validation across all surfaces, preferring the strongest focused validator already justified by the touched files.

## Cross-Surface Handling

Treat build and validation files as shared ownership:

- `Cargo.toml`, `Cargo.lock`, `pyproject.toml`, `uv.lock`, and toolchain files can require both language and tooling review.
- `justfile` and `.github/workflows/**` belong to project tooling, but route to Rust or Python too when they change the language checks that run.
- `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `docs/**` belong to project tooling when they describe commands, CI, tool versions, or maintainer workflow. Route to language orchestrators when they document public API, examples, notebooks, or behavior.
- Coupled crate docs, Rust API docs, release metadata, provenance, and scientific claims belong to `docs-review-orchestrator`, which routes them to the smallest applicable documentation skills.
- Generated files, fixtures, benchmarks, and support scripts should be reviewed by the language orchestrator that owns their behavior plus project tooling when command wiring changed.

## Final Summary

End with a concise summary that helps the maintainer review unstaged changes by surface. Include:

- the `Review Evidence` table described above
- orchestrators selected and skipped, with reasons
- focused skill groups, skill files, and reference files actually loaded by each selected orchestrator
- files changed and what was fixed
- validators run and their results
- cross-surface risks resolved or deferred
- anything intentionally not run
- confirmation that no git state mutations were performed, if true

Lead with unresolved blockers if any remain.
