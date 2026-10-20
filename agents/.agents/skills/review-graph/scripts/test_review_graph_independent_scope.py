"""A baseline repair requires its complete change, without inventing context reads."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _baseline_mutation_fixture, _compact_independent_payload, _json_plan


def _repair(tmp_path: Path, comparison: str = "commit") -> dict[str, Any]:
    git, repository, template, before, plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 2\n")
    (repository / "new.txt").write_text("new untracked input\n")
    (repository / "LICENSE").unlink()
    base = before["head"] if comparison == "commit" else "HEAD"
    if comparison == "omitted":
        template.pop("concrete_change_target", None)
        template.pop("change_target", None)
    elif comparison == "baseline":
        template.update(concrete_change_target=False)
        template.pop("change_target", None)
    else:
        template.update(concrete_change_target=True, change_target=f"git --no-pager diff {base} -- .")
    after = _scope_data(git, repository, "baseline", None, ())
    return {
        "plan": _json_plan(plan),
        "source_state": [before[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")],
        "previous_capture": before,
        "new_capture": after,
        "planning_template": template,
        "authorization_before": "review-only",
        "authorization_after": "review-and-fix",
        "repair_epoch": 1,
        "changed_paths": ["LICENSE", "new.txt", "tool.py"],
        "artifact_store": str(tmp_path / "repair"),
        "state_verification_command": "capture_scope.py --mode baseline",
    }


@pytest.mark.parametrize("comparison", ["commit", "HEAD", "omitted", "baseline"])
def test_baseline_repair_publishes_complete_change_and_separate_context(tmp_path: Path, comparison: str) -> None:
    request = _repair(tmp_path, comparison)
    result = runtime.advance_after_mutation(request)
    entries = result["dispatch_set"]["dispatches"]
    entry = next(item for item in entries if item["dispatch"]["mode"] == "independent-review")
    dispatch = entry["dispatch"]
    assert dispatch["planned_paths"] == ["LICENSE", "new.txt", "tool.py"]
    if comparison in {"omitted", "baseline"}:
        assert dispatch["change_target"].startswith(f"git --no-pager diff {request['previous_capture']['head']} -- ")
    assert "cliff.toml" in result["capture"]["captured_scope_paths"]
    assert any("state.rs" in item["dispatch"]["owned_paths"] for item in entries if item["dispatch"]["mode"] == "audit")
    payload = _compact_independent_payload(dispatch)
    payload["nearby_contract_owners"].append("cliff.toml")
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    content, metadata = runtime.compile_independent_payload(
        {"dispatch": {**dispatch, "before_state": result["new_source_state"], "after_state": result["new_source_state"]}, "payload": payload}
    )
    assert metadata["evidence"]["status"] == "no-findings"
    assert b"LICENSE, new.txt, tool.py" in content
    assert json.loads(Path(entry["worker_payload_path"]).read_bytes()) == payload


@pytest.mark.parametrize("missing", ["LICENSE", "new.txt", "tool.py"])
def test_repair_cannot_publish_without_each_changed_or_untracked_file(tmp_path: Path, missing: str) -> None:
    result = runtime.advance_after_mutation(_repair(tmp_path))
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["mode"] == "independent-review")
    payload = _compact_independent_payload(entry["dispatch"])
    payload["files_inspected"].remove(missing)
    for check in payload["adversarial_checks"]:
        check["inspected_paths"].remove(missing)
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    with pytest.raises(ValueError, match="files_inspected must equal"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert not Path(entry["worker_payload_path"]).exists()


@pytest.mark.parametrize("damage", ["narrow-routing", "stale-source", "hidden-untracked"])
def test_repair_scope_comes_from_verified_source(tmp_path: Path, damage: str) -> None:
    request = _repair(tmp_path)
    repository = Path(request["new_capture"]["repository_root"])
    document = bootstrap_document(request["new_capture"], request["planning_template"])
    document["planning_purpose"] = "repair-verification"
    if damage == "narrow-routing":
        document["routing_overrides"].append(
            {
                "catalog_id": "repo.independent",
                "disposition": "selected",
                "reason": "Inspect the selected repair.",
                "applicability_evidence": ["Concrete repair target."],
                "review_surface": ["tool.py"],
            }
        )
    elif damage == "stale-source":
        (repository / "tool.py").write_text("value = 3\n")
    else:
        document = deepcopy(document)
        document["untracked_paths"] = []
        plan = plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
        assert "new.txt" in next(node.coverage for node in plan.actual_worker_nodes if node.mode == "independent-review")
        return
    with pytest.raises(ValueError, match=r"omits changed or untracked paths|does not match independent recapture"):
        plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
