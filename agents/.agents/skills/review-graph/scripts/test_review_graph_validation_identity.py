"""Validator ownership and immutable planned references across repair epochs."""

import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_plan import ValidationArtifact, plan_from_document
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _compile_materialized_evidence,
    _compile_repair_fixture_entry,
    _json_plan,
    _late_validation_plan,
    _late_validation_requirement,
    _mutation_with_audit_source,
    _source_by_node,
    _sparse_plan_document,
)


def _runtime_cli(arguments: list[str]) -> None:
    """Bound the real CLI so instruction discovery regressions cannot hang tests."""
    result = subprocess.run(  # noqa: S603 - fixed runtime entry point and temporary fixture paths.
        [sys.executable, str(Path(runtime.__file__).resolve()), *arguments], capture_output=True, text=True, timeout=15, check=False
    )
    assert result.returncode == 0, result.stderr


def _absolute_command() -> str:
    return shlex.join((sys.executable, "-c", "pass"))


def test_absolute_validator_command_materializes_with_source_path_ownership(tmp_path: Path) -> None:
    planning = _sparse_plan_document()
    planning["validation_requirements"][0].update(commands=[_absolute_command()], canonical_recipe=None)
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    request = {
        "plan": _json_plan(plan),
        "source_state": ["scope", "worktree", "repository"],
        "artifact_store": str(tmp_path / "artifacts"),
        "authorization": "review-only",
        "repository_root": str(SKILL_ROOT.parents[2]),
        "state_verification_command": "capture_scope.py --mode baseline",
    }
    input_path, output_path = tmp_path / "input.json", tmp_path / "dispatches.json"
    input_path.write_text(json.dumps(request))
    _runtime_cli(["materialize-dispatches", "--input", str(input_path), "--output", str(output_path)])
    dispatches = json.loads(output_path.read_bytes())
    validator = next(item["dispatch"] for item in dispatches["dispatches"] if item["result_contract"] == "compact-validation")
    assert validator["owned_paths"] == list(plan.coalesced_validation_units[0].captured_paths)
    assert validator["command_policy"]["allowed_commands"] == [_absolute_command()]
    assert str(SKILL_ROOT.parents[2] / "AGENTS.md") in validator["instruction_paths"]


