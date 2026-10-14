# Frozen Runs And Delivery Profiles

## Freeze Before Planning

The bootstrap CLI automatically snapshots its skill root outside the reviewed
repository, beside the bootstrap output (`<output-stem>.runtime`). It retains
runtime scripts, schemas, routing, skill/reference contents, and the installed
`research-repo-tools` support package. It pins the Python executable digest and
version. Snapshot creation rejects symlinks and concurrent resource edits,
publishes atomically, and verifies the retained resources before use.

Use `$SKILLS_ROOT/<skill>/references/<file>` or a path relative to the approved
skill root in template `static_references`. Absolute static references are
rejected before creating a snapshot, with the exact supported spelling in the
diagnostic. Outside-root and symlink references remain invalid. Correct the
template and retry the same bootstrap output; no frozen run needs replacing.

Bootstrap re-executes under that snapshot before issuing the plan or dispatches.
All emitted commands, skill paths, and schema references use the retained root.
Use those commands throughout the run; live dotfiles changes apply to the next
run. Repository instructions and source remain capture-bound inputs: changing
them still requires affected verification. Validation toolchains, environments,
platform cells, and exact-commit CI retain their own execution identities.

An identical bootstrap retry uses the original snapshot. To recover after a
live runtime update, use the supported launcher and its saved reference:

```sh
uv run --locked python "$SKILLS_ROOT/review-graph/scripts/review_graph_session.py" \
  --reference <output-stem>.runtime/runtime-reference.json \
  --script review_graph_runtime.py -- \
  finalize-proof --input <lifecycle.json> --dispatches <dispatches.json> \
  --journal <execution.jsonl> --current-capture <capture.json> \
  --output <proof.json>
```

Recovery verifies the original manifest, resource bytes, and interpreter before
loading the saved plan. Never edit signed artifacts or relabel payloads to a
new runtime. If retained resources or the original interpreter are unavailable,
report the recovery blocker; do not silently rerun validation. Low-level Python
planning APIs remain available for fixtures; production runs start with bootstrap
to obtain the freeze guarantee.

## Routine Delivery (Default)

Bootstrap records `--delivery-profile routine` by default. Keep exhaustive
applicable specialist/scientific coverage and the existing bounded repair
budget. In review-and-fix work, complete initial specialists, batch authorized
required and requested optional fixes, then verify changed contracts and retain
proved unchanged judgments. Run one fresh conclusion-blind independent review
of the finished change. Repeat it only when subsequent source/dependency changes
affect its judgment. Do not launch it on intermediate source just to satisfy
bookkeeping. Routine review-and-fix bootstrap plans hold independent scheduling
until source audits finish, using a scheduling barrier without semantic
predecessor edges. At that boundary, perform authorized repair batches before
requesting more work; the replacement plan retains the barrier. Read-only
reviews run independence against the captured final target.

Workers receive compact `*.execution.json` views through receipts. These retain
owned scope, commands, task context, publication commands, and lazy schema and
canonical-input references. Full dispatches and compiler provenance remain
immutable on disk. Publication, compilation and persistence receipts are
deterministic; workers author semantic judgments only. Shared read-only packets
reduce repeated source reads while every specialist retains its own judgment;
the independent reviewer receives raw source without specialist conclusions.

Report promptly with `report-delivery`, using the same lifecycle, dispatches,
journal, current capture and output arguments as `finalize-proof`. This verifies
available evidence and reports completed repair batches, remaining findings,
pending nodes, validation dispositions and readiness. It always records
`graph_proof_status: not-certified`; a routine result never claims a complete
`RepositoryReviewProof`. A partial report does not waive unfinished semantic,
scientific or validation obligations. Continue authorized affected verification
when feasible and disclose anything that remains blocked.

## Explicit Certification

Select `--delivery-profile certification` when the user explicitly asks for a
formal repository proof/certification. Complete syntheses and every applicable
review and validation requirement, then run `finalize-proof` against the signed
dispatches and journal. Only a verified `complete` result establishes formal
proof completion. An explicit later `finalize-proof` request may certify a
routine run's retained evidence without resetting its repair budget.

Keep four conclusions distinct in either profile:

| Conclusion | Required evidence |
| --- | --- |
| Fixes delivered | Authorized captured source changes, with deferred findings disclosed |
| Local validation | Accepted current-source local command results |
| Hosted/native CI readiness | Required platform cells and exact-commit CI outcomes, with failed cells assigned to their owning contract |
| Formal certification | Verified complete `RepositoryReviewProof`, separately from CI inspection |

Pending/unavailable hosted checks block readiness; they alone do not invalidate
unchanged source audits. Actual failed requirements retain an owning recheck
disposition. Source/dependency/uncertainty assessments take place before such
failure dispositions. Metadata-only branch creation and staging preserve
eligible source and completed independent judgments. Passed source-only validators
retain their standard persisted metadata and original executions when captured Git
objects/modes, selection, execution identity and required artifacts match. Legacy
or Git-sensitive validation and syntheses refresh their bindings. HEAD, immutable comparison
base, captured scope, file bytes and modes must remain unchanged; staged scope
changes still require replanning. Neither metadata transitions, missing CI nor
proof bookkeeping restart a comprehensive review or reset the repair budget.

## Matched Protocol Measurement

[Retained measurements](measurements/frozen-runs-2026-10-12.json) compare the
runtime at `f8db9cba94356bb035d7c7c58acf61f4b7579f16` with this change over five
alternating trials of the same scale-20 fixture, planner, dependencies and
semantic observations. Nine audits and one independent payload are published
and compiled; validation and synthesis commands are not executed.

| Measured quantity | Before | After |
| --- | ---: | ---: |
| Worker-facing input bytes | 360,166 | 223,945 |
| Execution instruction bytes | 49,893 | 15,940 |
| Canonical worker input bytes retained on disk | 360,166 | 363,028 |
| Scripted source reads / repeated reads | 265 / 0 | 265 / 0 |
| Scripted coordinator API operations | 21 | 21 |
| Independent publications / formatting retries | 1 / 0 | 1 / 0 |
| Median materialization seconds | 0.215 | 0.213 |
| Median protocol seconds | 0.410 | 0.432 |

Worker-facing bytes fall about 38% and instruction bytes about 68%; canonical
provenance remains on disk. Protocol time increases about 5% in this sample,
so these results establish a size reduction, not an overall speedup. Four seeded
findings are preserved; that is not a measurement of reviewer recall. Provider
tokens/cost, model review time, model-assisted publication and recovery steps
remain unavailable. The replay excludes startup freezing, Git capture and model
work; it does not measure savings from avoided post-fix validation or routine
certification. Source/metadata handoff and routine delivery are exercised
separately by the integration fixtures.
