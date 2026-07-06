---
name: python-support-scripts
description: "Review Python support scripts and dev tooling that live alongside Rust crates on changed code or whole-repo baseline audits when explicitly requested: changelog generators, benchmark runners, release helpers, CI scripts, and fixture/diagnostic utilities. USE FOR: Python that parses commit messages, runs cargo bench/Criterion and aggregates results, generates CHANGELOG.md, scrapes GitHub Actions logs, prepares release artifacts, runs subprocess commands, manipulates Cargo metadata, validates fixtures, or stitches together CI workflows. Focus on transform/parse correctness, determinism, fixture-driven tests, malformed-input handling, subprocess discipline, and CLI ergonomics. DO NOT USE FOR: numerical/geometric/scientific algorithms, NumPy/SciPy correctness, or scientific reproducibility (use python-scientific-review); Rust code review (use rust-production-review or other Rust skills); generic Python web/app code; formatting-only cleanup; unrelated unchanged code unless a baseline audit is requested."
---

# python-support-scripts

Review Python that exists to support a Rust crate's development workflow: changelog generators, benchmark runners, release helpers, CI scripts, fixture utilities, and diagnostic CLIs.

These scripts are not user-facing scientific code, but they are still part of the project's release surface. A broken changelog generator or a flaky benchmark runner causes real damage on release day. The bar is correctness, determinism, and resilience to messy inputs, not algorithmic depth.

## Scope

Focus on newly added or modified Python that:

- parses commit messages, git logs, or GitHub Actions output
- generates `CHANGELOG.md` or release notes
- runs `cargo bench` / Criterion and aggregates JSON results
- prepares release artifacts (tarballs, signed assets, docs uploads)
- prepares reproducible paper, PDF, figure, or generated documentation artifacts
- manipulates `Cargo.toml`, `Cargo.lock`, or workspace metadata
- runs subprocess commands such as `cargo`, `gh`, `git`, or `rsync`
- generates fixtures or diagnostic reports for the Rust crate
- stitches together CI workflows or pre-commit checks

Ignore unrelated unchanged code unless reviewing it surfaces a real bug in the changed surface.

### Scope Modes

Default mode:
- Review newly added or modified Python support scripts, fixtures, tests, and CI-facing utilities.
- Ignore unrelated unchanged tooling unless it defines conventions or helper APIs used by the changed code.

Whole-repo baseline mode:
- Use when the user explicitly says "whole repo", "entire repo", "baseline audit", or similar.
- Audit all Python support scripts, their tests, fixtures, command-line entry points, subprocess boundaries, and committed generated-output paths.
- Prioritize findings by release/CI breakage risk, parser/renderer correctness, nondeterminism, unsafe subprocess behavior, malformed-input handling, and weak fixture coverage.
- Do not require fixing every historical tooling issue in one pass; separate release blockers from maintainability cleanup.

## Review posture

Be direct. Assume the author knows Python and Rust. Skip basic Python style commentary; focus on correctness, determinism, and how the script fails when inputs go wrong.

## Review goals

### 1. Transform and parse correctness

The interesting bugs live in input parsing and output rendering, not in glue code.

Check:

- parsers handle every documented input shape, including the malformed cases the script will see in the wild
- output renderers produce the format consumers (Codecov, crates.io, release-plz, git-cliff) actually accept
- round-trips compose: parse → transform → serialize matches the expected output for fixture inputs
- version computation, semver bumping, type/scope categorization, and section assignment match the project's commit/changelog conventions

Flag:

- regex parsers that succeed silently on bad input
- string concatenation building output that consumers parse strictly
- changelog logic that depends on commit message wording it does not actually validate

### 2. Determinism

Support scripts are usually run in CI and locally; the outputs need to match.

Check:

- iteration order is stable: sort lists, sort dict keys when serializing, do not depend on `set` iteration
- timestamps are absent or come from explicit inputs (commit dates, release tags), not `datetime.now()`
- absolute paths and machine-specific values do not leak into committed output
- random seeds, if any, are explicit
- subprocess output is parsed deterministically (`--porcelain`, `--json`, `LC_ALL=C` when relevant)
- dates used in committed artifacts come from explicit inputs and are parsed/formatted without relying on the process locale

