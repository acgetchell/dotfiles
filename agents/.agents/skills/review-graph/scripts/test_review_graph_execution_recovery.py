"""Permission failures after partial aggregate execution retain exact attempt history."""

import json
import os
import shlex
import subprocess
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest
from review_graph_executor import executor_permissions
from review_graph_plan import plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    _graph_plan,
    _planned_validation_digest,
    _validation_reconciliation,
    append_journal_event,
    capture_workspace_snapshot,
    main,
    materialize_dispatches,
    next_ready_nodes,
    preflight_validation,
    read_execution_journal,
    recover_validation_execution,
    recover_validation_launch,
)
from test_review_graph_repairs import _recovery_fixture
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _compile_repair_fixture_entry, _json_plan, _publish_worker_bytes, _sparse_plan_document

DENIAL = "PermissionError: [Errno 1] Operation not permitted"


def _ready(lifecycle: dict[str, Any], args: Namespace) -> dict[str, Any]:
    events, _state, _head = read_execution_journal(args.journal, plan=_graph_plan(lifecycle["plan"]), source_state=tuple(lifecycle["source_state"]))
    return next_ready_nodes(
        {**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=json.loads(args.dispatches.read_bytes())
    )


def _compile_aggregate(lifecycle: dict[str, Any], args: Namespace, entry: dict[str, Any], directory: Path, *, permitted: bool) -> dict[str, str]:
    """Run a deterministic executor fault model, then use the real compiler gates."""
    directory.mkdir()
    append_journal_event(args.journal, lifecycle, JournalEventRequest(entry["node_id"], "in-flight"))
    before = capture_workspace_snapshot(entry["dispatch"])
    unit = entry["dispatch"]["validation_unit"]
    preceding = []
    if len(unit["commands"]) > 1:
        started = time.monotonic()
        passed = subprocess.run(  # noqa: S603 - fixture-owned independent command, before the failing aggregate.
            shlex.split(unit["commands"][0]), cwd=unit["working_directories"][0], capture_output=True, check=True
        )
        preceding.append(
            {
                "command": unit["commands"][0],
                "working_directory": unit["working_directories"][0],
                "executor": entry["node_id"],
                "result": "passed",
                "exit_code": passed.returncode,
                "elapsed": f"{time.monotonic() - started}s",
                "evidence": "separate fixture command passed",
                "artifact_paths": [],
            }
        )
    started = time.monotonic()
    run = subprocess.run(  # noqa: S603 - fixture-owned aggregate models a denied capability without requiring actual socket access.
        shlex.split(unit["commands"][-1]),
        cwd=unit["working_directories"][0],
        env={**os.environ, "FIXTURE_SOCKET_ACCESS": "permitted" if permitted else "denied"},
        capture_output=True,
        check=False,
    )
    elapsed = time.monotonic() - started
    output = run.stdout + run.stderr
    assert b"2 checks passed" in output
    assert (b"build completed" in output) == permitted
    log = Path(unit["allowed_artifacts"][0]["path"])
    log.write_bytes(output)
    after = capture_workspace_snapshot(entry["dispatch"])
    status = "passed" if run.returncode == 0 else "failed"
    payload = {
        "status": status,
        "limitations": [] if permitted else ["The modeled executor denied socket binding after checks ran; build was not reached."],
        "executions": [
            *preceding,
            {
                "command": unit["commands"][-1],
                "working_directory": unit["working_directories"][0],
                "executor": entry["node_id"],
                "result": status,
                "exit_code": run.returncode,
                "elapsed": f"{elapsed}s",
                "evidence": "2 checks passed; build completed" if permitted else f"2 checks passed; socket.bind: {DENIAL}; build not reached",
                "artifact_paths": [str(log)],
            },
        ],
    }
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    for phase, snapshot in (("before", before), ("after", after)):
        if lifecycle.get("external_metadata_transitions"):
            snapshot["observed_source_state"] = lifecycle["current_source_state"]
        (directory / f"workspace-{phase}.json").write_text(json.dumps(snapshot))
    lifecycle_path = directory / "lifecycle.json"
    lifecycle_path.write_text(json.dumps(lifecycle))
    assert (
        main(
            [
                "compile-node",
                "--input",
                str(lifecycle_path),
                "--dispatches",
                str(args.dispatches),
                "--journal",
                str(args.journal),
                "--node-id",
                entry["node_id"],
                "--before-capture",
                str(args.current_capture),
                "--after-capture",
                str(args.current_capture),
                "--workspace-before",
                str(directory / "workspace-before.json"),
                "--workspace-after",
                str(directory / "workspace-after.json"),
                "--output",
                str(directory / "compiled.json"),
            ]
        )
        == 0
    )
    return {
        "log_path": str(log),
        "diagnostic": DENIAL,
        "before_capture": str(args.current_capture),
        "after_capture": str(args.current_capture),
        "workspace_before": str(directory / "workspace-before.json"),
        "workspace_after": str(directory / "workspace-after.json"),
    }


def _fixture(tmp_path: Path, *, extra_command: bool = False, non_utf8_output: bool = False) -> tuple[dict[str, Any], Namespace, dict[str, Any], dict[str, Any]]:
    script = tmp_path / "aggregate.py"
    script.write_text(
        ('import sys\nsys.stdout.buffer.write(b"\\xff\\n")\n' if non_utf8_output else "")
        + 'import os\nassert 1 + 1 == 2\nassert len([1, 2]) == 2\nprint("2 checks passed", flush=True)\n'
        'if os.environ["FIXTURE_SOCKET_ACCESS"] != "permitted":\n'
        '    raise PermissionError(1, "Operation not permitted")\nprint("build completed")\n'
    )
    planning = _sparse_plan_document()
    original = planning["validation_requirements"][0]
    planning["validation_requirements"].append(
        {
            **original,
            "requirement_id": "aggregate",
            "commands": [*(["true"] if extra_command else []), shlex.join([sys.executable, str(script)])],
            "canonical_recipe": "just ci",
            "isolation_root": str(tmp_path),
            "working_directories": [str(tmp_path)] * (2 if extra_command else 1),
            "allowed_artifacts": [{"path": str(tmp_path / "ci.log"), "kind": "log", "repository_status": "outside-repository"}],
        }
    )
    planning["pre_review_validation_requirement_ids"] = [original["requirement_id"], "aggregate"]
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "initial"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    args = Namespace(journal=tmp_path / "journal.jsonl", dispatches=tmp_path / "dispatches.json", current_capture=tmp_path / "capture.json")
    args.dispatches.write_text(json.dumps(dispatches))
    args.current_capture.write_text(
        json.dumps({"scope_fingerprint": "scope", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"})
    )
    successful = _ready(lifecycle, args)["ready_dispatches"][0]
    _compile_repair_fixture_entry(successful, lifecycle, args.journal)
    failed = _ready(lifecycle, args)["ready_dispatches"][0]
    failure = _compile_aggregate(lifecycle, args, failed, tmp_path / "first-execution", permitted=False)
    request = {
        **lifecycle,
        "artifact_store": str(tmp_path / "recovery"),
        "node_id": failed["node_id"],
        "failure_kind": "executor-permission",
        "checks_started": True,
        "reason": "Socket permission denial after passing checks belongs to the executor; the build stage was never reached.",
        "remedy": "Apply the permitted executor's socket capability.",
        "environment": "permitted native executor",
        "permission_change": "restricted sandbox to permitted executor",
        "executor_permissions": "require_escalated",
        "failure_evidence": failure,
    }
    return request, args, failed, successful


def _continuation(result: dict[str, Any]) -> tuple[dict[str, Any], Namespace]:
    return result["lifecycle_input"], Namespace(
        journal=Path(result["journal_path"]), dispatches=Path(result["dispatches_path"]), current_capture=Path(result["current_capture_path"])
    )


def _finalize(lifecycle: dict[str, Any], args: Namespace, directory: Path) -> dict[str, Any]:
    directory.mkdir(exist_ok=True)
    input_path, output_path = directory / "final-input.json", directory / "final.json"
    input_path.write_text(json.dumps(lifecycle))
    code = main(
        [
            "finalize-proof",
            "--input",
            str(input_path),
            "--dispatches",
            str(args.dispatches),
            "--journal",
            str(args.journal),
            "--current-capture",
            str(args.current_capture),
            "--output",
            str(output_path),
        ]
    )
    result = json.loads(output_path.read_bytes())
    assert code == (0 if result["status"] == "complete" else 2)
    return result


@pytest.mark.parametrize("non_utf8_output", [False, True])
def test_executed_permission_recovery_releases_early_gate_only_after_success(tmp_path: Path, non_utf8_output: bool) -> None:
    request, args, failed, successful = _fixture(tmp_path, non_utf8_output=non_utf8_output)
    assert not _ready(request, args)["ready_node_ids"]
    original = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert (b"\xff" in original[Path(request["failure_evidence"]["log_path"])]) == non_utf8_output
    recovered = recover_validation_execution(request, args)
    lifecycle, retry_args = _continuation(recovered)
    assert lifecycle["source_state"] == request["source_state"]
    assert recovered["retained_node_ids"] == [successful["node_id"]]
    ready = _ready(lifecycle, retry_args)
    assert ready["ready_node_ids"] == [failed["node_id"]]
    retry = ready["ready_dispatches"][0]
    assert retry["dispatch"]["evidence_id"] != failed["dispatch"]["evidence_id"]
    assert retry["dispatch"]["artifact_id"] != failed["dispatch"]["artifact_id"]
    assert retry["dispatch"]["executor_requirements"] == {"sandbox_permissions": "require_escalated"}
    before_proof = _finalize(lifecycle, retry_args, tmp_path / "partial-proof")
    assert before_proof["graph_proof_status"] != "complete"
    assert before_proof["repository_validation_status"] != "passed"
    assert before_proof["validation_recoveries"][0]["previous_evidence_id"] == failed["dispatch"]["evidence_id"]
    assert all(path.read_bytes() == content for path, content in original.items())
    recovery = lifecycle["plan"]["validation_recoveries"][0]
    saved_log = next(Path(item["path"]) for item in recovery["preserved_files"] if Path(item["path"]).name == "failure.log")
    assert saved_log.read_bytes() == original[Path(request["failure_evidence"]["log_path"])]
    _compile_aggregate(lifecycle, retry_args, retry, tmp_path / "retry-execution", permitted=True)
    assert _ready(lifecycle, retry_args)["ready_node_ids"]
    assert all(entry["result_contract"] != "compact-validation" for entry in _ready(lifecycle, retry_args)["ready_dispatches"])
    for _ in range(len(lifecycle["plan"]["actual_worker_nodes"])):
        ready = _ready(lifecycle, retry_args)
        if ready["complete"]:
            break
        for entry in ready["ready_dispatches"]:
            _compile_repair_fixture_entry(entry, lifecycle, retry_args.journal)
    final = _finalize(lifecycle, retry_args, tmp_path)
    assert final["graph_proof_status"] == "complete"
    assert final["repository_validation_status"] == "passed"
    assert saved_log.read_bytes() == original[Path(request["failure_evidence"]["log_path"])]
    for entry in (failed, successful):
        for key in ("artifact_path", "metadata_path"):
            path = Path(entry[key])
            assert path.read_bytes() == original[path]
    # Find by node ID, independent of coalescing order.
    prior_unit = next(unit for unit in _graph_plan(request["plan"]).coalesced_validation_units if unit.node_id == failed["node_id"])
    reconciliation = _validation_reconciliation(
        _graph_plan(lifecycle["plan"]),
        [
            {
                "status": "no-findings",
                "evidence_id": "audit:prior",
                "validation_requirements": [
                    {
                        "requirement_id": "aggregate",
                        "planned_validation_digest": _planned_validation_digest(prior_unit),
                        "owner": "review-validator",
                        "reason": "Original aggregate obligation",
                        "expected_evidence": "Aggregate passes",
                    }
                ],
            }
        ],
    )
    assert not reconciliation["blockers"]


@pytest.mark.parametrize(
    ("defect", "diagnostic"),
    [
        ("ordinary-failure", "permission-denial diagnostic"),
        ("log-tamper", "log differs"),
        ("snapshot-tamper", "artifact identities"),
        ("source-change", "unchanged source"),
        ("no-remedy", "explicit permission remedy"),
        ("successful-node", "one failed command"),
        ("unchanged-executor", "changed executor identity"),
        ("unrecorded-diagnostic", "log differs"),
    ],
)
def test_execution_recovery_rejects_unproven_or_ineligible_attempt_without_writes(tmp_path: Path, defect: str, diagnostic: str) -> None:
    request, args, _failed, successful = _fixture(tmp_path)
    if defect == "ordinary-failure":
        request["failure_evidence"]["diagnostic"] = "AssertionError: wrong value"
    elif defect == "log-tamper":
        Path(request["failure_evidence"]["log_path"]).write_text(DENIAL)
    elif defect == "snapshot-tamper":
        path = Path(request["failure_evidence"]["workspace_after"])
        snapshot = json.loads(path.read_bytes())
        snapshot["records"][0]["digest"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(snapshot))
    elif defect == "source-change":
        capture = json.loads(args.current_capture.read_bytes())
        capture["captured_worktree_fingerprint"] = "changed"
        args.current_capture.write_text(json.dumps(capture))
    elif defect == "no-remedy":
        request["permission_change"] = "none"
    elif defect == "unchanged-executor":
        request.update(environment="current host", executor_permissions="use_default")
    elif defect == "unrecorded-diagnostic":
        request["failure_evidence"]["diagnostic"] = "EACCES"
    else:
        request["node_id"] = successful["node_id"]
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match=diagnostic):
        recover_validation_execution(request, args)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in before.items())


def test_failed_retry_stays_partial_and_cannot_consume_another_recovery(tmp_path: Path) -> None:
    request, args, _failed, _successful = _fixture(tmp_path)
    result = recover_validation_execution(request, args)
    lifecycle, retry_args = _continuation(result)
    retry = _ready(lifecycle, retry_args)["ready_dispatches"][0]
    failure = _compile_aggregate(lifecycle, retry_args, retry, tmp_path / "retry-execution", permitted=False)
    assert not _ready(lifecycle, retry_args)["ready_node_ids"]
    assert _finalize(lifecycle, retry_args, tmp_path)["repository_validation_status"] == "failed"
    with pytest.raises(ValueError, match="budget exhausted"):
        recover_validation_execution({**request, **lifecycle, "failure_evidence": failure}, retry_args)
    launch = {key: value for key, value in request.items() if key not in {"executor_permissions", "failure_evidence"}}
    launch["checks_started"] = False
    with pytest.raises(ValueError, match="not a planning or check failure"):
        recover_validation_launch(launch, args)


def test_recovered_history_tampering_blocks_scheduling(tmp_path: Path) -> None:
    request, args, _failed, _successful = _fixture(tmp_path)
    lifecycle, retry_args = _continuation(recover_validation_execution(request, args))
    saved = next(item for item in lifecycle["plan"]["validation_recoveries"][0]["preserved_files"] if item["path"].endswith("failure.log"))
    path = Path(saved["path"])
    path.chmod(0o644)
    path.write_text("altered")
    with pytest.raises(ValueError, match="preserved validation recovery evidence changed"):
        _ready(lifecycle, retry_args)


def test_recovery_rejects_unit_with_a_separately_passed_command(tmp_path: Path) -> None:
    request, args, _failed, _successful = _fixture(tmp_path, extra_command=True)
    with pytest.raises(ValueError, match="never replay separately passed commands"):
        recover_validation_execution(request, args)
    assert not Path(request["artifact_store"]).exists()


def test_execution_recovery_cli_is_idempotent(tmp_path: Path) -> None:
    request, args, _failed, _successful = _fixture(tmp_path)
    input_path, output = tmp_path / "request.json", tmp_path / "result.json"
    input_path.write_text(json.dumps(request))
    argv = [
        "recover-validation-execution",
        "--input",
        str(input_path),
        "--dispatches",
        str(args.dispatches),
        "--journal",
        str(args.journal),
        "--current-capture",
        str(args.current_capture),
        "--output",
        str(output),
    ]
    assert main(argv) == 0
    saved = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert main(argv) == 0
    assert all(path.read_bytes() == content for path, content in saved.items())


def test_launch_permission_remedy_binds_the_replacement_executor(tmp_path: Path) -> None:
    request, args, _failed = _recovery_fixture(tmp_path)
    request.update(environment="current host", permission_change="Permit native socket access")
    with pytest.raises(ValueError, match="requires explicit executor_permissions"):
        recover_validation_launch(request, args)
    assert not Path(request["artifact_store"]).exists()
    request["executor_permissions"] = "require_escalated"
    recovered = recover_validation_launch(request, args)
    lifecycle, retry_args = _continuation(recovered)
    ready = _ready(lifecycle, retry_args)
    retry = next(entry for entry in ready["ready_dispatches"] if entry["node_id"] == request["node_id"])
    assert retry["dispatch"]["executor_requirements"] == {"sandbox_permissions": "require_escalated"}
    assert not recovered["validation_reconciliation"]["blockers"]


def test_permissions_are_explicit_and_preflight_cannot_drop_them(tmp_path: Path) -> None:
    request, args, _failed, _successful = _fixture(tmp_path)
    lifecycle, _retry_args = _continuation(recover_validation_execution(request, args))
    preflight = {
        "plan": lifecycle["plan"],
        "repository_root": str(SKILL_ROOT.parents[2]),
        "cache_paths": [],
        "command_policy": [
            {"command": command, "disposition": "allowed", "reason": "fixture commands"}
            for unit in lifecycle["plan"]["coalesced_validation_units"]
            for command in unit["commands"]
        ],
        "execution_prerequisites": [
            {"node_id": unit["node_id"], "executables": [sys.executable], "native_available": True, "reason": "native fixture"}
            for unit in lifecycle["plan"]["coalesced_validation_units"]
        ],
    }
    report = preflight_validation(preflight)
    unit = next(item for item in report["units"] if item["node_id"] == request["node_id"])
    assert any("permission requirement not selected" in blocker for blocker in unit["blockers"])
    prerequisite = next(item for item in preflight["execution_prerequisites"] if item["node_id"] == request["node_id"])
    prerequisite["sandbox_permissions"] = "require_escalated"
    unit = next(item for item in preflight_validation(preflight)["units"] if item["node_id"] == request["node_id"])
    assert not unit["blockers"]


@pytest.mark.parametrize("features", [["executor-permissions=unknown"], ["executor-permissions=use_default", "executor-permissions=require_escalated"]])
def test_invalid_permission_declarations_are_rejected(features: list[str]) -> None:
    with pytest.raises(ValueError, match="executor-permissions"):
        executor_permissions(features)
