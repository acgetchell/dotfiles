# Review State Transitions

Load for content repairs, external staging, or late validation/routing changes.
Apply the [bounded lifecycle](bounded-lifecycle.md) before another source-editing
batch or comprehensive restart; transitions retain the run-wide repair count.

## Replace An Invalidated Audit

If an accepted audit applied the wrong checklist, first finish compiling other
in-flight work, then explicitly invalidate the mistaken node. Set `REVIEW_PYTHON`
and `REVIEW_RUNTIME` to the interpreter and frozen runtime paths from this run's
generated commands. Run both commands from the reviewed repository:

```sh
"$REVIEW_PYTHON" "$REVIEW_RUNTIME" journal-append \
  --input <lifecycle.json> --journal <execution.jsonl> \
  --node-id <audit-node> --status invalidated \
  --reason 'Applied the wrong specialist checklist'
```

Create a request from the current lifecycle's `plan`, `source_state`, and any
`external_metadata_transitions`; add an external `artifact_store`, the invalidated
`node_id`, and a concrete `reason`. Then run:

```sh
"$REVIEW_PYTHON" "$REVIEW_RUNTIME" replace-invalidated-audit \
  --input <replacement-request.json> --journal <execution.jsonl> \
  --dispatches <dispatches.json> --current-capture <capture.json> \
  --output <replacement-result.json>
```

Follow the returned lifecycle, dispatch, journal, and capture paths. The runtime
requires unchanged source, quiescent execution, and one invalidated dependency
closure; unrelated invalidations must be reconciled separately. It preserves the invalidated
journal, payload, and compiled evidence by digest; the original plan cannot admit
more work. The affected dependency closure gets fresh node/evidence identities,
and the audit starts with full owned scope and no inherited judgment. Give the
replacement worker only its execution view and raw inputs, never the invalidated
conclusions. Unaffected accepted audits and validators remain bound to their
original evidence.

One replacement is permitted per specialist requirement set and source state;
another semantic mistake remains blocked. An identical request can recover its
saved result. Replacement leaves content-repair counters, the configured worker
budget, and reserve unchanged. It does not authorize content changes or a comprehensive
restart, and cannot revive a stopped run.

## Validation Expansion And Recovery

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

A compiled blocked source audit may remain while independent late validators are
added on unchanged source. Its dispatch, blocked status, reason, and sealed
evidence remain intact; `retained_blocked_node_ids` makes that explicit. The
runtime verifies blocked evidence as well as accepted evidence and carries its
discovered obligations. New validators follow their own dependencies; dependent
synthesis and final readiness still wait for the blocked audit. Active work,
source mutation, uncompiled blocks, and other blocked node modes require their
existing continuation/recovery paths. Expansion never promotes a blocker to
success or authorizes source edits. After `begin-repair`, reconcile late
requirements on the unchanged source before repair replanning; keep the returned
lifecycle, journal, and dispatch set together.

For uncertainty about an exact dependency version, reuse the managed toolchain
environment resolved during preflight, including its `CARGO_HOME` and registry
or vendor/source-replacement configuration. Searching only the ambient Cargo
registry establishes a discovery limitation, not absence. Inspect the locked
version there; if fetching or compilation is needed, plan that exact validation
obligation within existing permissions. Retain the original blocked evidence
until affected verification resolves the uncertainty.

