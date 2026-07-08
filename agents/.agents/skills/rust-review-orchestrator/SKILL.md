---
name: rust-review-orchestrator
description: "Coordinate a structured Rust code-review-and-fix workflow by loading named Rust skills in sequence, grouping them by API, invariant, implementation, validation, and synthesis concerns, applying fixes pass by pass, and choosing focused validators from changed files. Use when the user asks for a Rust review suite, repo-wide Rust review, whole-repo baseline audit, staged/changed Rust review, or 'fix all' across multiple Rust review skills. Also use when the user wants focused Rust skills applied in order with fixes and validation before moving to the next skill. Do not use when there is no Rust code, Rust API docs, Cargo/test/example/benchmark surface, or Rust workflow impact; for single-purpose reviews that name only one focused Rust skill; or for requests to commit, stage, push, tag, or otherwise mutate git state."
---

# rust-review-orchestrator

Coordinate focused Rust review skills without copying their content. This skill is an execution plan: load each selected named skill file, apply it to the current scope, fix actionable issues, validate the touched surface, and only then continue to the next selected skill.

## Ground Rules

- Do not perform git state mutations. Do not stage, commit, push, tag, checkout, reset, or stash unless the user explicitly asks in the current turn.
- Use read-only git commands to discover scope when needed: `git --no-pager status --short`, `git --no-pager diff --stat`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
- Respect repository-local agent instructions before editing. If the repository requires reading development docs before changes, read them first.
- Prefer changed-file review by default. Use whole-repo baseline mode only when the user explicitly asks for "repo", "whole repo", "entire repo", "baseline audit", or equivalent.
- When the user says "fix all", implement actionable findings as you go. Do not merely collect them for later unless the fix is blocked or unsafe.
- Do not run blanket full-CI validators by default. Select focused validators from changed and touched files. Run full CI only when repository rules require it for the touched surface or when changes cross broad core Rust behavior.

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

### 3. Implementation Pass

Use for Rust implementation edits, simplification, iterator/control-flow choices, naming/import hygiene, allocation behavior, and invariant-preserving performance.

- `rust-style-hygiene`
- `rust-iter-control-flow`
- `rust-simplification-review`
- `rust-invariant-performance` when changed code is hot, allocation-sensitive, numerical/geometric, validation-heavy, or performance-adjacent

### 4. Validation/Test Pass

Use for tests, doctests, proptests, integration tests, benchmark fixtures, examples that double as public samples, and Cargo or feature changes.

- `rust-test-quality`
- `rust-cargo-hygiene` when manifests, lockfiles, features, lints, MSRV, package metadata, or Cargo workflows changed

### 5. Final Synthesis Pass

Use for broad Rust changes, invariant-heavy code, scientific or numerical algorithms, topology, mutation workflows, or whole-repo review requests.

- `rust-production-review`

This pass reconciles findings from earlier groups, removes duplicates, checks severity, and decides whether remaining issues are blockers, follow-ups, or acceptable residual risk.

## Per-Group Fix Loop

For each selected group:

1. Announce the group and selected skills briefly.
2. Load the next selected skill file.
3. Inspect only relevant changed files and nearby invariant owners unless whole-repo mode is active.
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
