---
name: rust-review-orchestrator
description: "Coordinate multi-pass Rust reviews by selecting individual skills for build portability and Cargo, public surfaces, invariant state and errors, scientific correctness, concurrency, implementation, tests, and final synthesis. Use for changed, staged, PR, release-readiness, repository-wide, or fix-all Rust work spanning multiple concerns; use one focused Rust skill directly for a single concern."
---

# Rust Review Orchestrator

Coordinate focused Rust review skills without copying their content. Select skills individually, run them in logical groups, validate each affected contract, and finish with lean production synthesis.

Do not treat selecting a group as permission to load every skill listed in it. Load only skills whose trigger matches the scoped change and record explicit skips when a maintainer could reasonably expect a pass.

## Ground Rules

- Do not stage, commit, push, tag, checkout, reset, or stash unless explicitly requested in the current turn.
- Use read-only git commands to discover scope.
- Respect repository-local instructions and documented MSRV, edition, feature, target, safety, and validation policy.
- Prefer changed-file review. Use whole-repository baseline mode only when explicitly requested.
- Honor a parent `repo-review` file list or diff instead of rediscovering a narrower scope.
- When fixes are requested, implement verified findings within each selected skill before continuing.
- Select focused validators; do not run full CI merely because orchestration is ending.
- Maintain one cross-skill validation ledger keyed by source/build state,
  toolchain, target, features, instrumentation, and exact test selection. Reuse
  still-valid evidence instead of replaying it through broader recipes.

## Review Trace

At the start, record the scope, changed Rust-owned files, selected and skipped individual skills with reasons, repository references to load, focused validators, and the initial validation ledger.

For every selected skill:

- announce its group and name before loading it
- load its `SKILL.md` completely and only directly relevant references
- record files inspected, findings or explicit no-finding result, fixes, and validator evidence

When invoked by `repo-review`, provide table-ready evidence naming selected groups, exact skills and references loaded, validators, fixes, and meaningful skips.

## Scope Routing

Read [`references/check-routing.md`](references/check-routing.md) after identifying changed files. Use its individual-skill matrix and validation guidance.

Load only the matching repository reference after general routing:

- [`references/delaunay.md`](references/delaunay.md) for `delaunay` or closely related computational geometry.
- [`references/la-stack.md`](references/la-stack.md) for `la-stack` or closely related fixed-size linear algebra.

If the scope does not match cleanly, choose the smallest set of skills that covers the risk and state the assumption.

## Skill Groups

Run selected skills in this order. Conditions below are independent within each group.

### 1. Build, Feature, and Cargo Contract

- Use `rust-build-portability` for source-level `cfg`, feature combinations, MSRV compilation, targets, cross-compilation, build scripts, generated code, proc macros, `no_std`, WASM, FFI/native linking, or downstream-consumer portability.
- Use `rust-cargo-hygiene` for manifests, lockfile policy, dependency declarations, feature definitions, workspace inheritance, lint configuration, package metadata, MSRV/edition declarations, publishing, or release readiness.

Select both only when manifest decisions and demonstrated configuration behavior change together. Route recipes, CI jobs, caches, runner setup, and command wiring to `project-tooling-review`.

### 2. Public Surface and Usage

- Use `rust-api-docs` for new or changed public items whose documented contract must be assessed, public documentation edits, required rustdoc sections, examples as documentation, intra-doc links, or docs.rs presentation.
- Use `rust-prelude-exports` only for preludes, `pub use`, visibility, feature-gated re-exports, or downstream import ergonomics.
- Use `rust-fluent-api-design` only for staged workflows, builders, proposals, transactions, guards, chaining, or duplicate fluent/non-fluent surfaces.
- Use `rust-trait-bounds` only for generic constraints, associated types, HRTBs, `impl Trait`, callable bounds, or downstream generic diagnostics.
- Use `rust-cli-design` only for CLI packaging, argument parsing, process behavior, command examples, or optional CLI features.

