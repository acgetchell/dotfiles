---
name: rust-production-review
description: "Perform a senior-level Rust review for production-quality, performance-critical libraries with strong invariants on changed code or whole-repo baseline audits when explicitly requested. USE FOR: comprehensive Rust code review, systems programming review, computational geometry, topology, linear algebra, numerical algorithms, invariant-heavy data structures, public library API design, semver-sensitive changes, performance-critical correctness review, numerical robustness, ownership/mutability design, concurrency safety, and maintainability. DO NOT USE FOR: surface-only style/naming/import cleanup (use rust-style-hygiene), focused error variant audits (use rust-error-variants), focused test/doctest audits (use rust-test-quality), focused prelude/export audits (use rust-prelude-exports), focused trait-bound cleanup (use rust-trait-bounds), non-Rust code, generated code, or unrelated unchanged code unless a baseline audit is requested."
---

# rust-production-review

Review Rust code as a production-quality, performance-critical library intended for expert users and long-term semver stability.

Prioritize correctness and invariants over surface style. Performance matters, but never at the expense of soundness, numerical robustness, or a public API that is hard to misuse.

## Scope

Focus on newly added or modified Rust code that affects:

- algorithms with global invariants
- computational geometry, topology, linear algebra, numerical computing, graph algorithms, or systems-level data structures
- public APIs and semver-relevant behavior
- mutation-heavy state transitions
- performance-critical kernels or hot paths
- concurrency, parallel iteration, shared state, or global caches
- safety-critical code paths, especially panics or any `unsafe`

Use related focused Rust skills when the review narrows to a specialized concern, but keep this skill for broad production readiness and design review.

### Scope Modes

Default mode:
- Review newly added or modified Rust code and nearby invariants needed to assess it.
- Ignore unrelated unchanged code unless it defines the invariant, API, or performance contract the change relies on.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Review the full Rust library surface: public APIs, core invariants, mutation paths, numerical algorithms, hot paths, panic/error boundaries, and semver-relevant module organization.
- Prioritize findings by correctness, invariant preservation, numerical robustness, recoverable panics, API misuse risk, and performance complexity.
- Do not require fixing every historical issue in one pass; produce a prioritized remediation plan with focused follow-up patches.

## Review posture

Assume the author is an experienced Rust developer. Be direct and precise. Do not explain basic Rust concepts. Focus on findings that materially improve correctness, robustness, maintainability, performance, or API stability.

Do not approve a change just because it compiles or tests pass. Ask whether invalid states can be constructed, whether invariants survive all operation sequences, and whether downstream users can rely on the API for years.

## Review goals

### 1. Correctness and invariants

This is the highest priority.

Check:

- core invariants are explicitly represented, enforced, or documented
- topology, ordering, orientation, adjacency, manifold, graph, dimensional, or algebraic invariants cannot silently drift
- edge cases are handled: empty inputs, singleton inputs, degenerate geometry, duplicate points, boundary cases, invalid indices, non-finite floats, and precision-sensitive cases
- public operations cannot leave structures partially updated or invalid after early returns or errors
- assumptions are enforced at the right boundary with types, constructors, validation, assertions, or documented preconditions
- mutation APIs preserve invariants across every observable state transition

Flag:

- unchecked assumptions that can be violated by valid public API usage
- operations that update related fields in separate steps without rollback or validation
- invariants only implied by comments or tests but not enforced by the implementation
- accepting invalid inputs and relying on later code to fail
- logic that is correct only for a narrow happy path but exposed as general-purpose

### 2. Numerical robustness

For numerical, geometric, or algebraic code, review floating-point behavior as a correctness concern.

Check:

- comparisons involving floats avoid naive equality unless exact equality is truly intended
- epsilon tolerances are justified by scale and algorithmic context
- predicates are stable near degeneracy
- overflow, underflow, cancellation, rounding, and non-finite values are considered
- integer arithmetic cannot overflow in release builds when sizes, indices, or counts grow
- exact arithmetic, adaptive precision, or robust predicates are considered when orientation/incircle/intersection/order decisions affect topology

Flag:

- fixed epsilon constants used across unrelated scales
- sorting or deduplication that assumes total ordering over floats without handling NaN
- geometric predicates whose wrong sign can corrupt global structure
- numeric casts that truncate, wrap, or lose semantic range
- tests that avoid near-degenerate cases

### 3. API and abstraction design

Review public APIs as long-term contracts.

Check:

- the public surface is minimal, coherent, and hard to misuse
- types encode invariants where practical
- constructors validate invariants before exposing values
- responsibilities are separated between data representation, validation, algorithms, and presentation
- visibility is no broader than necessary
- semver implications are understood for public types, trait impls, error variants, feature flags, and re-exports

Flag:

- unnecessary `pub` exposure
- leaky abstractions that expose internal indexing, storage layout, or algorithm phases without a stability reason
- APIs that require callers to maintain internal invariants manually
- broad mutable access to fields that must remain coordinated
- public APIs that panic for recoverable conditions instead of returning `Result` or `Option`

### 4. Ownership, borrowing, and mutability

Ownership should make invalid states harder to express, not merely satisfy the borrow checker.

Check:

- mutability is minimized and scoped to the smallest region possible
- borrowed values do not outlive the invariants they depend on
- lifetimes communicate real relationships rather than compiler workarounds
- temporary cloning or allocation is justified
- interior mutability is used only when it improves the model, not to bypass design constraints

