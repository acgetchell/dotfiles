---
name: codecov-test-gaps
description: "Review the latest GitHub Actions run for .github/workflows/codecov.yml, inspect the Codecov/coverage report, and add missing tests when uncovered code represents meaningful behavior; supports whole-repo coverage baseline audits when explicitly requested. USE FOR: Codecov report review, latest codecov.yml workflow run, coverage regression investigation, uncovered lines/branches, missing tests from CI coverage, GitHub Actions coverage artifacts, adding tests to improve coverage, deciding whether a coverage gap is worth testing. DO NOT USE FOR: generic test review without Codecov data (use language-specific test-quality skills), writing superficial coverage-only tests, changing production code solely to satisfy coverage, unrelated CI failures, or repositories without a Codecov workflow unless the user asks to adapt the workflow."
---

# codecov-test-gaps

Review the latest `.github/workflows/codecov.yml` run, identify meaningful coverage gaps from the Codecov or coverage report, and add missing tests only when they improve confidence in real behavior.

The goal is not to chase coverage percentages. Use coverage as a signal to find untested behavior, error paths, invariants, and integration boundaries.

## Scope Modes

Default mode:
- Start from the current branch, PR, or latest relevant Codecov run.
- Prioritize patch coverage and existing gaps directly related to the current change.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Treat full project coverage as the primary signal, not only patch coverage.
- Audit uncovered source, tests, examples, benches, and report configuration across the whole repository when artifacts expose them.
- Prioritize existing gaps by public API risk, invariant/error-path importance, release relevance, and likelihood that a test would improve confidence.
- Do not require filling every historical coverage gap in one pass; propose focused test batches and skip low-value coverage chasing with a reason.

## Workflow

### 1. Confirm the coverage setup

Start by inspecting the repository:

- verify `.github/workflows/codecov.yml` exists
- read the workflow to identify test commands, the `cargo llvm-cov` invocation, artifact names, upload steps, flags, and paths
- check for `codecov.yml`, `.codecov.yml`, and the `lcov.info` artifact produced by `cargo-llvm-cov`
- identify the language test framework from project files instead of assuming one

If the workflow is missing or renamed, search `.github/workflows/` and explain the mismatch before proceeding.

### 2. Audit `codecov.yml` itself

`codecov.yml` (or `.codecov.yml`) defines what "good coverage" means for the project. Read it before reviewing the report so findings align with the policy that is actually enforced.

Check:

- `coverage.status.project` and `coverage.status.patch` thresholds, including `target`, `threshold`, and `informational`
- `coverage.range` (the color band shown in the UI)
- `flags` and per-flag carryforward, used for matrix builds (OS variants, feature combinations)
- `component_management` definitions when subsystems have different policies
- `ignore:` blocks that exclude paths from coverage entirely
- `comment` configuration so the PR comment exposes the right information

Flag:

- thresholds set so loose that regressions never fail the check
- `ignore:` entries that hide code which should be tested
- carryforward that masks broken matrix legs
- thresholds in `codecov.yml` that disagree with the project's stated policy

When the right answer is to update `codecov.yml` rather than write a low-value test, propose the YAML change explicitly.

### 3. Fetch the relevant Codecov context

Pick the report that matches the task. Prefer most-specific to least-specific:

1. **Open PR for the current branch.** This is the right view for release-prep work because Codecov highlights patch coverage and the project delta against the base.
   - `gh pr view --json number,headRefName,headRefOid,statusCheckRollup,comments,url`
   - read the Codecov bot comment for patch coverage, project delta, and per-file gaps
   - `gh api repos/:owner/:repo/commits/<sha>/status` for the Codecov status check
2. **Latest completed branch run.** Use this when there is no PR yet.
   - `gh run list --workflow codecov.yml --branch <branch> --limit 5 --json databaseId,status,conclusion,headBranch,headSha,displayTitle,createdAt,url`
3. **Latest completed run on `codecov.yml`.** Fall back to this when the task is not branch-specific.

For the chosen run:

- inspect with `gh run view <run-id> --log` and `gh run view <run-id> --json artifacts,jobs,conclusion,url`
- download coverage artifacts with `gh run download <run-id> --dir <tmp-dir>` when artifacts exist (typically `lcov.info`)
- record the commit SHA the report was generated from so findings reference the right code

Do not require or print Codecov tokens. If a private Codecov report cannot be accessed, rely on workflow artifacts/logs and ask the user for a report link only if necessary.

### 4. Separate patch coverage from existing gaps

