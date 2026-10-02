# Review Graph Python Environment

Run the graph scripts with Python 3.14 or newer and the published
`research-repo-tools` package. Dotfiles pins version 0.1.7. Consuming repositories
can declare the same tooling dependency:

```sh
uv add --group dev 'research-repo-tools==0.1.7'
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/capture_scope.py" --help
```

For a repository without that dependency, supply it for the invocation:

```sh
uv run --with 'research-repo-tools==0.1.7' \
  python "$SKILLS_ROOT/review-graph/scripts/review_graph_runtime.py" --help
```

The graph imports supported `research_repo_tools.evidence` and
`research_repo_tools.process` APIs directly. Graph-specific JSON encoding,
algorithm-prefixed identities, streaming scope fingerprints, journals, and
immutable publication remain graph-owned contracts. Shared JSON serialization
has a different byte format and cannot replace existing signed identities.

Generated capture and publication commands retain the executing Python path
without resolving its symlinks, preserving the environment that contains the
dependency. Keep that environment and the skill checkout available throughout
the graph and any continuation.
