"""Worker-visible shapes and publication bindings agree with native compilation."""

import json
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_benchmark import benchmark_fixture
from review_graph_plan import ValidationArtifact, plan_from_document
from test_review_graph_compact import _publish
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _compact_audit_payload,
    _compile_materialized_evidence,
    _execution_payload,
    _json_plan,
    _run_test_git,
    _sparse_plan,
    _sparse_plan_document,
    _worker_input_fixture,
)
from test_review_graph_transitions import _synthesis_payload


@pytest.fixture
def dispatch_set(tmp_path: Path) -> dict[str, Any]:
    document = benchmark_fixture(tmp_path / "repository")
    return runtime.materialize_dispatches({**document, "artifact_store": str(tmp_path / "proof")})


def test_optional_coverage_shape_publishes_and_compiles_first_attempt(dispatch_set: dict[str, Any]) -> None:
    materialized = dispatch_set
    entry = next(item for item in materialized["dispatches"] if item["dispatch"].get("mode") == "audit")
    dispatch = entry["dispatch"]
    schema = dispatch["payload_schema"]
    assert "coverage_units" not in schema["required_fields"]
    shape = schema["optional_shapes"]["coverage_units"][0]
    assert len(json.dumps(schema["optional_shapes"]).encode()) < 400
    payload = _compact_audit_payload(entry)
    payload.update(
        status="completed",
        nearby_contract_owners=["tests/context.py"],
        findings=[{"severity": "P3", "location": dispatch["owned_paths"][0] + ":1", "summary": "Fixture finding", "evidence": "Fixture", "remediation": "Fix"}],
        coverage_units=[dict.fromkeys(shape)],
    )
    payload["coverage_units"][0].update(
        unit_id="contract",
        owned_paths=dispatch["owned_paths"],
        dependency_paths=payload["nearby_contract_owners"],
        dependency_uncertainty="",
        finding_indices=[1],
    )
    receipt = _publish(entry, payload)
    dispatch = {**dispatch, "before_state": materialized["source_state"], "after_state": materialized["source_state"]}
    _content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["normalized_record"]["coverage_units"] == payload["coverage_units"]
    assert receipt["worker_payload_path"] == entry["worker_payload_path"]


@pytest.mark.parametrize("damage", ["missing-uncertainty", "missing-context", "zero-index", "missing-owned"])
def test_optional_coverage_remains_strict(dispatch_set: dict[str, Any], damage: str) -> None:
    materialized = dispatch_set
    entry = next(item for item in materialized["dispatches"] if item["dispatch"].get("mode") == "audit")
    payload = _compact_audit_payload(entry)
    payload["nearby_contract_owners"] = ["tests/context.py"]
    unit = {
        "unit_id": "contract",
        "owned_paths": entry["dispatch"]["owned_paths"],
        "dependency_paths": ["tests/context.py"],
        "dependency_uncertainty": "",
        "finding_indices": [],
    }
    payload["coverage_units"] = [unit]
    if damage == "missing-uncertainty":
        del unit["dependency_uncertainty"]
    elif damage == "missing-context":
        unit["dependency_paths"] = []
    elif damage == "zero-index":
        unit["finding_indices"] = [0]
    else:
        unit["owned_paths"] = unit["owned_paths"][:1]
    with pytest.raises(ValueError, match=r"dependency_uncertainty|dependency|at least 1|partition"):
        _publish(entry, payload)
    assert not Path(entry["worker_payload_path"]).exists()


def _validation_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document, _entries = _worker_input_fixture(tmp_path / "original")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".gitignore").write_text("target/\n")
    git = shutil.which("git")
    assert git is not None
    _run_test_git(git, "init", str(repository))
    _run_test_git(git, "-C", str(repository), "add", ".gitignore")
    effects = tmp_path / "effects"
    artifacts = (
        ValidationArtifact("target", "build", "ignored", "repository-rule", status_rule=".gitignore:target/"),
        ValidationArtifact(str(effects), "log", "outside-repository", "isolated-output-directory"),
    )
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=artifacts)
    plan = replace(plan, coalesced_validation_units=(unit,))
    materialized = runtime.materialize_dispatches(
        {**document, "plan": _json_plan(plan), "repository_root": str(repository), "artifact_store": str(tmp_path / "proof")}
    )
    entry = next(item for item in materialized["dispatches"] if item["result_contract"] == "compact-validation")
    before = runtime.capture_workspace_snapshot(entry["dispatch"])["records"]
    (repository / "target").mkdir()
    (repository / "target" / "coverage.xml").write_text("<coverage/>\n")
    effects.mkdir()
    (effects / "run.log").write_text("passed\n")
    after = runtime.capture_workspace_snapshot(entry["dispatch"])["records"]
    dispatch = {
        **entry["dispatch"],
        "before_state": document["source_state"],
        "after_state": document["source_state"],
        "workspace_before": before,
        "workspace_after": after,
    }
    return entry, dispatch