A single coverage percentage hides two different questions. Answer them in order:

1. **Is the patch covered?** New or modified lines on this branch should be exercised by new or existing tests. Patch coverage failures are usually the most actionable and should be addressed before release.
2. **Are pre-existing gaps worth filling now?** Older uncovered code may or may not be relevant to the current change. Touch it only when:
   - the release surfaces it as user-facing
   - the gap is in the same module as the patch
   - the gap protects an invariant the release affects

Report patch and existing gaps separately so the user can decide where to spend effort.

When reading the report:

- treat "coverage drop X%" and "file at Y%" as separate signals
- look at branch coverage and partial branches, not just lines
- partial-branch hits in Rust often come from `match` arms, `?` desugaring, and `if let` fall-throughs; do not chase 100% branch coverage on idiomatic control flow when the missing branch is unreachable for valid inputs

### 5. Identify meaningful uncovered code

Use the report to locate uncovered files, lines, branches, and partial branches.

Prioritize:

- newly changed code (patch coverage)
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

Respect existing exclusion markers in the source. With `cargo-llvm-cov` the relevant forms are:

- `// LCOV_EXCL_LINE`
- `// LCOV_EXCL_START` / `// LCOV_EXCL_STOP`
- `#[cfg(not(coverage))]` / `#[coverage(off)]` (nightly)

If a gap is not worth testing, say why and recommend either an exclusion marker in the source or a `codecov.yml` `ignore:` entry instead of adding a low-value test.

### 6. Design tests from behavior, not lines

For each worthwhile gap:

- read the uncovered code and nearby existing tests
- infer the intended behavior from types, docs, fixtures, and call sites
- write tests that assert outcomes, invariants, or errors
- include boundary and negative cases when the uncovered branch represents them
- prefer the existing test style and fixture patterns
- keep tests deterministic
- avoid duplicating implementation logic in the assertion

Do not add tests that merely execute a line without checking behavior.

### 7. Implement only appropriate tests

Before editing:

- confirm the test location and naming convention
- prefer small targeted tests over broad snapshot changes
- avoid changing production code unless the coverage review reveals a real bug and the user asked to fix it
- keep generated fixtures stable and minimal

After editing:

- run the targeted tests first
- run `cargo llvm-cov` (e.g., `cargo llvm-cov --workspace --lcov --output-path lcov.info`) when feasible to mirror CI
- run the repository's normal validation command when appropriate
- if coverage cannot be rerun locally, explain what was validated and what remains for CI/Codecov

## Language-specific guidance

- **Rust** is the primary target for this skill; the project uses `cargo-llvm-cov`.
  - typical artifacts: `target/llvm-cov/` and `lcov.info`
  - prefer `cargo llvm-cov --workspace --lcov --output-path lcov.info` locally to mirror CI
  - assert error variants and invariants, not just `is_ok()`
  - partial branch hits often come from `match` arms, `?` operator desugaring, and `if let` fall-throughs; treat unreachable arms as candidates for `unreachable!()` with a documented invariant or for an exclusion marker rather than a test
  - prefer doctests on public API to cover the documented contract
- **Python** when the same workflow also covers Python tests: most Python in this project is support tooling (changelog generators, benchmark runners, CI helpers), so testing should focus on parse/transform logic against committed fixtures, deterministic output, and malformed-input handling rather than numerical tolerances. For genuinely numerical Python, defer to `python-scientific-review`; for support scripts, defer to `python-support-scripts`.

When the coverage gap overlaps a specialized review skill (`rust-test-quality`, `python-scientific-review`, etc.), apply that skill's principles without losing focus on the Codecov report.

## Output format

### Coverage source
- Workflow run URL or ID, or PR Codecov comment / status used
- Commit SHA the report was generated from
- Branch / PR number reviewed
- Report/artifact source used

### Patch coverage
- Patch coverage percentage and the threshold from `codecov.yml`
- Uncovered lines/branches in the changed code
- Whether each gap was filled, excluded, or deferred and why

### Existing coverage gaps reviewed
- Pre-existing uncovered code touched by this review
- Why it was in scope for the current task
- Decision: tested, excluded, or deferred

### Changes made
- Tests added or updated
- Behavior/invariants covered
- `codecov.yml` updates, if any (with rationale)
- Source-level exclusion markers added, if any (with rationale)

### Validation
- Commands run
- Pass/fail result
- Any coverage rerun limitations

### Follow-ups
- Remaining coverage gaps
- Suggested future tests, exclusions, or `codecov.yml` adjustments