def test_absolute_validator_command_expands_late_validation_with_a_bounded_cli(tmp_path: Path) -> None:
    late = {**_late_validation_requirement(), "commands": [_absolute_command()]}
    plan, sources = _compile_materialized_evidence(tmp_path / "original", late_requirements=[late])
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatches = runtime.materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "original"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    dispatch_path, journal, capture_path = (tmp_path / name for name in ("dispatches.json", "execution.jsonl", "capture.json"))
    dispatch_path.write_text(json.dumps(dispatches))
    capture_path.write_text(
        json.dumps({"scope_fingerprint": "scope", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"})
    )
    by_node = _source_by_node(sources)
    for node in plan.actual_worker_nodes:
        if node.mode != "synthesis":
            runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(node.node_id, "accepted", source=by_node[node.node_id]))
    requirement = {**_late_validation_plan(), "commands": late["commands"]}
    request = {**lifecycle, "artifact_store": str(tmp_path / "revision"), "validation_requirements": [requirement]}
    input_path, output_path = tmp_path / "expand.json", tmp_path / "expanded.json"
    input_path.write_text(json.dumps(request))
    _runtime_cli(
        [
            "reconcile-validation-requirements",
            "--input",
            str(input_path),
            "--journal",
            str(journal),
            "--dispatches",
            str(dispatch_path),
            "--current-capture",
            str(capture_path),
            "--output",
            str(output_path),
        ]
    )
    expanded = json.loads(output_path.read_bytes())
    assert expanded["status"] == "expanded"
    revised = json.loads(Path(expanded["dispatches_path"]).read_bytes())
    added = next(item["dispatch"] for item in revised["dispatches"] if late["requirement_id"] in item["dispatch"]["requirement_ids"])
    assert added["validation_unit"]["commands"] == late["commands"]
    assert added["owned_paths"] == requirement["captured_paths"]
    assert {node.node_id for node in plan.actual_worker_nodes if node.mode == "validation"} <= set(expanded["retained_node_ids"])
    assert expanded["validation_reconciliation"]["blockers"] == []


@pytest.mark.parametrize("owned", ["/", "/outside/source.py", "../source.py", "nested/../../source.py", ".", "nested\\source.py"])
def test_instruction_discovery_rejects_unsupported_owned_paths(tmp_path: Path, owned: str) -> None:
    with pytest.raises(ValueError, match=r"concrete repository paths|portable repository-relative paths"):
        runtime._applicable_instruction_paths(tmp_path, (owned,), ())


def test_instruction_discovery_includes_nested_directories_and_deleted_sources(tmp_path: Path) -> None:
    nested = tmp_path / "src" / "nested"
    nested.mkdir(parents=True)
    instructions = (tmp_path / "AGENTS.md", tmp_path / "src" / "AGENTS.md", nested / "AGENTS.md")
    for instruction in instructions:
        instruction.write_text("Local instructions\n")
    paths = runtime._applicable_instruction_paths(tmp_path, ("src/nested", "src/nested/deleted.py"), ())
    assert paths == tuple(sorted(str(path) for path in instructions))


def test_planned_validation_reference_survives_two_repairs_with_fresh_validation(tmp_path: Path) -> None:  # noqa: PLR0915 - multi-epoch scheduler, synthesis, and proof regression.
    request, original, original_source = _mutation_with_audit_source(tmp_path, reference_planned_validation=True)
    original_bytes = {Path(path): Path(path).read_bytes() for path in original_source.values()}
    original_requirement = json.loads(Path(original_source["metadata_path"]).read_bytes())["normalized_record"]["validation_requirements"][0]
    old_dispatches = runtime.materialize_dispatches(
        {
            "plan": request["plan"],
            "source_state": request["source_state"],
            "artifact_store": str(tmp_path / "old-evidence"),
            "authorization": "review-only",
            "repository_root": request["previous_capture"]["repository_root"],
            "state_verification_command": request["state_verification_command"],
        }
    )
    old_validator = next(item for item in old_dispatches["dispatches"] if item["result_contract"] == "compact-validation")
    old_validation_source = _compile_repair_fixture_entry(old_validator, request, tmp_path / "old.jsonl")
    request["sources"].append(old_validation_source)
    original_bytes.update({Path(path): Path(path).read_bytes() for path in old_validation_source.values()})
    evidence_id = original["dispatch"]["evidence_id"]
    previous_validator_ids = {old_validator["dispatch"]["evidence_id"]}
    git = shutil.which("git")
    assert git is not None
    result = runtime.advance_after_mutation(request)
    for epoch in (1, 2):
        if epoch == 2:
            repository = Path(request["new_capture"]["repository_root"])
            (repository / "state.rs").write_text("pub fn state() { assert!(false); }\n")
            request = {
                **request,
                **json.loads(Path(result["lifecycle_input_path"]).read_bytes()),
                "authorization_before": "review-and-fix",
                "previous_capture": result["capture"],
                "new_capture": _scope_data(git, repository, "baseline", None, ()),
                "repair_epoch": epoch,
            }
            request.pop("sources")
            result = runtime.advance_after_mutation(request)
        lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
        plan = runtime._graph_plan(lifecycle["plan"])
        validator = plan.coalesced_validation_units[0]
        assert result["reused_evidence_ids"] == [evidence_id]
        assert validator.evidence_ids == ()
        assert runtime._planned_validation_digest(validator) != original_requirement["planned_validation_digest"]
        dispatches, journal = result["dispatch_set"], Path(result["journal_path"])
        ready = runtime.next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=(), dispatch_set=dispatches)
        assert ready["blockers"] == []
        assert validator.node_id in ready["ready_node_ids"]
        assert not set(plan.synthesis_nodes) & set(ready["ready_node_ids"])
        reconciliation = ready["validation_reconciliation"]["requirements"][0]
        assert reconciliation["resolution"] == "planned"
        assert reconciliation["requirement"] == original_requirement
        assert reconciliation["validation_unit_id"] == validator.node_id
        assert reconciliation["reuse_binding"] == {
            "original_planned_validation_digest": original_requirement["planned_validation_digest"],
            "original_source_state": original["dispatch"]["source_state"],
            "replacement_planned_validation_digest": runtime._planned_validation_digest(validator),
            "replacement_source_state": lifecycle["source_state"],
        }
        sources = []
        for _ in range(plan.complete_node_count + 1):
            events, _state, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
            ready = runtime.next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=dispatches)
            if ready["complete"]:
                break
            assert ready["ready_dispatches"], ready["blockers"]
            sources.extend(_compile_repair_fixture_entry(entry, lifecycle, journal) for entry in ready["ready_dispatches"])
        else:
            pytest.fail("repair graph did not complete within its node bound")
        output = tmp_path / f"proof-{epoch}.json"
        assert (
            runtime.main(
                [
                    "finalize-proof",
                    "--input",
                    result["lifecycle_input_path"],
                    "--dispatches",
                    result["dispatches_path"],
                    "--journal",
                    str(journal),
                    "--current-capture",
                    result["capture_path"],
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        final = json.loads(output.read_bytes())
        assert final["status"] == "complete", final["blockers"]
        assert final["repository_validation_status"] == "passed"
        accepted = set(final["proof"]["accepted_validation_evidence_ids"])
        assert accepted == {f"validation:{validator.node_id}"}
        assert not accepted & previous_validator_ids
        previous_validator_ids.update(accepted)
        bundle = runtime.build_synthesis_bundle({**lifecycle, "sources": sources})
        audit = next(record for record in bundle["records"] if record["evidence_id"] == evidence_id)
        assert audit["validation_requirements"] == [original_requirement]
        assert audit["reuse"]["original_source_state"] == original["dispatch"]["source_state"]
    assert all(path.read_bytes() == content for path, content in original_bytes.items())


@pytest.mark.parametrize(
    "field",
    [
        "commands",
        "working_directories",
        "environment",
        "toolchain",
        "features",
        "platform",
        "allowed_artifacts",
        "mutation_lock",
        "captured_paths",
        "expected_workspace_effects",
        "requires_isolation",
        "isolation_root",
    ],
)
def test_reused_audit_reference_rejects_changed_validation_contract(tmp_path: Path, field: str) -> None:
    request, _entry, _source = _mutation_with_audit_source(tmp_path, reference_planned_validation=True)
    result = runtime.advance_after_mutation(request)
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    plan = runtime._graph_plan(lifecycle["plan"])
    changes: dict[str, Any] = {
        "commands": ("false",),
        "working_directories": (str(tmp_path),),
        "environment": "different environment",
        "toolchain": "different toolchain",
        "features": ("other-feature",),
        "platform": "different platform",
        "allowed_artifacts": (
            ValidationArtifact(
                path=str(tmp_path / "output.json"), kind="report", repository_status="outside-repository", status_source="isolated-output-directory"
            ),
        ),
        "mutation_lock": "different-lock",
        "captured_paths": ("tool.py",),
        "expected_workspace_effects": ("tool.py",),
        "requires_isolation": True,
        "isolation_root": str(tmp_path / "isolation"),
    }
    replacement = {field: changes[field]}
    if field == "requires_isolation":
        replacement["isolation_root"] = changes["isolation_root"]
    unit = replace(plan.coalesced_validation_units[0], **replacement)
    changed = replace(plan, coalesced_validation_units=(unit,))
    bundle = runtime.build_synthesis_bundle({**lifecycle, "plan": _json_plan(changed)})
    reconciliation = bundle["plan_context"]["validation_reconciliation"]
    assert reconciliation["requirements"][0]["resolution"] == "identity-conflict"
    assert "reuse_binding" not in reconciliation["requirements"][0]
    assert reconciliation["blockers"]


def test_reused_validation_reference_is_scoped_to_its_verified_audit(tmp_path: Path) -> None:
    request, _entry, source = _mutation_with_audit_source(tmp_path, reference_planned_validation=True)
    result = runtime.advance_after_mutation(request)
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    plan = runtime._graph_plan(lifecycle["plan"])
    record = runtime._load_evidence_source(source, require_normalized=True)[4]
    assert record is not None
    for changed in (
        {**record, "evidence_id": "review:other-audit"},
        {**record, "artifact_digest": "sha256:" + "0" * 64},
        {**record, "observed_source_state": result["new_source_state"]},
    ):
        reconciliation = runtime._validation_reconciliation(plan, [changed])
        assert reconciliation["requirements"][0]["resolution"] == "identity-conflict"
        assert "reuse_binding" not in reconciliation["requirements"][0]
