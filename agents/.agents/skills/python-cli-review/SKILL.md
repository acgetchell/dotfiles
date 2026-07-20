---
name: python-cli-review
description: "Review Python CLI and small application behavior for argument contracts, exit status, stdout and stderr, privacy-sensitive output, date and time semantics, local file workflows, and user-visible failures. Use for argparse, Click, Typer, command front ends, import/export applications, and machine-consumed command output. Route invariant-bearing raw input parsing, support tooling, scientific code, packaging, and test design to their focused skills."
---

# Python CLI Review

Review behavior users and calling tools can observe. Focus on stable command contracts, useful failures, privacy-aware output, and safe application effects.

## Scope

Use changed-code mode by default. Inspect changed entry points, application workflows, directly related documentation, and nearby contract owners. Use whole-repository mode only when explicitly requested.

## Ownership Boundaries

- Own arguments, defaults, exit status, stdout/stderr, user-facing diagnostics, application date/time behavior, privacy, and local file workflows here.
- Route raw structured input and invariant-bearing values to `python-parse-dont-validate`.
- Route changelog, release, benchmark, CI, fixture, and diagnostic tooling to `python-support-scripts` unless it exposes a substantial user-facing application contract.
- Route mathematical behavior to `python-scientific-review`, installation and entry-point construction to `python-build-portability`, and test design to `python-test-quality`.

## Review Workflow

1. Identify documented users, calling scripts, machine-readable modes, files, and side effects.
2. Compare changed behavior with help text, examples, exit codes, and output contracts.
3. Trace invalid input and operational failures to their observable diagnostic and resulting state.
4. Verify privacy and filesystem behavior before recommending ergonomic cleanup.
5. Run focused command or application evidence without invoking destructive or external effects.

## Command Contract

Check:

- flags, positional arguments, defaults, aliases, and examples agree
- invalid arguments fail clearly with nonzero status
- normal user mistakes do not produce irrelevant tracebacks
- stdout contains intentional command results when callers may pipe or parse it
- stderr contains diagnostics and progress unless the documented format says otherwise
- machine-readable output has a stable schema, ordering, encoding, and newline policy
- deprecated options have an intentional compatibility path

Flag silent default changes, output-shape drift, mixed logs and structured output, ambiguous exit status, and commands that require source edits for ordinary configuration.

## Application Semantics

Trace filtering, sorting, grouping, aggregation, and date/time behavior when they are part of the user contract.

Check inclusive and exclusive boundaries, timezone-aware versus naive values, daylight-saving assumptions when relevant, recurrence and missing-value behavior, deterministic tie-breaking, and empty results. Avoid reliance on ambient locale, current time, filesystem order, set order, or undocumented current working directory.

## Privacy And Diagnostics

Check that logs, exceptions, progress output, and debug paths do not expose secrets or unintended private records such as titles, attendees, locations, notes, local paths, or imported data. Preserve deliberate user-requested output; do not confuse privacy with suppressing the command's purpose.

Ensure diagnostics name the offending file, record, field, or value when useful without dumping entire sensitive payloads.

## File And Process Effects

Check:

- reads and writes use explicit paths and encodings
- replacements are atomic when failure must preserve prior output
- validation finishes before destructive or externally visible effects
- temporary artifacts are private and cleaned on success and failure
- resources close across exceptions and early returns
- subprocess invocations use safe argument lists, bounded execution where appropriate, and useful failure context
- cleanup cannot target broad or user-controlled paths accidentally

Route package-resource and installed-entry-point failures to the build specialist. Route complex reusable subprocess orchestration for development tools to the support-script specialist.

## Maintainability

Prefer thin entry points that delegate to typed, side-effect-conscious functions. Avoid import-time effects, mutable defaults, swallowed exceptions, process-global mutation, and ambiguous `None` results that combine absence with failure.

Keep public behavior reachable through stable seams. Do not require callers or tests to patch private globals merely to supply time, environment, paths, or services.

## Evidence

Prefer repository commands and targeted behavior tests. Safe evidence can include help output, explicit success/failure invocations against temporary data, separate stdout/stderr assertions, stable exit codes, malformed input, boundary dates, atomic-write failure, and privacy-sensitive diagnostics.

Load `python-test-quality` when test artifacts changed or when evidence quality is itself in question. Do not load it solely because focused tests should run.

## Output

Lead with user-visible correctness, data-loss, privacy, or compatibility blockers. For each finding, cite the file and line, explain the observable contract, and propose the smallest fix. Report commands run, effects avoided, and remaining external or platform limitations.
