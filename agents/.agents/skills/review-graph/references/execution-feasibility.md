# Review Graph Execution Feasibility

Use this contract before repository capture, after the exact node plan exists,
and before every worker dispatch. Use `scripts/review_graph_plan.py` as the
deterministic decision model.

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

Treat an authoritative lifetime count as a completion forecast. A known zero
blocks the first dispatch; a positive count smaller than the planned graph does
not erase runnable work. Report that full completion is not guaranteed, dispatch
fresh workers sequentially, and account for later unrun nodes. When the count is
absent, record `not exposed; enforced incrementally` rather than inferring a
limit or release policy from concurrent capacity.

Do not call a status or listing surface for capacity diagnosis when its schema
or observed payload may include messages, reports, findings, results, outputs,
or other task content. Do not spawn a dummy worker. If a mechanism unexpectedly
returns task content, discard its values, retain only the sensitive field paths
needed to identify the isolation failure, persist that blocker, and stop.

## Early Capability Gate

Before capture, router loading, graph construction, or a pre-dispatch report:

1. Verify that fresh workers with no inherited turns are supported.
2. Obtain safe aggregate concurrent-capacity evidence without creating a worker.
3. Require at least one free concurrent slot. If an authoritative lifetime count
   is present, require it to be greater than zero for the first dispatch.
4. Record the evidence source, aggregate values, optional lifetime forecast,
   isolation status, and gate result in the journal.
5. If a check fails, emit the blocked capability report below and stop. Do not
   describe routers as consulted, create selected leaf nodes, or claim that a
   focused skill or validator ran.

An unavailable lifetime count is not a failed check. The early gate proves only
that the first isolated invocation can start.

## Exact Schedule Assessment

After routing creates a provisional node plan, count the maximum fresh-worker
attempts for:

- every audit, validation, independent-review, synthesis, fix, and revalidation
  node
- every permitted fresh-worker retry
- every planned post-fix rerun
- an explicit review-and-fix iteration reserve, when fixes are authorized

Do not count router reads, coordinator reconciliation, or formatting-only
follow-ups to an already-created worker as fresh creations. Dispatch nodes one
at a time and never assign a later node to a completed worker. Required peak
worker concurrency is therefore one.

Record planned attempts and any authoritative lifetime count. Classify
full-plan creation capacity as `guaranteed`, `not guaranteed`, or `unknown`.
Neither `not guaranteed` nor `unknown` blocks the first runnable node. If a real
worker creation later fails, record that node as `blocked-before-execution`,
preserve completed reports, and block every undispatched node. Never replace
them with coordinator review or reused-worker follow-ups.

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
