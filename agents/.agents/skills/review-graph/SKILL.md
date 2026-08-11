---
name: review-graph
description: "Execute complete mixed-surface repository reviews as an auditable graph of isolated skill workers with exhaustive C++/Rust/Python/tooling/documentation routing, exact skill-path proof, coalesced validation, independent change review, bounded resumable epochs, late-handoff closure, and repository synthesis. Use for branch, PR, staged, release-readiness, whole-repository baseline, fix-all, or review-and-fix work spanning multiple repository surfaces; use a focused skill directly for one narrow surface."
---

# Review Graph

Act only as the graph coordinator. Capture scope, obtain exhaustive routing,
plan every applicable skill, dispatch fresh workers, preserve raw evidence, and
enforce completion. Never replace an isolated worker with coordinator analysis.

Read these references completely before their corresponding phase:

- before planning: [bounded planning](references/planning-contract.md) and
  [execution feasibility](references/execution-feasibility.md)
- before routing: [routing handoff](references/routing-handoff.md); use
  [routing catalog](references/routing-catalog.json) through the planner
- before dispatch: [node contract](references/node-contract.md)
- before finalization: [report contract](references/report-contract.md) and
  [replacement acceptance](references/migration-acceptance.md)

Use `scripts/capture_scope.py` for source capture and
`scripts/review_graph_plan.py` for catalog validation, graph planning, epochs,
acceptance, resume, and completion decisions.

## Guarantees

- Create every node in a fresh worker with no inherited turns; use
  `fork_turns: "none"` when supported.
- Invoke exactly one skill per worker and never reuse a completed worker.
- Require the planned absolute skill path, matching frontmatter name, required
  reference paths, and complete native report. Require matching before/after
  fingerprints for completed or no-findings read-only nodes, the recorded
  blocker identity for blocked nodes, and the expected pre-edit identity plus
  changed-as-reported post-edit identity for authorized fix nodes.
- Preserve complete worker reports unchanged outside the reviewed repository in
  a coordinator-owned journal.
- Keep audit, validation, independent-review, synthesis, and revalidation nodes
  source-read-only. Edit only in authorized fix nodes and never concurrently.
- Do not mutate Git state unless explicitly requested.
- Describe routers as consulted, not executed skills.

## 0. Preflight Capability

1. Inspect only authoritative aggregate worker-capacity metadata. Never probe
   capacity with a dummy worker or a surface exposing other task content.
2. Require fresh no-inherited-turn workers and one free slot. Treat known zero
   creation capacity as blocked; treat unavailable lifetime telemetry as
   unknown, not unlimited.
3. Verify that catalog-routed independent, specialist, and synthesis skills
   resolve through the routing catalog. Resolve `review-validator` separately
   through the planner's approved skill-root path and frontmatter check.
4. Choose a positive per-root worker budget, defaulting to 24, and reserve at
   least one creation for recovery/finalization. Increase the reserve for fixes
   and reruns.
5. If capability cannot start the first epoch, report blocked without loading
   routers or performing a substitute review.

## 1. Capture Scope

1. Read repository instructions and determine review-only versus authorized
   review-and-fix behavior.
2. Default to branch scope: compare to the explicit PR/base or inferred default
   branch and include committed branch changes plus staged, unstaged, and
   untracked work.
3. Use staged-only or changed-file-only only when explicitly requested. Use
   baseline only for an explicit whole-repository review, including tracked
   files when the worktree is clean.
4. For release readiness, keep code/tooling branch scope but expand the docs
   slice to every tracked active document, excluding designated archives unless
   requested.
5. Run `capture_scope.py`, then retain scope, worktree, and repository-state
   fingerprints and the exact verification command. Map staged-only to
   `staged`, changed-worktree-only to `worktree`, PR/release code scope to
   `branch`, and whole-repository scope to `baseline`.
6. Recheck all fingerprints before and after each node. Stop, invalidate,
   recapture, and replan after unexpected state changes.

## 2. Close Repository And Surface Routing

1. Request `repo-review` in `graph-routing` mode for every repository catalog
   entry. Compare its surface decisions with the planner's conservative path
   classifier and resolve every conflict.
2. Request graph-routing mode from every selected C++, Rust, Python, or docs
   router. `project-tooling-review` is a direct leaf.
3. Require one decision per candidate in every consulted router catalog. Reject
   silence, duplicates, unknown skills, path/frontmatter mismatches, missing
   rules/evidence, missing owners, or absent required references.
