---
name: jupyter-notebook-review
description: "Review and fix Jupyter notebooks for reproducible execution, sound Python style, Polars-first dataframe workflows, and reliable Plotly/Matplotlib visualization. USE FOR: .ipynb review, notebook cleanup, hidden-state fixes, clearing outputs, headless execution failures, uv/Jupyter environment setup, converting pandas-style notebook code to Polars, improving CSV/Parquet/JSON loading, plotting diagnostics, notebook CI checks, and notebook front ends that wrap binaries or APIs. DO NOT USE FOR: ordinary Python package review without notebooks; scientific/numerical correctness review beyond notebook hygiene; slide/document/spreadsheet artifacts."
---

# jupyter-notebook-review

Review and fix notebooks as reproducible computational artifacts, not scratchpads. Keep core library, simulation, and production logic in importable modules,
CLIs, or examples; notebooks should orchestrate those APIs and analyze generated artifacts.

## Workflow

1. Locate notebooks with `rg --files -g '*.ipynb'` unless the user names a file.
2. Inspect structure with `scripts/notebook_check.py --summary NOTEBOOK.ipynb` before reading raw JSON.
3. Read code cells through `jq` or `notebook_check.py --summary`; avoid dumping large outputs into context.
4. Review for reproducibility, data handling, plotting, path hygiene, outputs, secrets, and environment setup.
5. Edit notebooks with `nbformat` or the helper scripts; do not hand-edit large notebook JSON by string substitution.
6. Validate with `uv run scripts/notebook_check.py --lint NOTEBOOK.ipynb` when the helper is copied into a repo, or with the skill-local script through
   `uv run`. The lint path compiles cells, runs notebook-specific AST checks, and requires Ruff lint, Ruff format, and ty on extracted notebook code unless a
   check is explicitly disabled. Execute with `--execute` when dependencies and runtime are reasonable.
7. Clear outputs before finalizing unless the repository intentionally tracks rendered notebook outputs.

## Related Python Skills

Use this skill as the notebook front door, then bring in narrower Python skills when the notebook contains substantial reusable code:
- Use `python-parse-dont-validate` when notebook inputs, config dictionaries, JSON summaries, dataframe schemas, or subprocess results carry invariants that
  should be parsed into typed objects before computation.
- Use `python-scientific-review` when notebook code implements or validates numerical, statistical, geometric, or scientific algorithms rather than merely
  plotting already-produced results.
- Use `python-support-scripts` when notebook helper code graduates into a reusable script for CI, release, benchmark, fixture, or diagnostic workflows.
- Use `python-cli-review` when notebook code is a small application or CLI front end with user-facing argument parsing and output contracts.
- Use `python-test-quality` when adding notebook checker tests, fixture notebooks, or coverage for notebook-adjacent helper scripts.

## Review Priorities

### Python Code Quality

Notebook Python should follow the same standards as repository scripts when the code may be reused, validated, or trusted by readers.

Check:
- functions have type hints at non-trivial boundaries and narrow responsibilities
- imports are grouped near the top instead of hidden in late cells
- `pathlib.Path` and explicit `encoding="utf-8"` are used for text I/O
- exceptions are specific and include enough context to diagnose bad files, rows, paths, or commands
- mutable defaults, import-time side effects, broad `except`, and swallowed failures are absent
- assertions are not used for user-input or environment validation; raise an exception with context instead
- output order is deterministic when listing files, records, glob results, keys, or categories

Prefer extracting long reusable code into `scripts/`, examples, or package modules when it stops being notebook-local tutorial glue.

### Reproducibility

Flag:
- hidden state: cells fail when run top-to-bottom in a fresh kernel
- code that relies on the current working directory without finding the repository root
- package installation cells that mutate global user environments
- random behavior without explicit seeds where output interpretation depends on repeatability
- timestamps, host paths, usernames, or machine-local state embedded in outputs

Prefer:
- a first setup cell with imports, deterministic paths, and configuration
- `uv run --group notebooks ...` or a repository `just notebook` / `just notebook-setup` recipe
- a headless recipe such as `just notebook-execute` for CI, remote servers, and HPC jobs
- data and generated artifacts under `target/`, `runs/`, or another documented output directory
- fresh-kernel execution through `nbconvert`, `nbclient`, or a repository notebook check recipe

### Boundary Parsing And Invariants

Parse external data at the notebook boundary before using it in computations or plots.

