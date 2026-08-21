"""Regression tests for deterministic review-graph planning contracts."""

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

import pytest
from review_graph_plan import (
    CompletionEvidence,
    CreationFailure,
    ExecutionLedger,
    FingerprintEvidence,
    MigrationTrial,
    NodeAcceptanceEvidence,
    PlanNode,
    ReviewRequirement,
    RoutingDecision,
    RoutingDiscovery,
    TimeBudget,
    ValidationRequirement,
    WorkerBudget,
    WorkerNode,
    assess_completion,
    assess_migration_trials,
    assess_node_acceptance,
    assess_repository_classifier_floor,
    assess_routing_discoveries,
    assess_time_budget,
    assess_worker_capacity,
    bounded_node_dispatch_seconds,
    classify_repository_paths,
    coalesce_review_requirements,
    coalesce_validation_requirements,
    guard_packaged_python_routing,
    load_routing_catalog,
    plan_from_document,
    plan_graph,
    reconcile_execution,
    select_execution_profile,
    stop_after_worker_creation_failure,
    validate_routing_ledger,
)

SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"


def _capacity(*, remaining: int | None = None, active: int = 1) -> dict[str, object]:
    result: dict[str, object] = {"source": "runtime-capability-metadata", "concurrent_worker_limit": 4, "active_workers": active}
    if remaining is not None:
        result["fresh_worker_creations_remaining"] = remaining
        result["lifecycle_semantics"] = "bounded-total"
    return result


def test_no_fresh_worker_capacity_blocks_before_dispatch() -> None:
    result = assess_worker_capacity(_capacity(remaining=0), required_fresh_worker_creations=1)

    assert not result.feasible
    assert result.blockers == ("no fresh-worker creation capacity remains",)


def test_unknown_total_fresh_worker_capacity_allows_incremental_dispatch() -> None:
    result = assess_worker_capacity(_capacity(), required_fresh_worker_creations=22)

    assert result.feasible
    assert result.fresh_worker_creations_remaining is None
    assert result.full_plan_creation_capacity_guaranteed is None


def test_known_insufficient_current_root_capacity_blocks_epoch_dispatch() -> None:
    result = assess_worker_capacity(_capacity(remaining=3), required_fresh_worker_creations=22)

    assert not result.feasible
    assert result.required_fresh_worker_creations == 22
    assert result.full_plan_creation_capacity_guaranteed is False
    assert result.blockers == ("known fresh-worker capacity is smaller than the bounded plan: requires 22, has 3",)


def test_no_free_concurrent_slot_blocks_before_dispatch() -> None:
    result = assess_worker_capacity(_capacity(active=4), required_fresh_worker_creations=1)

    assert not result.feasible
    assert result.blockers == ("insufficient concurrent-worker capacity: requires 1, has 0",)


def test_capacity_evidence_rejects_prior_reports_without_echoing_them() -> None:
    prior_text = "prior finding that must not enter capacity diagnosis"
    metadata = {**_capacity(remaining=3), "workers": [{"final_report": prior_text}]}

    result = assess_worker_capacity(metadata, required_fresh_worker_creations=1)

    assert not result.feasible
    assert result.blockers[0].startswith("isolation-failure:")
    assert "$.workers[0].final_report" in result.blockers[0]
    assert prior_text not in result.blockers[0]


def test_grouped_delivery_is_the_default_without_capacity_diagnosis() -> None:
    result = select_execution_profile()

    assert result.feasible
    assert result.profile == "grouped"
    assert result.blockers == ()


def test_explicit_isolation_uses_isolated_profile_when_capability_is_safe() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "isolated"


def test_explicit_isolation_uses_grouped_profile_when_lifetime_capacity_is_unknown() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "full bounded-plan fresh-worker creation capacity is not guaranteed" in result.blockers


def test_isolation_preference_falls_back_to_grouped_delivery() -> None:
    result = select_execution_profile(isolated_requested=True)

    assert result.feasible
    assert result.profile == "grouped"
    assert "fresh no-inherited-turn workers are unavailable" in result.blockers
    assert "safe aggregate worker-capacity metadata is unavailable" in result.blockers


def test_isolation_requires_creation_capacity_beyond_the_recovery_reserve() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=1, active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "known fresh-worker capacity is smaller than the bounded plan: requires 2, has 1" in result.blockers


def test_isolation_accepts_creation_capacity_beyond_the_recovery_reserve() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "isolated"


def test_isolated_only_blocks_when_safe_capacity_is_unavailable() -> None:
    result = select_execution_profile(
        isolated_only=True, fresh_workers_supported=True, capacity_metadata={**_capacity(), "workers": [{"final_report": "must not leak"}]}
    )

    assert not result.feasible
    assert result.profile == "blocked"
    assert result.blockers[0].startswith("isolation-failure:")
    assert "must not leak" not in result.blockers[0]


