# Review Execution Feasibility

Use this contract only when the user explicitly requests isolated execution.
Ordinary `review-graph` and `repo-review` requests use adaptive grouped
execution and do not inspect worker capacity before routing.

## Contents

- [Profile Selection](#profile-selection)
- [Safe Runtime Evidence](#safe-runtime-evidence)
- [Isolated Capability Gate](#isolated-capability-gate)
- [Isolated Epoch Schedule](#isolated-epoch-schedule)
- [Failure And Fallback](#failure-and-fallback)
- [Isolated-Only Blocked Report](#isolated-only-blocked-report)

## Profile Selection

Interpret explicit requests as follows:

- `isolated`, `isolated-graph`, or equivalent: prefer isolated execution and
  fall back to adaptive grouped execution when it is unavailable.
- `isolated-only`, `no grouped fallback`, or equivalent: require isolated
  execution and block when it is unavailable.
- no isolation wording: select adaptive grouped execution without running this
  gate.

Use `select_execution_profile` in `scripts/review_graph_plan.py` as the
deterministic model. Missing safe telemetry is a reason to select grouped
delivery, not a reason to return zero review results.

## Safe Runtime Evidence

Accept only an authoritative aggregate surface containing:

```text
source
concurrent_worker_limit
active_workers
```

Accept these lifetime values when the same surface supplies both:

```text
fresh_worker_creations_remaining
lifecycle_semantics
```

Never call an agent list, task list, status feed, message history, or other
surface whose schema or observed payload may contain reports, findings,
messages, results, or outputs. Never create a dummy worker to probe capacity.
Do not infer active count or release behavior from a documented concurrency
limit.

When safe aggregate metadata is unavailable, choose adaptive grouped execution. When a
mechanism unexpectedly exposes task content, retain only the sensitive field
paths needed to identify the isolation failure, discard the values, and choose
adaptive grouped execution unless isolation is mandatory.

## Isolated Capability Gate

Before repository capture, router loading, or graph construction:

1. Verify fresh workers with no inherited turns.
2. Obtain safe aggregate concurrent-capacity evidence without creating a
   worker.
3. Require at least one free concurrent slot.
4. Choose a positive per-root fresh-worker budget, defaulting to 24, and reserve
   at least one creation for recovery and finalization.
5. Set the effective per-root budget to the smaller configured or authoritative
   lifetime value. Require that effective budget to fit at least one execution
   worker plus the reserve.
6. Record the evidence source, values, configured and effective budgets,
   reserve, and gate result outside the reviewed repository.

If this gate fails, do not load isolated routers or create an isolated node
plan. Select adaptive grouped execution immediately unless the request is
isolated-only.

## Isolated Epoch Schedule

After exhaustive isolated routing creates the complete node plan, count every
audit, validation, independent-review, synthesis, fix, revalidation, and planned
retry node. Partition the plan into fresh-root epochs satisfying:

```text
nodes in the current epoch + recovery/finalization reserve <= effective budget
```

Never remove applicable coverage to make an epoch fit. Dispatch sequentially so
peak worker concurrency remains one. A future epoch keeps isolated completion
incomplete.

Apply the shared hard-deadline contract in
[`planning-contract.md`](planning-contract.md#hard-deadline-contract) to every
isolated dispatch. Epoch partitioning does not relax that deadline or its
reconciliation reserves.

## Failure And Fallback

For an isolation preference:

- If capability fails before capture, run adaptive grouped execution.
- If the gate or a dispatch fails before any isolated evidence is accepted,
  preserve the attempt and select adaptive grouped execution; do not label the
  result mixed.
- If a planned worker cannot be created, preserve the routing and node identity
  and execute that missing node adaptively.
- If a worker is created but its skill cannot load or execute before producing
  accepted evidence, record
  `blocked-after-creation-before-skill-execution`, then execute that missing
  node adaptively.
- If creation or capacity fails after isolated evidence was accepted, preserve
  accepted proof objects and continue the remaining graph adaptively. Once
  grouped fallback executes, label the result `mixed` with partial isolated
  evidence; do not claim isolated completion.
- Apply that same post-acceptance handling when a created worker fails to load
  its skill or execute: preserve earlier accepted proof objects and continue
  only missing or invalidated nodes adaptively.
- If a global deadline prevents more isolated dispatch but still leaves useful
  review time, continue dependency-ready adaptive nodes and account for every
  node the deadline leaves incomplete.

Do not return only a resume manifest while adaptive review remains possible. A
resume manifest may accompany the mixed result, but it cannot replace accepted
findings and proof evidence.

For isolated-only execution, stop after the first capability, creation,
`blocked-after-creation-before-skill-execution`, or deadline failure, preserve
accepted reports, and emit the exact resume manifest. Never substitute adaptive
evidence against the user's isolation requirement.

## Isolated-Only Blocked Report

When an isolated-only request cannot start, return:

```markdown
### Review Outcome

Blocked before isolated worker dispatch: <concise reason>.

### Isolation Gate

| Evidence source | Concurrent free/required | Lifetime creations remaining/planned | Isolation | Result |
| --- | --- | --- | --- | --- |

### Execution Accounting

| Routers consulted | Workers created | Skills executed | Validators run |
| --- | --- | --- | --- |

### Repository State

State that capture was intentionally skipped, whether source or Git state
changed, and that grouped fallback was prohibited by the request.
```

Use zero routers, workers, skills, and validators when the early isolated gate
fails. Never construct a provisional graph merely to make this report longer.
