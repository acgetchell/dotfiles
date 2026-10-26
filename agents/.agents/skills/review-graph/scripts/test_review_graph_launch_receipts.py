"""Large real CLI receipts retain every launch identity in immutable artifacts."""

import json
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_integrity import digest_bytes
from test_review_graph_runtime import SKILL_ROOT, _baseline_mutation_fixture, _run_test_git
from test_review_graph_sessions import _cli


def _large_bootstrap(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """Capture a mixed repository and route every matched leaf through the real CLI."""
    git, repository, _template, _capture, _plan = _baseline_mutation_fixture(tmp_path, instructions=True)
    for name, content in {
        "kernel.cpp": "double square(double value) { return value * value; }\n",
        "include/kernel.hpp": "double square(double value);\n",
        "CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\nproject(fixture)\n",
        "tests/kernel.cpp": "void test_square() {}\n",
        "src/lib.rs": "pub fn square(value: f64) -> f64 { value * value }\n",
        "tests/square.rs": "#[test] fn square() { assert_eq!(2 * 2, 4); }\n",
        "scripts/check.py": "def square(value):\n    return value * value\n",
        "README.md": "# Numerical fixture\n\nDeterministic scientific computations.\n",
        "Cargo.toml": '[package]\nname = "fixture"\nversion = "0.1.0"\n',
        "pyproject.toml": '[project]\nname = "fixture"\nversion = "0.1.0"\n',
        "justfile": "ci:\n    true\n",
    }.items():
        target = repository / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "mixed release fixture")
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(_scope_data(git, repository, "baseline", None, ())))
    scripts = SKILL_ROOT / "review-graph/scripts"
    choices_path = tmp_path / "operator.json"
    (tmp_path / "proof").mkdir()
    preparation = json.loads(
        _cli(
            scripts / "review_graph_starter.py",
            "baseline-release",
            "--capture",
            str(capture_path),
            "--artifact-root",
            str(tmp_path / "proof"),
            "--output",
            str(choices_path),
        ).stdout
    )
    discovery = json.loads(Path(preparation["discovery"]["path"]).read_bytes())
    choices = json.loads(choices_path.read_bytes())
    choices.update(
        authorization="review-only",
        ignored_outputs=[],
        command_policy={"disposition": "allowed", "reason": "Scripted CLI transport fixture; the gate is not executed."},
        execution_prerequisites={"executables": ["env"], "native_available": True, "reason": "POSIX transport fixture."},
        routing_overrides=[
            {
                "catalog_id": item["catalog_id"],
                "disposition": "selected",
                "reason": "Scripted fixture retains every matched leaf's launch identity.",
                "applicability_evidence": item["matched_paths"],
                "review_surface": item["matched_paths"],
                "owners": ["documentation" if item["catalog_id"].startswith("docs.") else item["catalog_id"].split(".")[0]],
            }
            for item in discovery["routing_projection"]["entries"]
            if item["target_kind"] == "leaf" and item["matched_paths"] and not item["catalog_id"].startswith("repo.")
        ],
    )
    choices_path.write_text(json.dumps(choices))
    bundle_path = tmp_path / "bootstrap.json"
    _cli(scripts / "review_graph_bootstrap.py", "--capture", str(capture_path), "--starter-config", str(choices_path), "--output", str(bundle_path))
    return bundle_path, json.loads(bundle_path.read_bytes())


def _read_reference(reference: dict[str, str]) -> dict[str, Any]:
    path = Path(reference["path"])
    content = path.read_bytes()
    assert digest_bytes(content) == reference["digest"]
    assert path.stat().st_mode & 0o222 == 0
    return json.loads(content)