When accepted reviewers use the same requirement ID for distinct execution
contracts, give the full additions unique planned IDs, such as
`ubuntu-ci.audit-001` and `ubuntu-ci.audit-002`. Supply
`validation_requirement_bindings`, each with the returned
`originating_evidence_id`, original `requirement_id`, `requirement_digest`, and
its `planned_requirement_id`. Bindings retain the original immutable obligations;
commands, working directories, environment, and dependency policy must still
match exactly. Multiple origins may bind one planned requirement only when its
execution contract satisfies every origin. An ambiguous origin binding is
rejected. Use the returned digests rather than reconstructing or editing evidence.

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
the replacement validator when its obligation is unchanged apart from source
state, scheduling policy, or a proved relocation of external stdout logs.
Reconciliation reports this runtime-derived
`reuse_binding` without rewriting the audit or reusing old validation success.
Reuse also checks semantic Git dependencies across intervening staging. A later
content repair cannot revive an audit invalidated by that staging, even when its
owned files stayed unchanged. This check applies to whole audits, coverage units,
and replay of their immutable evidence. A fresh audit on the latest metadata
state can be reused when its complete input proof still holds.
Changed commands, directories, environment, toolchain, features, platform,
artifacts, or mutation contracts prevent whole-audit reuse. The narrow log
exception requires the original digest-bound execution sidecar, declared
`kind: log` artifacts outside the repository, and terminal stdout redirection
with optional `2>&1`. Paths used as command inputs, report artifacts, workspace
effects, undeclared outputs, and other shell changes retain exact identity.
The replacement validator always executes against the new source and its exact
command/output contract; original logs and failed executions remain immutable.
Compact reconciliation receipts expose the changed identity fields. Normally
semantic contract changes also
prevent coverage-partition reuse. The
transition schedules the affected audit with `validation-requirements-changed`
and names the conflicting or missing requirement before fanout. The worker
reassesses the current validation requirement; original evidence and execution
digests remain immutable. Eligible coverage-partition reuse still requires
the worker to reconcile every original validation need in its new payload.
Metadata reconciliation itself does not run validation; the replacement graph
retains its required gates.

A commandless requirement with a planning blocker may instead enter
`validation_reassessment` when its exact `canonical_recipe` becomes the sole
command in the explicit repository directory. Environment, platform, toolchain,
features, isolation and mutation contracts must remain identical; other changes
still require full source review. This is a new review obligation, not an
execution-equivalence claim. Only independently proved unchanged source units
are candidates for reuse; changed files and affected dependencies require fresh
inspection. The dispatch preserves both execution identities and their digests,
old blockers, findings, and routing handoffs.

The fresh specialist must submit `validation_reassessments` with both supplied
digests, a contract assessment, native limitations, and a handoff assessment.
`source-independent` retains the proved source judgments; `reinspect` requires
all owned paths to be inspected again; `uncertain` blocks acceptance. Missing or
stale reassessment is rejected at publication, compilation, and evidence replay.
The resulting sealed audit binds the new validation requirement without changing
old payloads. It does not reuse a validation pass or satisfy a native CI gate.

Repair comparisons retain their original immutable base. When enumerating the
captured paths would exceed the comparison identifier limit, the replacement
dispatch uses a bounded root diff (`git diff <immutable-base> -- .`). Its separately
bound `owned_paths` still contain the complete scope: inspect untracked paths
directly, since Git diff omits them.

For a baseline repair whose full comparison is against the captured HEAD, the
planner derives independent-review ownership from captured raw file identities
against that immutable commit. Changed files, untracked files, and deletions
remain mandatory; unchanged context belongs in `nearby_contract_owners`.
Baseline specialist audits keep their full scope. Other comparison forms retain
their declared boundary rather than guessing a smaller change set. Explicit
routing cannot omit any derived changed path, and stale captures still reject.

For an existing frozen run whose advance failed on this representation limit,
keep its frozen resources, accepted evidence, captures, and open repair request.
Run the updated `review_graph_runtime.py advance-after-mutation` with the retained
Python runner and that request, supplying `routing_catalog_path` from the original
frozen runtime. Use a new output artifact directory if the failed attempt left
partial files. The updated runtime retains the original plan's skill locations
and verifies its run control and evidence; it consumes the already requested repair
epoch once and does not restart the comprehensive review. Follow only the returned
continuation paths. Never patch the old frozen resources or signed plan.
Per-node `reuse_decisions` explain disposition and reason code, distinguishing
`coverage-limitations`, `unclassified-limitations`, `unresolved-uncertainty`,
and `validation-evidence-limits`. Typed execution facts and delegated validation
context remain visible without blocking otherwise proven reuse. Untyped caveats
prevent reuse, never inferred informational exemptions. See the
[audit context fields](audit-context.md).

