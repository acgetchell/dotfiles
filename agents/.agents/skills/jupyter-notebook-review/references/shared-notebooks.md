# Shared Notebook Workflow

Use the consumer's named Just recipes when present. Published
`research-repo-tools==0.1.5` supplies inspection, advice, validation, native lint,
cleanup, and execution. Only the CLI and `research_repo_tools.cli.main` are
supported notebook interfaces; do not import internal loaders or copy helpers.

## Locked Consumer Environment

For an adopted consumer, declare `research-repo-tools[notebooks]==0.1.5` in its
notebook dependency group at the same exact version as its tooling pin. Keep
analysis dependencies in that group and Ruff 0.16.8 or newer and ty 0.0.82 or newer
in its locked development environment. Preserve a deliberately adopted newer
version. An upgrade is a consumer change, not an implicit part of review.

The default group name is `notebook`; substitute the consumer's configured group
where it differs. Run from the consumer root, including `dev` for the checkers:

```sh
uv run --locked --group notebook --group dev research-repo-tools notebooks inspect notebooks/example.ipynb
uv run --locked --group notebook --group dev research-repo-tools notebooks check notebooks/example.ipynb
uv run --locked --group notebook --group dev research-repo-tools notebooks advise notebooks/example.ipynb
uv run --locked --group notebook --group dev research-repo-tools notebooks lint notebooks/example.ipynb
```

`inspect` requires only the base package. It reports original cell positions,
types, IDs, line/output/execution counts, and short source previews without
printing stored outputs or metadata, executing cells, generating IDs, or writing
source files. Previews expose source text; use `--no-preview` to omit it. Use
`--json` for the [versioned inventory schema](https://github.com/acgetchell/research-repo-tools/blob/v0.1.5/docs/notebook-inspection.md).

Inspection tolerates older nbformat 4 notebooks and missing, invalid, or duplicate
IDs, reporting repair problems while returning zero for a complete inventory.
Unreadable input still fails. Repair structure deliberately before `check`,
`lint`, `advise`, `clear`, or `execute`: those commands retain strict nbformat 4.5
and existing unique-ID requirements. Python analysis also requires Python
notebook metadata. Inspection success is not a substitute for strict validation.

## Clean-Environment Review

If the consumer has not adopted the shared package, an isolated inspection can
use the published base package without changing its manifest or environment:

```sh
uv run --no-project --with research-repo-tools==0.1.5 research-repo-tools --root "$PWD" notebooks inspect notebooks/example.ipynb
```

For isolated advice, include the notebook extra and Ruff. This reads policy from
the consumer root; without configured policy, only descriptive-ID advice applies:

```sh
uv run --no-project --with 'research-repo-tools[notebooks]==0.1.5' --with ruff==0.16.8 research-repo-tools --root "$PWD" notebooks advise notebooks/example.ipynb
```

These commands may download dependencies into uv's cache. Use the consumer's
locked commands when available. Missing dependencies should be reported or added
through deliberate adoption; never substitute an isolated environment for the
consumer's execution environment.

## Consumer Advisory Policy

When adopting the skill's defaults, merge
[`assets/pyproject.toml`](../assets/pyproject.toml) into the consumer's existing
configuration. It contains only policy: shared descriptive-ID and timeout advice,
native Ruff annotation/exception rules, and opt-in pandas/csv import guidance.
Preserve the consumer's existing rules and ignores, and omit banned-import entries
where the repository standardizes on those libraries or a dependency requires
them. Polars remains a preference for dataframe-shaped work, not a universal ban.

`advise` runs separately from `lint`. Warnings return zero by default; CLI
`--strict` or configured `strict = true` fails on warnings. Informational skips
never fail strict mode. Operational errors, invalid structure or configuration,
missing checkers, and native syntax errors always fail. Diagnostics identify
original cell numbers and IDs on stderr; stdout contains compact counts.

The template enables `S602` in native lint to preserve `shell=True` as a hard
failure. Keep annotation, broad-exception, library-preference, and timeout advice
as warnings unless the consumer requests stricter policy. Other consumer lint
rules still apply; neither pass fixes or executes cells.

Native Ruff/ty handle supported IPython syntax in the original notebook. Only
the supplemental plain-AST timeout pass skips magic/non-Python cells, with an
informational diagnostic. It covers direct `subprocess.run`, `call`, `check_call`,
and `check_output` calls without a non-`None` timeout. Review aliases, wrappers,
runtime bounds, and `Popen` wait/communicate/termination lifecycles manually.

Descriptive-ID warnings are heuristics. Keep stable descriptive IDs, and manually
review positional `section-N` and `step-N` IDs in addition to the generated and
positional patterns detected upstream. Never rename valid IDs automatically.
See the [advisory contract and limits](https://github.com/acgetchell/research-repo-tools/blob/v0.1.5/docs/RUNNING_NOTEBOOKS.md#review-advisories).

## Cleanup And Execution

When cleanup is requested:

```sh
uv run --locked --group notebook research-repo-tools notebooks clear notebooks/example.ipynb
```

This validates the selection, then removes outputs, execution counts, execution
timing, and widget state while preserving IDs, source, attachments, and unrelated
metadata. There is no local cleanup implementation.

Execution additionally requires the consumer's declared Python/uv toolchain and
locked notebook environment. Follow its setup recipe and the
[upstream environment contract](https://github.com/acgetchell/research-repo-tools/blob/v0.1.5/docs/RUNNING_NOTEBOOKS.md).
Synchronize that environment before deliberate execution:

```sh
uv run --locked --group notebook research-repo-tools notebooks sync
uv run --locked --group notebook research-repo-tools notebooks execute notebooks/example.ipynb
```

Execution leaves source notebooks unchanged and writes an executed notebook plus
a status/provenance report beneath the configured output directory, normally
`target/notebooks`. Notebook code can still write its own files or contact services;
inspect its effects and cost before running it.

## Coverage Ownership

Dotfiles retains integration checks for the published CLI and this skill's actual
policy template. Generic inspection, ID heuristics, parser failures, native
syntax, checker failures, and advisory regression coverage belong to upstream
[`tests/notebooks`](https://github.com/acgetchell/research-repo-tools/tree/v0.1.5/tests/notebooks),
including the installed-consumer contracts in `public_notebook_consumer.py`.
