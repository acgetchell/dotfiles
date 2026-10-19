"""Semantic audit mistakes retain immutable history and require fresh judgments."""

import json
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from test_review_graph_compact import _publish
from test_review_graph_runtime import _compact_audit_payload, _compile_repair_fixture_entry, _continuation_fixture, _late_handoff_replan
from test_support_review_graph import _prepare_all_fixture_timing


def test_replacement_synthesis_retains_exact_reused_evidence() -> None:
    plan = _late_handoff_replan()
    expected = ("review:audit-001", "review:audit-002")
    assert runtime._synthesis_reused_evidence_ids(plan, "rust-synthesis") == expected
    replacement = runtime._replacement_plan(
        plan, {"replacement_node_ids": {"rust-synthesis": "rust-synthesis-replacement", "repository-synthesis": "repository-synthesis-replacement"}}
    )
    assert runtime._synthesis_reused_evidence_ids(replacement, "rust-synthesis-replacement") == expected
    assert runtime._synthesis_reused_evidence_ids(replacement, "repository-synthesis-replacement") == expected
    assert runtime._synthesis_reused_evidence_ids(replacement, "rust-synthesis") == ()


def _fixture(tmp_path: Path, *, repairs_completed: int = 0) -> tuple[dict[str, Any], Namespace, dict[str, Any], dict[str, Any]]:
    lifecycle, dispatches, paths = _continuation_fixture(tmp_path)
    if repairs_completed:
        lifecycle["plan"]["review_lifecycle"]["repairs_completed"] = repairs_completed
        sample = dispatches["dispatches"][0]["dispatch"]
        dispatches = runtime.materialize_dispatches(
            {
                **lifecycle,
                "artifact_store": str(tmp_path / "completed-repairs"),
                **{key: sample[key] for key in ("repository_root", "authorization", "state_verification_command")},
            }
        )
        paths["dispatches"].write_text(json.dumps(dispatches))
    audits = [entry for entry in dispatches["dispatches"] if entry["dispatch"]["mode"] == "audit"]
    for entry in audits:
        _publish(entry, _compact_audit_payload(entry))
        _compile_repair_fixture_entry(entry, lifecycle, paths["journal"])
    audit = audits[0]
    runtime.append_journal_event(
        paths["journal"], lifecycle, runtime.JournalEventRequest(audit["node_id"], "invalidated", reason="Applied another semantic checklist.")
    )
    request = {**lifecycle, "artifact_store": str(tmp_path / "replacement"), "node_id": audit["node_id"], "reason": "Redo the dispatched contract."}
    args = Namespace(journal=paths["journal"], dispatches=paths["dispatches"], current_capture=paths["current-capture"])
    return request, args, audit, dispatches


@pytest.mark.parametrize("repairs_completed", [0, 2])
def test_replacement_retains_history_and_compiles_fresh_identity(tmp_path: Path, repairs_completed: int) -> None:
    request, args, old, dispatches = _fixture(tmp_path, repairs_completed=repairs_completed)
    paths = [args.journal, args.dispatches, *(Path(old[field]) for field in ("worker_payload_path", "artifact_path", "metadata_path"))]
    before = {path: path.read_bytes() for path in paths}
    result = runtime.replace_invalidated_audit(request, args)
    assert runtime.replace_invalidated_audit(request, args) == result
    lifecycle = result["lifecycle_input"]
    plan = runtime._graph_plan(lifecycle["plan"])
    assert lifecycle["plan"]["review_lifecycle"] == request["plan"]["review_lifecycle"]
    if repairs_completed == 2:
        with pytest.raises(ValueError, match="repair budget exhausted"):
            plan.review_lifecycle.next_repair(3)
    assert plan.worker_budget == request["plan"]["worker_budget"]
    assert plan.recovery_finalization_reserve == request["plan"]["recovery_finalization_reserve"]
    replacement_id = result["audit_replacement"]["replacement_node_ids"][old["node_id"]]
    new_dispatches = json.loads(Path(result["dispatches_path"]).read_bytes())
    new = next(entry for entry in new_dispatches["dispatches"] if entry["node_id"] == replacement_id)
    assert new["dispatch"]["evidence_id"] != old["dispatch"]["evidence_id"]
    assert new["dispatch"]["skill_id"] == old["dispatch"]["skill_id"]
    assert new["dispatch"]["fresh_context"]
    assert new["worker_payload_path"] != old["worker_payload_path"]
    assert {path: path.read_bytes() for path in before} == before
    assert old["node_id"] not in {node.node_id for node in plan.actual_worker_nodes}
    assert all(old["node_id"] not in node.predecessors for node in plan.actual_worker_nodes)
    for entry in dispatches["dispatches"]:
        if entry["node_id"] in result["retained_node_ids"]:
            assert entry == next(item for item in new_dispatches["dispatches"] if item["node_id"] == entry["node_id"])
    with pytest.raises(ValueError, match="superseded"):
        runtime.append_journal_event(args.journal, request, runtime.JournalEventRequest(old["node_id"], "in-flight"))
    journal = Path(result["journal_path"])
    old_source = {key: old[key] for key in ("artifact_path", "metadata_path")}
    with pytest.raises(ValueError, match=r"identity|node|evidence"):
        runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(replacement_id, "accepted", source=old_source))
    _publish(new, _compact_audit_payload(new))
    _compile_repair_fixture_entry(new, lifecycle, journal)
    _events, state, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
    assert state[replacement_id] == "accepted"
    assert {path: path.read_bytes() for path in before} == before
    _prepare_all_fixture_timing(new_dispatches)
    for _ in range(len(plan.actual_worker_nodes)):
        events, _state, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = runtime.next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=new_dispatches)
        if ready["complete"]:
            break
        assert ready["ready_dispatches"]
        for entry in ready["ready_dispatches"]:
            _compile_repair_fixture_entry(entry, lifecycle, journal)
    final = runtime.finalize_proof(
        runtime._finalize_document_from_files(
            lifecycle, Namespace(journal=journal, dispatches=Path(result["dispatches_path"]), current_capture=args.current_capture)
        )
    )
    assert final["graph_proof_status"] == "complete"
    assert final["audit_replacements"] == [result["audit_replacement"]]
    runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(replacement_id, "invalidated", reason="Second semantic mistake."))
    retry = {**lifecycle, "artifact_store": request["artifact_store"], "node_id": replacement_id, "reason": request["reason"]}
    with pytest.raises(ValueError, match="allowance exhausted"):
        runtime.replace_invalidated_audit(retry, Namespace(journal=journal, dispatches=Path(result["dispatches_path"]), current_capture=args.current_capture))


