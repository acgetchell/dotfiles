# Exhaustive Review Routing Handoff

Use this contract whenever `repo-review`, a language orchestrator, or the
documentation orchestrator acts as a routing authority for `review-graph`.
Routers decide applicability; the graph validates closure and owns workers,
validation, epochs, fixes, and synthesis.

## Routing Sequence

1. Ask `repo-review` for the repository-layer ledger covering tooling, C++,
   Rust, Python, documentation, independent review, and repository synthesis.
2. For every selected surface router, request its complete surface ledger.
3. Validate both layers against
   [`routing-catalog.json`](routing-catalog.json) before planning workers.
4. Reject any unknown, duplicated, omitted, ambiguous, or mismatched catalog
   entry. Do not infer a decision from silence.

## Graph-Routing Mode

In `graph-routing` mode:

- inspect the supplied captured scope and the router's check-routing reference
- expand portable catalog paths to exact absolute paths under an approved skill
  root
- return one disposition for every catalog entry owned by that router
- cite the catalog rule and observed applicability evidence
- do not load selected specialist bodies
- do not review, validate, synthesize, edit, or create subagents
- preserve repository-specific static guidance as exact paths for affected
  workers

Keep standalone behavior unchanged outside graph-routing mode.

## Decision Record

Return one record per catalog entry:

```text
catalog_id: exact routing-catalog ID
requirement_id: stable router-owned ID
router_id: exact routing authority
rule_id: exact catalog rule
skill_id: exact catalog skill
skill_path: exact absolute SKILL.md path
disposition: selected | not-applicable | exact-evidence-reused |
  user-excluded | budget-deferred | capability-blocked | failed
reason: concrete applicability decision
applicability_evidence: inspected paths, contracts, or explicit scope facts
review_surface: exact paths and contract boundary, or empty when not selected
instruction_paths: exact applicable AGENTS.md or equivalent paths
static_references: exact required repository/routing references
validation_requirement_ids: separately declared validator requirements
priority: declared priority class
synthesis_dependency: exact synthesis node ID or none
owners: every shared-file owner
evidence_id: required for exact-evidence-reused, otherwise none
```

Use only `selected` for applicable work requiring a worker. Routers must not use
`budget-deferred` to reduce coverage; the graph partitions all selected work
into execution epochs. `capability-blocked` and `failed` are explicit incomplete
outcomes. `user-excluded` completes only the user-bounded scope and must remain
visible as a coverage limitation.

## Repository-Layer Closure

Return all `repo-review` catalog entries even when only one surface applies.
Use the deterministic repository classifier in
`scripts/review_graph_plan.py` as a conservative floor. A router may select
additional owners from semantic evidence but may not mark a signaled owner
`not-applicable` without resolving the conflict.

Route shared files to all affected owners. In particular:

- CMake/vcpkg surfaces: C++ and tooling
- Cargo manifests/locks: Rust and tooling
- Python project/lock metadata: Python and tooling
- workflows and recipes: tooling plus every affected language
- active docs: documentation plus tooling/language truth owners when applicable

Select `repository-independent-review` for a concrete branch, staged, pull
request, changed-file, or fix target. Mark it `not-applicable` for a pure
whole-repository baseline without a concrete change. Always select
`repository-production-review` for final broad-graph synthesis.

## Surface-Layer Closure

Return every candidate owned by the selected orchestrator, including its
production-synthesis catalog entry. Choose the smallest applicable specialist
set, but explain every non-applicable candidate. Path patterns are conservative
signals; semantic triggers establish the final decision.

Attach every applicable static repository reference to selected leaves and
affected synthesis nodes. Declare exact validation requirements separately so
the graph can coalesce identical evidence.

## Late Handoffs

Every accepted worker reports newly observed applicability by `catalog_id`,
evidence, and affected surface. Revalidate the ledger after each audit and after
every fix that changes repository surfaces. Add newly selected nodes before
dependent synthesis. Unresolved, unknown, budget-deferred, capability-blocked,
or failed handoffs keep the graph incomplete.
