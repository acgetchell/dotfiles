---
name: python-support-scripts
description: "Review Python development, release, benchmark, fixture, CI, diagnostic, and generated-artifact scripts for transformation correctness, determinism, safe subprocess orchestration, malformed tool output, atomic publication, and release-day failure behavior. Use for changelog generators, release helpers, benchmark runners, Cargo or GitHub tooling, and repository automation. Route user applications, scientific algorithms, packaging semantics, boundary models, and test design to focused skills."
---

# Python Support Scripts

Review Python that supports development and releases. Treat these scripts as part of the release surface: broken transforms, flaky ordering, unsafe subprocesses, and partial artifact publication can invalidate CI or releases.

## Scope And Boundaries

Use changed-code mode by default. Use whole-repository mode only when requested.

- Own development-tool transformations, deterministic rendering, external command orchestration, generated artifacts, release diagnostics, and support-script failure semantics here.
- Route substantial public application contracts to `python-cli-review`.
- Route invariant-bearing structured inputs to `python-parse-dont-validate` when they warrant domain models rather than local parse checks.
- Route scientific algorithms and scientific oracle design to `python-scientific-review`.
- Route build artifact and installed-package semantics to `python-build-portability`.
- Route general test mechanics to `python-test-quality` and workflow command wiring to `project-tooling-review`.

## Review Workflow

1. Identify inputs, consumers, generated artifacts, external commands, and release consequences.
2. Trace parse, transform, render, and publish stages separately.
3. Exercise malformed and empty tool output before reviewing CLI polish.
4. Check repeatability across machines and reruns.
5. Verify failures preserve prior valid artifacts and enough diagnostics for release pressure.

## Transform And Render Correctness

Check:

- parsers recognize every supported input form and reject malformed ambiguity
- transform rules match version, changelog, benchmark, coverage, fixture, or metadata conventions
- renderers produce schemas and syntax accepted by downstream consumers
- parse-transform-serialize composition is tested with representative fixtures
- unknown categories and future fields follow an explicit compatibility policy
- generated files have one source of truth

Flag permissive regular expressions, string concatenation for strict formats, silent partial parsing, and output validation performed only by rereading with the same flawed parser.

## Determinism And Reproducibility

Sort filesystem, set, mapping, and external-command results before committed output unless semantic order is already defined. Derive dates and versions from explicit inputs rather than the wall clock. Fix locale, timezone, encoding, and machine-readable command modes when parsing external output.

Keep absolute paths, usernames, temporary roots, process IDs, nondeterministic hashes, and host metadata out of committed artifacts. Make reruns idempotent or document intentional replacement behavior.

## Subprocess Discipline

Use argument arrays rather than interpolated shells. Check return status, preserve stderr/stdout context, set a timeout when a hang can block automation, and pass deterministic environment values when output is parsed.

Do not log tokens, signing material, GitHub credentials, or private payloads. Distinguish command absence, timeout, nonzero exit, malformed output, and empty-but-valid output when callers need different actions.

Avoid catching `CalledProcessError` only to discard its command and diagnostics. Keep publish, upload, tag, or release effects behind explicit intent and dry-run support where appropriate.

## Artifact Publication And Cleanup

Validate complete output before replacing an existing artifact. Use temporary files and atomic replacement where failure must preserve the prior result. Scope cleanup to explicit generated paths and avoid broad globs or unresolved environment variables.

Check archive contents, permissions, encodings, newlines, metadata, and output directories. Ensure a failed multi-artifact operation does not leave a misleading mixture of old and new results.

## Support CLI Contract

Keep support entry points configurable and discoverable. Provide useful help, meaningful exit codes, machine-readable stdout when consumed by automation, and diagnostics on stderr. Require dry-run or explicit confirmation for publish/destructive behavior.

Load `python-cli-review` only when the command exposes a substantial stable application contract beyond this support workflow.

## Evidence

Prefer small committed input/output fixtures, golden files for strict rendering, parametrized malformed cases, property tests for parsers/version logic, and safe command fakes at the subprocess boundary. Avoid live GitHub, network, wall-clock, or current-repository state in unit tests.

Load `python-test-quality` when fixtures or evidence structure changed or is materially weak. Run safe `--help` and dry-run smoke checks when relevant.

## Output

Lead with release/CI breakage, nondeterminism, unsafe execution, or data-loss risks. For each finding, name the input, transformation, consumer, failure consequence, and smallest fix. Report artifacts protected, commands validated, effects deliberately not executed, and remaining external limitations.