@pytest.mark.parametrize("value", [1, "isolated"])
def test_malformed_isolation_preference_uses_grouped_delivery(value: object) -> None:
    result = select_execution_profile(isolated_requested=cast("bool", value), fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "isolated_requested must be a boolean" in result.blockers


@pytest.mark.parametrize("value", [1, "available"])
def test_malformed_fresh_worker_support_uses_grouped_delivery(value: object) -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=cast("bool", value), capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "fresh_workers_supported must be a boolean" in result.blockers


@pytest.mark.parametrize("value", [1, "isolated-only"])
def test_malformed_isolated_only_request_blocks(value: object) -> None:
    result = select_execution_profile(isolated_only=cast("bool", value), fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert not result.feasible
    assert result.profile == "blocked"
    assert result.isolated_only
    assert "isolated_only must be a boolean" in result.blockers


@pytest.mark.parametrize(
    ("field", "value", "expected_blocker"),
    [
        ("total", True, "worker budget total must be a non-boolean integer"),
        ("total", "24", "worker budget total must be a non-boolean integer"),
        ("recovery_finalization_reserve", True, "worker budget recovery/finalization reserve must be a non-boolean integer"),
        ("recovery_finalization_reserve", "1", "worker budget recovery/finalization reserve must be a non-boolean integer"),
    ],
)
def test_malformed_worker_budget_uses_grouped_delivery(field: str, value: object, expected_blocker: str) -> None:
    malformed_budget = replace(WorkerBudget(), **{field: value})

    result = select_execution_profile(
        isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1), budget=malformed_budget
    )

    assert result.feasible
    assert result.profile == "grouped"
    assert expected_blocker in result.blockers


def test_packaged_python_support_tooling_requires_build_portability() -> None:
    pyproject = """
[build-system]
requires = ["setuptools"]

[project]
name = "support-tools"

[project.scripts]
alpha = "helpers:alpha"

[tool.setuptools]
package-dir = {"" = "src"}
py-modules = ["helpers"]

[tool.uv]
package = true
"""

    result = guard_packaged_python_routing(("python-support-scripts",), pyproject)

    assert result.added_python_build_portability
    assert result.selected_skills == ("python-support-scripts", "python-build-portability")
    assert {"project.scripts", "tool.setuptools.py-modules", "tool.uv.package"} <= set(result.packaging_signals)


def _closed_rust_routing_decisions() -> tuple[RoutingDecision, ...]:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    selected = {"repo.rust", "repo.independent", "repo.synthesis", "rust.invariants", "rust.tests", "rust.synthesis"}
    decisions: list[RoutingDecision] = []
    for entry in catalog:
        if entry.router_id not in {"repo-review", "rust-review-orchestrator"}:
            continue
        disposition = "selected" if entry.catalog_id in selected else "not-applicable"
        review_surface = ("src/state.rs",) if disposition == "selected" and entry.target_kind in {"leaf", "independent"} else ()
        decisions.append(
            RoutingDecision(
                catalog_id=entry.catalog_id,
                requirement_id=f"requirement-{entry.catalog_id}",
                router_id=entry.router_id,
                rule_id=entry.rule_id,
                skill_id=entry.skill_id,
                skill_path=entry.skill_path,
                disposition=disposition,
                reason=(
                    "fixture decision from observed Rust state transition" if disposition == "selected" else "fixture surface does not exhibit this contract"
                ),
                applicability_evidence=("src/state.rs inspected",),
                review_surface=review_surface,
                static_references=entry.required_static_references,
                synthesis_dependency=entry.synthesis_dependency if disposition == "selected" else None,
                priority=entry.default_priority,
                owners=(entry.surface,),
            )
        )
    return tuple(decisions)


def test_real_routing_catalog_resolves_every_skill_path_and_frontmatter() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)

    assert len(catalog) == 53
    assert all(Path(entry.skill_path).is_absolute() for entry in catalog)
    assert {entry.router_id for entry in catalog} == {
        "repo-review",
        "cpp-review-orchestrator",
        "rust-review-orchestrator",
        "python-review-orchestrator",
        "docs-review-orchestrator",
    }
    by_router = {router: {entry.skill_id for entry in catalog if entry.router_id == router} for router in {entry.router_id for entry in catalog}}
    assert by_router["repo-review"] == {
        "project-tooling-review",
        "cpp-review-orchestrator",
        "rust-review-orchestrator",
        "python-review-orchestrator",
        "docs-review-orchestrator",
        "repository-independent-review",
        "repository-production-review",
    }
    assert by_router["cpp-review-orchestrator"] == {
        "cpp-lifetime-ownership-safety",
        "cpp-exception-safety-error-contracts",
        "cpp-invariant-state-transitions",
        "cpp-parse-dont-validate",
        "cpp-api-design",
        "cpp-api-docs",
        "cpp-build-portability",
        "cpp-functional-style",
        "cpp-scientific-correctness",
        "cpp-concurrency-reentrancy",
        "cpp-test-quality",
        "cpp-production-review",
    }
    assert by_router["rust-review-orchestrator"] == {
        "rust-build-portability",
        "rust-cargo-hygiene",
        "rust-api-docs",
        "rust-prelude-exports",
        "rust-fluent-api-design",
        "rust-trait-bounds",
        "rust-cli-design",
        "rust-invariant-state-transitions",
        "rust-parse-dont-validate",
        "rust-error-variants",
        "rust-borrowed-view-audit",
        "rust-scientific-correctness",
        "rust-concurrency-async",
        "rust-style-hygiene",
        "rust-iter-control-flow",
        "rust-simplification-review",
        "rust-invariant-performance",
        "rust-test-quality",
        "rust-production-review",
    }
    assert by_router["python-review-orchestrator"] == {
        "python-build-portability",
        "jupyter-notebook-review",
        "python-cli-review",
        "python-parse-dont-validate",
        "python-scientific-review",
        "python-support-scripts",
        "python-test-quality",
        "python-production-review",
    }
    assert by_router["docs-review-orchestrator"] == {
        "repository-docs-review",
        "scientific-software-docs-review",
        "scientific-crate-docs-review",
        "cpp-api-docs",
        "rust-api-docs",
        "scientific-citation-audit",
        "academic-authorship-boundary",
    }


