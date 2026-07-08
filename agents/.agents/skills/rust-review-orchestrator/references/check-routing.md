# Changed-File Routing

Use this matrix after inspecting changed files. Prefer the smallest validator that covers the files touched by the current group. If a repository has stricter local guidance, follow the repository guidance.

## Scope Detection

Use read-only commands:

```bash
git --no-pager status --short
git --no-pager diff --stat
git --no-pager diff --name-status
git --no-pager diff
```

For staged-only requests, use the same commands with `--cached`.

Classify files by path and effect:

- `src/**/*.rs`: Rust library implementation or public API.
- `tests/**/*.rs`: Rust integration/property tests.
- `benches/**/*.rs`: benchmark harnesses or benchmark fixtures.
- `examples/**/*.rs`: public sample code.
- `Cargo.toml`, `Cargo.lock`, `.cargo/**`, `rust-toolchain.toml`, `rustfmt.toml`, `clippy.toml`: Cargo/toolchain surface.
- `justfile`, `.github/workflows/**`, config files: tooling or CI surface.
- `README.md`, `docs/**`, Rust doc comments: documentation surface.

## Skill Group Selection

| Changed surface | Select these groups |
|---|---|
| Public items, `pub` signatures, trait impls, re-exports, prelude modules, builders, doctests | Surface/API, Validation/Test, Final Synthesis |
| Constructors, validation APIs, invariant-bearing types, mutation workflows, rollback, snapshots, borrowed views | Invariant/Error, Implementation, Validation/Test, Final Synthesis |
| Error enums, error conversions, `Result` boundaries, diagnostic/report types | Invariant/Error, Surface/API, Validation/Test |
| Algorithmic geometry/topology/numerical code | Invariant/Error, Implementation, Validation/Test, Final Synthesis |
| Iterator/control-flow rewrites, allocation changes, naming/import cleanup | Implementation, Validation/Test |
| Tests/proptests/doctests only | Validation/Test, Implementation only if tests duplicate or obscure production behavior |
| Examples or benchmarks | Surface/API, Implementation, Validation/Test |
| Cargo manifests, features, lints, MSRV, package metadata | Validation/Test with `rust-cargo-hygiene`; Surface/API if feature-gated API changed |
| CLI binary, clap args, command output, CLI docs/examples | Surface/API with `rust-cli-design`, Validation/Test |
| Workflow/config only | No Rust skill group unless Rust behavior changed; run config validators |
| Docs-only repository prose | No Rust skill group unless Rust API docs changed; run docs validators |

## Focused Validators

Use the repository's documented commands when available. If no local guidance exists, use the generic Cargo fallbacks in this table.

| Files touched | Validator |
|---|---|
| Rust library source affecting core behavior | documented focused Rust check; fallback `cargo test --lib` plus `cargo clippy --all-targets --all-features -- -D warnings` |
| Rust unit tests only | documented narrow unit-test recipe; fallback `cargo test --lib` |
| Rust integration tests only | documented integration-test recipe; fallback `cargo test --tests` |
| Doctests or Rust API docs | documented doctest/docs recipe; fallback `cargo test --doc` |
| Examples | documented example validator; fallback `cargo check --examples` |
| Benchmarks or benchmark fixtures | benchmark smoke/check recipe or `cargo check --benches`; avoid performance claims unless optimizing |
| Cargo manifests/features/toolchain config | documented cargo-hygiene validators; fallback `cargo fmt --check`, `cargo clippy --all-targets --all-features -- -D warnings`, and targeted feature checks |
| GitHub workflows/YAML/config | documented config validators, `actionlint`, or YAML checks |
| Markdown/docs | documented docs validator, markdown lint, or link check |
| Python support scripts touched during Rust workflow | documented Python checks; fallback project pytest/ruff/mypy recipes if present |
| Notebook/paper artifacts touched | repository notebook or paper validators |

When a selected validator fails:

1. Treat the failure as part of the current group.
2. Fix the underlying issue.
3. Rerun the same validator.
4. Continue to the next skill only after the validator passes or the blocker is explicitly documented.

## Escalation To Full CI

Run the repository's full-CI validator when any of these are true:

- repository instructions explicitly require it for the touched files
- changes span multiple Rust layers and no smaller validator covers the combined risk
- public API and core invariant behavior changed together
- mutation/rollback/topology/numerical code changed in a way that could affect broad behavior
- final synthesis finds cross-cutting risk not covered by focused validators

Do not run full CI merely because the workflow is ending. Use focused validators for docs-only, config-only, tests-only, examples-only, benchmark-only, notebook-only, or paper-only changes when repository guidance allows them.

## Review Summary Template

Use this shape at handoff:

```text
Changed files:
- path: why it changed and which issue/skill finding it addressed

Review passes:
- Surface/API: skills run and notable outcomes
- Invariant/Error: skills run and notable outcomes
- Implementation: skills run and notable outcomes
- Validation/Test: skills run and notable outcomes
- Final Synthesis: remaining risk or none

Validation:
- command: pass/fail/blocked, with concise context

Git:
- No git state mutations performed.
```
