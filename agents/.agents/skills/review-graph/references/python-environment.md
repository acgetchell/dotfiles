# Review Graph Python Environment

Run the graph scripts with Python 3.15 or newer and the published
`research-repo-tools` package. Dotfiles pins version 0.2.3. Consuming repositories
can declare the same tooling dependency in an environment supporting Python
3.15. Use the consumer's migration recipes when upgrading an existing pin;
reconcile its Python selector and requirement before adding the dependency:

```sh
uv add --group dev 'research-repo-tools==0.2.3'
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/capture_scope.py" --help
```

For a repository without that dependency, supply it for the invocation:

```sh
uv run --python 3.15 --with 'research-repo-tools==0.2.3' \
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
  "argv": ["/absolute/path/to/uv", "run", "--no-sync", "--locked", "python"],
  "working_directory": "/absolute/repository",
  "environment": {"UV_CACHE_DIR": "/absolute/external/writable/cache"},
  "identity_files": ["/absolute/repository/pyproject.toml", "/absolute/repository/uv.lock"]
}
```

Choose the runner and approve its resources before startup. An `uv` runner needs
`run --no-sync --locked`, both project/lock identities, and an existing writable
external cache. Put `--no-sync` before the command or any option values so it is
an effective runner option. Bootstrap probes that exact runner for its interpreter identity and
freezes the invocation policy, executable identities, and lock identities.
Subsequent helpers reject changed prerequisites. Wrapper environments require
the host's `env` executable; raw interpreter mode remains available separately.
Environment names use the portable `[A-Za-z_][A-Za-z0-9_]*` grammar and values
must be NUL-free strings, so probe mappings and generated `env` arguments agree.

Every compact worker view retains `execution_context`, including the working
directory. Run its generated commands in that directory. Capture, publication,
scheduler, and timing-helper commands carry the chosen wrapper and cache without
workers reconstructing them. Keep the selected environment available throughout
the run. Unavailable resources require the normal execution-tool approval or a
blocker; never silently install dependencies or substitute another runner.

## Preplan a runner for consumer manifest repairs

When authorized work may repair `pyproject.toml`, `uv.lock`, or the Python
selector, bootstrap from a helper environment separate from the consumer. Use
an approved external proof store with a new helper directory:

```sh
(
  set -eu
  unset VIRTUAL_ENV CONDA_PREFIX UV_PROJECT_ENVIRONMENT UV_PYTHON UV_PROJECT \
    UV_WORKING_DIR UV_CONFIG_FILE UV_SYSTEM_PYTHON UV_TARGET UV_PREFIX UV_OVERRIDE \
    PYTHONHOME PYTHONPATH
  export UV_CACHE_DIR="$PROOF_STORE/helper-cache"
  uv venv --no-project --no-config --python 3.15 "$PROOF_STORE/helper"
  uv pip install --no-config --python "$PROOF_STORE/helper/bin/python" \
    --link-mode copy 'research-repo-tools==0.2.3'
  "$PROOF_STORE/helper/bin/python" -E -s \
    "$SKILLS_ROOT/review-graph/scripts/review_graph_bootstrap.py" \
    --helper-version 0.2.3 \
    --capture "$PROOF_STORE/initial.capture.json" --input "$PROOF_STORE/planning.json" \
    --output "$PROOF_STORE/bootstrap.json"
)
```

`--no-project` alone can reuse an active or discovered `.venv`, including a
same-version editable install. `uv run --isolated --no-project --with ...`
instead uses a temporary interpreter and a layered package environment; its
interpreter can disappear when the command exits. A named `uv venv` plus an
explicit `uv pip install --python` target provides the persistent environment
needed by retained commands. `--no-config` excludes consumer configuration, and
the cleared selectors prevent ambient environment and install-target choices.
Python `-E -s` excludes `PYTHONPATH`, `PYTHONHOME`, and user site packages.
Use the appropriate `Scripts/python.exe` path on Windows. See the
[uv commands](https://docs.astral.sh/uv/reference/cli/) and
[environment selectors](https://docs.astral.sh/uv/reference/environment/).

Before creating a snapshot, bootstrap verifies the package import against its
installed distribution's SHA-256 RECORD and rejects editable or shadowed imports.
`--helper-version` additionally requires the exact version, a virtual environment
outside the consumer, and Python `-E -s`. It retains the invocation path,
environment prefix, package location, version, and RECORD digest in the hashed
`python-origin.json` resource. Origin failures leave no new frozen runtime or
dispatch command. After setup, a read-only probe is:

```sh
"$PROOF_STORE/helper/bin/python" -E -s \
  "$SKILLS_ROOT/review-graph/scripts/review_graph_environment.py" \
  --repository "$PWD" --helper-version 0.2.3
```

Omit `--python-runner` to retain that helper interpreter directly. Keep its
environment available until the review finishes. The frozen runtime retains
its own package/resources and verifies the interpreter executable, version,
invocation path, and environment prefix; generated helper commands retain `-E -s`.
Two virtual environments sharing one base Python binary are not interchangeable.
For retries, use the retained interpreter and commands; do not recreate or
resynchronize the helper. Consumer manifests are source inputs, not helper runner prerequisites. A
tool-only manifest repair can use the generated capture command and normal
`advance-after-mutation` within the already authorized repair batch.

For dependency or Python changes, synchronize and verify the consumer environment
through its owning commands, update the validation template's toolchain/environment
identity, and revalidate affected obligations. The helper interpreter does not
certify the consumer environment. Preserve original captures and validation.

Choose this before bootstrap. An existing frozen uv wrapper still rejects changed
prerequisites; do not edit its manifest, replace its runner, or restart the review
to bypass that binding. For an unplanned repair blocked by that prerequisite,
retain the evidence and use the partial-delivery path in
[state transitions](state-transitions.md#external-source-edits).

If an already-started run used an editable or consumer-bound helper, preserve its
captures, snapshot, dispatches, journal, and validation results. Do not add an
isolation claim, change runners, rewrite manifests, or delete evidence. Existing
snapshots retain their original contract; this check does not retroactively
certify their origin. Report the setup/provenance limitation and affected checks
through the partial-delivery path. If an independent helper is needed to continue,
obtain authorization for a separate run and proof store, explicitly link the old
run, and revalidate affected obligations. The origin problem alone establishes
neither an incorrect semantic finding nor package corruption.
