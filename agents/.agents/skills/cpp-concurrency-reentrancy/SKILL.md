---
name: cpp-concurrency-reentrancy
description: "Audit C++ threads, mutexes, atomics, task systems, signal handlers, callbacks, and RNG state for races, deadlocks, lifetime hazards, cancellation errors, and reentrancy defects. Use when changes involve TBB, OpenMP, standard threads, executors, synchronization, asynchronous signals, shared state, or ThreadSanitizer-sensitive paths."
---

# C++ Concurrency and Reentrancy Review

Review concurrent C++ by identifying shared state, proving its ownership and happens-before relationships, and checking task lifetime and failure behavior. Do not treat a clean ThreadSanitizer run as a proof of correctness.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Honor repository-local concurrency and library contracts.
- Review changed code plus the state it shares and the code that starts, joins, cancels, or destroys its work.
- Establish sequential invariants before recommending parallelization or lock-free techniques.
- Prefer simple ownership and synchronization over clever memory ordering without measured need.

## Audit Workflow

### 1. Inventory execution and shared state

Identify:

- threads, pools, tasks, callbacks, parallel loops, and signal handlers
- mutable objects, caches, registries, loggers, RNG state, and globals they share
- owners of worker lifetime, cancellation, and completion
- data intended to be thread-confined, immutable, guarded, atomic, or externally synchronized

Make implicit serialization assumptions explicit.

### 2. Prove synchronization

Check:

- every non-atomic conflicting access is ordered by a happens-before relationship
- mutexes guard the same invariant consistently
- lock ordering prevents cycles and callbacks do not unexpectedly re-enter locked code
- condition-variable predicates handle spurious wakeups and notification ordering
- atomic memory orders are sufficient and documented; use stronger ordinary synchronization when the proof is unclear
- atomic modification order and memory ordering establish exactly the required guarantees; atomicity alone is not a synchronization proof
- compound invariants are not incorrectly split across independent atomics

Flag data races even when they appear benign; they are undefined behavior in C++.

### 3. Check task and object lifetime

Inspect:

- references, spans, iterators, handles, and captured `this` that outlive their owners
- detached work, task groups, futures, and pool shutdown
- thread-local storage destruction and static initialization/destruction order
- move or destruction while work is still running
- library handles invalidated by concurrent mutation

Use `cpp-lifetime-ownership-safety` for the underlying ownership proof when the hazard is not concurrency-specific.

### 4. Audit signal-handler safety

Treat asynchronous signal handling as a distinct execution environment:

- identify the language, platform, and runtime rules that govern the handler
- allow only operations documented as signal-safe; do not use mutexes, allocation, iostreams, or other unsafe library facilities
- communicate through `volatile std::sig_atomic_t`, a plain lock-free atomic operation permitted by the applicable C++ rules, or a platform mechanism such as a self-pipe only when its documented contract permits it
- verify handler installation, restoration, and every interaction with ordinary execution

### 5. Check failure, cancellation, and publication

Verify:

- exceptions from workers are observed or deliberately contained
- cancellation cannot strand locks, half-publish state, or skip joins
- partial results are committed atomically with respect to readers
- shutdown is bounded and repeatable
- callbacks and public entry points are safely reentrant or explicitly reject reentrancy

Review mutation atomicity jointly with `cpp-invariant-state-transitions`.
Hand exception propagation and cross-thread error contracts to `cpp-exception-safety-error-contracts` when they extend beyond synchronization or task lifetime.

### 6. Check determinism and stochastic isolation

Ensure tests can control scheduling-sensitive inputs where practical. Shared RNG engines require explicit synchronization or, preferably, explicit run/task ownership with documented stream semantics. Do not allow hidden global reseeding to make results timing-dependent.

### 7. Validate

Use repository recipes first. Prefer:

- targeted deterministic concurrency tests
- bounded stress tests with replay information
- ThreadSanitizer on a supported compiler/platform
- ASan/UBSan for task-lifetime and invalidation bugs
- lock-order or deadlock diagnostics when available

Account for platform limitations and known incompatibilities. A test that only sleeps and hopes for an interleaving is weak evidence; use barriers, latches, hooks, or controlled executors where feasible.

## Finding Standard

For each finding, name the shared state, conflicting operations, missing synchronization or lifetime edge, failure mode, minimal correction, and validation strategy.

## Handoff

Summarize concurrency surfaces inspected, defects fixed, synchronization assumptions, stress or sanitizer results, platform gaps, and confirmation that no git state mutations were performed when true.