def test_replacement_cannot_read_the_invalidated_judgment(tmp_path: Path) -> None:
    request, args, old, _dispatches = _fixture(tmp_path)
    result = runtime.replace_invalidated_audit(request, args)
    replacement_id = result["audit_replacement"]["replacement_node_ids"][old["node_id"]]
    dispatches = json.loads(Path(result["dispatches_path"]).read_bytes())
    new = next(entry for entry in dispatches["dispatches"] if entry["node_id"] == replacement_id)
    payload = _compact_audit_payload(new)
    payload["nearby_contract_owners"].append(old["artifact_path"])
    with pytest.raises(ValueError, match="fresh-context review read another node"):
        _publish(new, payload)
    assert not Path(new["worker_payload_path"]).exists()


@pytest.mark.parametrize("damage", ["source", "in-flight", "not-invalidated", "unrelated-invalidation", "history"])
def test_replacement_rejects_unsafe_transitions(tmp_path: Path, damage: str) -> None:
    request, args, old, dispatches = _fixture(tmp_path)
    if damage == "source":
        capture = json.loads(args.current_capture.read_bytes())
        capture["captured_worktree_fingerprint"] = "changed"
        args.current_capture.write_text(json.dumps(capture))
        message = "unchanged source"
    elif damage == "in-flight":
        validator = next(entry for entry in dispatches["dispatches"] if entry["dispatch"]["mode"] == "validation")
        runtime.append_journal_event(args.journal, request, runtime.JournalEventRequest(validator["node_id"], "in-flight"))
        message = "quiescent"
    elif damage == "not-invalidated":
        request["node_id"] = next(entry["node_id"] for entry in dispatches["dispatches"] if entry["dispatch"]["mode"] == "audit" and entry != old)
        message = "explicitly invalidated"
    elif damage == "unrelated-invalidation":
        other = next(entry for entry in dispatches["dispatches"] if entry["dispatch"]["mode"] == "audit" and entry != old)
        runtime.append_journal_event(
            args.journal, request, runtime.JournalEventRequest(other["node_id"], "invalidated", reason="Another contract needs reconciliation.")
        )
        message = "unrelated invalidated nodes"
    else:
        result = runtime.replace_invalidated_audit(request, args)
        artifact = Path(old["artifact_path"])
        artifact.chmod(0o644)
        artifact.write_bytes(b"Changed historical judgment")
        with pytest.raises(ValueError, match="preserved audit replacement evidence changed"):
            runtime._dispatches_by_node(
                json.loads(Path(result["dispatches_path"]).read_bytes()),
                plan=runtime._graph_plan(result["lifecycle_input"]["plan"]),
                source_state=tuple(request["source_state"]),
            )
        return
    with pytest.raises(ValueError, match=message):
        runtime.replace_invalidated_audit(request, args)


