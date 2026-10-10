---
name: review-graph
description: "Coordinate an exhaustive review across code, tooling, and docs with isolated judgments and a verified evidence record."
---

# Review Graph

Cover every applicable focused review; scripts own evidence identity and
reconciliation.

Read [the runtime contract](references/runtime-contract.md). Execute scripts;
inspect implementations only for failures or requested changes.

For PRs or platform-sensitive changes, apply
[platform/CI gates](references/platform-ci-review.md) before routing and final
reporting; missing skill reads or CI inspection block completion.

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
- Bootstrap capture and template with
  `review_graph_bootstrap.py`; follow its compact receipt and `next_command`.
  Branch `just ci`: [starter](references/bootstrap-starter.md).
  Keep full proof artifacts on disk; use `--full-output` only for diagnosis.
- Fix only when authorized and never mutate Git state.
- Keep all proof artifacts outside the reviewed repository.

## Route Compactly And Exhaustively

Use `references/routing-catalog.json` through `scripts/review_graph_plan.py`,
which owns catalog/router/rule IDs, skill paths, priorities, and synthesis dependencies.

1. Apply the deterministic repository classifier to captured paths.
2. Run `review_graph_runtime.py routing-projection` for the consulted routers.
   Inspect its candidates, path matches, and semantic triggers. Inspect a surface `references/check-routing.md`
   only when shared ownership or ambiguity is not resolved by the projection.
   Do not load orchestrator bodies for routing.
3. Inspect the affected contracts and return `routing_overrides` for each matched
   specialist: select it, justify `not-applicable`, reuse exact evidence, or record
   an exclusion/blocker. Include semantic additions even without path matches.
   Do not repeat catalog-owned identity fields or select a whole language suite
   from file extensions alone.
4. The planner rejects unassessed path-matched specialists. It retains mandatory
   classifier surfaces, independent review, and syntheses, expands unmatched
   omissions to `not-applicable`, and verifies exhaustive closure.

Every applicable leaf remains required; resolve late handoffs before dependent work.

Run the dormant [TypeSafe experiment](references/routing-experiment.md) only when
requested. Freeze ordinary routing first; preserve its decisions and proof gates.

## Execute Review Nodes

Dispatch selected leaves with exact skills and owned paths. Workers publish
`ReviewPayload` audits or `SynthesisPayload` syntheses through dispatch-bound
commands. The runtime validates, binds approval retries, and atomically persists
their bytes. Return publication receipts; `compile-node` reads persisted payloads.
Workers never author fingerprints, digests, evidence IDs, execution metadata,
canonical Markdown, or machine-evidence JSON. Use
`review_graph_runtime.py materialize-dispatches` for planner-owned dispatches.

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

Serialize compatible fixes; apply authorized repository formatting before the
batch's final capture. Invalidate affected evidence, reroute changed surfaces,
and rerun stale or newly applicable work. Default to two source-mutating repair
epochs after the initial review barrier.

At repair boundaries, follow [repair validation](references/repair-validation.md)
to schedule cheap canonical checks before affected review fanout.

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
Reuse equivalent checks when permitted. A required final gate may follow focused
red/green checks with a recorded reason for overlap; keep one owner for each
exact planned execution and do not count repeated coverage as independent. A validator failure is owner evidence, not
itself a finding. The compiler rejects unexpected outputs;
source-adjacent build intermediates require an isolated working tree.
`recover-validation-launch` handles failures before checks start;
`recover-validation-execution` handles permission denials during a failed
aggregate. Both preserve evidence and permit one remedied attempt per node/source.
Follow [continuations](references/state-transitions.md) and declare
[executor permissions](references/validation-preflight.md).

## Synthesize From A Compact Bundle

Give synthesis workers the `synthesis-bundle` canonical hashed view, digest,
accepted predecessor IDs, and exclusions. Keep complete predecessor reports and
raw artifacts in the proof store.

## Complete And Report

Journal verified lifecycle events with `journal-append`. With a current capture,
use `schedule-ready` for grouped/mixed lanes or `next-ready` for isolated dispatches;
follow returned continuations. `next-ready --output-dir` creates immutable generations.
Reconcile accepted handoffs before expansion; only new triggers reroute. Use
`advance-after-mutation` after authorized repairs to recapture, invalidate stale
nodes, and materialize the replacement graph.
For external staging with unchanged content, use `resume-after-external-metadata`.
Declare semantic `git_dependencies` to preserve source-discovery audits; follow
its continuation and [state transitions](references/state-transitions.md).
Retain both Git captures and the user's index.
Run `finalize-proof` with the signed dispatch set and journal after every
applicable review and validation requirement has accepted non-stale evidence.
It derives the mappings, manifest, and `RepositoryReviewProof`; report complete
only when its verifier returns `complete` and the platform/CI gate is reconciled.
Proof completeness does not establish CI inspection. Report repository readiness from
typed synthesis separately from proof completeness and validation success.

Report findings, changes, validation, blockers, skills, proof status, repository
state, and manifest location. Keep exhaustive evidence in the proof store.

Report stage costs as measured, estimated, or unavailable using
[graph accounting](references/routing-experiment.md#account-for-the-whole-graph).
Set external `REVIEW_GRAPH_USAGE_LEDGER` for runtime timings; preserve unknown
counts and failed/unfinished attempts.
