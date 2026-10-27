"""Mutation source identity survives optional fields without hiding conflicts."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from test_review_graph_runtime import _mutation_with_audit_source


def _accepted_mutation(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    request, entry, source = _mutation_with_audit_source(tmp_path)
    dispatches = runtime.materialize_dispatches(
        {
            "artifact_store": str(tmp_path / "old-evidence"),
            "authorization": "review-only",
            "plan": request["plan"],
            "repository_root": request["previous_capture"]["repository_root"],
            "source_state": request["source_state"],
            "state_verification_command": request["state_verification_command"],
        }
    )
    journal = tmp_path / "journal.jsonl"
    runtime.append_journal_event(journal, request, runtime.JournalEventRequest(entry["node_id"], "accepted", source=source))
    dispatch_path = tmp_path / "dispatches.json"
    dispatch_path.write_text(json.dumps(dispatches))
    request.update(journal_path=str(journal), dispatches_path=str(dispatch_path))
    return request, entry, source


@pytest.mark.parametrize("alias", ["absolute", "relative", "symlink"])
def test_explicit_kind_and_journal_source_reuse_once(tmp_path: Path, alias: str) -> None:
    request, entry, source = _accepted_mutation(tmp_path)
    originals = {Path(path): Path(path).read_bytes() for path in (*source.values(), request["journal_path"])}
    explicit = {**source, "kind": "review"}
    if alias == "relative":
        explicit.update({key: os.path.relpath(path) for key, path in source.items()})
    elif alias == "symlink":
        for key, path in source.items():
            link = tmp_path / key
            link.symlink_to(path)
            explicit[key] = str(link)
    request["sources"] = [explicit, source]

    result = runtime.advance_after_mutation(request)

    assert result["status"] == "advanced"
    assert result["reused_evidence_ids"].count(entry["dispatch"]["evidence_id"]) == 1
    assert all(path.read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("damage", ["kind", "contradictory-kinds", "different-evidence", "journal-binding"])
def test_mutation_source_conflicts_still_fail(tmp_path: Path, damage: str) -> None:
    request, entry, source = _accepted_mutation(tmp_path)
    if damage == "kind":
        request["sources"] = [{**source, "kind": "validation"}]
        match = "kind does not match"
    elif damage == "contradictory-kinds":
        request["sources"] = [{**source, "kind": "review"}, {**source, "kind": "validation"}]
        match = "contradictory kinds"
    else:
        # A second valid compiled judgment for the same node is not the accepted one.
        metadata = json.loads(Path(source["metadata_path"]).read_bytes())
        payload = runtime._canonical_worker_payload(Path(source["artifact_path"]).read_bytes())
        payload["commands_executed"] = ["cat tool.py"]
        dispatch = {**entry["dispatch"], "before_state": request["source_state"], "after_state": request["source_state"]}
        content, changed = runtime.compile_review({"dispatch": dispatch, "payload": payload})
        assert changed["artifact_digest"] != metadata["artifact_digest"]
        if damage == "journal-binding":
            Path(source["artifact_path"]).write_bytes(content)
            Path(source["metadata_path"]).write_text(json.dumps(changed))
            match = "differs from journal"
        else:
            artifact, sidecar = tmp_path / "other.txt", tmp_path / "other.json"
            artifact.write_bytes(content)
            sidecar.write_text(json.dumps(changed))
            request["sources"] = [{"artifact_path": str(artifact), "metadata_path": str(sidecar), "kind": "review"}]
            match = "unknown or duplicate node"
    with pytest.raises(ValueError, match=match):
        runtime.advance_after_mutation(request)
