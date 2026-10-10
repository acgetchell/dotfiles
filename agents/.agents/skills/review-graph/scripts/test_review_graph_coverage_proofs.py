"""External reuse proofs, compact execution views, and fixed dispatch measurements."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_coverage import coverage_execution_view
from review_graph_integrity import canonical_json, digest_bytes
from review_graph_plan import plan_from_document
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _complete_structural_fixture_routing,
    _run_test_git,
    _set_fixture_routing,
)
from test_review_graph_transitions import _materialize, _payload


def _proof_fixture(tmp_path: Path, *, validation_change: str | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Recheck one test while reusing its configuration in a 100-path repository."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    owned = ["pyproject.toml", "tests/tooling/test_adoption.py"]
    (repository / "tests/tooling").mkdir(parents=True)
    (repository / owned[0]).write_text('[project]\nname = "fixture"\nversion = "0.1.0"\n')
    (repository / owned[1]).write_text("def test_adoption():\n    assert True\n")
    (repository / "AGENTS.md").write_text("# Instructions\n\nInspect test contracts.\n")
    for index in range(92):
        (repository / f"unrelated_{index:03d}.txt").write_text("Unrelated captured input.\n")
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "fixed coverage fixture")
    template["consulted_routers"].append("docs-review-orchestrator")
    _set_fixture_routing(
        template,
        {
            "catalog_id": "python.tests",
            "disposition": "selected",
            "reason": "Test and configuration contracts",
            "applicability_evidence": owned,
            "owners": ["python"],
            "review_surface": owned,
        },
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    fresh = next(entry for entry in entries["dispatches"] if entry["dispatch"]["skill_id"] == "python-test-quality")
    validation = fresh["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload = {
        **_payload(owned),
        "status": "completed",
        "nearby_contract_owners": ["cliff.toml"],
        "coverage_units": [
            {"unit_id": "configuration", "owned_paths": [owned[0]], "dependency_paths": ["cliff.toml"], "dependency_uncertainty": "", "finding_indices": [1]},
            {"unit_id": "adoption-tests", "owned_paths": [owned[1]], "dependency_paths": [owned[0]], "dependency_uncertainty": "", "finding_indices": [2]},
        ],
        "findings": [
            {
                "severity": "P2",
                "location": f"{path}:1",
                "summary": summary,
                "evidence": "Seeded fixture observation.",
                "remediation": "Add the missing test contract.",
            }
            for path, summary in zip(owned, ("Configuration omits test discovery", "Test omits failure assertion"), strict=True)
        ],
        "validation_requirements": [
            {
                "requirement_id": validation["requirement_ids"][0],
                "planned_validation_digest": validation["planned_validation_digest"],
                "owner": "review-validator",
                "reason": "Run the fixture's required validation",
                "expected_evidence": "Checks pass",
            }
        ],
        "handoffs": [{"catalog_id": "python.build", "observed_trigger": "Test configuration", "reason": "Check installation", "scope": owned}],
    }
    content, metadata = runtime.compile_review(
        {"dispatch": {**fresh["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(fresh["artifact_path"]).write_bytes(content)
    Path(fresh["metadata_path"]).write_text(json.dumps(metadata))
    if validation_change == "renamed-requirement":
        template["validation_requirements"][0]["requirement_id"] += "-replacement"
    elif validation_change == "environment":
        template["validation_requirements"][0]["environment"] += "; changed executor"
    (repository / owned[1]).write_text("def test_adoption():\n    assert 1 == 1\n")
    result = runtime.advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": [owned[1]],
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "sources": [{key: fresh[key] for key in ("artifact_path", "metadata_path")}],
        }
    )
    partial = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["skill_id"] == "python-test-quality")
    validation = partial["dispatch"]["command_policy"]["planned_validation_units"][0]
    updated = {
        **_payload([owned[1]]),
        "status": "completed",
        "findings": payload["findings"][1:],
        "nearby_contract_owners": [owned[0]],
        "validation_requirements": [{**payload["validation_requirements"][0], "planned_validation_digest": validation["planned_validation_digest"]}],
        "handoffs": payload["handoffs"],
    }
    return fresh, partial, result, updated


def _compile(entry: dict[str, Any], result: dict[str, Any], payload: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    state = result["new_source_state"]
    return runtime.compile_review({"dispatch": {**entry["dispatch"], "before_state": state, "after_state": state}, "payload": payload})


@pytest.mark.parametrize("change", ["renamed-requirement", "environment"])
def test_changed_validation_contract_requires_fresh_partitioned_audit(tmp_path: Path, change: str) -> None:
    fresh, replacement, result, _partial_payload = _proof_fixture(tmp_path, validation_change=change)
    original = {key: Path(fresh[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    assert not replacement["dispatch"].get("coverage_reuse")
    decision = next(item for item in result["coverage_reuse_decisions"] if item["node_id"] == replacement["dispatch"]["node_id"])
    assert decision["reason_code"] == "validation-requirements-changed"
    validation = replacement["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload = {
        **_payload(["pyproject.toml", "tests/tooling/test_adoption.py"]),
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
    fresh, partial, result, payload = _proof_fixture(tmp_path)
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
    }
    assert sizes["partial_worker_input_bytes"] < sizes["partial_inline_comparison_bytes"] * 0.6
    assert sizes["partial_worker_input_bytes"] < sizes["fresh_worker_input_bytes"] + 6500
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


@pytest.mark.parametrize("tamper", ["missing", "bytes", "symlink"])
def test_missing_or_altered_external_proof_blocks_publication_compilation_and_verification(tmp_path: Path, tamper: str) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path)
    content, metadata = _compile(partial, result, payload)
    Path(partial["artifact_path"]).write_bytes(content)
    Path(partial["metadata_path"]).write_text(json.dumps(metadata))
    proof_path = Path(partial["dispatch"]["coverage_reuse"]["proof_reference"]["path"])
    proof_bytes = proof_path.read_bytes()
    proof_path.unlink()
    if tamper == "bytes":
        proof_path.write_bytes(proof_bytes + b"\n")
    elif tamper == "symlink":
        substitute = tmp_path / "substitute.json"
        substitute.write_bytes(proof_bytes)
        proof_path.symlink_to(substitute)
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    message = "coverage proof digest|regular non-symlink file"
    with pytest.raises(ValueError, match=message):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert not Path(partial["worker_payload_path"]).exists()
    with pytest.raises(ValueError, match=message):
        _compile(partial, result, payload)
    with pytest.raises(ValueError, match=message):
        runtime._load_evidence_source(partial, require_normalized=True)
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    with pytest.raises(ValueError, match=message):
        runtime.next_ready_nodes({**lifecycle, "current_source_state": result["new_source_state"]}, dispatch_set=result["dispatch_set"], journal_events=())


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
    dispatches = result["dispatch_set"]
    dispatches["dispatch_set_digest"] = digest_bytes(canonical_json({key: value for key, value in dispatches.items() if key != "dispatch_set_digest"}).encode())
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    with pytest.raises(ValueError, match="dispatch coverage proof differs from its bound plan"):
        runtime.next_ready_nodes({**lifecycle, "current_source_state": result["new_source_state"]}, dispatch_set=dispatches, journal_events=())
    assert not Path(partial["worker_payload_path"]).exists()
