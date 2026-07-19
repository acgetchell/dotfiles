---
name: cpp-production-review
description: "Review modern C++20/C++23 source, headers, tests, and code-facing build configuration for production readiness. Use for standalone broad reviews or final synthesis across language and build contracts, correctness, API/ABI design, performance, portability, dependency migrations, deletion, and test quality. Route focused ownership, invariants, exception safety, scientific correctness, concurrency, and tests to their specialists when orchestrated; route build-system and CI mechanics to project-tooling-review."
---

# C++ Production Review

Review C++ as production code whose correctness, portability, and maintenance life matter. Follow the repository's declared standard; assume C++23 only when it is not specified.

Prioritize observable defects, undefined behavior, broken invariants, and release risks over stylistic churn. Prefer deletion and standard-library facilities when they reduce real complexity, but do not modernize code merely to demonstrate newer syntax.

## Ground Rules

- Read repository-local guidance before reviewing or editing.
- Do not mutate git state unless the user explicitly requests it.
- Honor a parent orchestrator's handed-off scope instead of silently narrowing it.
- In orchestrated final-synthesis mode, consume prior specialist evidence and do not rerun completed ownership, invariant, exception, scientific, concurrency, or test passes. Focus on residual language, build, dependency, API/ABI, portability, performance, deletion, and integration risks.
- Default to changed C++ files and the nearby code needed to understand their contracts.
- Use whole-repository baseline mode only when the user explicitly requests a repository-wide, release-readiness, or baseline audit.
- Keep diagnostic reviews read-only. When fixes are requested, make minimal fixes pass by pass and validate each pass before continuing.
- Verify current compiler, standard-library, dependency, and tool behavior from authoritative sources when currentness matters. Do not rely on memory for version claims.
- Treat passing compilation as necessary but insufficient evidence. Tests, sanitizers, static analysis, and invariant reasoning find different classes of defects.

## Scope and Trace

At the start, record:

- scope mode and the source, header, and test files in scope
- declared C++ standard and supported compiler/standard-library combinations
- build configurations and validators available locally and in CI
- dependency upgrades or removals under consideration
- untracked or user-owned work that must remain untouched

When invoked by a repository orchestrator, provide table-ready evidence naming the files inspected, pass groups applied, findings or explicit no-finding results, fixes, and validators.

## Review Order

In standalone mode, run applicable passes in this order. In orchestrated final-synthesis mode, skip passes already completed by specialists and apply only the residual portions. Complete the evidence and focused validation for one pass before moving to the next when edits are authorized.

### 1. Language, Build, and Dependency Contract

Establish what the code actually compiles against.

Check:

- targets request the declared C++ standard consistently and do not depend on accidental global flags
- the claimed minimum GCC, Clang, AppleClang, MSVC, libstdc++, and libc++ versions implement every used facility from that standard
- source files include what they use and do not receive dependencies through transitive includes
- public header, template, inline-variable, explicit-instantiation, and module definitions obey ODR, linkage, visibility, and ABI contracts across translation units
- preprocessor definitions, assertion settings, exception/RTTI settings, and release/debug differences do not silently alter correctness
- dependency APIs used by the code match the versions the build resolves
- compiler extensions are disabled unless deliberately required

For dependency upgrades:

1. Inventory every include and symbol used from each dependency.
2. Compare declared dependencies with actual target usage.
3. Read the upstream release notes, migration guide, and current API documentation.
4. Separate source migration, semantic behavior changes, and build-system changes.
5. Upgrade one dependency boundary at a time when practical.
6. Compile and test after each boundary change.
7. Remove a dependency only after all uses and transitive assumptions are gone.

Flag unpinned or externally hidden dependency resolution as a reproducibility risk, but leave registry and lockfile mechanics to project tooling.

### 2. Correctness, Lifetime, and Undefined Behavior

Treat undefined behavior and lifetime errors as release blockers.

Check:

