---
name: python-review-orchestrator
description: "Coordinate a structured Python code-review-and-fix workflow by loading named Python skills in sequence, grouping them by notebook, boundary, scientific, support-tooling, validation, and synthesis concerns, applying fixes pass by pass, and choosing focused validators from changed files. Use when the user asks for a Python review suite, repo-wide Python review, whole-repo baseline audit, staged/changed Python review, notebook-and-script cleanup, or 'fix all' across multiple Python review skills. Also use when the user wants focused Python skills applied in order with fixes and validation before moving to the next skill. Do not use when there is no Python code, notebook, pytest, Python config, data fixture, or Python workflow impact; for single-purpose reviews that name only one focused Python skill; or for requests to commit, stage, push, tag, or otherwise mutate git state."
---

# python-review-orchestrator

Coordinate focused Python review skills without copying their content. This skill is an execution plan: load each selected named skill file, apply it to the current scope, fix actionable issues, validate the touched surface, and only then continue to the next selected skill.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Use read-only git commands to discover scope when needed: `git --no-pager status --short`, `git --no-pager diff --stat`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
- Respect repository-local agent instructions before editing. If the repository requires reading development docs before changes, read them first.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for "repo", "whole repo", "entire repo", "baseline audit", or equivalent.
- When the user says "fix all", implement actionable findings as you go. Do not merely collect them for later unless the fix is blocked or unsafe.
- Do not run blanket full-CI validators by default. Select focused validators from changed and touched files. Run full CI only when repository rules require it for the touched surface or when changes cross broad Python behavior.

## Required Skill Loading

This orchestrator must actually load the named skill files it selects. Do not summarize their names from memory.

For each selected skill:

1. Open and read that skill's `SKILL.md` completely.
2. Follow any directly referenced, task-relevant reference files from that skill.
3. Apply that skill to the current changed-file scope.
4. Fix actionable issues before moving on.
5. Run the focused validator for files touched by that skill's fixes.
6. If validation fails, fix and rerun the same validator before loading the next selected skill.

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
2. Load the next selected skill file.
3. Inspect only relevant changed files and nearby boundary owners unless whole-repo mode is active.
4. Implement minimal fixes for real findings.
5. Run the focused validator from `references/check-routing.md`.
6. Fix validator failures before continuing.
7. Record what changed per file for the final summary.

If a validator is expensive, blocked, or needs approval, use the repository's focused cheaper validator while iterating, then run the strongest relevant validator available before final handoff.

## Final Summary

End with a concise summary that helps the maintainer review unstaged changes by file. Include:

- each file changed and why
- which skill groups ran
- validators run and their results
- issues fixed while moving between skills
- anything intentionally deferred or not run
- confirmation that no git state mutations were performed, if true

Do not bury important risk in a generic "all good" closing. If unresolved issues remain, lead with them.
