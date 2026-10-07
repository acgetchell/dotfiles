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

Preserve the ordinary aggregate gate's complete coverage. Do not add a cheap
recipe here if a later aggregate reruns it on the same source. If the repository
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

Successful early evidence stays in the same plan and final proof. Later audits
reference its planned requirement IDs/digests; no second validator is created
for those requirements. The scheduler verifies the source, command/environment
identities, and persisted evidence before releasing work. A content mutation
invalidates early results with other validators; the new epoch runs them against
its new captured state. Keep old failures and captures. The barrier is a
scheduling constraint, so it does not make unchanged source audits semantically
dependent on validation or prevent their verified reuse across repairs.

External staging preserves the historical barrier that admitted retained audits
and invalidates its validation results for the new repository state. Preserved
audits may finish; new launches wait for current validation. Repeated metadata
resumes retain that history without treating the old success as current evidence.

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