- every object, reference, pointer, iterator, view, span, and callable wrapper has a valid lifetime
- container mutation cannot invalidate references or iterators that remain in use
- ownership is explicit and resources use RAII
- constructors establish complete valid states, and deletion through base interfaces is either supported by virtual destruction or deliberately prevented
- values are initialized on every path
- indexing, pointer arithmetic, shifts, signed overflow, narrowing, and size conversions are safe
- casts preserve alignment, aliasing, constness, and dynamic-type requirements
- lambdas do not outlive captured references
- exception paths, early returns, and allocation failures cannot leak resources or leave partial mutation
- C APIs, varargs, formatting, and raw memory operations use correct types and bounds
- assertions do not replace validation for reachable external input

Require a local safety argument for unavoidable raw ownership, placement construction, union tricks, FFI, or other code whose correctness is not apparent from the type system.

### 3. Invariants and State Transitions

Check:

- domain invariants are stated near the owning type and enforced at construction or mutation boundaries
- invalid states cannot be created by ordinary public API use
- coordinated fields update atomically from the caller's perspective
- failed operations preserve the prior valid state or document a deliberate destructive contract
- cached, derived, adjacency, orientation, indexing, topology, and bookkeeping state cannot drift from canonical storage
- sentinel values and magic integers are replaced by types or explicit optional state where that improves correctness

Trace mutation-heavy operations through complete success and failure paths. For graph, mesh, topology, or simulation code, review operation sequences rather than isolated calls.

### 4. Numerical and Scientific Robustness

Treat numerical behavior as correctness, not polish.

Check:

- units, dimensions, sign conventions, orientation, and boundary conditions are explicit and consistent
- integer counts and combinatorial expressions cannot overflow at supported problem sizes
- floating-point equality is used only when exact equality is intended
- tolerances are scale-aware and justified
- non-finite values, cancellation, underflow, overflow, and near-degenerate inputs are handled
- random-number engines and distributions have explicit ownership, seeding, reproducibility, and concurrency semantics
- parallel or reordered evaluation does not invalidate reproducibility claims
- tests use independent expected results where feasible rather than reimplementing the same algorithm

Do not endorse scientific claims solely because code compiles or regression snapshots remain unchanged.

### 5. API and Type Design

Review public and cross-module interfaces as long-lived contracts.

Check:

- public surface area is minimal and cohesive
- types encode important invariants and units
- ownership and nullability are visible in signatures
- `const`, value categories, forwarding, and move behavior match the contract
- parameters avoid unnecessary copies without introducing dangling views
- return values make failure and absence explicit
- exceptions, error values, and process termination have deliberate boundaries
- templates and concepts constrain the intended operations and produce actionable diagnostics
- inline definitions, explicit instantiations, module exports, symbol visibility, exception specifications, and layout exposure preserve intended ODR and ABI contracts
- virtual interfaces have correct destruction, override, and ownership semantics
- implementation details and storage layout are not exposed without need

Prefer simple value types and ordinary functions over elaborate abstraction. Do not force fluent, generic, or metaprogrammed designs where they obscure invariants.

### 6. Concurrency and Reentrancy

Apply when threads, task systems, parallel algorithms, global state, caches, or shared random-number generators are present.

Check:

- data-race freedom and happens-before relationships are demonstrable
- mutex scope and lock ordering avoid deadlocks and excessive contention
- atomics use the weakest correct ordering with a written invariant
- task lifetimes cannot outlive referenced state
- cancellation and exceptions cannot strand partial work
- logging, RNGs, caches, and singleton state are thread-safe or explicitly thread-confined
- parallelism preserves required ordering and determinism

Do not recommend parallelization before the sequential invariant and measurement baseline are sound.

### 7. Performance and Allocation

Make performance findings concrete.

Check:

- time and space complexity match expected workloads
- hot loops avoid accidental allocation, formatting, synchronization, virtual dispatch, and repeated lookup
- copies and moves of large structures are intentional
- containers and data layout fit dominant access patterns
- capacities are reserved when sizes are predictable
- views such as `std::span` or ranges improve traversal without creating lifetime hazards
- benchmarks isolate the operation and prevent optimization artifacts

