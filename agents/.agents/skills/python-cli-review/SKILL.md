---
name: python-cli-review
description: "Review general Python CLI and application code for correctness, user-facing behavior, privacy-sensitive output, parsing robustness, filesystem safety, and pytest coverage. USE FOR: Python command-line tools, single-file apps, parsers, date/time handling, local file import/export, stdout/stderr behavior, argparse/Click/Typer interfaces, and non-scientific application logic. DO NOT USE FOR: Python support tooling such as changelog/release/CI scripts (use python-support-scripts); numerical, geometric, statistical, or scientific code (use python-scientific-review); test-only quality audits (use python-test-quality); Rust code review; formatting-only cleanup; or unrelated unchanged code unless a baseline audit is requested."
---

# python-cli-review

Review Python CLI and small application code with a focus on behavior users can observe: correct parsing, reliable error handling, privacy-aware output, portable file I/O, and meaningful tests.

## Scope

Default mode:
- Review newly added or modified Python CLI/application code, its tests, and directly related docs or config.
- Ignore unrelated unchanged code unless needed to understand the changed behavior or local conventions.

Whole-repo baseline mode:
- Use only when the user explicitly asks for a whole-repo, entire-repo, or baseline audit.
- Audit CLI entry points, parsers, file readers/writers, output paths, error paths, and tests.
- Separate release-blocking behavior bugs from cleanup that can wait.

Use this skill for:
- `argparse`, Click, Typer, or hand-rolled CLI interfaces
- calendar, CSV, JSON, XML, SQLite, archive, or other local file parsing
- date/time ranges, timezone assumptions, filtering, sorting, grouping, and summaries
- stdout/stderr behavior, capture compatibility, and user-facing text
- privacy-sensitive local data such as meeting titles, attendees, locations, notes, paths, or records
- safe reads, atomic writes, temporary files, and malformed input handling
- pytest coverage for user-visible behavior and edge cases

Do not use this skill for:
- support tooling such as changelog generators, release helpers, benchmark runners, or CI scripts
- scientific/numerical/geometric Python
- Rust code review
- formatting-only changes

## Review Posture

Be direct and concrete. Assume the author knows Python. Focus on bugs, regressions, missing edge cases, and behavior that will surprise users or CI. Do not nitpick generic style unless it affects correctness, diagnostics, portability, privacy, or maintainability.

## Review Goals

### 1. CLI Contract And User Behavior

Check:
- documented flags and examples still match actual behavior
- defaults are stable and intentional
- invalid arguments fail with clear messages and non-zero exits
- stdout is reserved for intentional command output when another tool may consume it
- stderr/stdout choices are deliberate and tests reflect the contract

Flag:
- changed defaults not reflected in docs or tests
- traceback-prone error paths for normal user mistakes
- output shape changes that break scripts or documented examples
- mixed diagnostic and machine-readable output when the command is likely to be piped

### 2. Parsing And Input Robustness

Check:
- parsers handle documented formats and common export variants
- malformed, empty, partial, duplicate, or unexpected records fail loudly or are skipped intentionally
- errors name the offending file, field, row, event, or value when useful
- archive and database readers close resources reliably
- parsing is tolerant where product behavior requires it, but not so tolerant that arbitrary files are accepted

Flag:
- broad `except` blocks that hide corrupt input
- assuming optional columns, XML elements, headers, or calendar fields are always present
- treating decode, timezone, or date parse failures as valid empty data
- resource leaks around files, archives, database connections, or temporary files

### 3. Date, Time, Sorting, And Aggregation

Check:
- inclusive/exclusive date boundaries match docs and tests
- naive and timezone-aware datetimes are handled deliberately
- date parsing rejects ambiguous or unsupported formats with useful errors
- grouping, sorting, and tie-breaking are deterministic
- duration, recurrence, all-day events, missing end times, and negative ranges are handled intentionally when in scope

Flag:
- off-by-one day bugs at range boundaries
- timezone assumptions that silently shift events
- nondeterministic output order from dicts, sets, globs, SQL rows, or filesystem order
- summaries that double-count or drop records without tests

### 4. Privacy And Output Discipline

Check:
- raw imported records are not debug-printed or logged accidentally
- privacy-sensitive output is limited to intentional user-facing summaries
- file paths, attendee names, notes, locations, and meeting titles are exposed only when the CLI contract calls for it
- scanner suppressions or workarounds document intent narrowly without changing product behavior

Flag:
- new debug output of raw parsed data
- broad redaction that removes documented user-facing output
- writing private data to predictable temp paths or auxiliary files
- logging or printing more fields than the command promises

### 5. Filesystem Safety

Check:
- writes are atomic when replacing user files
- failed writes preserve existing output
- temporary files are cleaned up on success and failure
- input and output paths are validated enough to produce helpful errors
- code uses `pathlib.Path` and explicit encodings/newlines where text format matters

Flag:
- overwriting destination files before validation succeeds
- cleanup that can delete user-controlled broad paths
- relying on current working directory when callers can invoke the CLI elsewhere
- text I/O without explicit encoding for committed or portable outputs

### 6. Tests

Check:
- tests cover user-visible behavior, not just helper internals
- malformed inputs, empty inputs, boundary dates, output errors, and privacy-sensitive output paths have coverage
- fixtures are small, realistic, deterministic, and local
- tests avoid live network, current clock, local user data, and machine-specific paths unless explicitly controlled

Flag:
- tests that only assert no exception
- duplicated implementation logic in assertions
- missing regression tests for discovered bugs
- brittle tests that depend on absolute temp paths, wall clock time, locale, or filesystem ordering

### 7. Python Maintainability

Check:
- functions have clear responsibilities and type hints at non-trivial boundaries
- public helpers and CLI pathways have enough context in errors to debug failures
- global state and import-time side effects are avoided
- private helper tests are used only when behavior cannot be reached through a stable public path

Flag:
- mutable defaults
- swallowed exceptions
- ambiguous return values such as `None` meaning both "not found" and "parse failed"
- hidden dependency on patched globals, environment variables, or platform-specific streams

## Output Format

Start with a concise summary of overall quality and major risks.

Then group findings by severity:

### 🔴 Critical (must fix)
- User-visible correctness, data-loss, privacy leak, unsafe filesystem operation, or CI-blocking issues.

### 🟠 Important (should fix)
- Robustness, missing edge-case coverage, maintainability, or portability problems that should be addressed soon.

### 🟡 Improvements (nice to have)
- Non-blocking clarity, ergonomics, or test improvements.

For each finding, include the file and line, why it matters, and a minimal concrete fix. If there are no findings in a severity group, say `None`.
