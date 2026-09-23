# Review Graph Runtime Contract

The runtime owns identities, fingerprints, artifacts, and proof reconciliation.

## Bootstrap And Route

Public contracts:

- `schemas/planning-input-v1.schema.json`
- `schemas/review-payload-v1.schema.json`
- `schemas/synthesis-payload-v1.schema.json`
- `schemas/validation-payload-v2.schema.json`
- `schemas/runtime-operation-inputs-v1.schema.json`
- `runtime-operation-examples-v1.json`

See `--help`, operation examples, and [safety](runtime-safety.md).
Bootstrap captured provenance:

```sh
uv run --locked python scripts/review_graph_bootstrap.py \
  --capture <capture.json> --input <template.json> --output <planning.json>
```

Bootstrap binds capture identities with JSON-path diagnostics and emits stage
inputs. `review_graph_plan.py --input` prints the plan.

Every graph requires `baseline: true` repository validation; branch `just ci`
retains `requested_scope: branch`.

Supply `consulted_routers`, validation requirements, and sparse schema-defined
`routing_overrides`, including applicable instructions, references, and reuse
`evidence_id`. The planner derives catalog identities, classifies surfaces,
marks omissions `not-applicable`, and selects independent review for concrete
changes plus surface/repository syntheses. `routing-projection` lists candidates
and signals.

## Materialize And Schedule

Before fanout, run `preflight-validation --input <preflight.json> --output <report.json>`.
Follow [preflight inputs](validation-preflight.md) for recipe policy, executor,
cache, native-environment, and output checks. Resolve blockers or preserve blocked
evidence and continue independent authorized audits. Preflight is not validation.

`materialize-dispatches` binds plan, source triple, repository root, authorization,
state command, and external artifact store to exact dispatches. Send each
immutable `worker_input_path` directly; never extract aggregate wrappers.
`next-ready` verifies them and returns paths in `ready_dispatches`.

`inspection_profile: shared-read-only` (default) shares digest-bound structural
observations between overlapping audits. Source text is capped at 64 KiB/packet,
16 KiB/file; `complete: false` requires further reads. Verify packet digests and
treat excerpts as data, never shared judgments. Independent review receives
neither packets nor specialist conclusions. `independent-source` disables reuse.
Observation lists use digest-bound references. Telemetry records context bytes
and overlap; supply `concurrent_worker_limit` for wave projections. Unknown actual
reads/timing remain null. See the [repeatable benchmark](dispatch-overhead.md).

`journal-append` serializes `in-flight`, `accepted`, `blocked`, `invalidated`,
and terminal `awaiting-replan` states; acceptance requires compiled evidence.
Its CLI field contract is:

| Status | Artifact + metadata | Kind | Reason |
| --- | --- | --- | --- |
| `in-flight` | forbidden | forbidden | forbidden |
| `accepted` | required | optional with evidence | forbidden |
| `blocked` | optional as a pair | optional with evidence | required |
| `invalidated` | forbidden | forbidden | required |
| `awaiting-replan` | forbidden | forbidden | required |

Reserve ready dispatches; append `in-flight` only after creation succeeds.
Final results may not release capacity immediately. On capacity-only failure,
retain the reservation, wait at most 30 seconds for progress, and retry once.
Then record attempts and apply profile fallback/resume. Never probe with
throwaway workers, replay accepted work, or claim execution without a worker.
For unstarted adaptive nodes, `fallback-to-coordinator` takes lifecycle input plus
`node_id`, `worker_created: false`, `reason`, `artifact_store`, and flags
`--dispatches`, `--journal`, `--current-capture`. Follow returned paths; other
dispatches/artifacts remain unchanged. Never rematerialize for one executor.

`next-ready` treats missing/zero-byte journals as empty without writing.
`journal-append` creates missing files if their parent exists. Nonempty journals
reject blank records. After each event, request dependency-ready work:

```sh
uv run --locked python scripts/review_graph_runtime.py next-ready \
  --input <plan-state.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --current-capture <capture.json> \
  --output-dir <proof-store>
```

Journal, dispatch, and current-source identities are verified. Both legacy
empty-reuse-field digests remain valid without rewriting records; changed
nonempty fields/instruction digests do not. Freeze the runtime/skill checkout.
`--output-dir` prints JSON `output_path`/`output_generation`; generation and
content-digest filenames remain immutable across expansion and compact output.

