"""Saved content repair followed by external staging before publication."""

import json
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_review_graph_git import _discovery_payload
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compact_independent_payload,
    _compile_repair_fixture_entry,
    _publish_worker_bytes,
    _run_test_git,
)
from test_review_graph_transitions import _materialize, _payload


def _staged_repair(tmp_path: Path, dependency: str = "source") -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[Path, bytes]]:
    git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    template.update(concrete_change_target=True, change_target="fixture repair")
    template["validation_requirements"][0].update(commands=["just check-fast > ci-final.log"], canonical_recipe=None)
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    audit = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    payload = _discovery_payload(audit) if dependency == "source-discovery" else _payload(["tool.py"])
    if dependency == "index":
        payload["git_dependencies"] = [{"kind": "index", "reason": "Judgment depends on staging."}]
    planned = audit["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload["validation_requirements"] = [
        {
            "requirement_id": planned["requirement_ids"][0],
            "planned_validation_digest": planned["planned_validation_digest"],
            "owner": audit["dispatch"]["skill_id"],
            "reason": "Required fixture validation",
            "expected_evidence": "Checks pass",
        }
    ]
    content, metadata = runtime.compile_review(
        {"dispatch": {**audit["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(audit["artifact_path"]).write_bytes(content)
    Path(audit["metadata_path"]).write_text(json.dumps(metadata))
    sources = [{key: audit[key] for key in ("artifact_path", "metadata_path")}]
    validator = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    unit = validator["dispatch"]["validation_unit"]
    content, metadata = runtime.compile_validation(
        {
            "dispatch": {**validator["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]},
            "payload": {
                "artifacts": [],
                "limitations": [],
                "status": "failed",
                "executions": [
                    {
                        "artifact_paths": [],
                        "command": unit["commands"][0],
                        "working_directory": unit["working_directories"][0],
                        "elapsed": "1s",
                        "evidence": "Fixture assertion failed; retained historical failure.",
                        "executor": validator["node_id"],
                        "exit_code": 1,
                        "result": "failed",
                    }
                ],
            },
        }
    )
    Path(validator["artifact_path"]).write_bytes(content)
    Path(validator["metadata_path"]).write_text(json.dumps(metadata))
    sources.append({key: validator[key] for key in ("artifact_path", "metadata_path")})
    journal = tmp_path / "failed-execution.jsonl"
    runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(validator["node_id"], "accepted", source=sources[-1]))
    history = {Path(path): Path(path).read_bytes() for source in sources for path in source.values()}
    history[journal] = journal.read_bytes()
    (repository / "state.rs").write_text("pub fn state() { assert!(true); }\n")
    repaired = _scope_data(git, repository, "baseline", None, ())
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    staged = _scope_data(git, repository, "baseline", None, ())
    return (
        git,
        repository,
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": repaired,
            "post_repair_capture": staged,
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": ["state.rs"],
            "sources": sources,
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
        },
        audit,
        history,
    )


def _finish_repair(tmp_path: Path, result: dict[str, Any]) -> list[str]:
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    plan = runtime._graph_plan(lifecycle["plan"])
    journal = Path(result["journal_path"])
    executed: list[str] = []
    for _ in range(plan.complete_node_count + 1):
        events, _states, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = runtime.next_ready_nodes(lifecycle, journal_events=events, dispatch_set=result["dispatch_set"])
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready["blockers"]
        for entry in ready["ready_dispatches"]:
            if entry["dispatch"].get("mode") == "independent-review":
                payload = _compact_independent_payload(entry["dispatch"])
                payload.update(before_state=result["current_source_state"], after_state=result["current_source_state"])
                _publish_worker_bytes(entry, json.dumps(payload).encode())
                assert (
                    runtime.main(
                        [
                            "compile-node",
                            "--input",
                            result["lifecycle_input_path"],
                            "--dispatches",
                            result["dispatches_path"],
                            "--journal",
                            str(journal),
                            "--node-id",
                            entry["node_id"],
                            "--before-capture",
                            result["capture_path"],
                            "--after-capture",
                            result["capture_path"],
                            "--output",
                            str(tmp_path / "independent-result.json"),
                        ]
                    )
                    == 0
                )
            else:
                _compile_repair_fixture_entry(entry, lifecycle, journal)
            executed.append(entry["node_id"])
    else:
        pytest.fail("repair plus staging did not complete within its node bound")
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
    assert set(final["proof"]["accepted_validation_evidence_ids"]) == {f"validation:{unit.node_id}" for unit in plan.coalesced_validation_units}
    return executed


@pytest.mark.parametrize("dependency", ["source", "source-discovery", "index", "changed-validation"])
def test_repair_then_external_staging_preserves_only_eligible_evidence(tmp_path: Path, dependency: str) -> None:
    git, repository, request, audit, history = _staged_repair(tmp_path, dependency)
    if dependency == "changed-validation":
        request["planning_template"]["validation_requirements"][0]["commands"] = ["just check-fast > ci-release-review.log"]
    original_request = json.dumps(request, sort_keys=True)
    input_path, output_path = tmp_path / "request.json", tmp_path / "result.json"
    input_path.write_text(json.dumps(request))
    assert runtime.main(["advance-after-mutation", "--input", str(input_path), "--output", str(output_path)]) == 0
    result = json.loads(output_path.read_bytes())
    assert result["transition_kind"] == "repair-then-observed-external-git-metadata"
    assert result["capture"] == request["post_repair_capture"]
    retained = json.loads(Path(result["repair_transition_path"]).read_bytes())
    assert retained["capture"] == request["new_capture"]
    assert retained["previous_capture"] == request["previous_capture"]
    assert retained["historical_evidence_sources"] == request["sources"]
    old_id = audit["dispatch"]["evidence_id"]
    assert (old_id in result["reused_evidence_ids"]) is (dependency in {"source", "source-discovery"})
    if dependency == "index":
        assert old_id in result["stale_evidence_ids"]
        assert any(old_id in item.get("replaced_evidence_ids", []) for item in result["node_decisions"])
        assert audit["node_id"] in {item["node_id"] for item in result["invalidated_nodes"]}
        assert audit["node_id"] not in result["unaffected_node_ids"]
    executed = _finish_repair(tmp_path, result)
    assert len(executed) == len(set(executed))
    assert all(path.read_bytes() == content for path, content in history.items())
    assert _scope_data(git, repository, "baseline", None, ()) == request["post_repair_capture"]
    assert json.dumps(request, sort_keys=True) == original_request


@pytest.mark.parametrize("change", ["content", "mode", "instructions", "head", "boundary", "forged-bridge", "stale-live-index"])
def test_repair_staging_rejects_unverified_composition_before_publication(tmp_path: Path, change: str) -> None:
    git, repository, request, _audit, history = _staged_repair(tmp_path)
    if change == "content":
        (repository / "tool.py").write_text("value = 3\n")
    elif change == "mode":
        path = repository / "tool.py"
        path.chmod(path.stat().st_mode ^ 0o111)
    elif change == "instructions":
        (repository / "AGENTS.md").write_text("New applicable instructions.\n")
    elif change == "head":
        _run_test_git(git, "-C", str(repository), "commit", "-m", "externally committed")
    elif change == "boundary":
        request["post_repair_capture"] = _scope_data(git, repository, "baseline", None, ("state.rs",))
    elif change == "forged-bridge":
        request["new_capture"]["repository_path_fingerprints"]["tool.py"] = "0" * 64
    else:
        _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "state.rs")
    if change in {"content", "mode", "instructions", "head"}:
        request["post_repair_capture"] = _scope_data(git, repository, "baseline", None, ())
    current = _scope_data(git, repository, "baseline", None, ())
    with pytest.raises(ValueError, match=r"metadata transition|fingerprint|independent recapture"):
        runtime.advance_after_mutation(request)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in history.items())
    assert _scope_data(git, repository, "baseline", None, ()) == current
