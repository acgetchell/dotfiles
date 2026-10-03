"""Metadata invalidation across whole-audit reuse and subsequent content repairs."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from review_graph_runtime import (
    _graph_plan,
    advance_after_mutation,
    compile_review,
    finalize_proof,
    next_ready_nodes,
    read_execution_journal,
    resume_after_external_metadata,
)
from test_review_graph_git import _discovery_payload
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compile_repair_fixture_entry,
    _mutation_with_audit_source,
    _run_test_git,
)
from test_review_graph_transitions import _materialize, _payload


def _git_payload(entry: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "source-discovery":
        return _discovery_payload(entry)
    return {**_payload(entry["dispatch"]["owned_paths"]), "git_dependencies": [{"kind": kind, "reason": "Staging is part of the reviewed contract."}]}


@pytest.mark.parametrize("kind", ["index", "source-discovery"])
def test_staging_after_whole_audit_reuse_completes_with_current_evidence(tmp_path: Path, kind: str) -> None:
    request, original_entry, original_source = _mutation_with_audit_source(tmp_path)
    content, metadata = compile_review(
        {
            "dispatch": {**original_entry["dispatch"], "before_state": request["source_state"], "after_state": request["source_state"]},
            "payload": _git_payload(original_entry, kind),
        }
    )
    Path(original_source["artifact_path"]).write_bytes(content)
    Path(original_source["metadata_path"]).write_text(json.dumps(metadata))
    original_bytes = {key: Path(path).read_bytes() for key, path in original_source.items()}
    advanced = advance_after_mutation(request)
    old_id = original_entry["dispatch"]["evidence_id"]
    assert advanced["reused_evidence_ids"] == [old_id]
    git = shutil.which("git")
    assert git is not None
    repository = Path(request["new_capture"]["repository_root"])
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    resumed = resume_after_external_metadata(
        {
            **json.loads(Path(advanced["lifecycle_input_path"]).read_text()),
            "previous_capture": advanced["capture"],
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "dispatches_path": advanced["dispatches_path"],
            "journal_path": advanced["journal_path"],
            "artifact_store": str(tmp_path / "resumed"),
        }
    )
    replacement = [item for item in resumed["dispatch_set"]["dispatches"] if item["dispatch"].get("skill_id") == original_entry["dispatch"]["skill_id"]]
    if kind == "index":
        assert len(replacement) == 1
        assert replacement[0]["dispatch"]["owned_paths"] == ["tool.py"]
        assert replacement[0]["dispatch"]["evidence_id"] != old_id
        decision = next(item for item in resumed["node_decisions"] if item["node_id"] == replacement[0]["node_id"])
        assert decision["replaced_evidence_ids"] == [old_id]
        assert decision["reasons"][0]["evidence_id"] == old_id
    else:
        assert not replacement

    lifecycle = {**json.loads(Path(resumed["lifecycle_input_path"]).read_text()), "current_source_state": resumed["current_source_state"]}
    plan = _graph_plan(lifecycle["plan"])
    sources = []
    executed = []
    journal = Path(resumed["journal_path"])
    for _ in range(plan.complete_node_count + 1):
        events, _states, _head = read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = next_ready_nodes(lifecycle, journal_events=events, dispatch_set=resumed["dispatch_set"])
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready
        for entry in ready["ready_dispatches"]:
            sources.append(_compile_repair_fixture_entry(entry, lifecycle, journal))
            executed.append(entry["node_id"])
    else:
        pytest.fail("metadata continuation did not complete within its node bound")
    proof = finalize_proof({**lifecycle, "sources": sources})
    assert proof["graph_proof_status"] == "complete", proof["blockers"]
    accepted = proof["proof"]["accepted_review_evidence_ids"]
    if kind == "index":
        assert old_id not in accepted
        assert replacement[0]["dispatch"]["evidence_id"] in accepted
        assert replacement[0]["node_id"] in executed
    else:
        assert old_id in accepted
        assert old_id in ready["reused_evidence_ids"]
    for key, path in original_source.items():
        assert Path(path).read_bytes() == original_bytes[key]


@pytest.mark.parametrize(("kind", "fresh"), [("index", False), ("source-discovery", False), ("index", True)])
def test_repair_after_staging_reuses_only_valid_metadata_judgments(tmp_path: Path, kind: str, fresh: bool) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 2\n")
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    _run_test_git(git, "-C", str(repository), "add", "tool.py")
    staged = _scope_data(git, repository, "baseline", None, ())
    transitions = [{"before": capture, "after": staged}]
    state = (
        [staged[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")] if fresh else lifecycle["source_state"]
    )
    content, metadata = compile_review(
        {
            "dispatch": {**entry["dispatch"], "before_state": state, "after_state": state, "external_metadata_transitions": transitions if fresh else []},
            "payload": _git_payload(entry, kind),
        }
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    (repository / "state.rs").write_text("pub fn state() { assert!(true); }\n")
    advanced = advance_after_mutation(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "repair"),
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": ["state.rs"],
            "state_verification_command": "capture_scope.py --mode baseline",
            "sources": [source],
            "previous_capture": staged,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "external_metadata_transitions": transitions,
        }
    )
    old_id = entry["dispatch"]["evidence_id"]
    assert (old_id in advanced["reused_evidence_ids"]) is (fresh or kind == "source-discovery")
    if not fresh and kind == "index":
        decision = next(item for item in advanced["reuse_decisions"] if item["node_id"] == entry["node_id"])
        assert decision["reason_code"] == "metadata-dependencies-changed"
    else:
        # Reloading the persisted plan must accept valid old artifacts too.
        lifecycle = json.loads(Path(advanced["lifecycle_input_path"]).read_text())
        ready = next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=(), dispatch_set=advanced["dispatch_set"])
        assert old_id in ready["reused_evidence_ids"]
