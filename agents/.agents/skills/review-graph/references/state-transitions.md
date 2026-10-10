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
When permissions change, also supply `executor_permissions` (`use_default` or
`require_escalated`) so the replacement dispatch binds the required tool mode.

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

For an executor permission denial **after checks start**, use the separate
`recover-validation-execution` operation with the same CLI file arguments.
Its [input example](runtime-operation-examples-v1.json#/recover-validation-execution)
requires `checks_started: true`, `failure_kind: executor-permission`, a concrete
causal `reason`, `remedy`, replacement `environment`, non-`none` `permission_change`,
and `executor_permissions` (`use_default` or `require_escalated`). Explain why
the failure comes from the execution environment; an ordinary assertion failure,
short run, or desire to rerun is insufficient. Permission text never grants
approval; use the actual execution tool's permission mechanism.

This bounded path accepts a **single failed command**, including an aggregate
such as `just ci` whose internal tests passed before socket binding failed.
It requires accepted failed owner evidence, unchanged source captures, and
quiescent execution. Multi-command units are ineligible: the runtime does not
splice ledgers or replay separately passed commands. Other successful units
remain accepted and retain their dispatches. The pre-launch and execution
paths share one recovery allowance per node/source; another failed attempt
remains failed evidence and cannot trigger an automatic retry loop.

`failure_evidence` supplies the original `before_capture`, `after_capture`,
`workspace_before`, and `workspace_after` file paths, the exact declared
`log_path`, and a permission-denial `diagnostic` present in both the immutable
execution evidence and log. The log must be a recorded `kind: log` file artifact
with a content digest; directory-only or missing logs cannot prove this recovery.
The runtime verifies log bytes, snapshot node/source bindings, artifact identities,
and the compiled workspace audit. Approved cache/output changes are permitted;
unexpected source changes are not. Existing compiled artifacts can use their
original snapshots without republishing a payload.

Recovery archives the log bytes, both captures, both workspace snapshots,
original plan, journal, and dispatches, and binds the failed report, metadata,
and sealed payload by digest. Reusable output paths may subsequently change;
the archived failure log remains immutable. The new attempt has distinct
runtime-owned evidence and artifact IDs and a changed executor identity. It
retains the logical validation node and requirements, so the early gate remains
pending until the replacement passes. Final partial proofs and synthesis retain
the original failure under `validation_recoveries`; a successful replacement
satisfies the active requirement without erasing that history. Follow the
returned continuation paths together. Never alter source or Git metadata to
unlock a retry, and never delete failure evidence to manufacture a clean result.

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
artifacts, or mutation contracts prevent whole-audit and coverage-partition reuse. The
transition schedules the affected audit with `validation-requirements-changed`
and names the conflicting or missing requirement before fanout. The worker
reassesses the current validation requirement; original evidence and execution
digests remain immutable. Eligible coverage-partition reuse still requires
the worker to reconcile every original validation need in its new payload.
Metadata reconciliation itself does not run validation; the replacement graph
retains its required gates.
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

## External Staging During Repair Publication

When a real saved repair capture S2 is followed by external staging S3 before
`advance-after-mutation`, pass all three captures in that operation:

- `previous_capture`: accepted S1, with any existing metadata continuation.
- `new_capture`: saved S2 immediately after the content repair, before staging.
- `post_repair_capture`: fresh S3 after external staging.

Keep `changed_paths` equal to the S1→S2 content delta. The runtime verifies
S1→S2 without index/HEAD/boundary changes, verifies S2→S3 as index-only, and
independently recaptures S3 before publishing. It retains S2 as the repair plan's
source identity, then composes the normal metadata continuation to S3. No capture
is synthesized and no Git state is changed. Without the real saved S2, replan
from S3; do not manufacture a bridge or alter the index.

Follow the returned top-level continuation paths together. `capture` and
`capture_path` identify S3; `new_source_state` remains the S2 plan identity and
`current_source_state` identifies S3. The lifecycle retains the verified S2→S3
metadata transition. `repair_transition_path` retains the intermediate repair,
both S1/S2 captures, and supplied historical evidence references, including
failures. Original logs, journals, and sealed evidence remain unchanged.
Final `reuse_decisions`, `reused_evidence_ids`, and `node_decisions` account for
staging: source-only judgments can survive, while Git-sensitive judgments and
required validation are scheduled against S3. A content, mode, instruction,
HEAD, branch, boundary, or live-state mismatch rejects the composition.

## External Staging Without A Content Repair

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

Use the full returned lifecycle input, including `external_metadata_transitions`,
for `reconcile-validation-requirements`, `fallback-to-coordinator`,
`recover-validation-launch`, and `recover-validation-execution`. Supply the latest
observed capture through `--current-capture`; keep `source_state` at its original
logical identity. These operations verify and preserve the chain in their
continuations and recovery history. Validation and failure evidence must bind to
the latest observed state; execution recovery also requires before/after capture
and workspace snapshots from that state. This applies equally after an ordinary
metadata resume and a composed repair followed by staging.

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

## Authorized Commit And Native CI Handoff

When the user explicitly authorizes committing the reviewed source, retain a
capture immediately before the operation and capture again afterward. Use
`resume-after-authorized-commit --input <request.json> --output <result.json>`
to continue the review. This is optional; ordinary reviews need no commit step.
A review/fix request does not authorize branch creation, commits, push, or PR
publication. Existing explicit authorization for the same operation and scope
remains valid across turns; record it without asking again. The runtime observes
Git and never changes it or publishes anything.

Supply the existing lifecycle `plan`, logical `source_state`, any
`external_metadata_transitions`, `dispatches_path`, `journal_path`, both real
captures (`previous_capture`, `new_capture`), and a new external `artifact_store`.
Execution must be quiescent. The post-commit repository must be clean, on a named
branch, and exactly one commit beyond the captured HEAD. Baseline and worktree
captures are supported; other comparison modes, merges, and rebases require
replanning. The complete path map, file modes, repository boundary, instructions,
skills, and references must remain proved. The runtime independently recaptures
the repository and compares the committed tree against the captured bytes, so
clean status alone cannot hide an index flag or content-filter mismatch.
Submodule trees and changed path inventories require replanning. Symlink text
is bound, but reads through symlinks still require fresh inspection.

The request's `authorization` records `operation: branch-commit`,
`repository_root`, destination `branch`, the immediately preceding capture's
`source_state`, and the actual user's `user_authorization` text. This records
authorization; it does not create permission to execute Git mutations.

Reconciliation is explicit and defaults to rechecking uncertain evidence:

- Source-only audits retain their immutable evidence when their recorded reads
  and dependencies remain proved. Semantic `head`, `history`, or `index`
  dependencies and unclassified commands require current-state review.
- To retain an independent review, provide an `independent_reviews` entry keyed
  by node ID with its original `change_target`, immutable `comparison_commit`
  (the captured pre-commit HEAD), and `reason`. Supported comparison targets are
  plain local worktree diffs naming `HEAD` or its explicit SHA.
  Staged comparisons and unresolved moving refs require a fresh review. The
  original target remains attributed to its original evidence.
  Fresh independent reviews pin that same comparison to the pre-commit SHA;
  they must not compare against the new `HEAD` and silently inspect an empty
  diff. An unprovable comparison target requires replanning.
- To retain passed local validation, provide a `local_validation` entry keyed
  by node ID: copy its entire unchanged `validation_unit` as `execution_identity`,
  declare `git_dependencies: []` and `environment_unchanged: true`, and explain
  the inspected recipe's source-only inputs in `reason`. Check aggregate recipes
  and their tools, including version derivation, file discovery, and history
  assertions. Matching source bytes alone never establishes Git independence or
  unchanged external inputs. Git-sensitive, mixed, uncertain, failed, and omitted
  units run again in full. No successful old execution is rewritten or called
  a new run. Required final gates may run with disclosed overlap.

`native_ci` must map pending/blocked native validator node IDs to replacement
`commands` and required `checks` (`name`, `target`). Every replacement command
must name the new exact commit SHA. Keep the same platform, environment,
toolchain, workspace contract, and requirement ownership; a changed execution
environment needs its supported reconciliation or a fresh plan. The handoff
reconciles retained audits' original planned native-validation digest with this
specific replacement and explains the supersession. Old blocked evidence and
its journal remain available as history.

The native validator runs/queries the declared checks and records a `native_ci`
array in its payload. Each result supplies `name`, `target`, `head_sha`,
`conclusion`, and its HTTPS run `url`, alongside the normal command ledger.
Passing requires exactly the named targets, each with the new SHA and
`conclusion: success`; skipped, missing, duplicate, differently named targets
and old-commit results cannot satisfy it. Inspect the actual native execution;
do not infer native results from local success or substitute emulation.

Follow the returned lifecycle, dispatches, capture, and journal paths together.
The logical reviewed source identity remains unchanged; the full metadata chain
records both actual identities. Immutable history retains both raw captures,
the original plan, journal, dispatches, evidence, sealed payloads, and declarations.
Node decisions explain preservation/rechecking. Synthesis and final proof replay
the transition and exact-commit native evidence and reject changed history.
The index-only staging operation keeps its existing contract; use the immediately
preceding real capture and retain its chain when composing the two operations.
Never synthesize a bridging capture, edit sealed artifacts, or undo a commit to
make historical fingerprints appear current.
