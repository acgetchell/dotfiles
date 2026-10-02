---
name: review-graph
description: "Coordinate provenance-preserving mixed-surface repository reviews across C++, Rust, Python, tooling, and documentation. Capture one source state, route every applicable specialist, run fresh-context review nodes, validate exact requirements, and compile persisted evidence into one verified repository proof. Use for branch, PR, staged, release-readiness, whole-repository, fix-all, or review-and-fix work spanning multiple surfaces."
---

# Review Graph

Cover every applicable focused review. Reviewers make semantic judgments;
scripts own catalog identity, fingerprints, digests, canonical artifacts,
evidence envelopes, and proof reconciliation.

Read [the runtime contract](references/runtime-contract.md). Execute scripts;
inspect implementations only for failures or requested changes.

## Profiles

- **Adaptive grouped** (default): run read-only nodes concurrently across worker
  and coordinator lanes; permit worker-failure fallback.
- **Isolated**: fresh worker per node with declared adaptive fallback.
- **Isolated-only**: fresh workers without fallback; resume manifest when blocked.

`fork_turns: "none"` workers receive only dispatch, applicable
instructions/references, and result schema. Coordinator execution records
`worker_created: false`, `fresh_context: false` under the same contract.

## Capture And Authorization

- Honor repository instructions and explicit scope/base/exclusions; otherwise
  capture branch scope.
- Run `capture_scope.py` before routing and after each authorized repair batch.
- Bootstrap the capture and compact template with
  `review_graph_bootstrap.py`; follow its compact receipt and `next_command`.
  Keep full proof artifacts on disk; use `--full-output` only for diagnosis.
- Fix only when authorized and never mutate Git state.
- Keep all proof artifacts outside the reviewed repository.

## Route Compactly And Exhaustively

Use `references/routing-catalog.json` through `scripts/review_graph_plan.py`,
which owns catalog/router/rule IDs, skill paths, priorities, and synthesis dependencies.

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

For requested TypeSafe comparisons, follow
[the shadow experiment](references/routing-experiment.md). Freeze ordinary routing
first; preserve its decisions and proof gates.

## Execute Review Nodes

Dispatch selected leaves with exact skills and owned paths. Workers stream
`ReviewPayload` audit bytes or `SynthesisPayload` synthesis bytes through dispatch-bound review and persistence
commands; the runtime validates before writing, binds approval retries, and
atomically publishes. They return the publication receipt; `compile-node` reads
the bound bytes without a second conversational copy. Audit and synthesis workers do not author
fingerprints, digests, evidence IDs, execution metadata, canonical Markdown,
or machine-evidence JSON. Materialize dispatch bases from the accepted plan
with `review_graph_runtime.py materialize-dispatches`; never reconstruct planner-owned fields.

The materialized command policy is authoritative. Review nodes attest to every
command and do not execute validator-owned commands without an exact duplicate
authorization; authorized results remain explicit reusable evidence.
Audits reference dispatched planned-validation IDs/digests instead of restating
execution identities.
Identical skill/source/scope leaves execute once; each catalog requirement
retains ownership of the coalesced judgment and evidence.

Capture before and after execution. Invoke
`scripts/review_graph_runtime.py compile-node` with the node ID, materialized
dispatch set, captures, and journal. It reads the bound payload, seals accepted
bytes at a read-only content-addressed path, and records that copy in evidence.
Do not splice a dispatch or author compiler identities. Accept only when the
compiler and evidence verifier succeed.

For a concrete change target, run `repository-independent-review` fresh and
conclusion-blind. It supplies structured judgments and observed fingerprints;
the compiler renders native sections and verifies them through `compile-node`.
Never send it specialist findings or synthesis context.

Fix nodes are serialized. Batch compatible fixes, recapture once per batch,
invalidate affected evidence, reroute changed surfaces, and rerun only stale or
newly applicable work. The default repair budget remains two source-mutating
epochs after the initial review barrier.

## Validate Once

Before worker fanout, run the runtime's `preflight-validation` for command policy
(including nested fixtures), executor caches, hosted obligations, and concrete
output paths. Resolve launch blockers or retain explicit blocked evidence.
See [runtime contract](references/runtime-contract.md#materialize-and-schedule).

Collect exact validation requirements from accepted compact payloads. Coalesce
only identical source, command or recipe, working-directory, environment,
toolchain, feature, platform, artifact, and mutation-lock identities.
Narrative request and skip wording do not force duplicate execution; the plan
retains their per-requirement provenance.

Run each coalesced unit once through `review-validator`. Validator workers also
use `fork_turns: "none"`, read only its compact graph-dispatch reference, and
publish a schema-valid `ValidationPayload` without artifact records or digests
through the same reviewed persistence flow before returning it. Invoke
`snapshot-workspace` immediately before and after execution, then compile the
node from its bound payload path with both runtime-owned snapshots. Cache/build
manifests bind metadata for every immediate entry. Accept only when both gates pass.
Never replay equivalent checks. A validator failure is owner evidence, not
itself a finding. The compiler rejects unexpected outputs;
source-adjacent build intermediates require an isolated working tree.
For a proven failure before checks start, `recover-validation-launch` permits
one attempt after an explicit remedy, preserving accepted work and the failure.
Follow its returned continuation configuration; see
[state transitions](references/state-transitions.md).

## Synthesize From A Compact Bundle

Give synthesis workers the `synthesis-bundle` canonical hashed view, digest,
accepted predecessor IDs, and exclusions. Keep complete predecessor reports and
raw artifacts in the proof store.

## Complete And Report

Journal verified lifecycle events with `journal-append`. With a current capture,
use `schedule-ready` for grouped/mixed lanes or `next-ready` for isolated dispatches;
follow returned continuations. `next-ready --output-dir` creates immutable generations.
Reconcile accepted handoffs before expansion; only new triggers reroute. After an authorized repair use
`advance-after-mutation` to record the serialized repair epoch, recapture once,
move stale nodes to `awaiting-replan`, and materialize the replacement graph.
For external staging with unchanged
content, use `resume-after-external-metadata` and its returned continuation;
preserve both Git captures and the user's index. See the runtime contract for
partition dependencies, Git-sensitive revalidation, and source provenance.
Run `finalize-proof` with the signed dispatch set and journal after every
applicable review and validation requirement has accepted non-stale evidence.
It derives the mappings, manifest, and `RepositoryReviewProof`; report complete
only when its verifier returns `complete`. Report repository readiness from
typed synthesis separately from proof completeness and validation success.

Report findings, changes, validation, blockers, selected skills, proof status,
final repository state, and artifact-manifest location compactly. Keep exhaustive
lifecycle, routing, evidence, and resume views in the proof store; show them only
when requested or needed to explain incompleteness.

Report stage costs as measured, estimated, or unavailable using
[graph accounting](references/routing-experiment.md#account-for-the-whole-graph).
Set external `REVIEW_GRAPH_USAGE_LEDGER` for runtime timings; preserve unknown
counts and failed/unfinished attempts.
