# Review Graph Runtime Contract

Use this contract for ordinary adaptive, isolated, and mixed execution. The
planner and runtime own identities, fingerprints, digests, canonical artifacts,
envelopes, and proof reconciliation. Load maintainer contracts only when
changing those implementations or diagnosing a rejection.

## Bootstrap And Route

The versioned public contracts are:

- `schemas/planning-input-v1.schema.json`
- `schemas/review-payload-v1.schema.json`
- `schemas/validation-payload-v1.schema.json`
- `schemas/runtime-operation-inputs-v1.schema.json`
- `runtime-operation-examples-v1.json`

Every runtime subcommand links its exact input definition and a valid example
from `--help`.

Bootstrap capture provenance into the compact routing and validation template:

```sh
uv run --locked python scripts/review_graph_bootstrap.py \
  --capture <capture.json> --input <template.json> --output <planning.json>
```

Bootstrap binds each validator to the captured scope, worktree, and repository
fingerprints, capture command, and paths. Schema failures aggregate missing,
unknown, and malformed fields with JSON paths, accepted shapes, and enums.
Its output bundle contains schema-valid `planning_input`,
`materialization_input`, and `lifecycle_input` documents. Runtime commands that
own those stages accept the bundle directly.

Supply `consulted_routers`, validation requirements, and sparse
`routing_overrides`. Each override contains `catalog_id`, `disposition`,
`reason`, `applicability_evidence`, `review_surface`, and `owners`; selected
records may add `validation_requirement_ids`, `instruction_paths`, and
`static_references`, while exact reuse may add `evidence_id`. Do not author
router, rule, skill, path, priority, requirement, or synthesis identities.

The planner expands omissions to `not-applicable`, applies the repository
classifier, and selects independent review for a concrete change plus every
consulted surface synthesis and repository synthesis. Use
`routing-projection` for the complete candidate list and classifier signals.
Route shared workflows, recipes, lockfiles, toolchains, examples, and build
configuration to tooling/documentation and every affected language owner.

## Materialize And Schedule

After planning, run `materialize-dispatches` once. Its input names the accepted
plan, source triple, repository root, authorization, state command, and external
artifact store. Every output dispatch binds its compiler and journal operation,
canonical evidence/artifact paths, payload schema and digest, applicable
repository instructions and digests, command policy, validation unit, and
predecessor evidence. Planning stops before dispatch when a node mode lacks a
deterministic compiler or journal path.

`inspection_profile` defaults to `shared-read-only`: overlapping audit nodes
receive one persisted, digest-bound structural observation while retaining
separate semantic judgments. Use `independent-source` to disable this bounded
reuse.

Append lifecycle events serially with `journal-append`; valid states are
`in-flight`, `accepted`, `blocked`, `invalidated`, and terminal
`awaiting-replan`. Accepted events require the compiled artifact and metadata.
After each event, request only dependency-ready work:

```sh
uv run --locked python scripts/review_graph_runtime.py next-ready \
  --input <plan-state.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --current-capture <capture.json> \
  --output-dir <proof-store>
```

The runtime verifies the journal chain, dispatch digest, and current source
triple. Managed filenames use the journal generation, avoiding overwrite or
caller-invented sequences.

## Review Workers

Create workers with `fork_turns: "none"`. Send only their exact dispatch, skill,
references, repository instructions, and owned paths. Never send prior
conclusions, unrelated routing, the journal, or proof-format instructions.
Review nodes may use shared trusted read-only inspection observations, but each
still returns an independent semantic payload. Planned validators own their
commands; reviews attest to commands executed and normally return validation
requirements without rerunning validator recipes. An exact duplicate-command
authorization keeps the execution visible as reusable evidence.

Return only this `ReviewPayload` object:

