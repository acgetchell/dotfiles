---
name: review-graph
description: "Coordinate complete mixed-surface repository reviews across C++, Rust, Python, tooling, and documentation. Route every applicable review skill, run independent work in subagents when possible with coordinator fallback, dispatch validation through review-validator, and combine versioned fingerprinted evidence into one reusable repository proof. Use for branch, PR, staged, release-readiness, whole-repository, fix-all, or review-and-fix work spanning multiple surfaces."
---

# Review Graph

Deliver the same coverage and result as successively invoking every applicable
review skill against one captured source state. Prefer parallel workers when
they are safe and useful, but never let worker availability change coverage.

Read the [evidence contract](references/evidence-contract.md) before capture,
routing, dispatch, validation, or reuse. Use
`scripts/review_graph_plan.py` as the deterministic authority for routing
closure, evidence acceptance, validation mapping, invalidation, and final proof
reconciliation.

## Choose The Execution Profile

Choose exactly one profile:

- **Adaptive grouped** is the default for ordinary `$review-graph` and
  `$repo-review` requests. Dispatch independent review nodes to subagents when
  possible. Execute the same node in the coordinator when a worker is
  unavailable. Both locations must return the same evidence contract.
- **Isolated** is an explicit preference. Require a fresh no-inherited-turn
  worker for each node. A gate or dispatch failure before any accepted isolated
  evidence selects adaptive grouped execution, not mixed. After accepted
  isolated evidence, preserve it and continue the missing graph through
  adaptive grouped execution; label the result mixed only when that grouped
  fallback actually runs.
- **Isolated-only** is an explicit hard requirement. Block and emit the resume
  manifest instead of using coordinator fallback.

Use `select_execution_profile` only for an explicit isolation request. Missing
safe capacity telemetry selects adaptive grouped execution. Ordinary adaptive
reviews do not inspect worker capacity before routing; a failed best-effort
worker creation simply selects coordinator execution for that node.

## Capture And Authorization

- Read repository instructions before reviewing or editing.
- Capture branch scope by default. Honor explicit staged, worktree, pull-request,
  release, baseline, path, base, and exclusion requests.
- Use `scripts/capture_scope.py` to record scope, worktree, and repository-state
  fingerprints once before routing.
- Treat fixes as unauthorized unless explicitly requested. Never mutate Git
  state.
- Persist the graph journal, native results, evidence envelopes, and artifact
  manifest outside conversation context.

## Exhaustive Routing

Read completely:

1. [`repo-review` check routing](../repo-review/references/check-routing.md)
2. [routing handoff](references/routing-handoff.md)
3. [routing catalog](references/routing-catalog.json) through the planner

`review-graph` owns repository-layer routing. Apply the deterministic repository
classifier as a conservative floor and return one decision for every
repository-layer catalog entry. Consult each selected surface orchestrator in
its `graph-routing` mode for one disposition per surface candidate. Routers
return records only; they are not executed review skills.

Convert every selected leaf, independent review, validator, synthesis, fix, and
revalidation requirement to the complete graph. A selected applicable skill may
complete only through accepted current evidence or exact verified reuse. Record
every non-applicable and user-excluded candidate; budget and worker availability
never make an applicable skill disappear.

`selected` identifies applicable required review work, regardless of whether a
worker or the coordinator will execute it. Assign execution location only after
routing closes. Execution epochs belong only to isolated scheduling; adaptive
grouped execution schedules the complete dependency graph without epochs.

## Plan And Execute Review Nodes

Read [bounded planning](references/planning-contract.md) and
[node contract](references/node-contract.md) before dispatch. Give every node
its exact skill path, skill digest, reference digests, owned scope,
fingerprints, authorization, validation requirement IDs, and artifact location.

For adaptive grouped execution:

1. Dispatch dependency-independent read-only review nodes to separate subagents
   concurrently when safe worker creation is available.
2. When a worker cannot be created, or fails before accepted evidence, run that
   exact node successively in the coordinator. Do not reroute, broaden, or omit
   it.
