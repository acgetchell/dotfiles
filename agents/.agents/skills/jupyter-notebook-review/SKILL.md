---
name: jupyter-notebook-review
description: "Review and fix Jupyter notebooks for reproducible execution, stable cell identity, output hygiene, safe data boundaries, portable environments, and reliable generated artifacts. Use for .ipynb cleanup, hidden state, output clearing, notebook lint or execution, data loading, plots, headless or HPC use, experiment tracking, and notebook CI. Route substantial reusable, scientific, CLI, parsing, support-script, and test behavior to focused Python skills."
---

# Jupyter Notebook Review

Review notebooks as reproducible computational artifacts rather than scratchpads. Keep production logic in importable modules, CLIs, or examples; let notebooks orchestrate those APIs and interpret artifacts.

## Workflow

1. Locate the named notebooks or use `rg --files -g '*.ipynb'`.
2. Inspect structure with `scripts/notebook_check.py --summary NOTEBOOK.ipynb` before reading raw JSON.
3. Read code cells through the summary helper or `jq`; avoid loading large outputs into context.
4. Review fresh-kernel order, paths, inputs, outputs, secrets, environments, and generated artifacts.
5. Edit with `nbformat` or the bundled helpers rather than large JSON string substitutions.
6. Run structured lint after changes. Execute only when runtime behavior or a generated artifact is in scope.
7. Give every code, markdown, and raw cell a unique, stable, descriptive ID following repository rules or lowercase kebab-case.
8. Clear outputs and execution counts unless the repository intentionally tracks rendered results.

## Conditional References

Load only references that match the notebook:

- Read [`references/dataframes-and-plotting.md`](references/dataframes-and-plotting.md) when reviewing dataframe pipelines, tabular I/O, Matplotlib, Plotly, or saved figures.
- Read [`references/hpc-and-headless.md`](references/hpc-and-headless.md) for remote servers, CI execution, Slurm, Open OnDemand, scratch storage, or notebook dependency setup.
- Read [`references/experiment-tracking.md`](references/experiment-tracking.md) only for MLflow, model training, learned proposals, sweeps, or comparable tracked experiments.
- Read [`references/binary-frontends.md`](references/binary-frontends.md) when cells invoke external binaries, wrap a library API as an engine, parse subprocess output, or must discover the repository root portably.
- In the `delaunay` repository, read [`references/delaunay.md`](references/delaunay.md) after repository instructions.

## Related Python Skills

Select focused skills independently when notebook cells contain substantial owned behavior:

- `python-parse-dont-validate` for invariant-bearing config, structured inputs, dataframe schemas, or subprocess results
- `python-scientific-review` for mathematical, numerical, statistical, geometric, or scientific validation logic
- `python-support-scripts` when notebook helpers become reusable release, benchmark, fixture, CI, or diagnostic scripts
- `python-cli-review` for a material user-facing argument or output contract
- `python-test-quality` for notebook-checker tests, fixture notebooks, or notebook-adjacent helper evidence
- `python-build-portability` for notebook dependency groups, optional extras, installed imports, or supported runtime/platform claims

Do not load every related skill merely because a notebook contains imports, assertions, or a subprocess call.

## Core Review

### Reproducible State

Check that cells run top-to-bottom in a fresh kernel. Put imports, deterministic paths, seeds, and configuration near the beginning. Remove dependence on stale variables, manual execution order, current timestamps, ambient environment variables, local usernames, or undocumented working directories.

Avoid package-install cells that mutate global environments. Prefer the repository's locked environment and named notebook commands.

### Notebook Structure

Keep cells concise and purposeful. Move reusable algorithms and long helpers into importable code. Group imports near the top, document interpretation rather than restating implementation, and preserve stable descriptive cell IDs across edits.

Flag hidden late imports, duplicated helpers, monolithic cells mixing I/O/computation/plotting, user-input validation through `assert`, broad exception swallowing, and import-time or cell-order side effects.

### Inputs And Invariants

Validate paths, file shapes, required columns, dtypes, optional values, and finite numeric inputs before computation or plotting. Use a small parser, `TypedDict`, frozen dataclass, enum/literal, or schema check only when the notebook carries a meaningful invariant. Keep passive display-only reports lightweight.

Route deeper domain modeling to `python-parse-dont-validate` and mathematical validity to `python-scientific-review` rather than duplicating those reviews here.

### Generated And Tracked Artifacts

Write ordinary execution output under `target/`, `$SCRATCH`, or another documented disposable location. Refresh tracked figures or reports only through a named repository workflow when the requested task includes that artifact.

Prefer one canonical tracked asset when documentation and papers consume the same figure. Let named refresh commands provide tracked destinations instead of hard-coding documentation paths in normal notebook cells.

### Output, Metadata, And Privacy

Flag committed execution counts or outputs unless policy requires them, huge embedded images, widget state, stale exceptions, random-looking cell IDs, secrets, tokens, private records, absolute local paths, and machine-specific metadata.

Ensure human-facing output is intentional and machine-consumed data remains parseable. Do not print raw private records or secrets as diagnostics.

## Validation

Use repository commands first. Otherwise use bundled scripts:

- `scripts/notebook_check.py --summary NOTEBOOK.ipynb` for a compact inventory
- `scripts/notebook_check.py --lint NOTEBOOK.ipynb` for JSON, cell IDs, compilation, notebook AST checks, Ruff, formatting, and ty checks
- `scripts/notebook_check.py --execute NOTEBOOK.ipynb --repo-root PATH` for in-memory execution without writing outputs to the source
- `scripts/clear_outputs.py NOTEBOOK.ipynb` to clear outputs and counts in place

Run helpers with `uv run` or the active project environment. Execute a notebook only when dependencies, cost, side effects, and requested scope make execution appropriate. Never treat successful execution as proof of scientific correctness or portability.

## Output

Lead with reproducibility or privacy blockers. Cite notebook cells by number and ID where possible. Report structural, state, input, artifact, and environment findings; references and focused skills loaded; whether outputs were cleared; validators run; execution status; and any unavailable dependencies or runtime limitations.