4. Select specialists from observed contracts, not merely extensions. Retain
   all shared-file owners. Apply deterministic guards such as packaged Python
   requiring `python-build-portability`.
5. Select `repository-independent-review` for every concrete change target and
   mark it not applicable only for a pure whole-repository baseline.
6. Select every applicable language synthesis and always select
   `repository-production-review` for final reconciliation.

Do not permit routers to budget-defer applicable work. `not-applicable`, exact
verified reuse, and explicit user exclusion are non-execution dispositions;
capability-blocked and failed dispositions make the graph incomplete.

## 3. Plan The Complete Required Graph

Before creating a worker:

1. Convert every selected leaf disposition into a required worker commitment.
2. Coalesce only identical skill paths, scopes, references, synthesis owners,
   and compatible validator identities. Preserve every requirement and owner.
3. Add one required baseline `review-validator` unit, selected language
   syntheses, independent review, repository synthesis, planned fixes, and
   affected revalidations.
4. Topologically schedule the complete graph. Partition it into deterministic
   per-root epochs whose nodes plus reserve do not exceed the effective budget.
   Never remove an applicable skill to make an epoch fit.
5. Show the complete node count, epoch boundaries, required fresh-root
   continuations, routing closure, exact skill paths, validator mappings,
   synthesis dependencies, and reserve before dispatch.

An unfinished epoch or required future epoch keeps the result incomplete. A
fresh root may resume accepted evidence only when all three fingerprints still
match; otherwise recapture and replan.

## 4. Dispatch And Accept

For each dependency-ready node in the current epoch:

1. Recheck fingerprints and remaining per-root capacity.
2. Fill the exact mode prompt in `node-contract.md`. Pass only task-local input.
   Never leak specialist conclusions to audit, validation, or independent
   review nodes.
3. Journal the attempt, create one fresh worker, and wait for its result before
   reusing shared capacity. Preserve its complete native report.
4. Independently rerun state verification and apply the acceptance gate.
5. Accept timed-out work only when a complete conforming report arrived and all
   normal isolation, path, reference, scope, and fingerprint proofs pass.
6. Map validation reuse only when command, configuration, environment,
   artifact, selection, and fingerprints match exactly and a graph validator
   verifies it.

On worker-creation failure, stop dispatch, preserve completed reports, and emit
the exact resume manifest. Mark the failed and later nodes blocked before
execution. Never claim that another attempt in the same root resets capacity.

## 5. Reopen Routing From Discoveries

After every accepted audit or independent-review result:

1. Validate each routing handoff by catalog ID and evidence.
2. Re-run the owning router ledger when a handoff changes applicability.
3. Add newly selected nodes before dependent synthesis, preserving completed
   evidence and recomputing epochs.
4. Block synthesis while any handoff is unknown or unresolved.

After every authorized fix, recapture fingerprints, invalidate affected audit,
validation, independent-review, and synthesis evidence, and rerun repository
and affected surface routing. A fix that creates a new surface creates its
applicable worker nodes.

## 6. Synthesize And Fix

Run each language production-review skill in a fresh synthesis-only worker after
all of its leaves and validators are accepted. Do not rerun specialist analysis.

Run `repository-production-review` only after repository/surface routing is
closed and all language, docs, tooling, validation, independent-review, and
epoch evidence is accepted. Give it complete predecessor reports and mappings;
it may not capture, route, validate, edit, or create workers.

For authorized fixes:

1. Finish the read-only graph and assign each finding one owner.
2. Run one fresh single-skill fix worker at a time.
3. Recapture, reroute, and invalidate affected evidence after every edit.
4. Run coalesced validation, owner revalidation, fresh independent review, and
   affected syntheses.
5. Stop at the declared iteration limit or a recorded blocker.

## 7. Report

Use `report-contract.md`. Include the exhaustive routing ledger, classifier
signals and conflict resolutions, exact skills/paths/references, complete graph
and epoch lifecycle, exact reuse and user exclusions, unresolved blockers,
findings and changes, validation mappings, raw artifacts, resume manifest, and
final repository state.

Derive the legacy `Review Evidence` rows for tooling, C++, Rust, Python, and
documentation from graph evidence so `repo-review` callers retain a familiar
summary.

Report `complete` only when the planner's completion gate passes: no applicable
requirement was skipped, no future epoch or node remains, routing and handoffs
are closed, post-change routing was revalidated, required validation,
independent review, and synthesis are accepted, fingerprints match, isolation
has no failure, and the final report reconciles. Otherwise lead with
`incomplete` and the exact resumption work.
