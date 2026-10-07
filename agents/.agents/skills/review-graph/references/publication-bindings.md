# Publication Bindings

Read for optional coverage partitions or publication binding diagnostics.
Compact dispatches contain the applicable shapes/examples; full schemas remain
available lazily.

## Audit Coverage

`payload_schema.optional_shapes.coverage_units` includes all required unit fields.
Units partition every owned path and finding exactly once, using one-based
`finding_indices`. Their `dependency_paths` account for all inspected context.
`dependency_uncertainty` is required even when its value is `""` (no uncertainty);
a nonempty value conservatively prevents reuse. Omit `coverage_units` when no
complete partition can be declared.

## Validation Artifacts

`executions[].artifact_paths` references exact declared artifact roots, including
external log roots. Generated children belong in evidence text, not typed
references. Publication rejects unknown roots/children and absent outputs before
writing, naming permitted roots. Use `[]` when no artifact was produced. Correct
only references; retain command results, timing, and snapshots. Runtime owns
identities/digests, and compilation still verifies before/after snapshots.

## Synthesis Evidence

Use `dispatch.synthesis_examples` for reference placement. Cover each predecessor
once; reconcile each accepted validator once, including all its coalesced
requirement IDs. Several reviewers may consume that single validator.
Fresh accepted evidence uses `accepted`; consuming another worker's result does
not establish `reused`, which requires runtime proof. Merge inherited needs by
unique `requirement_id`, retaining all originating evidence IDs, owners, reasons,
and requested evidence in the merged row. Keep distinct requirement IDs separate.
Platforms without their own accepted evidence belong in limitations/risks.
Required unexecuted validators still block readiness; separate hosted evidence
gets its own ID and bound platform.

Publication reloads the immutable dispatch, verifies predecessor compiler
artifacts using a shared hashed plan sidecar, and reports synthesis binding
errors together before writing. The plan/source references are runtime inputs,
not additional worker reading. When routing reuses audits from the same source
state, the coordinator supplies their compiler `artifact_path`/`metadata_path`
pairs in `materialize-dispatches.sources`. Materialization verifies those
artifacts and binds the needed references in the sidecar; continuations retain
them. Cross-state audit reuse continues to use planner-bound transitions.
Native compilation and final proof still recheck
acceptance and current captures. Preserve every failed diagnostic: schema
failures allow one schema retry; semantic binding failures separately allow one
consolidated metadata correction. A second failure of either kind blocks the
node, and neither counter resets the other. Corrections preserve source,
commands, timings, snapshots, and review conclusions.
