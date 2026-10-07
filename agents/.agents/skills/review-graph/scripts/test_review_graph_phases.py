"""Repair validation barriers exercise real checks and ordinary evidence gates."""

import json
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_metrics import projected_waves
from review_graph_plan import graph_plan_digest, graph_plan_digest_matches, plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    _graph_plan,
    advance_after_mutation,
    append_journal_event,
    capture_workspace_snapshot,
    compile_validation,
    main,
    materialize_dispatches,
    next_ready_nodes,
    read_execution_journal,
    resume_after_external_metadata,
)
from review_graph_scheduling import select_execution_lanes
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _compile_repair_fixture_entry,
    _json_plan,
    _mutation_request,
    _mutation_with_audit_source,
    _publish_worker_bytes,
    _run_test_git,
    _sparse_plan_document,
)


def _phase_plan(profile: str = "grouped") -> dict[str, Any]:
    planning = _sparse_plan_document()
    planning["execution_profile"] = profile
    first = planning["validation_requirements"][0]
    planning["validation_requirements"].extend(
        [
            {**first, "requirement_id": "static-alias", "baseline": False},
            {**first, "requirement_id": "remaining-check", "canonical_recipe": "just tests", "commands": ["just tests"]},
        ]
    )
    planning["pre_review_validation_requirement_ids"] = ["static-alias", "baseline-validation"]
    return planning


@pytest.mark.parametrize("profile", ["grouped", "mixed", "isolated", "isolated-only"])
def test_phase_moves_whole_coalesced_unit_without_duplicate_execution_or_semantic_edges(profile: str) -> None:
    plan = plan_from_document(_phase_plan(profile), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    assert len(plan.pre_review_validation_nodes) == 1
    early = plan.pre_review_validation_nodes[0]
    assert plan.actual_worker_nodes[0].node_id == early
    assert len(plan.coalesced_validation_units) == 2
    assert {item.validation_unit_id for item in plan.validation_evidence_mapping if item.requirement_id != "remaining-check"} == {early}
    assert all(not node.predecessors for node in plan.actual_worker_nodes if node.mode == "audit")
    waves = projected_waves([asdict(node) for node in plan.actual_worker_nodes], 4, early_validation=plan.pre_review_validation_nodes)
    assert waves[0] == [early]
    assert sum(early in wave for wave in waves) == 1
    assert _graph_plan(_json_plan(plan)) == plan
    assert not graph_plan_digest_matches(plan, graph_plan_digest(replace(plan, pre_review_validation_nodes=())))


@pytest.mark.parametrize("defect", ["missing", "duplicate", "optional", "parallel", "continue", "empty"])
def test_invalid_phase_selection_fails_before_dispatch(defect: str) -> None:
    planning = _sparse_plan_document()
    planning["pre_review_validation_requirement_ids"] = ["baseline-validation"]
    unit = planning["validation_requirements"][0]
    if defect == "missing":
        planning["pre_review_validation_requirement_ids"] = ["missing"]
    elif defect == "duplicate":
        planning["pre_review_validation_requirement_ids"] *= 2
    elif defect == "optional":
        planning["validation_requirements"].append({**unit, "requirement_id": "real-baseline", "commands": ["true baseline"]})
        unit.update(required=False, baseline=False)
    elif defect == "parallel":
        unit["execution_strategy"] = "parallel-independent"
    elif defect == "continue":
        unit["dependency_policy"] = "continue-independent"
    else:
        unit.update(commands=[], working_directories=[])
    with pytest.raises(ValueError, match="pre-review validation"):
        plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))