Check:
- JSON/CSV/TOML/YAML shapes are checked before deep indexing
- dataframe columns have expected names and dtypes before aggregation
- numeric inputs used in scientific plots are finite and in expected ranges
- paths exist and point to files/directories as expected
- optional values are handled deliberately instead of assuming presence

Prefer small parser helpers, `TypedDict`, frozen dataclasses, `Enum`/`Literal`, or Polars schema checks when a notebook carries meaningful invariants. Do not add
heavy domain models for passive display-only report shapes.

### Dataframes And I/O

Prefer Polars for table work:

```python
import polars as pl

trace = pl.read_csv(trace_path)
summary = trace.select(
    pl.len().alias("steps"),
    pl.col("accepted").sum().alias("accepted"),
    pl.col("action").mean().alias("mean_action"),
)
```

Use `pl.scan_csv`, `pl.scan_parquet`, or LazyFrame pipelines when data may become large. Use Parquet/Arrow for cached intermediate tables when possible.

Accept pandas only when:
- the repository already standardizes on pandas
- a library API requires pandas objects
- the notebook is explicitly comparing pandas behavior

Flag:
- manual CSV parsing for dataframe-shaped analysis when Polars is available
- implicit dtype guesses that break booleans, datetimes, or categorical columns
- code that silently drops malformed rows or fills numeric failures with sentinels
- large in-memory conversions to Python lists before filtering or aggregating

For scientific or Rust-interoperability notebooks, also check:
- units, coordinate conventions, indexing bases, and dtype/precision assumptions match the Rust or data-source contract
- NaN, infinity, overflow, underflow, and degenerate inputs fail loudly or are explicitly filtered with explanation
- tolerances and rounding choices are justified by the plotted quantity and data scale

### Plotting

Use Matplotlib for stable static plots, saved figures, and headless validation. Set `MPLBACKEND=Agg` for noninteractive execution checks when needed.

Use Plotly for interactive exploration when hover, zoom, faceting, or shareable HTML output matters. Make Plotly cells tolerate noninteractive validation by
building figures as objects and avoiding browser-only side effects.

Check:
- axis labels, units, legends, and titles describe the plotted quantity
- plots use dataframe columns directly rather than duplicated hand-built lists when practical
- figure generation does not require a live browser in CI/headless mode
- saved plots use deterministic paths and create parent directories

### Notebook Hygiene

Flag:
- committed cell outputs or execution counts unless the project explicitly wants rendered notebooks
- huge base64 images, binary blobs, widgets, or stale errors in outputs
- secrets, tokens, local absolute paths, usernames, or private data in source or outputs
- hidden imports in later cells that should be in setup
- long cells that should be functions in a Python module or script

Prefer:
- short markdown context that explains interpretation, not implementation trivia
- functions for repeated notebook-local operations
- imports grouped in the first code cell
- concise cells with one clear purpose

### Subprocesses And CLI Front Ends

When notebooks run binaries or CLIs:
- use argument lists, never `shell=True` with interpolated values
- include a timeout or documented reason not to use one
- surface command, exit code, stdout, and stderr when failures matter
- keep machine-parseable command output separate from tutorial/log text when downstream cells parse it
- avoid printing secrets, tokens, or raw private records
- pass deterministic environment variables when command output is parsed

Streaming output is acceptable for tutorial front doors, but failures should still report enough context to reproduce the command outside the notebook.

### Tests And Validation

Notebook-adjacent helpers should have behavior tests when they become reusable scripts:
- lint helpers should be tested on valid notebooks, syntax errors, dirty outputs, and malformed JSON
- execution helpers should use `tmp_path` or in-memory execution and avoid changing source notebooks
- path and parser helpers should cover missing files, bad schemas, empty data, and malformed rows
- assertions should check outputs, exit codes, and diagnostics, not only "no exception"

## Fix Patterns

### Environment

For repos using uv, add a notebook dependency group rather than ad hoc pip cells:

```toml
[dependency-groups]
notebooks = [
    "ipykernel",
    "jupyterlab",
    "matplotlib",
    "polars",
    "plotly",
]
```

Prefer a `just` wrapper when the repo already uses `just`:

```just
notebook-setup:
    uv sync --group notebooks

notebook:
    uv run --group notebooks jupyter lab notebooks/00_quickstart.ipynb
```

Pin exact versions only when the repository's policy requires lockstep reproducibility. Otherwise let `uv.lock` capture the resolved versions.

