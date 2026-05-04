---
name: rust-trait-bounds
description: "Audit Rust trait bounds, generic constraints, and where clauses for simplification, idiomatic placement, and API clarity. USE FOR: Rust review comments asking whether trait bounds or where clauses can be simplified, redundant bounds, overly broad generic constraints, associated type constraints, HRTBs, impl/function generic cleanup, public API bound ergonomics, moving bounds from structs to impls/methods, choosing inline bounds vs where clauses. DO NOT USE FOR: Rust naming/import style (use rust-style-hygiene), error design (use rust-error-variants), test/doctest coverage (use rust-test-quality), prelude/export decisions (use rust-prelude-exports), non-Rust code, or unchanged code."
---

# rust-trait-bounds

Audit Rust trait bounds, generic constraints, and `where` clauses for simplification and idiomatic API clarity.

Good bounds express the minimum contract needed by the code. Overly broad, duplicated, or misplaced bounds make APIs harder to use and compiler diagnostics harder to understand, while overly clever simplification can hide important semantics.

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

### 2. Idiomatic placement

Use the form that is easiest to read and maintain.

Prefer inline bounds for simple cases:

- one or two short bounds
- obvious public API contracts
- common patterns such as `T: Copy`

Prefer `where` clauses for complex cases:

- multiple type parameters
- associated type equality or nested bounds
- lifetime-heavy bounds
- higher-ranked trait bounds
- constraints that would make the signature visually noisy

Flag:

- long inline bounds that obscure parameters or return types
- tiny `where` clauses that make a simple signature harder to scan
- inconsistent placement across similar functions without a readability reason

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

### 6. Smart pointer and ownership choice

The choice of smart pointer is part of the API contract that bounds support. Review it together with the bounds it implies.

Check that:

- `Box<T>` is used to give a value a stable size/heap address (e.g., trait objects, recursive types) rather than out of habit
- `Rc<T>` / `Arc<T>` are used only when shared ownership is genuinely needed; prefer borrowing or single ownership when feasible
- thread-shared data uses `Arc<T>` and not `Rc<T>` (and vice versa)
- interior mutability (`Cell`, `RefCell`, `Mutex`, `RwLock`) is justified by the access pattern, not used to bypass borrow checking
- one-time initialization uses `OnceLock` / `LazyLock` instead of ad hoc `Mutex<Option<_>>` patterns
- `Cow<'_, T>` is used when the API genuinely needs to return either a borrow or an owned value, not as a generic "maybe owned" smear
- function parameters use `&str` over `&String`, `&[T]` over `&Vec<T>`, and `impl AsRef<Path>`/`impl Into<X>` only when callers benefit

Flag:

- `Box<T>` purely to satisfy a trait object that could be a generic parameter
- `Arc<Mutex<T>>` patterns where simpler ownership would do
- `Rc`/`Arc` cloning to avoid lifetime annotations rather than to model real sharing
- public APIs that expose `Rc<T>` (which forbids `Send`) without intent
- public APIs that take owned `String`/`Vec<T>` when `&str`/`&[T]` would suffice

### 7. Tests and examples

When bounds change, tests should demonstrate the intended caller experience.

Prefer:

- doctests or integration tests that compile using the public API with minimal imports
- tests using lightweight custom types to prove unnecessary bounds were removed
- negative compile-fail tests only when the project already has a compile-fail testing setup

Avoid:

- relying only on internal unit tests that use overly capable types
- adding compile-fail infrastructure for a small cleanup unless the project already supports it

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Concrete issues with file/function/type references
- For each issue, state whether the problem is redundant, misplaced, overly broad, under-specified, or public-API-hostile

### Required Fixes
- Bounds to remove
- Bounds to move from type definitions to impls/methods
- Signatures or `where` clauses to simplify
- Smart pointer or parameter type changes that improve the API contract
- Public API docs, doctests, or integration tests to update

### Optional Improvements
- Non-blocking readability or ergonomics refinements
