# Language Guidance

## Language-specific guidance

- **Rust** projects commonly use `cargo-llvm-cov`.
  - typical artifacts: `target/llvm-cov/` and `lcov.info`
  - prefer `cargo llvm-cov --workspace --lcov --output-path lcov.info` locally to mirror CI
  - assert error variants and invariants, not just `is_ok()`
  - partial branch hits often come from `match` arms, `?` operator desugaring, and `if let` fall-throughs; treat unreachable arms as candidates for `unreachable!()` with a documented invariant or for an exclusion marker rather than a test
  - prefer doctests on public API to cover the documented contract
- **Python** projects commonly use `coverage.py`, `pytest-cov`, and `coverage.xml`.
  - prefer the repository's declared command, such as `just coverage`, `uv run pytest --cov`, or `coverage run -m pytest && coverage xml`
  - use `coverage report -m` or the terminal output from `pytest-cov` to map uncovered lines before editing tests
  - prioritize parser, CLI, file I/O, serialization, date/time, and error-path behavior over tests that merely execute branches
  - use `# pragma: no cover` or `# pragma: no branch` only for genuinely unreachable, platform-specific, or defensive code after explaining why a behavior test would be brittle
  - for genuinely numerical Python, defer to `python-scientific-review`; for support scripts, defer to `python-support-scripts`

When the coverage gap overlaps a specialized review skill (`rust-test-quality`, `python-scientific-review`, etc.), apply that skill's principles without losing focus on the Codecov report.
