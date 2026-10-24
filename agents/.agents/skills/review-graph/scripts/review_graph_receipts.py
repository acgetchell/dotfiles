"""Small CLI receipts referencing complete immutable operation artifacts."""

import json
from pathlib import Path
from typing import Any

from review_graph_integrity import digest_bytes


def artifact_reference(path: Path) -> dict[str, str]:
    """Bind a displayed artifact path to its actual saved bytes."""
    return {"path": str(path.resolve()), "digest": digest_bytes(path.read_bytes())}


def dispatch_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Expose the worker handoff without copying its inspection context."""
    dispatch = entry.get("dispatch", entry)
    return {
        "node_id": entry["node_id"],
        "skill_id": dispatch["skill_id"],
        "mode": dispatch["mode"],
        "selection_reason": dispatch["selection_reason"][:240],
        "result_contract": entry["result_contract"],
        "execution_location": entry.get("dispatch", entry)["execution_location"],
        **({"executor_requirements": entry["dispatch"]["executor_requirements"]} if "executor_requirements" in entry.get("dispatch", {}) else {}),
        **({"timing_prerequisite": entry["dispatch"]["timing_prerequisite"]} if "timing_prerequisite" in entry.get("dispatch", {}) else {}),
        "worker_input": artifact_reference(Path(entry.get("worker_execution_path", entry["worker_input_path"]))),
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
    if "control_result_path" in output:
        receipt["control_result"] = artifact_reference(Path(output["control_result_path"]))
    return receipt


def _validation_reconciliation_receipt(output: dict[str, Any]) -> dict[str, Any]:
    """Expose source rebinding without copying full execution and capture documents."""
    if reconciliation := output.get("validation_reconciliation"):
        return {
            "validation_reconciliation": {
                "blockers": reconciliation["blockers"],
                "requirement_count": len(reconciliation["requirements"]),
                "source_rebinding_count": sum("reuse_binding" in item for item in reconciliation["requirements"]),
                "details_field": "validation_reconciliation",
                "identity_changes": [
                    {"requirement_id": item["requirement_id"], "changed_identity_fields": item["reuse_binding"]["output_binding"]["changed_identity_fields"]}
                    for item in reconciliation["requirements"]
                    if item.get("reuse_binding", {}).get("output_binding")
                ],
            }
        }
    return {}


def stage_receipt(operation: str, output_path: Path, output: dict[str, Any]) -> dict[str, Any]:
    """Keep proof bodies on disk and return only stage status and handoff references."""
    saved = output_path.read_bytes()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "operation": operation,
        "output": {"path": str(output_path.resolve()), "digest": digest_bytes(saved)},
        "output_fields": sorted(json.loads(saved)),
    }
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
        "preflight_blocked_nodes",
        "creation_failure_action",
        "retry_after_seconds",
        "node_counts",
        "recheck_reason_counts",
        "audit_reuse_counts",
        "validation_log_archives",
        "phase_accounting",
        "review_lifecycle",
        "repair_epoch",
        "transition_kind",
        "proof_limitations",
        "next_command",
        "next_action",
        "stop_reason",
        "cancel_node_ids",
        "runtime_snapshot",
        "delivery_profile",
        "repairs_completed",
        "validation",
        "local_validation",
        "hosted_ci",
        "outstanding_hosted_ci",
        "remaining_findings",
        "incomplete_node_ids",
    ):
        if key in output:
            receipt[key] = output[key]
    plan = output.get("plan", {})
    receipt.update(_validation_reconciliation_receipt(output))
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
        receipt["in_flight_node_ids"] = output["lifecycle"]["in_flight_node_ids"]
        receipt["completion_order"] = "Compile published payloads for finished in-flight nodes before lowering worker occupancy or admitting repairs."
    receipt.update(_continuation_receipt(output))
    return receipt
