---
name: review-graph
description: "Execute complete mixed-surface repository reviews across C++, Rust, Python, tooling, and documentation with an auditable evidence ledger. Default to a delivery-first grouped profile that runs the applicable surface orchestrators and returns findings; use the isolated one-skill-per-worker graph only when the user explicitly requests isolation and the runtime proves it is feasible. Use for branch, PR, staged, release-readiness, whole-repository baseline, fix-all, or review-and-fix work spanning multiple repository surfaces."
---

# Review Graph

Deliver a useful repository review. A routing ledger or worker plan is not a
review result. Do not spend the task constructing an execution graph that the
runtime cannot run.

## Choose The Execution Profile First

Choose exactly one profile before repository capture or exhaustive routing:

- **Grouped delivery** is the default for ordinary `$review-graph` and
  `$repo-review` requests. Run the applicable tooling, language, and
  documentation orchestrators sequentially and return their actual findings,
  validation, and evidence.
- **Isolated** is an explicit preference requested with `isolated`,
  `isolated-graph`, or equivalent wording. Use it only when fresh
  no-inherited-turn workers and safe aggregate capacity metadata are available.
  Fall back to grouped delivery when the gate fails, and state why.
- **Isolated-only** is an explicit hard requirement. Block instead of falling
  back when its capability gate fails.

Use `select_execution_profile` from
`scripts/review_graph_plan.py` when evaluating an isolation request. Never call
an agent listing or status surface that can expose task reports merely to decide
the profile. Missing safe capacity telemetry selects grouped delivery; it does
not block the review.

Announce the selected profile in one sentence. Do not present the complete
isolated node graph unless isolated execution actually passed its gate.

## Shared Scope And Safety

- Read repository instructions before reviewing or editing.
- Do not mutate Git state unless the user explicitly requests it.
- Default to branch scope. Use staged-only or changed-file-only only when
  explicitly requested. Use baseline scope for an explicit whole-repository
  review and inventory tracked files even when the worktree is clean.
- For release readiness, keep code and tooling branch-scoped while expanding
  documentation to every tracked active document outside designated archives.
- Treat fixes as unauthorized unless the user explicitly requests them.
- Maintain one validation ledger keyed by source state, exact selection,
  environment, configuration, and artifact. Do not replay equivalent checks.
- Recheck repository state after every editing pass. Stop and recapture when an
  unexpected change invalidates the established scope.

## Grouped Delivery Profile

Read these files completely:

1. [`repo-review/references/check-routing.md`](../repo-review/references/check-routing.md)
2. [`repo-review/references/legacy-grouped-review.md`](../repo-review/references/legacy-grouped-review.md)

Then:

1. Establish the requested scope with read-only Git discovery. For baseline
   mode, count tracked files by surface and hand each selected orchestrator its
   complete relevant inventory.
2. Select the smallest complete set from `project-tooling-review`,
   `cpp-review-orchestrator`, `rust-review-orchestrator`,
   `python-review-orchestrator`, and `docs-review-orchestrator`. Preserve all
   owners for shared manifests, workflows, recipes, and documentation.
3. Emit a compact dispatch note naming selected and skipped orchestrators,
   reasons, scope, and order.
4. Read every selected orchestrator's complete `SKILL.md` and follow its grouped
   pass order. Run selected orchestrators sequentially in the coordinator
   context. A safe worker may host one complete surface orchestrator when that
   is useful, but workers are not required and unavailable worker capacity must
   never suppress the review.
5. Require each selected orchestrator to record the focused skills and
   references it actually loaded, scope inspected, findings or explicit
   no-finding outcomes, fixes, validation, and unresolved handoffs.
6. Continue with independent surfaces when one surface is blocked, unless its
   blocker makes the repository state unreliable for later work. Report partial
   evidence instead of discarding completed review work.
7. Resolve cross-surface handoffs and run only validation absent from the shared
   ledger. For review-and-fix work, rerun every affected owner and validator
   after edits.

Grouped delivery is complete when every selected orchestrator returned grouped
evidence or an explicit blocker, every handoff is resolved or visible, required
validation is accounted for, and the final `Review Evidence` table reconciles.
Do not describe grouped evidence as isolated.

## Isolated Profile

Use this profile only after the explicit isolation capability gate passes. Read
these references completely before their corresponding phase:

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

### Isolated Guarantees

- Create every node in a fresh worker with no inherited turns and invoke exactly
  one skill per worker. Never reuse a completed worker for a later node.
- Preserve complete worker reports unchanged outside the reviewed repository.
- Keep audit, validation, independent-review, synthesis, and revalidation nodes
  source-read-only. Edit only in authorized fix nodes and never concurrently.
- Require exact skill paths, references, scope, fingerprints, and native report
  contracts before accepting a node.
- Treat routers as coordinator-side authorities, not executed review skills.

### Isolated Execution

1. Pass the early capability gate before capture or router loading. If it fails,
   select grouped delivery unless the request is isolated-only.
2. Capture the exact scope and its scope, worktree, and repository-state
   fingerprints.
3. Obtain exhaustive repository and surface routing ledgers. Convert every
   applicable leaf, validator, independent check, and synthesis requirement to
   a planned node without budget-skipping coverage.
4. Partition the complete graph into bounded epochs while preserving a recovery
   reserve. A future epoch keeps isolated completion incomplete.
5. Dispatch dependency-ready nodes one at a time with the exact node contract.
   Recheck fingerprints and remaining safe capacity before every dispatch.
6. After accepted discoveries or authorized fixes, rerun affected routing,
   invalidate stale evidence, and replan before dependent synthesis.
7. Run language and repository synthesis only after their required predecessor
   evidence is accepted.

If worker creation or safe capacity fails before the first accepted node,
discard the plan-only work and run grouped delivery unless the request is
isolated-only. If it fails later, preserve accepted isolated reports as
supplemental evidence, run complete grouped surface passes for the applicable
scope, and label the final profile `grouped with partial isolated evidence`.
Never return only a resume manifest when grouped delivery remains possible.

Report isolated completion only when every required node, validator, synthesis,
fingerprint, routing handoff, and epoch passes the planner's completion gate.

## Final Report

Lead with findings and blockers, not orchestration statistics. State the
execution profile and whether the review is complete for that profile. Include:

- actionable findings with severity, location, evidence, and remediation
- changes made and why, or confirmation that review-only authorization was
  preserved
- validation commands and results without duplicate executions
- unresolved risks, blocked surfaces, and intentionally skipped work
- exact skills and references actually loaded
- a `Review Evidence` table with one row for each tooling, C++, Rust, Python,
  and documentation orchestrator
- final repository and Git-state status

For isolated or mixed evidence, additionally include the worker lifecycle,
accepted nodes, isolation failures, and incomplete epochs required by
`report-contract.md`. Never imply that planning, routing, or skill-file reading
constituted an executed review.