@pytest.mark.parametrize("status", ["passed", "failed", "blocked"])
def test_multiple_early_units_require_verified_success_in_declared_order(tmp_path: Path, status: str) -> None:
    planning = _phase_plan()
    planning["pre_review_validation_requirement_ids"].append("remaining-check")
    # A combined canonical command stays intact, including its ordinary gate.
    for requirement in planning["validation_requirements"][:2]:
        requirement.update(commands=["just check ci"], canonical_recipe="just check ci")
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
            "artifact_store": str(tmp_path / "proof"),
        }
    )
    entries = {entry["node_id"]: entry for entry in dispatches["dispatches"]}
    first, second = plan.pre_review_validation_nodes
    assert entries[first]["dispatch"]["validation_unit"]["commands"] == ["just check ci"]
    ready_input = {**lifecycle, "current_source_state": lifecycle["source_state"]}
    ready = next_ready_nodes(ready_input, journal_events=(), dispatch_set=dispatches)
    assert ready["ready_node_ids"] == [first]
    lanes = select_execution_lanes(
        {"preflight_blocked_nodes": [{"node_id": first, "reason": "Executor unavailable"}]},
        modes={node.node_id: node.mode for node in plan.actual_worker_nodes},
        entries=entries,
        ready=ready,
    )
    assert not lanes["worker_node_ids"]
    assert lanes["coordinator_node_id"] is None
    entry = entries[first]
    payload = {
        "status": status,
        "limitations": ["Executor unavailable"] if status == "blocked" else [],
        "executions": []
        if status == "blocked"
        else [
            {
                "command": "just check ci",
                "working_directory": str(SKILL_ROOT.parents[2]),
                "executor": first,
                "result": status,
                "exit_code": 0 if status == "passed" else 1,
                "elapsed": "0.01s",
                "artifact_paths": [],
                "evidence": "Fixture outcome",
            }
        ],
    }
    content, metadata = compile_validation(
        {"dispatch": {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    journal = tmp_path / "execution.jsonl"
    append_journal_event(
        journal,
        lifecycle,
        JournalEventRequest(
            first,
            "blocked" if status == "blocked" else "accepted",
            source={key: entry[key] for key in ("artifact_path", "metadata_path")},
            reason="Executor unavailable" if status == "blocked" else None,
        ),
    )
    events, _state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    ready = next_ready_nodes(ready_input, journal_events=events, dispatch_set=dispatches)
    assert ready["ready_node_ids"] == ([second] if status == "passed" else [])
    if status == "passed":
        Path(entry["artifact_path"]).write_bytes(b"tampered success")
        with pytest.raises(ValueError, match="digest"):
            next_ready_nodes(ready_input, journal_events=events, dispatch_set=dispatches)
    else:
        with pytest.raises(ValueError, match="pre-review validation"):
            append_journal_event(journal, lifecycle, JournalEventRequest(second, "in-flight"))


def _ready(result: dict[str, Any]) -> dict[str, Any]:
    lifecycle = json.loads(json.dumps(result["lifecycle_input"]))
    events, _state, _head = read_execution_journal(
        Path(result["journal_path"]), plan=_graph_plan(lifecycle["plan"]), source_state=tuple(lifecycle["source_state"])
    )
    return next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=result["dispatch_set"])


def _run_early_check(result: dict[str, Any], tmp_path: Path) -> dict[str, str]:
    lifecycle = result["lifecycle_input"]
    entry = _ready(result)["ready_dispatches"][0]
    dispatch = entry["dispatch"]
    journal = Path(result["journal_path"])
    append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "in-flight"))
    before = capture_workspace_snapshot(dispatch)
    unit = dispatch["validation_unit"]
    started = time.monotonic()
    command = subprocess.run(  # noqa: S603 - exact fixture-owned argv, no shell or external input.
        shlex.split(unit["commands"][0]), cwd=unit["working_directories"][0], capture_output=True, check=False
    )
    elapsed = time.monotonic() - started
    after = capture_workspace_snapshot(dispatch)
    status = "passed" if command.returncode == 0 else "failed"
    payload = {
        "status": status,
        "limitations": [],
        "executions": [
            {
                "command": unit["commands"][0],
                "working_directory": unit["working_directories"][0],
                "executor": entry["node_id"],
                "result": status,
                "exit_code": command.returncode,
                "elapsed": f"{elapsed}s",
                "artifact_paths": [],
                "evidence": " | ".join((command.stdout.decode() + command.stderr.decode()).splitlines()),
            }
        ],
    }
    if status == "failed":
        assert "E501" in payload["executions"][0]["evidence"]
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    git = shutil.which("git")
    assert git is not None
    capture = _scope_data(git, Path(dispatch["repository_root"]), "baseline", None, ())
    assert capture == result["capture"]
    capture_path = tmp_path / "after.json"
    capture_path.write_text(json.dumps(capture))
    snapshots = {"before": before, "after": after}
    for name, snapshot in snapshots.items():
        (tmp_path / f"{name}-workspace.json").write_text(json.dumps(snapshot))
    assert (
        main(
            [
                "compile-node",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--node-id",
                entry["node_id"],
                "--before-capture",
                result["capture_path"],
                "--after-capture",
                str(capture_path),
                "--workspace-before",
                str(tmp_path / "before-workspace.json"),
                "--workspace-after",
                str(tmp_path / "after-workspace.json"),
                "--output",
                str(tmp_path / "compiled.json"),
            ]
        )
        == 0
    )
    return {key: entry[key] for key in ("artifact_path", "metadata_path")}


