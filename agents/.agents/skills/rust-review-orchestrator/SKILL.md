---
name: rust-review-orchestrator
description: "Coordinate multi-pass Rust reviews by selecting focused skills for APIs, invariants and errors, scientific correctness, implementation, tests, Cargo, and final synthesis. Use for changed, staged, PR, release-readiness, repository-wide, or fix-all Rust work spanning multiple concerns. Use a focused Rust skill directly for single-concern reviews."
---

# rust-review-orchestrator

Coordinate focused Rust review skills without copying their content. This skill is an execution plan: load each selected named skill file, apply selected skills in logical pass groups, fix actionable issues, validate the touched surface for that group, and only then continue to the next group.

The intent is to replace a maintainer manually running the relevant Rust review passes one by one. Do not collapse API, invariant, scientific correctness, implementation, validation, and synthesis concerns into one blended review and report it as orchestrated work.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Use read-only git commands to discover scope when needed: `git --no-pager status --short`, `git --no-pager diff --stat`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
- Respect repository-local agent instructions before editing. If the repository requires reading development docs before changes, read them first.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for "repo", "whole repo", "entire repo", "baseline audit", or equivalent.
- When invoked by `repo-review` with a branch-scope file list or diff, honor that provided scope instead of rediscovering a narrower staged or worktree-only scope.
- When the user says "fix all", implement actionable findings as you go. Do not merely collect them for later unless the fix is blocked or unsafe.
- Do not run blanket full-CI validators by default. Select focused validators from changed and touched files. Run full CI only when repository rules require it for the touched surface or when changes cross broad core Rust behavior.

## Review Trace

When invoked by `repo-review`, begin with a handoff receipt that names:

- the parent branch scope and Rust-owned file list or file count handed off
- selected Rust skill groups and why they apply
- skipped Rust skill groups when a maintainer might reasonably expect them
- routing or crate-specific reference files that will be loaded

For every selected group, announce the group and focused skills before loading the first skill. After loading each focused skill or reference file, keep its name in the running trace for the final summary. This trace is required evidence that the orchestrator ran the selected Rust skills rather than only summarizing their names.

Evidence is grouped by pass, not by memory. A group is complete only when the final summary can name the group status (`selected` or `skipped`), the focused skill files loaded for that group, the changed files inspected, the findings or explicit no-finding result, fixes applied, and the focused validator run for that group. Loading skill files, remembering prior context, or running full CI does not by itself count as applying a group.

When invoked by `repo-review`, provide table-ready evidence for the parent `Review Evidence` table: selected groups, focused skill files loaded, reference files loaded, validators run, and any skipped groups that might otherwise look missing.

## Required Skill Loading

Load every selected skill's `SKILL.md` completely and follow its directly relevant references. Load skills at the start of their logical group, not before earlier groups have findings, fixes, and validator evidence. Use the [Per-Group Fix Loop](#per-group-fix-loop) as the single execution procedure.

## Scope Routing

Read [`references/check-routing.md`](references/check-routing.md) after identifying changed files. Use it to choose:

- which skill groups apply
- which focused validators to run after each group
- when final validation should escalate from focused commands to the repository's full-CI validator

If the repository matches a crate-specific reference, read that one after the general routing matrix:

- [`references/delaunay.md`](references/delaunay.md) for `delaunay` or closely related computational-geometry review-and-fix work.
- [`references/la-stack.md`](references/la-stack.md) for `la-stack` or closely related linear-algebra review-and-fix work.

If changed files do not match the table cleanly, choose the smallest validator that covers the risk and state the assumption in the final summary.

## Skill Groups

Run groups in this order when they apply. Within each group, load and apply each selected skill in the order listed.

### 1. Surface/API Pass

Use for public API changes, doc-comment changes, trait bounds, re-exports, builders, fluent workflows, examples, doctests, and semver-sensitive surface changes.

- `rust-api-docs`
- `rust-prelude-exports`
- `rust-fluent-api-design`
- `rust-trait-bounds`
- `rust-cli-design` when CLI surfaces, binary packaging, clap parsing, or command examples changed

### 2. Invariant/Error Pass

Use for constructors, validation boundaries, mutation APIs, snapshots/views, owned caches, typed errors, rollback, parse-don't-validate issues, or invalid-state prevention.

- `rust-parse-dont-validate`
- `rust-error-variants`
- `rust-borrowed-view-audit`
- `rust-concurrency-async` when async, threads, locks, channels, atomics, cancellation, or Send/Sync boundaries changed

### 3. Scientific Correctness Pass

Use when scientific or numerical behavior is in scope: mathematical models, formulas, predicates, solvers, exact or approximate arithmetic, tolerances, error bounds, stochastic methods, scientific fixtures, reproducibility, or the validity of scientific benchmark inputs and claims.

- `rust-scientific-correctness`

This pass establishes that the code answers the stated scientific question before implementation cleanup or optimization. If a later pass changes formulas, arithmetic order, tolerances, precision or fallback behavior, RNG semantics, or scientific fixtures, rerun the affected scientific checks before closing Validation/Test.

### 4. Implementation Pass

Use for Rust implementation edits, simplification, iterator/control-flow choices, naming/import hygiene, allocation behavior, and invariant-preserving performance.

- `rust-style-hygiene`
- `rust-iter-control-flow`
- `rust-simplification-review`
- `rust-invariant-performance` when changed code is hot, allocation-sensitive, numerical/geometric, validation-heavy, or performance-adjacent

### 5. Validation/Test Pass

Use for tests, doctests, proptests, integration tests, benchmark fixtures, examples that double as public samples, and Cargo or feature changes.

- `rust-test-quality`
- `rust-cargo-hygiene` when manifests, lockfiles, features, lints, MSRV, package metadata, or Cargo workflows changed

### 6. Final Synthesis Pass

Use for broad Rust changes, invariant-heavy code, scientific or numerical algorithms, topology, mutation workflows, or whole-repo review requests.

- `rust-production-review`

This pass reconciles findings from earlier groups, including scientific-correctness evidence when selected, removes duplicates, checks severity, and decides whether remaining issues are blockers, follow-ups, or acceptable residual risk.

## Per-Group Fix Loop

For each selected group:

1. Announce the group and selected skills briefly.
2. Load every selected focused skill file for that group, plus directly relevant references.
3. Inspect only relevant changed files and nearby invariant owners unless whole-repo mode is active.
4. Apply the selected skills as one logical group, keeping findings tied to the group and file references.
5. Implement minimal fixes for real findings.
6. Run the focused validator from `references/check-routing.md` for the group.
7. Fix validator failures before continuing.
8. Record what changed per file and the group outcome for the final summary.

Do not report a Rust orchestrator run as complete if the work was performed as one undifferentiated review across multiple groups. In that case, label it as preliminary context and rerun the applicable grouped passes.

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
