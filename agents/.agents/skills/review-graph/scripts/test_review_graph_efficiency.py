"""Workflow cost, prerequisite, and continuation regressions without Git mutations."""

import json
import sys
from argparse import Namespace
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_benchmark import _baseline_runtime, _trial, benchmark_fixture
from review_graph_metrics import projected_waves, source_demand
from review_graph_plan import ValidationArtifact, validation_requirements_from_document
from test_review_graph_runtime import (
    SKILL_ROOT,
    _compact_audit_payload,
    _execution_payload,
    _json_plan,
    _late_validation_fixture,
    _late_validation_plan,
    _sparse_plan,
    _sparse_plan_document,
    _worker_input_fixture,
)


def test_benchmark_preserves_catalog_independence_findings_and_measures_reads(tmp_path: Path) -> None:
    document = benchmark_fixture(tmp_path / "repository")
    nodes = document["plan"]["actual_worker_nodes"]
    assert Counter(node["mode"] for node in nodes) == {"audit": 9, "validation": 3, "independent-review": 1, "synthesis": 2}
    assert document["plan"]["routing_catalog_closed"]
    manifest = _trial(runtime, document, tmp_path / "trial")
    metrics = manifest["metrics"]
    assert len(manifest["findings"]) == 4
    assert len(manifest["receipts"]) == 9
    assert metrics["scripted_reads"]["source_file_reads"] == 18  # Independent review reads every source directly.
    assert metrics["scripted_reads"]["repeated_source_file_reads"] == 0
    assert metrics["coordinator_api_operations"] == 19
    assert metrics["model_review_seconds"] is None
    telemetry = manifest["dispatches"]["telemetry"]
    assert telemetry["source_demand"]["distinct_paths"] == 18
    assert telemetry["source_demand"]["repeated_file_reads"] > 0
    waves = telemetry["projected_waves"]
    completed: set[str] = set()
    by_id = {node["node_id"]: node for node in nodes}
    for wave in waves:
        assert 1 <= len(wave) <= 4
        assert all(set(by_id[node_id]["predecessors"]) <= completed for node_id in wave)
        completed.update(wave)
    assert completed == set(by_id)
    assert telemetry["observed_review_seconds"] is None


@pytest.mark.parametrize("field", ["worker_payload_digest", "worker_payload_path"])
def test_benchmark_rejects_mismatched_publication_receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    document = benchmark_fixture(tmp_path / "repository")
    publish = runtime.publish_worker_payload_bytes

    def mismatched_receipt(contract: dict[str, Any], content: bytes) -> dict[str, Any]:
        receipt = publish(contract, content)
        receipt[field] = "sha256:" + "0" * 64 if field == "worker_payload_digest" else str(tmp_path / "wrong-payload.json")
        return receipt

    monkeypatch.setattr(runtime, "publish_worker_payload_bytes", mismatched_receipt)
    with pytest.raises(ValueError, match="publication receipt does not match"):
        _trial(runtime, document, tmp_path / "trial")


def test_source_demand_counts_files_under_symlinked_root_without_following_escapes(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    content = b"source fixture\n"
    (repository / "sample.py").write_bytes(content)
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"outside fixture\n")
    (repository / "escape.py").symlink_to(outside)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(repository, target_is_directory=True)
    nodes = [{"mode": "audit", "coverage": ["sample.py", "escape.py"]}, {"mode": "independent-review", "coverage": ["sample.py"]}]

    demand = source_demand(nodes, linked_root)

    assert demand["distinct_source_bytes"] == len(content)
    assert demand["planned_source_bytes"] == 2 * len(content)
    assert demand["unavailable_paths"] == ["escape.py"]
    assert demand["overlapping_paths"] == {"sample.py": 2}


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_wave_projection_rejects_invalid_capacity(limit: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        projected_waves([], limit)


@pytest.mark.parametrize("ref", ["", "--output=unexpected-file"])
def test_benchmark_rejects_git_options_before_invocation(tmp_path: Path, ref: str) -> None:
    with pytest.raises(ValueError, match="not an option"):
        _baseline_runtime(tmp_path, ref)
    assert not list(tmp_path.iterdir())


def _preflight_request(tmp_path: Path) -> dict[str, Any]:
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], working_directories=(str(tmp_path),))
    return {
        "plan": _json_plan(replace(plan, coalesced_validation_units=(unit,))),
        "repository_root": str(tmp_path),
        "cache_paths": [],
        "command_policy": [{"command": "true", "disposition": "allowed", "reason": "read-only fixture"}],
        "execution_prerequisites": [{"node_id": unit.node_id, "executables": [sys.executable], "native_available": True, "reason": "current host"}],
    }


