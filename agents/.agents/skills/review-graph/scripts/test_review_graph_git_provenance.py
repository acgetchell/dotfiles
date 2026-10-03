"""Capture and inherited audit provenance across content-equivalent staging."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from review_graph_reuse import source_snapshot
from review_graph_runtime import JournalEventRequest, advance_after_mutation, append_journal_event, compile_review, resume_after_external_metadata
from test_review_graph_git import _accept, _discovery_payload
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _baseline_mutation_fixture, _run_test_git
from test_review_graph_transitions import _materialize, _payload, _staging_fixture


@pytest.mark.parametrize("absolute", [False, True])
def test_symlink_target_change_must_recheck_source_read(tmp_path: Path, absolute: bool) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 2\n")
    dependency = tmp_path / "external.toml"
    dependency.write_text('version = "1"\n')
    link = repository / "context.toml"
    link.symlink_to(dependency)
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    request = {**lifecycle, "journal_path": str(tmp_path / "old.jsonl")}
    payload = _discovery_payload(entry)
    payload["nearby_contract_owners"] = [str(link) if absolute else "context.toml"]
    _accept(request, entry, payload)
    dependency.write_text('version = "2"\n')
    _run_test_git(git, "-C", str(repository), "add", "tool.py")
    new_capture = _scope_data(git, repository, "baseline", None, ())
    assert capture["repository_path_fingerprints"] == new_capture["repository_path_fingerprints"]
    assert capture["repository_symlink_paths"] == new_capture["repository_symlink_paths"] == ["context.toml"]
    result = resume_after_external_metadata(
        {**request, "previous_capture": capture, "new_capture": new_capture, "dispatches_path": str(dispatches), "artifact_store": str(tmp_path / "resumed")}
    )
    decision = next(item for item in result["node_decisions"] if item["node_id"] == entry["node_id"])
    assert decision["disposition"] == "recheck"
    assert decision["reasons"][0]["path"] == payload["nearby_contract_owners"][0]
    assert "symlink" in decision["reasons"][0]["reason"]
    dispatch = {
        **entry["dispatch"],
        "external_metadata_transitions": result["lifecycle_input"]["external_metadata_transitions"],
        "before_state": request["source_state"],
        "after_state": result["current_source_state"],
    }
    # Acceptance and later replay use captured types, even after the live link disappears.
    link.unlink()
    with pytest.raises(ValueError, match="symlink"):
        compile_review({"dispatch": dispatch, "payload": payload})


@pytest.mark.parametrize("change", ["missing", "null", "old-version"])
def test_incomplete_or_obsolete_capture_requires_recapture(tmp_path: Path, change: str) -> None:
    _git, _repository, request, _audit, _entries = _staging_fixture(tmp_path)
    capture = request["previous_capture"]
    if change == "missing":
        capture.pop("repository_symlink_paths")
    elif change == "null":
        capture["repository_symlink_paths"] = None
    else:
        capture["repository_state_format"] = "review-graph-path-snapshot-v2"
    with pytest.raises(ValueError, match="recapture required"):
        source_snapshot(capture).verify()


def _partial_audit(tmp_path: Path, kind: str, *, stage_before_repair: bool = False) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "pyproject.toml").write_text('[project]\nname = "example"\nversion = "0.1.0"\n')
    _run_test_git(git, "-C", str(repository), "add", "pyproject.toml")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "manifest")
    (repository / "tool.py").write_text("value = 2\n")
    template["routing_overrides"].append(
        {
            "catalog_id": "python.cli",
            "disposition": "selected",
            "reason": "CLI and manifest contracts",
            "applicability_evidence": ["tool.py"],
            "owners": ["python"],
            "review_surface": ["tool.py", "pyproject.toml"],
        }
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("skill_id") == "python-cli-review")
    payload = _discovery_payload(entry, "git diff -- tool.py")
    if kind == "index":
        payload["git_dependencies"] = [{"kind": "index", "reason": "Implementation staging is part of the reviewed contract."}]
        payload["commands_executed"] = []
    elif kind == "legacy":
        payload["git_sensitive"] = True
    elif kind == "unclassified":
        payload.pop("git_dependencies")
    payload["coverage_units"] = [
        {"unit_id": path, "owned_paths": [path], "dependency_paths": [], "dependency_uncertainty": "", "finding_indices": []}
        for path in ("tool.py", "pyproject.toml")
    ]
    source = _accept({**lifecycle, "journal_path": str(tmp_path / "original.jsonl")}, entry, payload)
    previous_capture = capture
    transitions = []
    if stage_before_repair:
        _run_test_git(git, "-C", str(repository), "add", "tool.py")
        previous_capture = _scope_data(git, repository, "baseline", None, ())
        transitions = [{"before": capture, "after": previous_capture}]
    (repository / "pyproject.toml").write_text('[project]\nname = "example"\nversion = "0.2.0"\n')
    repaired_capture = _scope_data(git, repository, "baseline", None, ())
    advanced = advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": previous_capture,
            "new_capture": repaired_capture,
            "external_metadata_transitions": transitions,
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": ["pyproject.toml"],
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "sources": [source],
        }
    )
    delta = next(item for item in advanced["dispatch_set"]["dispatches"] if item["dispatch"].get("skill_id") == "python-cli-review")
    if not stage_before_repair:
        assert delta["dispatch"]["coverage_reuse"]["units"][0]["disposition"] == "reused"
    return git, repository, repaired_capture, advanced, delta


@pytest.mark.parametrize("kind", ["index", "source-discovery"])
def test_staging_before_repair_invalidates_only_metadata_sensitive_coverage(tmp_path: Path, kind: str) -> None:
    _git, _repository, _capture, advanced, delta = _partial_audit(tmp_path, kind, stage_before_repair=True)
    if kind == "source-discovery":
        assert delta["dispatch"]["coverage_reuse"]["units"][0]["disposition"] == "reused"
    else:
        assert "coverage_reuse" not in delta["dispatch"]
        assert set(delta["dispatch"]["owned_paths"]) == {"tool.py", "pyproject.toml"}
        decision = next(item for item in advanced["coverage_reuse_decisions"] if item["node_id"] == delta["node_id"])
        assert all(unit["disposition"] == "recheck" and "index" in unit["reason"] for unit in decision["units"])


@pytest.mark.parametrize("kind", ["index", "legacy", "unclassified", "source-discovery"])
@pytest.mark.parametrize("accepted", [False, True])
def test_partial_reuse_retains_git_dependencies_at_resume_and_compilation(tmp_path: Path, kind: str, accepted: bool) -> None:
    git, repository, repaired_capture, advanced, delta = _partial_audit(tmp_path, kind)
    lifecycle = json.loads(Path(advanced["lifecycle_input_path"]).read_text())
    if accepted:
        _accept({**lifecycle, "journal_path": advanced["journal_path"]}, delta, _payload(["pyproject.toml"]))
    else:
        append_journal_event(Path(advanced["journal_path"]), lifecycle, JournalEventRequest(delta["node_id"], "in-flight"))
    _run_test_git(git, "-C", str(repository), "add", "tool.py")
    resumed = resume_after_external_metadata(
        {
            **lifecycle,
            "dispatches_path": advanced["dispatches_path"],
            "journal_path": advanced["journal_path"],
            "previous_capture": repaired_capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "artifact_store": str(tmp_path / "resumed"),
        }
    )
    decision = next(item for item in resumed["node_decisions"] if item["node_id"] == delta["node_id"])
    if kind == "source-discovery":
        assert decision["disposition"] == "preserved"
        assert decision["discovery_reconciliation"]["inherited"]["commands"] == ["git diff -- tool.py"]
    else:
        assert decision["disposition"] == "recheck"
        assert decision["reasons"][0]["evidence_id"] == delta["dispatch"]["coverage_reuse"]["evidence_id"]
        dispatch = {
            **delta["dispatch"],
            "external_metadata_transitions": resumed["lifecycle_input"]["external_metadata_transitions"],
            "before_state": resumed["current_source_state"],
            "after_state": resumed["current_source_state"],
        }
        # Fresh manifest reads cannot refresh the inherited implementation judgment.
        with pytest.raises(ValueError, match="current metadata state"):
            compile_review({"dispatch": dispatch, "payload": _payload(["pyproject.toml"])})
        fresh = next(item for item in resumed["dispatch_set"]["dispatches"] if item["node_id"] == delta["node_id"])
        assert resumed["discarded_coverage_node_ids"] == [delta["node_id"]]
        assert "coverage_reuse" not in fresh["dispatch"]
        fresh_dispatch = {**fresh["dispatch"], "before_state": resumed["current_source_state"], "after_state": resumed["current_source_state"]}
        content, metadata = compile_review({"dispatch": fresh_dispatch, "payload": _payload(fresh["dispatch"]["owned_paths"])})
        assert "coverage_reuse" not in metadata["normalized_record"]
        Path(fresh["artifact_path"]).write_bytes(content)
        Path(fresh["metadata_path"]).write_text(json.dumps(metadata))
        append_journal_event(
            Path(resumed["journal_path"]),
            resumed["lifecycle_input"],
            JournalEventRequest(fresh["node_id"], "accepted", source={key: fresh[key] for key in ("artifact_path", "metadata_path")}),
        )


def test_partial_reuse_cannot_omit_original_git_context(tmp_path: Path) -> None:
    _git, _repository, _capture, advanced, delta = _partial_audit(tmp_path, "index")
    dispatch = deepcopy(delta["dispatch"])
    dispatch["before_state"] = dispatch["after_state"] = advanced["new_source_state"]
    dispatch["coverage_reuse"].pop("original_git_context")
    with pytest.raises(ValueError, match="original immutable"):
        compile_review({"dispatch": dispatch, "payload": _payload(["pyproject.toml"])})