### HPC And Headless Execution

For HPC clusters, remote servers, and CI:
- provide a non-GUI execution path with `jupyter nbconvert --execute`, `nbclient`, or a repository `just notebook-execute` recipe
- set `MPLBACKEND=Agg` for Matplotlib plots
- write executed notebooks and generated artifacts under `target/`, `$SCRATCH`, or another documented scratch/output directory
- let users set `UV_CACHE_DIR` when home-directory caches are unavailable or slow
- document whether `uv sync --group notebooks` must run on a login node before offline compute jobs
- honor an environment variable such as `CDT_BINARY`, `MODEL_BINARY`, or `SIM_BINARY` when a cluster module or release artifact provides the executable
- avoid browser-only Plotly renderers in batch mode; save HTML/JSON artifacts instead when interactivity matters
- include walltime/memory expectations for notebooks that run simulations or large analyses

For Open OnDemand:
- assume `just notebook` may run inside a Jupyter app backed by a compute allocation
- avoid requiring local GUI browser behavior inside notebook cells
- prefer notebook cells that submit long jobs to Slurm and later load generated artifacts for analysis
- keep `sbatch`/`srun` commands as argument lists or generated scripts with explicit paths, walltime, memory, and output locations
- make job IDs, run directories, trace paths, and summary paths visible to the reader

Example headless recipe:

```just
notebook-execute notebook="notebooks/00_quickstart.ipynb" output_dir="target/notebooks":
    mkdir -p "{{output_dir}}"
    MPLBACKEND=Agg uv run --group notebooks jupyter nbconvert --execute --to notebook --output-dir "{{output_dir}}" "{{notebook}}"
```

### Experiment Tracking

Use MLflow only for notebooks that manage model-training, learned proposals, hyperparameter sweeps, or comparable experiments. Do not add it to simple
quickstarts that only run a binary and plot trace files.

When MLflow is appropriate:
- keep tracking URI, experiment name, and artifact root configurable through environment variables or a small validated config cell
- log parameters, code version, dataset/run identifiers, seeds, metrics, and produced artifact paths
- store large model artifacts and generated datasets in a cluster/project artifact store, not inside the notebook
- make reruns idempotent by using explicit run names or tags rather than relying on ambient notebook state
- keep MLflow setup optional so headless validation can run without a live tracking server unless the notebook is specifically an MLflow integration test

### Paths

Use repository-root discovery instead of assuming the launch directory:

```python
from pathlib import Path

def find_repo_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if (path / "pyproject.toml").exists() or (path / ".git").exists():
            return path
    raise RuntimeError("Run this notebook from inside the repository.")

ROOT = find_repo_root(Path.cwd().resolve())
```

Validate data paths after constructing them:

```python
if not trace_path.is_file():
    raise FileNotFoundError(f"trace CSV not found: {trace_path}")
```

### Binary Or API Front Ends

If a notebook wraps a binary or library API:
- keep the binary/API as the engine
- stream command output for tutorials
- write artifacts to a documented directory
- load artifacts back into Polars or JSON for analysis
- avoid duplicating production simulation or data-processing logic in notebook cells

Use a typed command helper when the cell needs to preserve failure context:

```python
import subprocess

def run_command(command: list[str], *, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result
```

## Helper Scripts

Use bundled scripts from this skill when useful:

- `scripts/notebook_check.py --summary NOTEBOOK.ipynb` prints a compact cell inventory.
- `scripts/notebook_check.py --lint NOTEBOOK.ipynb` validates JSON, compiles code cells, requires Ruff lint, Ruff format, and ty by default, and reports output
  counts.
- `scripts/notebook_check.py --execute NOTEBOOK.ipynb --repo-root PATH` executes in memory without writing outputs back.
- `scripts/clear_outputs.py NOTEBOOK.ipynb` clears outputs and execution counts in place.

Run scripts with `uv run` or the active project Python. If a repository has its own notebook checker, prefer the repository command and use these scripts as a
fallback or comparison.

## Output

For a review, lead with findings ordered by severity and cite notebook cell numbers. Include:
- reproducibility blockers
- dataframe and I/O issues
- plotting/headless risks
- output/metadata hygiene
- concrete fixes or patches applied
- validation commands run and their result

For a fix, summarize the notebook changes and confirm whether outputs were cleared and whether fresh execution passed.
