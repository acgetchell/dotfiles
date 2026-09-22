"""Regression coverage for publication and recovery without Git fixture mutations."""

import json
import os
import tempfile
from argparse import Namespace
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import IO, Any

import pytest
from review_graph_plan import ValidationArtifact, _validation_nodes, plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    _graph_plan,
    _planned_validation_digest,
    _validation_reconciliation,
    append_journal_event,
    compile_review,
    compile_validation,
    main,
    materialize_dispatches,
    next_ready_nodes,
    persist_worker_payload_bytes,
    preflight_validation,
    read_execution_journal,
    reconcile_validation_requirements,
    recover_validation_launch,
    review_worker_payload_write,
)
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _compact_audit_payload,
    _compile_repair_fixture_entry,
    _continuation_fixture,
    _json_plan,
    _late_validation_plan,
    _late_validation_requirement,
    _sparse_plan,
    _sparse_plan_document,
    _worker_input_fixture,
)


def _partitioned_payload(entry: dict[str, Any]) -> dict[str, Any]:
    payload = _compact_audit_payload(entry)
    payload["nearby_contract_owners"] = ["AGENTS.md", "pyproject.toml"]
    payload["coverage_units"] = [
        {
            "unit_id": "library",
            "owned_paths": entry["dispatch"]["owned_paths"],
            "dependency_paths": ["AGENTS.md", "pyproject.toml"],
            "dependency_uncertainty": "",
            "finding_indices": [],
        }
    ]
    return payload


@pytest.mark.parametrize("defect", ["dependency", "duplicate-path", "missing-path", "duplicate-unit", "missing-finding", "duplicate-finding", "extra-finding"])
def test_partition_rejection_matches_publication_and_compilation_without_writes(tmp_path: Path, defect: str) -> None:
    document, dispatches = _worker_input_fixture(tmp_path)
    entry = next(item for item in dispatches["dispatches"] if item["dispatch"].get("mode") == "audit")
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    payload = _partitioned_payload(entry)
    unit = payload["coverage_units"][0]
    if defect == "dependency":
        unit["dependency_paths"] = ["pyproject.toml"]
    elif defect == "duplicate-path":
        unit["owned_paths"] = [*unit["owned_paths"], unit["owned_paths"][0]]
    elif defect == "missing-path":
        unit["owned_paths"] = ["missing.py"]
    elif defect == "duplicate-unit":
        payload["coverage_units"].append(deepcopy(unit))
    else:
        payload["status"] = "completed"
        payload["findings"] = [
            {
                "severity": "P2",
                "location": "state.rs:1",
                "summary": "State is lost",
                "evidence": "A failed transition drops state",
                "remediation": "Retain state",
            }
        ]
        unit["finding_indices"] = {"missing-finding": [], "duplicate-finding": [1, 1], "extra-finding": [1, 2]}[defect]
    dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    before = set(tmp_path.rglob("*"))
    with pytest.raises(ValueError, match=r"coverage|schema") as publication:
        review_worker_payload_write(contract, json.dumps(payload).encode())
    with pytest.raises(ValueError, match=r"coverage|schema") as compilation:
        compile_review({"dispatch": dispatch, "payload": payload})
    assert str(publication.value) == str(compilation.value)
    if defect == "dependency":
        assert "missing: AGENTS.md" in str(publication.value)
    assert set(tmp_path.rglob("*")) == before
    assert not Path(entry["worker_payload_path"]).exists()


