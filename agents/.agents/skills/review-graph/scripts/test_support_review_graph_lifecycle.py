"""Repair, continuation, and late-validation scenarios for review-graph tests."""

import json
import shutil
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import GraphPlan, plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    _graph_plan,
    append_journal_event,
    compile_independent_payload,
    compile_review,
    compile_validation,
    materialize_dispatches,
)
from review_graph_schema import require_schema_definition
from test_support_review_graph import (
    ROUTING_CATALOG,
    SCHEMA_ROOT,
    SKILL_ROOT,
    _complete_structural_fixture_routing,
    _json_plan,
    _materialize,
    _run_test_git,
    _sparse_plan_document,
    _worker_input_fixture,
)
from test_support_review_graph_evidence import _compact_independent_payload, _compile_materialized_evidence, _source_by_node, _typed_synthesis_payload


def _baseline_mutation_fixture(tmp_path: Path, *, instructions: bool = False) -> tuple[str, Path, dict[str, Any], dict[str, Any], GraphPlan]:
    """Initialize a real Git checkout, capture its baseline, and parse the matching review plan."""
    git = shutil.which("git")
    assert git is not None
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_test_git(git, "init", str(repository))
    _run_test_git(git, "-C", str(repository), "config", "user.email", "review@example.com")
    _run_test_git(git, "-C", str(repository), "config", "user.name", "Review Test")
    state_path = repository / "state.rs"
    state_path.write_text("pub fn state() {}\n", encoding="utf-8")
    (repository / "tool.py").write_text("value = 1\n", encoding="utf-8")
    for name in ("LICENSE", "cliff.toml", ".codecov.yml"):
        (repository / name).write_text("unchanged baseline fixture\n", encoding="utf-8")
    if instructions:
        (repository / "AGENTS.md").write_text("Baseline review instructions.\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "initial")
    template = _sparse_plan_document()
    # These literal placeholders have no active license/configuration semantics;
    # retain them as unowned transport history for mutation and provenance tests.
    template["captured_path_dispositions"] = [
        {
            "paths": ["LICENSE", "cliff.toml", ".codecov.yml"],
            "disposition": "historical",
            "reason": "Inactive mutation transport placeholders",
            "catalog_ids": [],
        }
    ]
    template["consulted_routers"] = ["review-graph", "rust-review-orchestrator", "python-review-orchestrator"]
    if instructions:
        template["consulted_routers"].append("docs-review-orchestrator")
    for override in template["routing_overrides"]:
        override["review_surface"] = ["state.rs"]
    template["validation_requirements"][0]["working_directories"] = [str(repository)]
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    return git, repository, template, capture, plan


def _mutation_request(tmp_path: Path, *, instructions: bool = False) -> dict[str, Any]:
    """Capture a fixture source edit and bind both source states to a repair request."""
    git, repository, template, previous_capture, plan = _baseline_mutation_fixture(tmp_path, instructions=instructions)
    (repository / "state.rs").write_text("pub fn state() { assert!(true); }\n", encoding="utf-8")
    return {
        "artifact_store": str(tmp_path / "proof-store"),
        "authorization_after": "review-and-fix",
        "authorization_before": "review-only",
        "changed_paths": ["state.rs"],
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "plan": _json_plan(plan),
        "planning_template": template,
        "previous_capture": previous_capture,
        "repair_epoch": 1,
        "source_state": [previous_capture[field] for field in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")],
        "state_verification_command": "capture_scope.py --mode baseline",
    }


def _mutation_with_audit_source(
    tmp_path: Path,
    *,
    nearby_contract_owners: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
    reference_planned_validation: bool = False,
    instructions: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Attach a compiled audit to the mutation request as its source of evidence."""
    request = _mutation_request(tmp_path, instructions=instructions)
    materialized = materialize_dispatches(
        {
            "artifact_store": str(tmp_path / "old-evidence"),
            "authorization": "review-only",
            "plan": request["plan"],
            "repository_root": request["previous_capture"]["repository_root"],
            "source_state": request["source_state"],
            "state_verification_command": request["state_verification_command"],
        }
    )
    entry = next(item for item in materialized["dispatches"] if item["dispatch"].get("mode") == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    dispatch = {**entry["dispatch"], "before_state": request["source_state"], "after_state": request["source_state"]}
    payload = {
        "changes": [],
        "command_policy_attested": True,
        "commands_executed": [],
        "files_inspected": ["tool.py"],
        "findings": [],
        "handoffs": [],
        "limitations": list(limitations),
        "scope_limitations": [],
        "nearby_contract_owners": [*dispatch.get("required_read_paths", []), *nearby_contract_owners],
        "status": "no-findings",
        "validation_requirements": [],
    }
    if reference_planned_validation:
        planned = dispatch["command_policy"]["planned_validation_units"][0]
        payload["validation_requirements"] = [
            {
                "requirement_id": planned["requirement_ids"][0],
                "planned_validation_digest": planned["planned_validation_digest"],
                "owner": dispatch["skill_id"],
                "reason": "Audit requires the planned validation",
                "expected_evidence": "Required checks pass",
            }
        ]
    content, metadata = compile_review({"dispatch": dispatch, "payload": _typed_synthesis_payload(dispatch, payload)})
    artifact_path = Path(entry["artifact_path"])
    metadata_path = Path(entry["metadata_path"])
    artifact_path.write_bytes(content)
    metadata_bytes = json.dumps(metadata).encode()
    metadata_path.write_bytes(metadata_bytes)
    source = {"artifact_path": str(artifact_path), "metadata_path": str(metadata_path)}
    request["sources"] = [source]
    return request, entry, source


def _compile_repair_fixture_entry(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path) -> dict[str, str]:
    """Compile repair evidence for the current state and append its acceptance to the journal."""
    state = lifecycle.get("current_source_state", lifecycle["source_state"])
    dispatch = {**entry["dispatch"], "before_state": state, "after_state": state}
    if entry["result_contract"] == "compact-validation":
        unit = dispatch["validation_unit"]
        payload = {
            "schema_version": 3,
            "artifacts": [],
            "executions": [
                {
                    "artifact_paths": [],
                    "command": command,
                    "elapsed": "0s",
                    "evidence": "fixture command passed",
                    "executor": dispatch["node_id"],
                    "exit_code": 0,
                    "result": "passed",
                    "working_directory": directory,
                }
                for command, directory in zip(unit["commands"], unit["working_directories"], strict=True)
            ],
            "limitations": [],
            "status": "passed",
        }
        content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
    elif entry["result_contract"] == "compact-independent-review":
        payload = {**_compact_independent_payload(dispatch), "before_state": list(state), "after_state": list(state)}
        content, metadata = compile_independent_payload({"dispatch": dispatch, "payload": payload})
    else:
        payload = {
            "changes": [],
            "command_policy_attested": True,
            "commands_executed": [],
            "files_inspected": list(dispatch["owned_paths"]) or ["state.rs", "tool.py"],
            "findings": [],
            "handoffs": [],
            "limitations": [],
            "nearby_contract_owners": list(dispatch.get("required_read_paths", [])),
            "scope_limitations": [],
            "status": "no-findings",
            "validation_requirements": [],
        }
        content, metadata = compile_review({"dispatch": dispatch, "payload": _typed_synthesis_payload(dispatch, payload, _graph_plan(lifecycle["plan"]))})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    source: dict[str, str] = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}
    append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
    return source


def _continuation_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    """Write the lifecycle inputs, dispatches, and current capture needed to exercise a continuation."""
    document, dispatches = _worker_input_fixture(tmp_path)
    lifecycle = {"plan": document["plan"], "source_state": document["source_state"]}
    paths = {key: tmp_path / f"{key}.json" for key in ("input", "dispatches", "current-capture", "journal")}
    paths["input"].write_text(json.dumps(lifecycle), encoding="utf-8")
    paths["dispatches"].write_text(json.dumps(dispatches), encoding="utf-8")
    paths["current-capture"].write_text(
        json.dumps({"scope_fingerprint": "scope", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"}), encoding="utf-8"
    )
    return lifecycle, dispatches, paths


def _late_validation_requirement() -> dict[str, Any]:
    """Describe the isolated Python build check discovered after initial planning."""
    return {
        "requirement_id": "python.build.isolated-artifacts",
        "owner": "review-validator",
        "reason": "clean install is not covered by CI",
        "commands": ["uv build"],
        "working_directory": str(SKILL_ROOT.parents[2]),
        "environment": "isolated Python",
        "expected_evidence": "sdist and wheel install cleanly",
        "dependency_policy": "stop-on-failure",
    }


def _late_validation_plan() -> dict[str, Any]:
    """Convert the late requirement into a schema-checked planning record."""
    requirement = _sparse_plan_document()["validation_requirements"][0]
    late = _late_validation_requirement()
    requirement.update(
        {
            "baseline": False,
            "canonical_recipe": None,
            "requirement_id": late["requirement_id"],
            "commands": late["commands"],
            "working_directories": [late["working_directory"]],
            "environment": late["environment"],
            "expected_evidence": late["expected_evidence"],
            "expected_workspace_effects": [],
            "requires_isolation": False,
            "isolation_root": None,
        }
    )
    require_schema_definition(requirement, SCHEMA_ROOT / "planning-input-v1.schema.json", "validationRequirement")
    return requirement


def _late_validation_fixture(
    tmp_path: Path, *, late_requirements_by_node: dict[str, list[dict[str, Any]]] | None = None
) -> tuple[GraphPlan, list[dict[str, str]], dict[str, Any], Path, Path, Path]:
    """Persist compiled evidence and journal acceptances before reconciling a newly reported requirement."""
    plan, sources = _compile_materialized_evidence(
        tmp_path / "original", late_requirements=[_late_validation_requirement()], late_requirements_by_node=late_requirements_by_node
    )
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    materialized = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "original"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    dispatch_path = tmp_path / "dispatches.json"
    dispatch_path.write_text(json.dumps(materialized), encoding="utf-8")
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(
        json.dumps({"scope_fingerprint": "scope", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"}), encoding="utf-8"
    )
    journal = tmp_path / "execution.jsonl"
    by_node = _source_by_node(sources)
    for node in plan.actual_worker_nodes:
        if node.mode != "synthesis":
            append_journal_event(journal, lifecycle, JournalEventRequest(node.node_id, "accepted", source=by_node[node.node_id]))
    return plan, sources, lifecycle, dispatch_path, capture_path, journal


def _control_args(tmp_path: Path, result: dict[str, Any]) -> Namespace:
    """Resolve the saved journal, dispatch, and capture paths for a control operation."""
    return Namespace(
        journal=Path(result["journal_path"]),
        dispatches=Path(result["dispatches_path"]),
        current_capture=Path(result.get("current_capture_path", result.get("capture_path"))),
        output=tmp_path / "control-result.json",
    )


def _two_repairs(tmp_path: Path) -> tuple[dict[str, Any], Namespace]:
    """Advance a real checkout through two repair epochs and return its control inputs."""
    git, repository, template, capture, plan = _baseline_mutation_fixture(tmp_path)
    lifecycle, _entries, _dispatches = _materialize(tmp_path, capture, plan)
    result: dict[str, Any] = {}
    for ordinal in (1, 2):
        (repository / "tool.py").write_text(f"value = {ordinal + 1}\n")
        new_capture = _scope_data(git, repository, "baseline", None, ())
        result = runtime.advance_after_mutation(
            {
                **lifecycle,
                "previous_capture": capture,
                "new_capture": new_capture,
                "planning_template": template,
                "changed_paths": ["tool.py"],
                "authorization_before": "review-and-fix",
                "authorization_after": "review-and-fix",
                "repair_epoch": ordinal,
                "artifact_store": str(tmp_path / "repairs"),
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )
        lifecycle = result["lifecycle_input"]
        capture = new_capture
    return result, _control_args(tmp_path, result)


def _control_fixture(tmp_path: Path) -> tuple[dict[str, Any], Namespace, Path]:
    """Prepare a stop request with an in-flight worker and a persisted journal."""
    _git, repository, _template, capture, plan = _baseline_mutation_fixture(tmp_path)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture))
    args = Namespace(journal=tmp_path / "execution.jsonl", dispatches=dispatches, current_capture=capture_path, output=tmp_path / "result.json")
    node_id = next(entry["node_id"] for entry in entries["dispatches"] if not entry["dispatch"]["predecessor_evidence_ids"])
    runtime.append_journal_event(args.journal, lifecycle, runtime.JournalEventRequest(node_id, "in-flight"))
    return {**lifecycle, "action": "stop", "reason": "Stop now", "artifact_store": str(tmp_path / "control")}, args, repository


def _control_cli(request: dict[str, Any], args: Namespace, tmp_path: Path) -> int:
    """Write a control request to disk and return the CLI's exit status."""
    input_path = tmp_path / "control-request.json"
    input_path.write_text(json.dumps(request))
    return runtime.main(
        [
            "review-control",
            "--input",
            str(input_path),
            "--journal",
            str(args.journal),
            "--dispatches",
            str(args.dispatches),
            "--current-capture",
            str(args.current_capture),
            "--output",
            str(args.output),
        ]
    )
