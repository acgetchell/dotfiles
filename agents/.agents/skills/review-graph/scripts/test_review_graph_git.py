"""Regression evidence for semantic Git dependencies across external staging."""

import json
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_git import git_dependency_blockers
from review_graph_receipts import stage_receipt
from review_graph_runtime import (
    JournalEventRequest,
    _load_evidence_source,
    _metadata_evidence_blockers,
    append_journal_event,
    compile_review,
    main,
    resume_after_external_metadata,
)
from test_review_graph_runtime import _publish_worker_bytes, _run_test_git
from test_review_graph_transitions import _payload, _staging_fixture


def _discovery_payload(audit: dict[str, Any], command: str = "git --no-pager diff -- tool.py state.rs") -> dict[str, Any]:
    return {
        **_payload(audit["dispatch"]["owned_paths"]),
        "commands_executed": [command],
        "git_dependencies": [{"kind": "source-discovery", "command": command, "reason": "Located changes; judgments use the inspected worktree files."}],
    }


def _accept(request: dict[str, Any], entry: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
    state = request["source_state"]
    content, metadata = compile_review({"dispatch": {**entry["dispatch"], "before_state": state, "after_state": state}, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source: dict[str, str] = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}
    append_journal_event(Path(request["journal_path"]), request, JournalEventRequest(entry["node_id"], "accepted", source=source))
    return source


@pytest.mark.parametrize("staging", ["all", "subset", "mixed"])
@pytest.mark.parametrize("mode", ["baseline", "worktree"])
def test_source_discovery_preserves_accepted_bytes_and_explains_each_node(tmp_path: Path, staging: str, mode: str) -> None:
    git, repository, request, audit, entries = _staging_fixture(tmp_path, staging=staging, mode=mode, independent=True)
    source = _accept(request, audit, _discovery_payload(audit))
    originals = {key: Path(path).read_bytes() for key, path in source.items()}
    result = resume_after_external_metadata(request)
    assert audit["node_id"] in result["preserved_node_ids"]
    assert result["node_counts"]["preserved"] == 1
    assert result["node_counts"]["recheck"] == len(entries["dispatches"]) - 1
    decisions = {item["node_id"]: item for item in result["node_decisions"]}
    reconciliation = decisions[audit["node_id"]]["discovery_reconciliation"]
    assert reconciliation["commands"] == _discovery_payload(audit)["commands_executed"]
    assert reconciliation["head"] == request["previous_capture"]["head"] == request["new_capture"]["head"]
    assert reconciliation["before_worktree_fingerprint"] == reconciliation["after_worktree_fingerprint"]
    for entry in entries["dispatches"]:
        node_mode = entry["dispatch"].get("mode", "validation")
        if node_mode in {"validation", "synthesis", "independent-review"}:
            assert decisions[entry["node_id"]]["disposition"] == "recheck"
            assert decisions[entry["node_id"]]["reasons"][0]["reason_code"] == f"{node_mode}-policy"
    for key, path in source.items():
        assert Path(path).read_bytes() == originals[key]
    _kind, _expectation, _evidence, _content, record = _load_evidence_source(source, require_normalized=True)
    assert record is not None
    assert not _metadata_evidence_blockers(result["lifecycle_input"], [record])
    assert _scope_data(git, repository, request["new_capture"]["capture_mode"], None, ())["index_fingerprint"] == request["new_capture"]["index_fingerprint"]
    output = tmp_path / "result.json"
    output.write_text(json.dumps(result))
    receipt = stage_receipt("resume-after-external-metadata", output, result)
    assert receipt["node_counts"] == result["node_counts"]
    assert receipt["recheck_reason_counts"] == result["recheck_reason_counts"]


@pytest.mark.parametrize("timing", ["before", "across", "after", "unstaged"])
def test_inflight_discovery_compiles_through_real_cli(tmp_path: Path, timing: str) -> None:
    git, repository, request, audit, _entries = _staging_fixture(tmp_path)
    payload = _discovery_payload(audit, "git --no-pager diff --cached --stat")
    _publish_worker_bytes(audit, json.dumps(payload).encode())
    result = resume_after_external_metadata(request)
    assert result["node_counts"]["in_flight_pending_verification"] == 1
    before_capture = request["previous_capture"]
    if timing == "unstaged":
        before_capture = request["new_capture"]
        _run_test_git(git, "-C", str(repository), "restore", "--staged", "tool.py")
        result = resume_after_external_metadata(
            {
                **result["lifecycle_input"],
                "dispatches_path": result["dispatches_path"],
                "journal_path": result["journal_path"],
                "previous_capture": before_capture,
                "new_capture": _scope_data(git, repository, "baseline", None, ()),
                "artifact_store": str(tmp_path / "unstaged-again"),
            }
        )
        assert result["current_source_state"] == request["source_state"]
    before = tmp_path / "before.json"
    before.write_text(json.dumps(before_capture))
    assert (
        main(
            [
                "compile-node",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--node-id",
                audit["node_id"],
                "--before-capture",
                result["capture_path"] if timing == "after" else str(before),
                "--after-capture",
                str(before) if timing == "before" else result["capture_path"],
                "--output",
                str(tmp_path / "compiled.json"),
            ]
        )
        == 0
    )
    metadata = json.loads(Path(audit["metadata_path"]).read_text())
    assert metadata["normalized_record"]["git_dependencies"] == payload["git_dependencies"]
    assert metadata["evidence"]["git_mutated"] is False
    fingerprints = metadata["evidence"]["fingerprints"]
    expected_before = [before_capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")]
    assert fingerprints["before"] == (result["current_source_state"] if timing == "after" else expected_before)
    assert not _metadata_evidence_blockers(result["lifecycle_input"], [metadata["normalized_record"]])


@pytest.mark.parametrize("kind", ["index", "head", "history", "legacy", "unclassified"])
def test_semantic_dependencies_recheck_with_exact_reasons_and_current_state_acceptance(tmp_path: Path, kind: str) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    command = "git --no-pager diff --cached --stat"
    payload = _discovery_payload(audit, command)
    if kind == "legacy":
        payload["git_sensitive"] = True
    elif kind == "unclassified":
        payload.pop("git_dependencies")
    else:
        payload["git_dependencies"][0].update(kind=kind, reason="The judgment depends on this Git metadata.")
    source = _accept(request, audit, payload)
    result = resume_after_external_metadata(request)
    assert audit["node_id"] in result["recheck_node_ids"]
    decision = next(item for item in result["node_decisions"] if item["node_id"] == audit["node_id"])
    assert decision["reasons"][0].get("command", command) == command
    _kind, _expectation, _evidence, _content, record = _load_evidence_source(source, require_normalized=True)
    assert record is not None
    assert _metadata_evidence_blockers(result["lifecycle_input"], [record])
    dispatch = {
        **audit["dispatch"],
        "external_metadata_transitions": result["lifecycle_input"]["external_metadata_transitions"],
        "before_state": request["source_state"],
        "after_state": result["current_source_state"],
    }
    with pytest.raises(ValueError, match="current metadata state"):
        compile_review({"dispatch": dispatch, "payload": payload})
    dispatch["before_state"] = result["current_source_state"]
    _content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["normalized_record"]["observed_source_state"] == result["current_source_state"]


def test_external_read_cannot_be_preserved_without_captured_identity(tmp_path: Path) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    dependency = tmp_path / "dependency.toml"
    dependency.write_text('version = "1"\n')
    payload = _discovery_payload(audit)
    payload["nearby_contract_owners"] = [str(dependency)]
    _accept(request, audit, payload)
    result = resume_after_external_metadata(request)
    decision = next(item for item in result["node_decisions"] if item["node_id"] == audit["node_id"])
    assert decision["disposition"] == "recheck"
    assert decision["reasons"][0]["path"] == str(dependency)
    assert decision["reasons"][0]["reason_code"] == "unproven-source-read"


@pytest.mark.parametrize("change", ["content", "head", "history"])
def test_discovery_cannot_hide_content_or_commit_changes(tmp_path: Path, change: str) -> None:
    git, repository, request, audit, _entries = _staging_fixture(tmp_path)
    _accept(request, audit, _discovery_payload(audit))
    if change == "content":
        (repository / "tool.py").write_text("value = 3\n")
    elif change == "head":
        _run_test_git(git, "-C", str(repository), "commit", "-m", "changed HEAD")
    else:
        _run_test_git(git, "-C", str(repository), "commit", "--amend", "-m", "rewritten history")
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    with pytest.raises(ValueError, match="only the index"):
        resume_after_external_metadata(request)
    assert not Path(request["artifact_store"]).exists()


@pytest.mark.parametrize(
    "command",
    [
        "git log -1",
        "git diff --no-index a b",
        "git -C elsewhere diff",
        "git diff HEAD~1",
        "git diff --ext-diff",
        "git diff --output=result",
        "git diff && git status",
        "git diff | head",
        "git diff $(git rev-parse HEAD)",
    ],
)
def test_source_discovery_does_not_exempt_unknown_commands(tmp_path: Path, command: str) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    with pytest.raises(ValueError, match="plain local git diff"):
        _accept(request, audit, _discovery_payload(audit, command))


def test_declarations_bind_to_ledger_and_do_not_override_other_commands(tmp_path: Path) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    payload = _discovery_payload(audit)
    payload["commands_executed"].append("git status --porcelain")
    assert git_dependency_blockers(payload)[0]["command"] == "git status --porcelain"
    payload["git_dependencies"][0]["command"] = "git diff --stat"
    with pytest.raises(ValueError, match="match commands_executed"):
        _accept(request, audit, payload)


def test_dependency_metadata_tampering_is_rejected(tmp_path: Path) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    source = _accept(request, audit, _discovery_payload(audit))
    metadata_path = Path(source["metadata_path"])
    metadata = json.loads(metadata_path.read_text())
    metadata["normalized_record"]["git_dependencies"][0]["kind"] = "index"
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="normalized record does not match"):
        resume_after_external_metadata(request)


def test_one_index_audit_does_not_invalidate_other_audits_across_two_staging_events(tmp_path: Path) -> None:
    git, repository, request, _audit, entries = _staging_fixture(tmp_path)
    audits = [entry for entry in entries["dispatches"] if entry["dispatch"].get("mode") == "audit"]
    assert len(audits) > 1
    sensitive = audits[0]["node_id"]
    for entry in audits:
        payload = _discovery_payload(entry)
        if entry["node_id"] == sensitive:
            payload["git_dependencies"] = [{"kind": "index", "reason": "Reviewing staged inclusion independently of the source findings."}]
            payload["commands_executed"] = []
        _accept(request, entry, payload)
    first = resume_after_external_metadata(request)
    assert first["node_counts"]["preserved"] == len(audits) - 1
    assert sensitive in first["recheck_node_ids"]
    assert first["recheck_reason_counts"]["semantic-git-dependency"] == 1
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    second = resume_after_external_metadata(
        {
            **first["lifecycle_input"],
            "dispatches_path": first["dispatches_path"],
            "journal_path": first["journal_path"],
            "previous_capture": request["new_capture"],
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "artifact_store": str(tmp_path / "resumed-again"),
        }
    )
    assert second["preserved_node_ids"] == first["preserved_node_ids"]
    assert len(second["lifecycle_input"]["external_metadata_transitions"]) == 2
