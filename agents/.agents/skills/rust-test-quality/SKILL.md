---
name: rust-test-quality
description: "Evaluate Rust code for test coverage, doctests, public API panic behavior, and documentation quality on changed code or whole-repo baseline audits when explicitly requested. USE FOR: Rust test review, public functions that panic for recoverable conditions, missing or trivial doctests on public APIs, missing /// docs on private helpers, weak assertions, missing boundary/error/negative cases, brittle or duplicated tests, doctest correctness vs actual behavior. DO NOT USE FOR: style/naming/import critique (use rust-style-hygiene), non-Rust code, or unrelated unchanged files unless a baseline audit is requested."
---

# rust-test-quality

Evaluate Rust code for test coverage, doctests, and documentation quality.

## Scope

Focus on:
- newly added or modified code
- public APIs
- supporting private helper functions

Ignore unrelated, unchanged code.

### Scope Modes

Default mode:
- Focus on newly added or modified Rust code.
- Ignore unrelated, unchanged code.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Evaluate all Rust source, tests, examples, benches, and doctests.
- Prioritize actionable gaps by public API risk, panic behavior, missing doctests, weak tests, and untested invariants.
- Do not require fixing every historical issue in one pass; report findings by priority and recommend focused follow-up patches.

---

## Requirements

### 1. Test Coverage

New functionality must include sufficient and reasonable tests.

A test suite is insufficient if it:
- only tests happy paths
- lacks boundary conditions
- does not test error handling
- does not validate invariants
- does not cover realistic usage patterns

Prefer:
- unit tests for core logic
- integration tests where behavior crosses modules

---

### 2. Public Functions (API Quality)

All public functions must include **doctests**.
Public functions should not panic for recoverable conditions. They should either be truly infallible or return `Result` / `Option`.

Doctests must:
- compile
- demonstrate intended usage
- reflect realistic inputs
- include edge cases when relevant

Flag:
- missing doctests
- trivial doctests that add no value
- examples that don't match actual behavior
- public API paths that can panic on recoverable input or state
- `unwrap`, `expect`, unchecked indexing, `assert!`, or `panic!` in public API paths unless they enforce a documented invariant that cannot be represented as a normal error
- undocumented panic preconditions

---

### 3. Non-Panicking Public Behavior

For public APIs, prefer recoverable behavior that callers can handle:

- return `Result` for errors with useful diagnostics
- return `Option` when absence is the only expected failure mode
- keep infallible functions genuinely infallible
- document any remaining panic as an invariant violation or explicit precondition

Tests and doctests should verify that recoverable bad inputs return `Err` / `None` instead of panicking.

---

### 4. Private Functions (Design Clarity)

All private functions must include `///` comments explaining:

- why the function exists (intent)
- what it does (behavior)

Reject:
- comments that restate the function name
- missing documentation on non-trivial helpers

---

### 5. Quality of Tests

Evaluate whether tests:

- assert meaningful outcomes (not just execution)
- validate invariants and correctness
- include negative / failure cases
- avoid duplication without abstraction
- are readable and maintainable

---

## Output Format

### Summary
- PASS
- NEEDS IMPROVEMENT
- FAIL

### Findings
- Bullet list of concrete, actionable issues

### Suggested Fixes
- Specific recommendations (e.g., "add boundary test for empty input")

### Optional Improvements
- Non-critical but valuable enhancements
