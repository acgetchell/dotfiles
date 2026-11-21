"""Worker payloads, publication, and compiled evidence for review-graph tests."""

import json
import subprocess
from pathlib import Path
from typing import Any

import review_graph_runtime as runtime
from review_graph_independent import CHECK_LABELS
from review_graph_runtime import (
    JournalEventRequest,
    _expected_evidence_id,
    append_journal_event,
    capture_workspace_snapshot,
    compile_review,
    compile_validation,
    materialize_dispatches,
)
from test_support_review_graph import SKILL_ROOT, STATE_FIXTURE, _json_plan, _sparse_plan
lazy from review_graph_plan import GraphPlan


def _compact_audit_payload(entry: dict[str, Any], *, commands: tuple[str, ...] = ()) -> dict[str, Any]:
    """Build a no-findings audit covering the assigned files and the specified commands."""
    return {
        "changes": [],
        "command_policy_attested": True,
        "commands_executed": list(commands),
        "files_inspected": entry["dispatch"]["owned_paths"],
        "findings": [],
        "handoffs": [],
        "limitations": [],
        "nearby_contract_owners": list(entry["dispatch"].get("required_read_paths", [])),
        "scope_limitations": [],
        "status": "no-findings",
        "validation_requirements": [],
    }


def _compact_independent_payload(dispatch: dict[str, Any]) -> dict[str, Any]:
    """Build independent evidence covering the dispatch's required reads at its assigned source state."""
    return {
        "nearby_contract_owners": list(dispatch.get("required_read_paths", [])),
        "status": "no-findings",
        "files_inspected": list(dispatch["planned_paths"]),
        "branches": "Captured change and adjacent control flow inspected.",
        "boundary_cases": "Inspection covers the dispatched adversarial cases.",
        "tests": "Read the test contracts; execution remains validator-owned.",
        "findings": [],
        "no_finding_evidence": [],
        "adversarial_checks": [
            {
                "check_id": check_id,
                "evidence": "The fixture has a single unconditional transition and no external calls.",
                "inspected_paths": list(dispatch["planned_paths"]),
            }
            for check_id, label in CHECK_LABELS.items()
            if label in dispatch["adversarial_checks"]
        ],
        "handoffs": [],
        "before_state": list(dispatch["source_state"]),
        "after_state": list(dispatch["source_state"]),
        "source_mutated": False,
        "git_mutated": False,
        "command_policy_attested": True,
        "commands_executed": [],
        "limitations": [],
    }


def _execution_payload(entry: dict[str, Any], result: str, exit_code: object, elapsed: object) -> dict[str, Any]:
    """Encode a fixture validation outcome with the corresponding execution details and limitations."""
    unit = entry["dispatch"]["validation_unit"]
    return {
        "schema_version": 3,
        "status": "blocked" if result == "not-run" else result,
        "executions": [
            {
                "artifact_paths": [],
                "command": unit["commands"][0],
                "elapsed": elapsed,
                "evidence": "fixture command result or reason execution could not start",
                "executor": entry["node_id"],
                "exit_code": exit_code,
                "result": result,
                "working_directory": unit["working_directories"][0],
            }
        ],
        "limitations": ["fixture execution unavailable"] if result in {"blocked", "not-run"} else [],
    }


