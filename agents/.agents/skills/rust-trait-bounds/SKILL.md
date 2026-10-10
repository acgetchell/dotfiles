---
name: rust-trait-bounds
description: "Review Rust generic constraints when bound necessity, placement, or downstream usability is in question."
---

# rust-trait-bounds

Rust-orchestrator passes use the shared [execution-v1 contract](../rust-review-orchestrator/references/execution-v1.md).

For direct invocation, read [references/standalone-workflow.md](references/standalone-workflow.md)
for scope discovery and the complete standalone report.

Audit Rust trait bounds, generic constraints, and `where` clauses for simplification and idiomatic API clarity.

Good bounds express the minimum contract needed by the code. Overly broad, duplicated, or misplaced bounds make APIs harder to use and compiler diagnostics harder to understand, while overly clever simplification can hide important semantics.

Keep general ownership, smart-pointer, interior-mutability, snapshot, and borrowed-view design under `rust-borrowed-view-audit`; keep Send/Sync and async bounds under `rust-concurrency-async`. This skill owns the necessity, placement, semantics, and caller ergonomics of generic constraints.

## Scope

Focus on newly added or modified Rust code that includes:

- generic functions, structs, enums, traits, or impl blocks
- `where` clauses
- associated type constraints
- higher-ranked trait bounds such as `for<'a>`
- public APIs whose trait bounds affect downstream users
- repeated bounds across multiple impls or methods

Ignore unrelated unchanged code unless needed to understand existing generic conventions.

## Review goals

### 1. Minimal necessary bounds

Check that each bound is required by the implementation or by the public API contract.

Flag:

- bounds that are never used by the function, impl, or trait item
- duplicated bounds in both inline generic parameters and `where` clauses
- bounds implied by supertraits or existing associated type constraints
- `Clone`, `Copy`, `Debug`, `Default`, `Send`, `Sync`, or `'static` added out of convenience rather than necessity
- bounds on a type definition that are only needed by one impl or method

Prefer:

- placing bounds on the smallest item that needs them
- leaving data type definitions unconstrained when possible
- deriving or implementing traits without forcing unrelated generic constraints onto every user

### 2. Placement and readability

Use inline bounds for simple signatures and `where` clauses when associated
types, lifetimes, or multiple constraints become hard to scan. Follow existing
local conventions when both are clear. Report placement only when it obscures
the caller contract, not to enforce one spelling everywhere.

### 3. Avoid over-generalization

Generic bounds should improve composability without making the API vague or harder to reason about.

Flag:

- accepting overly broad traits when the implementation depends on stronger semantic guarantees
- using conversion traits such as `Into`, `From`, `AsRef`, or `Borrow` where they blur ownership, allocation, or equality semantics
- replacing concrete types with generics when there is no caller benefit
- exposing complicated generic machinery in public APIs only to avoid a small internal conversion

Prefer:

- concrete types when the API is intentionally narrow
- `impl Trait` for simple argument polymorphism when callers do not need to name the type
- named type parameters when relationships between arguments, returns, and associated types matter

### 4. Associated types and higher-ranked bounds

Associated type constraints and HRTBs should be explicit enough to communicate the contract.

Check:

- associated type equality constraints are necessary and correct
- lifetime relationships are represented directly instead of hidden behind `'static`
- `for<'a>` bounds are used only when the code truly works for all lifetimes
- constraints on iterators, closures, and borrowed views match how values are consumed

Flag:

- adding `'static` to satisfy the compiler when a narrower lifetime would work
- weakening associated type constraints until invalid implementations can type-check
- complex bounds that would be clearer as a helper trait, adapter type, or private function

### 5. Public API ergonomics

Public bounds are part of the crate's user-facing contract.

Check that:

- public bounds are stable, intentional, and documented when non-obvious
- downstream callers can satisfy the bounds without importing private implementation traits
- error messages from failed bounds point users toward the real requirement
- simplification does not remove meaningful semantic constraints just because current tests still pass

Flag:

- leaking private implementation details through public bounds
- requiring callers to implement marker traits that could remain internal
- adding bounds to public structs that make construction or storage unnecessarily difficult

### 6. Tests and examples

When bounds change, tests should demonstrate the intended caller experience.

Prefer:

- doctests or integration tests that compile using the public API with minimal imports
- tests using lightweight custom types to prove unnecessary bounds were removed
- negative compile-fail tests only when the project already has a compile-fail testing setup

Avoid:

- relying only on internal unit tests that use overly capable types
- adding compile-fail infrastructure for a small cleanup unless the project already supports it
