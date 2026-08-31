# Review Graph Runtime Contract

The runtime owns identities, fingerprints, artifacts, and proof reconciliation
for all profiles. Load maintainer contracts only for implementation changes or
rejection diagnosis.

## Bootstrap And Route

The versioned public contracts are:

- `schemas/planning-input-v1.schema.json`
- `schemas/review-payload-v1.schema.json`
- `schemas/validation-payload-v2.schema.json`
- `schemas/runtime-operation-inputs-v1.schema.json`
- `runtime-operation-examples-v1.json`

`--help` links input definitions and examples.

Bootstrap capture provenance into the compact routing and validation template:

```sh
uv run --locked python scripts/review_graph_bootstrap.py \
  --capture <capture.json> --input <template.json> --output <planning.json>
```

Bootstrap binds capture identities with JSON-path diagnostics. Runtime commands
consume its stage inputs; `review_graph_plan.py --input` prints the bundled plan.

Every graph needs a repository check with `baseline: true`. This is not baseline
review scope: a branch `just ci` requirement keeps `requested_scope: branch`.

Supply `consulted_routers`, validation requirements, and sparse
`routing_overrides`: `catalog_id`, `disposition`, `reason`,
`applicability_evidence`, `review_surface`, `owners`, plus applicable validation,
instruction, reference, and reuse `evidence_id` fields. Catalog identities are derived.

The planner expands omissions to `not-applicable`, applies the repository
classifier, and selects independent review for a concrete change plus every
consulted surface synthesis and repository synthesis. Use
`routing-projection` for the complete candidate list and classifier signals.

## Materialize And Schedule

Run `materialize-dispatches` with the plan, source triple, repository root,
authorization, state command, and external artifact store. Dispatches bind
compiler/journal operations, artifact paths, payload schemas, instruction digests,
command policy, validation units, and predecessors.
`worker_input_path` names an immutable per-node file containing that exact
dispatch wrapper and worker prompt. Send it directly; do not extract wrappers
from the aggregate. `next-ready` verifies these files and returns their paths
inside `ready_dispatches`.

`inspection_profile` defaults to `shared-read-only`: overlapping audit nodes
receive one persisted, digest-bound structural observation while retaining
separate semantic judgments. Use `independent-source` to disable this bounded
reuse.

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
A final result need not release host capacity immediately. On a capacity-only
failure, preserve that exact reservation, wait for lifecycle/capacity progress
(at most 30 seconds), and retry once. Do not probe with throwaway workers or
replay accepted work. If still unavailable, use the profile's fallback/resume
policy and record the failed attempts; no worker means no execution evidence.

`--journal` may initially be missing or zero-byte; `next-ready` treats both as
empty without writing. `journal-append` creates a missing file when its parent
exists. Nonempty journals reject blank records.
After each event, request only dependency-ready work:

```sh
uv run --locked python scripts/review_graph_runtime.py next-ready \
  --input <plan-state.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --current-capture <capture.json> \
  --output-dir <proof-store>
```

The runtime verifies journal, dispatch, and current-source identities.
`--output-dir` prints JSON `output_path` and `output_generation` after publication;
filenames use the journal generation for immutable, replayable output.

## Review Workers

Use `fork_turns: "none"` with only the worker input, skill, references, and
instructions. Exclude coordinator conclusions, routing, and journals. Shared
observations do not replace independent judgment. Reviews attest to commands;
validator-command duplicates need explicit authorization and reusable evidence.

Return only a `ReviewPayload` object. Write its exact bytes to the candidate,
then execute `worker_payload_persistence.command` unchanged. Its complete argv
includes the executable, runtime script, and bound paths; it validates and
atomically publishes `worker_payload_path`.

Use the materialized payload schema for fields and enum values.

`compile-node` copies accepted bytes to a read-only content-addressed sibling
and records that sealed path in evidence metadata. The dispatch-bound payload
path remains staging only; later valid retries cannot replace accepted proof
bytes.

