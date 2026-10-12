"""Shared control authority survives stale copies, racing publication, and extensions."""

import json
from argparse import Namespace
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict
from functools import partial
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_control import control_marker_paths, verify_run_control
from review_graph_lifecycle import lifecycle_from_document
from review_graph_plan import graph_plan_digest, plan_from_document, plan_graph, validation_requirements_from_document
from test_review_graph_commit import _commit_fixture
from test_review_graph_lifecycle import _control_args, _control_cli, _control_fixture, _two_repairs
from test_review_graph_runtime import _baseline_mutation_fixture
from test_review_graph_transitions import _materialize


def _ready(result: dict[str, Any]) -> dict[str, Any]:
    lifecycle = result["lifecycle_input"]
    plan = runtime._graph_plan(lifecycle["plan"])
    events, _state, _head = runtime.read_execution_journal(Path(result["journal_path"]), plan=plan, source_state=tuple(lifecycle["source_state"]))
    return runtime.next_ready_nodes(
        {**lifecycle, "current_source_state": result.get("current_source_state", lifecycle["source_state"])},
        journal_events=events,
        dispatch_set=result["dispatch_set"],
    )


def test_original_copy_stays_stopped_without_a_journal_path(tmp_path: Path) -> None:
    request, args, repository = _control_fixture(tmp_path)
    original = {key: request[key] for key in ("plan", "source_state")}
    stopped = runtime.review_control(request, args)
    assert "journal_path" not in original
    assert runtime._review_stop_reason(original) == "user-stop: Stop now"
    store = tmp_path / "replayed-materialization"
    with pytest.raises(ValueError, match="review stopped"):
        runtime.materialize_dispatches(
            {
                **original,
                "artifact_store": str(store),
                "repository_root": str(repository),
                "authorization": "review-only",
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )
    assert not store.exists()
    assert _ready(stopped)["ready_node_ids"] == []


@pytest.mark.parametrize("operation", ["commit", "repair"])
def test_stop_racing_publication_blocks_the_returned_continuation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str) -> None:
    request: dict[str, Any]
    if operation == "commit":
        request, _entries, _sources = _commit_fixture(tmp_path)
        invoke = runtime.resume_after_authorized_commit
    else:
        git, repository, template, capture, plan = _baseline_mutation_fixture(tmp_path)
        lifecycle, _entries, dispatches = _materialize(tmp_path, capture, plan)
        (repository / "tool.py").write_text("value = 2\n")
        request = {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "planning_template": template,
            "changed_paths": ["tool.py"],
            "authorization_before": "review-and-fix",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "dispatches_path": str(dispatches),
            "journal_path": str(tmp_path / "original.jsonl"),
        }
        invoke = runtime.advance_after_mutation
    capture_path = tmp_path / "current.json"
    capture_path.write_text(json.dumps(request["new_capture"]))
    args = Namespace(
        journal=Path(request["journal_path"]), dispatches=Path(request["dispatches_path"]), current_capture=capture_path, output=tmp_path / "stop-result.json"
    )
    stop = {key: request[key] for key in ("plan", "source_state")}
    stop.update(action="stop", reason="Stop during publication", artifact_store=str(tmp_path / "terminal"))
    publish = runtime._publish_materialized_writes
    stopped: list[dict[str, Any]] = []

    def stop_before_publish(store: Path, pending: dict[Path, tuple[bytes, int]]) -> bool:
        if not stopped:
            stopped.append({})
            stopped[0] = runtime.review_control(stop, args)
        return publish(store, pending)

    monkeypatch.setattr(runtime, "_publish_materialized_writes", stop_before_publish)
    result = invoke(request)
    assert stopped[0]["status"] == "stopped"
    assert result["lifecycle_input"]["plan"]["review_lifecycle"]["run_control"] == request["plan"]["review_lifecycle"]["run_control"]
    assert Path(result["journal_path"]) != args.journal
    ready = _ready(result)
    assert ready["stop_reason"] == "user-stop: Stop during publication"
    assert ready["ready_dispatches"] == []
    assert not ready["complete"]
    node = result["dispatch_set"]["dispatches"][0]["node_id"]
    with pytest.raises(ValueError, match="review stopped"):
        runtime.append_journal_event(Path(result["journal_path"]), result["lifecycle_input"], runtime.JournalEventRequest(node, "in-flight"))


