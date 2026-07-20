---
name: cpp-test-quality
description: "Review doctest and CTest-based C++23 unit, integration, compile-contract, property, fuzz, sanitizer, benchmark, and example tests for meaningful behavior coverage, deterministic fixtures, independent assertions, and reliable failure diagnostics. Use when changes touch doctest BDD scenarios, CTest registration, public-header or template consumers, test data, fuzzers, sanitizer regressions, or tests for C++ production behavior."
---

# C++ Test Quality Review

Review C++ tests as executable evidence for behavior and invariants. Strengthen tests that can pass while the target behavior is wrong, and keep fixtures deterministic enough to reproduce failures.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Use doctest as the C++ test framework, CTest as the registration/execution layer, CMake for test targets, and `just` as the maintainer command surface. Do not add another test framework unless the user explicitly changes this contract.
- Honor repository-local naming, exact recipe/preset names, filters, labels, and sanitizer configuration.
- Prefer changed tests plus the production behavior and risk they claim to cover.
- Prefer doctest behavior-driven development for domain behavior, state transitions, and regression scenarios. Express the contract as `SCENARIO` / `GIVEN` / `WHEN` / `THEN`, using `AND_*` clauses only when they improve the narrative.
- Use ordinary doctest cases or templates when BDD would add ceremony to table-driven algorithms, compile-time properties, fuzz/property harnesses, benchmarks, or narrow crash regressions.
- Maintain a validation ledger keyed by source state, built binary, compiler/library/configuration, instrumentation, and selected test IDs. Never rerun a test whose evidence is still valid.
- Keep CI wiring and command-surface mechanics under `project-tooling-review`; this skill owns the semantic quality of C++ tests.
- Keep header self-containment, ODR/linkage, module-build, and supported-matrix correctness under `cpp-build-portability`; this skill owns whether durable compile-contract tests detect regressions in those guarantees.

## Audit Workflow

### 1. Identify the risk under test

For each changed behavior, name the defect or invariant the test should detect. Require assertions on observable behavior, exact state deltas, error semantics, or independently derived properties—not merely construction success, lack of a crash, or a generic `is_valid()` result.

Structure behavioral tests so the scenario states one user- or domain-visible contract:

- `GIVEN` establishes only the relevant preconditions
- `WHEN` performs the action under review
- `THEN` and `AND_THEN` assert precise observable outcomes, including unchanged state or failure semantics

Keep shared setup outside nested clauses only when doctest's subcase re-entry semantics remain correct and inexpensive.

Use doctest `REQUIRE*` assertions only for prerequisites whose failure makes later evaluation unsafe or meaningless, such as invalid handles, missing fixtures, or failed construction. Use `CHECK*` for independent `THEN` postconditions so one mismatch does not hide the rest of the observable state.

### 2. Cover success, rejection, and failure

Check for:

- minimal successful examples with precise expected outcomes
- invalid, inapplicable, and boundary inputs
- every meaningful rejection or error path
- failure atomicity and unchanged-state guarantees
- empty, singleton, degenerate, large, nonfinite, and overflow-adjacent inputs where relevant
- copy, move, destruction, invalidation, and exception paths for resource-bearing code

For state transitions, assert independent snapshots or canonical properties before and after the operation.

### 3. Use strong scientific oracles

For numerical, geometric, combinatorial, or stochastic behavior, prefer:

- analytically known values
- independent reference implementations or trusted library results
- metamorphic, inverse, round-trip, and conservation properties
- exact combinatorial counts and incidence relationships
- tolerances derived from the contract and scale

Do not share the same production helper between implementation and expected result when that would reproduce the same bug.

### 4. Make randomness and concurrency reproducible

Require explicit deterministic seeds or repository-owned deterministic RNG instances. Report failing seeds and shrink or minimize failing cases when property tools support it. Avoid timing-only assertions and uncontrolled sleeps in concurrency tests; prefer barriers or controlled scheduling hooks.

### 5. Check harness reliability

Verify:

- assertions cannot be compiled out accidentally
- death, exception, and process-exit tests observe the intended failure
- parameterized tests actually cover distinct cases
- fixtures clean up resources and do not leak order dependence
- test discovery and filters include the new tests
- sanitizer jobs propagate test failures and do not silently disable relevant instrumentation
- benchmark assertions do not confuse performance measurement with correctness coverage

Generated fixtures should have a documented owner and deterministic regeneration path.

### 6. Test compile-time and consumer contracts

When public headers, templates, concepts, overloads, deduction guides, modules, or ABI-facing declarations change, check:

- a minimal external consumer can include or import the public surface without hidden in-repository context or transitive includes
- compile-pass cases exercise intended overload selection, concept satisfaction, deduction, value categories, move-only types, and supported customization
- `static_assert`, `requires` expressions, type traits, and `noexcept` checks encode precise compile-time contracts where appropriate
- compile-fail cases prove rejected uses only when the harness expects compilation failure reliably; assert the stable constraint or error category rather than complete compiler-specific diagnostic prose
- multi-translation-unit or module-consumer tests expose ODR, linkage, visibility, and explicit-instantiation defects when those risks are present

Do not treat an ordinary runtime test's successful compilation as sufficient evidence for a public compile-time contract.

### 7. Validate

Before running any test, decide whether repository policy or the known scope
requires an indivisible full gate. Inspect the `just` recipe and enumerate the
doctest/CTest selection it executes so the full gate can be chosen initially
when required. Otherwise use the narrowest recipe that supplies new evidence,
backed by the declared CMake/CTest preset. After a build-only recipe establishes
the binary, use one direct doctest or CTest selection when no focused recipe
exists:

- a named test case or test executable while iterating
- the affected compile-pass, compile-fail, header-consumer, or module-consumer target
- the affected CTest label or suite
- ASan/UBSan for memory and undefined-behavior regressions
- TSan for concurrency regressions on supported platforms
- property or fuzz replay for discovered counterexamples

Do not run a named case, its containing suite, its containing CTest entry, and a full gate in sequence. Choose the smallest selection that proves the change. If broader coverage is independently required, exclude tests already recorded as passing or choose the broader selection initially. Check registration without execution using CTest discovery/listing.

If an indivisible policy-mandated gate is discovered only after overlapping
tests have passed and it offers no reliable exclusion, report the validation
and command-surface conflict and route it to `project-tooling-review`; do not
silently replay the tests or count the duplicate execution as new evidence.

Rerun a test only after relevant source, fixture, build, or configuration changes invalidate its result, or to diagnose suspected nondeterminism. The same logical test under a different compiler, standard library, sanitizer, linkage mode, or material configuration is distinct evidence rather than a duplicate.

Keep doctest discovery deliberate. Never add a filtered `add_test()` entry that reruns scenarios already covered by another CTest entry merely for reporting or convenience. Use direct doctest filters for focused local runs. Use `doctest_discover_tests()` only as an intentional registration design that replaces or remains disjoint from existing entries and justifies its configuration and cross-compilation costs.

## Finding Standard

For each finding, state what incorrect implementation could still pass, the missing assertion or input class, the minimal stronger test, and the command that demonstrates it.

## Handoff

Summarize doctest scenarios and consumer contracts inspected and changed, risks covered, independent oracles, deterministic seeds, compile-pass or compile-fail evidence, the validation ledger and non-overlapping `just`/CTest/sanitizer results, remaining gaps, and confirmation that no git state mutations were performed when true.