For broad audits, optionally partition `owned_paths` into `coverage_units`.
Choose language/activity and affected-contract boundaries using the conditional
[partitioning guidance](coverage-partitioning.md), including its evaluation of
broad documentation dependencies and section-level proofs.
Each unit declares a local `unit_id`, `owned_paths`, concrete `dependency_paths`,
`dependency_uncertainty` (empty only when dependencies are understood), and
one-based `finding_indices`. Partition every owned path and finding exactly
once; account for every nearby dependency. Shared manifests belong in each
unit's dependencies when their contract affects its judgments. Do not infer
independence just because implementation bytes are unchanged.

`advance-after-mutation` reports `coverage_reuse_decisions` with reason codes for
each unit, including uncertain dependencies and failed input proofs. Proven
partition decisions also report `input_changes` for changed owned and dependency
paths, including type/mode changes and missing files. These explanations do not
change the compiler-bound proof or make empty change lists a reuse exemption. Ineligible
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
reuse behavior. A completed delta audit may become a later origin only through
replay of its full compiler-bound inheritance chain. Its fresh reads stay distinct
from inherited paths; the runtime preserves proved units and conservatively groups
the rechecked surface, retaining findings and validation/handoff obligations.

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
is synthesized and no Git state is changed. Without a saved S2, use the
[interleaved continuation](#interleaved-repairs-and-staging) below.

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

## Interleaved Repairs And Staging

When the maintainer stages files throughout an authorized repair batch and no
final post-repair/pre-staging capture exists, use `advance-after-mutation` with
the actual `previous_capture` and current `new_capture`. Keep the original plan,
run control, repair epoch, authorization, journal, dispatches, and accepted
sources, including failed checks. Supply the exact content delta in
`changed_paths` and add:

```json
{
  "interleaved_staging": {
    "repair_attribution": "All changed_paths are agent edits within the already authorized repair batch.",
    "staging_attribution": "The maintainer confirmed staging files while reviewing these repairs."
  }
}
```

Use actual session evidence for those attributions. Unknown or unrelated source
edits cannot be labeled agent repairs. Omit `post_repair_capture`; never create
an intermediate capture by substituting index fields. This bounded adapter
requires unchanged HEAD, branch, base, capture mode, selected paths, file types,
modes, and instructions. Staged scopes and scope expansion require separate
reconciliation. On rejection, retain the evidence and report partial delivery
with the unsupported delta; do not restart comprehensive review for bookkeeping.

The runtime verifies the real content and index deltas separately, closes the
existing repair epoch once, and plans directly against the current capture.
Complete unchanged audit inputs may be reused; changed contracts, semantic Git
dependencies, uncertain inputs, independent review, and validation require
current evidence. It verifies live source before publication and preserves the
actual index. `repair_transition_path` retains both actual captures, the old
plan, execution history and original evidence references, including failures.
Earlier ordinary repairs compose through their saved endpoint proof; unchanged
audits do not restart solely because staging happened in a later repair epoch.

Follow the compact receipt's typed `next_action` (`continue-review`, operation
`next-ready`) with its argument-vector `command`; `next_command` remains the
compatible direct form. `proof_limitations` explicitly records
`missing-intermediate-capture`: endpoint proof cannot establish intermediate
source/index contents or the order of edits and staging. Final verification is
still required. The lifecycle retains the affected repair epochs, and both
`report-delivery` and `finalize-proof` emit this limitation after later
continuations. Routine delivery remains uncertified; include the limitation
in its explanation even when final checks pass.

## External Staging Without A Content Repair