@pytest.mark.parametrize("references", ["roots", "children", "unknown", "absent", "empty"])
def test_validation_artifact_references_agree_before_and_after_publication(tmp_path: Path, references: str) -> None:
    entry, dispatch = _validation_fixture(tmp_path)
    payload = _execution_payload(entry, "passed", 0, "1s")
    roots = [artifact["path"] for artifact in dispatch["validation_unit"]["allowed_artifacts"]]
    paths = {"roots": roots, "children": ["target/coverage.xml", roots[1] + "/run.log"], "unknown": ["unplanned.log"], "absent": roots, "empty": []}
    payload["executions"][0].update(artifact_paths=paths[references], evidence="Coverage is recorded in target/coverage.xml; timing is in effects/run.log.")
    if references == "absent":
        shutil.rmtree(tmp_path / "repository" / "target")
        shutil.rmtree(tmp_path / "effects")
        absent = runtime.capture_workspace_snapshot(entry["dispatch"])["records"]
        dispatch.update(workspace_before=absent, workspace_after=absent)
    if references in {"roots", "empty"}:
        _publish(entry, payload)
        _content, metadata = runtime.compile_validation({"dispatch": dispatch, "payload": payload})
        assert metadata["normalized_record"]["executions"] == payload["executions"]
    else:
        with pytest.raises(ValueError, match="absent outputs" if references == "absent" else "permitted roots") as error:
            _publish(entry, payload)
        if references != "absent":
            assert all(root in str(error.value) for root in roots)
        assert not Path(entry["worker_payload_path"]).exists()
        with pytest.raises(ValueError, match="absent outputs" if references == "absent" else "permitted roots"):
            runtime.compile_validation({"dispatch": dispatch, "payload": payload})
        # A reference-only correction keeps commands, timing, evidence and snapshots.
        corrected = deepcopy(payload)
        corrected["executions"][0]["artifact_paths"] = [] if references == "absent" else roots
        _publish(entry, corrected)
        _content, metadata = runtime.compile_validation({"dispatch": dispatch, "payload": corrected})
        assert metadata["normalized_record"]["executions"] == corrected["executions"]
        assert {key: value for key, value in corrected["executions"][0].items() if key != "artifact_paths"} == {
            key: value for key, value in payload["executions"][0].items() if key != "artifact_paths"
        }


def _synthesis_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _plan, _sources = _compile_materialized_evidence(tmp_path / "proof", reference_planned_validation=True)
    entry = json.loads((tmp_path / "proof" / "rust-synthesis.worker-input.json").read_bytes())
    dispatch = entry["dispatch"]
    bundle = runtime._synthesis_publication_bundle(dispatch)
    payload = _synthesis_payload(dispatch, bundle)
    needs = [need for record in bundle["records"] for need in record.get("validation_requirements", [])]
    assert len(needs) > 1
    assert len({need["requirement_id"] for need in needs}) == 1
    merged = deepcopy(needs[0])
    merged.update(owner="; ".join(need["owner"] for need in needs), reason="; ".join(need["reason"] for need in needs))
    payload["validation_requirements"] = [merged]
    return entry, bundle, payload


def test_shared_validator_and_inherited_needs_publish_once(tmp_path: Path) -> None:
    entry, bundle, payload = _synthesis_fixture(tmp_path)
    assert len(payload["validation_reconciliation"]) == 1
    payload["limitations"] = entry["dispatch"]["synthesis_examples"]["unexecuted_platform"]["limitations"]
    receipt = _publish(entry, payload)
    dispatch = {**entry["dispatch"], "before_state": bundle["source_state"], "after_state": bundle["source_state"], "synthesis_bundle": bundle}
    _content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["evidence"]["status"] == "no-findings"
    assert receipt["worker_payload_path"] == entry["worker_payload_path"]
    assert len(metadata["normalized_record"]["validation_requirements"]) == 1


