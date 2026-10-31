"""Whole-repository path assessment stays distinct from specialist closure."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import main as bootstrap_main
from review_graph_integrity import digest_bytes
from review_graph_path_inventory import captured_path_inventory
from review_graph_reuse import ExternalMetadataTransition, source_snapshot
from review_graph_starter import prepare_release
from test_review_graph_reuse import _audit_request
from test_review_graph_runtime import _baseline_mutation_fixture, _run_test_git

FIXTURE = Path(__file__).parent / "fixtures" / "baseline_path_inventory.json"


def _mixed_baseline(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    fixture = json.loads(FIXTURE.read_bytes())
    for group in fixture.values():
        for path, content in group.items():
            target = repository / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "mixed baseline inventory")
    capture = _scope_data(git, repository, "baseline", None, ())
    artifact_root = tmp_path / "validation"
    artifact_root.mkdir()
    choices, discovery = prepare_release(capture, artifact_root)
    projection = discovery["routing_projection"]
    matches = {entry["catalog_id"]: set(entry["matched_paths"]) for entry in projection["entries"]}
    assert set(fixture["tooling"]) <= matches["repo.tooling"]
    assert set(fixture["documentation"]) <= matches["docs.repository"]
    assert {path for name in ("semantic_owner", "dependency", "historical", "archive") for path in fixture[name]} <= set(projection["unmatched_captured_paths"])
    choices.update(
        ignored_outputs=[],
        command_policy={"disposition": "allowed", "reason": "Protocol fixture does not execute the gate"},
        execution_prerequisites={"executables": ["env"], "native_available": True, "reason": "POSIX fixture"},
        captured_path_dispositions=template["captured_path_dispositions"],
        routing_overrides=[
            {
                "catalog_id": entry["catalog_id"],
                "disposition": "selected",
                "reason": "Explicit scripted semantic decisions for this mixed protocol fixture",
                "applicability_evidence": entry["matched_paths"],
                "review_surface": [path for path in entry["matched_paths"] if path != ".config/nextest.toml"],
                "owners": ["fixture"],
            }
            for entry in projection["entries"]
            if entry["target_kind"] == "leaf" and entry["matched_paths"]
        ],
    )
    return repository, capture, choices, fixture


def test_closed_specialist_ledger_blocks_unassessed_paths_before_fanout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repository, capture, choices, fixture = _mixed_baseline(tmp_path)
    capture_path, choices_path = tmp_path / "capture.json", tmp_path / "operator.json"
    capture_path.write_text(json.dumps(capture))
    choices_path.write_text(json.dumps(choices))
    blocked = tmp_path / "blocked.json"
    assert bootstrap_main(["--capture", str(capture_path), "--starter-config", str(choices_path), "--output", str(blocked)]) == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preflight_status"] == "ready"
    assert not receipt["dispatch_allowed"]
    assert receipt["next_command"] is None
    bundle = json.loads(blocked.read_bytes())
    assert bundle["plan"]["routing_catalog_closed"]
    assert bundle["plan"]["routing_completion_blockers"] == []
    reference = receipt["captured_path_inventory_reference"]
    inventory_bytes = Path(reference["path"]).read_bytes()
    assert digest_bytes(inventory_bytes) == reference["digest"]
    inventory = json.loads(inventory_bytes)
    assert inventory == bundle["plan"]["captured_path_inventory"]
    expected = {".config/nextest.toml", *(path for name in ("semantic_owner", "dependency", "historical", "archive") for path in fixture[name])}
    assert set(inventory["unassessed_captured_paths"]) == expected
    assert reference["unassessed_path_count"] == len(expected)
    assert reference["unassigned_path_count"] == len(expected) + 3
    with pytest.raises(ValueError, match="blocked"):
        runtime.materialize_dispatches(bundle["materialization_input"])

    tooling = next(item for item in choices["routing_overrides"] if item["catalog_id"] == "repo.tooling")
    tooling["review_surface"].extend([".config/nextest.toml", *fixture["semantic_owner"]])
    choices["captured_path_dispositions"].extend(
        {
            "paths": list(fixture[name]),
            "disposition": name,
            "reason": f"Inspected fixture {name} role",
            "catalog_ids": ["repo.tooling"] if name == "dependency" else [],
        }
        for name in ("dependency", "historical", "archive")
    )
    # This transitive instruction is declared after inspecting AGENTS.md; a path
    # match does not prove that its instruction closure has been read.
    choices["instruction_paths"].append("instructions/review-rules.txt")
    choices_path.write_text(json.dumps(choices))
    ready = tmp_path / "ready.json"
    assert bootstrap_main(["--capture", str(capture_path), "--starter-config", str(choices_path), "--output", str(ready)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["captured_path_inventory_reference"]["unassessed_path_count"] == 0
    assert receipt["captured_path_inventory_reference"]["unassigned_path_count"] == 7
    bundle = json.loads(ready.read_bytes())
    _assert_inventory_dispatches(bundle, repository)


def _assert_inventory_dispatches(bundle: dict[str, Any], repository: Path) -> None:
    dispatches = runtime.materialize_dispatches(bundle["materialization_input"])
    tooling_dispatch = next(entry["dispatch"] for entry in dispatches["dispatches"] if entry["dispatch"]["skill_id"] == "project-tooling-review")
    assert "build.policy" in tooling_dispatch["owned_paths"]
    context = "instructions/review-rules.txt"
    assert context not in tooling_dispatch["owned_paths"]
    assert str(repository / context) in tooling_dispatch["required_read_paths"]
    assert str(repository / context) in tooling_dispatch["instruction_paths"]
    assert "context-only/release-context.txt" not in tooling_dispatch["owned_paths"]
    assert str(repository / "context-only/release-context.txt") in tooling_dispatch["required_read_paths"]
    assert str(repository / "context-only/release-context.txt") not in tooling_dispatch["instruction_paths"]
    assert "context-only/AGENTS.md" not in tooling_dispatch["owned_paths"]
    assert str(repository / "context-only/AGENTS.md") in tooling_dispatch["instruction_paths"]
    assert runtime._graph_plan(bundle["plan"]).captured_path_inventory == bundle["plan"]["captured_path_inventory"]
    synthesis = next(entry for entry in dispatches["dispatches"] if entry["dispatch"]["skill_id"] == "repository-production-review")
    view = json.loads(Path(synthesis["worker_execution_path"]).read_bytes())
    reference = view["dispatch"]["captured_path_inventory_reference"]
    assert digest_bytes(Path(reference["path"]).read_bytes()) == reference["digest"]
    assert json.loads(Path(reference["path"]).read_bytes()) == bundle["plan"]["captured_path_inventory"]
    _run_test_git("git", "-C", str(repository), "checkout", "-b", "fixture-context-continuation")
    transition = ExternalMetadataTransition(source_snapshot(bundle["capture"]), source_snapshot(_scope_data("git", repository, "baseline", None, ())))
    transition.verify()
    runtime._verify_continuation_instructions(runtime._graph_plan(bundle["plan"]), {entry["node_id"]: entry for entry in dispatches["dispatches"]}, transition)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"paths": ["missing"]}, "captured repository paths"),
        ({"paths": ["owned"]}, "audit ownership"),
        ({"paths": ["context", "context"]}, "more than once"),
        ({"reason": " "}, "nonblank"),
        ({"catalog_ids": []}, "require distinct selected"),
        ({"catalog_ids": ["repo.synthesis"]}, "selected audit leaves"),
        ({"disposition": "historical"}, "only dependency"),
    ],
)
def test_nonowned_assessments_reject_invalid_claims(mutation: dict[str, Any], message: str) -> None:
    assessment = {"paths": ["context"], "disposition": "dependency", "reason": "Required build context", "catalog_ids": ["repo.tooling"]}
    assessment.update(deepcopy(mutation))
    with pytest.raises(ValueError, match=message):
        captured_path_inventory(("owned", "context"), {"repo.tooling": ("owned",)}, {"repo.tooling"}, [assessment])


@pytest.mark.parametrize("context_path", ["cliff.toml", ".codecov.yml"])
def test_declared_context_reuse_requires_existing_read_evidence(tmp_path: Path, context_path: str) -> None:
    request, original, _payload = _audit_request(tmp_path)
    repository = Path(request["previous_capture"]["repository_root"])
    (repository / "tool.py").write_text("value = 1\n")
    (repository / "state.rs").write_text("pub fn state() { let value = 2; }\n")
    request.update(new_capture=_scope_data("git", repository, "baseline", None, ()), changed_paths=["state.rs"])
    dispositions = request["planning_template"]["captured_path_dispositions"]
    dispositions[0]["paths"].remove(context_path)
    dispositions.append({"paths": [context_path], "disposition": "dependency", "reason": "Explicit CLI context assessment", "catalog_ids": ["python.cli"]})
    result = runtime.advance_after_mutation(request)
    audits = [entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["skill_id"] == original["dispatch"]["skill_id"]]
    if context_path == "cliff.toml":
        assert not audits
        assert result["reused_evidence_ids"]
    else:
        assert len(audits) == 1
        assert not audits[0]["dispatch"].get("coverage_reuse")
        assert str(repository / context_path) in audits[0]["dispatch"]["required_read_paths"]
