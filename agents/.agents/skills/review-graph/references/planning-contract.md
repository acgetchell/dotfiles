# Complete Review Graph Planning

This is a maintainer-facing planner specification. Ordinary review execution
uses `runtime-contract.md` and the planner CLI; do not load this file unless
changing planning behavior or diagnosing a rejected plan.

Use this contract to build the complete evidence graph for every execution
profile. Adaptive grouped execution may place a node in a worker or the
coordinator; isolated execution additionally partitions fresh-worker epochs.

Read this contract before creating any worker. Use
`scripts/review_graph_plan.py` as the deterministic authority for routing
closure, path validation, coalescing, epochs, acceptance, resume, and completion.

## Contents

- [Routing Inputs](#routing-inputs)
- [Worker Budget And Epochs](#worker-budget-and-epochs)
- [Hard Deadline Contract](#hard-deadline-contract)
- [Node And Validation Identity](#node-and-validation-identity)
- [Scheduling And Discovery](#scheduling-and-discovery)
- [Failure And Resume](#failure-and-resume)
- [Completion Gate](#completion-gate)
- [Deterministic Dry Run](#deterministic-dry-run)

## Routing Inputs

`references/schemas/planning-input-v1.schema.json` is the versioned public
input schema. Build it with `scripts/review_graph_bootstrap.py`, which merges the
trusted `capture_scope.py` manifest, binds every validation requirement to the
captured fingerprint triple, and returns aggregate JSON-path diagnostics before
planning. Do not discover required capture fields by retrying planner failures.

Load `routing-catalog.json` under one or more approved skill roots. Validate for
every catalog entry:

- unique catalog ID, router ID, and rule ID
- known layer, target kind, and priority
- one existing skill path inside an approved root
- frontmatter `name` equal to the declared skill ID
- existing required static references
- at least one semantic trigger

Accept sparse semantic `routing_overrides` from consulted routers. Expand them
deterministically into one routing decision per owned catalog entry before
closure validation. The planner derives router, rule, skill, resolved path,
priority, requirement, and synthesis identity; sparse inputs containing those
catalog-owned fields are rejected. After expansion, reject missing, duplicated,
unknown, unconsulted, or mismatched entries exactly as before.

Selected leaves require a concrete scope, evidence, reason, priority, owners,
references, validators, and synthesis dependency. Convert every selected leaf
to a required review commitment. Convert a selected independent target to an
`independent-review` node. Preserve an `exact-evidence-reused` leaf or
independent target as typed non-executable evidence with its exact
requirement-to-evidence mapping; do not create a worker node for it. Selected
synthesis catalog entries must match the declared synthesis skill set exactly.

For exhaustive routing documents, normalize `captured_paths` and every
`review_surface` as portable repository-relative paths. Every selected or
exact-evidence-reused leaf and independent surface must be contained in the
captured path set. Apply the same containment rule to declared additional-node
coverage, which represents repository paths; reject traversal, absolute paths,
normalized duplicates, and out-of-scope coverage before dispatch. Parse every
document Boolean as an exact JSON Boolean and reject strings, numbers, and
nulls rather than coercing their truthiness.

For every selected or exactly reused independent-review path, record a
trusted-capture `captured_path_line_bounds` entry derived from the bytes covered
by the captured source identity. Before planning, independently recapture the
exact repository root, mode, base ref, pathspecs, and source state; reject the
document if any capture identity or declared line bound differs. Use the current
captured side for present files, the captured base side for deleted files, and
the greatest addressable line across the inspected sides when both are relevant;
use zero only for a repository-level or otherwise non-line-bearing path. Reject
missing, duplicate, negative, non-integer, or out-of-scope entries. Carry this
ordered path/bound tuple in the plan digest and independent evidence
expectation; a caller or result artifact cannot supply, substitute, or enlarge
it.

Allowed dispositions are:

- `selected`: applicable required review work, regardless of executor
- `not-applicable`: inspected trigger did not apply
- `exact-evidence-reused`: current graph validator verified an exact report;
  require an evidence ID
- `user-excluded`: outside the user's explicit scope; retain as a limitation
- `budget-deferred`, `capability-blocked`, or `failed`: completion-blocking

Routers do not own budgeting. Treat a router's `budget-deferred` decision as a
blocker and retain the applicable work in the complete graph. Assign worker or
coordinator execution only after routing. Partition into epochs only when
scheduling isolated execution.

## Worker Budget And Epochs

Adaptive grouped execution does not require a lifetime worker budget. Schedule
the complete dependency graph and use workers opportunistically without
changing selected coverage.

Exact reused review evidence is not part of the executable graph, consumes no
worker creation, and receives no execution epoch or dependency edge. Its routed
mapping remains a proof prerequisite for synthesis and completion.

For isolated execution, use a positive per-root fresh-worker budget, defaulting
to 24, and reserve at least one creation for recovery/finalization. When
authoritative lifetime capacity is known, use its lower ceiling for the current
root. Missing lifetime telemetry selects adaptive grouped execution unless the
user required isolated-only.

For every profile, plan the complete graph before dispatch. A transition plan
may contain selected leaves, required validators, independent review,
syntheses, planned fixes, and revalidations. After any fix runs, that plan and
its source state are historical: persist its fix/revalidation reports in the
invalidation history, recapture, reroute, and create a new final-state plan.
The final plan used to derive `RepositoryReviewProofExpectation` contains only
audit, independent-review, validation, and synthesis nodes plus exact
non-executable reuse. For isolated execution, partition each plan's topological
schedule into epochs satisfying:

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

Execution epochs exist only for isolated scheduling (`isolated`,
`isolated-only`, or the isolated portion preceding mixed fallback). Adaptive
grouped execution has no epochs, and routing never assigns one.

## Hard Deadline Contract

Treat every user or runtime time budget as a hard deadline in grouped,
isolated, isolated-only, and mixed execution. Record the monotonic deadline,
per-node elapsed caps, and coordinator, validation, and fix/revalidation
reserves in the plan. Before every worker dispatch or coordinator execution,
use `bounded_node_dispatch_seconds` or an equivalent monotonic calculation to
limit the node to the remaining dispatch window after all reserves.

When no dispatch window remains, start no new node. Preserve and verify every
accepted result, account for every unrun, unaccepted, or invalidated node, and
use the profile's failure or resume behavior. A deadline never permits routing
coverage to be deleted, a required node to be reclassified, or an incomplete
proof to be reported complete. If useful time remains after isolated execution
fails, an isolation preference may use grouped fallback under
[`execution-feasibility.md`](execution-feasibility.md#failure-and-fallback);
isolated-only may not.

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

The final proof must map every executable node in the recaptured final-state
`GraphPlan` to one unique accepted evidence ID, including requirement-free
synthesis. Reject a final proof expectation containing `fix` or `revalidation`
nodes: those source-mutating transition reports belong only to separately
verified invalidation history. Also reject missing planned nodes, reused
evidence assigned to an executable node, and evidence identity that differs
from the planned node. Each planned review node retains the planner-derived
skill digest and ordered static-reference path/digest pairs. Each planned
validator retains those provenance identities plus a canonical digest of its
exact coalesced `ValidationUnit`. The bundle gate compares record expectations
and envelopes to these plan-owned values; a caller cannot rebuild both sides
around substituted skill bytes, references, commands, working directories, or
canonical recipes.
Allow accepted non-node review evidence only for the exact reuse IDs declared
by the planner. Preserve each exact requirement-to-evidence mapping unchanged
through the routing assessment, graph plan, proof expectation, and proof, and
verify its complete envelope and artifact before accepting synthesis or
completion.

For each planned or exactly reused independent review, preserve the exact
concrete change target and ordered normalized review-surface paths through the
routing identity, `WorkerNode`, planner-derived evidence identity, dispatch
expectation, and bundle gate. Neither the worker artifact nor a caller-supplied
expectation may substitute a different target or path set.

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
expected workspace effects, isolation requirement, and exact isolation root
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
dependent synthesis. Reconcile each accepted handoff against the exact routing
ledger: selected, exactly reused, and explicitly user-excluded catalog entries
become `resolved_handoff_ids`; only genuinely new triggers remain in
`unresolved_handoff_ids`. The two disjoint sets together equal the globally
unique handoff IDs in accepted review evidence, and any unresolved ID blocks
completion. Persist the typed handoff-to-catalog mapping and verify it against
the accepted artifact before deriving either classification.

After an authorized fix, persist the S0→S1 fix and revalidation reports,
recapture S1 fingerprints, invalidate affected S0 reports, rerun repository and
affected surface routers, and build a fresh S1 plan without transition nodes.
Add newly applicable skills and rerun affected audit, validation, independent
review, and synthesis. Record stale, transition, and replacement evidence in
invalidation history rather than overwriting history or importing S0→S1 nodes
into the S1 proof.

Use `advance-after-mutation` for this transition. It records the serialized
repair epoch, accepts exactly one new capture, routes newly touched paths, moves
stale old-plan nodes to terminal `awaiting-replan`, and emits replacement
identities with lineage. Old immutable dispatches cannot be scheduled from that
state.

Derive the final `repository-production-review` synthesis edges in the planner.
It must depend on every selected non-repository synthesis node in addition to
the routed audits, validators, and additional nodes already assigned to it;
caller-supplied predecessor lists may add constraints but may not omit these
dependencies.

## Failure And Resume

In adaptive grouped execution, a failed worker creation or pre-acceptance worker
result selects coordinator execution for that exact node. Preserve the failed
attempt, do not change routing, and continue independent work.

In isolated execution, stop creating workers after the first creation failure
or exhausted current epoch. An isolation preference may continue the missing
graph adaptively after recording fallback. If no isolated evidence was accepted,
the resulting profile is grouped, not mixed. Only accepted isolated evidence
followed by actual grouped fallback selects mixed. Isolated-only preserves
completed raw reports and emits a manifest containing:

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

Before emitting this manifest, require accepted and unaccepted node IDs to be
known, unique, and disjoint. A failed node cannot be accepted and must appear in
both undispatched and unaccepted output.

Never substitute a completed worker for a later node. Coordinator execution is
permitted only after adaptive execution or mixed fallback is declared and must
produce the same accepted evidence envelope. A later root may resume only after
matching all fingerprints and revalidating routing closure. If fingerprints
changed, recapture and replan.

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
- all accepted reports have matching source fingerprints; isolated completion
  additionally has no isolation failure
- final findings, changes, validation, and lifecycle ledgers reconcile

Bind completion to the exact planner-derived proof expectation and proof, the
complete review and validation records, the typed artifact manifest, and the
trusted verifier payload boundary. The completion gate must invoke the evidence
bundle verifier itself and derive review, validation, synthesis,
independent-review, and exact-reuse coverage only after it succeeds; caller
lists and flags may only confirm the derived values and must fail on any
inconsistency.

`not-applicable`, exact verified reuse, and explicit user exclusion are routing
dispositions, not executed skills. User exclusion may yield complete only for
the explicitly narrowed request and must remain visible in limitations.

## Deterministic Dry Run

Use a portable JSON input with `consulted_routers` plus sparse
`routing_overrides`. The planner derives skill paths from the catalog and
expands the exhaustive ledger. Full `routing_decisions` remain accepted for
compatibility; legacy `review_requirements` are test-fixture-only.

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