def _assert_launches(receipt: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    assert {"dispatches", "ready_dispatches", "launch_manifest"}.isdisjoint(receipt)
    manifest = _read_reference(receipt["launch_manifest_reference"])
    assert len(manifest["nodes"]) == receipt["node_count"] == len(entries)
    assert [node["node_id"] for node in manifest["nodes"]] == [entry["node_id"] for entry in entries]
    for node, entry in zip(manifest["nodes"], entries, strict=True):
        dispatch = entry["dispatch"]
        for key in ("skill_id", "skill_path", "mode", "execution_location"):
            assert node[key] == dispatch[key]
        assert node["result_contract"] == entry["result_contract"]
        view = _read_reference(node["execution_view"])
        canonical = _read_reference(view["canonical_input"])
        assert canonical == entry
        for key in ("executor_requirements", "timing_prerequisite"):
            if key in dispatch:
                assert node[key] == dispatch[key]
    assert manifest["next_operation_inputs"] == receipt["next_operation_inputs"]
    return manifest


@pytest.mark.parametrize("worker_limit", [3, 64])
def test_large_cli_launch_receipts(tmp_path: Path, worker_limit: int) -> None:
    bundle_path, bundle = _large_bootstrap(tmp_path)
    nodes = bundle["plan"]["actual_worker_nodes"]
    assert len(nodes) >= 44
    runtime = Path(bundle["runtime_snapshot"]["path"]).parent / "skills/review-graph/scripts/review_graph_runtime.py"
    dispatches_path = tmp_path / "dispatches.json"
    arguments = ("materialize-dispatches", "--input", str(bundle_path), "--output", str(dispatches_path))
    materialization = _cli(runtime, *arguments)
    receipt = json.loads(materialization.stdout)
    dispatches = json.loads(dispatches_path.read_bytes())
    assert receipt["output"]["digest"] == digest_bytes(dispatches_path.read_bytes())
    assert [entry["node_id"] for entry in dispatches["dispatches"]] == [node["node_id"] for node in nodes]
    assert dispatches["source_state"] == bundle["lifecycle_input"]["source_state"]
    manifest = _assert_launches(receipt, dispatches["dispatches"])
    assert manifest["next_command"] == receipt["next_command"]
    assert json.loads(_cli(runtime, *arguments, "--full-output").stdout) == dispatches
    capacity_path = Path(receipt["scheduler_prerequisite"]["path"])
    capacity_path.write_text(json.dumps({"source": "fixture aggregate host capacity", "concurrent_worker_limit": worker_limit, "active_workers": 0}))
    schedule_arguments = receipt["next_command"][receipt["next_command"].index("schedule-ready") :]
    scheduling = _cli(runtime, *schedule_arguments)
    schedule_receipt = json.loads(scheduling.stdout)
    scheduled = _read_reference(schedule_receipt["output"])
    assert scheduled["ready_dispatches"]
    if worker_limit == 64:
        assert len(scheduled["ready_dispatches"]) >= 40
    _assert_launches(schedule_receipt, scheduled["ready_dispatches"])
    for key in ("status", "blockers", "capacity_state", "waiting", "preflight_blocked_nodes"):
        assert schedule_receipt[key] == scheduled[key]
    for key in ("worker", "reserved", "deferred"):
        assert schedule_receipt["node_counts"][key] == len(scheduled[f"{key}_node_ids"])
        assert f"{key}_node_ids" not in schedule_receipt
    assert schedule_receipt["continuation"]["path"] == scheduled["continuation_path"]
    assert json.loads(_cli(runtime, *schedule_arguments, "--full-output").stdout) == scheduled
    # These measure serialized UTF-8 transport only, not tokens, cost or review quality.
    metrics = {
        "node_count": len(nodes),
        "selected_node_count": len(scheduled["ready_dispatches"]),
        "materialization_stdout_bytes": len(materialization.stdout),
        "scheduling_stdout_bytes": len(scheduling.stdout),
        "materialization_artifact_bytes": dispatches_path.stat().st_size,
        "scheduling_artifact_bytes": Path(schedule_receipt["output"]["path"]).stat().st_size,
        "model_tokens": None,
        "provider_cost": None,
        "review_quality": None,
    }
    assert metrics["materialization_stdout_bytes"] < 6000, metrics
    assert metrics["scheduling_stdout_bytes"] < 12000, metrics
    print(json.dumps(metrics, sort_keys=True))
