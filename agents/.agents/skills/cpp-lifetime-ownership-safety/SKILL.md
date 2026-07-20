---
name: cpp-lifetime-ownership-safety
description: "Audit C++ source, headers, and tests for RAII, ownership, lifetime, invalidation, resource leaks, undefined behavior, and exception-safe cleanup. Use when code changes raw or smart pointers, references, views, spans, iterators, handles, callbacks, coroutines, promises, awaiters, suspension points, container mutation, resource wrappers, C interfaces, or sanitizer-sensitive paths."
---

# C++ Lifetime and Ownership Safety

Review C++ for concrete lifetime and resource-safety defects. Establish who owns each resource, how long every borrow remains valid, and whether every success and failure path preserves those facts.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Honor repository-local instructions and the project's documented C++ standard, compiler support, and dependency contracts.
- Prefer changed-file review plus nearby ownership and invariant owners. Expand scope only when a lifetime crosses the changed boundary.
- Report observable correctness risks, not stylistic preferences. Do not replace a valid non-owning raw pointer merely to introduce a smart pointer.
- Prefer the smallest fix that makes ownership and lifetime explicit without broad API churn.

## Audit Workflow

### 1. Map ownership and resources

For every changed resource-bearing path, identify:

- the unique, shared, or external owner
- non-owning pointers, references, spans, views, iterators, and handles
- acquisition, transfer, release, and destruction points
- whether objects can be destroyed through a base interface and that interface provides virtual destruction or deliberately prevents such deletion
- whether custom copy, move, assignment, or swap behavior preserves ownership

Flag ambiguous ownership, double ownership, leaks, double release, mismatched allocation/deallocation, and resources that escape their owner.

### 2. Trace lifetime and invalidation

Check borrows across:

- return values, stored references, lambdas, callbacks, coroutines, and asynchronous tasks
- container growth, erase, sort, swap, move, and destruction
- graph, mesh, triangulation, or topology mutation that can invalidate library handles
- temporary materialization, `string_view`, `span`, iterator pairs, and proxy references
- object copy/move and self-referential state

Treat a borrow as valid only when its owner and every invalidating operation are visible in the proof. Pay special attention to captured `this`, detached work, and library-specific handle guarantees.

### 3. Verify RAII and failure safety

Inspect partial construction, early returns, exceptions, and failed operations:

- acquire resources into RAII owners immediately
- ensure cleanup does not depend on reaching the bottom of a function
- keep destructors non-throwing
- ensure move operations preserve destination ownership and leave the source within its documented post-move contract and safely destructible
- distinguish basic, strong, and no-fail guarantees where callers depend on them
- ensure error paths do not leak locks, files, memory, registrations, or partially published state

Do not recommend exception machinery when the project deliberately uses another error model; require equivalent cleanup and state guarantees.
Hand the chosen failure representation, propagation, exception guarantee, and `noexcept` contract to `cpp-exception-safety-error-contracts`; this skill owns whether resources remain safe.

### 4. Audit undefined behavior and bounds

Check changed operations for:

- uninitialized reads, operations that violate a moved-from object's documented post-move contract, use-after-free, null dereference, and out-of-bounds access
- invalid downcasts, aliasing or alignment violations, dangling C strings, and format mismatches
- signed overflow, invalid shifts, narrowing, and index arithmetic overflow
- invalid iterator comparisons, overlapping copies, and mutation during traversal
- concurrency-related lifetime races; hand substantive synchronization review to `cpp-concurrency-reentrancy`

### 5. Validate the defect and fix

Use repository recipes first. Choose the smallest meaningful combination of:

- targeted unit or integration tests
- AddressSanitizer plus UndefinedBehaviorSanitizer
- standalone LeakSanitizer where supported and relevant
- compiler warnings and repository-owned static analysis

Sanitizer silence is supporting evidence, not proof. Add a deterministic regression test when the defect can be exercised reliably.

## Finding Standard

For each finding, state:

- the owner and borrower or resource pair involved
- the invalidating event or missed cleanup path
- the concrete failure mode
- the smallest safe correction
- the validator that demonstrates the corrected behavior

Do not file speculative findings that require an undocumented library invalidation rule. Verify such rules from the installed headers or current authoritative documentation first.

## Handoff

Summarize changed files, fixed defects, validators and results, remaining lifetime assumptions, and confirmation that no git state mutations were performed when true.
