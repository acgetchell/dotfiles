---
name: python-test-quality
description: "Evaluate Python tests and Python code for meaningful pytest coverage, behavior assertions, fixture quality, CLI/file I/O boundaries, parser/date-time edge cases, and error-path testing on changed code or whole-repo baseline audits when explicitly requested. USE FOR: Python test review, missing pytest cases, weak assertions, brittle fixtures, coverage gaps that need behavior tests, CLI output capture, tmp_path/monkeypatch/capsys usage, parametrized boundary tests, exception and malformed-input coverage. DO NOT USE FOR: numerical/scientific correctness (use python-scientific-review); Rust-adjacent support scripts and release tooling (use python-support-scripts); Codecov report triage itself (use codecov-test-gaps); formatting-only cleanup; unrelated unchanged code unless a baseline audit is requested."
---

# python-test-quality

Evaluate Python tests for behavioral value, maintainability, and risk coverage.

The goal is confidence, not high coverage for its own sake. Prefer tests that prove user-visible behavior, invariants, error handling, and integration boundaries.

## Scope

Default mode:
- Focus on newly added or modified Python source, tests, fixtures, and CLI behavior.
- Read nearby tests first and follow the repository's style.
- Ignore unrelated unchanged code unless it defines conventions used by the changed surface.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit Python source, tests, fixtures, CLI entry points, and coverage configuration across the repository.
- Prioritize by public/user-facing risk, parser/file I/O fragility, missing negative cases, weak assertions, nondeterminism, and fixture brittleness.
- Do not require fixing every historical gap in one pass; group findings into focused follow-up batches.

## Review Priorities

### 1. Behavior Coverage

Tests should exercise outcomes users or callers depend on.

Flag:
- tests that only execute code without asserting results
- happy-path-only tests for code that has meaningful branches
- missing boundary cases for empty, single-item, duplicate, min/max, and invalid inputs
- missing regression tests for reported bugs
- tests that duplicate implementation logic instead of asserting observable behavior

Prefer:
- assertions on returned values, emitted files, stdout/stderr, exit codes, exceptions, and state changes
- small parametrized tests for input variation
- regression tests named after the behavior they protect

### 2. Error Paths and Malformed Inputs

Bad inputs should fail predictably and with useful diagnostics.

Check:
- invalid files, malformed rows/JSON/YAML/TOML, missing fields, empty inputs, and permission-like failures
- exception type and message when diagnostics matter
- CLI exit codes and stderr for user-facing failures
- partial-write behavior for commands that modify files

Avoid:
- broad `pytest.raises(Exception)`
- swallowing errors only to assert that no crash occurred
- brittle exact-message assertions when a stable substring is enough

### 3. Fixtures and Test Data

Fixtures should make behavior easier to see, not hide it.

Prefer:
- small inline data for simple cases
- committed fixtures only when realistic structure matters
- `tmp_path` for filesystem writes
- `monkeypatch` for environment variables, current working directory, network calls, and time seams
- factories when multiple tests need related variants

Flag:
- oversized fixtures where the relevant field is hard to find
- tests that depend on the user's machine, home directory, locale, timezone, current date, or network
- mutation of shared fixture data across tests
- generated expected output that is not asserted against a stable value

### 4. CLI, File I/O, and Output

Command-line and file boundaries are common regression points.

Check:
- stdout and stderr separately with `capsys` or subprocess capture
- exit codes for success and failure
- `tmp_path` usage for all writes
- explicit encodings for text files
- deterministic ordering when output lists files, records, or keys
- no secrets or raw sensitive records in logs or test failure output

Prefer testing the CLI through the repository's established entry point when output formatting or argument parsing is part of the behavior. Test core logic directly when argument parsing is incidental.

### 5. Time, Dates, and Parsing

Date/time and parser code needs edge coverage.

Check:
- timezone-aware and timezone-naive inputs when both are accepted
- date-only versus datetime inputs
- boundary ranges and inclusive/exclusive endpoints
- DST-sensitive behavior only when the code explicitly handles timezones
- CSV quoting, delimiter variation, missing optional fields, and unknown extra fields

Keep tests deterministic by passing explicit dates/times instead of relying on `now()`.

### 6. Test Design Quality

Good tests should fail for one understandable reason.

Flag:
- large tests that cover many behaviors with one assertion
- excessive mocking of the function under test's collaborators
- snapshot/golden tests that obscure the intended contract
- tests coupled to private implementation details when public behavior is available
- duplicated setup that would be clearer as a fixture or helper

Prefer:
- arrange/act/assert structure when it improves readability
- descriptive test names
- one primary behavior per test
- targeted helpers for repetitive setup, not assertion logic

### 7. Coverage Gaps

When reviewing uncovered lines, decide whether a test would add real confidence.

Test:
- public behavior
- parser branches
- file I/O and CLI branches
- negative cases and diagnostics
- historical bugs

Skip or recommend exclusion for:
- defensive branches unreachable through valid inputs
- platform-specific fallbacks not practical in the current environment
- debug-only paths
- boilerplate dispatch

Use `# pragma: no cover` or `# pragma: no branch` sparingly, and only with a short reason in the review or patch summary.

## Output Format

### Summary
- PASS, NEEDS IMPROVEMENT, or FAIL
- One or two sentences naming the main risk.

### Findings
- Concrete issues ordered by severity.
- Include file and line references when available.
- Explain the missing behavior, not just the missing line.

### Suggested Tests
- Specific pytest cases, fixtures, or parametrizations to add.
- Mention when no test is worth adding and why.

### Validation
- Commands run and pass/fail result.
- Any coverage or environment limitations.