def test_exhaustive_routing_ledger_closes_selected_repository_and_surface_router() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    result = validate_routing_ledger(catalog, _closed_rust_routing_decisions(), consulted_routers=("repo-review", "rust-review-orchestrator"))

    assert result.feasible
    assert result.catalog_closed
    assert set(result.selected_requirement_ids) == {"requirement-repo.independent", "requirement-rust.invariants", "requirement-rust.tests"}


def test_empty_routing_ledger_cannot_close_without_repo_review() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)

    result = validate_routing_ledger(catalog, (), consulted_routers=())

    assert not result.feasible
    assert not result.catalog_closed
    assert result.blockers == ("routing ledger must consult repo-review before catalog closure",)


def test_exhaustive_routing_ledger_rejects_silent_omission() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    decisions = tuple(item for item in _closed_rust_routing_decisions() if item.catalog_id != "rust.errors")

    result = validate_routing_ledger(catalog, decisions, consulted_routers=("repo-review", "rust-review-orchestrator"))

    assert not result.feasible
    assert not result.catalog_closed
    assert any("rust.errors" in blocker for blocker in result.blockers)


def test_exhaustive_routing_document_plans_every_selected_leaf_across_epochs() -> None:
    document = {
        "worker_budget": 5,
        "recovery_finalization_reserve": 1,
        "scope_mode": "branch",
        "concrete_change_target": True,
        "captured_paths": ["src/state.rs"],
        "consulted_routers": ["repo-review", "rust-review-orchestrator"],
        "routing_decisions": [json.loads(json.dumps(asdict(item))) for item in _closed_rust_routing_decisions()],
        "validation_requirements": [
            {
                "requirement_id": "baseline",
                "source_state": ["scope", "worktree", "repository"],
                "commands": ["just ci"],
                "working_directories": ["/repo"],
                "environment": "locked",
                "toolchain": "stable",
                "features": ["default"],
                "platform": "current-host",
                "artifact_owner": "repository",
                "mutation_lock": "read-only",
                "canonical_recipe": "just ci",
                "required": True,
                "baseline": True,
            }
        ],
        "synthesis_nodes": [
            {
                "node_id": "rust-synthesis",
                "skill_id": "rust-production-review",
                "skill_path": "$SKILLS_ROOT/rust-production-review/SKILL.md",
                "coverage": ["Rust synthesis"],
                "predecessors": [],
            },
            {
                "node_id": "repository-synthesis",
                "skill_id": "repository-production-review",
                "skill_path": "$SKILLS_ROOT/repository-production-review/SKILL.md",
                "coverage": ["Repository synthesis"],
                "predecessors": ["rust-synthesis"],
            },
        ],
    }

    plan = plan_from_document(document)

    assert plan.dispatch_allowed
    assert plan.routing_catalog_closed
    assert plan.consulted_routers == ("repo-review", "rust-review-orchestrator")
    assert len(plan.actual_worker_nodes) == 6
    assert len(plan.execution_epochs) == 2
    assert {node.skill_id for node in plan.actual_worker_nodes} >= {
        "rust-invariant-state-transitions",
        "rust-test-quality",
        "repository-independent-review",
        "rust-production-review",
        "repository-production-review",
    }
    invariant_node = next(node for node in plan.actual_worker_nodes if node.skill_id == "rust-invariant-state-transitions")
    assert invariant_node.selection_reasons == ("fixture decision from observed Rust state transition",)
    assert invariant_node.owners == ("rust",)


