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


def launch_manifest(output: dict[str, Any]) -> dict[str, Any]:
    """Project launch identities and continuations without nested dispatch contracts."""
    requirements = {item["node_id"]: item for item in output.get("worker_requirements", [])}
    return {
        "schema_version": 1,
        "nodes": [_launch_node(entry, requirements) for entry in output.get("ready_dispatches", output.get("dispatches", []))],
        **_continuation_receipt(output),
    }


def _launch_node(entry: dict[str, Any], requirements: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Read canonical identity lazily for legacy flattened compact ready entries."""
    dispatch = entry.get("dispatch")
    if dispatch is None:
        dispatch = json.loads(Path(entry["worker_input_path"]).read_bytes())["dispatch"]
    return {
        "node_id": entry["node_id"],
        "skill_id": dispatch["skill_id"],
        "skill_path": dispatch["skill_path"],
        "mode": dispatch["mode"],
        "result_contract": entry["result_contract"],
        "execution_location": dispatch["execution_location"],
        "execution_view": artifact_reference(Path(entry.get("worker_execution_path", entry["worker_input_path"]))),
        **{key: dispatch[key] for key in ("executor_requirements", "timing_prerequisite") if key in dispatch},
        **({"worker_requirement": requirements[entry["node_id"]]} if entry["node_id"] in requirements else {}),
    }


def _launch_receipt(operation: str, output: dict[str, Any]) -> dict[str, Any]:
    receipt: dict[str, Any] = {}
    for key in ("dispatches", "ready_dispatches"):
        if key in output:
            if operation not in {"materialize-dispatches", "schedule-ready"}:
                receipt[key] = [dispatch_summary(entry) for entry in output[key]]
            receipt["node_count"] = len(output[key])
    if receipt:
        receipt["launch_manifest"] = launch_manifest(output)
    return receipt


def _lifecycle_receipt(operation: str, output: dict[str, Any]) -> dict[str, Any]:
    if "lifecycle" not in output:
        return {}
    counts = {key.removesuffix("_node_ids"): len(value) for key, value in output["lifecycle"].items()}
    counts.update(ready=len(output["ready_dispatches"]), waiting=len(output["waiting"]))
    if operation == "schedule-ready":
        counts.update({key: len(output[f"{key}_node_ids"]) for key in ("worker", "reserved", "deferred") if f"{key}_node_ids" in output})
    return {
        "node_counts": counts,
        "waiting": output["waiting"],
        **({"in_flight_node_ids": output["lifecycle"]["in_flight_node_ids"]} if operation != "schedule-ready" else {}),
        "completion_order": "Compile published payloads for finished in-flight nodes before lowering worker occupancy or admitting repairs.",
    }


def _coverage_receipt(output: dict[str, Any]) -> dict[str, Any]:
    if "coverage_reuse_decisions" not in output:
        return {}
    return {
        "coverage_continuation": [
            {
                "node_id": item["node_id"],
                "inherited_units": sum(unit["disposition"] == "reused" for unit in item["units"]),
                "instruction_review_units": sum(unit["disposition"] == "instruction-review" for unit in item["units"]),
                "recheck_units": sum(unit["disposition"] == "recheck" for unit in item["units"]),
                "next_action": (
                    "Read this node's execution view. Use only its bound coverage_reuse; preserve inherited findings, validation and handoffs. "
                    "If coverage_reuse is absent, inspect all owned paths. Whole-audit and uncertain dependencies cannot be silently partitioned after review."
                ),
                **({"reason": item["reason"]} if "reason" in item else {}),
            }
            for item in output["coverage_reuse_decisions"]
        ]
    }


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
        "instruction_preflight",
        "captured_path_inventory_reference",
        "retained_blocked_node_ids",
        "delivery_profile",
        "repairs_completed",
        "validation",
        "local_validation",
        "hosted_ci",
        "outstanding_hosted_ci",
        "remaining_findings",
        "incomplete_node_ids",
        "verification_followup",
        "permitted_paths",
    ):
        if key in output:
            receipt[key] = output[key]
    plan = output.get("plan", {})
    receipt.update(_validation_reconciliation_receipt(output))
    if plan:
        receipt["dispatch_allowed"] = plan["dispatch_allowed"]
        receipt["blockers"] = plan.get("blockers", [])
        receipt["node_count"] = len(plan["actual_worker_nodes"])
    if operation != "schedule-ready":
        receipt.update({key: output[key] for key in ("worker_node_ids", "reserved_node_ids", "deferred_node_ids") if key in output})
    receipt.update(_launch_receipt(operation, output))
    receipt.update(_coverage_receipt(output))
    for key in ("artifact_path", "metadata_path", "worker_payload_path"):
        if key in output:
            receipt[key.removesuffix("_path")] = artifact_reference(Path(output[key]))
    if "journal_event" in output:
        receipt["status"] = output["journal_event"]["status"]
    receipt.update(_lifecycle_receipt(operation, output))
    receipt.update(_continuation_receipt(output))
    return receipt
