---
name: rust-concurrency-async
description: "Audit Rust concurrency and async code for Send/Sync discipline, task and borrow lifetimes, blocking hazards, cancellation safety, structured concurrency, lock and channel design, atomic memory ordering, backpressure, shutdown, determinism, and mutation observed across scheduling boundaries. Use for runtimes, futures, streams, threads, tasks, callbacks, shared state, atomics, or owner-bound work crossing await or task boundaries."
---

# Rust Concurrency and Async

Audit correctness under realistic scheduling, cancellation, contention, failure, and shutdown. The compiler prevents many memory errors but does not prove progress, ordering, cancellation atomicity, backpressure, or deterministic semantics.

## Ground Rules

- Read repository runtime, thread-safety, determinism, and shutdown contracts first.
- Default to changed concurrent code and nearby state, callers, and tests needed to prove it.
- Keep purely synchronous coordinated mutation, rollback contents, caches, and operation sequences under `rust-invariant-state-transitions`.
- Keep general smart-pointer/view ownership under `rust-borrowed-view-audit` and generic-bound minimality under `rust-trait-bounds`.
- Do not recommend parallelism before the sequential invariant and measurement baseline are established.
- Keep reviews read-only unless fixes are requested; do not mutate git state without permission.

## Scope Modes

Use changed-code mode by default. Use whole-repository baseline mode only when explicitly requested; if the repository has little concurrency, say so rather than inventing findings.

## Workflow

### 1. Establish scheduling and ownership

Record:

- runtime or thread model and task ownership
- shared versus confined state
- required Send/Sync and `'static` behavior
- ordering, determinism, progress, cancellation, and shutdown promises
- error and panic propagation across task boundaries

Do not add `'static`, `Send`, or `Sync` only to appease a spawn API. Verify the caller and storage relationship they imply.

### 2. Audit task and borrow lifetimes

Check:

- spawned work cannot outlive borrowed state unless ownership is transferred deliberately
- joins, scopes, cancellation tokens, and task groups own completion
- detached tasks are intentional and observable failures are not discarded
- non-Send values and lock/borrow guards do not cross incompatible await or thread boundaries
- async trait/future representations match downstream runtime and Send expectations

Prefer structured concurrency (`scope`, task groups, join sets, owned cancellation) over hand-rolled detached spawning when supported by the repository.

### 3. Remove blocking from async execution

Check for synchronous file/network/database calls, CPU-heavy loops, blocking locks, sleeps, and `block_on` inside async contexts. Use async APIs, dedicated threads, or blocking pools according to runtime guidance.

Do not offload tiny work reflexively. Account for queueing, ownership transfer, cancellation, and saturation of the blocking pool.

### 4. Prove cancellation safety

A future can be dropped at any await point. Trace state before and after each suspension:

- partial writes or mutations remain valid, roll back, or are completed by an owned background operation
- `select!`, timeout, retry, and stream operations document cancellation behavior
- reservation, permit, lock, and resource cleanup is drop-safe
- externally visible effects are idempotent or carry an explicit commit boundary
- owner-bound transaction guards do not cross await or callbacks unless their invariant and cancellation behavior are proved

Use `rust-invariant-state-transitions` to prove the underlying state transition; this pass proves interruption and cross-task observation.

### 5. Audit locks, channels, and backpressure

Check:

- lock ordering and granularity avoid deadlock and unnecessary contention
- guards are released before unrelated await, callbacks, or expensive work
- `RwLock` matches an actually read-dominant workload
- channel type matches fan-in, fan-out, request/response, or state observation
- bounded queues and explicit overflow policy provide needed backpressure
- send/receive, join, close, and lag errors are handled
- shutdown closes producers/consumers in an order that cannot strand work

One-time initialization should use established once-cell primitives rather than ad hoc locked options when appropriate.

### 6. Audit atomics and lock-free state

Require a written invariant for each atomic relationship. Check producer/consumer pairing, compare-exchange retry, spurious failure, ABA risk, and interaction with non-atomic state.

Use the weakest ordering that is demonstrably correct, not the weakest imaginable. Flag both unjustified `SeqCst` and insufficient relaxed/acquire/release relationships.

### 7. Preserve determinism and error behavior

Check task/result ordering, parallel reductions, RNG streams, concurrent collection iteration, logging, shutdown, and retries against caller-visible determinism promises. Capture panics and errors instead of silently detaching or converting them to success.

Numerical or stochastic parallelism must preserve the scientific contract or explicitly revise it with `rust-scientific-correctness` evidence.

### 8. Review public concurrency contracts

Treat runtime coupling, Send/Sync, cancellation, ordering, callback reentrancy, backpressure, and shutdown as public API. Avoid forcing one runtime without documentation and a caller benefit.

## Validation

Prefer deterministic coordination over sleeps. Add focused tests for:

- task completion, cancellation at each meaningful suspension, timeout, and shutdown
- error/panic/join propagation
- lock ordering and channel close/backpressure behavior
- state consistency when work is cancelled or callbacks fail
- Send/Sync or compile-contract expectations
- deterministic output/RNG behavior where promised
- Loom or another model checker when established and the synchronization state space warrants it
- TSan or platform diagnostics only where supported and capable of exercising the path

A passing stress test supplements but does not prove race freedom or cancellation safety.

## Finding Standard

For each finding, state the schedule or cancellation point, shared state and synchronization, observable failure, violated contract, smallest correction, and focused deterministic evidence.

## Handoff

Summarize task/runtime contracts, Send/Sync conclusions, blocking and cancellation analysis, locks/channels/atomics, determinism, tests and validators, state-transition follow-up, files changed, and confirmation that no git state mutation occurred when true.
