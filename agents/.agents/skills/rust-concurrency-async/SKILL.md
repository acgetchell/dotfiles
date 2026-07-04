---
name: rust-concurrency-async
description: "Audit Rust concurrency, async, and transactional mutation code for Send/Sync discipline, blocking hazards, lock/channel design, cancellation safety, transaction guard design, and failure atomicity on changed code or whole-repo baseline audits. USE FOR: async/await, Tokio/async-std, Send/Sync bounds, spawn_blocking, cancellation safety, owner-bound transaction guards, rollback-on-drop, rollback-preserving snapshots, restore-before-retry, failure-atomic mutation windows, Mutex/RwLock/parking_lot/tokio::sync, atomics, channels, lock ordering, deadlocks, deterministic side effects, structured concurrency, async traits/lifetimes, futures, and streams. DO NOT USE FOR: synchronous correctness without concurrency/cancellation/transaction concerns (use rust-production-review), error design (use rust-error-variants), trait bounds (use rust-trait-bounds), iterators (use rust-iter-control-flow), non-Rust code, or unrelated unchanged code unless a baseline audit is requested."
---

# rust-concurrency-async

Audit Rust concurrency, async, and transactional mutation code for correctness under realistic scheduling and failure modes, with attention to `Send`/`Sync` discipline, blocking hazards, lock and channel design, cancellation safety, and rollback atomicity.

The compiler enforces only the minimum. A review must reason about scheduling, ordering, contention, cancellation, and partially completed mutations explicitly. Treat synchronous transactions as in scope when fallible mutation, retry, cancellation, or drop can leave coupled state inconsistent.

## Scope

Focus on newly added or modified Rust code that:

- adds or modifies `async fn`, `async {}`, `Future` impls, or `.await` points
- uses Tokio, async-std, smol, or another async runtime
- spawns tasks (`tokio::spawn`, `task::spawn_local`, `rayon::spawn`, raw threads)
- uses `Mutex`, `RwLock`, `parking_lot`, `tokio::sync::Mutex/RwLock/Semaphore/Notify`, or `OnceLock`/`LazyLock`
- uses channels (`mpsc`, `oneshot`, `broadcast`, `watch`)
- adds atomics or memory orderings
- changes `Send`/`Sync` bounds on public APIs
- adds `spawn_blocking` or thread pool offloading
- adds or changes transaction guards, rollback guards, snapshots, rollback-on-drop, `commit`/`rollback`/`restore`, or restore-on-failure mechanisms
- introduces fallible mutation APIs that should use a transaction even if no transaction abstraction exists yet
- mutates coupled storage, indexes, caches, hints, identities, handles, telemetry, or generation counters across a fallible or cancellable window
- adds fallback or retry flows after partial mutation

### Scope Modes

Default mode:
- Audit newly added or modified async, threaded, synchronized, atomic, transactional, or Send/Sync-affecting code.
- Ignore unrelated unchanged concurrency code unless it defines the scheduling or synchronization contract for the changed code.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit all async/concurrent Rust code, including public Send/Sync contracts, tasks, locks, channels, atomics, transaction guards, global caches, and tests that rely on ordering.
- Prioritize findings by deadlock risk, cancellation unsafety, failure-atomicity gaps, blocking in async contexts, hidden nondeterminism, and public Send/Sync API surprises.
- If the repo has little or no concurrency, say so explicitly instead of inventing findings.

## Review goals

### 1. Send/Sync discipline

Check:

- public futures and types are `Send`/`Sync` when callers reasonably expect them to be
- `!Send`/`!Sync` futures are documented and intentional
- non-async-aware lock guards (`std::sync::MutexGuard`, `RefMut`) do not cross `.await` points
- holding non-`Send` data (`Rc`, `RefCell`) across `.await` is intentional and scoped

Flag:

- accidental `!Send` future leaks via `Rc`/`RefCell`
- `std::sync::Mutex` held across `.await`
- types that should expose `Send + Sync` bounds but do not
- overly broad `: 'static` bounds on async functions added to satisfy the compiler

### 2. Blocking in async contexts

Check:

- CPU-heavy or I/O-blocking work uses `spawn_blocking` or a dedicated thread pool
- file I/O, sync database calls, or `std::thread::sleep` are not run on the async runtime
- async streams do not silently block the runtime in their `poll_next`

Flag:

- synchronous I/O inside `async fn`
- long CPU loops without `yield_now`/`spawn_blocking`
- blocking calls dispatched to the same runtime that scheduled the task
- `block_on` inside an async context

### 3. Cancellation safety

Check:

- futures can be dropped at any `.await` point without leaving inconsistent state
- partially completed work releases resources cleanly
- transactional mutation windows are rollback-safe if cancellation can interrupt them
- `select!` arms are cancellation-safe (or wrapped to be)
- timeouts and cancellation tokens propagate correctly through nested calls

Flag:

- mutation between `.await` points that becomes invalid if the future is dropped
- writes that must complete but live in a cancellable future
- assumptions that an async function runs to completion
- `select!` arms calling cancellation-unsafe operations such as buffered reads

### 4. Transactional mutation windows