Flag:

- `os.listdir`, `Path.glob`, or `set` iteration feeding committed output without sorting
- timestamps in changelog entries that change between runs
- locale-sensitive sorting or formatting on user-facing output
- `datetime.strptime(..., "%B ...")` or similar locale-dependent parsing for English month names in CI/reproducible artifact paths; prefer ISO dates or an explicit month-name map plus UTC-aware datetimes

### 3. Error and edge handling

Bad inputs should fail loudly with useful context, not silently produce wrong output.

Check:

- empty inputs, missing fields, unknown commit types, unparseable versions, and malformed JSON are handled explicitly
- error messages name the offending file, line, commit, or value
- exit codes distinguish "nothing to do" from "real failure"
- partial writes leave no half-rendered output behind (write to temp file, rename)

Flag:

- bare `except` or swallowed exceptions
- `try/except: pass` around parsing
- functions that return `None` for both "no match" and "error"
- writes that overwrite the destination before validation succeeds

### 4. Subprocess discipline

Most support scripts shell out to `cargo`, `git`, `gh`, or similar.

Check:

- subprocesses use argument lists, never `shell=True` with interpolated values
- failures are captured with the failing command, exit code, stdout, and stderr in the error message
- timeouts are set when a hang would block CI
- environment is set explicitly when output is parsed (e.g., `LC_ALL=C`, `GIT_PAGER=cat`)
- no Codecov / GitHub / signing tokens are logged

Flag:

- `subprocess.run(cmd, shell=True)` with f-strings
- `check=True` without surfacing stderr in the raised exception
- silent `subprocess.run(...)` whose result is ignored

### 5. CLI ergonomics

Support scripts have to be invokable both by humans and by CI.

Check:

- `argparse` (or equivalent) with explicit `--help`
- `--dry-run` for anything that writes or publishes
- separation between machine-parseable output (stdout) and human logs (stderr)
- exit codes are documented and meaningful
- `-q`/`-v` levels are handled by `logging`, not by `print`

Flag:

- scripts that require editing the source to change behavior
- scripts that mix log noise into stdout that another tool parses
- destructive defaults (deleting, force-pushing, force-publishing) without `--dry-run`

### 6. Tests and fixtures

For these scripts, tests are mostly fixture-driven.

Prefer:

- committed fixture inputs (small commit logs, Criterion JSON snippets, partial Cargo.toml) under `tests/fixtures/`
- tests that compare rendered output to a committed expected file (golden tests)
- property tests on commit-message parsing and version computation when input variation is the main risk
- pytest parametrization across fixture pairs

Flag:

- tests that only check `is_not_empty()` or `returncode == 0`
- tests that regenerate fixtures from live `git`/`gh` calls
- tests dependent on the network, the current clock, or ambient environment variables
- coverage of `argparse` boilerplate and `__main__` dispatch instead of the parsing/rendering core

### 7. Path and encoding handling

Scripts run on multiple OSes and from multiple CI environments.

Check:

- `pathlib.Path` everywhere, no string path concatenation
- explicit `encoding="utf-8"` on file reads/writes that are not binary
- newline handling is intentional when output is committed (consider `newline=""`)
- writes are scoped to the project tree, not user-controlled paths

### 8. Code structure and types

Keep the code easy to maintain after release pressure.

Check:

- transformation logic is in small functions that take and return data, not side effects
- script entry points (`main()` / `if __name__ == "__main__":`) are thin
- structured records use `dataclass`, `TypedDict`, or `NamedTuple` instead of opaque dicts
- type hints are present on public functions
- mutable defaults are avoided

## Output format

### Summary
Concise overall quality and major risks before release.

### 🔴 Critical (must fix)
- Correctness, determinism, data-loss, or unsafe-execution issues that should block merging.

### 🟠 Important (should fix)
- Robustness, test quality, or maintainability problems that should be addressed soon.

### 🟡 Improvements (nice to have)
- Non-blocking improvements that would make the script clearer or easier to maintain.

Provide concrete code suggestions where applicable. Avoid praise unless it highlights a strong pattern worth preserving.
