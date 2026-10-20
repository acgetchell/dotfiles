"""Output relocation preserves audit obligations but never old validator passes."""

import json
import shlex
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
import test_review_graph_runtime as fixtures
from review_graph_plan import ValidationArtifact
from review_graph_validation_outputs import obligation_identity


def _external_log(path: Path) -> ValidationArtifact:
    return ValidationArtifact(path=str(path), kind="log", repository_status="outside-repository", status_source="isolated-output-directory")


def test_repair_log_relocation_retains_source_audit_and_requires_fresh_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_request = fixtures._mutation_request
    log_root = tmp_path / "validation"
    log_root.mkdir()
    original_log, replacement_log = log_root / "ci.log", log_root / "ci-repair-1.log"
    original_log.write_text("immutable original execution\n")

    def request_with_log(directory: Path, *, instructions: bool = False) -> dict[str, Any]:
        request = original_request(directory, instructions=instructions)
        plan = runtime._graph_plan(request["plan"])
        unit = replace(
            plan.coalesced_validation_units[0],
            commands=("just check-fast > " + shlex.quote(str(original_log)) + " 2>&1",),
            canonical_recipe=None,
            allowed_artifacts=(_external_log(original_log),),
            dependency_policy="continue-independent",
            isolation_root=str(log_root),
        )
        request["plan"] = fixtures._json_plan(replace(plan, coalesced_validation_units=(unit,)))
        request["planning_template"]["validation_requirements"][0].update(
            commands=["just check-fast > " + shlex.quote(str(replacement_log)) + " 2>&1"],
            canonical_recipe=None,
            allowed_artifacts=[{"path": str(replacement_log), "kind": "log", "repository_status": "outside-repository"}],
            dependency_policy="stop-on-failure",
            execution_strategy="sequential",
            independence_basis="Stop at the first failed prerequisite.",
            isolation_root=str(log_root),
        )
        request["planning_template"]["pre_review_validation_requirement_ids"] = list(unit.requirement_ids)
        return request

    monkeypatch.setattr(fixtures, "_mutation_request", request_with_log)
    request, entry, source = fixtures._mutation_with_audit_source(tmp_path, reference_planned_validation=True)
    originals = {Path(path): Path(path).read_bytes() for path in source.values()}
    result = runtime.advance_after_mutation(request)
    assert entry["dispatch"]["evidence_id"] in result["reused_evidence_ids"]
    plan = runtime._graph_plan(result["lifecycle_input"]["plan"])
    assert plan.coalesced_validation_units[0].evidence_ids == ()
    assert plan.pre_review_validation_nodes
    assert str(replacement_log) in plan.coalesced_validation_units[0].commands[0]
    record = runtime._load_evidence_source(source, require_normalized=True)[4]
    assert record is not None
    reconciliation = runtime._validation_reconciliation(plan, [record])
    assert reconciliation["blockers"] == []
    binding = reconciliation["requirements"][0]["reuse_binding"]["output_binding"]
    assert {"commands", "allowed_artifacts", "source_state"} <= set(binding["changed_identity_fields"])
    assert original_log.read_text() == "immutable original execution\n"
    assert not replacement_log.exists()
    assert all(path.read_bytes() == content for path, content in originals.items())
    retained = json.loads(Path(binding["original_identity"]["path"]).read_bytes())
    assert runtime.digest_bytes(runtime.canonical_json(retained).encode()) == binding["original_identity"]["digest"]


@pytest.mark.parametrize("change", ["toolchain", "environment", "platform", "features", "effects", "command", "input", "repository-log", "report", "compound"])
def test_output_normalization_preserves_semantic_changes(tmp_path: Path, change: str) -> None:
    root = tmp_path / "repository"
    old_log, new_log = tmp_path / "old.log", tmp_path / "new.log"
    before: dict[str, Any] = {
        "commands": ["just ci > " + shlex.quote(str(old_log))],
        "allowed_artifacts": [runtime.asdict(_external_log(old_log))],
        "execution_strategy": "continue-independent",
        "independence_basis": "Independent units.",
    }
    after = {**before, "commands": ["just ci > " + shlex.quote(str(new_log))], "allowed_artifacts": [runtime.asdict(_external_log(new_log))]}
    assert obligation_identity(before, str(root)) == obligation_identity(after, str(root))
    if change == "effects":
        after["expected_workspace_effects"] = ["source.py"]
    elif change == "command":
        after["commands"] = ["just weaker > " + shlex.quote(str(new_log))]
    elif change == "input":
        after["commands"] = [f"cat {shlex.quote(str(new_log))} > {shlex.quote(str(new_log))}"]
    elif change == "repository-log":
        after["allowed_artifacts"] = [runtime.asdict(_external_log(root / "output.log"))]
        after["commands"] = ["just ci > " + shlex.quote(str(root / "output.log"))]
    elif change == "report":
        after["allowed_artifacts"][0]["kind"] = "report"
    elif change == "compound":
        after["commands"] = ["just ci > " + shlex.quote(str(new_log)) + " && false"]
    else:
        after[change] = "changed"
    assert obligation_identity(before, str(root)) != obligation_identity(after, str(root))