def test_rejected_partition_can_be_corrected_published_and_compiled(tmp_path: Path) -> None:
    document, dispatches = _worker_input_fixture(tmp_path)
    entry = next(item for item in dispatches["dispatches"] if item["dispatch"].get("mode") == "audit")
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    payload = _partitioned_payload(entry)
    payload["coverage_units"][0]["dependency_paths"] = []
    with pytest.raises(ValueError, match=r"AGENTS\.md, pyproject\.toml"):
        review_worker_payload_write(contract, json.dumps(payload).encode())
    payload["coverage_units"][0]["dependency_paths"] = payload["nearby_contract_owners"]
    content = json.dumps(payload).encode()
    approval = review_worker_payload_write(contract, content)
    persist_worker_payload_bytes(contract, content, approval_identity=approval["approval_identity"])
    dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    _native, metadata = compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["evidence"]["status"] == "no-findings"
    assert Path(entry["worker_payload_path"]).read_bytes() == content
    assert "partition every owned path and every finding exactly once" in entry["worker_prompt"]


def _block_validator(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path) -> None:
    dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
    payload = {"executions": [], "status": "blocked", "limitations": ["uv cache permission denied before checks started"]}
    content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    append_journal_event(
        journal,
        lifecycle,
        JournalEventRequest(
            entry["node_id"], "blocked", source={key: entry[key] for key in ("artifact_path", "metadata_path")}, reason=payload["limitations"][0]
        ),
    )