def test_budget_deferred_routing_is_completion_blocking() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    decisions = tuple(
        replace(item, disposition="budget-deferred", reason="worker budget exhausted") if item.catalog_id == "rust.tests" else item
        for item in _closed_rust_routing_decisions()
    )

    result = validate_routing_ledger(catalog, decisions, consulted_routers=("repo-review", "rust-review-orchestrator"))

    assert not result.feasible
    assert result.completion_blocking_catalog_ids == ("rust.tests",)


def test_late_routing_handoff_blocks_synthesis_until_replanned() -> None:
    decisions = _closed_rust_routing_decisions()
    discovery = RoutingDiscovery("handoff-errors", "audit-001", "rust.errors", "new typed error contract discovered")

    blocked = assess_routing_discoveries(decisions, (discovery,))
    selected = tuple(
        replace(item, disposition="selected", review_surface=("src/error.rs",)) if item.catalog_id == "rust.errors" else item for item in decisions
    )
    closed = assess_routing_discoveries(selected, (discovery,))

    assert not blocked.feasible
    assert closed.feasible


def test_repository_classifier_routes_shared_manifests_and_workflows_to_all_owners() -> None:
    signals = classify_repository_paths(("Cargo.toml", "pyproject.toml", "src/lib.rs", "src/tool.py", ".github/workflows/ci.yml", "README.md"))

    assert set(signals) == {"tooling", "rust", "python", "documentation"}
    assert any("Cargo.toml" in item for item in signals["tooling"])
    assert any("ci.yml" in item for item in signals["rust"])
    assert any("ci.yml" in item for item in signals["python"])


def test_repository_classifier_detects_nested_language_manifests_for_shared_workflows() -> None:
    signals = classify_repository_paths(("crates/core/Cargo.toml", "packages/app/pyproject.toml", ".github/workflows/ci.yml"))

    assert any("ci.yml" in item for item in signals["rust"])
    assert any("ci.yml" in item for item in signals["python"])


def test_repository_classifier_floor_rejects_router_conflict() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    decisions = _closed_rust_routing_decisions()
    signals = classify_repository_paths(("pyproject.toml",))

    result = assess_repository_classifier_floor(catalog, decisions, signals)

    assert not result.feasible
    assert any("repo.python is not-applicable" in blocker for blocker in result.blockers)
    assert any("repo.tooling is not-applicable" in blocker for blocker in result.blockers)


def test_repository_routing_surface_migration_matrix() -> None:
    fixture = Path(__file__).with_name("fixtures") / "routing_surface_matrix.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]

    for case in cases:
        signals = classify_repository_paths(tuple(case["paths"]), release_readiness=bool(case.get("release_readiness", False)))
        assert set(signals) == set(case["expected_surfaces"]), case["id"]


def test_bounded_critical_path_over_deadline_runs_with_explicit_risk() -> None:
    nodes = tuple(PlanNode(f"A{index:02}", 300) for index in range(1, 20))

    result = assess_time_budget(nodes, TimeBudget(overall_seconds=45 * 60, coordinator_reserve_seconds=5 * 60, validation_reserve_seconds=20 * 60))

    assert result.feasible
    assert result.critical_path_seconds == 19 * 300
    assert result.policy == "run-until-deadline-account-for-unrun"
    assert result.overall_budget_seconds is not None
    assert result.required_seconds > result.overall_budget_seconds
    assert result.completion_guaranteed_with_caps is False


def test_deadline_truncates_node_timeout_and_preserves_reconciliation_reserve() -> None:
    budget = TimeBudget(overall_seconds=600, coordinator_reserve_seconds=60, validation_reserve_seconds=120)

    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=100, budget=budget) == 300
    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=350, budget=budget) == 70
    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=500, budget=budget) == 0


def test_unbounded_request_keeps_per_node_cap() -> None:
    budget = TimeBudget(overall_seconds=None, coordinator_reserve_seconds=60, validation_reserve_seconds=120)
    result = assess_time_budget((PlanNode("A01", 300),), budget)

    assert result.feasible
    assert result.overall_budget_seconds is None
    assert result.completion_guaranteed_with_caps is None
    assert result.policy == "per-node-caps-only"
    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=10_000, budget=budget) == 300


