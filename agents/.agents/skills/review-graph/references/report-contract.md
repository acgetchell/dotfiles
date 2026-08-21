# Review Graph Reporting Contract

Use this detailed contract for every `review-graph` profile. Adaptive execution
records worker attempts and coordinator fallbacks exactly; it does not fabricate
worker, epoch, or isolation evidence. Read `evidence-contract.md` for the
versioned proof objects from which these views are derived.

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
  skill/reference digests, dispatch fingerprints, execution location,
  accepted/blocked/invalidated-stale result status,
  complete accepted result, blocked record, or stale invalidation record
review_evidence[]:
  schema version, evidence ID, node and requirement IDs, execution location,
  skill/reference digests, fingerprints, native-result artifact and digest,
  findings, validator requirements, handoffs, synthesis predecessor evidence
  IDs, parsed native Machine Evidence, acceptance and stale status
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
validation_evidence[]:
  schema version, evidence and node IDs, mapped requirements, fingerprints,
  command/environment digests, native-result artifact and digest, acceptance
supplied_validation_evidence[]:
  evidence ID, complete standalone Validation Result or artifact, import
  disposition, identity comparison, graph verifier node, reused-by nodes
invalidation_events[]:
  invalidated node/evidence, cause, persisted fix/revalidation transition
  reports, source-state boundary, and replacement final-state evidence
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
repository_review_proof:
  complete review and validation requirement mappings, accepted and stale
  evidence IDs, unresolved handoffs, final synthesis evidence, artifact manifest
  identity, verifier, and deterministic acceptance result
```

Final proof records contain only recaptured final-state audit,
independent-review, validation, and synthesis evidence plus exact
non-executable reuse. Keep prior `fix` and `revalidation` native reports in
`invalidation_events`; never list them as accepted final proof nodes. For every
accepted artifact, retain the exact UTF-8 Markdown, parsed canonical Machine
Evidence object, and heading-validation result so a future agent can repeat the
same semantic gate from trusted bytes.

Keep complete node reports unchanged. The journal adds cross-node indexes; it
does not replace raw reports with summaries.

Persist the journal and raw reports after every accepted, blocked, or
invalidated/stale node. Use
session-owned keyed storage when available; otherwise create a unique temporary
directory outside the reviewed repository. Do not rely on conversation context
alone. Record the storage mechanism and location in the journal and final
`Repository State` section. Failure to obtain persistent scratch storage is a
reporting limitation, not permission to discard or compress raw evidence.

## Pre-dispatch Output

For explicit isolation, if the early capability gate fails or the initial hard
deadline leaves no dispatch window, use the concise format in
`execution-feasibility.md`. An isolation preference then starts adaptive
execution; isolated-only stops. Adaptive grouped execution does not run this
early capacity gate.

Show the applicable sections before the first review execution.

### Scope

State authorization, capture mode, path boundary, base when applicable, and all
three fingerprints.

### Capability, Worker Budget, And Deadline Gate

| Evidence source | Concurrent free/required | Configured/effective root budget | Complete graph/current epoch nodes | Epoch count | Recovery/finalization reserve | Full-cap critical path | Hard deadline | Isolation | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Use aggregate capacity values only. Never reproduce payload text returned by an
unsafe capacity mechanism. When the runtime supplies no lifetime count, use the
concise adaptive-fallback or isolated-only blocked report instead of presenting
an executable isolated epoch. Otherwise show that current-epoch nodes plus
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
nodes, coordinator executions, nodes blocked after execution, nodes blocked before execution, isolation
failures, rerun nodes, independent checks, canonical findings by disposition,
material changes, validation requirements by disposition, coalesced validator
units, unique validator executions, validators not run, per-root budget,
reserve, execution epochs, and nodes stopped by the hard deadline.
State `complete` or `incomplete` using the completion gate.

### Execution Lifecycle

| Attempt or node | Execution location | Worker created | Skill loaded/executed | Result returned | Node outcome | Capacity consumed | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- |

Include every creation attempt, coordinator fallback, and node blocked before
execution. A failed creation never counts as a skill execution; a later
coordinator execution is a distinct lifecycle record. A completed worker must
never appear as the worker for a later node.

### Skills Run

| Node | Skill | Mode | Why it ran | Owned surface | Status | Outcome |
| --- | --- | --- | --- | --- | --- | --- |

Include every worker or coordinator node that actually loaded and executed its
skill, including a conforming blocked result. Exclude nodes blocked before any
execution or before skill loading; those belong in `Execution Lifecycle` and
`Review Graph Evidence`. Include focused review, fix, dedicated
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

| Node | Skill | Mode | Lifecycle status | Execution location | Worker created | Skill executed | Scope/worktree/repository fingerprints | Skill/reference digests | Validators | Invalidated/revalidated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

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
selected nodes = accepted nodes + blocked-after-execution + blocked-before-execution + invalidated/stale nodes
worker creation attempts = workers created + creation failures
skills executed <= workers created + coordinator executions
canonical findings = fixed + remaining + accepted-risk + blocked
executed validators = unique validation-ledger execution entries
planned validators = executed validators + validators not run
validation requirements = passed + reused + failed + blocked
material changed files = union of exact files in change records
invalidated evidence = replaced evidence + explicitly unresolved stale evidence
```

Also verify:

- every worker lifecycle row has a journal node or creation attempt
- every skills-run row has a worker or coordinator execution, a loaded skill,
  and an accepted or blocked-after-execution result
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
- isolation capacity evidence contains safe aggregate concurrency and lifetime
  metadata only; an absent lifetime count selects adaptive execution, and any
  isolation failure is reported without reproducing leaked task content
- every node that received neither worker nor adaptive coordinator execution
  remains selected and is reported as blocked before execution
- no completed worker was reused for a later node
- every adaptive coordinator fallback preserves the failed worker attempt and
  executes the same node identity, scope, skill, and evidence contract
- every invalidated/stale node is recorded as such until a current replacement
  result is accepted; an unresolved stale node blocks `complete`
- every source-mutating fix and subsequent revalidation is preserved as
  separately verified transition history, followed by recapture, rerouting,
  and a final plan with no `fix` or `revalidation` executable node
- every accepted native artifact has the contract's exact top heading and
  ordered required headings, exactly one canonical bounded Machine Evidence
  block, and payload fields matching its typed expectation, envelope, and
  source/Git state
- every synthesis native payload and typed envelope names exactly the accepted
  predecessor evidence IDs derived from the planner-owned proof mapping
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
- matched fingerprints, synthesized final output, deduplicated findings, and an
  accepted `RepositoryReviewProof` are all proved before the outcome says
  `complete`; isolated completion additionally requires zero isolation failures