For external branch creation or staging with unchanged reviewed content, use
`resume-after-external-metadata --input <request.json> --output <result.json>`.
Supply the existing `plan`, `source_state`, `dispatches_path`, `journal_path`,
immediately preceding `previous_capture`, fresh `new_capture`, and a new
external `artifact_store`. Include existing `external_metadata_transitions`
from the lifecycle input when resuming again. The runtime proves captured scope,
complete path identities (including types/modes), applicable instructions, HEAD,
and comparison base unchanged. Only branch name and index metadata may differ;
changes to staged scope or source require replanning. No Git command changes the index and no repair epoch is
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
it, so symlinked reads conservatively require rechecking. The v4 capture format
uses native Git blob IDs with modes for regular files and symlink targets and
derives a Git tree ID for the current source. Dirty/unavailable submodules retain
their separate content identities. Capturing neither writes Git objects nor
changes the index. Metadata envelopes retain their own checksums. Older captures
require recapture with the new runtime; frozen runs retain their original format.
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
the full decisions. Completed independent reviews and passed source-only
validators can retain their original evidence. Validation uses the standard
compiler-bound `ValidationPayload`, native ledger export and metadata, parsed
into immutable typed records before publication or consumption. Explicit
`git_dependencies: []` covers the entire invoked command; missing declarations,
changed artifacts or input selection, symlink traversal and semantic Git
dependencies require rechecking. Syntheses refresh their consumed bundles.
Restarting affected nodes does not invalidate
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
branch, and exactly one commit beyond the captured HEAD. Baseline, worktree, and
branch/PR captures are supported; staged comparisons, merges, and rebases require
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
  In branch scope, a plain `git diff <captured-merge-base-SHA> -- <paths>`
  declared as `head` can retain evidence when that immutable base, scope, and
  complete path identities remain unchanged. Moving refs remain uncertain.
- To retain an independent review, provide an `independent_reviews` entry keyed
  by node ID with its original `change_target`, immutable `comparison_commit`
  (the captured pre-commit HEAD for baseline/worktree or the original merge base
  SHA for branch scope), and `reason`. Supported comparison targets are
  plain local worktree diffs naming `HEAD` or its explicit SHA; branch scope
  requires the fixed merge base SHA with an unchanged captured path scope.
  Staged comparisons and unresolved moving refs require a fresh review. The
  original target remains attributed to its original evidence.
  Fresh independent reviews use the captured pre-commit SHA for baseline/worktree
  scope and the original merge base SHA for branch scope. They must not compare
  against the new `HEAD` and silently inspect an empty diff. An unprovable
  comparison target requires replanning.
- Local validation reuse is derived from verified version 3 records and the
  captured repository-owned `review-validation-contracts.json`. Exact commands,
  directories, environment, selected input membership and output identities must
  match. Deterministic source failures remain failed; transient or incomplete
  outcomes follow bounded recovery. Workers may add dependencies but cannot
  weaken a contract. Unmatched commands remain conservative. The handwritten
  `local_validation` request declaration is retired.
- For an externally performed commit/rebase preserving the complete tree,
  scope and comparison boundary, `resume-after-external-metadata` accepts
  `git_context_authorization`. It records existing user authorization and never
  mutates Git. A changed review scope/base requires replanning; the validation
  applicability API can still assess original evidence separately.

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

## External source edits

For a maintainer edit inside the existing captured scope, use
`resume-after-external-source --input request.json --output result.json`.
Start with the operation's schema/example. Supply the current plan, journal,
dispatches, actual `previous_capture` and `new_capture`, a fresh external artifact
store, `external_source_actor`, and `external_source_attribution` quoting or
referencing the maintainer's confirmation. Do not infer authorship from Git or
classify an agent repair as external. Wait for workers to become quiescent.

The continuation preserves run control, repair count, repair budget and existing
authorization, including when all agent repair batches have been used. It binds
the actual changed path identities, checks the live source again before publication,
and preserves original evidence files. Follow its returned lifecycle, dispatches,
journal and capture. The existing serialized `external_metadata_transitions`
chain also carries this explicitly typed source transition; the name is retained
for saved-record compatibility.

Only unchanged audit reads/dependencies and contracted validation inputs can be
reused. README whitespace still invalidates its documentation owner and any
content-sensitive check; semantic code changes invalidate their owning contracts.
Unknown dependencies remain unproven. Independent review and synthesis recheck.
The operation grants no additional agent repairs. Changed Git state, selection,
new paths, or applicable instructions need separate reconciliation/replanning and
are rejected by this bounded continuation.

For routine delivery when reconciliation is unavailable, stop formal bookkeeping
and report the completed work, exact capture/commit of each accepted result,
external changes since that capture, and remaining affected or unverified checks.
Use `report-delivery` when its current-capture requirements hold; otherwise give
that partial report directly. Do not claim a complete final proof, manufacture
matching captures, restart comprehensive review, or request another repair batch
solely to describe work already done. A new agent repair still requires available
budget and the existing repair authorization procedure.
