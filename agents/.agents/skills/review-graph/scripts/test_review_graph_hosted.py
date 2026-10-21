"""Hosted outcomes apply only to the matching committed source."""

from typing import TYPE_CHECKING

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_hosted import hosted_coverage
from review_graph_plan import plan_from_document
from review_graph_reuse import source_snapshot
from test_capture_scope import _commit_all, _git, _init_repo
from test_review_graph_commit import _save, _validation_payload
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _baseline_mutation_fixture, _run_test_git
from test_review_graph_transitions import _materialize
from test_support_review_graph import _prepare_fixture_timing

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("mutation", ["none", "dirty", "untracked", "branch"])
@pytest.mark.parametrize(
    ("status", "conclusion", "expected_status"),
    [
        ("passed", "success", "passed"),
        ("reused", "success", "passed"),
        ("failed", "failure", "failed"),
        ("passed", "failure", "failed"),
        ("failed", "success", "failed"),
    ],
)
def test_hosted_coverage_preserves_outcomes_and_source_gap(tmp_path: Path, mutation: str, status: str, conclusion: str, expected_status: str) -> None:
    git, repository, _template, initial, _plan = _baseline_mutation_fixture(tmp_path)
    if mutation == "dirty":
        (repository / "tool.py").write_text("value = 2\n")
    elif mutation == "untracked":
        (repository / "new.py").write_text("new = True\n")
    elif mutation == "branch":
        _run_test_git(git, "-C", str(repository), "switch", "-c", "review-metadata")
    current = source_snapshot(_scope_data(git, repository, "baseline", None, ()))
    results = [
        {
            "name": "CI",
            "target": target,
            "head_sha": initial["head"],
            "conclusion": conclusion if target == "windows" else "success",
            "url": "https://example.com/run/1",
        }
        for target in ("ubuntu", "macos", "windows")
    ]
    limitations = ["This committed baseline does not test the uncommitted repair."] if mutation in {"dirty", "untracked"} else []
    summary = hosted_coverage({"status": status, "native_ci": results, "limitations": limitations}, current)
    assert summary["results"] == results
    assert summary["observed_head_shas"] == [initial["head"]]
    assert summary["tested_targets"] == ["macos", "ubuntu", "windows"]
    assert summary["limitations"] == limitations
    assert summary["covered_source_identity"][0]["git_tree_id"] == initial["repository_git_tree_id"]
    assert summary["delivered_source_status"] == (expected_status if mutation in {"none", "branch"} else "pending")
    assert summary["coverage_status"] == ("current-source" if mutation in {"none", "branch"} else "committed-baseline-only")
    if mutation in {"dirty", "untracked"}:
        assert summary["next_action"].startswith("Obtain matching hosted results")
    elif expected_status == "failed":
        assert summary["next_action"].startswith("Diagnose the failed hosted results")
    else:
        assert summary["next_action"] is None


def test_unstructured_hosted_observation_cannot_claim_delivered_coverage() -> None:
    summary = hosted_coverage({"status": "passed", "limitations": ["Observed a green workflow."]}, None)
    assert summary["delivered_source_status"] == "pending"
    assert summary["coverage_status"] == "unverified"


@pytest.mark.parametrize(
    "mutation", ["none", "unchecked-out", "tracked", "untracked", "commit", "index", "filtered", "parent-dirty", "parent-untracked", "parent-deleted"]
)
def test_hosted_coverage_compares_submodules_and_paths_outside_review_scope(tmp_path: Path, mutation: str) -> None:
    nested = tmp_path / "nested"
    _init_repo(nested)
    (nested / "source.txt").write_bytes(b"original\n")
    (nested / ".gitattributes").write_bytes(b"*.txt text eol=lf\n")
    _commit_all(nested)
    repository = tmp_path / "repository"
    _init_repo(repository)
    (repository / "parent.txt").write_bytes(b"original\n")
    _git(repository, "-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(nested), "vendor/nested")
    _commit_all(repository)
    head = _git(repository, "rev-parse", "HEAD").strip()
    checkout = repository / "vendor/nested"
    if mutation == "unchecked-out":
        _git(repository, "submodule", "deinit", "--force", "--all")
    elif mutation == "untracked":
        (checkout / "new.txt").write_bytes(b"new\n")
    elif mutation == "filtered":
        (checkout / "source.txt").write_bytes(b"original\r\n")
        assert _git(checkout, "diff", "--name-only", "HEAD") == ""
    elif mutation in {"tracked", "commit", "index"}:
        (checkout / "source.txt").write_bytes(b"changed\n")
        if mutation == "commit":
            _commit_all(checkout)
        elif mutation == "index":
            _git(checkout, "add", "source.txt")
            (checkout / "source.txt").write_bytes(b"original\n")
    elif mutation == "parent-dirty":
        (repository / "parent.txt").write_bytes(b"changed\n")
    elif mutation == "parent-untracked":
        (repository / "new.txt").write_bytes(b"new\n")
    elif mutation == "parent-deleted":
        (repository / "parent.txt").unlink()
    # Hosted coverage binds the entire repository, even when the review is narrow.
    current = source_snapshot(_scope_data("git", repository, "baseline", None, (".gitmodules",)))
    assert current.git_tree_id is None
    result = {"name": "CI", "target": "linux", "head_sha": head, "conclusion": "success", "url": "https://example.com/run"}
    summary = hosted_coverage({"status": "passed", "native_ci": [result]}, current)
    clean = mutation in {"none", "unchecked-out"}
    assert summary["coverage_status"] == ("current-source" if clean else "committed-baseline-only")
    assert summary["delivered_source_status"] == ("passed" if clean else "pending")
    assert (summary["next_action"] is None) == clean


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
