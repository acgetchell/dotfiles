"""Large real handoffs retain complete proof behind bounded native references."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
import test_review_graph_commit as commit_tests
from review_graph_integrity import canonical_json, digest_bytes
from review_graph_plan import MAX_NATIVE_EVIDENCE_BLOCK_BYTES, MAX_NATIVE_SECTION_BYTES, _native_json_block
from review_graph_provenance import metadata_transition_reference
from review_graph_reuse import CommitHandoffTransition
from test_review_graph_commit import _save, _validation_payload
from test_review_graph_runtime import _compact_independent_payload, _run_test_git
from test_review_graph_transitions import _payload, _synthesis_payload


def _handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, large: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, str]]]:
    baseline = commit_tests._baseline_mutation_fixture

    def with_complete_inventory(root: Path) -> Any:
        fixture = baseline(root)
        git, repository, _template, _capture, _plan = fixture
        inventory = repository / "inventory"
        inventory.mkdir()
        for ordinal in range(450):
            (inventory / f"path-{ordinal:04d}.txt").write_text(f"baseline inventory {ordinal}\n")
        _run_test_git(git, "-C", str(repository), "add", "inventory")
        _run_test_git(git, "-C", str(repository), "commit", "-m", "Seed complete repository inventory")
        return fixture

    if large:
        monkeypatch.setattr(commit_tests, "_baseline_mutation_fixture", with_complete_inventory)
    request, _entries, sources = commit_tests._commit_fixture(tmp_path, mode="branch")
    result = runtime.resume_after_authorized_commit(request)
    return request, result, {node: source for node, source in sources.items() if node in result["preserved_node_ids"]}


def _dispatch(entry: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        **entry["dispatch"],
        "before_state": result["current_source_state"],
        "after_state": result["current_source_state"],
        "external_metadata_transitions": result["lifecycle_input"]["external_metadata_transitions"],
    }


def _load_compiled(tmp_path: Path, name: str, content: bytes, metadata: dict[str, Any]) -> None:
    artifact, record = tmp_path / f"{name}.review.md", tmp_path / f"{name}.evidence.json"
    artifact.write_bytes(content)
    record.write_text(json.dumps(metadata))
    runtime._load_evidence_source({"artifact_path": str(artifact), "metadata_path": str(record)}, require_normalized=True)


def _assert_reference(content: bytes, metadata: dict[str, Any], *, independent: bool = False, large: bool = True) -> None:
    text = content.decode()
    section = "## Review Graph Envelope" if independent else "## State Verification"
    body = text.split(section + "\n", 1)[1].split("\n## ", 1)[0]
    assert len(body.encode()) < MAX_NATIVE_SECTION_BYTES
    assert "- External metadata transitions reference: " in body
    assert "- External metadata transitions: " not in body
    transitions = metadata["evidence"]["fingerprints"]["metadata_transitions"]
    if large:
        assert len(transitions[0]["before"]["repository_path_fingerprints"]) > 450
        assert len(canonical_json(transitions).encode()) > MAX_NATIVE_SECTION_BYTES
    parsed = runtime._fingerprint_evidence(json.loads(json.dumps(metadata["evidence"]["fingerprints"])))
    assert canonical_json(metadata_transition_reference(parsed.metadata_transitions)) in body
    machine, blockers = _native_json_block(text)
    assert blockers == ()
    assert machine is not None
    assert len(canonical_json(dict(machine)).encode()) < MAX_NATIVE_EVIDENCE_BLOCK_BYTES


def test_large_real_commit_handoff_compiles_all_four_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, result, sources = _handoff(tmp_path, monkeypatch)
    entries = result["dispatch_set"]["dispatches"]
    audit = next(entry for entry in entries if entry["dispatch"]["mode"] == "audit")
    render_state = runtime._state_verification

    def inline_state(dispatch: dict[str, Any], evidence: Any, paths: tuple[str, ...]) -> str:
        body = render_state(dispatch, evidence, paths)
        compact = "- External metadata transitions reference: " + canonical_json(metadata_transition_reference(evidence.fingerprints.metadata_transitions))
        inline = "- External metadata transitions: " + canonical_json([asdict(item) for item in evidence.fingerprints.metadata_transitions])
        return body.replace(compact, inline)

    with monkeypatch.context() as original_rendering:
        original_rendering.setattr(runtime, "_state_verification", inline_state)
        with pytest.raises(ValueError, match="maximum size"):
            runtime.compile_review({"dispatch": _dispatch(audit, result), "payload": _payload(audit["dispatch"]["owned_paths"])})
    content, metadata = runtime.compile_review({"dispatch": _dispatch(audit, result), "payload": _payload(audit["dispatch"]["owned_paths"])})
    _assert_reference(content, metadata)
    _load_compiled(tmp_path, "audit-large", content, metadata)
    independent = next(entry for entry in entries if entry["dispatch"]["mode"] == "independent-review")
    payload = _compact_independent_payload(independent["dispatch"])
    payload.update(before_state=result["current_source_state"], after_state=result["current_source_state"])
    content, metadata = runtime.compile_independent_payload({"dispatch": _dispatch(independent, result), "payload": payload})
    _assert_reference(content, metadata, independent=True)
    _load_compiled(tmp_path, "independent-large", content, metadata)

    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    plan = runtime._graph_plan(lifecycle["plan"])
    seen: set[str] = set()
    for _ordinal in range(plan.complete_node_count + 1):
        events, _state, _head = runtime.read_execution_journal(Path(result["journal_path"]), plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = runtime.next_ready_nodes(lifecycle, journal_events=events, dispatch_set=result["dispatch_set"])
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready["blockers"]
        for entry in ready["ready_dispatches"]:
            mode = entry["dispatch"]["mode"]
            if mode == "validation":
                payload = _validation_payload(entry)
                payload["native_ci"] = [
                    {"name": "CI", "target": "linux", "head_sha": request["new_capture"]["head"], "conclusion": "success", "url": "https://example.com/runs/1"}
                ]
            else:
                assert mode == "synthesis"
                bundle = runtime.build_synthesis_bundle({**lifecycle, "sources": list(sources.values())})
                payload = _synthesis_payload(entry["dispatch"], bundle)
            source = _save(entry, lifecycle, Path(result["journal_path"]), payload)
            sources[entry["node_id"]] = source
            saved = json.loads(Path(source["metadata_path"]).read_bytes())
            _assert_reference(Path(source["artifact_path"]).read_bytes(), saved)
            seen.add(mode)
    assert seen == {"validation", "synthesis"}
    proof = runtime.finalize_proof({**lifecycle, "sources": list(sources.values())})
    assert proof["graph_proof_status"] == "complete", proof["blockers"]


@pytest.mark.parametrize("damage", ["digest", "field", "count", "extra", "missing", "duplicate", "history"])
def test_transition_reference_and_full_history_are_both_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    _request, result, _sources = _handoff(tmp_path, monkeypatch, large=False)
    entry = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["mode"] == "audit")
    content, metadata = runtime.compile_review({"dispatch": _dispatch(entry, result), "payload": _payload(entry["dispatch"]["owned_paths"])})
    fingerprints = runtime._fingerprint_evidence(json.loads(json.dumps(metadata["evidence"]["fingerprints"])))
    reference = metadata_transition_reference(fingerprints.metadata_transitions)
    line = "- External metadata transitions reference: " + canonical_json(reference)
    replacement = line
    if damage == "history":
        transition = fingerprints.metadata_transitions[-1]
        assert isinstance(transition, CommitHandoffTransition)
        history = transition.commit_handoff["preserved_files"][0]
        Path(history["path"]).unlink()
    elif damage == "missing":
        replacement = ""
    elif damage == "duplicate":
        replacement = line + "\n- External metadata transitions: " + canonical_json([asdict(item) for item in fingerprints.metadata_transitions])
    else:
        if damage == "digest":
            reference["digest"] = "sha256:" + "0" * 64
        elif damage == "field":
            reference["metadata_field"] = "expectation.canonical_worker_payload"
        elif damage == "count":
            reference["transition_count"] += 1
        else:
            reference["unchecked"] = True
        replacement = "- External metadata transitions reference: " + canonical_json(reference)
    content = content.replace(line.encode(), replacement.encode())
    metadata["artifact_digest"] = metadata["evidence"]["raw_result_digest"] = digest_bytes(content)
    with pytest.raises(ValueError, match=r"metadata transitions|metadata transition|history missing|maximum size"):
        _load_compiled(tmp_path, "tampered", content, metadata)


def test_existing_inline_native_transition_evidence_remains_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _request, result, _sources = _handoff(tmp_path, monkeypatch, large=False)
    entry = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["mode"] == "audit")
    content, metadata = runtime.compile_review({"dispatch": _dispatch(entry, result), "payload": _payload(entry["dispatch"]["owned_paths"])})
    fingerprints = runtime._fingerprint_evidence(json.loads(json.dumps(metadata["evidence"]["fingerprints"])))
    reference = canonical_json(metadata_transition_reference(fingerprints.metadata_transitions))
    inline = canonical_json([asdict(item) for item in fingerprints.metadata_transitions])
    content = content.replace(("- External metadata transitions reference: " + reference).encode(), ("- External metadata transitions: " + inline).encode())
    metadata["artifact_digest"] = metadata["evidence"]["raw_result_digest"] = digest_bytes(content)
    metadata["normalized_record"]["artifact_digest"] = digest_bytes(content)
    _load_compiled(tmp_path, "inline-existing", content, metadata)


def test_saved_failed_validation_payload_compiles_without_republication_or_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, result, _sources = _handoff(tmp_path, monkeypatch, large=False)
    entry = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["node_id"] in request["native_ci"])
    payload = _validation_payload(entry)
    payload["status"] = "failed"
    for execution in payload["executions"]:
        execution.update(result="failed", exit_code=1, elapsed=17.204975416, evidence="Recorded native command failure; retry compilation only.")
    payload_bytes = (json.dumps(payload) + "\n").encode()
    Path(entry["worker_payload_path"]).write_bytes(payload_bytes)
    snapshots: list[str] = []
    for phase in ("before", "after"):
        path = tmp_path / f"workspace-{phase}.json"
        assert (
            runtime.main(
                [
                    "snapshot-workspace",
                    "--input",
                    result["lifecycle_input_path"],
                    "--dispatches",
                    result["dispatches_path"],
                    "--node-id",
                    entry["node_id"],
                    "--current-capture",
                    result["capture_path"],
                    "--output",
                    str(path),
                ]
            )
            == 0
        )
        snapshots.extend([f"--workspace-{phase}", str(path)])

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        msg = "saved-payload compilation must neither republish nor execute validation"
        raise AssertionError(msg)

    monkeypatch.setattr(runtime, "publish_worker_payload_bytes", forbidden)
    monkeypatch.setattr(runtime, "run_command_bytes", forbidden)
    assert (
        runtime.main(
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
                result["capture_path"],
                "--output",
                str(tmp_path / "saved-compiled.json"),
                *snapshots,
            ]
        )
        == 0
    )
    assert Path(entry["worker_payload_path"]).read_bytes() == payload_bytes
    metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
    assert metadata["evidence"]["status"] == "failed"
    assert metadata["normalized_record"]["executions"][0]["elapsed"] == 17.204975416
    _assert_reference(Path(entry["artifact_path"]).read_bytes(), metadata, large=False)
