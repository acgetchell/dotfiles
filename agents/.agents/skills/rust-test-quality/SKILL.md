---
name: rust-test-quality
description: "Evaluate Rust code for test coverage, doctests, and documentation quality on changed code. USE FOR: Rust test review, missing or trivial doctests on public APIs, missing /// docs on private helpers, weak assertions, missing boundary/error/negative cases, brittle or duplicated tests, doctest correctness vs actual behavior. DO NOT USE FOR: style/naming/import critique (use rust-style-hygiene), non-Rust code, or unchanged files."
---

# rust-test-quality

Evaluate Rust code for test coverage, doctests, and documentation quality.

## Scope

Focus on:
- newly added or modified code
- public APIs
- supporting private helper functions

Ignore unrelated, unchanged code.

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

Doctests must:
- compile
- demonstrate intended usage
- reflect realistic inputs
- include edge cases when relevant

Flag:
- missing doctests
- trivial doctests that add no value
- examples that don't match actual behavior

---

### 3. Private Functions (Design Clarity)

All private functions must include `///` comments explaining:

- why the function exists (intent)
- what it does (behavior)

Reject:
- comments that restate the function name
- missing documentation on non-trivial helpers

---

### 4. Quality of Tests

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