def _recovery_fixture(tmp_path: Path, *, late: bool = False, extra_validator: bool = False) -> tuple[dict[str, Any], Namespace, dict[str, Any]]:
    lifecycle, dispatches, paths = _continuation_fixture(tmp_path)
    if extra_validator:
        planning = _sparse_plan_document()
        extra = {**planning["validation_requirements"][0], "requirement_id": "second-validation", "baseline": False, "environment": "second executor"}
        planning["validation_requirements"].append(extra)
        lifecycle["plan"] = _json_plan(plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)))
        dispatches = materialize_dispatches(
            {
                **lifecycle,
                "artifact_store": str(tmp_path / "two-validators"),
                "authorization": "review-only",
                "repository_root": str(SKILL_ROOT.parents[2]),
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )
        paths["dispatches"].write_text(json.dumps(dispatches))
    validation = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation")
    for entry in dispatches["dispatches"]:
        if entry["dispatch"].get("mode") == "audit":
            payload = _compact_audit_payload(entry)
            planned = entry["dispatch"]["command_policy"]["planned_validation_units"][0]
            payload["validation_requirements"] = [
                {
                    "requirement_id": planned["requirement_ids"][0],
                    "planned_validation_digest": planned["planned_validation_digest"],
                    "owner": "review-validator",
                    "reason": "Exercise the dispatch contract",
                    "expected_evidence": "Exact baseline passes",
                }
            ]
            if late:
                payload["validation_requirements"].append(_late_validation_requirement())
            dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
            content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
            Path(entry["artifact_path"]).write_bytes(content)
            Path(entry["metadata_path"]).write_text(json.dumps(metadata))
            append_journal_event(
                paths["journal"],
                lifecycle,
                JournalEventRequest(entry["node_id"], "accepted", source={key: entry[key] for key in ("artifact_path", "metadata_path")}),
            )
    _block_validator(validation, lifecycle, paths["journal"])
    request = {
        **lifecycle,
        "artifact_store": str(tmp_path / "recovery"),
        "node_id": validation["node_id"],
        "failure_kind": "cache-access",
        "checks_started": False,
        "reason": "uv failed to open its cache before pytest launched",
        "remedy": "Use an accessible repository-local uv cache",
        "environment": "UV_CACHE_DIR=.uv-cache",
        "permission_change": "none",
    }
    args = Namespace(journal=paths["journal"], dispatches=paths["dispatches"], current_capture=paths["current-capture"])
    return request, args, validation


@pytest.mark.parametrize("other_has_evidence", [False, True])
def test_launch_recovery_retains_other_blocked_nodes_and_recovers_each_once(tmp_path: Path, other_has_evidence: bool) -> None:
    request, args, first = _recovery_fixture(tmp_path, extra_validator=True)
    lifecycle = {key: request[key] for key in ("plan", "source_state")}
    original_dispatches = json.loads(args.dispatches.read_bytes())
    second = next(entry for entry in original_dispatches["dispatches"] if entry["result_contract"] == "compact-validation" and entry != first)
    reason = "uv cache permission denied before checks started" if other_has_evidence else "executor unavailable before launch"
    if other_has_evidence:
        _block_validator(second, lifecycle, args.journal)
    else:
        append_journal_event(args.journal, lifecycle, JournalEventRequest(second["node_id"], "blocked", reason=reason))
    original_files = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    old_events, _state, _head = read_execution_journal(args.journal, plan=_graph_plan(request["plan"]), source_state=tuple(request["source_state"]))
    previous_blocked = next(event for event in old_events if event["node_id"] == second["node_id"])

    recovered = recover_validation_launch(request, args)
    lifecycle = recovered["lifecycle_input"]
    journal = Path(recovered["journal_path"])
    dispatches = json.loads(Path(recovered["dispatches_path"]).read_bytes())
    events, state, _head = read_execution_journal(journal, plan=_graph_plan(lifecycle["plan"]), source_state=tuple(request["source_state"]))
    retained_blocked = next(event for event in events if event["node_id"] == second["node_id"])
    assert state[second["node_id"]] == "blocked"
    assert retained_blocked["evidence"] == previous_blocked["evidence"]
    assert retained_blocked["reason"] == reason
    assert next(entry for entry in dispatches["dispatches"] if entry["node_id"] == second["node_id"]) == second
    ready = next_ready_nodes({**lifecycle, "current_source_state": request["source_state"]}, journal_events=events, dispatch_set=dispatches)
    assert ready["ready_node_ids"] == [first["node_id"]]
    assert not ready["complete"]
    first_retry = next(entry for entry in dispatches["dispatches"] if entry["node_id"] == first["node_id"])
    _compile_repair_fixture_entry(first_retry, lifecycle, journal)
    next_args = Namespace(journal=journal, dispatches=Path(recovered["dispatches_path"]), current_capture=Path(recovered["current_capture_path"]))
    next_request = {**request, **lifecycle, "node_id": second["node_id"]}
    if not other_has_evidence:
        with pytest.raises(ValueError, match="compiled, journal-bound"):
            recover_validation_launch(next_request, next_args)
        assert all(path.read_bytes() == content for path, content in original_files.items())
        return

    recovered_again = recover_validation_launch(next_request, next_args)
    lifecycle = recovered_again["lifecycle_input"]
    journal = Path(recovered_again["journal_path"])
    dispatches = json.loads(Path(recovered_again["dispatches_path"]).read_bytes())
    assert next(entry for entry in dispatches["dispatches"] if entry["node_id"] == first["node_id"]) == first_retry
    events, state, _head = read_execution_journal(journal, plan=_graph_plan(lifecycle["plan"]), source_state=tuple(request["source_state"]))
    assert all(value == "accepted" for value in state.values())
    ready = next_ready_nodes({**lifecycle, "current_source_state": request["source_state"]}, journal_events=events, dispatch_set=dispatches)
    assert ready["ready_node_ids"] == [second["node_id"]]
    for entry in dispatches["dispatches"]:
        if entry["node_id"] not in recovered_again["retained_node_ids"]:
            _compile_repair_fixture_entry(entry, lifecycle, journal)
    output = tmp_path / "two-recoveries-final.json"
    assert (
        main(
            [
                "finalize-proof",
                "--input",
                recovered_again["lifecycle_input_path"],
                "--journal",
                str(journal),
                "--dispatches",
                recovered_again["dispatches_path"],
                "--current-capture",
                recovered_again["current_capture_path"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    final = json.loads(output.read_bytes())
    assert final["graph_proof_status"] == "complete"
    assert len(final["validation_recoveries"]) == 2
    assert all(path.read_bytes() == content for path, content in original_files.items())


def _interrupt_recovery_write(monkeypatch: pytest.MonkeyPatch, stage: str, name: str) -> list[Path]:
    """Fail below either direct or atomic publication after writing a prefix."""
    original_open, original_fdopen, original_mkstemp = Path.open, os.fdopen, tempfile.mkstemp
    descriptors: dict[int, Path] = {}
    interrupted: list[Path] = []

    def wrap(stream: IO[Any], path: Path) -> IO[Any]:
        target = path.name == name or path.name.startswith(f".{name}.")
        parent = path.parent.name
        selected = parent.startswith("launch-history-") if stage == "history" else parent.startswith("validation-recovered-")
        if target and (selected or stage == "result"):
            write = stream.write

            def fail(content: bytes) -> int:
                write(content[:17])
                stream.flush()
                interrupted.append(path)
                msg = "injected interrupted recovery write"
                raise OSError(msg)

            monkeypatch.setattr(stream, "write", fail)
        return stream

    def open_path(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        stream = original_open(path, mode, *args, **kwargs)
        return wrap(stream, path) if mode == "xb" else stream

    def mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        descriptor, path = original_mkstemp(*args, **kwargs)
        assert isinstance(descriptor, int)
        assert isinstance(path, str)
        descriptors[descriptor] = Path(path)
        return descriptor, path

    def fdopen(descriptor: int, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        stream = original_fdopen(descriptor, mode, *args, **kwargs)
        path = descriptors.pop(descriptor, None)
        return wrap(stream, path) if mode == "wb" and path is not None else stream

    monkeypatch.setattr(Path, "open", open_path)
    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(os, "fdopen", fdopen)
    return interrupted


@pytest.mark.parametrize(
    ("stage", "name"),
    [
        *(("history", name) for name in ("lifecycle.json", "execution.jsonl", "dispatches.json")),
        *(("continuation", name) for name in ("dispatches.json", "lifecycle.json", "execution.jsonl", "capture.json", "continuation.json")),
        ("result", "recovery-result.json"),
    ],
)
def test_interrupted_recovery_publication_can_retry_identical_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stage: str, name: str
) -> None:
    request, args, _validation = _recovery_fixture(tmp_path)
    input_path, output = tmp_path / "recovery-input.json", tmp_path / "recovery-result.json"
    input_path.write_text(json.dumps(request))
    original = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    argv = [
        "recover-validation-launch",
        "--input",
        str(input_path),
        "--journal",
        str(args.journal),
        "--dispatches",
        str(args.dispatches),
        "--current-capture",
        str(args.current_capture),
        "--output",
        str(output),
    ]
    with monkeypatch.context() as patch:
        interrupted = _interrupt_recovery_write(patch, stage, name)
        assert main(argv) == 2
    assert len(interrupted) == 1
    assert "injected interrupted recovery write" in capsys.readouterr().err
    assert not interrupted[0].exists()
    assert not output.exists()
    assert main(argv) == 0
    result = json.loads(output.read_bytes())
    assert result["status"] == "recovered"
    assert Path(result["continuation_path"]).is_file()
    events, state, _head = read_execution_journal(
        Path(result["journal_path"]), plan=_graph_plan(result["lifecycle_input"]["plan"]), source_state=tuple(request["source_state"])
    )
    assert all(value == "accepted" for value in state.values())
    ready = next_ready_nodes(
        {**result["lifecycle_input"], "current_source_state": request["source_state"]},
        journal_events=events,
        dispatch_set=json.loads(Path(result["dispatches_path"]).read_bytes()),
    )
    assert request["node_id"] in ready["ready_node_ids"]
    assert all(path.read_bytes() == content for path, content in original.items())
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("status", ["in-flight", "awaiting-replan"])
def test_recovery_still_rejects_active_or_source_mutated_nodes(tmp_path: Path, status: str) -> None:
    request, args, first = _recovery_fixture(tmp_path, extra_validator=True)
    lifecycle = {key: request[key] for key in ("plan", "source_state")}
    dispatches = json.loads(args.dispatches.read_bytes())
    second = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation" and entry != first)
    append_journal_event(args.journal, lifecycle, JournalEventRequest(second["node_id"], "in-flight"))
    if status == "awaiting-replan":
        append_journal_event(args.journal, lifecycle, JournalEventRequest(second["node_id"], status, reason="source changed during validation"))
    with pytest.raises(ValueError, match="quiescent execution"):
        recover_validation_launch(request, args)
    assert not Path(request["artifact_store"]).exists()


def test_launch_recovery_preserves_audits_failure_and_schedules_one_new_attempt(tmp_path: Path) -> None:
    request, args, old_validation = _recovery_fixture(tmp_path)
    original = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = recover_validation_launch(request, args)
    lifecycle = result["lifecycle_input"]
    plan = _graph_plan(lifecycle["plan"])
    events, state, _head = read_execution_journal(Path(result["journal_path"]), plan=plan, source_state=tuple(request["source_state"]))
    assert result["retained_node_ids"]
    assert result["validation_reconciliation"]["blockers"] == []
    assert set(state) == set(result["retained_node_ids"])
    dispatches = json.loads(Path(result["dispatches_path"]).read_bytes())
    ready = next_ready_nodes({**lifecycle, "current_source_state": request["source_state"]}, journal_events=events, dispatch_set=dispatches)
    assert request["node_id"] in ready["ready_node_ids"]
    validation = next(entry for entry in dispatches["dispatches"] if entry["node_id"] == request["node_id"])
    assert validation["artifact_path"] != old_validation["artifact_path"]
    assert validation["dispatch"]["validation_unit"]["environment"] == "UV_CACHE_DIR=.uv-cache"
    assert all(path.read_bytes() == content for path, content in original.items())
    assert Path(result["continuation_path"]).is_file()
    _block_validator(validation, lifecycle, Path(result["journal_path"]))
    retry = {**request, **lifecycle, "environment": "UV_CACHE_DIR=another-cache"}
    retry_args = Namespace(journal=Path(result["journal_path"]), dispatches=Path(result["dispatches_path"]), current_capture=args.current_capture)
    with pytest.raises(ValueError, match="budget exhausted"):
        recover_validation_launch(retry, retry_args)


@pytest.mark.parametrize("defect", ["no-remedy", "already-started", "unchanged-environment", "changed-source"])
def test_launch_recovery_rejects_unsafe_requests_before_writing(tmp_path: Path, defect: str) -> None:
    request, args, validation = _recovery_fixture(tmp_path)
    if defect == "no-remedy":
        request["remedy"] = ""
    elif defect == "already-started":
        request["checks_started"] = True
    elif defect == "unchanged-environment":
        request["environment"] = validation["dispatch"]["validation_unit"]["environment"]
    else:
        request["source_state"][0] = "changed"
    with pytest.raises(ValueError, match=r"schema|requires"):
        recover_validation_launch(request, args)
    assert not Path(request["artifact_store"]).exists()


def test_recovery_rejects_modified_historical_failure(tmp_path: Path) -> None:
    request, args, validation = _recovery_fixture(tmp_path)
    result = recover_validation_launch(request, args)
    Path(validation["artifact_path"]).write_bytes(b"tampered")
    lifecycle = result["lifecycle_input"]
    dispatches = json.loads(Path(result["dispatches_path"]).read_bytes())
    with pytest.raises(ValueError, match="preserved validation recovery evidence changed"):
        next_ready_nodes({**lifecycle, "current_source_state": request["source_state"]}, journal_events=(), dispatch_set=dispatches)


def test_blocked_commandless_validation_and_absent_outputs_compile(tmp_path: Path) -> None:
    document, _dispatches = _worker_input_fixture(tmp_path / "initial")
    plan = _sparse_plan()
    original = plan.coalesced_validation_units[0]
    artifact = ValidationArtifact(
        path=str(tmp_path / "never-produced.json"), kind="report", repository_status="outside-repository", status_source="isolated-output-directory"
    )
    unit = replace(original, commands=(), working_directories=(), canonical_recipe=None, allowed_artifacts=(artifact,))
    owner = next(node for node in plan.actual_worker_nodes if node.node_id == unit.node_id)
    assert _validation_nodes((unit,), skill_path=owner.skill_path, skill_digest=owner.skill_digest, reference_digests=owner.reference_digests)[0].coverage == ()
    nodes = tuple(replace(node, coverage=()) if node.node_id == unit.node_id else node for node in plan.actual_worker_nodes)
    plan = replace(plan, coalesced_validation_units=(unit,), actual_worker_nodes=nodes)
    dispatches = materialize_dispatches({**document, "artifact_store": str(tmp_path / "blocked"), "plan": _json_plan(plan)})
    entry = next(item for item in dispatches["dispatches"] if item["node_id"] == unit.node_id)
    assert entry["dispatch"]["owned_paths"] == []
    snapshot = [
        {
            "path": artifact.path,
            "status": "outside-repository",
            "exists": False,
            "digest": "sha256:" + sha256(b"absent").hexdigest(),
            "snapshot_mode": "absent-v1",
        }
    ]
    dispatch = {
        **entry["dispatch"],
        "before_state": document["source_state"],
        "after_state": document["source_state"],
        "workspace_before": snapshot,
        "workspace_after": snapshot,
    }
    payload = {"status": "blocked", "limitations": ["Hosted matrix cannot run here"], "executions": []}
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    approval = review_worker_payload_write(contract, json.dumps(payload).encode())
    assert approval["approval_identity"]
    _content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
    assert metadata["normalized_record"]["artifacts"][0]["artifact_digest_mode"] == "absent-v1"
    assert not Path(artifact.path).exists()


def test_next_ready_generations_include_output_identity(tmp_path: Path) -> None:
    _lifecycle, _dispatches, paths = _continuation_fixture(tmp_path)
    argv = ["next-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output-dir", str(tmp_path / "ready")]
    assert main(argv) == 0
    assert main([*argv, "--compact"]) == 0
    generated = sorted((tmp_path / "ready").glob("next-ready.000000.*.json"))
    assert len(generated) == 2
    before = {path: path.read_bytes() for path in generated}
    assert main(argv) == 0
    assert all(path.read_bytes() == content for path, content in before.items())


def test_preflight_reports_policy_effect_path_and_cache_blockers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], expected_workspace_effects=("writes temporary files here",))
    plan = replace(plan, coalesced_validation_units=(unit,))
    request = {
        "plan": _json_plan(plan),
        "repository_root": str(tmp_path),
        "command_policy": [{"command": "true", "disposition": "blocked", "reason": "nested fixtures mutate Git"}],
        "cache_paths": [str(tmp_path)],
    }
    monkeypatch.setattr("review_graph_runtime._git_path_status", lambda *_args: "untracked")

    def denied(_path: Path) -> None:
        msg = "cache inaccessible"
        raise PermissionError(msg)

    monkeypatch.setattr("review_graph_runtime.os.scandir", denied)
    report = preflight_validation(request)
    assert report["status"] == "blocked"
    blockers = report["units"][0]["blockers"]
    assert any("nested fixtures mutate Git" in item for item in blockers)
    assert any("not prose" in item for item in blockers)
    assert any("cache is inaccessible" in item for item in blockers)


def test_preflight_missing_command_policy_is_not_permission_to_execute(tmp_path: Path) -> None:
    report = preflight_validation({"plan": _json_plan(_sparse_plan()), "repository_root": str(tmp_path), "command_policy": [], "cache_paths": []})
    assert report["status"] == "blocked"
    assert "not reviewed" in report["units"][0]["blockers"][0]


def test_successful_recovery_allows_late_expansion_and_complete_proof(tmp_path: Path) -> None:
    request, args, _validation = _recovery_fixture(tmp_path, late=True)
    recovered = recover_validation_launch(request, args)
    lifecycle = recovered["lifecycle_input"]
    entries = json.loads(Path(recovered["dispatches_path"]).read_bytes())["dispatches"]
    entry = next(item for item in entries if item["node_id"] == request["node_id"])
    _compile_repair_fixture_entry(entry, lifecycle, Path(recovered["journal_path"]))
    expansion = {**lifecycle, "artifact_store": str(tmp_path / "expanded"), "validation_requirements": [_late_validation_plan()]}
    expansion_args = Namespace(journal=Path(recovered["journal_path"]), dispatches=Path(recovered["dispatches_path"]), current_capture=args.current_capture)
    expanded = reconcile_validation_requirements(expansion, expansion_args)
    assert request["node_id"] in expanded["retained_node_ids"]
    assert len(expanded["lifecycle_input"]["plan"]["validation_recoveries"]) == 1
    entries = json.loads(Path(expanded["dispatches_path"]).read_bytes())["dispatches"]
    for entry in entries:
        if entry["node_id"] not in expanded["retained_node_ids"]:
            _compile_repair_fixture_entry(entry, expanded["lifecycle_input"], Path(expanded["journal_path"]))
    output = tmp_path / "final.json"
    assert (
        main(
            [
                "finalize-proof",
                "--input",
                expanded["lifecycle_input_path"],
                "--journal",
                expanded["journal_path"],
                "--dispatches",
                expanded["dispatches_path"],
                "--current-capture",
                str(args.current_capture),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    final = json.loads(output.read_bytes())
    assert final["graph_proof_status"] == "complete"
    assert final["repository_validation_status"] == "passed"
    assert len(final["validation_recoveries"]) == 1


def test_actual_check_failure_cannot_use_launch_recovery(tmp_path: Path) -> None:
    request, args, validation = _recovery_fixture(tmp_path)
    lifecycle = {key: request[key] for key in ("plan", "source_state")}
    unit = validation["dispatch"]["validation_unit"]
    payload = {
        "status": "failed",
        "limitations": [],
        "executions": [
            {
                "command": unit["commands"][0],
                "working_directory": unit["working_directories"][0],
                "executor": validation["node_id"],
                "result": "failed",
                "exit_code": 1,
                "elapsed": "1s",
                "evidence": "A real assertion failed",
                "artifact_paths": [],
            }
        ],
    }
    dispatch = {**validation["dispatch"], "before_state": request["source_state"], "after_state": request["source_state"]}
    content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
    artifact, metadata_path = tmp_path / "failed.md", tmp_path / "failed.json"
    artifact.write_bytes(content)
    metadata_path.write_text(json.dumps(metadata))
    journal = tmp_path / "actual-check.jsonl"
    append_journal_event(
        journal, lifecycle, JournalEventRequest(validation["node_id"], "accepted", source={"artifact_path": str(artifact), "metadata_path": str(metadata_path)})
    )
    args.journal = journal
    with pytest.raises(ValueError, match="not a planning or check failure"):
        recover_validation_launch(request, args)
    assert not Path(request["artifact_store"]).exists()


@pytest.mark.parametrize("environment", ["current host", "UV_CACHE_DIR=.uv-cache", "unrelated executor"])
def test_recovery_reconciles_both_prior_and_new_audits_without_accepting_other_environments(tmp_path: Path, environment: str) -> None:
    request, args, _validation = _recovery_fixture(tmp_path)
    recovered = recover_validation_launch(request, args)
    plan = _graph_plan(recovered["lifecycle_input"]["plan"])
    unit = plan.coalesced_validation_units[0]
    requirement = {
        "requirement_id": unit.requirement_ids[0],
        "planned_validation_digest": _planned_validation_digest(replace(unit, environment=environment)),
        "owner": "review-validator",
        "reason": "Validate the selected executor",
        "expected_evidence": "Exact baseline passes",
    }
    report = _validation_reconciliation(plan, [{"status": "no-findings", "evidence_id": "review:fixture", "validation_requirements": [requirement]}])
    assert bool(report["blockers"]) == (environment == "unrelated executor")
