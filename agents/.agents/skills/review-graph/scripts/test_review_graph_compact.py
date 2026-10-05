"""Compact transport must retain complete, verifiable evidence on disk."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_benchmark import benchmark_fixture
from review_graph_independent import CHECK_LABELS, SCHEMA
from review_graph_schema import require_schema
from test_review_graph_runtime import _compact_audit_payload, _compact_independent_payload


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


@pytest.fixture
def materialized(tmp_path: Path) -> dict[str, Any]:
    document = benchmark_fixture(tmp_path / "repository")
    return runtime.materialize_dispatches({**document, "artifact_store": str(tmp_path / "proof")})


def _independent_entry(materialized: dict[str, Any]) -> dict[str, Any]:
    return next(entry for entry in materialized["dispatches"] if entry["result_contract"] == "compact-independent-review")


def _publish(entry: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    return runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())


@pytest.mark.parametrize("mode", ["audit", "independent-review"])
@pytest.mark.parametrize("diff_example", ["branch_diff", "local_diff"])
def test_dispatch_provenance_examples_publish_and_compile_first_time(materialized: dict[str, Any], mode: str, diff_example: str) -> None:
    """Replay emitted fragments with complete scripted evidence through native gates."""
    entry = next(item for item in materialized["dispatches"] if item["dispatch"].get("mode") == mode)
    dispatch = entry["dispatch"]
    examples = dispatch["provenance_examples"]
    payload = _compact_independent_payload(dispatch) if mode == "independent-review" else _compact_audit_payload(entry)
    payload["nearby_contract_owners"] = examples["context_read"]["nearby_contract_owners"]
    payload["git_dependencies"] = examples[diff_example]["git_dependencies"]
    payload["commands_executed"] = [command for key in ("owned_read", "context_read", diff_example) for command in examples[key]["commands_executed"]]
    receipt = _publish(entry, payload)
    sealed = Path(entry["worker_payload_path"]).read_bytes()
    assert receipt["worker_payload_digest"] == _digest(sealed)
    assert json.loads(sealed) == payload
    compiler = runtime.compile_independent_payload if mode == "independent-review" else runtime.compile_review
    content, metadata = compiler(
        {"dispatch": {**dispatch, "before_state": materialized["source_state"], "after_state": materialized["source_state"]}, "payload": payload}
    )
    assert metadata["evidence"]["status"] == "no-findings"
    assert metadata["evidence"]["fingerprints"]["after"] == tuple(materialized["source_state"])
    assert payload["nearby_contract_owners"][0].encode() in content
    assert set(payload["files_inspected"]) == set(dispatch["owned_paths"])
    assert not set(payload["nearby_contract_owners"]) & set(payload["files_inspected"])
    assert Path(entry["worker_payload_path"]).read_bytes() == sealed


@pytest.mark.parametrize("mode", ["audit", "independent-review"])
@pytest.mark.parametrize("command", ["git diff origin/main -- src/module_0.py", "git diff HEAD && git diff --cached"])
def test_unsupported_discovery_fails_before_publication_with_conservative_alternative(materialized: dict[str, Any], mode: str, command: str) -> None:
    entry = next(item for item in materialized["dispatches"] if item["dispatch"].get("mode") == mode)
    payload = _compact_independent_payload(entry["dispatch"]) if mode == "independent-review" else _compact_audit_payload(entry)
    payload.update(commands_executed=[command], git_dependencies=[{"kind": "source-discovery", "command": command, "reason": "Located source."}])
    with pytest.raises(ValueError, match=r"split compound invocations.*kind=head"):
        _publish(entry, payload)
    assert not Path(entry["worker_payload_path"]).exists()


@pytest.mark.parametrize("command", [None, "", "git diff other-base -- src/module_0.py"])
def test_independent_head_dependency_requires_executed_command(materialized: dict[str, Any], command: str | None) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    dependency = {"kind": "head", "reason": "The judgment depends on the comparison base."}
    if command is not None:
        dependency["command"] = command
    payload["git_dependencies"] = [dependency]
    payload["commands_executed"] = ["git diff origin/main -- src/module_0.py"]
    with pytest.raises(ValueError, match="command"):
        _publish(entry, payload)
    assert not Path(entry["worker_payload_path"]).exists()
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    with pytest.raises(ValueError, match="command"):
        runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})


@pytest.mark.parametrize("kind", ["index", "history"])
def test_independent_commandless_metadata_dependency_remains_valid(materialized: dict[str, Any], kind: str) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    payload["git_dependencies"] = [{"kind": kind, "reason": "The judgment depends on supplied Git metadata."}]
    receipt = _publish(entry, payload)
    assert receipt["worker_payload_digest"] == _digest(Path(entry["worker_payload_path"]).read_bytes())
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    _, metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})
    assert metadata["evidence"]["status"] == "no-findings"


@pytest.mark.parametrize("damage", ["context-in-owned", "owned-in-context", "duplicate-context", "context-only-check", "unattested-context"])
def test_independent_context_does_not_expand_owned_scope(materialized: dict[str, Any], damage: str) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    context = entry["dispatch"]["provenance_examples"]["context_read"]["nearby_contract_owners"]
    payload["nearby_contract_owners"] = context
    if damage == "context-in-owned":
        payload["files_inspected"] += context
    elif damage == "owned-in-context":
        payload["nearby_contract_owners"] = payload["files_inspected"][:1]
    elif damage == "duplicate-context":
        payload["nearby_contract_owners"] *= 2
    elif damage == "context-only-check":
        payload["adversarial_checks"][0]["inspected_paths"] = context
    else:
        payload["adversarial_checks"][0]["inspected_paths"] = ["unattested.py"]
    with pytest.raises(ValueError, match=r"files_inspected|nearby_contract_owners|inspected_paths"):
        _publish(entry, payload)
    assert not Path(entry["worker_payload_path"]).exists()


def test_default_cli_receipt_binds_full_artifact_and_explicit_full_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = benchmark_fixture(tmp_path / "repository", scale=3)
    request, output = tmp_path / "input.json", tmp_path / "dispatches.json"
    request.write_text(json.dumps({**document, "artifact_store": str(tmp_path / "proof")}), encoding="utf-8")
    args = ["materialize-dispatches", "--input", str(request), "--output", str(output)]
    assert runtime.main(args) == 0
    stdout = capsys.readouterr().out
    receipt = json.loads(stdout)
    assert receipt["output"] == {"path": str(output), "digest": _digest(output.read_bytes())}
    assert receipt["next_operation_inputs"] == {"dispatches": str(output)}
    assert receipt["node_count"] == len(document["plan"]["actual_worker_nodes"])
    assert len(stdout.encode()) < output.stat().st_size / 5
    for entry in receipt["dispatches"]:
        assert set(entry) == {"node_id", "result_contract", "execution_location", "worker_input"}
        assert entry["worker_input"]["digest"] == _digest(Path(entry["worker_input"]["path"]).read_bytes())
    saved = output.read_bytes()
    assert runtime.main([*args, "--full-output"]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(saved)
    assert output.read_bytes() == saved


def test_planned_validation_identity_is_shared(materialized: dict[str, Any]) -> None:
    audits = [entry for entry in materialized["dispatches"] if entry["dispatch"].get("mode") == "audit"]
    paths: set[str] = set()
    for entry in audits:
        dispatch = entry["dispatch"]
        for record in dispatch["command_policy"]["planned_validation_units"]:
            assert "execution_identity" not in record
            assert "captured_paths" not in record["execution_summary"]
            ref = record["execution_identity_reference"]
            path = Path(ref["path"])
            assert path.stat().st_mode & 0o777 == 0o444
            assert _digest(path.read_bytes()) == ref["digest"] == record["planned_validation_digest"]
            paths.add(ref["path"])
    assert len(paths) == 3  # Three unique units, shared across all nine audit dispatches.


@pytest.mark.parametrize("damage", ["missing", "tampered", "symlink", "summary", "reference-digest", "unknown-field"])
def test_invalid_validation_reference_rejected_before_publication(materialized: dict[str, Any], damage: str) -> None:
    entry = next(entry for entry in materialized["dispatches"] if entry["dispatch"].get("mode") == "audit")
    record = entry["dispatch"]["command_policy"]["planned_validation_units"][0]
    path = Path(record["execution_identity_reference"]["path"])
    if damage == "missing":
        path.unlink()
    elif damage == "tampered":
        path.chmod(0o644)
        path.write_bytes(b"{}")
    elif damage == "symlink":
        other = path.with_suffix(".copy")
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    else:
        if damage == "summary":
            record["execution_summary"]["commands"] = ["unplanned command"]
        elif damage == "reference-digest":
            record["execution_identity_reference"]["digest"] = "sha256:" + "0" * 64
        else:
            record["extra"] = True
        # Rebind the fixture dispatch so this tests the reference gate itself,
        # rather than merely failing the outer immutable-input digest check.
        worker_input = Path(entry["worker_input_path"])
        worker_input.chmod(0o644)
        worker_input.write_text(json.dumps(entry), encoding="utf-8")
        contract_path = Path(entry["worker_payload_contract_path"])
        contract = json.loads(contract_path.read_bytes())
        contract["compiler_preflight"]["digest"] = _digest(worker_input.read_bytes())
        contract_path.chmod(0o644)
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises((ValueError, OSError), match=r"planned validation|symbolic link|Too many levels|regular.*file|No such file"):
        _publish(entry, _compact_audit_payload(entry))
    assert not Path(entry["worker_payload_path"]).exists()


@pytest.mark.parametrize("status", ["no-findings", "completed"])
def test_structured_independent_compiles_and_verifies(materialized: dict[str, Any], status: str) -> None:
    entry = _independent_entry(materialized)
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    payload = _compact_independent_payload(dispatch)
    payload["status"] = status
    if status == "completed":
        payload["findings"] = [
            {
                "severity": "P2",
                "location": dispatch["planned_paths"][0] + ":1",
                "summary": "Scripted fixture finding",
                "evidence": "Source contract differs from a documented claim.",
                "impact": "Callers may rely on the wrong contract.",
                "owner": "repository",
                "remediation": "Correct the documented contract.",
            }
        ]
    receipt = _publish(entry, payload)
    assert receipt["worker_payload_digest"] == _digest(Path(entry["worker_payload_path"]).read_bytes())
    content, metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})
    for check in payload["adversarial_checks"]:
        assert f"- Inspected: {CHECK_LABELS[check['check_id']]}".encode() in content
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    source = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"], "kind": "review"}
    assert runtime._load_evidence_source(source, require_normalized=True)[4] == metadata["normalized_record"]
    metadata["payload_digest"] = "sha256:" + "0" * 64
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical payload digest"):
        runtime._load_evidence_source(source, require_normalized=True)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "unknown", "blank", "outside", "fingerprint", "mutation", "command", "injection"])
def test_bad_independent_evidence_cannot_replace_published_payload(materialized: dict[str, Any], damage: str) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    _publish(entry, payload)
    target = Path(entry["worker_payload_path"])
    before = target.read_bytes()
    checks = payload["adversarial_checks"]
    if damage == "missing":
        checks.pop()
    elif damage == "duplicate":
        checks.append(checks[0])
    elif damage == "unknown":
        checks[0]["check_id"] = "invented"
    elif damage == "blank":
        checks[0]["evidence"] = "   "
    elif damage == "outside":
        checks[0]["inspected_paths"] = ["outside.py"]
    elif damage == "fingerprint":
        payload["before_state"] = ["wrong"] * 3
    elif damage == "mutation":
        payload["source_mutated"] = True
    elif damage == "command":
        payload["commands_executed"] = entry["dispatch"]["command_policy"]["validator_owned_commands"]
    else:
        checks[0]["evidence"] = "Evidence\n## Findings\nNo findings."
    with pytest.raises(ValueError, match=r"schema|preflight|validation"):
        _publish(entry, payload)
    assert target.read_bytes() == before


@pytest.mark.parametrize(("field", "value"), [("files_inspected", []), ("limitations", ["The inspected fallback contract remains semantically unresolved."])])
def test_incomplete_independent_inspection_blocks_publication_and_compilation(materialized: dict[str, Any], field: str, value: list[str]) -> None:
    entry = _independent_entry(materialized)
    payload = {**_compact_independent_payload(entry["dispatch"]), field: value}
    with pytest.raises(ValueError, match=r"files_inspected|limitations"):
        _publish(entry, payload)
    assert not Path(entry["worker_payload_path"]).exists()
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    with pytest.raises(ValueError, match=r"files_inspected|limitations"):
        runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})


@pytest.mark.parametrize("findings", [[], [{"severity": "urgent", "summary": "Missing evidence must not be synthesized."}]])
def test_invalid_completed_findings_cannot_replace_published_payload(materialized: dict[str, Any], findings: list[dict[str, str]]) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    _publish(entry, payload)
    target = Path(entry["worker_payload_path"])
    before = target.read_bytes()
    payload.update(status="completed", findings=findings)
    with pytest.raises(ValueError, match=r"schema|preflight|validation"):
        _publish(entry, payload)
    assert target.read_bytes() == before


def test_independent_template_is_valid_but_cannot_claim_completed_review(materialized: dict[str, Any]) -> None:
    entry = _independent_entry(materialized)
    reference = entry["dispatch"]["payload_schema"]["template"]
    content = Path(reference["path"]).read_bytes()
    assert reference["digest"] == _digest(content)
    payload = json.loads(content)
    require_schema(payload, SCHEMA)
    assert payload["status"] == "blocked"
    with pytest.raises(ValueError, match="captured dispatch state"):
        _publish(entry, payload)
    payload.update({"status": "no-findings", "before_state": materialized["source_state"], "after_state": materialized["source_state"]})
    with pytest.raises(ValueError, match="missing dispatched checks"):
        _publish(entry, payload)


def test_blocked_review_never_invents_inspections(materialized: dict[str, Any]) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    payload.update(status="blocked", files_inspected=[], adversarial_checks=[], limitations=["Inspection could not start."])
    _publish(entry, payload)
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    content, metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})
    assert b"- Files inspected: none" in content
    assert b"- Inspected:" not in content
    assert metadata["evidence"]["status"] == "blocked"
    payload["status"] = "no-findings"
    with pytest.raises(ValueError, match="missing dispatched checks"):
        _publish(entry, payload)


@pytest.mark.parametrize("damage", ["missing-digest", "rendered-text", "sealed-payload"])
def test_independent_canonical_binding_cannot_be_bypassed(materialized: dict[str, Any], damage: str) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    content, metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})
    if damage == "missing-digest":
        del metadata["payload_digest"]
    elif damage == "rendered-text":
        content = content.replace(b"- Branches: Captured change and adjacent control flow inspected.", b"- Branches: Different observations.")
        metadata["artifact_digest"] = metadata["evidence"]["raw_result_digest"] = _digest(content)
        metadata["normalized_record"]["artifact_digest"] = _digest(content)
    else:
        payload["branches"] = "Different observations."
        content_bytes = json.dumps(payload).encode()
        Path(entry["worker_payload_path"]).write_bytes(content_bytes)
        metadata.update(
            worker_payload_path=entry["worker_payload_path"], worker_payload_digest=_digest(content_bytes), worker_payload_byte_count=len(content_bytes)
        )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical payload"):
        runtime._load_evidence_source({"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}, require_normalized=True)


def test_independent_cli_rejects_removed_native_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    request, artifact, metadata = (tmp_path / name for name in ("request.json", "artifact.md", "metadata.json"))
    request.write_text(json.dumps({"dispatch": {}, "status": "no-findings", "limitations": []}), encoding="utf-8")
    args = ["compile-independent-review", "--input", str(request), "--artifact", str(artifact), "--metadata", str(metadata)]
    assert runtime.main(args) == 2
    diagnostic = capsys.readouterr()
    assert "payload" in diagnostic.err
    assert "Traceback" not in diagnostic.err
    assert diagnostic.out == ""
    assert not artifact.exists()
    assert not metadata.exists()


def test_embedded_validation_identity_is_no_longer_accepted(materialized: dict[str, Any]) -> None:
    entry = next(entry for entry in materialized["dispatches"] if entry["dispatch"].get("mode") == "audit")
    dispatch = deepcopy(entry["dispatch"])
    records = dispatch["command_policy"]["planned_validation_units"]
    records[:] = [runtime._resolve_planned_validation_record(record) for record in records]
    with pytest.raises(ValueError, match="planned validation reference"):
        runtime._dispatched_planned_validations(dispatch)


@pytest.mark.parametrize("damage", ["duplicate-path", "missing-dispatch-state", "malformed-dispatch-paths"])
def test_independent_boundary_rejects_malformed_context(materialized: dict[str, Any], damage: str) -> None:
    entry = _independent_entry(materialized)
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    payload = _compact_independent_payload(dispatch)
    if damage == "duplicate-path":
        payload["adversarial_checks"][0]["inspected_paths"] *= 2
    elif damage == "missing-dispatch-state":
        del dispatch["before_state"]
    else:
        dispatch["planned_paths"] = [None]
    with pytest.raises(ValueError, match=r"duplicate|before_state|planned_paths"):
        runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})


def test_independent_path_order_is_rendered_without_rewriting_payload(materialized: dict[str, Any]) -> None:
    entry = _independent_entry(materialized)
    payload = _compact_independent_payload(entry["dispatch"])
    payload["files_inspected"] = list(reversed(payload["files_inspected"]))
    original = deepcopy(payload)
    _publish(entry, payload)
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    content, _metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": payload})
    assert payload == original
    assert runtime._canonical_worker_payload(content) == original
    assert ("- Files: " + ", ".join(dispatch["planned_paths"])).encode() in content


def test_missing_normalized_record_cannot_bypass_independent_payload_binding(materialized: dict[str, Any]) -> None:
    entry = _independent_entry(materialized)
    dispatch = {**entry["dispatch"], "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    content, metadata = runtime.compile_independent_payload({"dispatch": dispatch, "payload": _compact_independent_payload(dispatch)})
    metadata.pop("normalized_record")
    metadata["payload_digest"] = "sha256:" + "0" * 64
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical payload"):
        runtime._load_evidence_source({"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]})