Do not trade correctness or clarity for speculative micro-optimization. Require measurement for non-obvious performance rewrites.

### 8. Modern C++ Simplification and Deletion

Use facilities available under the repository's declared C++20/C++23 contract to remove complexity where support is real across the compiler matrix.

Consider standard facilities such as `std::span`, `std::string_view`, ranges, concepts, `std::expected`, `std::optional`, `std::variant`, `std::format`, `std::print`, `std::filesystem`, `std::chrono`, and scoped algorithms when they replace custom or third-party machinery cleanly.

Check before replacing:

- compiler and standard-library availability on every supported platform
- semantic differences, especially allocation, ownership, formatting, locale, time-zone, and error behavior
- performance and binary-size impact
- whether the existing dependency supplies functionality not covered by C++23

Identify and classify:

- unreachable or unbuilt source files
- commented-out implementations and stale feature branches embedded in code
- duplicate executables, wrappers, helpers, and tests
- declarations or dependencies with no actual use
- compatibility workarounds for unsupported compiler versions
- debug output or generated artifacts accidentally committed

Prefer deletion when a surface is unsupported, untested, and superseded. Preserve historically or scientifically important artifacts in documentation or release notes rather than keeping dead production paths.

### 9. Tests and Diagnostics

Check:

- tests assert behavior and invariants rather than merely execute code
- negative tests verify exit status or structured errors, not only matching output text
- deterministic unit tests cover empty, boundary, invalid, degenerate, and large inputs
- randomized tests record seeds and validate invariants after operation sequences
- regression tests exist for fixed defects
- concurrency tests do not depend on timing alone
- release and debug configurations both receive meaningful coverage
- warnings, sanitizer reports, and static-analysis findings fail validation rather than being marked successful
- logging does not hide errors, leak sensitive paths/data, or dominate hot loops

Use property, fuzz, or model-based testing for parsers, topology mutations, state machines, and serialization when their risk justifies it.

## Validation

Choose the strongest focused validators the repository already supports. For a release baseline, prefer:

1. clean configure and build with the primary supported compiler
2. complete tests with failures propagated
3. a second supported compiler or platform configuration
4. warnings-as-errors for project code where dependencies are isolated as system headers
5. AddressSanitizer plus UndefinedBehaviorSanitizer
6. ThreadSanitizer for concurrent code
7. MemorySanitizer or Valgrind where practical
8. clang-tidy, cppcheck, or the repository's static-analysis contract
9. release-mode smoke tests of shipped executables

Record commands, compiler and dependency versions, pass/fail status, and any validator intentionally not run. Do not claim platform support from a configuration file alone.

## Finding Severity

- **P0 — Release blocker:** build failure, undefined behavior, data race, memory/resource safety defect, invariant corruption, scientifically invalid result, or tests that cannot detect failure.
- **P1 — Must fix for production:** reachable wrong behavior, non-reproducible dependency/build contract, unsafe error handling, serious portability failure, or untested critical path.
- **P2 — High-value improvement:** meaningful API, maintainability, performance, diagnostic, or test improvement that need not block a preserved legacy release.
- **P3 — Optional:** low-risk cleanup or stylistic modernization. Keep this category small.

For every finding, provide file and line evidence, the failure scenario, why it matters, and the smallest credible remediation. Distinguish confirmed defects from hypotheses requiring a validator or platform that is unavailable.

## Final Report

Lead with unresolved P0/P1 findings. Include:

- release-readiness verdict
- findings ordered by severity with file/line evidence
- deletion and dependency-removal candidates, with proof still required
- dependency migration risks and source changes expected
- validators run and exact results
- supported-platform claims actually demonstrated
- intentionally deferred work and residual risk
- files changed, if fixes were authorized
- confirmation that no git state mutation occurred, when true