@pytest.mark.parametrize("defect", ["executable", "empty-executables", "native", "directory", "uninspected"])
def test_preflight_detects_executor_blockers_without_running_commands(tmp_path: Path, defect: str) -> None:
    request = _preflight_request(tmp_path)
    if defect == "executable":
        request["execution_prerequisites"][0]["executables"] = [str(tmp_path / "missing-executable")]
    elif defect == "empty-executables":
        request["execution_prerequisites"][0]["executables"] = []
    elif defect == "native":
        request["execution_prerequisites"][0].update(native_available=False, reason="Windows runner unavailable")
    elif defect == "directory":
        request["plan"]["coalesced_validation_units"][0]["working_directories"] = [str(tmp_path / "missing")]
    else:
        request.pop("execution_prerequisites")
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    assert report["units"][0]["execution_blockers"]
    assert report["units"][0]["repository_findings"] == []
    assert report["units"][0]["configuration_errors"] == []
    assert not list(tmp_path.iterdir())


def test_preflight_absent_permitted_output_is_ready_and_not_created(tmp_path: Path) -> None:
    request = _preflight_request(tmp_path)
    isolation_root = tmp_path.parent / f"{tmp_path.name}-isolated"
    artifact = ValidationArtifact(str(isolation_root / "never-created-output"), "build", "outside-repository", "isolated-output-directory")
    request["plan"]["coalesced_validation_units"][0].update(allowed_artifacts=[asdict(artifact)], isolation_root=str(isolation_root))
    report = runtime.preflight_validation(request)
    assert report["status"] == "ready"
    assert report["units"][0]["output_observations"] == [{"path": artifact.path, "exists": False, "repository_status": "outside-repository", "required": False}]
    assert not Path(artifact.path).exists()


@pytest.mark.parametrize("error_type", [OSError, ValueError])
def test_preflight_reports_unavailable_output_classification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]) -> None:
    request = _preflight_request(tmp_path)
    request["plan"]["coalesced_validation_units"][0]["expected_workspace_effects"] = ["output"]

    def unavailable_status(repository_root: Path, path: Path) -> str:
        message = "Git classification unavailable"
        raise error_type(message)

    monkeypatch.setattr(runtime, "_git_path_status", unavailable_status)
    report = runtime.preflight_validation(request)

    assert report["status"] == "blocked"
    assert report["units"][0]["configuration_errors"] == ["cannot inspect output output: Git classification unavailable"]
    assert report["units"][0]["output_observations"] == []


@pytest.mark.parametrize("escape", [False, True])
def test_preflight_resolves_isolated_relative_effects_and_rejects_escapes(tmp_path: Path, escape: bool) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    isolation_root = tmp_path / "isolated"
    isolation_root.mkdir()
    if escape:
        (isolation_root / "build").symlink_to(repository, target_is_directory=True)
    else:
        (isolation_root / "build").mkdir()
    (isolation_root / "build" / "output.txt").write_text("observed output", encoding="utf-8")
    request = _preflight_request(repository)
    request["plan"]["coalesced_validation_units"][0].update(
        requires_isolation=True, isolation_root=str(isolation_root), working_directories=[str(isolation_root)], expected_workspace_effects=["build/output.txt"]
    )

    report = runtime.preflight_validation(request)

    if escape:
        assert report["status"] == "blocked"
        assert any("inside the captured repository" in reason for reason in report["units"][0]["configuration_errors"])
    else:
        assert report["status"] == "ready"
        assert report["units"][0]["output_observations"] == [
            {"path": "build/output.txt", "exists": True, "repository_status": "outside-repository", "required": False}
        ]


@pytest.mark.parametrize("root_kind", ["missing", "inside-repository", "ancestor", "unrelated"])
def test_preflight_rejects_outside_artifacts_without_valid_isolation_root(tmp_path: Path, root_kind: str) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    request = _preflight_request(repository)
    roots = {"missing": None, "inside-repository": str(repository / "nested"), "ancestor": str(tmp_path), "unrelated": str(tmp_path / "unrelated")}
    artifact = ValidationArtifact(str(tmp_path / "isolated" / "output"), "build", "outside-repository", "isolated-output-directory")
    request["plan"]["coalesced_validation_units"][0].update(allowed_artifacts=[asdict(artifact)], isolation_root=roots[root_kind])

    report = runtime.preflight_validation(request)

    assert report["status"] == "blocked"
    assert any(f"cannot inspect output {artifact.path}:" in reason for reason in report["units"][0]["configuration_errors"])
    assert report["units"][0]["output_observations"] == []
    assert not Path(artifact.path).exists()


def test_planning_rejects_prose_effect_before_materialization() -> None:
    document = _sparse_plan_document()
    document["validation_requirements"][0]["expected_workspace_effects"] = ["writes build files and caches"]
    with pytest.raises(ValueError, match="expected_workspace_effects must name concrete ignored output paths"):
        validation_requirements_from_document(document, SKILL_ROOT.parents[2])


