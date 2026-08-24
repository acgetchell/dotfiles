# Compact Graph Validation Dispatch

Use this mode only for an exact `review-graph` validation unit. The graph owns
planning, coalescing, executor placement, evidence compilation, and proof
acceptance. Execute the supplied commands without discovery or broadening.

## Required Dispatch

Require:

- exact validation unit from the accepted graph plan
- expected source, worktree, and repository-state fingerprints
- exact state-verification command
- execution location and fresh-context identity
- exact commands, corresponding working directories, environment, toolchain,
  features, platform, artifact owner, and mutation lock
- approved artifacts with status provenance; exact effects, absolute isolation
  root, and snapshot policy
- dependency policy and elapsed bounds

Return `blocked` for any missing field. Do not fall through to standalone
discovery.

## Execution

1. Snapshot relevant filesystem/Git state; verify source state.
2. Recheck that every dispatched command is non-mutating under repository-owned
   definitions or policy.
3. Execute each command exactly once in order. Respect `stop-on-failure` or
   `continue-independent`. Isolated working directories and external artifacts
   must remain beneath the dispatched isolation root.
4. Record command, working directory, executor, result, exit code, elapsed time,
   concise output evidence, and approved artifact paths.
5. Compute approved artifact content digests.
6. Repeat both snapshot and state checks. Block unexpected tracked, untracked,
   or ignored output and source/Git mutation. Return snapshots beside, not
   inside, the payload.

Do not review code, diagnose findings, edit, install substitute toolchains,
change dependencies, re-plan, or create another worker.

## ValidationPayload

Return one JSON object and no compatibility Markdown:

```json
{
  "status": "passed | failed | blocked | reused | not-applicable",
  "executions": [
    {
      "executor": "worker node-id | coordinator",
      "command": "exact command",
      "working_directory": "/absolute/path",
      "result": "passed | failed | blocked | not-run",
      "exit_code": 0,
      "elapsed": "3.2s",
      "evidence": "concise stdout/stderr facts",
      "artifact_paths": []
    }
  ],
  "artifacts": [
    {
      "path": "/exact/path",
      "artifact_id": null,
      "artifact_digest": "sha256:<digest>",
      "kind": "build | cache | coverage | log | report | test-result | other",
      "repository_status": "ignored | outside-repository"
    }
  ],
  "limitations": []
}
```

Use `null` or `"none"` for unavailable exit codes as appropriate. A blocked
payload requires a concrete limitation. `reused` and `not-applicable` contain
no execution records. Artifact records must match the approved dispatch exactly.

The coordinator persists this payload and invokes:

```sh
uv run --locked python ../review-graph/scripts/review_graph_runtime.py \
  compile-validation \
  --input <dispatch-and-payload.json> \
  --artifact <compiled-validation.md> \
  --metadata <compiled-validation-evidence.json>
```

The compiler inserts command/environment digests, fingerprints, requirement
mappings, ledger export, canonical machine evidence, and artifact identities,
then runs the existing native and envelope acceptance gates.
