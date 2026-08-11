# Complete Review Graph Planning

This contract applies only to the explicit isolated execution profile. Grouped
delivery uses the surface-orchestrator workflow and validation ledger instead;
it does not create one fresh worker per specialist or partition worker epochs.

Read this contract before creating any worker. Use
`scripts/review_graph_plan.py` as the deterministic authority for routing
closure, path validation, coalescing, epochs, acceptance, resume, and completion.

## Contents

- [Routing Inputs](#routing-inputs)
- [Worker Budget And Epochs](#worker-budget-and-epochs)
- [Node And Validation Identity](#node-and-validation-identity)
- [Scheduling And Discovery](#scheduling-and-discovery)
- [Failure And Resume](#failure-and-resume)
- [Completion Gate](#completion-gate)
- [Deterministic Dry Run](#deterministic-dry-run)

## Routing Inputs

Load `routing-catalog.json` under one or more approved skill roots. Validate for
every catalog entry:

- unique catalog ID, router ID, and rule ID
- known layer, target kind, and priority
- one existing skill path inside an approved root
- frontmatter `name` equal to the declared skill ID
- existing required static references
- at least one semantic trigger

Obtain one routing decision per entry owned by every consulted router. Reject
missing, duplicated, unknown, or unconsulted entries. Require decisions to
match the catalog router, rule, skill, and resolved path exactly.

Selected leaves require a concrete scope, evidence, reason, priority, owners,
references, validators, and synthesis dependency. Convert every selected leaf
to a required worker commitment. Convert a selected independent target to an
`independent-review` node. Selected synthesis catalog entries must match the
declared synthesis skill set exactly.

Allowed dispositions are:

- `selected`: execute a required worker
- `not-applicable`: inspected trigger did not apply
- `exact-evidence-reused`: current graph validator verified an exact report;
  require an evidence ID
- `user-excluded`: outside the user's explicit scope; retain as a limitation
- `budget-deferred`, `capability-blocked`, or `failed`: completion-blocking

Routers do not own budgeting. Treat a router's `budget-deferred` decision as a
blocker and schedule applicable work through graph epochs instead.

## Worker Budget And Epochs

Use a positive per-root fresh-worker budget, defaulting to 24, and reserve at
least one creation for recovery/finalization. When authoritative lifetime
capacity is known, use its lower ceiling for the current root. Missing lifetime
telemetry is unknown, not unlimited.

Plan the complete graph before dispatch. All selected leaves, required
validators, independent review, syntheses, planned fixes, and revalidations
remain in that graph. Partition the topological schedule into epochs satisfying:

```text
nodes in one epoch + recovery/finalization reserve <= effective root budget
```

Do not delete or reclassify applicable nodes to fit. Priority controls order
within dependency constraints, never coverage. A graph with later epochs is
valid to start but remains incomplete until every epoch finishes. Each later
epoch records that a fresh root may be required.

Persist:

- configured/effective budget and reserve
- complete node count and dependency graph
- every epoch and node ID
- current/future root requirements
- routing ledger and requirement-to-node mapping
- validation units and synthesis dependencies

## Node And Validation Identity

Keep these concepts separate:

- routing catalog candidate
- exhaustive routing decision
- selected review requirement
- coalesced worker node
- validation requirement and coalesced validation unit
- exact evidence-reuse mapping
- synthesis node
- execution epoch

Coalesce review requirements only when all of these match:

```text
skill ID and resolved absolute path
mode and exact review surface
instruction and static-reference paths
synthesis dependency
compatible ownership
```

Retain every router/rule/requirement/owner on the coalesced node.

Coalesce validation only when all of these match:

```text
scope/worktree/repository-state fingerprints
exact commands or canonical recipe
working directories
environment and toolchain
features/configuration and platform
artifact owner
mutation/locking compatibility
```

Map every validation requirement to exactly one unit and accepted execution or
verified reuse. A failed validator is evidence for its owning reviewer, not an
automatic review finding.

Require at least one baseline validator. Require all applicable language
production syntheses, `repository-independent-review` for concrete change
targets, and `repository-production-review` for final broad reconciliation.

## Scheduling And Discovery

Topologically order nodes, using priority only among ready nodes:

1. `required-routing-synthesis`
2. `correctness-invariants`
3. `required-validation`
4. `supporting-quality`
5. `optional-hygiene`

Every selected applicable leaf is required even when its priority is
`optional-hygiene`.

Before and after every dispatch, verify all three source fingerprints. After an
accepted audit or independent result, validate every routing handoff. A handoff
is closed only when its catalog decision becomes selected, exact-reused, or
explicitly user-excluded. Replan the complete remaining graph and epochs before
dependent synthesis.

After an authorized fix, recapture fingerprints, invalidate affected reports,
rerun repository and affected surface routers, add newly applicable skills, and
rerun affected validation, independent review, and synthesis. Record stale and
replacement evidence rather than overwriting history.

## Failure And Resume

Stop creating workers after the first creation failure or exhausted current
epoch. Preserve completed raw reports and emit a manifest containing:

```text
captured fingerprints and verification command
catalog version and exhaustive routing ledger
complete graph and current/future epochs
failed attempt and capacity evidence
accepted nodes and immutable raw-report locations
undispatched/unaccepted nodes with exact skill paths and dependencies
outstanding validation mappings and syntheses
unresolved handoffs and post-fix routing state
```

Never substitute same-context analysis or a completed worker. A later root may
resume only after matching all fingerprints and revalidating routing closure.
If fingerprints changed, recapture and replan.

Accept a result after its elapsed cap only when the complete native report
arrived and every ordinary isolation, skill, reference, structure, and
fingerprint check passes.

## Completion Gate

Report `complete` only when:

- every selected applicable requirement completed or has exact verified reuse
- no applicable requirement appears only as a meaningful/budget skip
- every consulted catalog is exhaustive and path-valid
- no budget-deferred, capability-blocked, or failed routing disposition remains
- every late handoff is resolved
- routing was rerun after every surface-changing fix
- every epoch and selected node completed and was accepted
- required documentation/citation coverage completed
- baseline and all required validation completed
- applicable language and repository synthesis completed
- required independent review completed for a concrete change
- all accepted reports have matching source fingerprints and no isolation
  failure
- final findings, changes, validation, and lifecycle ledgers reconcile

`not-applicable`, exact verified reuse, and explicit user exclusion are routing
dispositions, not executed skills. User exclusion may yield complete only for
the explicitly narrowed request and must remain visible in limitations.

## Deterministic Dry Run

Use a portable JSON input whose skill paths are `$SKILLS_ROOT/...` or exact
absolute paths. Prefer exhaustive `consulted_routers` plus `routing_decisions`;
legacy `review_requirements` are accepted only for isolated planner fixtures.

Use a repository-owned `just` recipe when one wraps this dry run. Otherwise,
run the following from `agents/.agents/skills/review-graph`:

```sh
uv run --locked python scripts/review_graph_plan.py \
  --input scripts/fixtures/representative_rust_python_docs.json \
  --catalog references/routing-catalog.json \
  --skill-root ..
```

The output must show the complete worker graph, resolved skill paths,
requirement mappings, validation units, execution epochs, routing closure, and
continuation requirements. Run the planner tests and surface-routing matrix
before relying on changed routing behavior.
