# Review State Transitions

Load for content repairs, external staging, or late validation/routing changes.

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

For broad audits, optionally partition `owned_paths` into `coverage_units`.
Each unit declares a local `unit_id`, `owned_paths`, concrete `dependency_paths`,
`dependency_uncertainty` (empty only when dependencies are understood), and
one-based `finding_indices`. Partition every owned path and finding exactly
once; account for every nearby dependency. Shared manifests belong in each
unit's dependencies when their contract affects its judgments. Do not infer
independence just because implementation bytes are unchanged.

`advance-after-mutation` reports `coverage_reuse_decisions` for each partition.
Its plan-bound `coverage_reuse` dispatch retains original artifacts, captures,
findings, and instruction identities. Inspect only units marked `recheck`;
`files_inspected` records those actual reads. The compiler combines this with
proved reused coverage, carries original finding provenance forward, and keeps
historical rechecked findings visible. Reconcile original validation needs and
handoffs in the new payload. Validators still run for the new source. Omitted
partitions, uncertain dependencies, changed instructions, or changed routing
require fresh inspection. Legacy audits without partitions retain whole-audit
reuse behavior; a delta audit is not itself a fresh partition origin.

Synthesis bundles expose `plan_context.validation_environments` by validator
node ID. Copy its executor `platform` into validation reconciliation; use its
digest-bound `environment` and `features`, together with execution evidence and
limitations, to distinguish native runs, emulation, and unexecuted target cells.

For external staging with unchanged reviewed content, use
`resume-after-external-metadata --input <request.json> --output <result.json>`.
Supply the existing `plan`, `source_state`, `dispatches_path`, `journal_path`,
immediately preceding `previous_capture`, fresh `new_capture`, and a new
external `artifact_store`. Include existing `external_metadata_transitions`
from the lifecycle input when resuming again. The runtime proves baseline or
worktree scope, complete path identities (including types/modes), applicable
instructions, HEAD, branch, and boundaries unchanged. Staged/branch targets
require replanning. No Git command changes the index and no repair epoch is
consumed.

Follow the returned continuation paths. The review's original `source_state`
remains its identity; actual before/after fingerprints and both snapshots are
retained in `external_metadata_transitions`. In-flight content audits can
compile across this verified transition. Mark `git_sensitive: true` when an
audit judgment depends on the index or other Git metadata; command-dependent
audits are also conservatively rechecked. Validators and synthesis restart on
the new metadata state. Scheduling, workspace snapshots, and final proof accept
only the latest verified capture. Never rewrite fingerprints or undo staging.
