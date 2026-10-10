"""Continuations retain the successful barrier that admitted preserved audits."""

import json
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from test_review_graph_execution_recovery import _compile_aggregate
from test_review_graph_repair_staging import _continuation_args, _finish_repair, _recovery_request, _run_continuation, _staged_repair
from test_review_graph_runtime import _late_validation_plan, _late_validation_requirement, _run_test_git
from test_review_graph_transitions import _payload


def _ready(result: dict[str, Any]) -> dict[str, Any]:
    lifecycle = result["lifecycle_input"]
    events, _state, _head = runtime.read_execution_journal(
        Path(result["journal_path"]), plan=runtime._graph_plan(lifecycle["plan"]), source_state=tuple(lifecycle["source_state"])
    )
    return runtime.next_ready_nodes(
        {**lifecycle, "current_source_state": result["current_source_state"]}, journal_events=events, dispatch_set=result["dispatch_set"]
    )


def _barrier_fixture(tmp_path: Path, *, resumes: int) -> tuple[dict[str, Any], dict[str, Any], dict[Path, bytes]]:
    git, repository, request, _old_audit, _history = _staged_repair(tmp_path)
    request.pop("post_repair_capture")
    _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    executor = tmp_path / "executor"
    executor.mkdir()
    script = executor / "aggregate.py"
    script.write_text(
        'import os\nprint("2 checks passed", flush=True)\nif os.environ["FIXTURE_SOCKET_ACCESS"] != "permitted":\n'
        '    raise PermissionError(1, "Operation not permitted")\nprint("build completed")\n'
    )
    template = request["planning_template"]
    template["pre_review_validation_requirement_ids"] = [template["validation_requirements"][0]["requirement_id"]]
    template["validation_requirements"][0].update(
        commands=[shlex.join([sys.executable, str(script)])],
        working_directories=[str(executor)],
        canonical_recipe="just ci",
        isolation_root=str(executor),
        requires_isolation=True,
        allowed_artifacts=[{"path": str(executor / "ci.log"), "kind": "log", "repository_status": "outside-repository"}],
    )
    result = runtime.advance_after_mutation(request)
    result["current_source_state"] = result["new_source_state"]
    gate = _ready(result)["ready_dispatches"][0]
    _compile_aggregate(result["lifecycle_input"], _continuation_args(result), gate, tmp_path / "original-pass", permitted=True)
    audit = next(entry for entry in _ready(result)["ready_dispatches"] if entry["dispatch"].get("mode") == "audit")
    requirement = {**_late_validation_requirement(), "commands": ["true"], "working_directory": str(repository)}
    content, metadata = runtime.compile_review(
        {
            "dispatch": {**audit["dispatch"], "before_state": result["current_source_state"], "after_state": result["current_source_state"]},
            "payload": {**_payload(audit["dispatch"]["owned_paths"]), "validation_requirements": [requirement]},
        }
    )
    Path(audit["artifact_path"]).write_bytes(content)
    Path(audit["metadata_path"]).write_text(json.dumps(metadata))
    runtime.append_journal_event(
        Path(result["journal_path"]), result["lifecycle_input"], runtime.JournalEventRequest(audit["node_id"], "accepted", source=audit)
    )
    history = {path: path.read_bytes() for path in Path(request["artifact_store"]).rglob("*") if path.is_file()}
    for ordinal in range(resumes):
        arguments = ("add", "state.rs") if ordinal % 2 == 0 else ("restore", "--staged", "state.rs")
        _run_test_git(git, "-C", str(repository), *arguments)
        result = runtime.resume_after_external_metadata(
            {
                **result["lifecycle_input"],
                "previous_capture": json.loads(Path(result["capture_path"]).read_bytes()),
                "new_capture": _scope_data(git, repository, "baseline", None, ()),
                "journal_path": result["journal_path"],
                "dispatches_path": result["dispatches_path"],
                "artifact_store": str(tmp_path / f"resumed-{ordinal}"),
            }
        )
        assert audit["node_id"] in result["preserved_node_ids"]
        assert _ready(result)["ready_node_ids"] == [gate["node_id"]]
    return result, audit, history


def _expand(tmp_path: Path, result: dict[str, Any]) -> dict[str, Any]:
    lifecycle = result["lifecycle_input"]
    sample = result["dispatch_set"]["dispatches"][0]["dispatch"]
    addition = {**_late_validation_plan(), "source_state": lifecycle["source_state"], "commands": ["true"], "working_directories": [sample["repository_root"]]}
    request = {
        **lifecycle,
        "external_metadata_transitions": lifecycle.get("external_metadata_transitions", []),
        "artifact_store": str(tmp_path / "expanded"),
        "validation_requirements": [addition],
    }
    return _run_continuation(tmp_path, "reconcile-validation-requirements", request, _continuation_args(result))


