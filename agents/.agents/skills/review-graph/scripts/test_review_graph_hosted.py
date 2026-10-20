"""Hosted success covers only the matching committed source."""

from typing import TYPE_CHECKING

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_hosted import hosted_coverage
from review_graph_plan import plan_from_document
from review_graph_reuse import source_snapshot
from test_review_graph_commit import _save, _validation_payload
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _baseline_mutation_fixture, _run_test_git
from test_review_graph_transitions import _materialize
from test_support_review_graph import _prepare_fixture_timing

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("mutation", ["none", "dirty", "untracked", "branch"])
def test_hosted_coverage_preserves_baseline_success_and_source_gap(tmp_path: Path, mutation: str) -> None:
    git, repository, _template, initial, _plan = _baseline_mutation_fixture(tmp_path)
    if mutation == "dirty":
        (repository / "tool.py").write_text("value = 2\n")
    elif mutation == "untracked":
        (repository / "new.py").write_text("new = True\n")
    elif mutation == "branch":
        _run_test_git(git, "-C", str(repository), "switch", "-c", "review-metadata")
    current = source_snapshot(_scope_data(git, repository, "baseline", None, ()))
    results = [
        {"name": "CI", "target": target, "head_sha": initial["head"], "conclusion": "success", "url": "https://example.com/run/1"}
        for target in ("ubuntu", "macos", "windows")
    ]
    limitations = ["This committed baseline does not test the uncommitted repair."] if mutation in {"dirty", "untracked"} else []
    summary = hosted_coverage({"status": "passed", "native_ci": results, "limitations": limitations}, current)
    assert summary["results"] == results
    assert summary["observed_head_shas"] == [initial["head"]]
    assert summary["tested_targets"] == ["macos", "ubuntu", "windows"]
    assert summary["limitations"] == limitations
    assert summary["covered_source_identity"][0]["git_tree_id"] == initial["repository_git_tree_id"]
    assert summary["delivered_source_status"] == ("passed" if mutation in {"none", "branch"} else "pending")
    assert summary["coverage_status"] == ("current-source" if mutation in {"none", "branch"} else "committed-baseline-only")


def test_unstructured_hosted_observation_cannot_claim_delivered_coverage() -> None:
    summary = hosted_coverage({"status": "passed", "limitations": ["Observed a green workflow."]}, None)
    assert summary["delivered_source_status"] == "pending"
    assert summary["coverage_status"] == "unverified"


@pytest.mark.parametrize("dirty", [False, True])
def test_delivery_reports_baseline_result_and_outstanding_repair_ci(tmp_path: Path, dirty: bool) -> None:
    git, repository, template, baseline, _plan = _baseline_mutation_fixture(tmp_path)
    if dirty:
        (repository / "tool.py").write_text("value = 2\n")
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, dispatches, _path = _materialize(tmp_path, capture, plan)
    lifecycle.update(capture=capture, current_source_state=lifecycle["source_state"])
    entry = next(item for item in dispatches["dispatches"] if item["dispatch"]["mode"] == "validation")
    _prepare_fixture_timing(entry)
    payload = _validation_payload(entry)
    payload["native_ci"] = [
        {"name": "CI", "target": target, "head_sha": baseline["head"], "conclusion": "success", "url": "https://example.com/run"}
        for target in ("linux", "macos", "windows")
    ]
    payload["limitations"] = ["The uncommitted repair has no hosted result."] if dirty else []
    source = _save(entry, lifecycle, tmp_path / "journal.jsonl", payload)
    report = runtime.report_delivery({**lifecycle, "sources": [source]})
    hosted = report["hosted_ci"][0]
    assert hosted["status"] == "passed"
    assert hosted["limitations"] == payload["limitations"]
    assert hosted["observer_platform"] == entry["dispatch"]["validation_unit"]["platform"]
    assert hosted["tested_targets"] == ["linux", "macos", "windows"]
    assert hosted["delivered_source_status"] == ("pending" if dirty else "passed")
    assert bool(report["outstanding_hosted_ci"]) == dirty
    assert any("required validation" in blocker for blocker in report["blockers"]) == dirty