def test_repair_lint_failure_stops_fanout_then_new_source_reruns_once(tmp_path: Path) -> None:
    request = _mutation_request(tmp_path)
    repository = Path(request["new_capture"]["repository_root"])
    source = repository / "tool.py"
    source.write_text("values = dict(" + ", ".join(f"key_{i}={i}" for i in range(20)) + ")\n")
    git = shutil.which("git")
    assert git is not None
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    request["changed_paths"] = ["state.rs", "tool.py"]
    command = shlex.join([sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--select", "E501", "--line-length", "88", "tool.py"])
    template = request["planning_template"]
    template["validation_requirements"][0].update(commands=[command], canonical_recipe=command)
    template["pre_review_validation_requirement_ids"] = ["baseline-validation"]
    template.update(concrete_change_target=True, change_target="repaired source")
    first = advance_after_mutation(request)
    first["lifecycle_input"] = json.loads(json.dumps(first["lifecycle_input"]))
    ready = _ready(first)
    assert len(ready["ready_node_ids"]) == 1
    entries = {entry["node_id"]: entry for entry in first["dispatch_set"]["dispatches"]}
    modes = {node["node_id"]: node["mode"] for node in first["new_plan"]["actual_worker_nodes"]}
    assert "independent-review" in modes.values()
    lanes = select_execution_lanes({}, modes=modes, entries=entries, ready=ready)
    assert lanes["worker_node_ids"] == ready["ready_node_ids"]
    semantic = next(node_id for node_id, mode in modes.items() if mode == "audit")
    with pytest.raises(ValueError, match="pre-review validation"):
        append_journal_event(Path(first["journal_path"]), first["lifecycle_input"], JournalEventRequest(semantic, "in-flight"))
    failed_source = _run_early_check(first, tmp_path)
    assert not _ready(first)["ready_node_ids"]
    accounting = {item["stage"]: item for item in _ready(first)["phase_accounting"]}
    assert accounting["semantic-review"]["worker_launch_count"] == 0
    assert accounting["pre-review-validation"]["worker_launch_count"] == 1
    assert accounting["pre-review-validation"]["first_start_unix_ns"] <= accounting["pre-review-validation"]["last_result_unix_ns"]
    assert accounting["pre-review-validation"]["provider_cost_usd"] is None
    failed_bytes = Path(failed_source["artifact_path"]).read_bytes()

    subprocess.run(  # noqa: S603 - formatter targets only this test's temporary source.
        [sys.executable, "-m", "ruff", "format", "--isolated", "--no-cache", "--line-length", "88", str(source)], check=True, capture_output=True
    )
    next_capture = _scope_data(git, repository, "baseline", None, ())
    second = advance_after_mutation(
        {
            **request,
            "plan": first["lifecycle_input"]["plan"],
            "source_state": first["new_source_state"],
            "previous_capture": first["capture"],
            "new_capture": next_capture,
            "repair_epoch": 2,
            "changed_paths": ["tool.py"],
            "sources": [failed_source],
        }
    )
    second["lifecycle_input"] = json.loads(json.dumps(second["lifecycle_input"]))
    assert not set(first["new_plan"]["pre_review_validation_nodes"]) & set(second["new_plan"]["pre_review_validation_nodes"])
    assert _ready(second)["ready_dispatches"][0]["result_contract"] == "compact-validation"
    passing_directory = tmp_path / "passing"
    passing_directory.mkdir()
    _run_early_check(second, passing_directory)
    assert _ready(second)["ready_node_ids"]
    assert all(entry["result_contract"] != "compact-validation" for entry in _ready(second)["ready_dispatches"])
    assert Path(failed_source["artifact_path"]).read_bytes() == failed_bytes
    # This fixture exercises the real lint and compile gates; semantic fixture
    # judgments are supplied separately and never execute validator commands.
    independent = next(entry for entry in second["dispatch_set"]["dispatches"] if entry["result_contract"] == "compact-independent-review")
    assert independent["node_id"] in _ready(second)["ready_node_ids"]


def test_early_success_is_final_evidence_and_unchanged_audit_reuse_survives(tmp_path: Path) -> None:
    request, unchanged, _source = _mutation_with_audit_source(tmp_path)
    request["planning_template"]["pre_review_validation_requirement_ids"] = ["baseline-validation"]
    result = advance_after_mutation(request)
    assert unchanged["dispatch"]["evidence_id"] in result["reused_evidence_ids"]
    result["lifecycle_input"] = json.loads(json.dumps(result["lifecycle_input"]))
    executions: list[str] = []
    for _ in range(result["new_plan"]["complete_node_count"] + 1):
        ready = _ready(result)
        if ready["complete"]:
            break
        assert ready["ready_dispatches"]
        for entry in ready["ready_dispatches"]:
            _compile_repair_fixture_entry(entry, result["lifecycle_input"], Path(result["journal_path"]))
            executions.append(entry["node_id"])
    assert _ready(result)["complete"]
    early = result["new_plan"]["pre_review_validation_nodes"][0]
    assert executions.count(early) == 1
    assert (
        main(
            [
                "finalize-proof",
                "--input",
                result["lifecycle_input_path"],
                "--journal",
                result["journal_path"],
                "--dispatches",
                result["dispatches_path"],
                "--current-capture",
                result["capture_path"],
                "--output",
                str(tmp_path / "final.json"),
            ]
        )
        == 0
    )
    final = json.loads((tmp_path / "final.json").read_bytes())
    assert final["graph_proof_status"] == "complete"
    assert final["repository_validation_status"] == "passed"


def test_early_validation_unexpected_effects_do_not_release_barrier(tmp_path: Path) -> None:
    planning = _phase_plan()
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    effect = tmp_path / "unexpected.txt"
    units = tuple(
        replace(unit, expected_workspace_effects=(str(tmp_path / "approved.txt"),)) if unit.node_id in plan.pre_review_validation_nodes else unit
        for unit in plan.coalesced_validation_units
    )
    plan = replace(plan, coalesced_validation_units=units)
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
            "artifact_store": str(tmp_path / "proof"),
        }
    )
    entry = dispatches["dispatches"][0]
    before = capture_workspace_snapshot(entry["dispatch"])
    effect.write_text("unapproved output")
    after = capture_workspace_snapshot(
        {**entry["dispatch"], "validation_unit": {**entry["dispatch"]["validation_unit"], "expected_workspace_effects": [str(effect)]}}
    )
    dispatch = {
        **entry["dispatch"],
        "before_state": lifecycle["source_state"],
        "after_state": lifecycle["source_state"],
        "workspace_before": before["records"],
        "workspace_after": after["records"],
    }
    with pytest.raises(ValueError, match="unexpected"):
        compile_validation({"dispatch": dispatch, "payload": {"status": "blocked", "limitations": ["unapproved output"], "executions": []}})
    ready = next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=(), dispatch_set=dispatches)
    assert ready["ready_node_ids"] == list(plan.pre_review_validation_nodes)


