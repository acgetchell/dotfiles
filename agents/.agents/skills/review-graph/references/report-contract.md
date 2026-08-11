# Review Graph Reporting Contract

Use this contract for the coordinator-owned graph journal, the pre-dispatch
plan, and the final user-facing report. The final answer must be self-contained;
commentary and hidden worker reports are not substitutes for any required
section.

## Contents

- [Graph Journal](#graph-journal)
- [Pre-dispatch Output](#pre-dispatch-output)
- [Finding Dispositions](#finding-dispositions)
- [Final Output](#final-output)
- [Final Reconciliation Gates](#final-reconciliation-gates)

## Graph Journal

Initialize the journal before routing and update it after every routing,
dispatch, finding, fix, invalidation, revalidation, and synthesis event. Preserve
these records:

```text
scope:
  request, authorization, graph mode, paths, scope/worktree/repository-state
  fingerprints, instructions, inspection commands, external limitations
capability_gate:
  aggregate evidence source, concurrent limit and active count, optional
  lifetime creations and lifecycle semantics, configured/effective worker
  budget ceiling, isolation status, early result; never task messages, reports,
  findings, outputs, or payloads
budget_plan:
  configured and effective per-root worker budget, telemetry basis, complete
  selected requirements and nodes, coalesced validator units, synthesis nodes,
  recovery/finalization reserve, execution epochs and fresh-root continuations,
  dispatch decision, hard deadline or unbounded-by-request, full-cap
  critical path, time reserves, remaining dispatch window, stop policy, and
  nodes the deadline prevented from running
routing_decisions[]:
  catalog/router/rule IDs, exact skill/path, disposition, reason, applicability
  evidence, owned paths, shared owners, exact reuse or user exclusion,
  applicable static references, validation requirements, synthesis dependency
nodes[]:
  node ID, exact skill/path, selection reason, mode, owned paths,
  predecessors, instruction and static routing/repository references, budgets,
  dispatch fingerprints, result status,
  complete accepted result or blocked record
worker_attempts[]:
  attempt ID, node ID, creation ordinal, created=yes/no, skill loaded=yes/no,
  result returned=yes/no, elapsed time, remaining deadline, blocker; never infer
  execution from node selection
validation_requirements[]:
  requirement ID, owning skill or routing authority, exact commands,
  state/configuration/selection identity, dependency policy, disposition,
  satisfying validation node or ledger entry
validation_units[]:
  unit ID, every requirement ID satisfied, exact coalescing identity, command or
  canonical recipe, candidate evidence, selected/omitted status
independent_checks[]:
  repository-independent-review node ID, exact change target, dispatch fingerprints,
  native report, graph finding IDs, status, rerun or invalidation history
findings[]:
  finding ID, severity, owning node/skill, summary, evidence,
  disposition, duplicate-of when applicable
changes[]:
  change ID, finding IDs, owning node/skill, exact files,
  what changed, why, preserved contracts/tradeoffs
validation_ledger[]:
  exact command, all three evidence fingerprints, environment/configuration,
  result, source node, reused-by nodes
supplied_validation_evidence[]:
  evidence ID, complete standalone Validation Result or artifact, import
  disposition, identity comparison, graph verifier node, reused-by nodes
invalidation_events[]:
  invalidated node/evidence, cause, replacement revalidation/synthesis
validators_not_run[]:
  node and requirement IDs, exact planned commands, pre-execution blocker
deadline_events[]:
  elapsed time, remaining dispatch window, active worker action, and every node
  blocked by global-deadline-exhausted
resume_manifest:
  exact captured fingerprints, failure reason, undispatched and unaccepted
  nodes, outstanding validator units and syntheses, unresolved handoffs, future
  execution epochs, journal/raw-report location, and whether a fresh root task
  may be required
```

Keep complete node reports unchanged. The journal adds cross-node indexes; it
does not replace raw reports with summaries.

Persist the journal and raw reports after every accepted or blocked node. Use
session-owned keyed storage when available; otherwise create a unique temporary
directory outside the reviewed repository. Do not rely on conversation context
alone. Record the storage mechanism and location in the journal and final
`Repository State` section. Failure to obtain persistent scratch storage is a
reporting limitation, not permission to discard or compress raw evidence.

## Pre-dispatch Output

If the early capability gate fails or the initial hard deadline leaves no
dispatch window, use only the concise blocked format in
`execution-feasibility.md`. Do not load routers after an early failure or
display a provisional plan as executable when no first worker can run.

Show these sections before spawning the first worker.

### Scope

State authorization, capture mode, path boundary, base when applicable, and all
three fingerprints.

### Capability, Worker Budget, And Deadline Gate

| Evidence source | Concurrent free/required | Configured/effective root budget | Complete graph/current epoch nodes | Epoch count | Recovery/finalization reserve | Full-cap critical path | Hard deadline | Isolation | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Use aggregate capacity values only. Never reproduce payload text returned by an
unsafe capacity mechanism. Use `not exposed; bounded by configured budget <N>`
when the runtime supplies no lifetime count. Show that current-epoch nodes plus
reserve fit the effective root budget and list every later fresh-root epoch.
State the hard-deadline and worker-creation stop policies.

### Routing Authorities Consulted

| Surface | Router | Reference | Decision |
| --- | --- | --- | --- |

Routers in this table were consulted, not run as review workers.

### Complete Graph And Epochs

| Node | Skill and exact path | Mode | Why selected | Owned scope or target | Predecessors | Expected validation | Epoch/budget |
| --- | --- | --- | --- | --- | --- | --- | --- |

The budget cell must include elapsed/retry caps and maximum fresh-worker attempts
for the node. These are safety/accounting bounds, not upfront reservations.

Follow with a compact `Validation Coalescing` table:

| Validator unit | Requirements satisfied | Reused command/recipe | Identity and compatibility basis | Candidate evidence |
| --- | --- | --- | --- | --- |

List every declared validation requirement exactly once across the unit rows.

### Exhaustive Routing Ledger

| Catalog/rule | Router | Skill and path | Disposition | Applicability evidence | Scope/owners | Reuse or limitation |
| --- | --- | --- | --- | --- | --- | --- |

List every candidate owned by every consulted router exactly once. Do not call
`not-applicable`, exact reuse, or user exclusion an executed skill. A
budget-deferred, capability-blocked, failed, or unresolved row makes the plan
incomplete.

### Supplied Validation Evidence

| Evidence | Standalone status | Identity match | Import disposition | Planned verifier or owner |
| --- | --- | --- | --- | --- |

Show this table when the user supplied a standalone `review-validator` result.
Use `candidate-for-reuse`, `evidence-only`, `stale`, `malformed`, or `ineligible`
as the import disposition. Omit the section only when no result was supplied.

## Finding Dispositions

Assign every canonical finding exactly one final disposition:

- `fixed`: an authorized change landed and independent revalidation accepted it
- `remaining`: confirmed and not fixed
- `accepted-risk`: user explicitly accepted it without a fix
- `blocked`: confirmation or correction could not complete

Mark redundant specialist reports as `duplicate` and link them to the canonical
finding. Mark a synthesis-rejected false positive as `withdrawn` with the exact
reason. Duplicate and withdrawn IDs do not count as canonical findings.

Do not silently omit low-severity, duplicate, withdrawn, or fixed findings.

## Final Output

Use the following sections in this order.

### Review Outcome

Lead with the practical result. Include counts for routers consulted, selected
nodes, worker creation attempts, workers created, skills executed, accepted
nodes, nodes blocked after execution, nodes blocked before execution, isolation
failures, rerun nodes, independent checks, canonical findings by disposition,
material changes, validation requirements by disposition, coalesced validator
units, unique validator executions, validators not run, per-root budget,
reserve, execution epochs, and nodes stopped by the hard deadline.
State `complete` or `incomplete` using the completion gate.

### Worker Lifecycle

| Attempt or node | Worker created | Skill loaded/executed | Result returned | Node outcome | Capacity consumed | Blocker |
| --- | --- | --- | --- | --- | --- | --- |

Include every creation attempt and every node blocked before any attempt. A
failed creation never counts as a skill execution. Show every later node blocked
after a creation failure or hard-deadline exhaustion. A completed worker must
never appear as the worker for a later node.

### Skills Run

| Node | Skill | Mode | Why it ran | Owned surface | Status | Outcome |
| --- | --- | --- | --- | --- | --- | --- |

Include every worker that actually loaded and executed its skill, including a
worker that later returned a conforming blocked result. Exclude nodes blocked
before worker creation or before skill loading; those belong in `Worker
Lifecycle` and `Review Graph Evidence`. Include focused review, fix, dedicated
`review-validator`, `repository-independent-review`, revalidation, and
production-review synthesis nodes. Use the exact skill ID. Keep routers out of
this table and do not describe the independent reviewer as a validator.

Follow with a short `Routing authorities consulted` paragraph or table so the
user can distinguish router reads from executed skills.

### Findings and Disposition

| Finding | Severity | Owning skill | Problem and evidence | Final disposition | Change or remaining action |
| --- | --- | --- | --- | --- | --- |

Include every canonical finding plus duplicate and withdrawn records. Preserve
the reason for deduplication or withdrawal.

Preserve independent-review findings in their native report and assign stable graph
IDs for this table. Route each to the applicable owning surface without implying
that a validator diagnosed it.

### Changes Made

For review-and-fix graphs, include one row per material change:

| Change | Finding(s) | Owning skill | Files | What changed | Why | Validation | Independent revalidation |
| --- | --- | --- | --- | --- | --- | --- | --- |

Use exact paths. Explain behavior and rationale rather than repeating filenames
or saying only “fixed,” “cleanup,” or “hardening.” Report explicit incidental
changes in this same table with their incidental-change ID.

For review-only graphs, write `No files were changed; authorization was
review-only.`

### Remaining Findings and Limitations

Lead with P0/P1 items, then blocked nodes, untested configurations, environment
limits, and accepted risks. Write `none` only when all are genuinely absent.

### Routing Dispositions And Exclusions

List every catalog candidate grouped by router with `selected`,
`not-applicable`, exact verified reuse, or explicit user exclusion. Explain
conflict resolutions and coverage limitations. A budget-deferred,
capability-blocked, failed, unknown, or unresolved candidate belongs under
remaining limitations and makes the graph incomplete.

### Validation Ledger

| Command | Requirements | Fingerprints | Environment/configuration | Result | Produced by | Reused by |
| --- | --- | --- | --- | --- | --- | --- |

List each unique execution once. Include the validation-requirement IDs it
satisfies. Do not present a reused result as a rerun. A failed command remains
failed evidence until an exact replacement execution supersedes it.

Identify imported standalone evidence in `Produced by` and the graph validator
node that verified it in `Reused by`. Do not claim that a standalone result was
automatically transferred from another task.

### Validators Not Run

| Validator node | Requirements | Planned commands | Why not run | Blocked before or after worker creation |
| --- | --- | --- | --- | --- |

List every selected validation node without an accepted native result. Keep its
commands out of the executed validation ledger. Write `none` only when all
planned validators returned accepted results.

### Resume Manifest

When any node is undispatched or unaccepted, list its exact node ID, skill, mode,
requirements, priority, dependencies, planned validator commands, and blocker.
Include the captured fingerprints and persisted journal/raw-report location.
State that retrying in the same root task does not reset a lifetime worker limit
and whether a fresh root task may be required. Omit this section only for a
complete graph.

### Review Graph Evidence

| Node | Skill | Mode | Lifecycle status | Worker created | Skill executed | Scope/worktree/repository fingerprints | Skill/references loaded | Validators | Invalidated/revalidated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Include one row per selected node. If an invalidated node was rerun, identify
both the stale evidence and its replacement rather than overwriting history.
Use lifecycle statuses such as `accepted`, `blocked-after-execution`, and
`blocked-before-execution`; never fabricate loaded references for an uncreated
worker.

### Review Evidence

Derive this compatibility view from the exhaustive graph ledger:

| Orchestrator | Status | Why selected or skipped | Scope handed off | Skills/references actually loaded | Validators |
| --- | --- | --- | --- | --- | --- |

Include exactly one row for `project-tooling-review`,
`cpp-review-orchestrator`, `rust-review-orchestrator`,
`python-review-orchestrator`, and `docs-review-orchestrator`. Use `selected`,
`skipped`, or `blocked`; never imply that a consulted router executed.

### Repository State

State the final branch/HEAD, whether the index or worktree changed during the
graph, which source changes belong to this task, and whether git state was
mutated. Include the final repository-state fingerprint and identify
out-of-repository validator artifacts separately.

## Final Reconciliation Gates

Do not send the final response until all applicable equalities hold:

```text
selected nodes = accepted nodes + blocked-after-execution + blocked-before-execution
worker creation attempts = workers created + creation failures
skills executed <= workers created
canonical findings = fixed + remaining + accepted-risk + blocked
executed validators = unique validation-ledger execution entries
planned validators = executed validators + validators not run
validation requirements = passed + reused + failed + blocked
material changed files = union of exact files in change records
invalidated evidence = replaced evidence + explicitly unresolved stale evidence
```

Also verify:

- every worker lifecycle row has a journal node or creation attempt
- every skills-run row has a created worker, a loaded skill, and an accepted or
  blocked-after-execution result
- every selected leaf appears in `Skills Run` or is explicitly
  blocked-before-execution without a claim that its skill ran
- every finding ID appears in `Findings and Disposition`
- every fixed finding points to at least one change and independent revalidation
- every material change points to a finding or explicit incidental-change ID
- every change explains both what changed and why
- every validation claim points to one ledger row
- every validation requirement points to one accepted `review-validator`
  result; reuse is accepted only when that result verifies the exact ledger entry
- every selected validator appears exactly once as an executed validator or in
  `Validators Not Run`
- every supplied standalone validator result has one journal import disposition;
  every reused import has a current graph validator result that verified it
- every concrete change target has an accepted current
  `repository-independent-review` result; whole-repository baselines without a
  concrete diff mark that catalog entry not applicable
- every native independent-review finding has a stable graph finding ID and final
  disposition
- no independent-review result is counted as validation evidence and no
  `review-validator` failure is promoted to a finding without reviewer diagnosis
- routers are described as consulted, never as executed skills
- capacity evidence contains safe aggregate concurrency and optional lifetime
  metadata only; an absent lifetime count is not a blocker, and any isolation
  failure is reported without reproducing leaked task content
- every node prevented by worker-creation failure or hard-deadline exhaustion
  remains selected and is reported as blocked before execution
- no completed worker was reused for a later node
- no blocked node was replaced by same-context coordinator review
- each execution epoch's nodes plus recovery/finalization reserve did not exceed
  its effective root budget, and every epoch completed before `complete`
- every declared validation requirement maps to exactly one coalesced validator
  unit and every accepted evidence reuse maps back to all requirements it
  satisfies
- every consulted router catalog has exactly one decision per candidate and no
  path, rule, owner, or applicability-evidence mismatch
- every selected applicable specialist completed or has exact verified reuse;
  no meaningful or budget skip satisfies applicability
- every late handoff resolved and routing was revalidated after surface-changing
  fixes
- required documentation/citation coverage, baseline validation, independent
  review, and language/repository syntheses completed
- no undispatched or unaccepted node remains when the outcome says `complete`
- matched fingerprints, zero isolation failures, synthesized final output, and
  deduplicated findings are all proved before the outcome says `complete`
