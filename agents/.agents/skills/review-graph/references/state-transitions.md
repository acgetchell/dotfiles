# Review State Transitions

Load for content repairs, external staging, or late validation/routing changes.

For completed software DOI checks needing canonical metadata, use
[software DOI reconciliation](software-doi-reconciliation.md). It adds a focused
validator while retaining the original failed execution; it is not launch recovery.

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

For infrastructure failures before checks start, run `recover-validation-launch`
with the same four path flags as reconciliation. Supply `plan`, `source_state`,
`artifact_store`, validator `node_id`, `failure_kind` (`cache-access`,
`command-launch`, or `executor-permission`), `checks_started: false`, concrete
`reason` and `remedy`, replacement `environment`, and `permission_change` (`none`
when unchanged). Use observed launch diagnostics to justify the classification;
short elapsed time alone is insufficient. At least the environment or permission
must change. Environment text records the binding; the executor must actually
apply the stated remedy before running commands.

Recovery requires compiled blocked evidence, unchanged source/workspace, and
quiescent execution without active or source-mutated nodes. Unrelated blocked
nodes retain their dispatches, reasons, and available evidence; each eligible
validator can recover separately. Recovery rejects executed passed/failed checks,
planning blockers, and a second recovery of the same node/source. The revised
plan preserves accepted audits and successful validators, snapshots the prior
journal and dispatches, and binds the original failure, metadata, and sealed payload by
digest. Synthesis exposes this history through `validation_recoveries`.
Late validation expansion works after the replacement validator finishes.
Follow `continuation_path`: it names the lifecycle, journal, dispatches, current
capture, and next-ready output directory together. Never mix old and new paths.
Keep historical artifacts available; altered or missing evidence blocks reuse.
History and continuation files publish atomically, with the continuation
manifest last. An interrupted publication can retry the identical request
without leaving partial final files or overwriting existing evidence.

Run `reconcile-handoffs` before expansion. Selected, exactly reused, or user-excluded
catalog entries resolve handoffs; only `new_routing_triggers` expand routing.
Final proof classification uses typed catalog mappings reparsed from accepted
evidence, never caller-provided resolved IDs.

After authorized repairs, apply the repository formatter where it is part of
the fix before final capture. Plan [early checks](repair-validation.md) in the
replacement template, then run `advance-after-mutation` with the immediately
preceding `previous_capture`, `new_capture`, and their exact `changed_paths`
content delta. Invalidation follows owners and downstream dependencies. Supply
accepted `sources` for verified unchanged-input audit reuse; validators,
independent reviews, syntheses, and unproven audits rerun. Follow returned
`lifecycle_input_path`, `dispatches_path`, `journal_path`, and `capture_path`;
old artifacts remain unchanged. `preserved_evidence` contains only proven reuse.
For a verified reused audit, its original planned validation digest can bind to
the replacement validator when the complete execution identity is unchanged
except for the captured source state. Reconciliation reports this runtime-derived
`reuse_binding` without rewriting the audit or reusing old validation success.
Reuse also checks semantic Git dependencies across intervening staging. A later
content repair cannot revive an audit invalidated by that staging, even when its
owned files stayed unchanged. This check applies to whole audits, coverage units,
and replay of their immutable evidence. A fresh audit on the latest metadata
state can be reused when its complete input proof still holds.
Changed commands, directories, environment, toolchain, features, platform,
artifacts, or mutation contracts still require explicit reconciliation.
Per-node `reuse_decisions` explain disposition and reason code, distinguishing
`coverage-limitations`, `unclassified-limitations`, `unresolved-uncertainty`,
and `validation-evidence-limits`. Typed execution facts and delegated validation
context remain visible without blocking otherwise proven reuse. Untyped caveats
prevent reuse, never inferred informational exemptions. See the
[audit context fields](audit-context.md).

For broad audits, optionally partition `owned_paths` into `coverage_units`.
Each unit declares a local `unit_id`, `owned_paths`, concrete `dependency_paths`,
`dependency_uncertainty` (empty only when dependencies are understood), and
one-based `finding_indices`. Partition every owned path and finding exactly
once; account for every nearby dependency. Shared manifests belong in each
unit's dependencies when their contract affects its judgments. Do not infer
independence just because implementation bytes are unchanged.

`advance-after-mutation` reports `coverage_reuse_decisions` with reason codes for
each unit, including uncertain dependencies and failed input proofs. Ineligible
audits also report the applicable category; an audit without a partition reports
`no-coverage-partition` with an empty unit list.
Its plan-bound `coverage_reuse` dispatch is a verified execution view: unit paths,
dependencies, reused/recheck dispositions, original findings attributed to
`evidence_id`, typed audit/Git context, and validation/handoff obligations.
`proof_reference` names a read-only full proof artifact by absolute path and
SHA-256 digest. It retains both complete captures, original artifact references,
instruction identities, and metadata transitions outside ordinary worker context.
Read that artifact only when the full proof is needed. Inspect only units marked `recheck`;
`files_inspected` records those actual reads. The compiler combines this with
proved reused coverage, carries original finding provenance forward, and keeps
historical rechecked findings visible. Reconcile original validation needs and
handoffs in the new payload. Validators still run for the new source. Omitted
partitions, uncertain dependencies, changed instructions, or changed routing
require fresh inspection. Legacy audits without partitions retain whole-audit
reuse behavior; a delta audit is not itself a fresh partition origin.

