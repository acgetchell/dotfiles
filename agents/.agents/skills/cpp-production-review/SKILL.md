---
name: cpp-production-review
description: "Review modern C++23 for production readiness as either a directly requested standalone broad or release-readiness audit, or final synthesis after focused C++ reviews. In standalone mode, cover cross-cutting production risks. In orchestrated mode, reconcile prior evidence and assess only residual dependency, performance, simplification, deletion, validation, and integration risk without repeating specialist passes."
---

# C++ Production Review

Review C++ as production code whose correctness, portability, and maintenance life matter. Follow the repository's declared standard. When none is declared, use C++23 as the working design baseline, report the missing build contract, and inspect what each target requests before relying on C++23 support. Treat C++26 as opt-in until the repository or user explicitly chooses it and the supported compiler and standard-library matrix implements the required facilities.

Prioritize observable defects, undefined behavior, broken invariants, and release risks over stylistic churn. Prefer deletion and standard-library facilities only when they reduce real complexity under the supported toolchain contract.

## Select the Mode

### Orchestrated final synthesis

Use this mode when a parent orchestrator invokes the skill after focused review groups.

- Consume the prior groups' scope, evidence, findings, fixes, validators, and explicit skips.
- Do not load the standalone checklist.
- Do not rerun completed build-portability, ownership, invariant, parsing, exception, API, functional, scientific, concurrency, or test analysis.
- Revisit a specialist concern only when later edits invalidate its evidence or the handoff exposes an unresolved cross-group contradiction.
- Focus on residual dependency, performance, simplification, deletion, validation, and integration risks, then reconcile the release verdict.

### Standalone broad review

Use this mode only when the skill is invoked directly for a broad C++ review, release-readiness review, or whole-repository baseline. Read [references/standalone-review.md](references/standalone-review.md) completely before applying the common residual workflow below.

## Ground Rules

- Read repository-local guidance before reviewing or editing.
- Do not mutate git state unless the user explicitly requests it.
- Honor a parent orchestrator's handed-off scope.
- Default to changed C++ files and nearby code needed to understand their contracts.
- Use whole-repository baseline mode only when explicitly requested.
- Keep diagnostic reviews read-only. When fixes are requested, make the smallest safe corrections and validate the affected contract.
- Verify current compiler, standard-library, dependency, and tool behavior from authoritative sources when version sensitivity matters.
- Treat compilation, tests, sanitizers, static analysis, and reasoning as complementary evidence.

## Scope and Evidence

Record:

- scope mode and files or targets in scope
- declared C++ standard and supported compiler/standard-library combinations
- affected build configurations and available validators
- dependency upgrades or removals under consideration
- prior specialist evidence in orchestrated mode
- untracked or user-owned work that must remain untouched

When invoked by an orchestrator, provide table-ready evidence naming the files inspected, residual concerns applied, findings or an explicit no-finding result, fixes, and validators.

## Residual Workflow

### 1. Reconcile dependencies and integration

Check that dependency APIs match resolved versions, public and private dependency exposure is intentional, migrations account for semantic as well as source changes, and removals eliminate transitive assumptions. Route registry, lockfile, workflow, and command mechanics to `project-tooling-review`.

For an upgrade or removal:

1. Inventory affected includes, symbols, targets, and public exposure.
2. Compare declared dependencies with actual target usage.
3. Read authoritative release notes, migration guidance, and API documentation.
4. Separate source migration, behavior change, build impact, and consumer impact.
5. Validate one dependency boundary at a time when practical.

### 2. Review performance and allocation

Check complexity, hot-path allocation and synchronization, accidental copies, data layout, repeated lookup or computation, and benchmark validity. Require measurement for non-obvious rewrites. Do not trade correctness or clarity for speculative micro-optimization.

### 3. Simplify or delete safely

Identify duplicate helpers and tests, unused declarations or dependencies, unreachable or unbuilt sources, stale compatibility branches, committed debug artifacts, and custom machinery replaced cleanly by supported C++23 facilities.

Before replacement or deletion, verify supported compiler/library availability, semantic and performance differences, downstream use, and whether the existing dependency supplies behavior not covered by the replacement. Prefer a proved deletion over a parallel compatibility path.

### 4. Reconcile validation and release risk

Map each material behavior or configuration change to evidence. In orchestrated mode, reuse valid specialist results and add only validators required by residual or cross-group risk. Do not claim platform support from configuration alone or turn unavailable matrix cells into inferred success.

Record exact commands, versions when relevant, results, unavailable validators, and why any expected validation was skipped. If a late fix affects an earlier contract, return it to the owning specialist and refresh that evidence before final classification.

## Finding Severity

- **P0 — Release blocker:** build failure, undefined behavior, data race, memory or resource safety defect, invariant corruption, scientifically invalid result, or tests unable to detect failure.
- **P1 — Must fix for production:** reachable wrong behavior, non-reproducible dependency or build contract, unsafe error handling, serious supported-platform failure, or untested critical path.
- **P2 — High-value improvement:** meaningful API, maintainability, performance, diagnostic, or test improvement that need not block a preserved legacy release.
- **P3 — Optional:** low-risk cleanup or stylistic modernization; keep this category small.

For every finding, provide file and line evidence, the failure scenario, why it matters, and the smallest credible remediation. Distinguish confirmed defects from hypotheses requiring unavailable validation.

## Final Report

Lead with unresolved P0/P1 findings. Include:

- release-readiness verdict
- findings ordered by severity with evidence
- prior specialist outcomes and contradictions resolved in orchestrated mode
- dependency and deletion candidates with proof still required
- validators and exact results
- supported-platform claims actually demonstrated
- deferred work and residual risk
- files changed when fixes were authorized
- confirmation that no git state mutation occurred when true
