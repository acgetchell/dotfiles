"""Small CLI receipts referencing complete immutable operation artifacts."""

from pathlib import Path
from typing import Any

from review_graph_integrity import digest_bytes


def artifact_reference(path: Path) -> dict[str, str]:
    """Bind a displayed artifact path to its actual saved bytes."""
    return {"path": str(path.resolve()), "digest": digest_bytes(path.read_bytes())}


def dispatch_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Expose the worker handoff without copying its inspection context."""
    return {
        "node_id": entry["node_id"],
        "result_contract": entry["result_contract"],
        "execution_location": entry.get("dispatch", entry)["execution_location"],
        "worker_input": artifact_reference(Path(entry["worker_input_path"])),
    }


def _continuation_receipt(output: dict[str, Any]) -> dict[str, Any]:
    receipt: dict[str, Any] = {}
    next_inputs = {
        key: output[key]
        for key in (
            "lifecycle_input_path",
            "schedule_input_path",
            "dispatches_path",
            "journal_path",
            "capture_path",
            "current_capture_path",
            "next_ready_output_dir",
        )
        if key in output
    }
    if next_inputs:
        receipt["next_operation_inputs"] = next_inputs
    if "continuation_path" in output:
        receipt["continuation"] = artifact_reference(Path(output["continuation_path"]))
    return receipt


def stage_receipt(operation: str, output_path: Path, output: dict[str, Any]) -> dict[str, Any]:
    """Keep proof bodies on disk and return only stage status and handoff references."""
    receipt: dict[str, Any] = {"schema_version": 1, "operation": operation, "output": artifact_reference(output_path)}
    for key in (
        "status",
        "blockers",
        "plan_digest",
        "source_state",
        "node_id",
        "output_generation",
        "complete",
        "graph_proof_status",
        "repository_validation_status",
        "repository_readiness",
        "summary",
        "capacity_state",
        "coordinator_node_id",
        "worker_node_ids",
        "reserved_node_ids",
        "deferred_node_ids",
        "creation_failure_action",
        "retry_after_seconds",
        "node_counts",
        "recheck_reason_counts",
    ):
        if key in output:
            receipt[key] = output[key]
    plan = output.get("plan", {})
    if plan:
        receipt["dispatch_allowed"] = plan["dispatch_allowed"]
        receipt["blockers"] = plan.get("blockers", [])
        receipt["node_count"] = len(plan["actual_worker_nodes"])
    for key in ("dispatches", "ready_dispatches"):
        if key in output:
            receipt[key] = [dispatch_summary(entry) for entry in output[key]]
            receipt["node_count"] = len(output[key])
    for key in ("artifact_path", "metadata_path", "worker_payload_path"):
        if key in output:
            receipt[key.removesuffix("_path")] = artifact_reference(Path(output[key]))
    if "journal_event" in output:
        receipt["status"] = output["journal_event"]["status"]
    if "lifecycle" in output:
        receipt["node_counts"] = {key.removesuffix("_node_ids"): len(value) for key, value in output["lifecycle"].items()}
        receipt["node_counts"].update(ready=len(output["ready_dispatches"]), waiting=len(output["waiting"]))
        receipt["waiting"] = output["waiting"]
    receipt.update(_continuation_receipt(output))
    return receipt