def test_successful_validation_may_leave_permitted_outputs_absent(tmp_path: Path) -> None:
    document, _entries = _worker_input_fixture(tmp_path / "original")
    plan = _sparse_plan()
    artifact = ValidationArtifact(str(tmp_path / "never-created"), "build", "outside-repository", "isolated-output-directory")
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(artifact,))
    plan = replace(plan, coalesced_validation_units=(unit,))
    dispatches = runtime.materialize_dispatches({**document, "plan": _json_plan(plan), "artifact_store": str(tmp_path / "absent")})
    entry = next(item for item in dispatches["dispatches"] if item["node_id"] == unit.node_id)
    snapshot = runtime.capture_workspace_snapshot(entry["dispatch"])["records"]
    dispatch = {
        **entry["dispatch"],
        "before_state": document["source_state"],
        "after_state": document["source_state"],
        "workspace_before": snapshot,
        "workspace_after": snapshot,
    }
    payload = _execution_payload(entry, "passed", 0, "1s")
    _content, metadata = runtime.compile_validation({"dispatch": dispatch, "payload": payload})
    assert metadata["evidence"]["status"] == "passed"
    absent = metadata["normalized_record"]["artifacts"][0]
    assert absent["artifact_digest_mode"] == "absent-v1"
    assert not Path(artifact.path).exists()
    payload["artifacts"] = [absent]
    with pytest.raises(ValueError, match="claims an artifact absent"):
        runtime.compile_validation({"dispatch": dispatch, "payload": payload})


@pytest.mark.parametrize("declared_prerequisites", [False, True])
def test_commandless_hosted_requirement_preflights_as_blocked(tmp_path: Path, declared_prerequisites: bool) -> None:
    request = _preflight_request(tmp_path)
    unit = request["plan"]["coalesced_validation_units"][0]
    unit.update(commands=[], working_directories=[], canonical_recipe=None, planning_blocker="staged bytes have no hosted commit")
    request["execution_prerequisites"][0]["executables"] = []
    if not declared_prerequisites:
        request["execution_prerequisites"] = []
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    assert any("no hosted commit" in reason for reason in report["units"][0]["execution_blockers"])
    assert not any("executor" in reason for reason in report["units"][0]["execution_blockers"])
    assert report["units"][0]["configuration_errors"] == []


def test_expansion_continuation_can_reuse_previous_ready_directory(tmp_path: Path) -> None:
    _plan, _sources, lifecycle, dispatches, capture, journal = _late_validation_fixture(tmp_path)
    request = {**lifecycle, "artifact_store": str(tmp_path / "expanded")}
    args = Namespace(dispatches=dispatches, current_capture=capture, journal=journal)
    ready_dir = tmp_path / "ready"
    initial_input = tmp_path / "initial.json"
    initial_input.write_text(json.dumps({key: request[key] for key in ("plan", "source_state")}), encoding="utf-8")
    assert (
        runtime.main(
            [
                "next-ready",
                "--input",
                str(initial_input),
                "--journal",
                str(args.journal),
                "--dispatches",
                str(args.dispatches),
                "--current-capture",
                str(args.current_capture),
                "--output-dir",
                str(ready_dir),
            ]
        )
        == 0
    )
    original = {path: path.read_bytes() for path in ready_dir.iterdir()}
    expanded = runtime.reconcile_validation_requirements(
        {key: request[key] for key in ("plan", "source_state", "artifact_store")} | {"validation_requirements": [_late_validation_plan()]}, args
    )
    continuation = expanded["continuation"]
    assert Path(continuation["next_ready_output_dir"]) != ready_dir
    argv = [
        "next-ready",
        "--input",
        continuation["lifecycle_input_path"],
        "--journal",
        continuation["journal_path"],
        "--dispatches",
        continuation["dispatches_path"],
        "--current-capture",
        continuation["current_capture_path"],
        "--output-dir",
        str(ready_dir),
    ]
    assert runtime.main(argv) == 0
    assert len(list(ready_dir.iterdir())) == len(original) + 1
    assert all(path.read_bytes() == content for path, content in original.items())
    assert runtime.main(argv) == 0
    assert len(list(ready_dir.iterdir())) == len(original) + 1
    assert expanded["retained_node_ids"]


def test_combined_publication_preserves_binding_on_wrong_approval(tmp_path: Path) -> None:
    _document, dispatches = _worker_input_fixture(tmp_path)
    entry = next(item for item in dispatches["dispatches"] if item["dispatch"].get("mode") == "audit")
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    content = json.dumps(_compact_audit_payload(entry)).encode()
    with pytest.raises(ValueError, match="approval"):
        runtime.publish_worker_payload_bytes(contract, content, approval_identity="wrong-identity")
    assert not Path(entry["worker_payload_path"]).exists()
    receipt = runtime.publish_worker_payload_bytes(contract, content)
    assert receipt["artifact_write_review"]["approval_identity"]
    assert Path(entry["worker_payload_path"]).read_bytes() == content
