---
name: cpp-exception-safety-error-contracts
description: "Audit modern C++20/C++23 exception safety and error contracts for correctness, consistency, and preserved failure guarantees. Use when changes touch throw/try/catch, noexcept, constructors, destructors, move operations, std::expected, std::error_code, result/status/optional returns, assertions, termination, rollback or transaction logic, parsing, serialization, filesystem, networking, callbacks, plugin interfaces, threads, coroutines, C interoperability, ABI boundaries, or partial mutation before failure."
---

# C++ Exception Safety and Error Contracts

Review how C++ code represents, propagates, and recovers from failure. Judge the implementation against the project's chosen error model instead of prescribing exceptions, `std::expected`, error codes, or another mechanism universally.

## Ground Rules

- Follow repository conventions and the documented public contract.
- Review changed operations together with their callers, callees, cleanup, and error boundaries.
- Distinguish no-throw, strong, basic, and explicitly weaker guarantees.
- Report concrete contract violations, termination hazards, lost failures, and untested recovery paths—not stylistic preferences.
- Hand resource lifetime defects to `cpp-lifetime-ownership-safety` and corrupted post-failure state to `cpp-invariant-state-transitions` rather than duplicating those reviews.
- Hand synchronization and worker-lifetime defects to `cpp-concurrency-reentrancy`, and detailed test-oracle quality to `cpp-test-quality`.

## Audit Workflow

### 1. Establish the failure contract

For each fallible operation, identify:

- the failure channel: exception, `std::expected`, `std::error_code`, status/result object, optional result, assertion, callback, termination, or a documented combination
- which failures are recoverable, impossible by contract, or fatal
- the guarantee promised to callers and the observable state after failure
- whether constructors, destructors, move/swap operations, callbacks, and worker tasks obey the same policy

Do not replace one coherent project-wide mechanism with another merely because it is fashionable or more familiar.

### 2. Trace every failure path

Walk from the first acquisition or mutation through every exit. Check that:

- validation and potentially throwing work happen before irreversible mutation when a strong guarantee is promised
- rollback covers every field, registration, handle, counter, and external side effect it claims to restore
- basic-guarantee paths preserve invariants and keep objects safely usable or destructible
- cleanup cannot mask the original failure or allow a second exception to escape during unwinding
- constructors release fully acquired subresources when later initialization fails
- error translation preserves actionable context and never silently converts failure into apparent success

### 3. Verify `noexcept` and special members

Inspect explicit and implicit exception specifications, including transitive callees:

- an operation declared `noexcept` cannot reach an uncontained throwing path
- conditional specifications use `noexcept(...)` or type traits that match the real operations performed
- move construction, move assignment, and `swap` provide the intended container behavior without making false promises
- destructors and cleanup paths do not let exceptions escape
- callbacks, comparison/hash functions, deleters, and customization points satisfy the exception contract required by their caller
- a missing or added `noexcept` does not unintentionally change overload selection, ABI/API expectations, optimization behavior, or termination semantics
- no hidden throwing path converts an ordinary failure into `std::terminate`

Treat `noexcept` as a correctness contract first, not an optimization annotation.

### 4. Review representations and boundaries

Check that exceptions, `std::expected`, status/result values, optional results, and error codes are consumed and translated consistently:

- success values cannot be observed when an error is present, and errors cannot be accidentally ignored
- translations preserve cause, category, and relevant context without logging the same failure at every layer
- C, plugin, callback, and other non-throwing ABI boundaries contain exceptions and return the documented failure representation
- thread, task, coroutine, and callback boundaries capture and communicate failures instead of terminating or discarding them unexpectedly
- filesystem, networking, allocation, parsing, serialization, and external-library failures follow the same public contract as adjacent operations
- assertions and deliberate termination are reserved for the project's documented fatal conditions rather than recoverable external failures
- public documentation and signatures still describe the actual failure channel and guarantee

### 5. Validate recovery behavior

Prefer focused tests that inject or simulate failure at meaningful steps:

- allocation, construction, callback, filesystem, networking, parsing, serialization, plugin, and external-library failures
- exceptions before and after the first mutation
- rollback and post-failure reuse or destruction
- `static_assert(noexcept(...))` or equivalent checks for contractually significant operations
- cross-thread, callback, plugin, C ABI, result/status, and `std::expected` propagation paths

Use the repository's existing test framework and fault-injection facilities. Do not add elaborate injection machinery unless the risk and unreachable coverage justify it.

## Finding Standard

For each finding, state the promised failure contract, the path that violates it, the resulting state or lost error, why callers can observe the defect, and the smallest correction plus verification.

## Reference

Use [references/review-checklist.md](references/review-checklist.md) as a final coverage check after tracing the concrete failure paths.

## Handoff

Summarize reviewed failure channels and guarantees, `noexcept` conclusions, boundary translations, rollback evidence, focused tests, and any ownership, invariant, concurrency, or test-quality follow-up.
