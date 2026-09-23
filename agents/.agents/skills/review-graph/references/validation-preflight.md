# Validation Preflight

Before fanout, run `preflight-validation --input <preflight.json> --output <report.json>`.
Supply `plan`, an existing absolute `repository_root`, `cache_paths`, and
`command_policy` entries: exact `command`, `disposition` (`allowed`/`blocked`),
and `reason`. Inspect nested recipes and fixtures against user restrictions;
omitted commands are unreviewed.

For each executable unit, supply `execution_prerequisites` with `node_id`,
explicit `executables` including nested tools, `native_available`, and a concrete
`reason`. The runtime checks executable discovery and working directories;
the native-environment observation comes from the coordinator. An omitted
prerequisite remains uninspected and blocks execution readiness. These checks
describe the current executor; they cannot certify a different sandbox's
permissions or toolchain. See the `preflight-validation` definition in
[operation schemas](schemas/runtime-operation-inputs-v1.schema.json).

The read-only report checks obligations, caches, and effect paths without
executing commands or certifying sandbox write access. Missing permitted outputs
are recorded as absent without creating them. `allowed_artifacts` grants output
permission; required outputs belong in `expected_evidence`. An explicit artifact
digest additionally requires that identity. With a trusted repository root,
planning rejects non-ignored workspace effects outside isolated execution before
materialization. Effect paths may contain spaces; prose must not replace paths.

Configuration errors and execution blockers remain separate from repository
findings. Resolve blockers or preserve blocked evidence and continue independent
authorized audits. The preflight report is not validation evidence and cannot
make a failed or blocked attempt pass. Keep its report beside the immutable
attempt and follow the runtime's continuation configuration after recovery.
