"""Saved content repair followed by external staging before publication."""

import json
import shlex
import sys
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_review_graph_execution_recovery import _compile_aggregate
from test_review_graph_git import _discovery_payload
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compact_independent_payload,
    _compile_repair_fixture_entry,
    _late_validation_plan,
    _late_validation_requirement,
    _publish_worker_bytes,
    _run_test_git,
)
from test_review_graph_transitions import _materialize, _payload


def _staged_repair(tmp_path: Path, dependency: str = "source") -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[Path, bytes]]:
    git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    template.update(concrete_change_target=True, change_target="fixture repair")
    template["validation_requirements"][0].update(commands=["just check-fast > ci-final.log"], canonical_recipe=None)
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    audit = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    payload = _discovery_payload(audit) if dependency == "source-discovery" else _payload(["tool.py"])
    if dependency == "index":
        payload["git_dependencies"] = [{"kind": "index", "reason": "Judgment depends on staging."}]
    planned = audit["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload["validation_requirements"] = [
        {
            "requirement_id": planned["requirement_ids"][0],
            "planned_validation_digest": planned["planned_validation_digest"],
            "owner": audit["dispatch"]["skill_id"],
            "reason": "Required fixture validation",
            "expected_evidence": "Checks pass",
        }
    ]
    content, metadata = runtime.compile_review(
        {"dispatch": {**audit["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(audit["artifact_path"]).write_bytes(content)
    Path(audit["metadata_path"]).write_text(json.dumps(metadata))
    sources = [{key: audit[key] for key in ("artifact_path", "metadata_path")}]
    validator = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    unit = validator["dispatch"]["validation_unit"]
    content, metadata = runtime.compile_validation(
        {
            "dispatch": {**validator["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]},
            "payload": {
                "artifacts": [],
                "limitations": [],
                "status": "failed",
                "executions": [
                    {
                        "artifact_paths": [],
                        "command": unit["commands"][0],
                        "working_directory": unit["working_directories"][0],
                        "elapsed": "1s",
                        "evidence": "Fixture assertion failed; retained historical failure.",
                        "executor": validator["node_id"],
                        "exit_code": 1,
                        "result": "failed",
                    }
                ],
            },
        }
    )
    Path(validator["artifact_path"]).write_bytes(content)
    Path(validator["metadata_path"]).write_text(json.dumps(metadata))
    sources.append({key: validator[key] for key in ("artifact_path", "metadata_path")})
    journal = tmp_path / "failed-execution.jsonl"
    runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(validator["node_id"], "accepted", source=sources[-1]))
    history = {Path(path): Path(path).read_bytes() for source in sources for path in source.values()}
    history[journal] = journal.read_bytes()
    (repository / "state.rs").write_text("pub fn state() { assert!(true); }\n")
    repaired = _scope_data(git, repository, "baseline", None, ())
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    staged = _scope_data(git, repository, "baseline", None, ())
    return (
        git,
        repository,
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": repaired,
            "post_repair_capture": staged,
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": ["state.rs"],
            "sources": sources,
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
        },
        audit,
        history,
    )


def _finish_repair(tmp_path: Path, result: dict[str, Any]) -> list[str]:
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    plan = runtime._graph_plan(lifecycle["plan"])
    journal = Path(result["journal_path"])
    executed: list[str] = []
    for _ in range(plan.complete_node_count + 1):
        events, _states, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = runtime.next_ready_nodes(lifecycle, journal_events=events, dispatch_set=result["dispatch_set"])
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready["blockers"]
        for entry in ready["ready_dispatches"]:
            if entry["dispatch"].get("mode") == "independent-review":
                payload = _compact_independent_payload(entry["dispatch"])
                payload.update(before_state=result["current_source_state"], after_state=result["current_source_state"])
                _publish_worker_bytes(entry, json.dumps(payload).encode())
                assert (
                    runtime.main(
                        [
                            "compile-node",
                            "--input",
                            result["lifecycle_input_path"],
                            "--dispatches",
                            result["dispatches_path"],
                            "--journal",
                            str(journal),
                            "--node-id",
                            entry["node_id"],
                            "--before-capture",
                            result["capture_path"],
                            "--after-capture",
                            result["capture_path"],
                            "--output",
                            str(tmp_path / "independent-result.json"),
                        ]
                    )
                    == 0
                )
            else:
                _compile_repair_fixture_entry(entry, lifecycle, journal)
            executed.append(entry["node_id"])
    else:
        pytest.fail("repair plus staging did not complete within its node bound")
    output = tmp_path / "final.json"
    assert (
        runtime.main(
            [
                "finalize-proof",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                str(journal),
                "--current-capture",
                result["capture_path"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    final = json.loads(output.read_bytes())
    assert final["status"] == "complete", final["blockers"]
    assert final["repository_validation_status"] == "passed"
    assert set(final["proof"]["accepted_validation_evidence_ids"]) == {
        entry["dispatch"]["evidence_id"] for entry in result["dispatch_set"]["dispatches"] if entry["result_contract"] == "compact-validation"
    }
    return executed


@pytest.mark.parametrize("dependency", ["source", "source-discovery", "index", "changed-validation"])
def test_repair_then_external_staging_preserves_only_eligible_evidence(tmp_path: Path, dependency: str) -> None:
    git, repository, request, audit, history = _staged_repair(tmp_path, dependency)
    if dependency == "changed-validation":
        request["planning_template"]["validation_requirements"][0]["commands"] = ["just check-fast > ci-release-review.log"]
    original_request = json.dumps(request, sort_keys=True)
    input_path, output_path = tmp_path / "request.json", tmp_path / "result.json"
    input_path.write_text(json.dumps(request))
    assert runtime.main(["advance-after-mutation", "--input", str(input_path), "--output", str(output_path)]) == 0
    result = json.loads(output_path.read_bytes())
    assert result["transition_kind"] == "repair-then-observed-external-git-metadata"
    assert result["capture"] == request["post_repair_capture"]
    retained = json.loads(Path(result["repair_transition_path"]).read_bytes())
    assert retained["capture"] == request["new_capture"]
    assert retained["previous_capture"] == request["previous_capture"]
    assert retained["historical_evidence_sources"] == request["sources"]
    old_id = audit["dispatch"]["evidence_id"]
    assert (old_id in result["reused_evidence_ids"]) is (dependency in {"source", "source-discovery"})
    lineage = {item["node_id"]: item["replaces_node_ids"] for item in result["replacement_lineage"]}
    assert set(lineage) == {node["node_id"] for node in result["new_plan"]["actual_worker_nodes"]}
    if dependency == "index":
        assert old_id in result["stale_evidence_ids"]
        restored = next(item for item in result["node_decisions"] if old_id in item.get("replaced_evidence_ids", []))
        assert lineage[restored["node_id"]] == [audit["node_id"]]
        assert restored["node_id"] not in {item["node_id"] for item in retained["replacement_lineage"]}
        assert audit["node_id"] in {item["node_id"] for item in result["invalidated_nodes"]}
        assert audit["node_id"] not in result["unaffected_node_ids"]
    executed = _finish_repair(tmp_path, result)
    assert len(executed) == len(set(executed))
    assert all(path.read_bytes() == content for path, content in history.items())
    assert _scope_data(git, repository, "baseline", None, ()) == request["post_repair_capture"]
    assert json.dumps(request, sort_keys=True) == original_request


@pytest.mark.parametrize("change", ["content", "mode", "instructions", "head", "boundary", "forged-bridge", "stale-live-index"])
def test_repair_staging_rejects_unverified_composition_before_publication(tmp_path: Path, change: str) -> None:
    git, repository, request, _audit, history = _staged_repair(tmp_path)
    if change == "content":
        (repository / "tool.py").write_text("value = 3\n")
    elif change == "mode":
        path = repository / "tool.py"
        path.chmod(path.stat().st_mode ^ 0o111)
    elif change == "instructions":
        (repository / "AGENTS.md").write_text("New applicable instructions.\n")
    elif change == "head":
        _run_test_git(git, "-C", str(repository), "commit", "-m", "externally committed")
    elif change == "boundary":
        request["post_repair_capture"] = _scope_data(git, repository, "baseline", None, ("state.rs",))
    elif change == "forged-bridge":
        request["new_capture"]["repository_path_fingerprints"]["tool.py"] = "0" * 64
    else:
        _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    if change in {"content", "mode", "instructions", "head"}:
        request["post_repair_capture"] = _scope_data(git, repository, "baseline", None, ())
    current = _scope_data(git, repository, "baseline", None, ())
    with pytest.raises(ValueError, match=r"metadata transition|fingerprint|independent recapture"):
        runtime.advance_after_mutation(request)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in history.items())
    assert _scope_data(git, repository, "baseline", None, ()) == current


def _continuation_args(result: dict[str, Any]) -> Namespace:
    return Namespace(journal=Path(result["journal_path"]), dispatches=Path(result["dispatches_path"]), current_capture=Path(result["capture_path"]))


def _run_continuation(tmp_path: Path, operation: str, request: dict[str, Any], args: Namespace) -> dict[str, Any]:
    input_path, output_path = tmp_path / f"{operation}-input.json", tmp_path / f"{operation}-result.json"
    input_path.write_text(json.dumps(request))
    assert (
        runtime.main(
            [
                operation,
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--dispatches",
                str(args.dispatches),
                "--journal",
                str(args.journal),
                "--current-capture",
                str(args.current_capture),
            ]
        )
        == 0
    )
    result = json.loads(output_path.read_bytes())
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    assert lifecycle["source_state"] == request["source_state"]
    assert lifecycle["external_metadata_transitions"] == request["external_metadata_transitions"]
    return {
        **result,
        "lifecycle_input": lifecycle,
        "dispatch_set": json.loads(Path(result["dispatches_path"]).read_bytes()),
        "capture_path": result.get("current_capture_path", str(args.current_capture)),
        "current_source_state": list(runtime._capture_source_state(args.current_capture)),
    }


def _ordinary_resume(tmp_path: Path, git: str, repository: Path, request: dict[str, Any]) -> dict[str, Any]:
    _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(
        bootstrap_document(capture, request["planning_template"]), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository
    )
    directory = tmp_path / "ordinary"
    directory.mkdir()
    lifecycle, _entries, dispatches = _materialize(directory, capture, plan)
    journal = directory / "execution.jsonl"
    journal.write_text("")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    return runtime.resume_after_external_metadata(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "dispatches_path": str(dispatches),
            "journal_path": str(journal),
            "artifact_store": str(tmp_path / "resumed"),
        }
    )


@pytest.mark.parametrize("transition", ["repair", "ordinary"])
def test_staged_repair_can_expand_late_validation_and_finish(tmp_path: Path, transition: str) -> None:
    git, repository, request, _audit, history = _staged_repair(tmp_path)
    result = runtime.advance_after_mutation(request) if transition == "repair" else _ordinary_resume(tmp_path, git, repository, request)
    lifecycle = result["lifecycle_input"]
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"].get("mode") == "audit")
    requirement = {**_late_validation_requirement(), "commands": ["true"], "working_directory": str(repository)}
    payload = {**_payload(entry["dispatch"]["owned_paths"]), "validation_requirements": [requirement]}
    content, metadata = runtime.compile_review(
        {"dispatch": {**entry["dispatch"], "before_state": result["current_source_state"], "after_state": result["current_source_state"]}, "payload": payload}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    runtime.append_journal_event(Path(result["journal_path"]), lifecycle, runtime.JournalEventRequest(entry["node_id"], "accepted", source=entry))
    history.update({Path(entry[key]): Path(entry[key]).read_bytes() for key in ("artifact_path", "metadata_path")})
    history[Path(result["journal_path"])] = Path(result["journal_path"]).read_bytes()
    addition = {**_late_validation_plan(), "source_state": lifecycle["source_state"], "commands": ["true"], "working_directories": [str(repository)]}
    expanded = _run_continuation(
        tmp_path,
        "reconcile-validation-requirements",
        {**lifecycle, "artifact_store": str(tmp_path / "expansion"), "validation_requirements": [addition]},
        _continuation_args(result),
    )
    assert entry["node_id"] in expanded["retained_node_ids"]
    executed = _finish_repair(tmp_path, expanded)
    assert entry["node_id"] not in executed
    assert all(path.read_bytes() == content for path, content in history.items())


def _operation_request(tmp_path: Path, operation: str, result: dict[str, Any]) -> dict[str, Any]:
    request = {**deepcopy(result["lifecycle_input"]), "artifact_store": str(tmp_path / "rejected-continuation")}
    if operation == "fallback-to-coordinator":
        entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"].get("mode") == "audit")
        return {**request, "node_id": entry["node_id"], "worker_created": False, "reason": "Fixture worker capacity exhausted."}
    if operation.startswith("recover-validation"):
        entry = next(item for item in result["dispatch_set"]["dispatches"] if item["result_contract"] == "compact-validation")
        request.update(_recovery_request(tmp_path, result, entry, checks_started=operation.endswith("execution")))
        if operation.endswith("execution"):
            request["failure_evidence"] = {
                key: str(tmp_path / "unreached-failure-input")
                for key in ("log_path", "diagnostic", "before_capture", "after_capture", "workspace_before", "workspace_after")
            }
    return request


@pytest.mark.parametrize(
    "operation", ["reconcile-validation-requirements", "fallback-to-coordinator", "recover-validation-launch", "recover-validation-execution"]
)
@pytest.mark.parametrize("defect", ["stale-capture", "tampered-chain", "disconnected-chain"])
def test_metadata_continuations_reject_stale_captures_and_unverified_chains(tmp_path: Path, operation: str, defect: str) -> None:
    _git, _repository, repair, _audit, _history = _staged_repair(tmp_path)
    result = runtime.advance_after_mutation(repair)
    request = _operation_request(tmp_path, operation, result)
    args = _continuation_args(result)
    if defect == "stale-capture":
        args.current_capture = tmp_path / "stale-capture.json"
        args.current_capture.write_text(json.dumps(repair["new_capture"]))
    elif defect == "tampered-chain":
        request["external_metadata_transitions"][0]["after"]["index_fingerprint"] = "0" * 64
    else:
        request["external_metadata_transitions"] *= 2
    original = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match=r"capture differs|unchanged source state|repository fingerprint|do not form a chain"):
        getattr(runtime, operation.replace("-", "_"))(request, args)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in original.items())


@pytest.mark.parametrize(
    "operation", ["reconcile-validation-requirements", "fallback-to-coordinator", "recover-validation-launch", "recover-validation-execution"]
)
def test_metadata_continuations_reject_stale_validator_evidence(tmp_path: Path, operation: str) -> None:
    git, repository, repair, _audit, history = _staged_repair(tmp_path)
    staged = repair.pop("post_repair_capture")
    _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    result = runtime.advance_after_mutation(repair)
    result["current_source_state"] = result["new_source_state"]
    validator = next(item for item in result["dispatch_set"]["dispatches"] if item["result_contract"] == "compact-validation")
    if operation == "recover-validation-launch":
        _block_staged_validator(validator, result)
    else:
        _compile_repair_fixture_entry(validator, result["lifecycle_input"], Path(result["journal_path"]))
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    assert _scope_data(git, repository, "baseline", None, ()) == staged
    # A valid chain alone must not promote old validation or launch failures.
    result["lifecycle_input"]["external_metadata_transitions"] = [{"before": repair["new_capture"], "after": staged}]
    args = _continuation_args(result)
    args.current_capture = tmp_path / "staged.json"
    args.current_capture.write_text(json.dumps(staged))
    request = _operation_request(tmp_path, operation, result)
    history.update({Path(result[key]): Path(result[key]).read_bytes() for key in ("journal_path", "dispatches_path", "lifecycle_input_path")})
    history.update({Path(validator[key]): Path(validator[key]).read_bytes() for key in ("artifact_path", "metadata_path")})
    with pytest.raises(ValueError, match="Evidence requires revalidation after external staging"):
        getattr(runtime, operation.replace("-", "_"))(request, args)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in history.items())


def test_staged_repair_can_fallback_and_finish(tmp_path: Path) -> None:
    _git, _repository, request, _audit, history = _staged_repair(tmp_path)
    result = runtime.advance_after_mutation(request)
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"].get("mode") == "audit")
    fallback = _run_continuation(
        tmp_path,
        "fallback-to-coordinator",
        {
            **result["lifecycle_input"],
            "artifact_store": str(tmp_path / "fallback"),
            "node_id": entry["node_id"],
            "worker_created": False,
            "reason": "Fixture worker creation exhausted capacity.",
        },
        _continuation_args(result),
    )
    changed = next(item for item in fallback["dispatch_set"]["dispatches"] if item["node_id"] == entry["node_id"])
    assert changed["dispatch"]["execution_location"] == "coordinator"
    assert changed["dispatch"]["external_metadata_transitions"] == result["lifecycle_input"]["external_metadata_transitions"]
    assert entry["node_id"] in _finish_repair(tmp_path, fallback)
    assert all(path.read_bytes() == content for path, content in history.items())


def _recovery_request(tmp_path: Path, result: dict[str, Any], entry: dict[str, Any], *, checks_started: bool) -> dict[str, Any]:
    return {
        **result["lifecycle_input"],
        "artifact_store": str(tmp_path / "recovery"),
        "node_id": entry["node_id"],
        "failure_kind": "executor-permission",
        "checks_started": checks_started,
        "reason": "The fixture executor denied access.",
        "remedy": "Use the permitted fixture executor.",
        "environment": "permitted native executor",
        "permission_change": "Enable the fixture capability.",
        "executor_permissions": "require_escalated",
    }


def _block_staged_validator(entry: dict[str, Any], result: dict[str, Any]) -> None:
    content, metadata = runtime.compile_validation(
        {
            "dispatch": {**entry["dispatch"], "before_state": result["current_source_state"], "after_state": result["current_source_state"]},
            "payload": {"executions": [], "status": "blocked", "limitations": ["Permission denied before launch."]},
        }
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    runtime.append_journal_event(
        Path(result["journal_path"]),
        result["lifecycle_input"],
        runtime.JournalEventRequest(entry["node_id"], "blocked", source=entry, reason="Permission denied before launch."),
    )


@pytest.mark.parametrize("checks_started", [False, True])
def test_staged_repair_can_recover_validation_and_finish(tmp_path: Path, checks_started: bool) -> None:
    _git, _repository, request, _audit, history = _staged_repair(tmp_path)
    if checks_started:
        executor = tmp_path / "executor"
        executor.mkdir()
        script = executor / "aggregate.py"
        script.write_text(
            'import os\nprint("2 checks passed", flush=True)\nif os.environ["FIXTURE_SOCKET_ACCESS"] != "permitted":\n'
            '    raise PermissionError(1, "Operation not permitted")\nprint("build completed")\n'
        )
        request["planning_template"]["validation_requirements"][0].update(
            commands=[shlex.join([sys.executable, str(script)])],
            working_directories=[str(executor)],
            canonical_recipe="just ci",
            isolation_root=str(executor),
            requires_isolation=True,
            allowed_artifacts=[{"path": str(executor / "ci.log"), "kind": "log", "repository_status": "outside-repository"}],
        )
    result = runtime.advance_after_mutation(request)
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["result_contract"] == "compact-validation")
    recovery = _recovery_request(tmp_path, result, entry, checks_started=checks_started)
    args = _continuation_args(result)
    if checks_started:
        lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
        recovery["failure_evidence"] = _compile_aggregate(lifecycle, args, entry, tmp_path / "failed-attempt", permitted=False)
        for field in ("before_capture", "after_capture", "workspace_before", "workspace_after"):
            stale = tmp_path / f"stale-{field}.json"
            snapshot = json.loads(Path(recovery["failure_evidence"][field]).read_bytes())
            if field.endswith("capture"):
                snapshot = request["new_capture"]
            else:
                snapshot["observed_source_state"] = result["lifecycle_input"]["source_state"]
            stale.write_text(json.dumps(snapshot))
            rejected = {**recovery, "failure_evidence": {**recovery["failure_evidence"], field: str(stale)}}
            with pytest.raises(ValueError, match=r"unchanged before/after source captures|predates the current external metadata state"):
                runtime.recover_validation_execution(rejected, args)
            assert not Path(recovery["artifact_store"]).exists()
    else:
        _block_staged_validator(entry, result)
    history.update({Path(result[key]): Path(result[key]).read_bytes() for key in ("journal_path", "lifecycle_input_path", "dispatches_path")})
    history.update({Path(entry[key]): Path(entry[key]).read_bytes() for key in ("artifact_path", "metadata_path")})
    operation = "recover-validation-execution" if checks_started else "recover-validation-launch"
    recovered = _run_continuation(tmp_path, operation, recovery, args)
    prior = recovered["lifecycle_input"]["plan"]["validation_recoveries"][0]
    history_lifecycle = next(item for item in prior["preserved_files"] if item["path"].endswith("lifecycle.json"))
    assert json.loads(Path(history_lifecycle["path"]).read_bytes()) == result["lifecycle_input"]
    if checks_started:
        retry = next(item for item in recovered["dispatch_set"]["dispatches"] if item["node_id"] == entry["node_id"])
        lifecycle = {**recovered["lifecycle_input"], "current_source_state": recovered["current_source_state"]}
        _compile_aggregate(lifecycle, _continuation_args(recovered), retry, tmp_path / "successful-attempt", permitted=True)
    _finish_repair(tmp_path, recovered)
    assert all(path.read_bytes() == content for path, content in history.items())


def test_repeated_repair_then_staging_retains_original_replacement_lineage(tmp_path: Path) -> None:
    git, repository, request, audit, history = _staged_repair(tmp_path, "index")
    request.pop("post_repair_capture")
    _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    first = runtime.advance_after_mutation(request)
    evidence_id = audit["dispatch"]["evidence_id"]
    assert evidence_id in first["reused_evidence_ids"]
    assert audit["node_id"] not in {item["node_id"] for item in first["new_plan"]["actual_worker_nodes"]}
    history.update({path: path.read_bytes() for path in Path(request["artifact_store"]).rglob("*") if path.is_file()})
    (repository / "state.rs").write_text("pub fn state() { assert_eq!(1, 1); }\n")
    repaired = _scope_data(git, repository, "baseline", None, ())
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    second = runtime.advance_after_mutation(
        {
            **request,
            **first["lifecycle_input"],
            "repair_epoch": 2,
            "authorization_before": "review-and-fix",
            "previous_capture": first["capture"],
            "new_capture": repaired,
            "post_repair_capture": _scope_data(git, repository, "baseline", None, ()),
            "sources": [{key: audit[key] for key in ("artifact_path", "metadata_path")}],
        }
    )
    restored = next(item for item in second["node_decisions"] if evidence_id in item.get("replaced_evidence_ids", []))
    lineage = next(item for item in second["replacement_lineage"] if item["node_id"] == restored["node_id"])
    assert lineage["replaces_node_ids"] == [audit["node_id"]]
    assert restored["node_id"] in _finish_repair(tmp_path, second)
    assert all(path.read_bytes() == content for path, content in history.items())
