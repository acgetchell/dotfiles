# Review Graph Runtime Contract

The runtime owns identities, fingerprints, artifacts, and proof reconciliation.
Load maintainer contracts only for implementation changes or rejection diagnosis.

## Bootstrap And Route

Public contracts:

- `schemas/planning-input-v1.schema.json`
- `schemas/review-payload-v1.schema.json`
- `schemas/validation-payload-v2.schema.json`
- `schemas/runtime-operation-inputs-v1.schema.json`
- `runtime-operation-examples-v1.json`

Safety details: [runtime-safety.md](runtime-safety.md).

`--help` links input definitions and examples.

Bootstrap capture provenance into the routing/validation template:

```sh
uv run --locked python scripts/review_graph_bootstrap.py \
  --capture <capture.json> --input <template.json> --output <planning.json>
```

Bootstrap binds capture identities with JSON-path diagnostics. Runtime commands
consume its stage inputs; `review_graph_plan.py --input` prints the plan.

Every graph needs a repository check with `baseline: true`, independent of review
scope: branch `just ci` keeps `requested_scope: branch`.

Supply `consulted_routers`, validation requirements, and sparse
`routing_overrides`: `catalog_id`, `disposition`, `reason`,
`applicability_evidence`, `review_surface`, `owners`, plus applicable validation,
instruction, reference, and reuse `evidence_id` fields. Catalog identities are derived.

The planner marks omissions `not-applicable`, applies the repository classifier,
and selects independent review for concrete changes, consulted surface syntheses,
and repository synthesis. `routing-projection` lists all candidates and signals.

## Materialize And Schedule

`materialize-dispatches` takes plan, source triple, repository root, authorization,
state command, and external artifact store; binds compiler/journal operations,
artifact paths, payload schemas, instruction digests, command policy, validation
units, and predecessors.
`worker_input_path` names the immutable per-node dispatch wrapper and prompt.
Send it directly; do not extract aggregate wrappers. `next-ready` verifies these
files and returns their paths in `ready_dispatches`.

`inspection_profile` defaults to `shared-read-only`: overlapping audits share a
persisted, digest-bound structural observation, not semantic judgments.
`independent-source` disables this reuse.

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

Reserve ready dispatches locally; append `in-flight` only after creation succeeds.
A final result may not immediately release capacity. On capacity-only failure,
preserve the reservation, wait for lifecycle/capacity progress (at most 30 seconds),
and retry once. Never probe with throwaway workers or replay accepted work.
If unavailable, apply the profile's fallback/resume policy and record attempts;
no worker means no execution evidence.
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

The runtime verifies journal, dispatch, and current-source identities, accepting
both established empty-reuse-field plan digests without rewriting records.
Freeze the runtime/skill checkout per run; compatibility never permits changed
non-empty plan fields or ignored instruction digests.
`--output-dir` prints JSON `output_path`/`output_generation` after publication;
journal-generation filenames ensure immutable, replayable output.

## Review Workers

Use `fork_turns: "none"` with only the worker input, skill, references, and
instructions. Exclude coordinator conclusions, routing, and journals. Shared
observations do not replace independent judgment. Reviews attest to commands;
validator-command duplicates need explicit authorization and reusable evidence.

Return only `ReviewPayload`. Write its exact bytes to the candidate, then execute
`worker_payload_persistence.command` unchanged. Its complete argv includes the
executable, script, and bound paths; it validates and atomically publishes
`worker_payload_path`.

Use the materialized payload schema; planned needs reference dispatched
validation IDs/digests.

`compile-node` seals accepted bytes in a read-only content-addressed sibling,
recorded in evidence metadata. The dispatch-bound path remains staging;
retries cannot replace accepted proof bytes.

Use empty arrays for absent fields. `blocked` requires a limitation;
`no-findings` requires no findings and inspection of every audit-owned path.
A completed audit may omit an owned path only with exactly one path-specific
`scope_limitations` reason. Inspected paths must be unique and dispatch-owned;
persistence and compilation both enforce this.
Bundle-only synthesis allows empty `files_inspected`, but requires predecessor
evidence. Never invent source reads.
The compiler rejects validator-owned
commands and non-catalog handoffs. One schema mismatch permits one retry using
field diagnostics; a second mismatch blocks the node. For authorized fixes,
each change names finding IDs, files, what changed, why, and the preserved
contract; the trusted dispatch records mutation facts.

