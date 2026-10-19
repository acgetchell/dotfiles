"""Source coverage never silently reconciles a newly executable validation contract."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from test_review_graph_coverage_proofs import _compile, _proof_fixture


def _judgment(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: candidate[key] for key in ("requirement_id", "original_planned_validation_digest", "replacement_planned_validation_digest")},
        "disposition": "source-independent",
        "contract_assessment": "The same just ci recipe now has an explicit repository directory and artifact contract; source judgments remain independent.",
        "native_limitations": "No previous pass is available; the current validator still owes execution and native CI remains required.",
        "handoff_assessment": "The original installation handoff remains applicable and is retained.",
    }


def test_commandless_recipe_requires_fresh_reassessment_before_accepting_source_reuse(tmp_path: Path) -> None:
    fresh, partial, result, payload = _proof_fixture(tmp_path, validation_change="commandless")
    context = partial["dispatch"].get("coverage_reuse")
    assert context is not None
    assert "validation_reassessments" in partial["dispatch"]["payload_schema"]["optional_shapes"]
    assert "validation_reassessments" not in fresh["dispatch"]["payload_schema"]["optional_shapes"]
    assert [(unit["unit_id"], unit["disposition"]) for unit in context["units"]] == [("configuration", "reused"), ("adoption-tests", "recheck")]
    candidate = context["validation_reassessment"][0]
    assert candidate["original_execution_identity"]["commands"] == []
    assert candidate["original_execution_identity"]["planning_blocker"] == "External CI has no retained log"
    assert candidate["replacement_execution_identity"]["commands"] == ["just ci"]
    original = {key: Path(fresh[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    with pytest.raises(ValueError, match="validation reassessment"):
        _compile(partial, result, payload)
    payload["validation_reassessments"] = [_judgment(candidate)]
    contract = json.loads(Path(partial["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    content, metadata = _compile(partial, result, payload)
    assert metadata["normalized_record"]["coverage_reuse"]["validation_reassessments"] == payload["validation_reassessments"]
    assert metadata["normalized_record"]["files_inspected"] == ["tests/tooling/test_adoption.py"]
    assert metadata["normalized_record"]["inherited_audit_context"]["validation_limits"][0]["status"] == "unavailable"
    assert metadata["normalized_record"]["handoffs"]
    assert len(result["new_plan"]["coalesced_validation_units"]) == 1
    assert result["new_plan"]["coalesced_validation_units"][0]["evidence_ids"] == ()
    Path(partial["artifact_path"]).write_bytes(content)
    Path(partial["metadata_path"]).write_text(json.dumps(metadata))
    runtime._load_evidence_source(partial, require_normalized=True)
    assert {key: Path(fresh[key]).read_bytes() for key in original} == original
    stale = deepcopy(payload)
    stale["validation_reassessments"][0]["replacement_planned_validation_digest"] = candidate["original_planned_validation_digest"]
    with pytest.raises(ValueError, match="exact old/new digests"):
        _compile(partial, result, stale)


@pytest.mark.parametrize("change", ["environment", "platform", "commands"])
def test_material_execution_change_requires_full_source_review(tmp_path: Path, change: str) -> None:
    _fresh, partial, result, _payload = _proof_fixture(tmp_path, validation_change="commandless-" + change)
    assert "coverage_reuse" not in partial["dispatch"]
    assert any(item.get("reason_code") == "validation-requirements-changed" for item in result["coverage_reuse_decisions"])


@pytest.mark.parametrize("damage", ["missing", "duplicate", "old-digest", "empty-reason", "reinspect", "uncertain", "changed-proof"])
def test_reassessment_rejects_incomplete_or_stale_proof(tmp_path: Path, damage: str) -> None:
    _fresh, partial, result, payload = _proof_fixture(tmp_path, validation_change="commandless")
    context = partial["dispatch"]["coverage_reuse"]
    judgment = _judgment(context["validation_reassessment"][0])
    payload["validation_reassessments"] = [judgment]
    if damage == "missing":
        payload["validation_reassessments"] = []
    elif damage == "duplicate":
        payload["validation_reassessments"].append(judgment)
    elif damage == "old-digest":
        judgment["original_planned_validation_digest"] = judgment["replacement_planned_validation_digest"]
    elif damage == "empty-reason":
        judgment["native_limitations"] = " "
    elif damage in {"reinspect", "uncertain"}:
        judgment["disposition"] = damage
    else:
        context["validation_reassessment"][0]["replacement_execution_identity"]["platform"] = "different"
    with pytest.raises(ValueError, match=r"reassessment|coverage execution view"):
        _compile(partial, result, payload)
    assert not Path(partial["artifact_path"]).exists()