def _block_gate(entry: dict[str, Any], result: dict[str, Any]) -> None:
    snapshot = runtime.capture_workspace_snapshot(entry["dispatch"])
    dispatch = {
        **entry["dispatch"],
        "before_state": result["current_source_state"],
        "after_state": result["current_source_state"],
        "workspace_before": snapshot["records"],
        "workspace_after": snapshot["records"],
    }
    content, metadata = runtime.compile_validation(
        {"dispatch": dispatch, "payload": {"executions": [], "status": "blocked", "limitations": ["Permission denied before launch."]}}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    runtime.append_journal_event(
        Path(result["journal_path"]),
        result["lifecycle_input"],
        runtime.JournalEventRequest(entry["node_id"], "blocked", source=entry, reason="Permission denied before launch."),
    )


def _assert_historical_attempt_cannot_be_promoted(result: dict[str, Any], gate: dict[str, Any]) -> None:
    lifecycle = result["lifecycle_input"]
    plan = runtime._graph_plan(lifecycle["plan"])
    state = tuple(lifecycle["source_state"])
    events, _view, _head = runtime.read_execution_journal(Path(result["journal_path"]), plan=plan, source_state=state)
    assert events[-1]["node_id"] == gate["node_id"]
    assert events[-1]["status"] == "invalidated"
    with pytest.raises(ValueError, match="journal evidence ID differs from plan"):
        runtime._fold_execution_journal(plan, state, events[:-1])
    forged = json.loads(json.dumps(events))
    original_pass = next(event for event in forged if event["node_id"] == gate["node_id"] and (event["evidence"] or {}).get("evidence_status") == "passed")
    assert original_pass["evidence"]["evidence_id"] == gate["dispatch"]["evidence_id"]
    original_pass["evidence"]["artifact_digest"] = "sha256:" + "0" * 64
    for index, event in enumerate(forged):
        event["previous_event_digest"] = forged[index - 1]["event_digest"] if index else None
        del event["event_digest"]
        event["event_digest"] = runtime.digest_bytes(runtime.canonical_json(event).encode())
    with pytest.raises(ValueError, match="journal evidence ID differs from plan"):
        runtime._fold_execution_journal(plan, state, tuple(forged))


@pytest.mark.parametrize("operation", ["expansion", "launch-recovery", "execution-recovery"])
@pytest.mark.parametrize("resumes", [1, 2])
def test_metadata_continuation_preserves_barrier_history_and_owes_current_validation(tmp_path: Path, operation: str, resumes: int) -> None:
    result, audit, history = _barrier_fixture(tmp_path, resumes=resumes)
    gate = _ready(result)["ready_dispatches"][0]
    if operation != "expansion":
        checks_started = operation == "execution-recovery"
        recovery = _recovery_request(tmp_path, result, gate, checks_started=checks_started)
        if checks_started:
            lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
            recovery["failure_evidence"] = _compile_aggregate(lifecycle, _continuation_args(result), gate, tmp_path / "denied", permitted=False)
        else:
            _block_gate(gate, result)
        operation_name = "recover-validation-execution" if checks_started else "recover-validation-launch"
        history.update({Path(result[key]): Path(result[key]).read_bytes() for key in ("journal_path", "dispatches_path", "lifecycle_input_path")})
        result = _run_continuation(tmp_path, operation_name, recovery, _continuation_args(result))
    else:
        result = _expand(tmp_path, result)

    ready = _ready(result)
    assert ready["ready_node_ids"] == [gate["node_id"]]
    assert audit["node_id"] in ready["lifecycle"]["accepted_node_ids"]
    assert not ready["complete"]
    retry = ready["ready_dispatches"][0]
    if operation == "execution-recovery":
        assert retry["dispatch"]["evidence_id"] != gate["dispatch"]["evidence_id"]
        _assert_historical_attempt_cannot_be_promoted(result, gate)
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    _compile_aggregate(lifecycle, _continuation_args(result), retry, tmp_path / "current-pass", permitted=True)
    if operation == "execution-recovery":
        capture = json.loads(Path(result["capture_path"]).read_bytes())
        git = shutil.which("git")
        assert git is not None
        repository = Path(capture["repository_root"])
        arguments = ("restore", "--staged", "state.rs") if resumes % 2 else ("add", "state.rs")
        _run_test_git(git, "-C", str(repository), *arguments)
        result = runtime.resume_after_external_metadata(
            {
                **result["lifecycle_input"],
                "previous_capture": capture,
                "new_capture": _scope_data(git, repository, "baseline", None, ()),
                "journal_path": result["journal_path"],
                "dispatches_path": result["dispatches_path"],
                "artifact_store": str(tmp_path / "resumed-after-recovery"),
            }
        )
        assert audit["node_id"] in result["preserved_node_ids"]
        assert _ready(result)["ready_node_ids"] == [gate["node_id"]]
        retry = _ready(result)["ready_dispatches"][0]
        lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
        _compile_aggregate(lifecycle, _continuation_args(result), retry, tmp_path / "post-recovery-staging-pass", permitted=True)
    if operation != "expansion":
        result = _expand(tmp_path, result)
    assert audit["node_id"] not in _finish_repair(tmp_path, result)
    assert all(path.read_bytes() == content for path, content in history.items())


def test_ordinary_expansion_keeps_completed_barrier_and_audit(tmp_path: Path) -> None:
    result, audit, history = _barrier_fixture(tmp_path, resumes=0)
    gate_id = result["lifecycle_input"]["plan"]["pre_review_validation_nodes"][0]
    expanded = _expand(tmp_path, result)
    ready = _ready(expanded)
    assert {gate_id, audit["node_id"]} <= set(ready["lifecycle"]["accepted_node_ids"])
    assert gate_id not in ready["ready_node_ids"]
    assert audit["node_id"] not in _finish_repair(tmp_path, expanded)
    assert all(path.read_bytes() == content for path, content in history.items())
