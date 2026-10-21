# Compact Graph Validation Dispatch

## Required Dispatch

- exact validation unit from the accepted graph plan
- expected source, worktree, and repository-state fingerprints
- exact state-verification command
- execution location and fresh-context identity
- exact commands, corresponding working directories, environment, toolchain,
  features, platform naming the actual executor, artifact owner, and mutation
  lock; encode the target platform and native/emulated mode in the
  digest-covered environment or features rather than only in narrative evidence
- approved artifacts with status provenance; exact effects, absolute isolation
  root, and runtime snapshot policy
- recursive required payload shape and the exact worker payload path
- dependency policy and elapsed bounds
- execution-tool `executor_requirements.sandbox_permissions` (legacy: `use_default`)

Missing fields mean `blocked`, not standalone discovery.

## Execution

1. Run `validation_observations.before.capture_command`, then its
   `workspace_command`. Without `validation_observations`, obtain before/after
   source captures and workspace snapshots from the coordinator.
2. Verify every command is non-mutating under repository policy.
3. Apply required tool permissions; respect approvals. If unavailable, report
   blocked. Execute each command exactly once in order. Respect `stop-on-failure` or
   `continue-independent`. Isolated working directories and external artifacts
   must remain beneath the dispatched isolation root.
4. Record command, working directory, executor, result, exit code, elapsed time,
   concise output evidence, actual platform and native/emulated mode, and
   approved artifact paths. Put unexecuted target cells and the boundary of any
   emulation in `limitations`.
   For Git-dependent commands, read [dependency examples](git-dependencies.md) before execution.
   For failures, classify `failure_kind` as source, infrastructure, timeout or inconclusive.
5. Run `validation_observations.after.capture_command`, then its
   `workspace_command`, before publication. Follow `worker_prompt`: serialize the complete
   payload once and stream it to `worker_payload_persistence.publish_command`,
   which reviews and publishes identical bytes. Return its bound receipt without
   echoing the payload.

Do not report artifact digests, snapshots, fingerprints, or compiler identities.
When checks never started, leave `executions` empty and explain the observed
blocker in `limitations`. Never create placeholder outputs; runtime snapshots
record absence. For executed permission failures, report `failed`, quote the
denial in `evidence`, and retain an approved log. Only coordinators request recovery.

Success covers only the dispatched environment; local/emulated runs cannot
establish another platform's native behavior.

For strict Semgrep failures, including `0 findings`, follow
[diagnostic guidance](../../project-tooling-review/references/static-analysis.md#validation).
Request missing diagnostics through the coordinator.

Before asynchronous execution, read [execution timing](execution-timing.md) for
measurement and recovery.

## ValidationPayload

Publish version 3 JSON:

```json
{
  "schema_version": 3,
  "status": "passed | failed | blocked",
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
  "limitations": []
}
```

`passed` requires exit `0`; `failed` requires a nonzero integer. Both require
finite, nonnegative elapsed seconds, optionally with units. `not-run` requires `null` or
`"none"` for both fields. `blocked` allows unavailable timing and a nonzero or
unavailable exit code, with a concrete limitation. `artifact_paths` names exact
`validation_unit.allowed_artifacts[].path` roots, including external logs.
Children belong in evidence text; absent outputs use `[]`. Publication names
permitted roots on rejection. Correct references without reruns; runtime owns
identities/snapshots.

`compile-node` consumes the persisted payload and runtime snapshots, derives
identities, mappings, ledger export and canonical evidence, and checks
native/envelope acceptance. Diagnose with runtime `--help` and operation examples.
