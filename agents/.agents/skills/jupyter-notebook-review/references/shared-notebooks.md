# Shared Notebook Workflow

Use the consumer's named Just recipes when present. The supported implementation
is the published `research-repo-tools` CLI; do not copy its helpers into the
consumer or import undocumented internal notebook modules.

## Environment

Declare `research-repo-tools[notebooks]` in the consumer's notebook dependency group
at the same exact version as its tooling pin. Keep analysis dependencies in that
group, and Ruff and ty in the locked development environment. The v0.1.4 native
lint contract requires Ruff 0.16.8 or newer and ty 0.0.82 or newer. A version
upgrade is a deliberate consumer change, not part of running a review.

The default group name is `notebook`; substitute the consumer's configured group
where it differs. Run from the consumer root:

```sh
uv run --locked --group notebook research-repo-tools notebooks check notebooks/example.ipynb
uv run --locked --group notebook research-repo-tools notebooks lint notebooks/example.ipynb
```

`check` and `lint` require nbformat 4.5 with existing unique cell IDs. Use the
skill's compact summary to inspect older notebooks or IDs awaiting repair, then
repair them deliberately before invoking the strict shared gates. Lint reads
native notebook cells, including supported IPython syntax, without extracting
temporary Python files or executing cells. The skill's `--advice` pass adds only
review policy and is not a substitute for these gates.

## Cleanup And Execution

When cleanup is requested:

```sh
uv run --locked --group notebook research-repo-tools notebooks clear notebooks/example.ipynb
```

This validates the selected notebooks, then removes outputs, execution counts,
execution timing, and widget state while preserving IDs, source, attachments, and
unrelated metadata. There is no local `clear_outputs.py` implementation.

Execution additionally requires the consumer's declared Python/uv toolchain and
locked notebook environment. Follow its setup recipe and the
[upstream environment contract](https://github.com/acgetchell/research-repo-tools/blob/v0.1.4/docs/RUNNING_NOTEBOOKS.md).
Synchronize that environment before deliberate execution:

```sh
uv run --locked --group notebook research-repo-tools notebooks sync
uv run --locked --group notebook research-repo-tools notebooks execute notebooks/example.ipynb
```

Execution leaves source notebooks unchanged and writes an executed notebook plus
a status/provenance report beneath the configured output directory, normally
`target/notebooks`. Notebook code can still write its own files or contact services;
inspect its effects and cost before running it. The old helper's `--execute`
mode has been retired in favor of this explicit shared artifact contract.

For repositories that do not yet declare the shared dependency, plan adoption in
that consumer and use its existing approved commands meanwhile. Do not silently
install packages or switch interpreters during a notebook review.

## Remaining Local Policy

`notebook_check.py --summary` and `--advice` are the temporary local inspection and
advisory layer. They need only Python's standard library. Dotfiles
[#78](https://github.com/acgetchell/dotfiles/issues/78) retires them after published
v0.1.5 supplies the inspection and configurable advisory capabilities requested
in upstream [#39](https://github.com/acgetchell/research-repo-tools/issues/39) and
[#40](https://github.com/acgetchell/research-repo-tools/issues/40).
