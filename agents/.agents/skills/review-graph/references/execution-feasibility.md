# Review Graph Execution Feasibility

Use this contract before repository capture, after the exact bounded node plan
exists, and before every worker dispatch. Read `planning-contract.md` first and
use `scripts/review_graph_plan.py` as the deterministic decision model.

## Contents

- [Safe Runtime Evidence](#safe-runtime-evidence)
- [Early Capability Gate](#early-capability-gate)
- [Exact Schedule Assessment](#exact-schedule-assessment)
- [Hard Deadline Accounting](#hard-deadline-accounting)
- [Blocked Capability Report](#blocked-capability-report)

## Safe Runtime Evidence

Require an authoritative runtime surface for the aggregate values needed to
start one fresh worker:

```text
source
concurrent_worker_limit
active_workers
```

Accept these lifetime values when the runtime supplies both, but do not require
them:

```text
fresh_worker_creations_remaining
lifecycle_semantics
```

Treat an authoritative lifetime count as the current root's hard epoch ceiling.
A known zero blocks the first dispatch. Partition a larger complete plan into
fresh-root epochs; never reduce applicable coverage. When the count is absent,
use the configured per-root budget (default 24) and record `not exposed; bounded
by configured budget <N>`. Do not infer a limit or release policy from
concurrent capacity.

Do not call a status or listing surface for capacity diagnosis when its schema
or observed payload may include messages, reports, findings, results, outputs,
or other task content. Do not spawn a dummy worker. If a mechanism unexpectedly
returns task content, discard its values, retain only the sensitive field paths
needed to identify the isolation failure, persist that blocker, and stop.

## Early Capability Gate

Before capture, router loading, graph construction, or a pre-dispatch report:

1. Verify that fresh workers with no inherited turns are supported.
2. Obtain safe aggregate concurrent-capacity evidence without creating a worker.
3. Require at least one free concurrent slot and a positive configured total
   fresh-worker budget. If an authoritative lifetime count is present, require
   it to be greater than zero and use the smaller value as the effective budget.
   Require the effective budget to be strictly greater than the
   recovery/finalization reserve so at least one worker remains dispatchable.
4. Record the evidence source, aggregate values, configured and effective
   budgets, recovery/finalization reserve, isolation status, and gate result in
   the journal.
5. If a check fails, emit the blocked capability report below and stop. Do not
   describe routers as consulted, create selected leaf nodes, or claim that a
   focused skill or validator ran.

An unavailable lifetime count is not a failed check and is never unlimited. The
configured total budget remains binding.

## Exact Schedule Assessment

After exhaustive routing creates the complete node plan, coalesce compatible
requirements and partition the schedule under `planning-contract.md`. Count
fresh-worker commitments for:

- every audit, validation, independent-review, synthesis, fix, and revalidation
  node
- every explicitly planned fresh-worker retry or synthesis rerun
- every planned post-fix rerun
- an explicit review-and-fix iteration reserve, when fixes are authorized

Do not count router reads, coordinator reconciliation, or formatting-only
follow-ups to an already-created worker as fresh creations. Count the
recovery/finalization reserve separately. Dispatch nodes one at a time and never
assign a later node to a completed worker. Required peak worker concurrency is
therefore one.

Require `nodes in the current epoch + recovery/finalization reserve <= effective
root budget`. Record the complete graph count, every epoch, reserve, and
authoritative lifetime count. If the complete graph exceeds one root, retain all
nodes and mark later epochs as fresh-root continuations. Until they complete,
the graph is incomplete. If a real worker creation later fails, stop all
dispatch, record that node as `blocked-before-execution`, preserve completed
reports, and emit a resume manifest for every undispatched or unaccepted node.
Never replace them with coordinator review or reused-worker follow-ups.

## Hard Deadline Accounting

Treat an overall time budget supplied by the user or runtime as a hard global
deadline. When none exists, report `unbounded by request` and retain each node's
elapsed-time cap.

Before dispatch, calculate and report:

- the full-cap critical path for the sequential graph
- reserves for coordinator work, validation, fixes/revalidation, and final
  reconciliation that are not already represented by node caps
- the dispatch window remaining after reserves
- whether all nodes are guaranteed to fit if every cap is consumed
- the policy `run until deadline; account for every unrun node`

Node caps are safety limits, not reservations. A full-cap critical path longer
than the hard deadline is a completion risk, not an upfront blocker when a first
worker still has time to run.

Before each dispatch, use `bounded_node_dispatch_seconds` from
`scripts/review_graph_plan.py` or an equivalent monotonic calculation. Cap the
node timeout to the smaller of its own cap and the remaining dispatch window.
When the result is zero, mark that node and every undispatched node
`blocked-before-execution` with `global-deadline-exhausted`. Preserve selected
skills, reasons, dependencies, and planned validator commands. If the deadline
expires while a worker is active, request its prompt result, interrupt if it
cannot return within the remaining time, record the exact outcome, and then
reconcile the graph.

## Blocked Capability Report

When the graph cannot start any worker, return only:

```markdown
### Review Outcome

Blocked before worker dispatch: <concise reason>.

### Capability And Deadline Gate

| Evidence source | Concurrent free/required | Lifetime creations remaining/planned | Time available/first dispatch | Isolation | Result |
| --- | --- | --- | --- | --- | --- |

### Execution Accounting

| Routers consulted | Workers created | Skills executed | Nodes blocked before execution | Isolation failures | Validators run | Validators not run |
| --- | --- | --- | --- | --- | --- | --- | --- |

### Repository State

State whether capture was intentionally skipped, whether source or Git state
changed, and that no same-context substitute was used.
```

When the early gate fails, use `0` routers consulted and do not invent selected
nodes. When an initial hard deadline leaves no first-dispatch window after
routing, list provisional node IDs as blocked before execution and every planned
validator as not run. Distinguish an isolation failure, no concurrent slot, a
known zero lifetime count, and deadline exhaustion.
