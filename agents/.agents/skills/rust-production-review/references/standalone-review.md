# Standalone Rust Production Review

Load this reference only for a directly requested broad, release-readiness, or whole-repository production review. The main skill owns residual dependency, unsafe, performance, simplification, validation, severity, and reporting.

## Review Order

Apply only relevant passes to scoped files and nearby contract owners.

### Build and configuration

- Verify the declared edition, MSRV, feature and target matrix, `cfg` agreement, generated code, build scripts, external consumers, and constrained environments.
- Check manifest dependency placement, feature additivity, package metadata, lint/safety enforcement, and publishing policy.
- Route workflow and recipe mechanics to `project-tooling-review`.

### Correctness and invariants

- State canonical invariants and examine empty, boundary, malformed, moved-from, degenerate, and adversarial states.
- Trace coordinated mutation, caches, indexes, topology, state machines, rollback, retries, inverse operations, and failure paths.
- Ensure public construction and mutation cannot store unsupported states or expose partial updates.

### Ownership, borrowing, and views

- Check canonical ownership, lifetime relationships, aliasing, interior mutability, detached handles, stale snapshots, clone-to-appease-borrowing patterns, and invalidation.
- Prefer borrowed views or owner-bound guards only when they make the invariant clearer than an intentional owned snapshot.

### Public API and compatibility

- Keep visibility and exports minimal; make ownership, mutation, absence, failure, generic constraints, and feature gating honest.
- Review builders and staged workflows from downstream call sites.
- Treat public types, trait implementations, errors, features, re-exports, panic behavior, and layout/FFI promises as compatibility surfaces.

### Error and panic contracts

- Keep recoverable failures typed and actionable; reserve panic for documented preconditions or impossible internal invariants.
- Preserve context through conversions and avoid string categories callers or tests must parse.
- Check errors after partial mutation and across process, task, callback, and FFI boundaries.

### Scientific and numerical behavior

- Establish the mathematical contract, units, dimensions, conventions, supported regimes, exact/approximate semantics, and failure behavior.
- Inspect stability, conditioning, overflow, non-finite values, degeneracy, tolerances, stochastic semantics, and reproducibility.
- Require independent known-value, exact, higher-precision, metamorphic, or external evidence.

### Concurrency and async

- Check Send/Sync intent, task and borrow lifetimes, blocking, cancellation, lock/channel design, atomic ordering, structured concurrency, determinism, and cross-task state observation.
- Do not recommend parallelism before the sequential invariant and measurement baseline are established.

### Implementation and maintainability

- Check iterator/control-flow clarity, exhaustiveness, allocation, complexity, naming/import hygiene, safe deletion, diagnostic overhead, and explanatory invariant/algorithm comments.
- Avoid style or abstraction rewrites without caller, correctness, or maintenance benefit.

### Tests and documentation

- Require strong unit, integration, doctest, property, fuzz, compile-contract, model, or regression evidence proportional to risk.
- Check precise assertions, exact error variants, deterministic randomness, failure injection, feature/target coverage, and realistic public examples.
- Document public error, panic, safety, feature, complexity, and scientific contracts where applicable.

## Standalone Validation Ladder

Choose repository-supported evidence appropriate to risk:

1. format, focused compile, lint, and affected tests
2. doctests, examples, external consumers, and docs
3. no-default, all, and curated feature combinations
4. declared MSRV and affected targets
5. property, fuzz regression, compile-fail, Miri, Loom, sanitizer, or FFI checks when established and relevant
6. independent scientific validators
7. representative before/after benchmarks after correctness passes
8. package/publish and full repository gates for release scope

Record omitted tiers and never present one configuration as proof of the full contract.