Metadata at `expectation.coverage_reuse` and the normalized record retain the same
execution view and proof reference. Native Markdown binds that view by canonical
digest and reused/rechecked unit counts. Publication preflight, compilation, and
evidence verification reload the full proof without following file symlinks,
check its digest and exact execution projection, and replay source, dependency,
instruction, and finding provenance checks. Missing or altered proofs block
acceptance even after a report has been compiled. The full proof also remains
plan-bound; keep it with the other immutable artifacts. Original typed context
remains attributed to its evidence ID
in `inherited_audit_context`; it is not a fresh worker assertion. Older inline
coverage proofs and saved dispatches remain readable under the existing native
size limits. New external-proof publication contracts require compiler preflight.
The coverage proof also retains `original_git_context`, verified against the
original immutable artifact. Git dependencies and unclassified commands apply
to every reused unit because the payload has no unit-specific Git attribution.
Metadata decisions check reused reads and dependencies separately and attribute
their reasons to the original evidence ID. Fresh reads of a rechecked unit
cannot refresh a Git-sensitive judgment in a reused unit.
When staging invalidates inherited coverage, the continuation drops that reuse
context and dispatches the node's full owned surface for a fresh review. This
also applies to in-flight partial audits before their payload is available.
For invalidated whole-audit reuse, the continuation restores the original routed
requirements as executable audit work and reconnects synthesis dependencies.
Its decision records the replaced evidence IDs; the new audit receives a fresh
identity, and original artifacts remain available as history.

If an older runtime published a worker payload but failed compilation because
the generated coverage proof exceeded a native section limit, retry
`compile-node` using the updated runtime and the same saved lifecycle,
dispatches, journal, before/after captures, and payload bytes. Saved publication
contracts remain compatible. Do not edit the dispatch, republish the payload,
or advance the repair epoch for this retry. Accepted original evidence stays
unchanged; an interrupted compilation can retry the same operation paths.

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
retained in `external_metadata_transitions`. Declare semantic `git_dependencies`
in audit payloads with `kind`, `reason`, and the exact `commands_executed` string
in `command` when applicable:

- `source-discovery`: a plain local `git diff` used to locate source reads.
  Judgments must come from `files_inspected` and `nearby_contract_owners`,
  independent of what was staged. This requires a matching command; supported
  forms include `git --no-pager diff`, display flags, `--cached`/`--staged`,
  optional `HEAD`, and repository-relative paths after `--`. Shell compounds,
  other revisions/repositories, external diff tools, and unknown options cannot
  claim this exemption.
- `index`, `head`, `history`: judgments about staged content, commit metadata,
  or release history. These conservatively require current-state review.
  A dependency without a command still records a semantic judgment.

For example, a worker that uses a diff for orientation and then reads the source
can include:

```json
{
  "commands_executed": ["git --no-pager diff -- src/lib.rs", "cat src/lib.rs"],
  "git_dependencies": [{
    "kind": "source-discovery",
    "command": "git --no-pager diff -- src/lib.rs",
    "reason": "Located changes; judgments use the inspected worktree file."
  }]
}
```

The compiler binds these declarations to the immutable payload and rejects
missing ledger commands or unsupported discovery forms. Undeclared commands
retain conservative classification; `git_sensitive: true` remains a legacy
override even when discovery is declared. Do not reclassify a staging judgment
as discovery to gain preservation.

Accepted source-only audits survive when all recorded reads have unchanged
captured identities. Reads outside the captured repository require rechecking.
Captures bind `repository_symlink_paths`, including paths with symlinked parent
directories. A link identity proves its target text, not the bytes read through
it, so symlinked reads conservatively require rechecking. The v3 capture format
requires this traversal information; older captures require recapture.
The same restriction applies when reusing audit coverage across content repairs.
The runtime reconciles discovery against the combined HEAD-to-worktree content
identity, which is independent of the staged/unstaged split, retaining the
original commands and both captures. It neither reruns the old diff nor claims
its output is unchanged. In-flight audit dispatches survive provisionally; the
compiler checks their actual payload dependencies and reads before accepting
historical or transition-spanning captures. Unproven reads or semantic Git
dependencies require review entirely on the latest state.

`node_decisions` explains every preservation/recheck with exact dependency,
command, or path reasons and discovery reconciliation. The compact receipt
reports `node_counts` and `recheck_reason_counts`; its output artifact contains
the full decisions. Independent fresh reviews, validators, and synthesis have
separate explicit restart policies. Restarting these nodes does not invalidate
unrelated source audit leaves. Scheduling, workspace snapshots, and final proof
accept only the latest verified capture. Never rewrite fingerprints or undo staging.
