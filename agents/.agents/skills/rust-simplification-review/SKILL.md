---
name: rust-simplification-review
description: "Review Rust code and tests for safe simplification, deletion, deduplication, and redundancy removal in invariant-heavy libraries. USE FOR: Rust review passes focused on simplifying code, deleting dead or redundant helpers, consolidating duplicate tests, shrinking public or crate-internal surfaces, and removing accidental complexity without weakening correctness, domain invariants, API orthogonality, performance, diagnostics, or regression coverage. DO NOT USE FOR: broad production-readiness review (use rust-production-review), surface-only naming/import cleanup (use rust-style-hygiene), focused test coverage audits without simplification goals (use rust-test-quality), non-Rust code, generated code, or unrelated unchanged code unless a baseline simplification audit is requested."
---

# rust-simplification-review

Review Rust changes for simplification that preserves behavior, invariants, orthogonality, and performance.

Favor deletion and consolidation only when the remaining code still says the same mathematical, API, and testing truths. Do not treat shorter code as better code by default.

## Scope

Default mode:
- Review newly added or modified Rust code, tests, examples, benches, doctests, public exports, and nearby helpers needed to judge the change.
- Ignore unrelated unchanged code unless it defines an invariant, API contract, or performance path the change relies on.

Whole-repo baseline mode:
- Use only when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Prioritize high-confidence simplifications that reduce maintenance risk without changing behavior.
- Do not require fixing every historical issue in one pass; produce a focused remediation plan.

Look for:
- code that can be deleted safely
- duplicated tests that cover the same behavior, inputs, dimensions, feature gates, and failure mode
- helper functions whose indirection no longer carries an invariant or name worth preserving
- redundant assertions, branches, allocations, clones, imports, comments, cfgs, or re-exports
- public API overlap that weakens orthogonality
- test scaffolding that obscures the invariant being checked

## Priority Order

Apply this order when tradeoffs conflict:

1. correctness
2. explicit invariants
3. orthogonality and public API clarity
4. performance and allocation discipline
5. test signal and regression coverage
6. readability and maintenance

## Do Not Delete

Do not recommend deletion of code, comments, or tests that protect a distinct:
- error variant or typed failure path
- public API contract
- dimension-generic behavior
- feature-gated behavior
- numerical boundary or degeneracy case
- topological invariant
- allocation or performance budget
- regression fixture
- panic or no-panic guarantee
- adversarial input family
- benchmark methodology or measured hot path

When apparent duplication protects different invariants, classify it as `Keep`.

## Workflow

1. Inspect the changed surface.
   - Use read-only git commands such as `git --no-pager status --short`, `git --no-pager diff --stat`, `git --no-pager diff --name-status`, and `git --no-pager diff`.
   - For staged reviews, inspect `git --no-pager diff --cached`.
   - Identify production code, tests, examples, benches, docs, and public exports touched by the change.

2. Classify each candidate.
   - `Delete`: dead code, stale comments, obsolete scaffolding, redundant assertions, unused helpers.
   - `Simplify`: clearer control flow, less indirection, fewer allocations, existing API replacing custom logic.
   - `Keep`: apparent redundancy that protects a distinct invariant.
   - `Split`: worthwhile cleanup that belongs in a separate patch.

3. Check invariants before recommending edits.
   - Name the affected behavior or invariant.
   - Explain why the simplification is behavior-preserving.
   - Call out possible performance effects.
   - Identify focused validation needed.

4. Prefer conservative implementation.
   - If asked to edit, apply only high-confidence `Delete` and low-risk `Simplify` items unless the user explicitly asks for broader refactoring.
   - Avoid merging tests unless their inputs, assertions, failure modes, dimensions, and feature gates are genuinely equivalent.
   - Prefer existing public constructors, validators, helpers, and iterators over new local abstractions.

## Review Checklist

Production code:
- unnecessary `clone`, `collect`, allocation, formatting, boxing, dynamic dispatch, or temporary storage
- duplicate validation paths that can share a helper without hiding layer boundaries
- branches that can become clearer with `let else`, `matches!`, direct `match`, or early return
- helpers with one caller that do not encode a useful concept
- comments that restate code instead of documenting invariants, algorithms, conditioning, or rollback semantics
- public exports or focused prelude items that overlap unrelated workflows
- error pathways that conflate independent failure axes

Tests:
- duplicated tests with identical domain coverage and failure modes
- weak smoke tests superseded by stronger unit, integration, doctest, or property coverage
- helper abstractions that make failures harder to diagnose
- assertions that only check `is_ok()` or `is_err()` when typed details matter
- proptests that add runtime cost without broader input coverage
- doctests that duplicate examples without guarding API behavior

Performance:
- unnecessary heap allocation in hot paths
- avoidable full clones or snapshots
- timers, logging, or string formatting in measured or hot loops
- repeated hash/index construction where cached state remains valid
- benchmark setup accidentally included in measured work

Orthogonality:
- focused preludes mixing unrelated workflows
- tests coupling geometry, topology, and construction when a narrower layer would prove the invariant
- public types or helpers that duplicate existing concepts
- feature flags with unclear or overlapping responsibilities

## Output Format

Start with findings, ordered by severity and confidence.

Use this structure:

```text
Summary: PASS | NEEDS IMPROVEMENT | FAIL

Findings
- [Delete/Simplify/Keep/Split] path:line - recommendation and rationale.

Applied Changes
- List only if edits were made.

Validation
- Commands run and results.
- Note any checks that could not be run.

Residual Risk
- Anything still uncertain or worth a follow-up issue.
```

When there are no safe simplifications, say so directly and identify the strongest invariants that justify keeping the code as-is.
