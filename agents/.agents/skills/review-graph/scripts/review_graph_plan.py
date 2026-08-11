"""Deterministic planning checks for review-graph orchestration."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_REQUIRED_CAPACITY_FIELDS = frozenset({"active_workers", "concurrent_worker_limit", "source"})
_OPTIONAL_CAPACITY_FIELDS = frozenset({"fresh_worker_creations_remaining", "lifecycle_semantics"})
_CAPACITY_FIELDS = _REQUIRED_CAPACITY_FIELDS | _OPTIONAL_CAPACITY_FIELDS
_CONTEXT_KEYS = frozenset(
    {
        "analysis",
        "content",
        "final_answer",
        "final_report",
        "finding",
        "findings",
        "message",
        "messages",
        "native_report",
        "output",
        "payload",
        "report",
        "reports",
        "result",
        "results",
    }
)


@dataclass(frozen=True)
class Assessment:
    """One deterministic feasibility or reconciliation result."""

    feasible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class CapacityAssessment(Assessment):
    """Concurrent capacity and optional lifetime-capacity forecast."""

    fresh_worker_creations_remaining: int | None
    required_fresh_worker_creations: int
    free_concurrent_slots: int | None
    required_peak_workers: int
    full_plan_creation_capacity_guaranteed: bool | None


@dataclass(frozen=True)
class PlanNode:
    """One bounded node in a sequential or dependency-driven schedule."""

    node_id: str
    elapsed_seconds: int
    predecessors: tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetAssessment(Assessment):
    """Hard-deadline readiness without treating node caps as reservations."""

    critical_path_seconds: int
    coordinator_reserve_seconds: int
    validation_reserve_seconds: int
    fix_revalidation_reserve_seconds: int
    required_seconds: int
    overall_budget_seconds: int | None
    dispatch_window_seconds: int | None
    completion_guaranteed_with_caps: bool | None
    policy: str


@dataclass(frozen=True)
class TimeBudget:
    """Graph-wide hard deadline and explicit non-worker reserves."""

    overall_seconds: int | None
    coordinator_reserve_seconds: int
    validation_reserve_seconds: int
    fix_revalidation_reserve_seconds: int = 0
    sequential: bool = True


@dataclass(frozen=True)
class RoutingGuard:
    """Result of the narrow packaged-Python routing guard."""

    selected_skills: tuple[str, ...]
    packaging_signals: tuple[str, ...]
    added_python_build_portability: bool


@dataclass(frozen=True)
class ExecutionLedger:
    """Lifecycle sets used by final graph reconciliation."""

    selected_nodes: tuple[str, ...]
    accepted_nodes: tuple[str, ...]
    blocked_after_execution: tuple[str, ...]
    blocked_before_execution: tuple[str, ...]
    worker_attempts: tuple[str, ...]
    workers_created: tuple[str, ...]
    worker_creation_failures: tuple[str, ...]
    skills_executed: tuple[str, ...]
    planned_validators: tuple[str, ...]
    executed_validators: tuple[str, ...]
    validators_not_run: tuple[str, ...]


def _context_paths(value: object, path: str = "$") -> tuple[str, ...]:
    """Return sensitive key paths without retaining or rendering their values."""
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.casefold().replace("-", "_") in _CONTEXT_KEYS:
                matches.append(child_path)
                continue
            matches.extend(_context_paths(item, child_path))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            matches.extend(_context_paths(item, f"{path}[{index}]"))
    return tuple(matches)


def _required_capacity_metadata_blocker(metadata: Mapping[str, Any]) -> str | None:
    """Validate the aggregate fields required to start one worker."""
    source = metadata.get("source")
    concurrent_limit = metadata.get("concurrent_worker_limit")
    active_workers = metadata.get("active_workers")
    if not isinstance(source, str) or not source.strip():
        return "capacity evidence source is unknown or invalid"
    if not isinstance(concurrent_limit, int) or isinstance(concurrent_limit, bool) or concurrent_limit < 1:
        return "concurrent-worker capacity is unknown or invalid"
    if not isinstance(active_workers, int) or isinstance(active_workers, bool) or active_workers < 0:
        return "active-worker count is unknown or invalid"
    if active_workers > concurrent_limit:
        return "active-worker count exceeds the concurrent-worker limit"
    return None


def _optional_lifetime_metadata_blocker(metadata: Mapping[str, Any]) -> str | None:
    """Validate lifetime metadata only when the runtime supplies it."""
    lifetime_fields = {"fresh_worker_creations_remaining", "lifecycle_semantics"}
    present = lifetime_fields & set(metadata)
    if present and present != lifetime_fields:
        return "optional lifetime-capacity evidence is incomplete"
    if not present:
        return None
    remaining = metadata["fresh_worker_creations_remaining"]
    lifecycle = metadata["lifecycle_semantics"]
    if not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 0:
        return "fresh total-worker creation capacity is invalid"
    if lifecycle not in {"bounded-total", "release-on-completion"}:
        return "worker lifecycle semantics are invalid"
    return None


def _capacity_metadata_blocker(metadata: Mapping[str, Any]) -> str | None:
    """Validate safe concurrency metadata and optional lifetime metadata."""
    exposed_context = _context_paths(metadata)
    if exposed_context:
        return "isolation-failure: capacity evidence exposed task context at " + ", ".join(exposed_context)
    unexpected = sorted(set(metadata) - _CAPACITY_FIELDS)
    if unexpected:
        return "capacity evidence contains unsupported fields: " + ", ".join(unexpected)
    missing = sorted(_REQUIRED_CAPACITY_FIELDS - set(metadata))
    if missing:
        return "capacity evidence is missing required fields: " + ", ".join(missing)
    return _required_capacity_metadata_blocker(metadata) or _optional_lifetime_metadata_blocker(metadata)


def _blocked_capacity(reason: str, *, required_fresh_worker_creations: int, required_peak_workers: int) -> CapacityAssessment:
    """Create one capacity blocker without leaking rejected metadata values."""
    return CapacityAssessment(
        feasible=False,
        blockers=(reason,),
        fresh_worker_creations_remaining=None,
        required_fresh_worker_creations=required_fresh_worker_creations,
        free_concurrent_slots=None,
        required_peak_workers=required_peak_workers,
        full_plan_creation_capacity_guaranteed=None,
    )


def assess_worker_capacity(metadata: Mapping[str, Any], *, required_fresh_worker_creations: int, required_peak_workers: int = 1) -> CapacityAssessment:
    """Require start capacity and forecast total capacity only when supplied."""
    if required_fresh_worker_creations < 0 or required_peak_workers < 1:
        msg = "worker requirements must be nonnegative with a positive peak"
        raise ValueError(msg)

    blocker = _capacity_metadata_blocker(metadata)
    if blocker is not None:
        return _blocked_capacity(blocker, required_fresh_worker_creations=required_fresh_worker_creations, required_peak_workers=required_peak_workers)

    raw_remaining = metadata.get("fresh_worker_creations_remaining")
    remaining = int(raw_remaining) if raw_remaining is not None else None
    concurrent_limit = int(metadata["concurrent_worker_limit"])
    active_workers = int(metadata["active_workers"])

    free_slots = max(0, concurrent_limit - active_workers)
    blockers: list[str] = []
    if required_fresh_worker_creations > 0 and remaining == 0:
        blockers.append("no fresh-worker creation capacity remains")
    if free_slots < required_peak_workers:
        blockers.append(f"insufficient concurrent-worker capacity: requires {required_peak_workers}, has {free_slots}")
    full_plan_guaranteed = None if remaining is None else remaining >= required_fresh_worker_creations
    return CapacityAssessment(
        not blockers, tuple(blockers), remaining, required_fresh_worker_creations, free_slots, required_peak_workers, full_plan_guaranteed
    )


def _validate_nodes(nodes: Sequence[PlanNode]) -> dict[str, PlanNode]:
    by_id = {node.node_id: node for node in nodes}
    if len(by_id) != len(nodes):
        msg = "node IDs must be unique"
        raise ValueError(msg)
    for node in nodes:
        if node.elapsed_seconds < 0:
            msg = f"node {node.node_id} has a negative elapsed budget"
            raise ValueError(msg)
        missing = sorted(set(node.predecessors) - set(by_id))
        if missing:
            msg = f"node {node.node_id} has missing predecessors: {', '.join(missing)}"
            raise ValueError(msg)
    return by_id


def critical_path_seconds(nodes: Sequence[PlanNode], *, sequential: bool) -> int:
    """Return the bounded schedule length, rejecting dependency cycles."""
    by_id = _validate_nodes(nodes)
    if sequential:
        return sum(node.elapsed_seconds for node in nodes)

    visiting: set[str] = set()
    complete: dict[str, int] = {}

    def visit(node_id: str) -> int:
        if node_id in complete:
            return complete[node_id]
        if node_id in visiting:
            msg = f"dependency cycle includes {node_id}"
            raise ValueError(msg)
        visiting.add(node_id)
        node = by_id[node_id]
        predecessor_cost = max((visit(item) for item in node.predecessors), default=0)
        visiting.remove(node_id)
        complete[node_id] = predecessor_cost + node.elapsed_seconds
        return complete[node_id]

    return max((visit(node.node_id) for node in nodes), default=0)


def assess_time_budget(nodes: Sequence[PlanNode], budget: TimeBudget) -> BudgetAssessment:
    """Report worst-case deadline risk while allowing incremental dispatch."""
    values = (budget.coordinator_reserve_seconds, budget.validation_reserve_seconds, budget.fix_revalidation_reserve_seconds)
    if min(values) < 0 or (budget.overall_seconds is not None and budget.overall_seconds < 0):
        msg = "time budgets and reserves must be nonnegative"
        raise ValueError(msg)
    critical_path = critical_path_seconds(nodes, sequential=budget.sequential)
    reserves = sum(values)
    required = critical_path + reserves
    if budget.overall_seconds is None:
        dispatch_window = None
        completion_guaranteed = None
        blockers: tuple[str, ...] = ()
        policy = "per-node-caps-only"
    else:
        dispatch_window = max(0, budget.overall_seconds - reserves)
        completion_guaranteed = required <= budget.overall_seconds
        blockers = ("global deadline leaves no time for worker dispatch after required reserves",) if nodes and dispatch_window == 0 else ()
        policy = "run-until-deadline-account-for-unrun"
    return BudgetAssessment(
        not blockers,
        blockers,
        critical_path,
        budget.coordinator_reserve_seconds,
        budget.validation_reserve_seconds,
        budget.fix_revalidation_reserve_seconds,
        required,
        budget.overall_seconds,
        dispatch_window,
        completion_guaranteed,
        policy,
    )


def bounded_node_dispatch_seconds(*, node_cap_seconds: int, elapsed_seconds: int, budget: TimeBudget) -> int:
    """Return the node timeout allowed by the remaining hard deadline."""
    if node_cap_seconds < 0 or elapsed_seconds < 0:
        msg = "node cap and elapsed time must be nonnegative"
        raise ValueError(msg)
    if budget.overall_seconds is None:
        return node_cap_seconds
    reserves = budget.coordinator_reserve_seconds + budget.validation_reserve_seconds + budget.fix_revalidation_reserve_seconds
    remaining = max(0, budget.overall_seconds - elapsed_seconds - reserves)
    return min(node_cap_seconds, remaining)


def python_packaging_signals(pyproject_text: str) -> tuple[str, ...]:
    """Detect only the packaging signals needed by the graph-side routing guard."""
    document = tomllib.loads(pyproject_text)
    project = document.get("project", {})
    tool = document.get("tool", {})
    setuptools = tool.get("setuptools", {})
    uv = tool.get("uv", {})
    signals: list[str] = []
    if document.get("build-system"):
        signals.append("build-system")
    if project.get("scripts"):
        signals.append("project.scripts")
    if project.get("gui-scripts"):
        signals.append("project.gui-scripts")
    if project.get("entry-points"):
        signals.append("project.entry-points")
    if setuptools.get("package-dir"):
        signals.append("tool.setuptools.package-dir")
    if setuptools.get("py-modules"):
        signals.append("tool.setuptools.py-modules")
    if setuptools.get("packages"):
        signals.append("tool.setuptools.packages")
    if uv.get("package") is True:
        signals.append("tool.uv.package")
    return tuple(signals)


def guard_packaged_python_routing(selected_skills: Iterable[str], pyproject_text: str) -> RoutingGuard:
    """Require build-portability without duplicating the Python routing matrix."""
    selected = list(dict.fromkeys(selected_skills))
    signals = python_packaging_signals(pyproject_text)
    required = bool(signals) and "python-build-portability" not in selected
    if required:
        selected.append("python-build-portability")
    return RoutingGuard(tuple(selected), signals, required)


def reconcile_execution(ledger: ExecutionLedger) -> Assessment:
    """Reconcile node, worker, skill, and validator lifecycle sets."""
    selected = set(ledger.selected_nodes)
    accepted = set(ledger.accepted_nodes)
    blocked_after = set(ledger.blocked_after_execution)
    blocked_before = set(ledger.blocked_before_execution)
    attempts = set(ledger.worker_attempts)
    created = set(ledger.workers_created)
    creation_failures = set(ledger.worker_creation_failures)
    executed_skills = set(ledger.skills_executed)
    validator_plan = set(ledger.planned_validators)
    validator_runs = set(ledger.executed_validators)
    validator_skips = set(ledger.validators_not_run)
    outcomes = accepted | blocked_after | blocked_before
    checks = (
        (selected != outcomes, "selected nodes do not reconcile with accepted and blocked lifecycle outcomes"),
        (bool((accepted & blocked_after) or (accepted & blocked_before) or (blocked_after & blocked_before)), "node lifecycle outcome sets overlap"),
        (bool(attempts != created | creation_failures or created & creation_failures), "worker creation attempts do not reconcile"),
        (not created <= attempts or not executed_skills <= created, "created-worker or executed-skill records lack a worker attempt"),
        (not (accepted | blocked_after) <= created, "executed node outcomes lack a created worker"),
        (not accepted <= executed_skills or not executed_skills <= accepted | blocked_after, "accepted-node and executed-skill records do not reconcile"),
        (bool(blocked_before & created), "pre-execution blocked nodes incorrectly claim a created worker"),
        (bool(validator_plan != validator_runs | validator_skips or validator_runs & validator_skips), "planned validators do not reconcile"),
        (not validator_plan <= selected, "planned validators are not selected graph nodes"),
        (not validator_runs <= accepted, "executed validators lack an accepted node result"),
    )
    blockers = [message for failed, message in checks if failed]
    return Assessment(not blockers, tuple(blockers))
