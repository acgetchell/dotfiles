# Compact Review Routing Handoff

Use this compatibility reference when a surface orchestrator is explicitly
asked for `graph-routing`. Normal `review-graph` execution uses
`routing-projection` and sends sparse semantic overrides to the planner. Read a
surface's `references/check-routing.md` only when the projection leaves shared
ownership or applicability ambiguous.

## Contract

Inspect the supplied captured paths and the surface routing matrix. Return only
records whose disposition is one of:

- `selected`
- `not-applicable`, with evidence for a matched candidate
- `exact-evidence-reused`
- `user-excluded`
- `budget-deferred`, `capability-blocked`, or `failed`

Assess every path-matched specialist explicitly, including evidence-backed
`not-applicable` decisions. Omit only unmatched, semantically untriggered
candidates. The planner rejects unassessed matches and expands other omissions
into explicit catalog records. Uncertainty is a visible blocker, not a negative
applicability judgment.

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
- requires semantic decisions for projection-matched leaves; a path alone never dispatches a language specialist
- applies catalog `excluded_path_patterns` to default projection matches only;
  semantic overrides can still select an excluded path with concrete evidence
- selects required repository and consulted-surface syntheses
- selects independent review for a concrete change target
- expands unmatched, untriggered omissions to `not-applicable`
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
