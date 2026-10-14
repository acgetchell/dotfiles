# Review Graph Python Environment

Run the graph scripts with Python 3.15 or newer and the published
`research-repo-tools` package. Dotfiles pins version 0.1.9. Consuming repositories
can declare the same tooling dependency in an environment supporting Python
3.15. Use the consumer's migration recipes when upgrading an existing pin;
reconcile its Python selector and requirement before adding the dependency:

```sh
uv add --group dev 'research-repo-tools==0.1.9'
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/capture_scope.py" --help
```

For a repository without that dependency, supply it for the invocation:

```sh
uv run --python 3.15 --with 'research-repo-tools==0.1.9' \
  python "$SKILLS_ROOT/review-graph/scripts/review_graph_runtime.py" --help
```

The graph imports supported `research_repo_tools.evidence` and
`research_repo_tools.process` APIs directly. Graph-specific JSON encoding,
algorithm-prefixed identities, streaming scope fingerprints, journals, and
immutable publication remain graph-owned contracts. Shared JSON serialization
has a different byte format and cannot replace existing signed identities.

By default, generated capture and publication commands retain the executing
Python path without resolving its symlinks. For a repository that requires a
wrapper, supply `--python-runner <operator-runner.json>` to bootstrap. Its exact
shape is:

```json
{
  "argv": ["/absolute/path/to/uv", "run", "--locked", "python"],
  "working_directory": "/absolute/repository",
  "environment": {"UV_CACHE_DIR": "/absolute/external/writable/cache"},
  "identity_files": ["/absolute/repository/pyproject.toml", "/absolute/repository/uv.lock"]
}
```

Choose the runner and approve its resources before startup. An `uv` runner needs
`run --locked`, both project/lock identities, and an existing writable external
cache. Bootstrap probes that exact runner for its interpreter identity and
freezes the invocation policy, executable identities, and lock identities.
Subsequent helpers reject changed prerequisites. Wrapper environments require
the host's `env` executable; raw interpreter mode remains available separately.

Every compact worker view retains `execution_context`, including the working
directory. Run its generated commands in that directory. Capture, publication,
scheduler, and timing-helper commands carry the chosen wrapper and cache without
workers reconstructing them. Keep the selected environment available throughout
the run. Unavailable resources require the normal execution-tool approval or a
blocker; never silently install dependencies or substitute another runner.
