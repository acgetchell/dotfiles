# Compact Graph Validation Dispatch

Execute only the exact `review-graph` unit. The graph owns planning, coalescing,
placement, compilation, and proof acceptance; never discover or broaden work.

## Required Dispatch

Require:

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

Missing fields mean `blocked`, never standalone discovery.

## Execution

1. Wait for the runtime-owned pre-execution workspace snapshot; verify source
   state.
2. Recheck that every dispatched command is non-mutating under repository-owned
   definitions or policy.
3. Execute each command exactly once in order. Respect `stop-on-failure` or
   `continue-independent`. Isolated working directories and external artifacts
   must remain beneath the dispatched isolation root.
4. Record command, working directory, executor, result, exit code, elapsed time,
   concise output evidence, actual platform and native/emulated mode, and
   approved artifact paths. Put unexecuted target cells and the boundary of any
   emulation in `limitations`.
5. Repeat the source-state check. Follow `worker_prompt`: serialize the complete
   payload once and stream it to `worker_payload_persistence.publish_command`,
   which reviews and publishes identical bytes. Return its bound receipt without
   echoing the payload.
6. The coordinator invokes the runtime-owned
   post-execution snapshot immediately afterward.

Do not report artifact digests, snapshots, fingerprints, or compiler identities.
When checks never started, leave `executions` empty and explain the observed
blocker in `limitations`. Never create placeholder outputs; runtime snapshots
record absence. Only the coordinator authorizes bounded launch recovery;
executed results remain owner evidence.

A successful command proves only the dispatched execution environment. Do not
describe a local aggregate run or focused emulation as native evidence for a
different platform.

Do not review code, diagnose findings, edit, install substitute toolchains,
change dependencies, re-plan, or create another worker.

Before asynchronous execution, read [execution timing](execution-timing.md) for
measurement and recovery.

## ValidationPayload

Publish one JSON object:

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
  "limitations": []
}
```

`passed` requires exit `0`; `failed` requires a nonzero integer. Both require
finite, nonnegative elapsed seconds, optionally with units. `not-run` requires `null` or
`"none"` for both fields. `blocked` allows unavailable timing and a nonzero or
unavailable exit code, with a concrete limitation. `reused` and `not-applicable`
contain no executions. Reference only dispatched artifact paths; the runtime
resolves their identities.

The coordinator invokes `compile-node` with the persisted payload and runtime
snapshots. The compiler derives all identities, mappings, ledger export, and
canonical evidence, then checks native and envelope acceptance. For low-level
`compile-validation` diagnosis, consult the runtime's `--help` and operation examples.