def test_replacement_rejects_symlinked_history_before_writing(tmp_path: Path) -> None:
    request, args, old, _dispatches = _fixture(tmp_path)
    plan = runtime._graph_plan(request["plan"])
    events, _state, head = runtime.read_execution_journal(args.journal, plan=plan, source_state=tuple(request["source_state"]))
    accepted = next(event for event in events if event["node_id"] == old["node_id"] and event["status"] == "accepted")
    record = {
        "node_id": old["node_id"],
        "skill_id": old["dispatch"]["skill_id"],
        "requirement_ids": old["dispatch"]["requirement_ids"],
        "reason": request["reason"],
        "source_state": request["source_state"],
        "previous_plan_digest": runtime._plan_digest(plan),
        "previous_journal_head": head,
        "invalidated_evidence_id": accepted["evidence"]["evidence_id"],
    }
    identity = runtime.digest_bytes(runtime.canonical_json(record).encode())[7:23]
    destination = tmp_path / "unexpected-history"
    destination.mkdir()
    store = Path(request["artifact_store"])
    store.mkdir()
    history = store / f"audit-history-{identity}"
    history.symlink_to(destination, target_is_directory=True)
    before = args.journal.read_bytes()
    with pytest.raises(ValueError, match="history directory must not traverse symlinks"):
        runtime.replace_invalidated_audit(request, args)
    assert not list(destination.iterdir())
    assert list(store.iterdir()) == [history]
    assert args.journal.read_bytes() == before
    assert not runtime._audit_replacement_marker(plan).exists()


def test_saved_replacement_records_reject_malformed_history_and_copy_containers(tmp_path: Path) -> None:
    request, args, _old, _dispatches = _fixture(tmp_path)
    result = runtime.replace_invalidated_audit(request, args)
    raw = result["lifecycle_input"]["plan"]
    record = raw["audit_replacements"][0]
    for field in record:
        incomplete = deepcopy(raw)
        del incomplete["audit_replacements"][0][field]
        with pytest.raises(ValueError, match="audit replacement record is missing fields"):
            runtime._graph_plan(incomplete)
    malformed_values = {
        "node_id": "",
        "skill_id": 5,
        "requirement_ids": [],
        "reason": False,
        "source_state": ["only", "two"],
        "previous_plan_digest": "invalid",
        "previous_journal_head": 5,
        "invalidated_evidence_id": None,
        "replacement_node_ids": {record["node_id"]: []},
        "preserved_files": [{"path": "history", "digest": "invalid"}],
        "forbidden_artifacts": ["unrelated"],
    }
    for field, value in malformed_values.items():
        malformed = deepcopy(raw)
        malformed["audit_replacements"][0][field] = value
        with pytest.raises(ValueError, match=field if field != "replacement_node_ids" else "must be one non-empty line"):
            runtime._graph_plan(malformed)
    for field in ("replacement_node_ids", "preserved_files", "forbidden_artifacts"):
        malformed = deepcopy(raw)
        malformed["audit_replacements"][0][field] = {}
        with pytest.raises(ValueError, match=field):
            runtime._graph_plan(malformed)
    parsed = runtime._graph_plan(raw)
    saved = deepcopy(parsed.audit_replacements)
    record["preserved_files"][0]["path"] = "changed"
    record["replacement_node_ids"].clear()
    record["requirement_ids"].clear()
    record["forbidden_artifacts"].clear()
    record["source_state"].clear()
    assert parsed.audit_replacements == saved


@pytest.mark.parametrize("interrupt_output", [False, True])
def test_replacement_cli_uses_real_operation_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, interrupt_output: bool
) -> None:
    request, args, _old, _dispatches = _fixture(tmp_path)
    path, output = tmp_path / "request.json", tmp_path / "result.json"
    path.write_text(json.dumps(request))
    marker = runtime._audit_replacement_marker(runtime._graph_plan(request["plan"]))
    committed_marker = None
    command = [
        "replace-invalidated-audit",
        "--input",
        str(path),
        "--journal",
        str(args.journal),
        "--dispatches",
        str(args.dispatches),
        "--current-capture",
        str(args.current_capture),
        "--output",
        str(output),
    ]
    if interrupt_output:
        fsync_directory = runtime._fsync_directory

        def fail_output_sync(path: Path) -> None:
            if path == output.parent and output.exists():
                msg = "Interrupted result publication"
                raise OSError(msg)
            fsync_directory(path)

        with monkeypatch.context() as patch:
            patch.setattr(runtime, "_fsync_directory", fail_output_sync)
            assert runtime.main(command) == 2
        assert "Interrupted result publication" in capsys.readouterr().err
        assert not output.exists()
        committed_marker = marker.read_bytes()
    assert runtime.main(command) == 0
    if committed_marker is not None:
        assert marker.read_bytes() == committed_marker
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "audit-replaced"
    full = json.loads(output.read_bytes())
    assert receipt["output_fields"] == sorted(full)
    assert receipt["next_operation_inputs"]["lifecycle_input_path"] == full["lifecycle_input_path"]
