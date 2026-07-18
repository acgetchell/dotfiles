---
name: python-review-orchestrator
description: "Coordinate multi-pass Python reviews by selecting focused skills for notebooks, CLI and boundary behavior, scientific code, support tooling, and tests. Use for changed, staged, PR, release-readiness, repository-wide, or fix-all Python work spanning multiple concerns. Use a focused Python skill directly for single-concern reviews."
---

# python-review-orchestrator

Coordinate focused Python review skills without copying their content. This skill is an execution plan: load each selected named skill file, apply selected skills in logical pass groups, fix actionable issues, validate the touched surface for that group, and only then continue to the next group.

The intent is to replace a maintainer manually running the relevant Python, notebook, and scientific review passes one by one. Do not collapse notebook, boundary, scientific, support-tooling, validation, and synthesis concerns into one blended review and report it as orchestrated work.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Use read-only git commands to discover scope when needed: `git --no-pager status --short`, `git --no-pager diff --stat`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
- Respect repository-local agent instructions before editing. If the repository requires reading development docs before changes, read them first.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for "repo", "whole repo", "entire repo", "baseline audit", or equivalent.
- When invoked by `repo-review` with a branch-scope file list or diff, honor that provided scope instead of rediscovering a narrower staged or worktree-only scope.
- When the user says "fix all", implement actionable findings as you go. Do not merely collect them for later unless the fix is blocked or unsafe.
- Do not run blanket full-CI validators by default. Select focused validators from changed and touched files. Run full CI only when repository rules require it for the touched surface or when changes cross broad Python behavior.

## Review Trace

When invoked by `repo-review`, begin with a handoff receipt that names:

- the parent branch scope and Python-owned file list or file count handed off
- selected Python skill groups and why they apply
- skipped Python skill groups when a maintainer might reasonably expect them
- routing reference files that will be loaded

For every selected group, announce the group and focused skills before loading the first skill. After loading each focused skill or reference file, keep its name in the running trace for the final summary. This trace is required evidence that the orchestrator ran the selected Python skills rather than only summarizing their names.

Evidence is grouped by pass, not by memory. A group is complete only when the final summary can name the group status (`selected` or `skipped`), the focused skill files loaded for that group, the changed files inspected, the findings or explicit no-finding result, fixes applied, and the focused validator run for that group. Loading skill files, remembering prior context, or running full CI does not by itself count as applying a group.

When invoked by `repo-review`, provide table-ready evidence for the parent `Review Evidence` table: selected groups, focused skill files loaded, reference files loaded, validators run, and any skipped groups that might otherwise look missing.

## Required Skill Loading

Load every selected skill's `SKILL.md` completely and follow its directly relevant references. Load skills at the start of their logical group, not before earlier groups have findings, fixes, and validator evidence. Use the [Per-Group Fix Loop](#per-group-fix-loop) as the single execution procedure.

## Scope Routing

Read [`references/check-routing.md`](references/check-routing.md) after identifying changed files. Use it to choose:

- which skill groups apply
- which focused validators to run after each group
- when final validation should escalate from focused commands to the repository's full-CI validator

If changed files do not match the table cleanly, choose the smallest validator that covers the risk and state the assumption in the final summary.

## Skill Groups

Run groups in this order when they apply. Within each group, load and apply each selected skill in the order listed.

### 1. Notebook/Reproducibility Pass

Use when `.ipynb` files, notebook execution helpers, notebook dependency groups, rendered outputs, or notebook CI paths changed.

- `jupyter-notebook-review`

This skill is the notebook front door. After it runs, select additional Python skills below when notebook code contains substantial reusable, scientific, CLI, support-tooling, or test behavior.

### 2. Boundary/Application Pass

Use for CLI/application behavior, parsers, file I/O, stdout/stderr contracts, privacy-sensitive output, date/time handling, config loading, raw data boundaries, typed models, or invalid-state prevention.

- `python-cli-review`
- `python-parse-dont-validate` when raw dicts, config, environment variables, subprocess output, JSON/CSV/TOML/YAML, paths, optionals, or primitive values carry invariants

### 3. Scientific/Data Pass

Use for numerical, geometric, statistical, dataframe, fixture-generation, scientific reproducibility, Rust-interoperability, NumPy/SciPy, or Hypothesis-over-numerical-input changes.

- `python-scientific-review`

### 4. Support Tooling Pass

Use for changelog generators, release helpers, benchmark runners, CI scripts, fixture utilities, diagnostic CLIs, subprocess wrappers around `cargo`/`git`/`gh`, generated artifact preparation, or Rust-crate development tooling.

- `python-support-scripts`

### 5. Validation/Test Pass

Use for tests, fixtures, coverage gaps, pytest ergonomics, CLI output capture, malformed-input coverage, notebook checker tests, and error-path behavior.

- `python-test-quality`

### 6. Final Synthesis Pass

Use this pass after all selected skills and validators have run.

This pass reconciles findings from earlier groups, removes duplicates, checks severity, and decides whether remaining issues are blockers, follow-ups, or acceptable residual risk. Do not load an extra broad Python skill unless one of the focused skills above actually applies to the remaining issue.

## Per-Group Fix Loop

For each selected group:

1. Announce the group and selected skills briefly.
2. Load every selected focused skill file for that group, plus directly relevant references.
3. Inspect only relevant changed files and nearby boundary owners unless whole-repo mode is active.
4. Apply the selected skills as one logical group, keeping findings tied to the group and file references.
5. Implement minimal fixes for real findings.
6. Run the focused validator from `references/check-routing.md` for the group.
7. Fix validator failures before continuing.
8. Record what changed per file and the group outcome for the final summary.

Do not report a Python orchestrator run as complete if the work was performed as one undifferentiated review across multiple groups. In that case, label it as preliminary context and rerun the applicable grouped passes.

If a validator is expensive, blocked, or needs approval, use the repository's focused cheaper validator while iterating, then run the strongest relevant validator available before final handoff.

## Final Summary

End with a concise summary that helps the maintainer review unstaged changes by file. Include:

- each file changed and why
- which skill groups ran
- focused skill files and reference files actually loaded
- table-ready evidence for `repo-review` when invoked by the meta-orchestrator
- validators run and their results
- issues fixed while moving between skills
- anything intentionally deferred or not run
- confirmation that no git state mutations were performed, if true

Do not bury important risk in a generic "all good" closing. If unresolved issues remain, lead with them.
