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

- `*.py`, `src/**/*.py`, `scripts/**/*.py`, `tools/**/*.py`: Python implementation, CLI, support tooling, or scientific code.
- `tests/**/*.py`, `test_*.py`, `*_test.py`, `conftest.py`: pytest surface, fixtures, and test helpers.
- `notebooks/**/*.ipynb`, `*.ipynb`: notebook source, outputs, and execution hygiene.
- `pyproject.toml`, `uv.lock`, `requirements*.txt`, `setup.cfg`, `tox.ini`, `noxfile.py`, `mypy.ini`, `.python-version`, `.ruff.toml`, `ruff.toml`, `ty.toml`, `pyrightconfig.json`: Python packaging, dependency, lint, format, and type-check surface.
- `data/**`, `fixtures/**`, `tests/fixtures/**`, `examples/**`: fixtures, examples, generated reference data, and interoperability artifacts.
- `justfile`, `.github/workflows/**`, config files: tooling or CI surface.
- `README.md`, `docs/**`, notebook markdown, and CLI examples: documentation surface.

## Skill Group Selection

| Changed surface | Select these groups |
|---|---|
| `.ipynb` notebooks, notebook execution helpers, notebook dependency groups, committed outputs | Notebook/Reproducibility, then any domain group implied by code cells, Validation/Test |
| CLI entry points, argparse/Click/Typer, stdout/stderr, local file import/export, date/time parsing, privacy-sensitive output | Boundary/Application, Validation/Test |
| JSON/CSV/TOML/YAML/env/subprocess parsing, dataclasses/attrs/Pydantic models, raw dicts or primitives with invariants | Boundary/Application with `python-parse-dont-validate`, Validation/Test |
| Numerical, geometric, statistical, scientific, dataframe, NumPy/SciPy, Hypothesis-over-numeric, or Rust-interoperability code | Scientific/Data, Boundary/Application when raw inputs carry invariants, Validation/Test |
| Changelog/release/CI/benchmark/fixture/diagnostic scripts, generated artifact preparation, subprocess wrappers around `cargo`/`git`/`gh` | Support Tooling, Boundary/Application when CLI behavior matters, Validation/Test |
| Tests/fixtures only | Validation/Test, plus domain group only if tests encode scientific, CLI, parser, or support-tool behavior that can hide a production bug |
| Python packaging, lint, format, type-check, or dependency config | Validation/Test, plus affected domain group if config changes behavior |
| Docs-only Python examples or notebook prose | Relevant domain group only if examples are executable or user-facing behavior changed; otherwise docs validators |
| Workflow/config only | No Python skill group unless Python behavior, validators, notebooks, or generated artifacts changed; run config validators |

## Focused Validators

Use the repository's documented commands when available. If no local guidance exists, use the generic fallbacks in this table.

| Files touched | Validator |
|---|---|
| Python library/application source | documented focused Python check; fallback `python -m compileall <changed paths>` plus targeted `pytest` when tests exist |
| CLI entry points or user-facing command output | documented CLI tests; fallback targeted `pytest`, plus `python -m <module> --help` or the local command's `--help` when discoverable |
| Parser/config/model changes | targeted parser/model tests; fallback targeted `pytest` plus the repository type checker if configured |
| Scientific/numerical/dataframe code | targeted scientific tests, property tests, or fixture checks; run benchmark/allocation checks only when making performance claims |
| Support scripts and dev tooling | targeted pytest/golden tests; run `--help` smoke checks for changed CLIs when safe |
| Tests only | `pytest <changed test files>` or the repository's narrow test recipe |
| Notebooks | repository notebook lint/execute recipe; fallback notebook JSON parse and lightweight lint, execute only when dependencies and runtime are reasonable |
| Python package/dependency config | repository lock/check recipe; fallback `python -m compileall` and configured lint/type/test commands when available |
| Type annotations or invariant-carrying models | configured type checker (`mypy`, `pyright`, `basedpyright`, `ty`, or local recipe) plus targeted tests |
| Markdown/docs/examples | docs, markdown, link, or example validators from the repository |
| GitHub workflows/YAML/config | documented config validators, `actionlint`, or YAML checks |

When a selected validator fails:

1. Treat the failure as part of the current group.
2. Fix the underlying issue.
3. Rerun the same validator.
4. Continue to the next skill only after the validator passes or the blocker is explicitly documented.

## Escalation To Full CI

Run the repository's full-CI validator when any of these are true:

- repository instructions explicitly require it for the touched files
- changes span multiple Python layers and no smaller validator covers the combined risk
- public CLI behavior and parser/model invariants changed together
- scientific/reproducibility behavior changed in a way that could affect broad results
- notebook execution, support scripts, and package config changed together
- final synthesis finds cross-cutting risk not covered by focused validators

Do not run full CI merely because the workflow is ending. Use focused validators for docs-only, config-only, tests-only, examples-only, fixture-only, notebook-only, or support-script-only changes when repository guidance allows them.

## Review Summary Template

Use this shape at handoff:

```text
Changed files:
- path: why it changed and which issue/skill finding it addressed

Review passes:
- Notebook/Reproducibility: skills run and notable outcomes
- Boundary/Application: skills run and notable outcomes
- Scientific/Data: skills run and notable outcomes
- Support Tooling: skills run and notable outcomes
- Validation/Test: skills run and notable outcomes
- Final Synthesis: remaining risk or none

Validation:
- command: pass/fail/blocked, with concise context

Git:
- No git state mutations performed.
```