@pytest.mark.parametrize("in_flight", [False, True])
def test_metadata_resume_retains_audits_and_restarts_only_current_validation(tmp_path: Path, in_flight: bool) -> None:
    request = _mutation_request(tmp_path)
    request["planning_template"]["pre_review_validation_requirement_ids"] = ["baseline-validation"]
    result = advance_after_mutation(request)
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_text())
    journal = Path(result["journal_path"])
    validator = _ready(result)["ready_dispatches"][0]
    _compile_repair_fixture_entry(validator, lifecycle, journal)
    audit = next(entry for entry in _ready(result)["ready_dispatches"] if entry["dispatch"].get("mode") == "audit")
    if in_flight:
        append_journal_event(journal, lifecycle, JournalEventRequest(audit["node_id"], "in-flight"))
    else:
        _compile_repair_fixture_entry(audit, lifecycle, journal)
    git = shutil.which("git")
    assert git is not None
    repository = Path(result["capture"]["repository_root"])
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    resumed = resume_after_external_metadata(
        {
            **lifecycle,
            "previous_capture": result["capture"],
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "journal_path": str(journal),
            "dispatches_path": result["dispatches_path"],
            "artifact_store": str(tmp_path / "resumed"),
        }
    )
    assert audit["node_id"] in resumed["preserved_node_ids"]
    resumed_lifecycle = json.loads(Path(resumed["lifecycle_input_path"]).read_text())
    events, _state, _head = read_execution_journal(
        Path(resumed["journal_path"]), plan=_graph_plan(resumed_lifecycle["plan"]), source_state=tuple(lifecycle["source_state"])
    )
    ready = next_ready_nodes(
        {**resumed_lifecycle, "current_source_state": resumed["current_source_state"]}, journal_events=events, dispatch_set=resumed["dispatch_set"]
    )
    assert ready["ready_node_ids"] == [validator["node_id"]]
    _run_test_git(git, "-C", str(repository), "restore", "--staged", "state.rs")
    resumed_again = resume_after_external_metadata(
        {
            **resumed_lifecycle,
            "previous_capture": json.loads(Path(resumed["capture_path"]).read_text()),
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "journal_path": resumed["journal_path"],
            "dispatches_path": resumed["dispatches_path"],
            "artifact_store": str(tmp_path / "resumed-again"),
        }
    )
    assert audit["node_id"] in resumed_again["preserved_node_ids"]
    if in_flight:
        current = {**resumed_again["lifecycle_input"], "current_source_state": resumed_again["current_source_state"]}
        current = json.loads(json.dumps(current))
        current_audit = next(entry for entry in resumed_again["dispatch_set"]["dispatches"] if entry["node_id"] == audit["node_id"])
        _compile_repair_fixture_entry(current_audit, current, Path(resumed_again["journal_path"]))


