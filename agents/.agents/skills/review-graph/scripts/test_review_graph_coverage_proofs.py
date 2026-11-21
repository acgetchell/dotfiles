"""External reuse proofs, compact execution views, and fixed dispatch measurements."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import review_graph_runtime as runtime
from review_graph_coverage import coverage_execution_view
from review_graph_integrity import canonical_json, digest_bytes
from review_graph_views import execution_view_bytes
from test_support_review_graph_evidence import _payload
from test_support_review_graph_reuse import _compile, _proof_fixture


def test_repair_then_staging_reports_discarded_partial_coverage(tmp_path: Path) -> None:
    _fresh, replacement, result, _partial_payload = _proof_fixture(tmp_path, stage_after_repair=True)
    assert "coverage_reuse" not in replacement["dispatch"]
    node_id = replacement["node_id"]
    decision = next(item for item in result["coverage_reuse_decisions"] if item["node_id"] == node_id)
    assert decision["units"]
    assert all(unit["disposition"] == "recheck" for unit in decision["units"])
    assert all(unit["reason_code"] == "metadata-dependencies-changed" for unit in decision["units"])
    assert decision["reason_code"] == "metadata-dependencies-changed"
    assert next(item for item in result["node_decisions"] if item["node_id"] == node_id)["disposition"] == "recheck"
    history = json.loads(Path(result["repair_transition_path"]).read_text())
    original = next(item for item in history["coverage_reuse_decisions"] if item["node_id"] == node_id)
    assert [(unit["unit_id"], unit["disposition"]) for unit in original["units"]] == [("configuration", "reused"), ("adoption-tests", "recheck")]


@pytest.mark.parametrize("change", ["renamed-requirement", "environment"])
def test_changed_validation_contract_requires_fresh_partitioned_audit(tmp_path: Path, change: str) -> None:
    fresh, replacement, result, _partial_payload = _proof_fixture(tmp_path, validation_change=change)
    original = {key: Path(fresh[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    assert not replacement["dispatch"].get("coverage_reuse")
    decision = next(item for item in result["coverage_reuse_decisions"] if item["node_id"] == replacement["dispatch"]["node_id"])
    assert decision["reason_code"] == "validation-requirements-changed"
    validation = replacement["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload = {
        **_payload(["pyproject.toml", "tests/tooling/test_adoption.py"], dispatch=replacement["dispatch"]),
        "validation_requirements": [
            {
                "requirement_id": validation["requirement_ids"][0],
                "planned_validation_digest": validation["planned_validation_digest"],
                "owner": "review-validator",
                "reason": "Delegate the current execution contract",
                "expected_evidence": "Checks pass",
            }
        ],
    }
    contract = json.loads(Path(replacement["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    _content, metadata = _compile(replacement, result, payload)
    assert metadata["normalized_record"]["validation_requirements"] == payload["validation_requirements"]
    assert {key: Path(fresh[key]).read_bytes() for key in original} == original


def test_fixed_partial_recheck_dispatch_bytes_and_seeded_findings(tmp_path: Path) -> None:
    fresh, partial, result, payload = _proof_fixture(tmp_path, unrelated_paths=92)
    view = partial["dispatch"]["coverage_reuse"]
    proof_path = Path(view["proof_reference"]["path"])
    proof = runtime._coverage_proof(view)
    assert proof_path.stat().st_mode & 0o777 == 0o444
    assert len(proof["origin"]["repository_path_fingerprints"]) == len(proof["target"]["repository_path_fingerprints"]) == 100
    assert [(unit["owned_paths"], unit["disposition"]) for unit in view["units"]] == [
        (["pyproject.toml"], "reused"),
        (["tests/tooling/test_adoption.py"], "recheck"),
    ]
    for path in (partial["worker_input_path"], partial["worker_payload_contract_path"]):
        worker_text = Path(path).read_text()
        assert "repository_path_fingerprints" not in worker_text
        assert "unrelated_000.txt" not in worker_text
    inline = {**partial, "dispatch": {**partial["dispatch"], "coverage_reuse": proof}}
    sizes = {
        "fresh_worker_input_bytes": Path(fresh["worker_input_path"]).stat().st_size,
        "partial_worker_input_bytes": Path(partial["worker_input_path"]).stat().st_size,
        "partial_inline_comparison_bytes": len((json.dumps(inline, indent=2, sort_keys=True) + "\n").encode()),
        "full_proof_bytes": proof_path.stat().st_size,
        "execution_view_bytes": len(canonical_json(view).encode()),
        "partial_publication_contract_bytes": Path(partial["worker_payload_contract_path"]).stat().st_size,
        "additional_isolation_bytes": len(json.dumps(partial["dispatch"]["fresh_context_forbidden_artifacts"], indent=2).encode())
        - len(json.dumps(fresh["dispatch"]["fresh_context_forbidden_artifacts"], indent=2).encode()),
    }
    assert sizes["partial_worker_input_bytes"] < sizes["partial_inline_comparison_bytes"] * 0.6
    # Repair-prefixed node names expand the required peer-artifact boundary.
    # Preserve the existing budget for the coverage transport itself.
    assert sizes["partial_worker_input_bytes"] < sizes["fresh_worker_input_bytes"] + sizes["additional_isolation_bytes"] + 6500
    assert sizes["execution_view_bytes"] < sizes["full_proof_bytes"] * 0.2
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    receipt = runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert receipt["artifact_write_review"]["audit_path_roles"]["runtime_reused_paths"] == ["pyproject.toml"]
    content, metadata = _compile(partial, result, payload)
    record = metadata["normalized_record"]
    assert [finding["summary"] for finding in record["findings"]] == ["Configuration omits test discovery", "Test omits failure assertion"]
    assert record["findings"][0]["source_findings"] == [
        {"evidence_id": fresh["dispatch"]["evidence_id"], "finding_id": view["original_findings"][0]["finding_id"]}
    ]
    assert record["coverage_reuse"]["original_findings"][1] == view["original_findings"][1]
    Path(partial["artifact_path"]).write_bytes(content)
    Path(partial["metadata_path"]).write_text(json.dumps(metadata))
    assert runtime._load_evidence_source(partial, require_normalized=True)[4] == record
    print(json.dumps({**sizes, "seeded_findings_retained": 2, "model_tokens": None, "model_cost": None, "model_review_seconds": None}, sort_keys=True))


@pytest.mark.parametrize("tamper", ["missing", "bytes", "relative-symlink", "absolute-symlink"])
def test_missing_or_altered_external_proof_blocks_publication_compilation_and_verification(tmp_path: Path, tamper: str) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path)
    content, metadata = _compile(partial, result, payload)
    Path(partial["artifact_path"]).write_bytes(content)
    Path(partial["metadata_path"]).write_text(json.dumps(metadata))
    compiled = {Path(partial[key]): Path(partial[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    proof_path = Path(partial["dispatch"]["coverage_reuse"]["proof_reference"]["path"])
    proof_bytes = proof_path.read_bytes()
    proof_path.unlink()
    substitute = tmp_path / "substitute.json"
    if tamper == "bytes":
        proof_path.write_bytes(proof_bytes + b"\n")
    elif tamper.endswith("symlink"):
        substitute.write_bytes(proof_bytes)
        target = substitute.relative_to(proof_path.parent, walk_up=True) if tamper == "relative-symlink" else substitute
        proof_path.symlink_to(target)
    invalid_bytes = proof_path.read_bytes() if proof_path.exists() else None
    link_target = proof_path.readlink() if proof_path.is_symlink() else None

    def assert_unchanged() -> None:
        """Compare published artifacts and the substituted proof with their state before the rejected operation."""
        assert not Path(partial["worker_payload_path"]).exists(follow_symlinks=False)
        assert all(not path.is_symlink() and path.read_bytes() == original for path, original in compiled.items())
        if link_target is not None:
            assert proof_path.is_symlink()
            assert proof_path.readlink() == link_target
            assert proof_path.samefile(substitute)
            assert substitute.read_bytes() == proof_bytes
        else:
            assert not proof_path.is_symlink()
        if invalid_bytes is None:
            assert not proof_path.exists(follow_symlinks=False)
        else:
            assert proof_path.read_bytes() == invalid_bytes

    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    message = "coverage proof digest|regular non-symlink file"
    with pytest.raises(ValueError, match=message):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert_unchanged()
    with pytest.raises(ValueError, match=message):
        _compile(partial, result, payload)
    assert_unchanged()
    with pytest.raises(ValueError, match=message):
        runtime._load_evidence_source(partial, require_normalized=True)
    assert_unchanged()
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    with pytest.raises(ValueError, match=message):
        runtime.next_ready_nodes({**lifecycle, "current_source_state": result["new_source_state"]}, dispatch_set=result["dispatch_set"], journal_events=())
    assert_unchanged()


@pytest.mark.parametrize("tamper", ["partition", "dependency", "instructions", "unsupported", "finding", "view", "mode"])
def test_rebinding_a_forged_proof_cannot_authorize_reuse(tmp_path: Path, tamper: str) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path)
    view = partial["dispatch"]["coverage_reuse"]
    proof = runtime._coverage_proof(view)
    if tamper == "partition":
        proof["units"][1]["disposition"] = "reused"
    elif tamper == "dependency":
        proof["units"][0]["dependency_paths"] = []
    elif tamper == "instructions":
        proof["instruction_digests"][0][1] = "sha256:" + "0" * 64
    elif tamper == "unsupported":
        proof["origin"]["repository_state_format"] = "unsupported"
    elif tamper == "finding":
        proof["original_findings"] = []
    elif tamper == "view":
        view["units"][1]["disposition"] = "reused"
    else:
        partial["dispatch"]["mode"] = "revalidation"
    if tamper not in {"view", "mode"}:
        proof_path = Path(view["proof_reference"]["path"])
        proof_bytes = canonical_json(proof).encode()
        proof_path.chmod(0o644)
        proof_path.write_bytes(proof_bytes)
        partial["dispatch"]["coverage_reuse"] = coverage_execution_view(proof, {"path": str(proof_path), "digest": digest_bytes(proof_bytes)})
    # Even matching wrapper digests cannot make the original partition support a forged claim.
    worker_input = Path(partial["worker_input_path"])
    worker_input.chmod(0o644)
    worker_input.write_text(json.dumps(partial))
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    contract.update(coverage_reuse=partial["dispatch"]["coverage_reuse"], mode=partial["dispatch"]["mode"])
    contract["compiler_preflight"]["digest"] = digest_bytes(worker_input.read_bytes())
    with pytest.raises(ValueError, match=r"verified unit decisions|audit mode|scope validation"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    with pytest.raises(ValueError, match=r"verified unit decisions|audit mode"):
        _compile(partial, result, payload)
    assert not Path(partial["worker_payload_path"]).exists()


@pytest.mark.parametrize("field", ["validation_requirements", "handoffs"])
def test_partial_publication_requires_inherited_obligations(tmp_path: Path, field: str) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path)
    payload[field] = []
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    with pytest.raises(ValueError, match="reconcile original validation requirements"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    with pytest.raises(ValueError, match="reconcile original validation requirements"):
        _compile(partial, result, payload)
    assert not Path(partial["worker_payload_path"]).exists()


def test_external_proof_requires_preflight_and_legacy_inline_evidence_remains_readable(tmp_path: Path) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path)
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    del contract["compiler_preflight"]
    with pytest.raises(ValueError, match="requires its bound compiler preflight"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    legacy = deepcopy(partial)
    legacy["dispatch"]["coverage_reuse"] = runtime._coverage_proof(legacy["dispatch"]["coverage_reuse"])
    content, metadata = _compile(legacy, result, payload)
    Path(legacy["artifact_path"]).write_bytes(content)
    Path(legacy["metadata_path"]).write_text(json.dumps(metadata))
    Path(partial["dispatch"]["coverage_reuse"]["proof_reference"]["path"]).unlink()
    assert runtime._load_evidence_source(legacy, require_normalized=True)[4] == metadata["normalized_record"]


@pytest.mark.parametrize("field", ["origin", "target", "artifact_digest", "instruction_digests", "metadata_transitions"])
def test_incomplete_rebound_proof_reports_input_error_without_publication(tmp_path: Path, capsys: pytest.CaptureFixture[str], field: str) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path)
    view = partial["dispatch"]["coverage_reuse"]
    proof = runtime._coverage_proof(view)
    del proof[field]
    proof_bytes = canonical_json(proof).encode()
    proof_path = Path(view["proof_reference"]["path"])
    proof_path.chmod(0o644)
    proof_path.write_bytes(proof_bytes)
    partial["dispatch"]["coverage_reuse"] = coverage_execution_view(proof, {"path": str(proof_path), "digest": digest_bytes(proof_bytes)})
    worker_input = Path(partial["worker_input_path"])
    worker_input.chmod(0o644)
    worker_input.write_text(json.dumps(partial))
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    contract["coverage_reuse"] = partial["dispatch"]["coverage_reuse"]
    contract["compiler_preflight"]["digest"] = digest_bytes(worker_input.read_bytes())
    with pytest.raises(ValueError, match=f"coverage proof {field}"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert not Path(partial["worker_payload_path"]).exists()

    state = result["new_source_state"]
    compiler_input = tmp_path / "compile-input.json"
    compiler_input.write_text(json.dumps({"dispatch": {**partial["dispatch"], "before_state": state, "after_state": state}, "payload": payload}))
    artifact, metadata = tmp_path / "rejected.md", tmp_path / "rejected.json"
    assert runtime.main(["compile-review", "--input", str(compiler_input), "--artifact", str(artifact), "--metadata", str(metadata)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert f"coverage proof {field}" in output.err
    assert "Traceback" not in output.err
    assert not artifact.exists()
    assert not metadata.exists()


@pytest.mark.parametrize("tamper", ["missing", "substituted"])
def test_self_consistent_dispatch_still_requires_its_planned_coverage(tmp_path: Path, tamper: str) -> None:
    _fresh, partial, result, _payload_after = _proof_fixture(tmp_path)
    if tamper == "missing":
        del partial["dispatch"]["coverage_reuse"]
    else:
        view = partial["dispatch"]["coverage_reuse"]
        proof = runtime._coverage_proof(view)
        proof["node_id"] = "another-audit"
        substitute = tmp_path / "substituted-proof.json"
        content = canonical_json(proof).encode()
        substitute.write_bytes(content)
        partial["dispatch"]["coverage_reuse"] = coverage_execution_view(proof, {"path": str(substitute), "digest": digest_bytes(content)})
        # The substituted projection and bytes agree; the unchanged plan must reject it.
        assert runtime._coverage_proof(partial["dispatch"]["coverage_reuse"]) == proof
    worker_input = Path(partial["worker_input_path"])
    worker_input.chmod(0o644)
    worker_input.write_text(json.dumps(partial, indent=2, sort_keys=True) + "\n")
    execution_view = Path(partial["worker_execution_path"])
    execution_view.chmod(0o644)
    execution_view.write_bytes(execution_view_bytes(partial, worker_input.read_bytes()))
    dispatches = result["dispatch_set"]
    dispatches["dispatch_set_digest"] = digest_bytes(canonical_json({key: value for key, value in dispatches.items() if key != "dispatch_set_digest"}).encode())
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    with pytest.raises(ValueError, match="dispatch coverage proof differs from its bound plan"):
        runtime.next_ready_nodes({**lifecycle, "current_source_state": result["new_source_state"]}, dispatch_set=dispatches, journal_events=())
    assert not Path(partial["worker_payload_path"]).exists()
