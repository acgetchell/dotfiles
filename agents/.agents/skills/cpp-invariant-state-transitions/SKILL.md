---
name: cpp-invariant-state-transitions
description: "Audit C++ constructors, factories, mutation workflows, caches, state machines, and graph or topology operations for preserved invariants and failure-atomic behavior. Use when changes coordinate multiple fields, update derived state, invalidate handles, implement inverse operations, or can fail after mutation begins."
---

# C++ Invariant and State-Transition Review

Review C++ state changes as transitions between valid states. Identify the canonical owner of each invariant, trace every success and failure edge, and make the smallest correction needed to prevent invalid or partially updated state.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Honor repository-local instructions and documented domain contracts.
- Prefer changed files plus the constructors, mutators, caches, and callers that own the affected invariant.
- Do not mandate parse-don't-validate, wrapper types, builders, or a broad API redesign. Recommend architectural change only when it is the smallest credible fix for a verified defect.
- Separate invalid caller input, inapplicable domain operations, internal invariant violations, and expected rejection outcomes.

## Audit Workflow

### 1. State the invariant

For each changed type or workflow, write down:

- canonical state and which object owns it
- derived fields, caches, indices, counters, adjacency, and metadata
- construction preconditions and valid postconditions
- whether callers may observe intermediate state
- which operations invalidate references, iterators, or external handles

If the invariant cannot be stated, inspect tests and authoritative domain documentation before proposing a fix.

### 2. Trace construction and ordinary use

Check that constructors, factories, deserializers, and public mutators cannot produce an invalid object during ordinary supported use. Verify:

- validation occurs before dependent state is published
- default, copy, and move states are intentional
- setters and mutable accessors do not bypass coordinated updates
- cached or denormalized state has one clear refresh policy
- assertions are not the sole defense against recoverable external input

Strong types or restricted construction may be useful, but only propose them when they remove a demonstrated class of invalid states without disproportionate churn.

### 3. Trace each mutation edge

Follow the full transition:

```text
precondition -> preparation -> first mutation -> remaining mutations -> postcondition
```

Verify that:

- all preconditions are checked before irreversible mutation where practical
- coordinated fields, incidence, adjacency, counts, and caches change together
- every successful path establishes all postconditions
- every rejected or failed path either leaves the object unchanged or documents and tests its destructive semantics
- inverse operations restore the intended combinatorial or semantic state, not merely matching counts

For graph, mesh, or triangulation work, inspect reciprocal adjacency, orientation, manifold conditions, cell/simplex classifications, and library validity checks where applicable.

### 4. Audit failure atomicity

Inspect exceptions, error returns, allocation failures, callbacks, and library operations that can fail after mutation begins. Prefer, in order of local fit:

- completing all fallible preparation before mutation
- using repository- or library-provided transactional primitives
- applying a proven rollback that cannot itself violate invariants
- constructing replacement state off to the side and committing once

Do not introduce full-state copies into hot paths without evidence that the cost is acceptable.

### 5. Reconcile lifetime, error contracts, and concurrency

Hand off or jointly inspect:

- invalidated pointers, views, iterators, and handles with `cpp-lifetime-ownership-safety`
- raw boundary representations, repeated validation, and proof-bearing domain types with `cpp-parse-dont-validate`
- exception guarantees, failure representations, `noexcept`, and cross-boundary propagation with `cpp-exception-safety-error-contracts`
- concurrent publication, locking, atomics, and cancellation with `cpp-concurrency-reentrancy`
- numerical, geometric, stochastic, or scientific invariants with `cpp-scientific-correctness`

### 6. Validate

Prefer focused tests that cover:

- a minimal successful transition and exact expected state deltas
- every meaningful rejection and failure path
- failure atomicity using canonical snapshots or independent observations
- inverse or round-trip operations when mathematically appropriate
- repeated mutation under ASan and UBSan for handle and state corruption

Do not rely only on a production `is_valid()` helper as the test oracle. Assert independent properties that would catch a shared implementation bug.

## Finding Standard

For each finding, name the invariant, transition edge, observable invalid state, minimal correction, and regression evidence. Distinguish confirmed defects from follow-up design opportunities.

## Handoff

Summarize changed files, invariants checked, transition and failure paths covered, validators and results, deferred architectural opportunities, and confirmation that no git state mutations were performed when true.
