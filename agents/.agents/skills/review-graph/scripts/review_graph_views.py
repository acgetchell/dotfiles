"""Small worker execution views; canonical provenance stays in immutable sidecars."""

import json
from typing import Any

from review_graph_integrity import digest_bytes
from review_graph_isolation import ISOLATION_INSTRUCTIONS

_EXECUTION_FIELDS = (
    "node_id",
    "mode",
    "skill_id",
    "skill_path",
    "reference_paths",
    "instruction_paths",
    "required_read_paths",
    "provenance_examples",
    "repository_root",
    "authorization",
    "state_verification_command",
    "handoff_destinations",
    "execution_context",
    "owned_paths",
    "command_policy",
    "worker_payload_path",
    "coverage_reuse",
    "shared_inspection_evidence",
    "executor_requirements",
    "workspace_policy",
    "predecessor_evidence_ids",
    "selection_reason",
    "synthesis_examples",
    "change_target",
    "planned_paths",
    "planned_path_line_bounds",
    "adversarial_checks",
    "adversarial_check_ids",
    "source_state",
    "validation_unit",
    "launch_recovery",
    "execution_recovery",
    "timing_prerequisite",
    "validation_observations",
    "audit_observations",
)


def execution_view_bytes(entry: dict[str, Any], canonical_bytes: bytes) -> bytes:
    """Preserve semantic tasks and commands without duplicating compiler identities."""
    dispatch = entry["dispatch"]
    mode = dispatch["mode"]
    schema = dispatch["payload_schema"]
    view = {
        "schema_version": 1,
        "dispatch": {key: dispatch[key] for key in _EXECUTION_FIELDS if key in dispatch},
        "payload_schema": {
            key: schema[key] for key in ("path", "digest", "template", "completed_example", "required_fields", "optional_shapes") if key in schema
        },
        "canonical_input": {"path": entry["worker_input_path"], "digest": digest_bytes(canonical_bytes)},
        "publish_command": dispatch["worker_payload_persistence"]["publish_command"],
        "instructions": (
            "Read skill/instructions and conditional references, then perform only this dispatched contract. Read the payload schema before publication. "
            "Publish semantic JSON through publish_command (stdin); the runtime assembles provenance, canonical evidence and receipts. "
            "Record actual reads/commands and truthful limitations. Command policy is authoritative; delegate validator-owned checks. "
            "Use handoff_destinations to choose an exact catalog_id for handoffs. "
            "Use the shared read-only source packet when supplied; each specialist makes its own judgment. "
            "Every complete:false excerpt requires direct reads of the missing source; packet observations alone do not establish complete coverage. "
            "Full provenance and recovery commands are available through canonical_input when needed."
        ),
    }
    if "provenance_examples" in dispatch:
        view["instructions"] += (
            " provenance_examples are illustrative fragments, not performed work; merge only actual reads/commands. "
            "files_inspected is owned-only; record required instruction reads there or in nearby_contract_owners according to scope. "
            "git_dependencies[].command is singular and matches an exact commands_executed entry. "
            "source-discovery permits only a plain local git diff with optional HEAD; fixed-base branch comparisons use head. "
            "Replace origin/main with the captured base."
        )
    if mode == "audit":
        if dispatch.get("fresh_context"):
            view["instructions"] += " " + ISOLATION_INSTRUCTIONS
        view["instructions"] += (
            " Inspect recheck units only when coverage_reuse is present; retain inherited findings/validation/handoffs. "
            "For instruction-review units, inspect every supplied input delta against this contract, its rules, commands, applicability and obligations. "
            "A fresh worker may submit instruction_reconciliations with reasons for all four dimensions and actual changed-document reads. "
            "Only unchanged judgments preserve source evidence; material changes require full affected-unit inspection, and uncertainty blocks acceptance. "
            "Without reconciliation, inspect all pending units. Full before/after documents remain in the bound coverage proof when context is needed. "
            "Never claim reused paths as fresh reads. "
            "Optional coverage_units partitions all owned paths, findings and dependencies; record dependency uncertainty. "
            "Put source gaps in scope_limitations, uncertainty in unresolved_uncertainties, platform caveats in requirement-bound validation_limits. "
            "Unavailable checks block readiness independently of source judgments; failed checks reopen their owning contract. "
            "Record exact Git commands with semantic git_dependencies; unknown dependencies remain conservative."
        )
    elif mode == "independent-review":
        view["instructions"] += " " + ISOLATION_INSTRUCTIONS
        view["instructions"] += (
            " Work fresh and conclusion-blind from raw source only. Account for every owned path and dispatched adversarial check. "
            "Pending/delegated tests are not passed checks. Observe before/after captures; "
            "incomplete inspection or semantic uncertainty requires blocked status."
        )
    elif mode == "validation":
        view["instructions"] += (
            " Apply executor permissions; report blocked if unavailable. Omit artifacts (runtime owns snapshots/digests). "
            "Before execution, run validation_observations.before.capture_command then its workspace_command. "
            "Read the prepared timing manifest; execute its exact launch commands in the dispatched environment and retain the receipts. "
            "An existing receipt is an execution attempt: recover it without rerunning. "
            "After execution, run validation_observations.after.capture_command then its workspace_command before publishing. "
            "If validation_observations is absent, obtain both observations from the coordinator. "
            "executions[].artifact_paths contains exact allowed output roots only; children belong in evidence text."
            " Declare semantic git_dependencies for the whole invoked recipe; [] means source-only, omission remains conservative."
        )
    else:
        view["instructions"] += (
            " Use the hashed synthesis bundle and accepted predecessor IDs. Report readiness separately from proof and local validation. "
            "One diagnostic-guided schema retry and one consolidated semantic correction are permitted; another failure blocks the node."
        )
    if "audit_observations" in dispatch:
        view["dispatch"].pop("state_verification_command", None)
        view["instructions"] += (
            " Before source inspection, run audit_observations.before.capture_command and require its completed compact receipt. "
            "After inspection, run audit_observations.after.capture_command. These commands persist complete immutable captures and receipts; "
            "compile-node requires those exact files. Never copy expected fingerprints into a capture or reconstruct a missing before observation."
        )
    return (json.dumps(view, indent=2, sort_keys=True) + "\n").encode()
