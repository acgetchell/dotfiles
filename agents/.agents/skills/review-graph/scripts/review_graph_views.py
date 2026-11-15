"""Small worker execution views; canonical provenance stays in immutable sidecars."""

import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from review_graph_integrity import digest_bytes
from review_graph_isolation import ISOLATION_INSTRUCTIONS
from review_graph_results import parse_json_object

_EXECUTION_FIELDS = (
    "node_id",
    "mode",
    "skill_id",
    "skill_path",
    "reference_paths",
    "instruction_paths",
    "instruction_context",
    "required_read_paths",
    "captured_path_inventory_reference",
    "provenance_examples",
    "repository_root",
    "authorization",
    "state_verification_command",
    "handoff_destinations",
    "execution_context",
    "owned_paths",
    "review_scope_exclusions",
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
    "source_discovery",
)


def _render_execution_view(entry: dict[str, Any], canonical_bytes: bytes) -> bytes:
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
        "self_dispatch_recovery": {
            "worker_execution_path": entry["worker_execution_path"],
            "worker_input_path": entry["worker_input_path"],
            "policy": "Use these exact paths; if missing, ask the coordinator to resend this node's ready_dispatches entry. Never infer schedule paths.",
        },
        "publish_command": dispatch["worker_payload_persistence"]["publish_command"],
        "instructions": (
            "Read skill/instructions and conditional references, then perform only this dispatched contract. Read the payload schema before publication. "
            "Follow instruction_context.reload_policy after compaction or fresh-worker continuation; disk identities never attest a completed read. "
            "Publish semantic JSON through publish_command (stdin); the runtime assembles provenance, canonical evidence and receipts. "
            "Record exact text for each actual shell execution in commands_executed, including newlines; prose is not command provenance. "
            "Independent bounded cat/sed/rg reads run together may occupy one newline-separated entry; never split or infer past executions. "
            "Use source_discovery for captured path selection after the before capture; its policy lists supported selectors. "
            "Exact generated instruction, capture, discovery and publication operations may share newline-separated entries with bounded reads. "
            "Publication may use stdin or '<' with an external file containing exactly this node's submitted payload. "
            "Inspect publication reuse_eligibility diagnostics before acceptance; unknown commands and unbound external reads prevent reuse. "
            "Record truthful limitations. Command policy is authoritative; delegate validator-owned checks. "
            "Use handoff_destinations to choose an exact catalog_id for handoffs. "
            "Use the shared read-only source packet when supplied; each specialist makes its own judgment. "
            "Navigation gives lexical declaration spans, not complete inspection. Every complete:false excerpt requires direct reads of missing bodies "
            "and omitted declarations; packet observations alone do not establish complete coverage. "
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
            "When supplied, read captured_path_inventory_reference and retain dependency, historical/archive and user-excluded dispositions "
            "in the coverage assessment. "
            "These assessments do not establish owned audit coverage. "
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
    if "execution_view_instructions" in entry:
        instructions = entry["execution_view_instructions"]
        if not isinstance(instructions, str) or not instructions:
            msg = "execution view instructions must be nonempty bound text"
            raise ValueError(msg)
        view["instructions"] = instructions
    return (json.dumps(view, indent=2, sort_keys=True) + "\n").encode()


def bind_execution_instructions(entry: dict[str, Any]) -> None:
    """Bind new guidance before hashing the canonical input, without a digest cycle."""
    candidate = {key: value for key, value in entry.items() if key != "execution_view_instructions"}
    canonical_bytes = (json.dumps(candidate, indent=2, sort_keys=True) + "\n").encode()
    view = parse_json_object(execution_view_bytes(candidate, canonical_bytes))
    instructions = view.get("instructions")
    if not isinstance(instructions, str) or not instructions:
        msg = "execution renderer did not produce nonempty instruction text"
        raise ValueError(msg)
    entry["execution_view_instructions"] = instructions


@lru_cache(maxsize=128)
def _frozen_view(scripts: str, manifest_digest: str, canonical_bytes: bytes) -> bytes:
    """Render only after the caller verifies the complete immutable runtime inventory."""
    code = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); "
        "import review_graph_views as views; raw = sys.stdin.buffer.read(); "
        "render = getattr(views, '_render_execution_view', views.execution_view_bytes); "
        "sys.stdout.buffer.write(render(json.loads(raw), raw))"
    )
    try:
        result = subprocess.run(  # noqa: S603 - original interpreter and verified frozen renderer, no submitted commands.
            [sys.executable, "-E", "-s", "-B", "-c", code, scripts], input=canonical_bytes, capture_output=True, check=True, timeout=30
        )
    except subprocess.TimeoutExpired as error:
        msg = "historical execution renderer exceeded 30 seconds; preserve the snapshot and retained Python runtime"
        raise ValueError(msg) from error
    except subprocess.CalledProcessError as error:
        diagnostic = (error.stderr or b"").decode("utf-8", errors="backslashreplace")[-1000:]
        msg = f"historical execution renderer exited {error.returncode}; retained runtime diagnostic: {diagnostic}"
        raise ValueError(msg) from error
    view = parse_json_object(result.stdout)
    if view.get("schema_version") != 1 or not isinstance(view.get("instructions"), str) or not view["instructions"]:
        msg = "historical execution renderer produced an invalid view"
        raise ValueError(msg)
    return result.stdout


def execution_view_bytes(entry: dict[str, Any], canonical_bytes: bytes) -> bytes:
    """Verify historical guidance against its frozen authority, never today's prose."""
    if "execution_view_instructions" not in entry and (reference := entry["dispatch"].get("runtime_snapshot")):
        from review_graph_session import verify_snapshot  # noqa: PLC0415 - avoid the runtime/session initialization cycle.

        # Reverify even on cache hits: changed resources must never inherit trust.
        manifest = verify_snapshot(reference)
        relative = "skills/review-graph/scripts/review_graph_views.py"
        if relative not in dict(manifest.files):
            msg = "frozen runtime lacks the execution view renderer"
            raise ValueError(msg)
        renderer = Path(reference["path"]).parent / relative
        if renderer.read_bytes() != Path(__file__).read_bytes():
            return _frozen_view(str(renderer.parent), reference["digest"], canonical_bytes)
    return _render_execution_view(entry, canonical_bytes)
