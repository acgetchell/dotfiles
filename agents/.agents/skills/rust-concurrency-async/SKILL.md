---
name: rust-concurrency-async
description: "Audit Rust concurrency and async code for correctness, Send/Sync discipline, blocking hazards, and lock/channel design on changed code or whole-repo baseline audits when explicitly requested. USE FOR: async/await review, Tokio/async-std runtime usage, Send/Sync bounds, spawn_blocking, cancellation safety, Mutex/RwLock/parking_lot/tokio::sync use, atomics ordering, channel discipline (mpsc/oneshot/broadcast/watch), lock ordering, deadlocks, deterministic ordering of side effects, structured concurrency, async trait bounds, async lifetimes, futures and streams. DO NOT USE FOR: synchronous correctness only (use rust-production-review), error design (use rust-error-variants), trait bound cleanup (use rust-trait-bounds), iterator/pattern idioms (use rust-iter-control-flow), non-Rust code, or unrelated unchanged code unless a baseline audit is requested."
---

# rust-concurrency-async

Audit Rust concurrency and async code for correctness under realistic scheduling, with attention to `Send`/`Sync` discipline, blocking hazards, lock and channel design, and cancellation safety.

The compiler enforces only the minimum. A review must reason about scheduling, ordering, contention, and cancellation explicitly.

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

### Scope Modes

Default mode:
- Audit newly added or modified async, threaded, synchronized, atomic, or Send/Sync-affecting code.
- Ignore unrelated unchanged concurrency code unless it defines the scheduling or synchronization contract for the changed code.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit all async/concurrent Rust code, including public Send/Sync contracts, tasks, locks, channels, atomics, global caches, and tests that rely on ordering.
- Prioritize findings by deadlock risk, cancellation unsafety, blocking in async contexts, hidden nondeterminism, and public Send/Sync API surprises.
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
- `select!` arms are cancellation-safe (or wrapped to be)
- timeouts and cancellation tokens propagate correctly through nested calls

Flag:

- mutation between `.await` points that becomes invalid if the future is dropped
- writes that must complete but live in a cancellable future
- assumptions that an async function runs to completion
- `select!` arms calling cancellation-unsafe operations such as buffered reads

### 4. Locks and channels

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

### 5. Atomics and memory ordering

Check:

- `Relaxed`, `Acquire`, `Release`, `AcqRel`, `SeqCst` choices are justified
- atomic operations are paired correctly between producer and consumer
- `compare_exchange` retry loops handle spurious failure
- atomics are not used as a substitute for proper synchronization of non-atomic state

Flag:

- defaulting to `SeqCst` without considering whether `Acquire`/`Release` would suffice
- mixing relaxed atomics with non-atomic state expecting happens-before guarantees
- ABA hazards in lock-free code without mitigation

### 6. Determinism and ordering

Check:

- task spawn ordering does not silently change observable output
- iteration over concurrent collections produces stable enough results for tests
- shutdown order, log ordering, and effect ordering are deterministic when callers depend on them

Flag:

- tests asserting ordering on concurrent results without synchronization
- nondeterministic shutdown that drops in-flight work
- joins that are ignored, leaving detached tasks

### 7. API surface

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
- Lock/channel changes
- Atomic ordering changes

### Optional Improvements
- Structured concurrency, runtime independence, or test determinism refinements