Flag:

- `RefCell`, `Cell`, `Mutex`, `RwLock`, or global state used to sidestep ownership without a clear invariant story
- cloning large structures to appease the borrow checker
- APIs that expose mutable references to internals whose consistency depends on other fields
- complex lifetime signatures that suggest the abstraction boundary is wrong

### 5. Performance and complexity

Performance review should be concrete: identify complexity, data movement, allocations, and likely hot paths.

Check:

- Big-O complexity of key operations matches the intended use case
- allocations, copies, hashing, sorting, and dynamic dispatch are necessary
- data layout is cache-friendly for expected traversal patterns
- indices and handles are chosen deliberately
- inlining, const generics, stack allocation, small-vector patterns, or preallocation would materially help
- benchmark coverage exists for changed hot paths

Flag:

- accidental quadratic behavior
- repeated allocation inside loops
- avoidable `clone`, `collect`, boxing, string formatting, or dynamic dispatch on hot paths
- storing data in layouts that fight the dominant access pattern
- performance changes without benchmarks or complexity discussion

### 6. Concurrency and parallelism

Only recommend parallelism when it preserves invariants and improves realistic workloads.

Check:

- shared mutable state is absent, synchronized, or deliberately partitioned
- caches, global registries, random number generators, and feature flags are thread-safe
- types should or should not be `Send` / `Sync`
- deterministic behavior is required and preserved
- Rayon or similar parallel iteration is appropriate for the algorithm's dependency structure

Flag:

- hidden global coupling that prevents safe parallel execution
- parallel mutation that can observe intermediate invalid states
- nondeterministic ordering that affects numerical or topology results
- adding Rayon before proving the sequential algorithm and invariants are correct

### 7. Error handling and safety

Recoverable failures should be explicit and actionable.

Check:

- public APIs return `Result` or `Option` for recoverable conditions
- errors preserve enough structured context to debug
- panic paths are reserved for impossible internal invariants or documented preconditions
- partial mutations are not left behind after errors
- no new `unsafe` is introduced

Flag:

- `unwrap`, `expect`, unchecked indexing, or `panic!` reachable through recoverable public inputs
- string-only errors where callers need typed handling
- error paths that discard key context
- `unsafe` blocks, `unsafe fn`, raw pointer manipulation, unchecked indexing, or FFI without a compelling reason and a documented safety argument

If existing `unsafe` is in scope, treat it as exceptional: require a local safety comment, narrow unsafe boundary, tests around invariants, and a clear explanation for why safe Rust is insufficient.

### 8. Testing strategy

Tests should protect invariants, not only examples.

Check:

- unit tests cover local logic and edge cases
- integration tests exercise public API behavior
- doctests demonstrate semver-relevant usage
- property tests check invariants over generated inputs
- parameterized tests cover families of boundary cases
- fuzzing or randomized testing is considered for parsers, topology mutations, geometry predicates, and state machines
- regression tests exist for discovered degeneracies or bug-prone sequences

Flag:

- tests that only check happy paths or `is_ok()`
- tests using only well-conditioned numeric inputs
- missing tests for operation sequences that could break global invariants
- no benchmark coverage for performance-sensitive changes

### 9. Diagnostics and observability

Committed diagnostics should be structured and filterable.

Check:

- library, test, example, and benchmark diagnostics use `tracing` or a project-approved structured logging facade instead of direct `stdout`/`stderr` writes
- benchmark and test diagnostics are feature-gated when the project has diagnostic flags such as `bench-logging` or `diagnostics`
- logging, formatting, allocation, or error-wrapping helpers are kept out of benchmark hot loops and measured closures
- diagnostics preserve useful typed context without replacing returned errors

Flag:

- committed `println!`, `eprintln!`, or direct `std::io::{stdout, stderr}` writes used for diagnostics instead of tracing
- logging in Criterion-measured closures or performance-critical kernels
- feature-gated diagnostics that silently change non-diagnostic behavior

### 10. Documentation and maintainability

Complex code needs maintainable explanations at the invariant and algorithm level.

Check:

- invariants are documented near the types and mutation APIs that rely on them
- algorithm comments explain why the approach is correct, not just what each line does
- public docs state preconditions, error behavior, and complexity when relevant
- modules are decomposed around coherent responsibilities
- helper functions make invariant-preserving steps explicit

Flag:

- monolithic functions mixing validation, mutation, algorithmic logic, and formatting
- comments that restate code while omitting key invariants
- hidden coupling between fields or modules
- public behavior that is discoverable only by reading tests or implementation

## Output Format

### Critical Issues (must fix)
- Correctness, invariant, soundness, safety, or semver problems that should block merging.

### High-Value Improvements
- Changes that materially improve robustness, maintainability, diagnostics, or long-term API quality.

### Performance Opportunities
- Complexity, allocation, data layout, cache behavior, benchmark, or hot-path recommendations.

### API Design Feedback
- Public surface, abstraction boundaries, visibility, mutability, and misuse-resistance feedback.

### Testing Gaps
- Missing unit, integration, doctest, property, fuzz, randomized, regression, or benchmark coverage.

### Optional / Nitpicks
- Non-blocking cleanup only. Keep this section short and avoid surface style unless it affects clarity.
