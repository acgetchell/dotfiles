---
name: cpp-test-quality
description: "Review C++ unit, integration, property, fuzz, sanitizer, benchmark, and example tests for meaningful behavior coverage, deterministic fixtures, independent assertions, and reliable failure diagnostics. Use when changes touch doctest, Catch2, GoogleTest, CTest, test data, fuzzers, sanitizer regressions, or tests for C++ production behavior."
---

# C++ Test Quality Review

Review C++ tests as executable evidence for behavior and invariants. Strengthen tests that can pass while the target behavior is wrong, and keep fixtures deterministic enough to reproduce failures.

## Ground Rules

- Do not mutate git state unless the user explicitly asks in the current turn.
- Honor repository-local test frameworks, naming, recipes, and sanitizer configuration.
- Prefer changed tests plus the production behavior and risk they claim to cover.
- Do not rewrite a test framework for style. Fix weak evidence with the project's existing framework unless migration is independently justified.
- Keep CI wiring and command-surface mechanics under `project-tooling-review`; this skill owns the semantic quality of C++ tests.

## Audit Workflow

### 1. Identify the risk under test

For each changed behavior, name the defect or invariant the test should detect. Require assertions on observable behavior, exact state deltas, error semantics, or independently derived properties—not merely construction success, lack of a crash, or a generic `is_valid()` result.

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

### 6. Validate

Use the repository's narrowest documented command first:

- a named test case or test executable while iterating
- the affected CTest label or suite
- ASan/UBSan for memory and undefined-behavior regressions
- TSan for concurrency regressions on supported platforms
- property or fuzz replay for discovered counterexamples

Then run the broader affected test tier when shared fixtures, test registration, or core behavior changed.

## Finding Standard

For each finding, state what incorrect implementation could still pass, the missing assertion or input class, the minimal stronger test, and the command that demonstrates it.

## Handoff

Summarize tests inspected and changed, risks covered, independent oracles and deterministic seeds used, validators and results, remaining gaps, and confirmation that no git state mutations were performed when true.
