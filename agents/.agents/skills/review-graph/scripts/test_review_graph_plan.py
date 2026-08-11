"""Regression tests for deterministic review-graph planning contracts."""

from __future__ import annotations

from review_graph_plan import (
    ExecutionLedger,
    PlanNode,
    TimeBudget,
    assess_time_budget,
    assess_worker_capacity,
    bounded_node_dispatch_seconds,
    guard_packaged_python_routing,
    reconcile_execution,
)


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


def test_insufficient_total_fresh_worker_capacity_does_not_preblock_graph() -> None:
    result = assess_worker_capacity(_capacity(remaining=3), required_fresh_worker_creations=22)

    assert result.feasible
    assert result.required_fresh_worker_creations == 22
    assert result.full_plan_creation_capacity_guaranteed is False
    assert not result.blockers


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
