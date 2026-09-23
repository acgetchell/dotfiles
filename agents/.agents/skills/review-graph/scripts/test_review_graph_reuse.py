"""Large partial-recheck proofs and typed audit context across repair epochs."""

import hashlib
import json
import shlex
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import MAX_NATIVE_SECTION_BYTES, plan_from_document
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compile_repair_fixture_entry,
    _publish_worker_bytes,
    _run_test_git,
    _worker_input_fixture,
)
from test_review_graph_transitions import _materialize, _payload, _synthesis_payload


def _audit_request(tmp_path: Path, *, large: bool = False, caveat: str = "facts") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:  # noqa: C901 - explicit fixture policy variants.
    """Capture an actual repository and preserve a fresh, partitioned audit."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    owned = ["LICENSE", "tool.py"]
    if large:
        owned = [f"scientific_model_{index:03d}_numerical_invariants_and_reproducibility.py" for index in range(23)]
        for path in owned:
            (repository / path).write_text("value = 1\n")
        for index in range(153):
            (repository / f"context_{index:03d}_captured_repository_dependency_manifest.txt").write_text("stable context\n")
        _run_test_git(git, "-C", str(repository), "add", ".")
        _run_test_git(git, "-C", str(repository), "commit", "-m", "whole repository fixture")
    catalog = "python.scientific" if large else "python.cli"
    template["routing_overrides"].append(
        {
            "catalog_id": catalog,
            "disposition": "selected",
            "reason": "Owned contracts",
            "applicability_evidence": owned,
            "owners": ["python"],
            "review_surface": owned,
        }
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    skill = "python-scientific-review" if large else "python-cli-review"
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["skill_id"] == skill)
    owned = entry["dispatch"]["owned_paths"]
    payload = _payload(owned)
    payload["coverage_units"] = [
        {"unit_id": path, "owned_paths": [path], "dependency_paths": ["cliff.toml"], "dependency_uncertainty": "", "finding_indices": []} for path in owned
    ]
    payload["nearby_contract_owners"] = ["cliff.toml"]
    if caveat == "facts":
        payload["execution_facts"] = ["validators-not-executed", "source-captures-match", "git-not-mutated"]
        payload["commands_executed"] = [f"nl -ba {owned[0]}", shlex.join(entry["dispatch"]["worker_payload_persistence"]["publish_command"])]
    elif caveat == "unclassified":
        payload["limitations"] = ["No validators ran; a free-text caveat is not typed evidence."]
    elif caveat == "scope":
        payload.update(status="completed", files_inspected=owned[1:], scope_limitations=[{"path": owned[0], "reason": "Source unavailable"}])
    elif caveat == "uncertainty":
        payload["unresolved_uncertainties"] = [{"kind": "semantic", "reason": "The input contract is unresolved"}]
    elif caveat == "dependency":
        payload["coverage_units"][0]["dependency_uncertainty"] = "Unknown dynamic dependency"
    elif caveat in {"delegated", "unavailable", "failed"}:
        planned = entry["dispatch"]["command_policy"]["planned_validation_units"][0]
        requirement = planned["requirement_ids"][0]
        payload["validation_requirements"] = [
            {
                "requirement_id": requirement,
                "planned_validation_digest": planned["planned_validation_digest"],
                "owner": "review-validator",
                "reason": "Platform evidence",
                "expected_evidence": "Required checks pass",
            }
        ]
        payload["validation_limits"] = [
            {"requirement_id": requirement, "environment": "current host", "status": caveat, "reason": "Execution belongs to the validator"}
        ]
    if caveat == "no-partition":
        del payload["coverage_units"]
    dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
    content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    changed = owned[-1]
    (repository / changed).write_text("value = 2\n")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "planning_template": template,
        "authorization_before": "review-only",
        "authorization_after": "review-and-fix",
        "repair_epoch": 1,
        "changed_paths": [changed],
        "artifact_store": str(tmp_path / "repair"),
        "state_verification_command": "capture_scope.py --mode baseline",
        "sources": [{key: entry[key] for key in ("artifact_path", "metadata_path")}],
    }
    return request, entry, payload


def _compile_args(result: dict[str, Any], entry: dict[str, Any], output: Path) -> list[str]:
    return [
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
        str(output),
    ]


def test_large_recheck_publishes_retries_and_finalizes_without_expanding_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: PLR0915 - complete publication/recovery/finalization regression.
    request, original, _original_payload = _audit_request(tmp_path, large=True)
    result = runtime.advance_after_mutation(request)
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == original["dispatch"]["skill_id"])
    context = entry["dispatch"]["coverage_reuse"]
    assert len(context["origin"]["repository_path_fingerprints"]) >= 180
    assert len(json.dumps(context, separators=(",", ":")).encode()) > MAX_NATIVE_SECTION_BYTES
    assert sum(unit["disposition"] == "reused" for unit in context["units"]) == 22
    assert sum(unit["disposition"] == "recheck" for unit in context["units"]) == 1
    payload = _payload(request["changed_paths"])
    payload_bytes = json.dumps(payload).encode()
    _publish_worker_bytes(entry, payload_bytes)
    original_bytes = Path(original["artifact_path"]).read_bytes()
    args = _compile_args(result, entry, tmp_path / "compiled.json")
    write_once = runtime._write_bytes_atomically_once

    def fail_metadata(path: Path, content: bytes, *, mode: int = 0o444) -> bool:
        if str(path) == entry["metadata_path"]:
            message = "fixture metadata publication interrupted"
            raise OSError(message)
        return write_once(path, content, mode=mode)

    with monkeypatch.context() as patch:
        patch.setattr(runtime, "_write_bytes_atomically_once", fail_metadata)
        assert runtime.main(args) == 2
    assert Path(entry["worker_payload_path"]).read_bytes() == payload_bytes
    assert not Path(entry["artifact_path"]).exists()
    assert not Path(entry["metadata_path"]).exists()
    assert runtime.main(args) == 0
    native = Path(entry["artifact_path"]).read_text()
    scope = native.split("## Scope Inspected\n", 1)[1].split("## Findings\n", 1)[0]
    assert len(scope.encode()) < 4096
    assert "Coverage reuse reference:" in scope
    metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
    assert metadata["expectation"]["coverage_reuse"] == context
    assert metadata["normalized_record"]["coverage_reuse"] == context
    assert Path(metadata["worker_payload_path"]).read_bytes() == payload_bytes
    source = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    assert runtime._load_evidence_source(source, require_normalized=True)[4] == metadata["normalized_record"]
    sources = [source]
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    journal = Path(result["journal_path"])
    for other in result["dispatch_set"]["dispatches"]:
        if other["node_id"] == entry["node_id"]:
            continue
        if other["dispatch"].get("mode") == "synthesis":
            bundle = runtime.build_synthesis_bundle({**lifecycle, "sources": sources})
            dispatch = {**other["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"], "synthesis_bundle": bundle}
            content, sidecar = runtime.compile_review({"dispatch": dispatch, "payload": _synthesis_payload(dispatch, bundle)})
            Path(other["artifact_path"]).write_bytes(content)
            Path(other["metadata_path"]).write_text(json.dumps(sidecar))
            other_source = {key: other[key] for key in ("artifact_path", "metadata_path")}
            runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(other["node_id"], "accepted", source=other_source))
            sources.append(other_source)
        else:
            sources.append(_compile_repair_fixture_entry(other, lifecycle, journal))
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
                result["journal_path"],
                "--current-capture",
                result["capture_path"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    final = json.loads(output.read_bytes())
    assert final["graph_proof_status"] == "complete", final["blockers"]
    assert Path(original["artifact_path"]).read_bytes() == original_bytes
    tampered = deepcopy(metadata)
    tampered["expectation"]["coverage_reuse"]["units"][0]["dependency_paths"].append("missing.py")
    Path(entry["metadata_path"]).chmod(0o644)
    Path(entry["metadata_path"]).write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="verified unit decisions"):
        runtime._load_evidence_source(source, require_normalized=True)


@pytest.mark.parametrize(
    ("caveat", "category"),
    [
        ("facts", "verified"),
        ("delegated", "verified"),
        ("unclassified", "unclassified-limitations"),
        ("scope", "coverage-limitations"),
        ("uncertainty", "unresolved-uncertainty"),
        ("dependency", "dependency-uncertainty"),
        ("unavailable", "validation-evidence-limits"),
        ("failed", "validation-evidence-limits"),
        ("no-partition", "no-coverage-partition"),
    ],
)
def test_typed_caveats_control_unit_reuse_and_explain_rejections(tmp_path: Path, caveat: str, category: str) -> None:
    request, original, payload = _audit_request(tmp_path, caveat=caveat)
    result = runtime.advance_after_mutation(request)
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == original["dispatch"]["skill_id"])
    decision = next(item for item in result["coverage_reuse_decisions"] if item["node_id"] == entry["node_id"])
    assert ("coverage_reuse" in entry["dispatch"]) == (category == "verified")
    assert category in {unit["reason_code"] for unit in decision["units"]} or decision["reason_code"] == category
    record = json.loads(Path(original["metadata_path"]).read_bytes())["normalized_record"]
    for field in ("execution_facts", "validation_limits", "unresolved_uncertainties", "scope_limitations", "limitations"):
        if field in payload:
            assert record[field] == payload[field]
    if category == "verified":
        planned = entry["dispatch"]["command_policy"]["planned_validation_units"]
        digests = {requirement: unit["planned_validation_digest"] for unit in planned for requirement in unit["requirement_ids"]}
        updated = {
            **_payload(request["changed_paths"]),
            "validation_requirements": [{**item, "planned_validation_digest": digests[item["requirement_id"]]} for item in payload["validation_requirements"]],
        }
        state = result["new_source_state"]
        _content, metadata = runtime.compile_review({"dispatch": {**entry["dispatch"], "before_state": state, "after_state": state}, "payload": updated})
        inherited = metadata["normalized_record"]["inherited_audit_context"]
        assert inherited["evidence_id"] == record["evidence_id"]
        assert inherited == {"evidence_id": record["evidence_id"], **{key: payload[key] for key in ("execution_facts", "validation_limits") if key in payload}}


def test_saved_payload_compiles_unchanged_and_legacy_native_proof_still_verifies(tmp_path: Path) -> None:
    request, original, _payload_before = _audit_request(tmp_path)
    result = runtime.advance_after_mutation(request)
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == original["dispatch"]["skill_id"])
    saved_dispatch = Path(result["dispatches_path"]).read_bytes()
    # Model a publication made under the previous contract, before preflight existed.
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    del contract["compiler_preflight"]
    payload_bytes = json.dumps(_payload(request["changed_paths"])).encode()
    receipt = runtime.publish_worker_payload_bytes(contract, payload_bytes)
    assert receipt["artifact_write_review"]["audit_path_roles"]["omitted_dispatch_owned_paths"] == []
    assert runtime.main(_compile_args(result, entry, tmp_path / "compiled.json")) == 0
    assert Path(entry["worker_payload_path"]).read_bytes() == payload_bytes
    assert Path(result["dispatches_path"]).read_bytes() == saved_dispatch
    source = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    _kind, _expectation, _evidence, content, record = runtime._load_evidence_source(source, require_normalized=True)
    assert record is not None
    context = entry["dispatch"]["coverage_reuse"]
    legacy = "- Coverage reuse: " + json.dumps(context, sort_keys=True, separators=(",", ":"))
    native = content.decode()
    reference = next(line for line in native.splitlines() if line.startswith("- Coverage reuse reference:"))
    metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
    for replacement, valid in ((legacy, True), (reference.replace('"reused_units":1', '"reused_units":2'), False)):
        rewritten = native.replace(reference, replacement).encode()
        digest = "sha256:" + hashlib.sha256(rewritten).hexdigest()
        changed = deepcopy(metadata)
        changed["artifact_digest"] = digest
        changed["evidence"]["raw_result_digest"] = digest
        changed["normalized_record"]["artifact_digest"] = digest
        for path, data in ((entry["artifact_path"], rewritten), (entry["metadata_path"], json.dumps(changed).encode())):
            Path(path).chmod(0o644)
            Path(path).write_bytes(data)
        if valid:
            assert runtime._load_evidence_source(source, require_normalized=True)[4] == {**record, "artifact_digest": digest}
        else:
            with pytest.raises(ValueError, match="Coverage reuse"):
                runtime._load_evidence_source(source, require_normalized=True)


def test_oversized_payload_and_modified_preflight_fail_before_publication(tmp_path: Path) -> None:
    _document, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    payload = {**_payload(entry["dispatch"]["owned_paths"]), "limitations": ["x" * MAX_NATIVE_SECTION_BYTES]}
    with pytest.raises(ValueError, match=r"preflight.*maximum size"):
        runtime.review_worker_payload_write(contract, json.dumps(payload).encode())
    assert not Path(entry["worker_payload_path"]).exists()
    changed = {**contract, "compiler_preflight": {**contract["compiler_preflight"], "digest": "sha256:" + "0" * 64}}
    with pytest.raises(ValueError, match="preflight worker input digest"):
        runtime.review_worker_payload_write(changed, json.dumps(_payload(entry["dispatch"]["owned_paths"])).encode())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("execution_facts", ["unknown-fact"], "schema"),
        ("execution_facts", ["validators-not-executed"], "planned validator command ledger"),
        (
            "validation_limits",
            [{"requirement_id": "missing", "environment": "other host", "status": "delegated", "reason": "Evidence pending"}],
            "explicit validation_requirements",
        ),
        ("unresolved_uncertainties", [{"kind": "unknown", "reason": "unclear"}], "schema"),
    ],
)
def test_unclassified_or_false_typed_context_cannot_authorize_publication(tmp_path: Path, field: str, value: Any, message: str) -> None:
    document, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    payload = {**_payload(entry["dispatch"]["owned_paths"]), field: value}
    if value == ["validators-not-executed"]:
        payload["commands_executed"] = [entry["dispatch"]["command_policy"]["prohibited_commands"][0]]
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    with pytest.raises(ValueError, match=message):
        runtime.review_worker_payload_write(contract, json.dumps(payload).encode())
    dispatch: dict[str, Any] = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    with pytest.raises(ValueError, match=message):
        runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert not Path(entry["worker_payload_path"]).exists()


@pytest.mark.parametrize("fact", ["source-captures-match", "git-not-mutated"])
def test_execution_fact_contradicting_capture_or_mutation_is_rejected(tmp_path: Path, fact: str) -> None:
    document, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    dispatch: dict[str, Any] = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    if fact == "source-captures-match":
        dispatch["after_state"] = ["changed", *dispatch["after_state"][1:]]
    else:
        dispatch["git_mutated"] = True
    with pytest.raises(ValueError, match="contradicts"):
        runtime.compile_review({"dispatch": dispatch, "payload": {**_payload(dispatch["owned_paths"]), "execution_facts": [fact]}})


def test_authorized_validator_execution_still_contradicts_nonexecution_fact(tmp_path: Path) -> None:
    document, entries = _worker_input_fixture(tmp_path)
    original = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    command = original["dispatch"]["command_policy"]["validator_owned_commands"][0]
    authorized = runtime.materialize_dispatches(
        {**document, "artifact_store": str(tmp_path / "authorized"), "duplicate_command_authorizations": {original["node_id"]: [command]}}
    )
    entry = next(item for item in authorized["dispatches"] if item["node_id"] == original["node_id"])
    assert command not in entry["dispatch"]["command_policy"]["prohibited_commands"]
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    payload = {**_payload(dispatch["owned_paths"]), "commands_executed": [command]}
    assert runtime.review_worker_payload_write(contract, json.dumps(payload).encode())["decision"] == "valid-bound-artifact-write"
    _content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["normalized_record"]["commands_executed"] == [command]
    payload["execution_facts"] = ["validators-not-executed"]
    with pytest.raises(ValueError, match="planned validator command ledger"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    with pytest.raises(ValueError, match="planned validator command ledger"):
        runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert not Path(entry["worker_payload_path"]).exists()


@pytest.mark.parametrize(
    ("field", "status"), [("unresolved_uncertainties", "semantic"), *(("validation_limits", status) for status in ("delegated", "unavailable", "failed"))]
)
def test_multiline_audit_reason_is_rejected_at_every_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, status: str) -> None:
    document, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    payload = _payload(entry["dispatch"]["owned_paths"])
    reason = "Evidence is incomplete\nAdditional explanation"
    if field == "unresolved_uncertainties":
        payload[field] = [{"kind": status, "reason": reason}]
    else:
        planned = entry["dispatch"]["command_policy"]["planned_validation_units"][0]
        requirement = planned["requirement_ids"][0]
        payload["validation_requirements"] = [
            {
                "requirement_id": requirement,
                "planned_validation_digest": planned["planned_validation_digest"],
                "owner": "review-validator",
                "reason": "Platform checks",
                "expected_evidence": "Checks pass",
            }
        ]
        payload[field] = [{"requirement_id": requirement, "environment": "current host", "status": status, "reason": reason}]
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    # Model evidence accepted by the previous compiler before this boundary check.
    with monkeypatch.context() as patch:
        patch.setattr(runtime, "_validate_audit_caveats", lambda _dispatch, _payload: None)
        content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="reason must be one non-empty line"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    with pytest.raises(ValueError, match="reason must be one non-empty line"):
        runtime.compile_review({"dispatch": dispatch, "payload": payload})
    with pytest.raises(ValueError, match="reason must be one non-empty line"):
        runtime._load_evidence_source({key: entry[key] for key in ("artifact_path", "metadata_path")}, require_normalized=True)
    assert not Path(entry["worker_payload_path"]).exists()