Use empty arrays for absent fields. `blocked` requires a limitation;
`no-findings` requires no findings and inspection of every audit-owned path.
A completed audit may omit an owned path only when `scope_limitations` contains
exactly one path-specific reason for it. Inspected paths must be unique and
owned by the dispatch. Payload persistence and compilation both enforce this.
Bundle-only synthesis may leave `files_inspected` empty; predecessor evidence
remains mandatory. Do not invent source reads to satisfy a field.
The compiler rejects validator-owned
commands and non-catalog handoffs. One schema mismatch permits one retry using
field diagnostics; a second mismatch blocks the node. For authorized fixes,
each change names finding IDs, files, what changed, why, and the preserved
contract; the trusted dispatch records mutation facts.

Run `compile-node` with the node ID, signed dispatch set, captures, and journal.
It reads only the bound payload, preserves its bytes, assigns identities,
renders and verifies native evidence, then journals it. `compile-review` remains
available for diagnosis.

## Independent Review And Validation

The conclusion-blind independent worker returns the six sections defined by
`repository-independent-review`. Pass the native result to `compile-node`; its
compiler verifies target/path
provenance, line bounds, before/after fingerprints, dispatched adversarial
checks, findings, and catalog handoffs; it assigns identities, appends the
envelope and Machine Evidence, and emits journal-compatible metadata.

Coalesced validators read only `review-validator/references/graph-dispatch.md`,
publish through `persist-worker-payload`, and return identical bytes. Snapshot
the workspace immediately before and after commands; the runtime derives
artifact records, digest modes, command/environment identities, mappings, and
ledger evidence. `ignored` artifacts require a tracked `.gitignore`; other
excludes fail. Unexpected workspace effects fail. Source-adjacent intermediates
and outside-repository artifacts stay under the dispatched isolation root.
Known cache/build roots use bounded metadata manifests; other recursive content
uses content digests.

Use `synthesis-bundle` to verify accepted artifacts and derive the compact,
hashed findings, mappings, validation, handoff, limitation, and artifact view.
Synthesis receives that bundle, never full predecessor reports.
Supply its `plan` to include hashed router closure, exclusions, exact reuse,
requirement/validator mappings, and handoff reconciliation in `plan_context`.

## Mutation, Handoffs, And Proof

Accepted late validation requirements block synthesis and final proof until
exactly planned or explicitly user-excluded. Run
`reconcile-validation-requirements --input <request.json> --journal <journal>
--dispatches <dispatches.json> --current-capture <capture.json> --output <result.json>`.
Start with `plan` and `source_state` to inspect discoveries. To expand, add
`validation_requirements` (planning-schema objects) and `artifact_store`, or
explicit `user_exclusions` bound to the returned origin, requirement ID/digest,
and reason. Follow returned lifecycle, journal, and dispatch paths. Source state
and accepted audits/CI stay unchanged; synthesis inputs refresh. Wait for active
workers before expansion. Details: [planning-contract.md](planning-contract.md#late-validation-expansion).

Run `reconcile-handoffs` before expansion. Selected, exactly reused, or
user-excluded catalog entries resolve existing handoffs; only
`new_routing_triggers` expand routing. Final proof classification is derived
from the typed catalog mappings reparsed from accepted evidence, not from
caller-provided resolved IDs.

After authorized repairs, run `advance-after-mutation` with the immediately
preceding `previous_capture`, `new_capture`, and their exact `changed_paths`
content delta. Invalidation follows owners and downstream dependencies. Supply
accepted `sources` for verified unchanged-input audit reuse; validators,
independent reviews, syntheses, and unproven audits rerun. Follow returned
`lifecycle_input` and fresh dispatches; old artifacts remain unchanged.

Persist all capture, plan, payload, compiled evidence, journal, synthesis,
invalidation, manifest, and proof artifacts outside the reviewed repository.
Run `finalize-proof` with the lifecycle bundle, signed dispatch set, journal,
and `--current-capture`; it discovers accepted evidence paths without a
caller-authored sources document. It rejects stale source state, unresolved handoffs, missing
evidence, or verifier failures. Report `repository_validation_status`
separately from `graph_proof_status`; structural independent-evidence
acceptance does not imply semantic agreement or adjudicated recall.