Use this section for synchronous code too when a fallible sequence mutates canonical state.

Preferred pattern:

- start the transaction at the highest owner that owns all state affected by the mutation
- snapshot canonical storage plus coupled auxiliary state such as indexes, caches, hints, identities, handles, diagnostics, telemetry, and generation counters
- expose mutation through the guard so callers cannot accidentally mutate outside the failure boundary
- restore on `Drop` unless the guard is finished; use `commit(self)` to close without restore, `rollback(self)` to restore and close, and `restore(&mut self)` to restore while keeping the window open for retry
- use rollback-preserving snapshot semantics when ordinary `Clone` would allocate fresh owner identity, generations, handle provenance, or borrowed-view provenance
- keep raw low-level primitives no-rollback when a higher-level API owns the transaction; name or document them as raw primitives and keep them non-public unless a primitive layer is intentional
- prevalidate impossible cases before mutation when possible, then validate and repair/canonicalize postconditions inside the transaction before commit
- roll back with typed diagnostic errors on validation, repair, or canonicalization failure

Check:

- fallible mutation sequences are protected by an owner-bound transaction guard, rollback guard, or prevalidated no-fail proof
- rollback restores all coupled state, including indexes, caches, hints, identities, counters, and topology generations
- guards roll back on `Drop` unless explicitly committed, and commit/rollback paths are idempotence-aware
- fallback strategies restore the original state before trying an alternate mutation path
- snapshot/restore does not leave borrowed views, cached keys, handles, or generation checks stale by accident
- raw low-level primitives do not take their own snapshots when a higher-level transaction owns the failure boundary
- transaction guards are not held across `.await`, blocking calls, or callbacks unless the invariant is documented and safe
- nested transactions are intentional and do not double-snapshot expensive state by accident
- tests force failure after mutation and assert the original storage plus auxiliary state is restored; cover drop rollback, explicit rollback, restore-and-retry, and commit paths

Flag:

- manual clone/restore snapshots when a local transaction abstraction exists or should be introduced
- ordinary `Clone` used for rollback where owner identity, provenance, generations, or cache invalidation matters
- partial rollback that restores primary storage but leaves derived indexes, hints, or generation counters stale
- fallible mutation followed by validation without rollback on validation failure
- commit before validation, repair, or canonicalization establishes the postcondition
- low-level primitives snapshotting under a high-level transaction boundary
- public/top-level mutation APIs that start the transaction below the owner of affected auxiliary state
- transaction guards crossing `.await` points, lock acquisitions, or external callbacks
- fallback code that attempts a second mutation without restoring after the first failure
- tests that cover only successful transactions and never inject post-mutation failure

### 5. Locks and channels

Check:

- lock granularity matches contention patterns
- locks are released before awaiting unrelated work
- read-mostly workloads use `RwLock` only when reads dominate
- channel choice matches usage:
  - `mpsc` for fan-in
  - `broadcast` for fan-out
  - `oneshot` for request/response
  - `watch` for state observation
- bounded channels are used where backpressure matters
- `OnceLock`/`LazyLock` are used for one-time initialization rather than ad hoc `Mutex<Option<_>>`

Flag:

- nested locks acquired in inconsistent order (deadlock risk)
- coarse locks held across long async sections
- unbounded channels in fan-in pipelines that can run away
- ignoring `try_send` errors as if they were transient
- swallowed `JoinError`/`RecvError`

### 6. Atomics and memory ordering

Check:

- `Relaxed`, `Acquire`, `Release`, `AcqRel`, `SeqCst` choices are justified
- atomic operations are paired correctly between producer and consumer
- `compare_exchange` retry loops handle spurious failure
- atomics are not used as a substitute for proper synchronization of non-atomic state

Flag:

- defaulting to `SeqCst` without considering whether `Acquire`/`Release` would suffice
- mixing relaxed atomics with non-atomic state expecting happens-before guarantees
- ABA hazards in lock-free code without mitigation

### 7. Determinism and ordering

Check:

- task spawn ordering does not silently change observable output
- iteration over concurrent collections produces stable enough results for tests
- shutdown order, log ordering, and effect ordering are deterministic when callers depend on them

Flag:

- tests asserting ordering on concurrent results without synchronization
- nondeterministic shutdown that drops in-flight work
- joins that are ignored, leaving detached tasks

### 8. API surface

Check:

- async traits (`async fn` in trait, `BoxFuture`, `async-trait`) suit the audience
- public APIs do not require a specific runtime unless documented
- `Send + 'static` bounds are intentional, not compiler appeasement
- structured concurrency primitives (`JoinSet`, `task::scope`) are preferred over hand-rolled spawning when supported
- bounds added to a public `async fn` are treated as semver-relevant

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Concrete concurrency or async issues with file/function references
- For each issue, state the failure mode and the trigger condition

### Required Fixes
- Send/Sync corrections
- Blocking offloads
- Cancellation safety repairs
- Transaction guard design/reuse, rollback-preserving snapshot repairs, validation-before-commit repairs, and failure-injection tests
- Lock/channel changes
- Atomic ordering changes

### Optional Improvements
- Structured concurrency, runtime independence, or test determinism refinements