A public item does not automatically select all five skills. Choose the specific contract affected.

### 3. Invariants, State, Errors, and Views

- Use `rust-invariant-state-transitions` for coordinated mutation, state machines, caches/indexes, topology or graph edits, transactions, rollback, failure atomicity, inverse operations, or operation sequences.
- Use `rust-parse-dont-validate` for raw-to-domain boundaries, smart constructors, refined types, deserialization, setters, or invalid stored states.
- Use `rust-error-variants` for error enums, typed categories, conversions, propagation, diagnostic fields, or public failure compatibility.
- Use `rust-borrowed-view-audit` for snapshots, owned caches, cloned canonical data, handles, provenance, borrowed views, or lifetime-bound transaction/view shapes.

Select only the ownership lenses present. A constructor does not require borrowed-view analysis unless borrowing, snapshots, caches, or provenance are involved.

### 4. Scientific Correctness

- Use `rust-scientific-correctness` when mathematical models, formulas, numerical behavior, geometry/topology, exact or approximate arithmetic, tolerances, error bounds, stochastic methods, scientific fixtures, reproducibility, or scientific benchmark claims change.

Establish scientific validity before optimizing. Rerun affected scientific evidence if later edits change formulas, arithmetic order, precision, tolerances, fallbacks, RNG semantics, fixtures, or claims.

### 5. Concurrency and Async

- Use `rust-concurrency-async` only for async, threads, locks, channels, atomics, task lifetime, Send/Sync, blocking, cancellation, structured concurrency, or mutation observed across scheduling boundaries.

Keep purely synchronous state atomicity in `rust-invariant-state-transitions`.

### 6. Implementation Lenses

- Use `rust-style-hygiene` only for naming, import organization, and path clarity.
- Use `rust-iter-control-flow` only for material iterator, closure, loop, pattern-matching, exhaustiveness, or allocation-through-control-flow questions.
- Use `rust-simplification-review` only when deletion, deduplication, redundant helpers/tests, public-surface reduction, or substantial simplification is plausible or requested.
- Use `rust-invariant-performance` only for demonstrated or plausible hot paths, allocation/data movement, complexity, benchmark-guided optimization, or performance-sensitive invariants.

Do not load implementation lenses merely because a Rust source file changed.

### 7. Validation and Test Quality

- Use `rust-test-quality` when tests, doctests as executable evidence, proptests, fuzz targets, compile-fail tests, examples as tests, concurrency models, sanitizer/Miri evidence, or production behavior requiring regression coverage changes.

This pass owns semantic test strength. Build portability owns which configurations must compile; Cargo hygiene and project tooling own manifest and workflow mechanics.

### 8. Final Synthesis

Always load `rust-production-review` after selected specialist skills. Hand it prior findings, fixes, validators, and explicit skips. It must use orchestrated mode, avoid the standalone checklist, reconcile contradictions, assess residual dependency/performance/simplification/unsafe/integration risk, deduplicate findings, and issue the final severity and readiness verdict.

## Per-Skill Fix Loop

For each selected skill:

1. Announce the group and skill.
2. Load the complete skill and directly relevant references.
3. Inspect scoped files and nearby owners of the affected contract.
4. Record findings or an explicit no-finding result.
5. Apply the smallest safe correction when fixes were requested.
6. Run the focused validator selected from routing guidance only when equivalent evidence is not already valid in the shared ledger.
7. Resolve caused failures or document a genuine blocker.
8. Record changed files or read-only status and the skill outcome.

If prior work was an undifferentiated review, treat it as preliminary context and rerun applicable individual skills before claiming orchestrator completion.

## Final Summary

Lead with unresolved blockers. Include changed files, every selected and meaningful skipped skill, exact skill/reference files loaded, the non-overlapping validation ledger and results, fixed findings, final synthesis classification, deferred work, and confirmation that no git state mutation occurred when true.
