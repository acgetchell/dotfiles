"""Staged repairs, interleaved changes, and continuation requests for review-graph tests."""

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_support_review_graph import ROUTING_CATALOG, SKILL_ROOT, _finalize_fixture_proof, _materialize, _prepare_all_fixture_timing, _run_test_git
from test_support_review_graph_evidence import _compact_independent_payload, _discovery_payload, _payload, _publish_worker_bytes
from test_support_review_graph_lifecycle import _baseline_mutation_fixture, _compile_repair_fixture_entry


def _staged_repair(tmp_path: Path, dependency: str = "source") -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[Path, bytes]]:
    """Build a repair request with staged changes and retain historical evidence for comparison."""
    git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    template.update(concrete_change_target=True, change_target="fixture repair")
    template["validation_requirements"][0].update(commands=["just check-fast > ci-final.log"], canonical_recipe=None)
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    audit = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    payload = _discovery_payload(audit) if dependency == "source-discovery" else _payload(["tool.py"], dispatch=audit["dispatch"])
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
                "schema_version": 3,
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
    """Run the remaining verification work and check the accepted validation evidence IDs."""
    _prepare_all_fixture_timing(result["dispatch_set"])
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
    final = _finalize_fixture_proof(result, output=tmp_path / "final.json")
    assert final["status"] == "complete", final["blockers"]
    assert final["repository_validation_status"] == "passed"
    assert set(final["proof"]["accepted_validation_evidence_ids"]) == {
        entry["dispatch"]["evidence_id"] for entry in result["dispatch_set"]["dispatches"] if entry["result_contract"] == "compact-validation"
    }
    return executed


def _continuation_args(result: dict[str, Any]) -> Namespace:
    """Resolve the journal, dispatch set, and capture files emitted by the previous operation."""
    return Namespace(journal=Path(result["journal_path"]), dispatches=Path(result["dispatches_path"]), current_capture=Path(result["capture_path"]))


def _run_continuation(tmp_path: Path, operation: str, request: dict[str, Any], args: Namespace) -> dict[str, Any]:
    """Invoke a continuation from disk and expose its persisted state for the next operation."""
    input_path, output_path = tmp_path / f"{operation}-input.json", tmp_path / f"{operation}-result.json"
    input_path.write_text(json.dumps(request))
    assert (
        runtime.main(
            [
                operation,
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--dispatches",
                str(args.dispatches),
                "--journal",
                str(args.journal),
                "--current-capture",
                str(args.current_capture),
            ]
        )
        == 0
    )
    result = json.loads(output_path.read_bytes())
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    assert lifecycle["source_state"] == request["source_state"]
    assert lifecycle["external_metadata_transitions"] == request["external_metadata_transitions"]
    return {
        **result,
        "lifecycle_input": lifecycle,
        "dispatch_set": json.loads(Path(result["dispatches_path"]).read_bytes()),
        "capture_path": result.get("current_capture_path", str(args.current_capture)),
        "current_source_state": list(runtime._capture_source_state(args.current_capture)),
    }


def _recovery_request(tmp_path: Path, result: dict[str, Any], entry: dict[str, Any], *, checks_started: bool) -> dict[str, Any]:
    """Request a retry of the specified node with the fixture's permitted executor."""
    return {
        **result["lifecycle_input"],
        "artifact_store": str(tmp_path / "recovery"),
        "node_id": entry["node_id"],
        "failure_kind": "executor-permission",
        "checks_started": checks_started,
        "reason": "The fixture executor denied access.",
        "remedy": "Use the permitted fixture executor.",
        "environment": "permitted native executor",
        "permission_change": "Enable the fixture capability.",
        "executor_permissions": "require_escalated",
    }


def _interleaved(tmp_path: Path, dependency: str = "source") -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[Path, bytes]]:
    """Prepare a staged repair with interleaved changes and retain the Git index bytes for comparison."""
    git, repository, request, audit, history = _staged_repair(tmp_path, dependency)
    # Earlier diagnostic captures are allowed; no capture exists for either final
    # repair before staging. Leave a mixture of staged and unstaged final edits.
    request.pop("post_repair_capture")
    path = repository / "state.rs"
    path.write_text("pub fn state() { assert_eq!(1, 1); }\n")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    path.write_text("pub fn state() { assert_eq!(2, 2); }\n")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    path.write_text("pub fn state() { assert_eq!(3, 3); }\n")
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    request["interleaved_staging"] = {
        "repair_attribution": "All changed_paths are agent edits within the existing authorized repair batch.",
        "staging_attribution": "The maintainer said they staged files as they reviewed the agent's repairs.",
    }
    history[repository / ".git" / "index"] = (repository / ".git" / "index").read_bytes()
    return git, repository, request, audit, history
