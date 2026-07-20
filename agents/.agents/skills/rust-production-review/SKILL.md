---
name: rust-production-review
description: "Review Rust for production readiness as either a directly requested standalone broad or release-readiness audit, or final synthesis after focused Rust reviews. In standalone mode, cover cross-cutting correctness, API, safety, performance, and maintainability risks. In orchestrated mode, reconcile prior evidence and assess only residual dependency, unsafe, performance, simplification, validation, and integration risk without repeating specialist passes."
---

# Rust Production Review

Review Rust as long-lived production software whose correctness, soundness, portability, and public contracts matter. Follow the repository's declared edition, MSRV, feature/target support, safety policy, and semver promises.

Prioritize observable defects, invariant corruption, unsoundness, scientifically invalid behavior, and release risk over stylistic churn.

## Select the Mode

### Orchestrated final synthesis

Use this mode when `rust-review-orchestrator` invokes the skill after focused passes.

- Consume prior scope, selected skills, explicit skips, findings, fixes, and validators.
- Do not load the standalone checklist or rerun completed specialists.
- Revisit an earlier concern only when later edits invalidate its evidence or the handoff exposes a contradiction.
- Focus on residual dependency, unsafe, performance, simplification, validation, and cross-contract integration risk.
- Deduplicate findings and issue the final severity and readiness verdict.

### Standalone broad review

Use this mode only when invoked directly for a broad Rust, release-readiness, or whole-repository audit. Read [references/standalone-review.md](references/standalone-review.md) completely, then apply the common residual workflow below.

## Ground Rules

- Read repository-local guidance before reviewing or editing.
- Default to changed Rust files and nearby contract owners.
- Use whole-repository baseline mode only when explicitly requested.
- Keep diagnostic reviews read-only; make the smallest safe fixes when authorized.
- Do not mutate git state without explicit permission.
- Verify current compiler, Cargo, dependency, and target behavior from authoritative sources when version sensitivity matters.
- Treat compilation, tests, model checking, dynamic analysis, independent scientific evidence, and reasoning as complementary.

## Scope and Evidence

Record:

- mode, files, packages, features, and targets in scope
- edition, MSRV, safety policy, semver promise, and supported configurations
- prior specialist evidence in orchestrated mode
- dependency changes, unsafe boundaries, performance claims, and available validators
- user-owned or unrelated work that must remain untouched

Provide table-ready evidence when invoked by an orchestrator.

## Residual Workflow

### 1. Reconcile dependencies and integration

Check that dependency APIs and enabled features match resolved versions, public dependency exposure is intentional, migrations account for semantic behavior, and removals eliminate transitive assumptions. Route manifest/publishing policy to `rust-cargo-hygiene` and workflow mechanics to `project-tooling-review`.

For a migration, separate source changes, behavior changes, feature/MSRV effects, target effects, public API effects, and validation. Prefer one dependency boundary at a time when practical.

### 2. Reconcile unsafe and trust boundaries

Identify `unsafe`, FFI, raw-pointer, unchecked-index, uninitialized-memory, layout, and external-invariant boundaries not already covered. Require a local safety argument, minimal unsafe scope, documented caller obligations, and evidence that safe code cannot violate the assumptions.

Do not introduce unsafe for performance without representative measurement and a proof burden proportionate to the new trusted surface. When a project forbids unsafe, verify enforcement rather than performing a speculative unsafe audit.

### 3. Review residual performance and simplification

Check for accidental complexity, hot-path allocation or cloning, stale caches, needless public surface, redundant helpers/tests, and custom machinery superseded by an established facility. Reuse `rust-invariant-performance` and `rust-simplification-review` evidence when selected; do not repeat them.

Require measurement for non-obvious performance changes and proof before deletion. Preserve behavior, invariants, errors, feature coverage, diagnostics, and regression value.

### 4. Reconcile validation and release risk

Map every material behavior, API, feature, target, scientific, or state-transition change to evidence. Reuse valid specialist results and add only missing integration validators. Do not infer full support from one toolchain, target, feature set, test suite, or benchmark.

If a late fix affects an earlier contract, return it to the owning skill and refresh its evidence before final classification.

## Severity

- **P0 — Release blocker:** unsoundness, undefined behavior through FFI/unsafe, build failure on a supported configuration, invariant corruption, data race, scientifically invalid result, or tests unable to detect critical failure.
- **P1 — Must fix:** reachable wrong behavior, failure-atomicity defect, recoverable public panic, serious compatibility or portability break, lost typed failure, or untested critical path.
- **P2 — High value:** meaningful API, maintainability, performance, diagnostic, or test improvement that need not block a preserved release.
- **P3 — Optional:** low-risk cleanup; keep this category small.

For every finding, show file/line evidence, the trigger and observable consequence, the violated contract, the smallest credible correction, and required validation. Distinguish confirmed defects from unavailable-evidence hypotheses.

## Final Report

Lead with unresolved P0/P1 findings. Include the readiness verdict, findings by severity, prior specialist outcomes and resolved contradictions, dependency/unsafe/deletion candidates, validators and exact results, supported configurations actually demonstrated, deferred work and residual risk, files changed, and confirmation that no git state mutation occurred when true.
