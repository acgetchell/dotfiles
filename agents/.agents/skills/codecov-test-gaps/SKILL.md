---
name: codecov-test-gaps
description: "Use a Codecov report to identify and fix meaningful coverage gaps when coverage analysis or missing tests are requested."
---

# Codecov Test Gaps

Use coverage to locate missing behavioral evidence. Bind reports to their actual
commit before comparing them with current code. Review requests produce findings;
requests to add tests or fix gaps authorize relevant test edits and safe checks.
Production or coverage-policy changes need to be within the requested fix scope.
Never alter behavior or suppress real gaps merely to raise a percentage.

Start with patch coverage unless a whole-project audit is requested. Prioritize
public behavior, error paths, invariants, and affected integration boundaries.

- If the report is not supplied, read [report retrieval](references/report-retrieval.md).
- When thresholds, ignored paths, flags, or carryforward affect the interpretation,
  read [coverage policy](references/coverage-policy.md).
- For Rust or Python coverage-tool details, read the relevant part of
  [language guidance](references/language-guidance.md).

## Separate patch coverage from existing gaps

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
- partial-branch hits can come from language/runtime constructs rather than meaningful behavior. For example, Rust often reports partial branches from `match` arms, `?` desugaring, and `if let` fall-throughs; Python often reports narrow exception or platform branches. Do not chase 100% branch coverage when the missing branch is unreachable for valid inputs or would require brittle tests.

## Identify meaningful uncovered code

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

Respect existing exclusion markers in the source. Use the marker syntax supported by the repository's coverage tool. Common forms include:

- `// LCOV_EXCL_LINE`
- `// LCOV_EXCL_START` / `// LCOV_EXCL_STOP`
- `#[cfg(not(coverage))]` / `#[coverage(off)]` (nightly)
- `# pragma: no cover`
- `# pragma: no branch`

If a gap is not worth testing, explain why. Recommend an exclusion only when it accurately expresses coverage policy; low priority alone does not justify hiding executable code.

## Design tests from behavior, not lines

For each worthwhile gap:

- read the uncovered code and nearby existing tests
- infer the intended behavior from types, docs, fixtures, and call sites
- write tests that assert outcomes, invariants, or errors
- include boundary and negative cases when the uncovered branch represents them
- prefer the existing test style and fixture patterns
- keep tests deterministic
- avoid duplicating implementation logic in the assertion

Do not add tests that merely execute a line without checking behavior.

## Implement only appropriate tests

Before editing:

- confirm the test location and naming convention
- prefer small targeted tests over broad snapshot changes
- avoid changing production code unless the coverage review reveals a real bug and the user asked to fix it
- keep generated fixtures stable and minimal

After editing:

- run the targeted tests first
- rerun the repository's coverage command when feasible to mirror CI, such as `cargo llvm-cov --workspace --lcov --output-path lcov.info` for Rust or `pytest --cov --cov-report=xml` for Python
- run the repository's normal validation command when appropriate
- if coverage cannot be rerun locally, explain what was validated and what remains for CI/Codecov

## Report

Identify the report URL/artifact and commit, meaningful patch and existing gaps,
tests or policy changes made, validation results, and remaining limitations.
Include percentages only when the report supplies them. Explain skipped gaps
without manufacturing tests to fill a template.
