# Standalone C++ Production Review

Load this reference only for a directly requested broad, release-readiness, or whole-repository production review. The main skill owns residual dependency, performance, simplification, deletion, validation, severity, and reporting; do not duplicate those steps here.

## Review Order

Apply each relevant pass to the scoped files and nearby contract owners. Complete focused evidence for one pass before moving to the next when fixes are authorized.

### Language and build contract

- Confirm each target enforces C++23 and does not depend on accidental global flags.
- Use target-based CMake, checked-in presets, vcpkg manifest mode, and `just`; report divergence instead of introducing another build/dependency workflow.
- Check direct includes, public-header self-containment, target usage requirements, compiler extensions, and supported compiler/library facilities.
- Check ODR, linkage, visibility, explicit instantiation, modules, configuration macros, exception/RTTI/assertion modes, static/shared builds, and debug/release agreement.
- Route command, preset, CI, package-registry, and tool-pin mechanics to `project-tooling-review`.

### Correctness, lifetime, and undefined behavior

- Verify object, pointer, reference, iterator, view, span, callback, and handle lifetimes.
- Check invalidation across container mutation and deferred execution.
- Require RAII and explicit ownership; inspect early returns, exceptions, allocation failure, and cleanup.
- Check initialization, bounds, pointer arithmetic, overflow, narrowing, shifts, casts, alignment, aliasing, raw memory, C APIs, and formatting types.
- Require a local safety argument for unavoidable raw ownership, placement construction, unions, FFI, or similar type-system escapes.

### Invariants and state transitions

- State domain invariants near their owning types and reject invalid public construction or mutation.
- Trace coordinated fields, caches, adjacency, orientation, indexing, topology, and bookkeeping through success and failure.
- Verify failed operations preserve the prior valid state or document a deliberate weaker contract.
- Review graph, mesh, topology, and simulation operation sequences rather than isolated calls.

### Numerical and scientific behavior

- Check units, dimensions, signs, orientation, boundaries, combinatorial overflow, and supported problem sizes.
- Require justified scale-aware tolerances and deliberate treatment of non-finite, degenerate, cancellation, underflow, and overflow cases.
- Make RNG ownership, seeding, reproducibility, distribution behavior, and concurrency explicit.
- Prefer independent expected results, analytical values, metamorphic properties, or trusted references over duplicated production logic.

### Public API and type design

- Keep surfaces cohesive and minimal; encode important units, ownership, nullability, absence, and failure honestly.
- Check value categories, conversions, overloads, concepts, diagnostics, virtual destruction, exposed layout, symbol visibility, and compatibility promises.
- Avoid unnecessary abstraction, genericity, fluent protocols, metaprogramming, or implementation exposure.
- Review representative external consumers and distinguish source, behavior, and binary compatibility.

### Exception and error contracts

- Identify each failure channel and promised no-throw, strong, basic, or weaker guarantee.
- Trace rollback, partial mutation, cleanup, error translation, `noexcept`, special members, callbacks, and non-throwing ABI boundaries.
- Ensure assertions and termination are reserved for documented fatal conditions, not reachable external rejection.

### Functional composition and control flow

- Check algorithm, range, view, lambda, and result-type pipelines for lifetime, laziness, repeated traversal, evaluation order, allocation, error loss, and hidden side effects.
- Keep an imperative loop when it expresses mutation, cleanup, ordering, or failure atomicity more clearly.

### Concurrency and reentrancy

- Demonstrate data-race freedom, happens-before relationships, lock ordering, atomic invariants, task lifetime, cancellation, and exception propagation.
- Check logging, RNGs, caches, callbacks, and singleton state for thread safety or explicit confinement.
- Require the sequential invariant and measurement baseline before recommending parallelism.

### Tests and diagnostics

- Require tests that assert behavior and invariants, including rejection, boundary, degenerate, failure-atomicity, and regression cases.
- Check deterministic seeds, independent scientific oracles, compile-time consumer contracts, release/debug coverage, and nonzero failure propagation.
- Use property, fuzz, or model-based testing for parsers, topology mutations, state machines, or serialization when risk justifies it.
- Ensure warnings, sanitizer reports, and static-analysis findings fail validation rather than being reported as success.

## Standalone Validation Ladder

Choose the strongest repository-supported evidence appropriate to the risks:

1. clean configure and primary supported build
2. focused and complete affected tests
3. a second supported compiler, standard library, platform, or configuration
4. project warnings-as-errors where dependencies are isolated
5. ASan plus UBSan
6. TSan for concurrent code
7. MSan where the fully instrumented standard-library/dependency contract is sound
8. clang-tidy and repository Semgrep analysis
9. release-mode smoke tests of shipped executables

Record every omitted tier and never present one compiler or configuration as proof of the full support matrix.