`compile-node` takes node ID, signed dispatches, captures, and journal; reads only
the bound payload, preserves bytes, assigns identities, renders/verifies native
evidence, then journals it. `compile-review` supports diagnosis.

## Independent Review And Validation

The conclusion-blind independent worker returns `repository-independent-review`'s
six sections. Pass the native result to `compile-node`, which verifies target/path
provenance, line bounds, before/after fingerprints, dispatched adversarial checks,
findings, and catalog handoffs; assigns identities; appends the envelope and
Machine Evidence; and emits journal-compatible metadata.

Coalesced validators read only `review-validator/references/graph-dispatch.md`,
publish through `persist-worker-payload`, and return identical bytes. Snapshot
the workspace immediately before and after commands; the runtime derives
artifact records, digest modes, command/environment identities, mappings, and
ledger evidence. `ignored` artifacts require a tracked `.gitignore`; other
excludes fail. Unexpected workspace effects fail. Source-adjacent intermediates
and outside-repository artifacts stay under the dispatched isolation root.
Known cache/build roots use bounded metadata manifests; other recursive content
uses content digests.
Isolation roots must not overlap the repository, including through symlinks or
ignored directories. Planning, materialization, and snapshots enforce this
before execution.

`synthesis-bundle` verifies accepted artifacts, hashing findings, mappings,
validation, handoffs, limitations, and artifacts. Synthesis receives only this
bundle, never full reports. Supply `plan` for hashed router closure, exclusions,
exact reuse, requirement/validator mappings, and handoff reconciliation in
`plan_context`.

## Mutation, Handoffs, And Proof

Accepted late validation requirements block synthesis/proof until exactly planned
or explicitly user-excluded. Run
`reconcile-validation-requirements --input <request.json> --journal <journal>
--dispatches <dispatches.json> --current-capture <capture.json> --output <result.json>`.
Supply `plan` and `source_state` to inspect discoveries. Expand with
`validation_requirements` (planning-schema objects) and `artifact_store`, or
`user_exclusions` bound to returned origin, requirement ID/digest, and reason.
Follow returned lifecycle/journal/dispatch paths. Source state and accepted
audits/CI remain; synthesis inputs refresh. Wait for active workers before expansion.
Details: [planning-contract.md](planning-contract.md#late-validation-expansion).

Run `reconcile-handoffs` before expansion. Selected, exactly reused, or user-excluded
catalog entries resolve handoffs; only `new_routing_triggers` expand routing.
Final proof classification uses typed catalog mappings reparsed from accepted
evidence, never caller-provided resolved IDs.

After authorized repairs, run `advance-after-mutation` with the immediately
preceding `previous_capture`, `new_capture`, and their exact `changed_paths`
content delta. Invalidation follows owners and downstream dependencies. Supply
accepted `sources` for verified unchanged-input audit reuse; validators,
independent reviews, syntheses, and unproven audits rerun. Follow returned
`lifecycle_input_path`, `dispatches_path`, `journal_path`, and `capture_path`;
old artifacts remain unchanged. `preserved_evidence` contains only proven reuse.
Per-node `reuse_decisions` explain disposition and reason code, distinguishing
`coverage-limitations` from `unclassified-limitations`. Untyped caveats prevent
reuse, never inferred informational exemptions.

Persist all capture, plan, payload, compiled evidence, journal, synthesis,
invalidation, manifest, and proof artifacts outside the reviewed repository.
Run `finalize-proof` with the lifecycle bundle, signed dispatch set, journal,
and `--current-capture`; it discovers accepted evidence paths, rejecting stale
source state, unresolved handoffs, missing evidence, or verifier failures.
Blocked events without evidence produce an incomplete proof with their reason,
not nonexistent-artifact reads. Report `repository_validation_status`
separately from `graph_proof_status`; structural independent-evidence
acceptance does not imply semantic agreement or adjudicated recall.