def test_pre_execution_blocks_reconcile_without_claiming_skills_or_validators() -> None:
    result = reconcile_execution(
        ExecutionLedger(
            selected_nodes=("A01", "V01"),
            accepted_nodes=(),
            blocked_after_execution=(),
            blocked_before_execution=("A01", "V01"),
            invalidated_nodes=(),
            worker_attempts=(),
            workers_created=(),
            worker_creation_failures=(),
            skills_executed=(),
            planned_validators=("V01",),
            executed_validators=(),
            validators_not_run=("V01",),
        )
    )

    assert result.feasible


def test_invalidated_validator_reconciles_as_an_explicit_stale_outcome() -> None:
    result = reconcile_execution(
        ExecutionLedger(
            selected_nodes=("V01",),
            accepted_nodes=(),
            blocked_after_execution=(),
            blocked_before_execution=(),
            invalidated_nodes=("V01",),
            worker_attempts=("V01",),
            workers_created=("V01",),
            worker_creation_failures=(),
            skills_executed=("V01",),
            planned_validators=("V01",),
            executed_validators=("V01",),
            validators_not_run=(),
        )
    )

    assert result.feasible


def _review_requirement(
    ordinal: int, *, priority: str = "supporting-quality", required: bool = False, skill_id: str | None = None, synthesis_dependency: str = "rust-synthesis"
) -> ReviewRequirement:
    return ReviewRequirement(
        requirement_id=f"R{ordinal:02d}",
        skill_id=skill_id or f"specialist-{ordinal:02d}",
        skill_path=f"/skills/specialist-{ordinal:02d}/SKILL.md",
        router_id="rust-review-orchestrator",
        rule_id=f"fixture-rule-{ordinal:02d}",
        review_surface=(f"src/surface_{ordinal:02d}.rs",),
        reason="fixture surface owns this contract",
        priority=priority,
        synthesis_dependency=synthesis_dependency,
        required=required,
    )


def _validation_requirement(requirement_id: str, *, command: str = "just ci", evidence_id: str | None = None, baseline: bool = False) -> ValidationRequirement:
    return ValidationRequirement(
        requirement_id=requirement_id,
        source_state=("scope", "worktree", "repository"),
        commands=(command,),
        working_directories=("/repo",),
        environment="macos-arm64; locked dependencies",
        toolchain="stable",
        features=("default",),
        platform="macos-arm64",
        artifact_owner="repository-current-host",
        mutation_lock="shared-readonly-build-root",
        canonical_recipe=command,
        evidence_id=evidence_id,
        baseline=baseline,
    )


def _synthesis(node_id: str = "rust-synthesis") -> WorkerNode:
    return WorkerNode(
        node_id=node_id,
        skill_id="rust-production-review",
        skill_path=str(SKILL_ROOT / "rust-production-review" / "SKILL.md"),
        mode="synthesis",
        priority="required-routing-synthesis",
        required=True,
        coverage=("Rust synthesis",),
    )


def test_over_budget_plan_is_partitioned_without_omission() -> None:
    requirements = tuple(_review_requirement(index) for index in range(1, 9))
    plan = plan_graph(
        requirements, (_validation_requirement("V-baseline", baseline=True),), (_synthesis(),), budget=WorkerBudget(total=5, recovery_finalization_reserve=1)
    )

    assert plan.dispatch_allowed
    assert plan.complete_node_count == 10
    assert len(plan.actual_worker_nodes) == 10
    assert len(plan.execution_epochs) == 3
    assert all(len(epoch.node_ids) + epoch.recovery_finalization_reserve <= epoch.worker_budget for epoch in plan.execution_epochs)
    assert plan.requires_continuation


def test_synthesis_and_baseline_validation_retain_reserved_capacity() -> None:
    plan = plan_graph(
        tuple(_review_requirement(index, priority="optional-hygiene") for index in range(1, 7)),
        (_validation_requirement("V-baseline", baseline=True),),
        (_synthesis(),),
        budget=WorkerBudget(total=4, recovery_finalization_reserve=1),
    )

    selected = {node.node_id for node in plan.actual_worker_nodes}
    assert {"validation-001", "rust-synthesis"} <= selected
    assert len(plan.actual_worker_nodes) == 8
    assert len(plan.execution_epochs) == 3
    order = [node.node_id for node in plan.actual_worker_nodes]
    assert order.index("validation-001") < order.index("rust-synthesis")


def test_plan_rejects_missing_baseline_validation_before_dispatch() -> None:
    with pytest.raises(ValueError, match="at least one baseline validation unit"):
        plan_graph((_review_requirement(1),), (_validation_requirement("V-focused"),), (_synthesis(),))


