# Validation Preflight

Before fanout, run `preflight-validation --input <preflight.json> --output <report.json>`.
Supply `plan`, an existing absolute `repository_root`, `cache_paths`, and
`command_policy` entries: exact `command`, `disposition` (`allowed`/`blocked`),
and `reason`. Inspect nested recipes and fixtures against user restrictions;
omitted commands are unreviewed.

For each executable unit, supply `execution_prerequisites` with `node_id`,
explicit host `executables` including nested tools, `native_available`, and a concrete
`reason`. The runtime checks executable discovery and working directories;
the native-environment observation comes from the coordinator. An omitted
prerequisite remains uninspected and blocks execution readiness. These checks
describe the current executor; they cannot certify a different sandbox's
permissions or toolchain. See the `preflight-validation` definition in
[operation schemas](schemas/runtime-operation-inputs-v1.schema.json).

For inspected `uv run --locked` commands, including nested Just recipes, use
the validated prerequisite template in
[operation examples](runtime-operation-examples-v1.json#/preflight-validation).
Keep host wrappers and native tools in `executables`; declare environment tools
by name in `uv_projects`, so Python need not exist on ambient PATH:

```json
{
  "node_id": "<validation node>",
  "executables": ["just", "uv"],
  "uv_projects": [{
    "project_directory": ".",
    "environment_path": ".venv",
    "executables": ["python", "pytest"]
  }],
  "native_available": true,
  "reason": "Inspected nested locked uv recipes use this existing project environment."
}
```

Adapt tool names to the inspected recipes, including native host tools such as
`cargo` where required. `project_directory` is the uv workspace root, relative
to `repository_root` or absolute. `environment_path` is the inspected effective
project environment, relative to that workspace root or absolute; copy an
explicit `UV_PROJECT_ENVIRONMENT` override here. uv defaults to `.venv` and
resolves relative overrides from the workspace root, as documented in
[uv project configuration](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).
The runtime does not infer overrides from its own process or parse recipes.
Do not use the template for `uvx`, isolated/script environments, `--active`, or
other wrappers unless their resolution has been independently inspected and
represented through explicit executable paths.

Preflight checks TOML syntax in `pyproject.toml` and `uv.lock`, requires an integer
`version` and string `requires-python` in the lockfile, and reads `pyvenv.cfg`.
It permits workspace roots without a `[project]` table and does not validate
the full uv metadata schema. It then checks the environment's Python and declared
tools in `bin` (`Scripts` on Windows), checking each repeated tool name only once.
It always requires the environment interpreter, including for console tools;
it never substitutes ambient Python or an ambient tool for a missing environment
executable. If recipes set `UV_PYTHON` or `--python` to a path, supply that path
as optional `configured_python` (relative to `project_directory` or absolute).
It must be executable and resolve to the existing environment interpreter;
missing paths or differing interpreters block readiness. Resolve version/name
selectors separately before using this path-only template.

The report's per-unit `executor_observations` separates host discovery from
uv project paths, resolved executables, and interpreter selection. Missing or
malformed metadata, missing environments, and broken/non-executable Python or
tools produce execution blockers. These observations establish discovery only;
they do not certify lock freshness, interpreter versions, installed dependency
consistency, or a later sync's success. Do not run uv, sync, download, or launch
validation to obtain this prerequisite evidence. Native availability, command
policy, cache observations, and hosted obligations remain separate checks.

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

For an unstarted grouped/mixed validator blocked by preflight, add
`preflight_blocked_nodes: [{"node_id": "<validator node>", "reason": "<concrete preflight blocker>"}]`
to `schedule-ready`. This holds execution without reserving a worker or taking
the serial lane, so authorized audits can continue unless a planned
[early validation barrier](repair-validation.md) holds them. Do not put a held validator
in `reserved_node_ids`, append `in-flight`, or claim validation evidence.
The compact receipt and `schedule_input_path` preserve the hold and reason.
After resolving the blocker and rerunning preflight, explicitly remove that
entry from a new scheduling request. The validator then becomes eligible;
dependent synthesis and final proof still require its accepted evidence.
Already-started or compiled blocked attempts use the recovery workflow in
[state transitions](state-transitions.md).
