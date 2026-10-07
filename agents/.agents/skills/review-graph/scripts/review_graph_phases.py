"""Validation scheduling barriers, separate from semantic review dependencies."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from review_graph_plan import GraphPlan


def validate_validation_barrier(plan: GraphPlan) -> None:
    """Reject malformed saved plans before materialization or lifecycle replay."""
    early = plan.pre_review_validation_nodes
    units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
    modes = {node.node_id: node.mode for node in plan.actual_worker_nodes}
    if len(set(early)) != len(early) or any(node_id not in units or modes.get(node_id) != "validation" for node_id in early):
        msg = "pre-review validation requires unique planned validator nodes"
        raise ValueError(msg)
    if any(
        not units[node_id].required
        or not units[node_id].commands
        or units[node_id].dependency_policy != "stop-on-failure"
        or units[node_id].execution_strategy != "sequential"
        for node_id in early
    ):
        msg = "pre-review validation requires required executable sequential stop-on-failure units"
        raise ValueError(msg)


def pending_validation_barrier(plan: GraphPlan, state: dict[str, str], latest: dict[str, dict[str, Any]], node_id: str) -> tuple[str, ...]:
    """Failed evidence is accepted history but cannot release subsequent work."""
    early = plan.pre_review_validation_nodes
    predecessors = early[: early.index(node_id)] if node_id in early else early
    return tuple(
        candidate
        for candidate in predecessors
        if state.get(candidate) != "accepted" or (latest.get(candidate, {}).get("evidence") or {}).get("evidence_status") not in {"passed", "reused"}
    )


def require_validation_barrier(plan: GraphPlan, state: dict[str, str], latest: dict[str, dict[str, Any]], *, node_id: str, status: str) -> None:
    """Enforce the barrier for direct journal/compile calls as well as scheduling."""
    if status in {"invalidated", "awaiting-replan"}:
        return
    if state.get(node_id) == "in-flight" and status in {"accepted", "blocked"}:
        # A preserved audit can finish across external staging after its original
        # successful barrier. Compilation still verifies the actual source reads.
        return
    pending = pending_validation_barrier(plan, state, latest, node_id)
    if pending:
        msg = f"cannot transition {node_id} to {status}; pre-review validation has not passed: " + ", ".join(pending)
        raise ValueError(msg)


def _launch_totals_known(nodes: set[str], events: tuple[dict[str, Any], ...]) -> bool:
    """Require each attempt's start and avoid inferring historical executor lanes."""
    active: set[str] = set()
    started: set[str] = set()
    for event in events:
        node_id, status = event["node_id"], event["status"]
        if status in {"invalidated", "awaiting-replan"}:
            affected = set(event["affected_node_ids"]) & nodes
            if affected & started:
                # A continuation may replace the dispatch lane. The journal
                # records starts, but does not bind their historical executors.
                return False
            active.difference_update(affected)
        elif node_id in nodes:
            if status == "in-flight":
                active.add(node_id)
                started.add(node_id)
            elif status in {"accepted", "blocked"}:
                if node_id not in active:
                    return False
                active.remove(node_id)
    return True


def phase_accounting(plan: GraphPlan, events: tuple[dict[str, Any], ...], entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Report observed journal boundaries and starts without estimating provider costs."""
    stages = {
        "pre-review-validation": set(plan.pre_review_validation_nodes),
        "semantic-review": {node.node_id for node in plan.actual_worker_nodes if node.mode in {"audit", "independent-review", "revalidation"}},
        "remaining-validation": {node.node_id for node in plan.actual_worker_nodes if node.mode == "validation"} - set(plan.pre_review_validation_nodes),
        "synthesis": {node.node_id for node in plan.actual_worker_nodes if node.mode == "synthesis"},
    }
    result = []
    for stage, nodes in stages.items():
        observed = [event for event in events if event["node_id"] in nodes]
        starts = [event for event in observed if event["status"] == "in-flight"]
        recorded = [event for event in observed if event["status"] in {"accepted", "blocked"}]
        launches_known = _launch_totals_known(nodes, events)
        result.append(
            {
                "stage": stage,
                "planned_node_count": len(nodes),
                "journal_start_count": len(starts),
                "worker_launch_count": (
                    sum(entries[event["node_id"]]["dispatch"]["execution_location"] == "worker" for event in starts) if launches_known else None
                ),
                "coordinator_start_count": (
                    sum(entries[event["node_id"]]["dispatch"]["execution_location"] == "coordinator" for event in starts) if launches_known else None
                ),
                "result_record_count": len(recorded),
                "first_start_unix_ns": starts[0].get("recorded_at_unix_ns") if starts else None,
                "last_result_unix_ns": recorded[-1].get("recorded_at_unix_ns") if recorded else None,
                "first_start_sequence": starts[0]["sequence"] if starts else None,
                "last_result_sequence": recorded[-1]["sequence"] if recorded else None,
                "provider_cost_usd": None,
                "provider_cost_basis": "unavailable",
            }
        )
    return result