3. Join at a barrier, persist every native result, create its `ReviewEvidence`
   envelope, and run `assess_review_evidence`.
4. Resolve late handoffs and add newly applicable nodes before dependent
   validation or synthesis.

For isolated execution, also read
[execution feasibility](references/execution-feasibility.md). Use the lower
configured or authoritative lifetime capacity as the effective per-root budget,
preserve the recovery reserve, and run exactly one skill in each fresh worker.
Adaptive evidence is accepted only after fallback is declared; it never proves
isolated completion.

Read-only nodes sharing one captured state may run concurrently. Fix nodes are
always serialized. After each authorized fix, recapture state, begin a new
evidence epoch, invalidate affected evidence, reroute changed surfaces, and
rerun only stale or newly required nodes.

### Bound Repair Convergence

Do not seek an automatic whole-repository fixed point. For review-and-fix work,
the default repair budget is two source-mutating epochs after the initial review
barrier: one batched repair epoch and, when the closeout review finds a new
actionable defect, one follow-up repair epoch. A different budget requires an
explicit user request.

- Batch compatible confirmed fixes before recapturing. Keep fix execution
  serialized, but do not create a new evidence epoch for every individual edit.
- After a repair batch, recapture once and rerun only invalidated review nodes,
  newly applicable nodes, their validators, and downstream synthesis. Preserve
  unaffected evidence only when the planner's exact reuse gate proves its
  covered source and skill/reference identities unchanged.
- Run broad canonical CI once after the last planned mutation. Earlier repair
  epochs use the narrow checks required by their finding owners.
- Run at most one full-scope independent closeout review automatically. If it
  finds a defect and repair budget remains, apply the follow-up batch and run
  targeted independent revalidation of that batch; do not restart the complete
  repository review automatically.
- When the budget is exhausted, or a required current-state proof cannot close,
  stop with the accepted partial result and exact resume manifest. Report every
  remaining finding or stale requirement explicitly; never imply completion.

An explicit request to continue may start another bounded run from the resume
manifest. Unchanged external state or the absence of a proof is not permission
to keep retrying indefinitely.

## Validation

Collect validation requirements from accepted review results. Coalesce only
requirements with identical source, command or canonical recipe, working
directory, environment/toolchain, features, platform, artifact ownership, and
mutation/locking identity.

Dispatch every coalesced unit through
[`review-validator`](../review-validator/SKILL.md). In adaptive execution it may
run in a worker or the coordinator; in isolated execution it must run in its own
fresh worker. Persist the complete native Validation Result, create
`ValidationEvidence`, and run `assess_validation_evidence`. A failed validator
is evidence for its review owner, not automatically a finding.

Reuse prior evidence only after recapturing state and verifying the artifact,
schema, result digest, skill/reference digests, command/environment identity,
and exact selection. Mark mismatches stale and run the affected node.

## Synthesis And Completion

Run surface synthesis only after its selected review and validation evidence is
accepted. Run repository synthesis only after all required surface evidence,
independent review, validation mappings, handoffs, exclusions, and invalidation
history are available. Synthesis may deduplicate and reconcile findings; it may
not perform missing review or validation.

Construct and verify one `RepositoryReviewProof`. Report `complete` only when:

- every applicable review requirement maps exactly once to accepted non-stale
  review evidence
- every required validation requirement maps exactly once to accepted
  validation evidence
- every handoff is resolved and post-fix routing is current
- final repository synthesis is accepted
- the persisted artifact manifest and source fingerprints verify

## Final Report

Lead with findings and blockers. State the execution profile and whether the
proof is complete. Include changes, validation, unresolved risks, exact skills
and references executed, artifact-manifest location, final source/Git state,
and the five-row `Review Evidence` compatibility table derived from the proof.

Include worker lifecycle and accepted evidence for every execution profile.
For mixed, isolated, or isolated-only execution, also include isolation failures
and incomplete epochs required by [report contract](references/report-contract.md).
Never imply that routing, planning, skill loading, or an ancestor's summary
constitutes accepted review evidence.