def test_graph_document_rejects_selected_only_legacy_routing_without_fixture_escape_hatch() -> None:
    with pytest.raises(ValueError, match="exhaustive routing_decisions"):
        plan_from_document({"review_requirements": []})


@pytest.mark.parametrize("allow_legacy_fixture", [1, "false"])
def test_graph_document_rejects_non_boolean_legacy_fixture_escape_hatch(allow_legacy_fixture: object) -> None:
    with pytest.raises(ValueError, match="allow_legacy_fixture must be a boolean"):
        plan_from_document({"allow_legacy_fixture": allow_legacy_fixture, "review_requirements": []})


def test_repeated_validation_requirements_coalesce_and_reuse_mapping_is_complete() -> None:
    requirements = (
        _validation_requirement("V-rust", evidence_id="ledger-current-host"),
        _validation_requirement("V-python", evidence_id="ledger-current-host"),
        _validation_requirement("V-docs", evidence_id="ledger-current-host"),
    )

    units, mappings = coalesce_validation_requirements(requirements)

    assert len(units) == 1
    assert units[0].requirement_ids == ("V-docs", "V-python", "V-rust")
    assert units[0].evidence_ids == ("ledger-current-host",)
    assert {item.requirement_id for item in mappings} == {item.requirement_id for item in requirements}
    assert {item.validation_unit_id for item in mappings} == {"validation-001"}
    assert {item.evidence_id for item in mappings} == {"ledger-current-host"}


def test_review_coalescing_preserves_reasons_and_does_not_merge_distinct_owners() -> None:
    first = _review_requirement(1)
    second = replace(first, requirement_id="R02", reason="second routing reason")
    distinct_owner = replace(first, requirement_id="R03", owners=("documentation",))

    nodes, mappings = coalesce_review_requirements((first, second, distinct_owner))

    assert len(nodes) == 2
    merged = next(node for node in nodes if set(node.requirement_ids) == {"R01", "R02"})
    assert merged.selection_reasons == ("fixture surface owns this contract", "second routing reason")
    assert merged.owners == ()
    assert dict(mappings).keys() == {"R01", "R02", "R03"}


def test_budget_never_reclassifies_applicable_specialists_as_skips() -> None:
    requirements = tuple(_review_requirement(index) for index in range(1, 6))
    plan = plan_graph(
        requirements, (_validation_requirement("V-baseline", baseline=True),), (_synthesis(),), budget=WorkerBudget(total=4, recovery_finalization_reserve=1)
    )

    selected_requirements = {requirement for node in plan.actual_worker_nodes for requirement in node.requirement_ids if requirement.startswith("R")}
    assert selected_requirements == {item.requirement_id for item in requirements}
    assert plan.requires_continuation


def test_worker_creation_failure_halts_dispatch_and_emits_resume_manifest() -> None:
    planned_nodes = tuple(
        WorkerNode(
            node_id=node_id,
            skill_id="review-validator" if node_id == "V01" else "specialist",
            skill_path=f"/skills/{'review-validator' if node_id == 'V01' else 'specialist'}/SKILL.md",
            mode="validation" if node_id == "V01" else "audit",
            priority="required-validation" if node_id == "V01" else "supporting-quality",
            required=node_id == "V01",
            requirement_ids=(f"requirement-{node_id}",),
        )
        for node_id in ("A01", "A02", "V01", "S01")
    )
    manifest = stop_after_worker_creation_failure(
        CreationFailure(
            planned_nodes=planned_nodes,
            accepted_node_ids=("A01",),
            failed_node_id="A02",
            unaccepted_node_ids=(),
            source_state=("scope", "worktree", "repository"),
            journal_location="/artifacts/review-graph/journal.json",
        )
    )

    assert manifest.dispatch_halted
    assert tuple(node.node_id for node in manifest.undispatched_nodes) == ("A02", "V01", "S01")
    assert manifest.unaccepted_nodes == manifest.undispatched_nodes
    assert manifest.fresh_root_task_may_be_required
    assert manifest.journal_location == "/artifacts/review-graph/journal.json"


def test_incomplete_graph_cannot_report_completed_outcome() -> None:
    result = assess_completion(
        CompletionEvidence(
            required_requirement_ids=("R01", "R02"),
            completed_requirement_ids=("R01",),
            meaningful_skip_requirement_ids=(),
            required_documentation_ids=("R-docs",),
            completed_documentation_ids=(),
            required_validation_node_ids=("V01",),
            accepted_validation_node_ids=(),
            required_synthesis_node_ids=("S01",),
            accepted_synthesis_node_ids=(),
            unaccepted_node_ids=("A02",),
            undispatched_node_ids=("V01", "S01"),
            fingerprints_matched=True,
            isolation_failures=(),
            final_report_synthesized=False,
            findings_deduplicated=False,
        )
    )

    assert not result.feasible
    assert any("required review requirements are incomplete" in blocker for blocker in result.blockers)
    assert any("undispatched nodes remain" in blocker for blocker in result.blockers)


