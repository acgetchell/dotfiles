---
name: review-graph
description: "Coordinate provenance-preserving mixed-surface repository reviews across C++, Rust, Python, tooling, and documentation. Capture one source state, route every applicable specialist, run fresh-context review nodes, validate exact requirements, and compile persisted evidence into one verified repository proof. Use for branch, PR, staged, release-readiness, whole-repository, fix-all, or review-and-fix work spanning multiple surfaces."
---

# Review Graph

Deliver the coverage of every applicable focused review while keeping proof
bookkeeping out of model-authored prose. Reviewers make semantic judgments;
deterministic scripts own catalog identity, fingerprints, digests, canonical
artifacts, evidence envelopes, and proof reconciliation.

Read [the runtime contract](references/runtime-contract.md). Execute the helper
scripts without reading their implementations unless a script fails or this
task changes them.

## Profiles

- **Adaptive grouped** is the default. Run dependency-independent read-only
  nodes concurrently when useful and use coordinator fallback for a failed
  worker attempt.
- **Isolated** is an explicit preference. Require a fresh worker for every node
  and permit declared adaptive fallback.
- **Isolated-only** is an explicit hard requirement. Emit a resume manifest
  rather than falling back.

Every worker in every profile uses `fork_turns: "none"`. Give it only the exact
dispatch, repository instructions, skill path, relevant static references, and
compact result schema. Record `fresh_context: true`. A coordinator execution
uses the same compact payload contract and records `worker_created: false`.

## Capture And Authorization

- Read repository instructions before review or edits.
- Capture branch scope by default; honor explicit staged, worktree, pull-request,
  release, baseline, path, base, and exclusion requests.
- Use `scripts/capture_scope.py` once before routing and after each authorized
  repair batch. Preserve scope, worktree, and repository-state fingerprints.
- Normalize the capture and compact routing/validation template with
  `scripts/review_graph_bootstrap.py`. It binds every validator to the captured
  fingerprint triple and validates the versioned planning schema before graph
  construction; do not transcribe capture fields into planner input.
- Treat fixes as unauthorized unless explicitly requested. Never mutate Git
  state.
- Persist compact worker payloads, compiled artifacts, routing input, graph
  plans, validation records, invalidation history, and the final manifest
  outside the reviewed repository.

## Route Compactly And Exhaustively

Use `references/routing-catalog.json` through
`scripts/review_graph_plan.py`. The planner owns catalog IDs, router IDs, rule
IDs, skill paths, priorities, and synthesis dependencies.

1. Apply the deterministic repository classifier to captured paths.
2. Run `review_graph_runtime.py routing-projection` for the consulted routers.
   Use its complete candidate list, path matches, and semantic triggers as the
   ordinary routing context. Inspect a surface `references/check-routing.md`
   only when shared ownership or ambiguity is not resolved by the projection.
   Do not load the surface orchestrator body merely to produce routing records.
3. Return sparse `routing_overrides` only for selected leaves, semantic
   additions, exact reuse, user exclusions, or blockers. Do not repeat
   catalog-owned identity fields.
4. Let `plan_from_document` expand omissions into explicit `not-applicable`
   records, select classifier-signaled repository surfaces and required
   syntheses, validate closure, and derive synthesis nodes.

Every applicable leaf remains required. The compact representation changes
serialization, not coverage. Resolve late handoffs before dependent validation
or synthesis.

## Execute Review Nodes

Dispatch each selected leaf with its exact skill and owned paths. The worker
returns only the `ReviewPayload` from the runtime contract. It does not author
fingerprints, digests, evidence IDs, execution metadata, canonical Markdown,
or machine-evidence JSON. Materialize exact dispatch bases from the accepted
plan with `review_graph_runtime.py materialize-dispatches`; do not reconstruct
planner-owned fields in prompts.

The materialized command policy is authoritative. Review nodes attest to every
command and do not execute validator-owned commands without an exact duplicate
authorization; authorized results remain explicit reusable evidence.
Exact-overlap leaves may reuse the materialized trusted read-only inspection
record, but each leaf still produces its own judgment and payload.

Run the state-verification command before and after execution. Then invoke
`scripts/review_graph_runtime.py compile-review` with the trusted dispatch,
observed states, and compact payload. Accept the node only when compilation and
the existing evidence verifier both succeed.

Use `repository-independent-review` for a concrete change target. Keep it fresh
and conclusion-blind. Its existing native result remains accepted evidence;
do not send specialist findings or synthesis context to it.
Compile its six native sections with `compile-independent-review`; the compiler
assigns graph finding/handoff identities, appends the envelope and machine
evidence, verifies adversarial-check coverage and line bounds, and emits the
metadata sidecar used by the journal and finalizer.

Fix nodes are serialized. Batch compatible fixes, recapture once per batch,
invalidate affected evidence, reroute changed surfaces, and rerun only stale or
newly applicable work. The default repair budget remains two source-mutating
epochs after the initial review barrier.

## Validate Once

Collect exact validation requirements from accepted compact payloads. Coalesce
only identical source, command or recipe, working-directory, environment,
toolchain, feature, platform, artifact, and mutation-lock identities.
Narrative request and skip wording do not force duplicate execution; the plan
retains their per-requirement provenance.

Run each coalesced unit once through `review-validator`. Validator workers also
use `fork_turns: "none"`, read only its compact graph-dispatch reference, and
return a `ValidationPayload`. Compile it with
`scripts/review_graph_runtime.py compile-validation`; accept it only when the
native and envelope gates pass. Never replay an equivalent check for another
owner. A failed validator is evidence for its owner, not a finding by itself.
For units with declared artifacts or workspace effects, provide trusted before
and after workspace snapshots. The compiler rejects unexpected outputs;
source-adjacent build intermediates require an isolated working tree.

## Synthesize From A Compact Bundle

Do not pass complete predecessor reports to a synthesis worker. Use
`scripts/review_graph_runtime.py synthesis-bundle` to create a canonical hashed
view containing only normalized findings, requirement mappings, validation
status, handoffs, limitations, and raw-artifact identities. Raw predecessor
artifacts remain in the proof store and are independently verified.

Give synthesis workers the bundle, its digest, accepted predecessor evidence
IDs, and explicit exclusions. Surface and repository synthesis reconcile this
accepted content without repeating specialist inspection.

## Complete And Report

Append verified lifecycle events with `journal-append`, then run `next-ready`
with a current capture to obtain only dependency-ready dispatches. Prefer its
runtime-managed `--output-dir` generations. Reconcile accepted handoffs before
expansion; only genuinely new triggers reroute. After an authorized repair use
`advance-after-mutation` to record the serialized repair epoch, recapture once,
move stale nodes to `awaiting-replan`, and materialize the replacement graph.
Run `finalize-proof` after every
applicable review and validation requirement has accepted non-stale evidence.
It derives the mappings, manifest, and `RepositoryReviewProof`; report complete
only when its verifier returns `complete`.

The default user report is compact: findings, changes, validation, blockers,
selected skills, proof status, final repository state, and artifact-manifest
location. Persist exhaustive lifecycle, routing, evidence, and resume views in
the proof store; render them inline only when requested or needed to explain an
incomplete result.