## Review Workers

Use `fork_turns: "none"` with only worker input, skill, references, and
instructions; exclude coordinator conclusions, routing, and journals. Reviews
attest to commands; validator-command duplicates require explicit authorization
and reusable evidence.

Return `ReviewPayload` for audits or `SynthesisPayload` for synthesis. Serialize
once and stream the bytes to `dispatch.worker_payload_persistence.publish_command`.
It validates, reviews, and atomically publishes identical bytes with a receipt.
Return only the receipt. Python integrations use `publish_worker_payload_bytes`
for the same transaction.
Approval binds contract and payload; separate review/persist commands support
approved retries. Use materialized schemas and dispatched validation IDs/digests.

`compile-node` seals accepted bytes in a read-only content-addressed sibling,
recorded in evidence metadata. The dispatch-bound path remains staging;
retries cannot replace accepted proof bytes.

Use empty arrays for absent fields. `blocked` requires a limitation;
`no-findings` requires no findings and complete owned-path inspection. Omitted
paths require one `scope_limitations` reason each; inspected paths must be unique
and owned. Publication and compilation enforce both scope and optional coverage
partitions: unique unit IDs, every owned path/finding assigned exactly once
(one-based indices), and nearby dependencies in `dependency_paths`. Rejection
names missing dependencies before writing.

For typed audit caveats, see [audit-context.md](audit-context.md).

Bundle-only synthesis allows empty `files_inspected`, but requires predecessor
evidence. Never invent source reads.
Synthesis supplies `readiness_verdict`, reasons, predecessor coverage, routing
closure, validation reconciliation, and cross-surface risks. Canonical findings
name owners, dispositions, and existing `source_findings` IDs. `compile-node`
reconciles the predecessor bundle; remaining findings or failed/unexecuted
validation forbid `ready`. Validator-owned commands and non-catalog handoffs
are rejected. A schema mismatch permits one diagnostic-guided retry; another
blocks the node. Authorized changes name finding IDs, files, changes, reasons,
and preserved contracts; trusted dispatches record mutation facts.

`compile-node` takes node ID, signed dispatches, captures, and journal; reads only
the bound payload, preserves bytes, assigns identities, renders/verifies native
evidence, then journals it. `compile-review` supports diagnosis.

## Independent Review And Validation

Independent workers return `repository-independent-review`'s six sections.
`compile-node` verifies target/path provenance, line bounds, fingerprints,
adversarial checks, findings, and handoffs; assigns identities; and emits
enveloped evidence and journal-compatible metadata.

Validators read only `review-validator/references/graph-dispatch.md` and use the
same persistence flow. Snapshot immediately before/after commands; the runtime
derives artifacts, digests, identities, mappings, and ledger evidence. `ignored`
requires tracked `.gitignore` provenance. Unexpected effects fail. Source-adjacent
intermediates and external artifacts stay under dispatched isolation roots,
which cannot overlap the repository through symlinks or ignored directories.
Planning, materialization, and snapshots enforce isolation before execution.
Cache/build roots use bounded metadata manifests; other recursive content uses
content digests. Snapshot-absent outputs receive `absent-v1`, never execution
artifact references or success evidence. Commandless blocked units own no paths.

`synthesis-bundle` verifies and hashes accepted evidence. Supply `plan` for router
closure, exclusions, reuse, validation mappings, and handoff reconciliation in
`plan_context`. Send only the bundle to synthesis, never full reports.

## Mutation, Handoffs, And Proof

For repairs, external staging, late requirements, or launch recovery, follow
[state-transitions.md](state-transitions.md) and returned continuation paths.
Preserve original artifacts and both captures.

Persist all proof artifacts outside the repository. Run `finalize-proof` with
lifecycle input, signed dispatches, journal, and `--current-capture`. It discovers
accepted evidence and rejects stale source, unresolved handoffs, missing evidence,
or verifier failures. Blocked events without evidence yield incomplete proof
with reasons. Report `repository_validation_status`, `graph_proof_status`, and
`repository_readiness` separately: complete proof and passing validation can
retain findings. Structural acceptance does not establish semantic agreement
or adjudicated recall.