def _typed_synthesis_payload(dispatch: dict[str, Any], payload: dict[str, Any], plan: GraphPlan | None = None) -> dict[str, Any]:
    """Populate synthesis-specific predecessor and validation records when the dispatch requires them."""
    if dispatch.get("mode") != "synthesis":
        return payload
    requirements = {_expected_evidence_id(node, plan): list(node.requirement_ids) for node in plan.actual_worker_nodes} if plan else {}
    reused = {key for _requirement, key in plan.exact_reused_review_evidence} if plan else set()
    platforms = (
        {
            _expected_evidence_id(node, plan): unit.platform
            for node in plan.actual_worker_nodes
            for unit in plan.coalesced_validation_units
            if unit.node_id == node.node_id
        }
        if plan
        else {}
    )
    if plan:
        for requirement, evidence_id in plan.exact_reused_review_evidence:
            requirements.setdefault(evidence_id, []).append(requirement)
    return {
        "changes": [],
        **payload,
        "readiness_verdict": "ready",
        "verdict_reasons": ["All required evidence reconciles."],
        "predecessor_coverage": [
            {"evidence_id": key, "requirement_ids": requirements.get(key, []), "disposition": "reused" if key in reused else "accepted"}
            for key in dispatch["predecessor_evidence_ids"]
        ],
        "routing_closure": {"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
        "validation_reconciliation": [
            {
                "evidence_id": key,
                "requirement_ids": requirements.get(key, []),
                "result": "passed",
                "platform": platforms.get(key, "current host"),
                "execution_mode": "native",
            }
            for key in dispatch["predecessor_evidence_ids"]
            if key.startswith("validation:")
        ],
        "cross_surface_risks": [],
    }


def _compile_cli_paths(tmp_path: Path, document: dict[str, Any], dispatches: dict[str, Any]) -> tuple[Path, Path, Path]:
    """Write lifecycle, dispatch, and capture inputs for a file-based compile-node invocation."""
    lifecycle_path = tmp_path / "lifecycle.json"
    dispatch_path = tmp_path / "dispatches.json"
    capture_path = tmp_path / "capture.json"
    lifecycle_path.write_text(json.dumps({"plan": document["plan"], "source_state": document["source_state"]}), encoding="utf-8")
    dispatch_path.write_text(json.dumps(dispatches), encoding="utf-8")
    capture_path.write_text(
        json.dumps(
            {
                "captured_worktree_fingerprint": document["source_state"][1],
                "repository_state_fingerprint": document["source_state"][2],
                "scope_fingerprint": document["source_state"][0],
            }
        ),
        encoding="utf-8",
    )
    return lifecycle_path, dispatch_path, capture_path


def _publish_worker_bytes(entry: dict[str, Any], payload_bytes: bytes) -> dict[str, Any]:
    """Exercise the materialized stdin protocol for compiler and lifecycle fixtures."""
    persistence = entry["dispatch"]["worker_payload_persistence"]
    review = subprocess.run(persistence["review_command"], input=payload_bytes, capture_output=True, check=True, timeout=30)  # noqa: S603
    identity = json.loads(review.stdout)["approval_identity"]
    published = subprocess.run(  # noqa: S603 - runtime-materialized commands for this test's proof store.
        [*persistence["command"], "--approval-identity", identity], input=payload_bytes, capture_output=True, check=True, timeout=30
    )
    return json.loads(published.stdout)


def _compile_passing_validation(dispatch: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Compile a passing result for every planned command, including required workspace snapshots."""
    if dispatch["workspace_policy"]["snapshots_required"]:
        snapshot = capture_workspace_snapshot(dispatch)["records"]
        dispatch.update({"workspace_after": snapshot, "workspace_before": snapshot})
    unit = dispatch["validation_unit"]
    payload = {
        "schema_version": 3,
        "artifacts": [],
        "executions": [
            {
                "artifact_paths": [],
                "command": command,
                "elapsed": "0s",
                "evidence": "command exited successfully",
                "executor": dispatch["node_id"],
                "exit_code": 0,
                "result": "passed",
                "working_directory": working_directory,
            }
            for command, working_directory in zip(unit["commands"], unit["working_directories"], strict=True)
        ],
        "limitations": [],
        "status": "passed",
    }
    return compile_validation({"dispatch": dispatch, "payload": payload})


def _compile_materialized_evidence(  # noqa: PLR0913
    tmp_path: Path,
    *,
    handoff_catalog_id: str | None = None,
    resolved_handoff: bool = False,
    plan: GraphPlan | None = None,
    skip_node_ids: tuple[str, ...] = (),
    late_requirements: list[dict[str, Any]] | None = None,
    late_requirements_by_node: dict[str, list[dict[str, Any]]] | None = None,
    reference_planned_validation: bool = False,
    audit_findings: list[dict[str, Any]] | None = None,
    reused_sources: list[dict[str, str]] | None = None,
) -> tuple[GraphPlan, list[dict[str, str]]]:
    """Materialize a plan and compile its worker artifacts and evidence sidecars."""
    plan = plan or _sparse_plan()
    materialized = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "sources": reused_sources or [],
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    sources: list[dict[str, str]] = []
    for entry in materialized["dispatches"]:
        if entry["node_id"] in skip_node_ids:
            continue
        dispatch = entry["dispatch"]
        dispatch.update(before_state=dispatch["source_state"], after_state=dispatch["source_state"])
        if entry["result_contract"] == "compact-validation":
            content, metadata = _compile_passing_validation(dispatch)
            kind = "validation"
        elif entry["result_contract"] == "compact-independent-review":
            content, metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": _compact_independent_payload(dispatch)})
            kind = "review"
        else:
            if handoff_catalog_id is not None and dispatch["skill_id"] == "rust-invariant-state-transitions":
                handoffs = [
                    {
                        "catalog_id": handoff_catalog_id,
                        "observed_trigger": "the accepted audit discovered a newly applicable review surface",
                        "reason": "late routing must add the catalog owner before synthesis",
                        "scope": [STATE_FIXTURE],
                    }
                ]
            elif resolved_handoff and dispatch["mode"] == "audit":
                handoffs = [
                    {
                        "catalog_id": "rust.invariants",
                        "observed_trigger": "state transition ownership confirmed",
                        "reason": "the current plan already selected the owning catalog entry",
                        "scope": [STATE_FIXTURE],
                    }
                ]
            else:
                handoffs = []
            if reference_planned_validation and dispatch["mode"] == "audit":
                planned = dispatch["command_policy"]["planned_validation_units"][0]
                validation_requirements = [
                    {
                        "expected_evidence": f"{dispatch['skill_id']} expects the planned command to pass",
                        "owner": dispatch["skill_id"],
                        "planned_validation_digest": planned["planned_validation_digest"],
                        "reason": f"{dispatch['node_id']} independently confirms the planned validation need",
                        "requirement_id": planned["requirement_ids"][0],
                    }
                ]
            else:
                validation_requirements = late_requirements or [] if dispatch["node_id"] == "audit-001" else []
                if late_requirements_by_node is not None:
                    validation_requirements = late_requirements_by_node.get(dispatch["node_id"], [])
            payload = {
                "command_policy_attested": True,
                "commands_executed": [],
                "files_inspected": [STATE_FIXTURE],
                "findings": [],
                "handoffs": handoffs,
                "limitations": [],
                "scope_limitations": [],
                "nearby_contract_owners": list(dispatch.get("required_read_paths", [])),
                "status": "no-findings",
                "validation_requirements": validation_requirements,
            }
            if bool(audit_findings) and dispatch["mode"] == "audit":
                payload.update({"status": "completed", "findings": audit_findings})
            content, metadata = compile_review({"dispatch": dispatch, "payload": _typed_synthesis_payload(dispatch, payload, plan)})
            kind = "review"
        artifact_path = Path(entry["artifact_path"])
        metadata_path = Path(entry["metadata_path"])
        artifact_path.write_bytes(content)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        sources.append({"artifact_path": str(artifact_path), "kind": kind, "metadata_path": str(metadata_path)})
    return plan, sources


def _source_by_node(sources: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Index compiled artifact sources by the node ID recorded in each sidecar."""
    return {json.loads(Path(source["metadata_path"]).read_text(encoding="utf-8"))["evidence"]["node_id"]: source for source in sources}


def _payload(paths: list[str], *, dispatch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a no-findings audit for the supplied paths and the dispatch's required reads."""
    return {
        "status": "no-findings",
        "files_inspected": paths,
        "findings": [],
        "changes": [],
        "handoffs": [],
        "limitations": [],
        "scope_limitations": [],
        "nearby_contract_owners": list((dispatch or {}).get("required_read_paths", [])),
        "validation_requirements": [],
        "commands_executed": [],
        "command_policy_attested": True,
    }


def _synthesis_payload(dispatch: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    """Summarize the predecessor records declared by this synthesis dispatch."""
    records = [record for record in bundle["records"] if record["evidence_id"] in dispatch["predecessor_evidence_ids"]]
    findings = [
        {
            **{key: finding[key] for key in ("severity", "location", "summary", "evidence", "remediation")},
            "owner": record["skill_id"],
            "disposition": "remaining",
            "source_findings": [{"evidence_id": record["evidence_id"], "finding_id": finding["finding_id"]}],
        }
        for record in records
        for finding in record.get("findings", [])
    ]
    return {
        **_payload([]),
        "status": "completed" if findings else "no-findings",
        "findings": findings,
        "readiness_verdict": "not-ready" if findings else "ready",
        "verdict_reasons": ["Findings remain." if findings else "Required evidence reconciles."],
        "predecessor_coverage": [
            {"evidence_id": record["evidence_id"], "requirement_ids": record["requirement_ids"], "disposition": "reused" if record.get("reuse") else "accepted"}
            for record in records
        ],
        "routing_closure": {"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
        "validation_reconciliation": [
            {
                "evidence_id": record["evidence_id"],
                "requirement_ids": record["requirement_ids"],
                "result": record["status"],
                "platform": bundle["plan_context"]["validation_environments"][record["node_id"]]["platform"],
                "execution_mode": "native",
            }
            for record in records
            if record["record_type"] == "validation"
        ],
        "cross_surface_risks": [],
    }


def _discovery_payload(audit: dict[str, Any], command: str = "git --no-pager diff -- tool.py state.rs") -> dict[str, Any]:
    """Build an audit result that records a Git command used for source discovery."""
    return {
        **_payload(audit["dispatch"]["owned_paths"], dispatch=audit["dispatch"]),
        "commands_executed": [command],
        "git_dependencies": [{"kind": "source-discovery", "command": command, "reason": "Located changes; judgments use the inspected worktree files."}],
    }


def _accept(request: dict[str, Any], entry: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    """Compile the worker result against its source state and journal the accepted evidence."""
    state = request["source_state"]
    content, metadata = compile_review({"dispatch": {**entry["dispatch"], "before_state": state, "after_state": state}, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source: dict[str, str] = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}
    append_journal_event(Path(request["journal_path"]), request, JournalEventRequest(entry["node_id"], "accepted", source=source))
    return source


def _save(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path, payload: dict[str, Any]) -> dict[str, str]:
    """Write a worker result and record its accepted or blocked outcome in the fixture journal."""
    state = lifecycle.get("current_source_state", lifecycle["source_state"])
    dispatch = {**entry["dispatch"], "before_state": state, "after_state": state, "source_capture": lifecycle.get("capture", lifecycle.get("new_capture"))}
    compiler = {
        "audit": runtime.compile_review,
        "synthesis": runtime.compile_review,
        "independent-review": runtime.compile_independent_payload,
        "validation": runtime.compile_validation,
    }[dispatch["mode"]]
    content, metadata = compiler({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source: dict[str, str] = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    runtime.append_journal_event(
        journal,
        lifecycle,
        runtime.JournalEventRequest(
            entry["node_id"],
            "blocked" if payload["status"] == "blocked" else "accepted",
            source=source,
            reason="Native CI requires an authorized published commit." if payload["status"] == "blocked" else None,
        ),
    )
    return source


def _validation_payload(entry: dict[str, Any], *, blocked: bool = False) -> dict[str, Any]:
    """Build command results for a passed validation or a blocked native CI handoff."""
    unit = entry["dispatch"]["validation_unit"]
    return {
        "schema_version": 3,
        "status": "blocked" if blocked else "passed",
        "artifacts": [],
        "limitations": ["Native CI unavailable before authorized commit and push."] if blocked else [],
        "executions": [
            {
                "command": command,
                "working_directory": directory,
                "executor": "fixture",
                "result": "blocked" if blocked else "passed",
                "evidence": "Unavailable before commit" if blocked else "Fixture completed",
                "exit_code": None if blocked else 0,
                "elapsed": "0s",
                "artifact_paths": [],
            }
            for command, directory in zip(unit["commands"], unit["working_directories"], strict=True)
        ],
    }
