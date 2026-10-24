# Validation Before Repair Reviews

Before the final repair capture, apply the repository formatter when formatting
is part of the authorized fix. Then select cheap deterministic checks from the
repository's canonical validation plan. The coordinator plans them; the single
`review-validator` owner executes each coalesced unit.

In the `advance-after-mutation` planning template, set
`pre_review_validation_requirement_ids` to the ordered requirement IDs to run
before affected audit and independent-review workers. For example, if the
existing plan already declares separate canonical `static-checks` and
`runtime-tests` requirements:

```json
{"pre_review_validation_requirement_ids": ["static-checks"]}
```

The selector promotes entire coalesced units. It never creates commands or
splits a command, recipe, or unit. Aliases for the same exact execution select
one owner. Units must be required, executable, sequential, and stop-on-failure.
An omitted or empty selector preserves ordinary scheduling; it does not claim
that an early check ran. The same selector can be used in an initial plan when
early validation is useful there too.

Preserve the ordinary aggregate gate's complete coverage. Avoid adding a cheap
recipe solely to repeat evidence. A focused diagnostic or red/green check may
precede a required final aggregate; record its purpose and overlapping coverage.
Each graph execution still needs its exact planned requirement and owner. If the repository
only exposes a combined command such as `just check ci`, move that whole unit
early or keep its ordinary placement; do not infer a split or substitute a
lint-only pass for the aggregate. Separately exposed, nonoverlapping canonical
units may be planned in phases when their complete coverage is established.

After materialization and availability preflight, use `schedule-ready` or
`next-ready` normally. The runtime releases one selected validator at a time.
Every selected unit must have verified `passed` or exact `reused` evidence before
any remaining node starts. This applies to grouped, mixed, and isolated profiles,
including direct journal and compile calls. A preflight hold cannot release
reviews through this barrier; availability is never executed validation.

Use the normal captures, workspace snapshots, payload publication, compilation,
and journal. A failed command remains accepted failure evidence, but it stops
later early checks and review fanout. Blocked execution and unexpected effects
also hold the barrier. Diagnose and repair through the coordinator's authorized
workflow, then capture and advance a new epoch. Launch recovery remains limited
to proven failures before checks started.

## Diagnostics Inside An Open Repair Batch

After `review-control begin-repair` authorizes a batch, the coordinator may run
focused canonical diagnostics outside the graph against evolving source. The
coordinator owns each execution; do not dispatch an additional graph validator
for the same attempt. Before each attempt, record the exact command, working
directory, environment/toolchain, purpose, overlap with the failed check and
final aggregate, and an intermediate source capture in a unique external
proof-store directory. Record actual executor, start/end timing, exit status,
raw output, and an after capture there. Preserve every attempt, including red
results, with write-once logs and identities; never overwrite a prior log or
edit sealed graph evidence. Unexpected command mutations require investigation.

These supplemental diagnostic records do not satisfy graph requirements or
release the failed early-validation barrier. Do not publish or retrofit them
as accepted graph validation. No reconciliation or `advance-after-mutation`
is needed between diagnostic-driven edits. Remain within the authorized scope
and repair budget; check review control before further edits and stop on user
stop. Close the batch with one final capture and `advance-after-mutation` when
the repair is ready. Only that closure counts the content-changing repair.
The final planned validators execute against the final capture, even if the
same command passed as a supplemental diagnostic. Their evidence retains native
platform and hosted-CI limitations normally.

## One Verification Follow-Up

A completed batch permits one final correction discovered by its affected review
in an already repaired file. Before editing, call `review-control begin-repair`
with `verification_followup` alongside the normal control input:

```json
{
  "previous_repair": {"path": "/tmp/review-proof/repair-result.json", "digest": "sha256:<exact saved result digest>"},
  "finding_evidence_id": "<accepted current review evidence ID>",
  "reason": "Correct the confirmed defect found while verifying the repaired helper."
}
```

The runtime binds the saved result to its immutable run-control repair origin,
current plan/capture, and a current completed audit or independent-review finding.
Inherited historical findings cannot authorize a follow-up. The control receipt
returns the same `repair_epoch` and permitted repaired paths. Keep execution
quiescent and honor any stop decision. After the correction, capture and use
`advance-after-mutation` with the same `verification_followup`, ordinal, current
lifecycle, evidence sources, and normal changed-path declaration. The runtime
rechecks the boundary, retains prior attempts, and emits a distinct immutable
verification continuation without incrementing `repairs_completed`.

This allowance also applies at the final budgeted batch, before a budget-exhaustion
stop has been recorded. It does not clear a stop, permit a second follow-up, expand
the original repaired paths, or waive validators and affected source reviews.
Expanded repairs use the next ordinary batch or an explicitly authorized budget
extension. Interleaved staging uses its existing separate continuation.

## Final Validation And Reuse

Successful early evidence stays in the same plan and final proof. Later audits
reference its planned requirement IDs/digests; no second validator is created
for those requirements. The scheduler verifies the source, command/environment
identities, and persisted evidence before releasing work. A content mutation
invalidates early results with other validators; the new epoch runs them against
its new captured state. Keep old failures and captures. The barrier is a
scheduling constraint, so it does not make unchanged source audits semantically
dependent on validation or prevent their verified reuse across repairs.

The repair receipt exposes `validation_reconciliation` with original and
replacement planned digests. When only `source_state` and capture-derived
`captured_paths` change, verified unchanged audits retain their sealed judgments
and pending validation obligations. Both path inventories are bound to retained
captures; command, environment, artifact and other execution-contract changes
still require rechecks. `audit_reuse_counts` reports retained evidence and newly
scheduled audits, not measured executions or provider-cost savings.

Audits without an explicit coverage partition use a conservative whole-audit
unit assembled from all owned paths, findings and recorded dependencies.
Publication reports `coverage_reuse_policy`. For instruction-only changes, a
fresh specialist still assesses rules, commands, applicability and obligations;
material or uncertain changes require source reinspection. Unbound external
reads remain blockers and receipts identify their exact paths and classification.

External staging preserves historical admission for retained audits. Validators
whose Git inputs changed require current validation before new launches.
Source-only or verified worktree-selection gates can retain historical admission
under the [metadata continuation policy](run-profiles.md), while formal reuse
remains unproven without a repository contract. Repeated resumes retain that
history without treating the old success as current evidence.

Record `in-flight` only after an actual worker launch or coordinator start.
Scheduling receipts expose `phase_accounting` for early validation, semantic
reviews, remaining validation, and synthesis. It separates planned nodes,
journal starts, worker launches, coordinator starts, result records, and journal
boundary timestamps (Unix nanoseconds). These timestamps measure lifecycle
recording, not command duration. Command elapsed time remains in validation
evidence. Missing start records or legacy timestamps produce unknown launch
counts or times, not inferred measurements. Launch totals also remain unknown
after a recorded start is invalidated: a continuation can replace its dispatch
lane, and the journal does not prove the historical executor. The raw
`journal_start_count` still reports every observed start. Continuations retain original
result timestamps and keep historical journals available. Reconcile their
lineage before combining counts across journals to avoid counting retained
events twice.

For measured stage duration and provider usage, use the existing
[usage ledger](routing-experiment.md#account-for-the-whole-graph) with separate
`pre-review-validation` and `semantic-review` stage names. Runtime operation time,
command time, worker launch counts, and provider costs are separate observations.
Keep unavailable provider costs unknown; do not claim savings from fewer launches.
