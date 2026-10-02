"""Capacity-aware lane selection without creating workers or changing coverage."""

from typing import Any


def _capacity_state(capacity: dict[str, Any] | None, occupied_workers: int) -> tuple[str, int]:
    if capacity is None:
        return "unknown", 1
    source = capacity.get("source")
    if not isinstance(source, str) or not source.strip():
        msg = "worker capacity requires an authoritative aggregate evidence source"
        raise ValueError(msg)
    limit = capacity.get("concurrent_worker_limit")
    active = capacity.get("active_workers")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or not isinstance(active, int) or isinstance(active, bool) or active < 0:
        msg = "worker capacity requires a positive integer limit and nonnegative integer active count"
        raise ValueError(msg)
    if active < occupied_workers:
        msg = "worker capacity understates journal-bound in-flight workers"
        raise ValueError(msg)
    free = limit - active
    if free < 0:
        msg = "active_workers exceeds concurrent_worker_limit"
        raise ValueError(msg)
    return ("known-exhausted" if free == 0 else "known-available"), free


def _failure_action(failure: dict[str, Any] | None, capacity_state: str) -> str | None:
    if failure is None:
        return None
    if failure["failure_kind"] == "capacity" and failure["attempts"] == 1 and capacity_state != "known-exhausted":
        return "bounded-retry"
    return "coordinator-fallback"


def select_execution_lanes(  # noqa: C901, PLR0912 - one selection preserves reservations, capacity, and serialization together.
    document: dict[str, Any], *, modes: dict[str, str], entries: dict[str, dict[str, Any]], ready: dict[str, Any]
) -> dict[str, Any]:
    """Reserve one adaptive coordinator lane and only available worker lanes."""
    ready_ids = ready["ready_node_ids"]
    in_flight = ready["lifecycle"]["in_flight_node_ids"]
    occupied_workers = sum(entries[node_id]["dispatch"]["execution_location"] == "worker" for node_id in in_flight)
    capacity_state, free_workers = _capacity_state(document.get("worker_capacity"), occupied_workers)
    declared = document.get("reserved_node_ids", [])
    if len(declared) != len(set(declared)) or set(declared) - set(entries):
        msg = "reserved_node_ids must contain unique planned nodes"
        raise ValueError(msg)
    # Started/accepted reservations are now accounted for by the journal. Keep
    # unstarted reservations distinct from actual creation and execution.
    reserved = [node_id for node_id in declared if node_id in ready_ids]
    failure = document.get("creation_failure")
    action = _failure_action(failure, capacity_state)
    failed_id = failure["node_id"] if failure else None
    if failed_id is not None:
        if failed_id not in ready_ids or entries[failed_id]["dispatch"]["execution_location"] != "worker" or modes[failed_id] != "audit":
            msg = "creation_failure requires an unstarted dependency-ready audit worker dispatch"
            raise ValueError(msg)
        if failed_id in reserved:
            reserved.remove(failed_id)
    reserved_workers = sum(entries[node_id]["dispatch"]["execution_location"] == "worker" for node_id in reserved)
    free_workers = max(0, free_workers - reserved_workers)
    coordinator_busy = any(entries[node_id]["dispatch"]["execution_location"] == "coordinator" for node_id in (*in_flight, *reserved))
    serial_busy = any(modes[node_id] not in {"audit", "independent-review"} for node_id in (*in_flight, *reserved))
    candidates = [node_id for node_id in ready_ids if node_id not in reserved]
    coordinator_id = None
    workers: list[str] = []
    if not coordinator_busy and not serial_busy:
        if action == "coordinator-fallback" and failed_id is not None and modes[failed_id] == "audit":
            coordinator_id = failed_id
        else:
            coordinator_id = next((node_id for node_id in candidates if modes[node_id] == "audit" and node_id != failed_id), None)
    if coordinator_id is not None:
        candidates.remove(coordinator_id)
    if not serial_busy:
        if action == "bounded-retry" and failed_id is not None and free_workers:
            # This is the same immutable dispatch after a bounded progress wait,
            # not a new creation receipt. Do not exceed known free capacity.
            workers.append(failed_id)
            free_workers -= 1
        parallel = [
            node_id
            for node_id in candidates
            if modes[node_id] in {"audit", "independent-review"} and entries[node_id]["dispatch"]["execution_location"] == "worker" and node_id != failed_id
        ]
        workers.extend(parallel[:free_workers])
        if not workers and coordinator_id is None and not in_flight and not reserved:
            serial = next((node_id for node_id in candidates if modes[node_id] != "independent-review" and node_id != failed_id), None)
            if serial is not None:
                if entries[serial]["dispatch"]["execution_location"] == "coordinator" or capacity_state == "known-exhausted":
                    coordinator_id = serial
                elif free_workers:
                    workers.append(serial)
    selected = [*workers, *([coordinator_id] if coordinator_id is not None else [])]
    reservations = [*reserved, *selected]
    return {
        "capacity_state": capacity_state,
        "coordinator_node_id": coordinator_id,
        "worker_node_ids": workers,
        "reserved_node_ids": reservations,
        "deferred_node_ids": [node_id for node_id in ready_ids if node_id not in selected],
        "creation_failure": failure,
        "creation_failure_action": action,
        "retry_after_seconds": 30 if action == "bounded-retry" else 0,
    }