def test_meaningful_skip_cannot_satisfy_an_applicable_requirement() -> None:
    result = assess_completion(
        CompletionEvidence(
            required_requirement_ids=("R01",),
            completed_requirement_ids=(),
            meaningful_skip_requirement_ids=("R01",),
            required_documentation_ids=(),
            completed_documentation_ids=(),
            required_validation_node_ids=(),
            accepted_validation_node_ids=(),
            required_synthesis_node_ids=(),
            accepted_synthesis_node_ids=(),
            unaccepted_node_ids=(),
            undispatched_node_ids=(),
            fingerprints_matched=True,
            isolation_failures=(),
            final_report_synthesized=True,
            findings_deduplicated=True,
        )
    )

    assert not result.feasible
    assert any("cannot complete through meaningful skips" in blocker for blocker in result.blockers)


def _migration_trial(trial_id: str, mode: str, *, forced_worker_failure: bool = False, multi_epoch: bool = False) -> MigrationTrial:
    return MigrationTrial(
        trial_id=trial_id,
        mode=mode,
        expected_applicable_skill_ids=("rust-test-quality",),
        observed_applicable_skill_ids=("rust-test-quality",),
        unexpected_skill_ids=(),
        expected_canonical_finding_ids=("finding-1",),
        observed_canonical_finding_ids=("finding-1", "valid-extra"),
        nodes_reconciled=True,
        validation_complete=True,
        synthesis_complete=True,
        fingerprints_matched=True,
        report_complete=True,
        accepted=True,
        recovery_completed=forced_worker_failure,
        multi_epoch_completed=multi_epoch,
        runtime_artifact_id=f"artifact://{trial_id}",
        runtime_artifact_verified=True,
        runtime_artifact_verifier="forward-trial-recorder",
        workers_created=1,
        grouped_fallback_completed=forced_worker_failure,
        worker_failure_forced=forced_worker_failure,
    )


def test_migration_gate_requires_three_consecutive_modes_recovery_and_epochs() -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )

    result = assess_migration_trials(trials)

    assert result.feasible


@pytest.mark.parametrize("value", [1, "complete"])
def test_migration_gate_rejects_malformed_multi_epoch_evidence(value: object) -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )
    trials = tuple(replace(trial, multi_epoch_completed=cast("bool", value)) if trial.trial_id == "baseline-release-1" else trial for trial in trials)

    result = assess_migration_trials(trials)

    assert not result.feasible
    assert "no accepted multi-epoch fresh-root continuation trial completed" in result.blockers


def test_migration_gate_rejects_missing_applicable_skill_recall() -> None:
    trials = tuple(_migration_trial(f"branch-{ordinal}", "branch-read-only") for ordinal in range(1, 4))
    trials = (*trials, replace(_migration_trial("branch-failure", "branch-read-only"), observed_applicable_skill_ids=()))

    result = assess_migration_trials(trials)

    assert not result.feasible
    assert any("branch-read-only has 0 consecutive" in blocker for blocker in result.blockers)


def test_migration_gate_rejects_trials_without_runtime_evidence() -> None:
    trial = replace(
        _migration_trial("branch-1", "branch-read-only"),
        runtime_artifact_id=None,
        runtime_artifact_verified=False,
        runtime_artifact_verifier=None,
        workers_created=0,
    )

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any("has no runtime trial artifact" in blocker for blocker in result.blockers)
    assert any("created no runtime workers" in blocker for blocker in result.blockers)


def test_migration_gate_rejects_an_unverified_runtime_artifact() -> None:
    trial = replace(_migration_trial("branch-1", "branch-read-only"), runtime_artifact_verified=False, runtime_artifact_verifier=None)

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any("runtime trial artifact was not independently verified" in blocker for blocker in result.blockers)


@pytest.mark.parametrize(
    ("changes", "expected_blocker"),
    [
        ({"runtime_artifact_id": "  "}, "has no runtime trial artifact"),
        ({"runtime_artifact_verifier": "\t"}, "runtime trial artifact was not independently verified"),
        ({"runtime_artifact_verified": 1}, "runtime trial artifact was not independently verified"),
        ({"workers_created": True}, "has an invalid runtime worker count"),
        ({"workers_created": 1.5}, "has an invalid runtime worker count"),
    ],
)
def test_migration_gate_rejects_malformed_runtime_evidence(changes: dict[str, object], expected_blocker: str) -> None:
    trial = replace(_migration_trial("branch-1", "branch-read-only"), **changes)

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any(expected_blocker in blocker for blocker in result.blockers)


