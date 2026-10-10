---
name: rust-simplification-review
description: "Find justified Rust deletions and simplifications while preserving behavior, invariants, compatibility, and regression value."
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

Use the supplied scope or inspect the requested diff. For each concrete candidate,
classify it as `Delete`, `Simplify`, `Keep`, or `Split` and explain the invariant,
behavior, and cost that justify that choice. Implement authorized high-confidence
changes and run validation that can detect a changed contract.

Merge tests only when their inputs, assertions, failure modes, dimensions, and
feature gates are equivalent. Preserve existing abstractions that name a useful
concept or protect a distinct invariant. Do not manufacture cleanup to fill a
checklist; a justified `Keep` or no-finding result is complete.

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

## Results

Use the parent result contract when dispatched. Otherwise list findings by
severity and confidence with `Delete`, `Simplify`, `Keep`, or `Split`, a source
location, and rationale. Include applied changes, validation, and residual risks
only when present. If no safe simplification exists, say so and identify the
invariants that justify retaining the code.