def test_successful_early_evidence_is_stale_after_content_mutation(tmp_path: Path) -> None:
    request = _mutation_request(tmp_path)
    request["planning_template"]["pre_review_validation_requirement_ids"] = ["baseline-validation"]
    result = advance_after_mutation(request)
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_text())
    early = _ready(result)["ready_dispatches"][0]
    source = _compile_repair_fixture_entry(early, lifecycle, Path(result["journal_path"]))
    assert early["node_id"] not in _ready(result)["ready_node_ids"]
    git = shutil.which("git")
    assert git is not None
    repository = Path(result["capture"]["repository_root"])
    (repository / "tool.py").write_text("value = 3\n")
    capture = _scope_data(git, repository, "baseline", None, ())
    with pytest.raises(ValueError, match="current recapture differs"):
        next_ready_nodes(
            {
                **lifecycle,
                "current_source_state": [capture[field] for field in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")],
            },
            journal_events=(),
            dispatch_set=result["dispatch_set"],
        )
    second = advance_after_mutation(
        {
            **request,
            **lifecycle,
            "previous_capture": result["capture"],
            "new_capture": capture,
            "sources": [source],
            "repair_epoch": 2,
            "changed_paths": ["tool.py"],
        }
    )
    assert early["dispatch"]["evidence_id"] in second["stale_evidence_ids"]
    assert _ready(second)["ready_node_ids"] == list(second["new_plan"]["pre_review_validation_nodes"])