@pytest.mark.parametrize("value", [1, "complete"])
@pytest.mark.parametrize(
    ("field", "expected_blocker"),
    [
        ("nodes_reconciled", "failed node lifecycle"),
        ("validation_complete", "failed validation"),
        ("synthesis_complete", "failed synthesis"),
        ("fingerprints_matched", "failed fingerprints"),
        ("report_complete", "failed report"),
        ("accepted", "failed accepted outcome"),
    ],
)
def test_migration_gate_rejects_malformed_success_evidence(field: str, expected_blocker: str, value: object) -> None:
    trial = replace(_migration_trial("branch-1", "branch-read-only"), **{field: value})

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any(expected_blocker in blocker for blocker in result.blockers)


def test_migration_gate_requires_explicit_forced_worker_failure_evidence() -> None:
    trials = tuple(
        replace(
            _migration_trial(
                f"{mode}-{ordinal}",
                mode,
                forced_worker_failure=mode == "branch-read-only" and ordinal == 1,
                multi_epoch=mode == "baseline-release" and ordinal == 1,
            ),
            worker_failure_forced=False,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )

    result = assess_migration_trials(trials)

    assert not result.feasible
    assert "no accepted forced worker-failure trial completed grouped fallback" in result.blockers


@pytest.mark.parametrize(
    ("field", "value"),
    [("recovery_completed", 1), ("recovery_completed", "complete"), ("grouped_fallback_completed", 1), ("grouped_fallback_completed", "complete")],
)
def test_migration_gate_requires_exact_true_for_recovery_evidence(field: str, value: object) -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )
    malformed_trial = replace(trials[0], **{field: value})

    result = assess_migration_trials((malformed_trial, *trials[1:]))

    assert not result.feasible
    assert "no accepted forced worker-failure trial completed grouped fallback" in result.blockers


def test_migration_gate_allows_a_recovered_trailing_streak() -> None:
    old_failure = replace(_migration_trial("old-failure", "branch-read-only"), observed_applicable_skill_ids=())
    recovered_trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )

    result = assess_migration_trials((old_failure, *recovered_trials))

    assert result.feasible


def test_node_acceptance_requires_isolation_skill_reference_and_fingerprint_proof() -> None:
    expected = ("scope", "worktree", "repository")
    accepted = assess_node_acceptance(
        NodeAcceptanceEvidence(
            node_id="A01",
            worker_created=True,
            fresh_context=True,
            expected_skill_path="/skills/rust-scientific-correctness/SKILL.md",
            loaded_skill_path="/skills/rust-scientific-correctness/SKILL.md",
            required_static_references=("/skills/rust-review-orchestrator/references/la-stack.md",),
            loaded_static_references=("/skills/rust-review-orchestrator/references/la-stack.md",),
            fingerprints=FingerprintEvidence(expected=expected, before=expected, after=expected),
            report_complete=True,
            timed_out=True,
        )
    )
    rejected = assess_node_acceptance(
        NodeAcceptanceEvidence(
            node_id="A02",
            worker_created=True,
            fresh_context=False,
            expected_skill_path="/skills/rust-test-quality/SKILL.md",
            loaded_skill_path=None,
            required_static_references=("/skills/rust-review-orchestrator/references/la-stack.md",),
            loaded_static_references=(),
            fingerprints=FingerprintEvidence(expected=expected, before=expected, after=("scope", "changed", "repository")),
            report_complete=False,
        )
    )

    assert accepted.feasible
    assert not rejected.feasible
    assert len(rejected.blockers) == 5


def test_representative_rust_python_docs_fixture_stays_within_budget() -> None:
    fixture = Path(__file__).with_name("fixtures") / "representative_rust_python_docs.json"
    plan = plan_from_document(json.loads(fixture.read_text(encoding="utf-8")))

    assert plan.dispatch_allowed
    assert all(len(epoch.node_ids) + epoch.recovery_finalization_reserve <= epoch.worker_budget for epoch in plan.execution_epochs)
    assert {"rust-synthesis", "python-synthesis", "repository-synthesis"} <= set(plan.synthesis_nodes)
    assert any(unit.baseline for unit in plan.coalesced_validation_units)
    order = [node.node_id for node in plan.actual_worker_nodes]
    assert order.index("validation-001") < order.index("rust-synthesis")
    assert order.index("validation-002") < order.index("python-synthesis")
    assert any("la-stack.md" in reference for item in json.loads(fixture.read_text())["review_requirements"] for reference in item["static_references"])