def test_extension_preserves_history_and_an_older_generation_can_stop_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result, args = _two_repairs(tmp_path)
    stopped = runtime.review_control(
        {**result["lifecycle_input"], "action": "begin-repair", "authorization": "review-and-fix", "artifact_store": str(tmp_path / "exhaustion")}, args
    )
    request = {
        **stopped["lifecycle_input"],
        "action": "extend-budget",
        "additional_epochs": 1,
        "user_authorization": "One more batch",
        "artifact_store": str(tmp_path / "extension"),
    }
    extension_args = _control_args(tmp_path, stopped)
    extended = runtime.review_control(request, extension_args)
    old = json.loads(json.dumps(stopped["review_lifecycle"]))
    new = json.loads(json.dumps(extended["review_lifecycle"]))
    assert new["repairs_completed"] == old["repairs_completed"] == 2
    assert new["budget_extensions"] == [*old["budget_extensions"], {"additional_epochs": 1, "user_authorization": "One more batch"}]
    assert new["run_control"]["identity"] == old["run_control"]["identity"]
    assert new["run_control"]["generation"] != old["run_control"]["generation"]
    reason = runtime._review_stop_reason(stopped["lifecycle_input"])
    assert reason is not None
    assert reason.startswith("repair-budget-exhausted")
    assert runtime._review_stop_reason(extended["lifecycle_input"]) is None
    with pytest.raises(ValueError, match="already extended"):
        runtime.review_control({**request, "additional_epochs": 2, "user_authorization": "A distinct grant"}, extension_args)
    extension_args.output = tmp_path / "extension-replay.json"
    assert _control_cli(request, extension_args, tmp_path) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["review_lifecycle"] == new
    stop_request = {**stopped["lifecycle_input"], "action": "stop", "reason": "Stop all generations", "artifact_store": str(tmp_path / "user-stop")}
    extension_args.output = tmp_path / "user-stop-result.json"
    assert _control_cli(stop_request, extension_args, tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["stop_reason"] == "user-stop: Stop all generations"
    assert _ready(extended)["ready_dispatches"] == []
    assert runtime._review_stop_reason(extended["lifecycle_input"]) == "user-stop: Stop all generations"


def test_journal_marker_failure_keeps_shared_stop_and_replay_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    request, args, _repository = _control_fixture(tmp_path)
    journal_marker = args.journal.with_name(args.journal.name + ".stop.json")
    publish = runtime._write_bytes_atomically_once

    def fail_journal_copy(path: Path, content: bytes, *, mode: int) -> bool:
        if path == journal_marker:
            msg = "journal marker storage failed"
            raise OSError(msg)
        return publish(path, content, mode=mode)

    monkeypatch.setattr(runtime, "_write_bytes_atomically_once", fail_journal_copy)
    assert _control_cli(request, args, tmp_path) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["cancel_node_ids"]
    assert not journal_marker.exists()
    assert runtime._review_stop_reason({key: request[key] for key in ("plan", "source_state")}) == "user-stop: Stop now"
    args.output = tmp_path / "recovered.json"
    assert _control_cli(request, args, tmp_path) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["cancel_node_ids"] == first["cancel_node_ids"]
    assert second["control_result"] == first["control_result"]


@pytest.mark.parametrize("target", ["identity", "generation", "user-stop", "budget-stop", "extension", "lock"])
def test_dangling_control_symlinks_cannot_admit_work(tmp_path: Path, target: str) -> None:
    request, _args, _repository = _control_fixture(tmp_path)
    binding = lifecycle_from_document(request["plan"]["review_lifecycle"]).run_control
    assert binding is not None
    paths = {
        "identity": Path(binding.identity.path),
        "generation": Path(binding.generation.path),
        "user-stop": control_marker_paths(binding)[0],
        "budget-stop": control_marker_paths(binding)[1],
        "extension": Path(binding.generation.path).with_suffix(".extension.json"),
        "lock": Path(binding.identity.path).with_name("admission.lock"),
    }
    path = paths[target]
    path.unlink(missing_ok=True)
    path.symlink_to(tmp_path / "missing-control-target")
    journal = tmp_path / "new-journal.jsonl"
    node = request["plan"]["actual_worker_nodes"][0]["node_id"]
    with pytest.raises((ValueError, OSError)):
        runtime.append_journal_event(journal, {key: request[key] for key in ("plan", "source_state")}, runtime.JournalEventRequest(node, "in-flight"))
    assert not journal.exists()


def test_unbound_transport_remains_readable_and_cannot_execute(tmp_path: Path) -> None:
    request, _args, repository = _control_fixture(tmp_path)
    document = {key: deepcopy(request[key]) for key in ("plan", "source_state")}
    document["plan"]["review_lifecycle"]["run_control"] = None
    plan = runtime._graph_plan(document["plan"])
    assert plan.review_lifecycle.run_control is None
    with pytest.raises(ValueError, match="unbound review lifecycle"):
        runtime.materialize_dispatches({**document, "artifact_store": str(tmp_path / "unbound"), "repository_root": str(repository)})
    assert not (tmp_path / "unbound").exists()


def test_control_references_are_immutable_and_bound_to_the_repository(tmp_path: Path) -> None:
    request, _args, repository = _control_fixture(tmp_path)
    original = deepcopy(request["plan"]["review_lifecycle"])
    lifecycle = lifecycle_from_document(original)
    binding = lifecycle.run_control
    assert binding is not None
    original["run_control"]["identity"]["path"] = str(tmp_path / "substituted")
    field = "path"
    with pytest.raises(FrozenInstanceError):
        setattr(binding.identity, field, str(tmp_path / "substituted"))
    plan = runtime._graph_plan(request["plan"])
    assert graph_plan_digest(runtime._graph_plan(json.loads(json.dumps(asdict(plan))))) == graph_plan_digest(plan)
    with pytest.raises(ValueError, match="repository_root differs"):
        verify_run_control(binding, repository=repository.parent)


@pytest.mark.parametrize("constructor", ["document", "graph"])
def test_initialization_does_not_infer_repository_from_validation_directory(tmp_path: Path, constructor: str) -> None:
    _git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    document = bootstrap_document(capture, template)
    validation_directory = tmp_path / "validation-workspace"
    validation_directory.mkdir()
    document["validation_requirements"][0]["working_directories"] = [str(validation_directory)]
    store = tmp_path / "unissued-control"
    if constructor == "document":
        plan = plan_from_document(document, control_root=store)
    else:
        plan = plan_graph((), validation_requirements_from_document(document, repository), (), control_root=store)
    assert plan.review_lifecycle.run_control is None
    assert not store.exists()


@pytest.mark.parametrize("constructor", ["document", "graph"])
def test_initialization_binds_explicit_repository_with_external_validation_directory(tmp_path: Path, constructor: str) -> None:
    _git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    document = bootstrap_document(capture, template)
    validation_directory = tmp_path / "validation-workspace"
    validation_directory.mkdir()
    document["validation_requirements"][0]["working_directories"] = [str(validation_directory)]
    store = tmp_path / "issued-control"
    if constructor == "document":
        plan = plan_from_document(document, repository_root=repository, control_root=store)
    else:
        plan = plan_graph((), validation_requirements_from_document(document, repository), (), repository_root=repository, control_root=store)
    binding = plan.review_lifecycle.run_control
    assert binding is not None
    verify_run_control(binding, repository=repository)
    with pytest.raises(ValueError, match="repository_root differs"):
        verify_run_control(binding, repository=validation_directory)


@pytest.mark.parametrize("constructor", ["document", "graph"])
def test_initialization_rejects_repository_control_store_before_writes(tmp_path: Path, constructor: str) -> None:
    _git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    document = bootstrap_document(capture, template)
    inside = repository / "control-store"
    if constructor == "document":
        initialize = partial(plan_from_document, document, repository_root=repository, control_root=inside)
    else:
        initialize = partial(plan_graph, (), validation_requirements_from_document(document, repository), (), repository_root=repository, control_root=inside)
    with pytest.raises(ValueError, match=r"overlaps|external control store"):
        initialize()
    assert not inside.exists()
