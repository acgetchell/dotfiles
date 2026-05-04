---
name: codecov-test-gaps
description: "Review the latest GitHub Actions run for .github/workflows/codecov.yml, inspect the Codecov/coverage report, and add missing tests when the uncovered code represents meaningful behavior. USE FOR: Codecov report review, latest codecov.yml workflow run, coverage regression investigation, uncovered lines/branches, missing tests from CI coverage, GitHub Actions coverage artifacts, adding tests to improve coverage, deciding whether a coverage gap is worth testing. DO NOT USE FOR: generic test review without Codecov data (use language-specific test-quality skills), writing superficial coverage-only tests, changing production code solely to satisfy coverage, unrelated CI failures, or repositories without a Codecov workflow unless the user asks to adapt the workflow."
---

# codecov-test-gaps

Review the latest `.github/workflows/codecov.yml` run, identify meaningful coverage gaps from the Codecov or coverage report, and add missing tests only when they improve confidence in real behavior.

The goal is not to chase coverage percentages. Use coverage as a signal to find untested behavior, error paths, invariants, and integration boundaries.

## Workflow

### 1. Confirm the coverage setup

Start by inspecting the repository:

- verify `.github/workflows/codecov.yml` exists
- read the workflow to identify test commands, coverage generators, artifact names, upload steps, flags, and paths
- check for `codecov.yml`, `.codecov.yml`, `coverage.xml`, `lcov.info`, `tarpaulin`, `cargo-llvm-cov`, `grcov`, `pytest-cov`, `nyc`, or other coverage tooling
- identify the language test framework from project files instead of assuming one

If the workflow is missing or renamed, search `.github/workflows/` and explain the mismatch before proceeding.

### 2. Fetch the latest Codecov workflow run

Use GitHub CLI when available:

- `gh run list --workflow codecov.yml --limit 5 --json databaseId,status,conclusion,headBranch,headSha,displayTitle,createdAt,url`
- prefer the latest completed run for the current branch when the task is branch-specific
- otherwise use the latest completed run for `.github/workflows/codecov.yml`
- inspect the run with `gh run view <run-id> --log` and `gh run view <run-id> --json artifacts,jobs,conclusion,url`
- download coverage artifacts with `gh run download <run-id> --dir <tmp-dir>` when artifacts exist

If the Codecov report is available through a PR comment or status, inspect it:

- `gh pr view --json comments,statusCheckRollup,headRefName,headRefOid`
- `gh api repos/:owner/:repo/commits/<sha>/status`
- Codecov status links or report URLs from workflow logs

Do not require or print Codecov tokens. If a private Codecov report cannot be accessed, rely on workflow artifacts/logs and ask the user for a report link only if necessary.

### 3. Identify meaningful uncovered code

Use the report to locate uncovered files, lines, branches, and partial branches.

Prioritize:

- newly changed code
- public APIs and documented behavior
- error handling paths
- boundary conditions
- branch conditions that encode invariants
- serialization/deserialization, parsing, file I/O, and CLI behavior
- numerical, geometric, or state-machine edge cases
- integration boundaries where regressions are likely

Deprioritize or skip:

- generated code
- dead or deprecated code already marked for removal
- debug-only logging
- defensive impossible branches that would require brittle tests
- platform-specific guards that cannot run in the current environment
- trivial accessors or boilerplate where a test adds no real confidence

If a gap is not worth testing, say why instead of adding a low-value test.

### 4. Design tests from behavior, not lines

For each worthwhile gap:

- read the uncovered code and nearby existing tests
- infer the intended behavior from types, docs, fixtures, and call sites
- write tests that assert outcomes, invariants, or errors
- include boundary and negative cases when the uncovered branch represents them
- prefer the existing test style and fixture patterns
- keep tests deterministic
- avoid duplicating implementation logic in the assertion

Do not add tests that merely execute a line without checking behavior.

### 5. Implement only appropriate tests

Before editing:

- confirm the test location and naming convention
- prefer small targeted tests over broad snapshot changes
- avoid changing production code unless the coverage review reveals a real bug and the user asked to fix it
- keep generated fixtures stable and minimal

After editing:

- run the targeted tests first
- run the relevant coverage command if available and reasonably fast
- run the repository's normal validation command when appropriate
- if coverage cannot be rerun locally, explain what was validated and what remains for CI/Codecov

## Language-specific guidance

Use the repository's conventions. For common cases:

- Rust: prefer meaningful unit/integration/doctests; assert variants and invariants, not just `is_ok()`
- Python: prefer deterministic pytest/Hypothesis tests; seed randomness; handle numerical tolerances carefully
- JavaScript/TypeScript: prefer behavior-level tests and branch coverage for user-visible paths

When the coverage gap overlaps a specialized review skill, apply that skill's principles without losing focus on the Codecov report.

## Output format

### Coverage source
- Workflow run URL or ID
- Commit/branch reviewed
- Report/artifact source used

### Findings
- Uncovered files/lines or branches considered
- Which gaps are worth testing and why
- Which gaps were skipped and why

### Changes made
- Tests added or updated
- Behavior/invariants covered

### Validation
- Commands run
- Pass/fail result
- Any coverage rerun limitations

### Follow-ups
- Remaining coverage gaps
- Suggested future tests or exclusions if applicable
