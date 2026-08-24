# Compact Review Routing Handoff

Use this compatibility reference when a surface orchestrator is explicitly
asked for `graph-routing`. New `review-graph` execution normally reads the
surface's `references/check-routing.md` directly and sends sparse semantic
overrides to the planner.

## Contract

Inspect the supplied captured paths and the surface routing matrix. Return only
records whose disposition is one of:

- `selected`
- `exact-evidence-reused`
- `user-excluded`
- `budget-deferred`, `capability-blocked`, or `failed`

Omit ordinary `not-applicable` candidates. The planner expands every omission
into an explicit catalog record and verifies total closure.

Each returned record contains:

```text
catalog_id
disposition
reason
applicability_evidence
review_surface
owners
validation_requirement_ids
instruction_paths, when candidate-specific
static_references, when candidate-specific
evidence_id, only for exact reuse
```

Do not return `requirement_id`, `router_id`, `rule_id`, `skill_id`,
`skill_path`, `priority`, or `synthesis_dependency`. Those are catalog-owned
identities derived by `scripts/review_graph_plan.py`; caller-authored copies are
rejected.

## Closure

The planner:

- applies the conservative repository classifier
- selects required repository and consulted-surface syntheses
- selects independent review for a concrete change target
- expands every omitted candidate to `not-applicable`
- resolves exact skill paths under approved roots
- attaches catalog priority and synthesis identity
- rejects unknown, duplicated, out-of-scope, or contradictory overrides

Shared files still retain every applicable owner. A sparse handoff changes only
serialization; it never permits applicable coverage to disappear.

## Late Handoffs

Accepted review payloads report newly observed applicability with `catalog_id`,
trigger evidence, reason, and exact paths. Add the corresponding sparse override
only after `review_graph_runtime.py reconcile-handoffs` reports it in
`new_routing_triggers`. Handoffs already selected, exactly reused, or explicitly
excluded are resolved by the current plan. Replan genuine triggers before
dependent validation or synthesis. After fixes, rerun routing only for changed
surfaces plus repository classification.