```json
{
  "status": "completed | no-findings | blocked",
  "commands_executed": [],
  "command_policy_attested": true,
  "files_inspected": ["path"],
  "nearby_contract_owners": ["path"],
  "findings": [{
    "severity": "P0 | P1 | P2 | P3",
    "location": "path:line",
    "summary": "actionable defect",
    "evidence": "violated behavior or contract",
    "remediation": "smallest safe correction"
  }],
  "validation_requirements": [{
    "requirement_id": "stable-id",
    "owner": "skill-id",
    "reason": "risk requiring evidence",
    "commands": ["exact command"],
    "working_directory": "/absolute/path",
    "environment": "relevant identity",
    "expected_evidence": "observable success",
    "dependency_policy": "stop-on-failure | continue-independent"
  }],
  "handoffs": [{
    "catalog_id": "catalog.entry",
    "observed_trigger": "new applicability evidence",
    "reason": "why another owner is required",
    "scope": ["path"]
  }],
  "changes": [],
  "limitations": []
}
```

Use empty arrays for absent fields. `blocked` requires a limitation;
`no-findings` requires no findings. The compiler rejects validator-owned
commands and non-catalog handoffs. One schema mismatch permits one retry using
field diagnostics; a second mismatch blocks the node. For authorized fixes,
each change names finding IDs, files, what changed, why, and the preserved
contract; the trusted dispatch records mutation facts.

Persist the payload exactly as returned. Run `compile-node` with the node ID,
signed dispatch set, before/after captures, payload, and journal. It selects the
dispatch without coordinator-side JSON extraction, preserves the original
payload bytes, assigns identities, renders the native artifact and envelope,
runs both evidence gates, and journals verified evidence. The lower-level
`compile-review` command remains available for compiler diagnosis.

## Independent Review And Validation

The conclusion-blind independent worker returns the six sections defined by
`repository-independent-review`. Pass the native result to `compile-node`; its
compiler verifies target/path
provenance, line bounds, before/after fingerprints, dispatched adversarial
checks, findings, and catalog handoffs; it assigns identities, appends the
envelope and Machine Evidence, and emits journal-compatible metadata.

Coalesced validators read only `review-validator/references/graph-dispatch.md`
and return its `ValidationPayload`. Run `snapshot-workspace` immediately before
and after the exact command sequence, then pass both snapshots to
`compile-node`. The worker omits artifact records and digests; the runtime
derives them from the post-execution snapshot. `compile-validation` derives
command/environment digests, mappings, ledger export, and canonical evidence.
Declared artifacts include independently verified status provenance. `ignored` requires a tracked repository
`.gitignore`; repository-local and global excludes are rejected. Declared
workspace effects require trusted before/after filesystem and Git snapshots;
unexpected tracked, untracked, or ignored outputs fail acceptance. Validators
that can create source-adjacent intermediates run under the exact dispatched
isolation root; outside-repository artifacts must resolve beneath that root.

Use `synthesis-bundle` to verify accepted artifacts and derive the compact,
hashed findings, mappings, validation, handoff, limitation, and artifact view.
Synthesis receives that bundle, never full predecessor reports.

## Mutation, Handoffs, And Proof

Run `reconcile-handoffs` before expansion. Selected, exactly reused, or
user-excluded catalog entries resolve existing handoffs; only
`new_routing_triggers` expand routing. Final proof classification is derived
from the typed catalog mappings reparsed from accepted evidence, not from
caller-provided resolved IDs.

After an authorized repair batch, run `advance-after-mutation`. It records an
authorization upgrade when applicable, one serialized repair epoch and
recapture, terminally invalidates stale nodes as `awaiting-replan`, includes
newly touched paths, and emits replacement identities, lineage, and dispatches
bound to the final source triple. Never redispatch an old immutable dispatch.

Persist all capture, plan, payload, compiled evidence, journal, synthesis,
invalidation, manifest, and proof artifacts outside the reviewed repository.
Run `finalize-proof` with the lifecycle bundle, signed dispatch set, journal,
and `--current-capture`; it discovers accepted evidence paths without a
caller-authored sources document. It rejects stale source state, unresolved handoffs, missing
evidence, or verifier failures. Report `repository_validation_status`
separately from `graph_proof_status`; structural independent-evidence
acceptance does not imply semantic agreement or adjudicated recall.