def test_synthesis_reports_all_binding_diagnostics_and_corrects_metadata_only(tmp_path: Path) -> None:
    entry, bundle, valid = _synthesis_fixture(tmp_path)
    invalid = deepcopy(valid)
    invalid["validation_requirements"] *= 2
    invalid["validation_reconciliation"] *= 2
    invalid["predecessor_coverage"][0]["disposition"] = "reused"
    with pytest.raises(ValueError, match="synthesis") as error:
        _publish(entry, invalid)
    diagnostic = str(error.value)
    assert "requirement IDs must be unique" in diagnostic
    assert "duplicate or unknown evidence" in diagnostic
    assert "disposition=accepted" in diagnostic
    assert not Path(entry["worker_payload_path"]).exists()
    before = {
        Path(source[key]): Path(source[key]).read_bytes() for source in entry["dispatch"]["synthesis_sources"] for key in ("artifact_path", "metadata_path")
    }
    _publish(entry, valid)
    assert all(path.read_bytes() == content for path, content in before.items())
    runtime.compile_review(
        {
            "dispatch": {**entry["dispatch"], "before_state": bundle["source_state"], "after_state": bundle["source_state"], "synthesis_bundle": bundle},
            "payload": valid,
        }
    )


def test_synthesis_rejects_hosted_rows_without_separate_evidence(tmp_path: Path) -> None:
    entry, _bundle, payload = _synthesis_fixture(tmp_path)
    hosted = {**payload["validation_reconciliation"][0], "platform": "hosted-linux", "execution_mode": "unexecuted"}
    payload["validation_reconciliation"].append(hosted)
    with pytest.raises(ValueError, match="synthesis") as error:
        _publish(entry, payload)
    assert "duplicate or unknown evidence" in str(error.value)
    assert "bound executor environment" in str(error.value)
    assert "validation gaps" in str(error.value)
    assert not Path(entry["worker_payload_path"]).exists()


def test_synthesis_publication_plan_cannot_be_replaced(tmp_path: Path) -> None:
    entry, _bundle, payload = _synthesis_fixture(tmp_path)
    plan_path = Path(entry["dispatch"]["synthesis_plan_reference"]["path"])
    plan_path.chmod(0o644)
    plan_path.write_text("{}")
    with pytest.raises(ValueError, match="plan digest differs"):
        _publish(entry, payload)
    assert not Path(entry["worker_payload_path"]).exists()


@pytest.mark.parametrize("unexecuted", [False, True])
def test_separate_hosted_evidence_and_required_unexecuted_matrix(tmp_path: Path, unexecuted: bool) -> None:
    document = _sparse_plan_document()
    hosted = {**document["validation_requirements"][0], "requirement_id": "hosted-linux", "platform": "linux-x64", "baseline": False}
    if unexecuted:
        hosted.update(commands=[], working_directories=[], canonical_recipe=None, planning_blocker="Hosted runner unavailable")
    document["validation_requirements"].append(hosted)
    plan = plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    hosted_unit = next(unit for unit in plan.coalesced_validation_units if "hosted-linux" in unit.requirement_ids)
    store = tmp_path / "proof"
    _compile_materialized_evidence(store, plan=plan, skip_node_ids=(hosted_unit.node_id,) if unexecuted else ())
    if unexecuted:
        validator = json.loads((store / f"{hosted_unit.node_id}.worker-input.json").read_bytes())
        dispatch = {
            **validator["dispatch"],
            "before_state": document["validation_requirements"][0]["source_state"],
            "after_state": document["validation_requirements"][0]["source_state"],
        }
        blocked = {"status": "blocked", "executions": [], "limitations": ["Hosted runner unavailable"]}
        content, metadata = runtime.compile_validation({"dispatch": dispatch, "payload": blocked})
        Path(validator["artifact_path"]).write_bytes(content)
        Path(validator["metadata_path"]).write_text(json.dumps(metadata))
    entry = json.loads((store / "repository-synthesis.worker-input.json").read_bytes())
    bundle = runtime._synthesis_publication_bundle(entry["dispatch"])
    payload = _synthesis_payload(entry["dispatch"], bundle)
    assert len(payload["validation_reconciliation"]) == 2
    assert {row["platform"] for row in payload["validation_reconciliation"]} == {"current host", "linux-x64"}
    if unexecuted:
        for row in payload["predecessor_coverage"]:
            if row["evidence_id"] == f"validation:{hosted_unit.node_id}":
                row["disposition"] = "blocked"
        next(row for row in payload["validation_reconciliation"] if row["platform"] == "linux-x64")["execution_mode"] = "unexecuted"
        with pytest.raises(ValueError, match="validation gaps"):
            _publish(entry, payload)
        payload.update(status="blocked", readiness_verdict="blocked", limitations=["Required hosted matrix remains unexecuted"])
    _publish(entry, payload)
    dispatch = {**entry["dispatch"], "before_state": bundle["source_state"], "after_state": bundle["source_state"], "synthesis_bundle": bundle}
    _content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["normalized_record"]["readiness_verdict"] == ("blocked" if unexecuted else "ready")
