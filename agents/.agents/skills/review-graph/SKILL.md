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

- **Adaptive grouped** (default): run independent read-only nodes concurrently;
  permit coordinator fallback after a worker failure.
- **Isolated**: use a fresh worker per node with declared adaptive fallback.
- **Isolated-only**: use fresh workers without fallback; emit a resume manifest
  when blocked.

Workers use `fork_turns: "none"` and receive only their dispatch, applicable
instructions/references, and result schema. Coordinator fallback uses the same
contract with `worker_created: false`.

## Capture And Authorization

- Honor repository instructions and explicit scope/base/exclusions; otherwise
  capture branch scope.
- Run `capture_scope.py` before routing and after each authorized repair batch.
- Bootstrap the capture and compact template with
  `review_graph_bootstrap.py`; do not transcribe fingerprint fields.
- Fix only when authorized and never mutate Git state.
- Keep all proof artifacts outside the reviewed repository.

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
3. Return sparse `routing_overrides` only for semantic additions, exact reuse,
   exclusions, blockers, or corrections to projection matches. Do not repeat
   catalog-owned identity fields.
4. Let `plan_from_document` select projection matches, classifier-signaled
   repository surfaces, and required syntheses; it expands other omissions to
   `not-applicable`, validates closure, and derives synthesis nodes.

Every applicable leaf remains required. Resolve late handoffs before dependent
validation or synthesis.

## Execute Review Nodes

Dispatch each selected leaf with its exact skill and owned paths. The worker
writes only the `ReviewPayload` to the dispatch-bound candidate path, invokes
the runtime-owned `persist-worker-payload` operation to validate and atomically
publish it, and returns those same bytes. It does not author
fingerprints, digests, evidence IDs, execution metadata, canonical Markdown,
or machine-evidence JSON. Materialize exact dispatch bases from the accepted
plan with `review_graph_runtime.py materialize-dispatches`; do not reconstruct
planner-owned fields in prompts.

The materialized command policy is authoritative. Review nodes attest to every
command and do not execute validator-owned commands without an exact duplicate
authorization; authorized results remain explicit reusable evidence.
Audits reference dispatched planned-validation IDs/digests instead of restating
execution identities.
Identical skill/source/scope leaves execute once; each catalog requirement
retains ownership of the coalesced judgment and evidence.

Run the capture command before and after execution. Then invoke
`scripts/review_graph_runtime.py compile-node` with the node ID, materialized
dispatch set, captures, and journal. It reads the bound payload, seals accepted
bytes at a read-only content-addressed path, and records that copy in evidence.
Do not splice a dispatch or author compiler identities. Accept only when the
compiler and evidence verifier succeed.

For a concrete change target, run `repository-independent-review` fresh and
conclusion-blind. Compile its six native sections through `compile-node`; never
send it specialist findings or synthesis context.

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
publish a schema-valid `ValidationPayload` without artifact records or digests
through `persist-worker-payload` before returning it. Invoke
`snapshot-workspace` immediately before and after execution, then compile the
node from its bound payload path with both runtime-owned snapshots. Cache/build
manifests bind metadata for every immediate entry. Accept only when both gates pass.
Never replay equivalent checks. A validator failure is owner evidence, not
itself a finding. The compiler rejects unexpected outputs;
source-adjacent build intermediates require an isolated working tree.

## Synthesize From A Compact Bundle

Use `synthesis-bundle` rather than complete predecessor reports. Give synthesis
workers its canonical hashed view, digest, accepted predecessor IDs, and
exclusions. Keep raw artifacts in the proof store.

## Complete And Report

Append verified lifecycle events with `journal-append`, then run `next-ready`
with a current capture to obtain only dependency-ready dispatches. Prefer its
runtime-managed `--output-dir` generations. Reconcile accepted handoffs before
expansion; only genuinely new triggers reroute. After an authorized repair use
`advance-after-mutation` to record the serialized repair epoch, recapture once,
move stale nodes to `awaiting-replan`, and materialize the replacement graph.
Run `finalize-proof` with the signed dispatch set and journal after every
applicable review and validation requirement has accepted non-stale evidence.
It derives the mappings, manifest, and `RepositoryReviewProof`; report complete
only when its verifier returns `complete`.

The default user report is compact: findings, changes, validation, blockers,
selected skills, proof status, final repository state, and artifact-manifest
location. Persist exhaustive lifecycle, routing, evidence, and resume views in
the proof store; render them inline only when requested or needed to explain an
incomplete result.
