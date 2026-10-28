"""External content continuation preserves budgets and proven unaffected evidence."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
import review_graph_source_change
from capture_scope import _scope_data
from test_review_graph_git import _accept
from test_review_graph_runtime import ROUTING_CATALOG, _compile_repair_fixture_entry, _mutation_with_audit_source
from test_review_graph_transitions import _payload
from test_review_graph_validation_handoff import _handoff


def _external(
    tmp_path: Path, *, changed: str = "README.md", repairs_completed: int = 0, dependency: str | None = None, git_dependency: str | None = None
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    lifecycle, validator, capture, git, repository, _metadata = _handoff(
        tmp_path,
        dependencies=[{"kind": "index", "reason": "The fixture validation depends on staged contents."}] if git_dependency == "index" else [],
        prefixes=["tool.py"],
        readme=True,
        repairs_completed=repairs_completed,
    )
    entries = json.loads(Path(lifecycle["dispatches_path"]).read_bytes())
    for entry in entries["dispatches"]:
        if entry["dispatch"]["mode"] == "audit":
            payload = _payload(entry["dispatch"]["owned_paths"], dispatch=entry["dispatch"])
            if git_dependency is not None and "tool.py" in payload["files_inspected"]:
                command = "git --no-pager diff --cached -- tool.py"
                payload.update(commands_executed=[command], git_dependencies=[{"kind": git_dependency, "command": command, "reason": "Fixture Git input."}])
            if dependency is not None and "tool.py" in payload["files_inspected"]:
                payload["coverage_units"] = [
                    {
                        "unit_id": "tool",
                        "owned_paths": payload["files_inspected"],
                        "finding_indices": [],
                        "dependency_paths": [*payload["nearby_contract_owners"], *([] if dependency == "uncertain" else [dependency])],
                        "dependency_uncertainty": "Dynamic configuration is not fully classified." if dependency == "uncertain" else "",
                    }
                ]
            _accept(lifecycle, entry, payload)
    (repository / changed).write_text("# Fixture\n\nDescription.\n" if changed == "README.md" else "value = 42\n")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "artifact_store": str(tmp_path / "external"),
        "external_source_actor": "maintainer",
        "external_source_attribution": "The maintainer confirmed this edit in the review chat.",
    }
    return request, validator, repository, entries


def test_external_readme_edit_preserves_validation_audits_and_exhausted_budget(tmp_path: Path) -> None:
    request, validator, _repository, entries = _external(tmp_path, repairs_completed=2)
    original = {
        path: Path(path).read_bytes() for entry in entries["dispatches"] for key in ("artifact_path", "metadata_path") if Path(path := entry[key]).exists()
    }
    result = runtime.resume_after_external_source(request)
    assert validator["node_id"] in result["preserved_node_ids"]
    assert result["transition_kind"] == "external-source-change"
    assert result["lifecycle_input"]["plan"]["review_lifecycle"] == request["plan"]["review_lifecycle"]
    for entry in entries["dispatches"]:
        if entry["dispatch"]["mode"] == "audit":
            expected = result["recheck_node_ids"] if "README.md" in entry["dispatch"]["owned_paths"] else result["preserved_node_ids"]
            assert entry["node_id"] in expected
    assert all(Path(path).read_bytes() == content for path, content in original.items())
    with pytest.raises(ValueError, match="repair budget exhausted"):
        runtime._graph_plan(result["lifecycle_input"]["plan"]).review_lifecycle.next_repair(3)
    assert all(entry["dispatch"]["authorization"] == "review-only" for entry in result["dispatch_set"]["dispatches"])
    record = runtime.load_validation_record(metadata_path=Path(validator["metadata_path"]), artifact_path=Path(validator["artifact_path"]))
    assert runtime._metadata_evidence_blockers(result["lifecycle_input"], [record]) == []
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    journal = Path(result["journal_path"])
    for entry in result["dispatch_set"]["dispatches"]:
        if entry["node_id"] in result["recheck_node_ids"]:
            _compile_repair_fixture_entry(entry, lifecycle, journal)
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
    assert json.loads(output.read_bytes())["graph_proof_status"] == "complete"


def test_semantic_external_edit_invalidates_owning_audit_and_validation(tmp_path: Path) -> None:
    request, validator, _repository, entries = _external(tmp_path, changed="tool.py")
    result = runtime.resume_after_external_source(request)
    assert validator["node_id"] in result["recheck_node_ids"]
    for entry in entries["dispatches"]:
        if "tool.py" in entry["dispatch"]["owned_paths"]:
            assert entry["node_id"] in result["recheck_node_ids"]


@pytest.mark.parametrize("dependency", ["uncertain", "README.md", "/unproven/external.json"])
def test_external_source_preserves_only_proven_coverage_dependencies(tmp_path: Path, dependency: str) -> None:
    request, _validator, _repository, entries = _external(tmp_path, dependency=dependency)
    result = runtime.resume_after_external_source(request)
    for entry in entries["dispatches"]:
        if entry["dispatch"]["mode"] == "audit" and "tool.py" in entry["dispatch"]["owned_paths"]:
            assert entry["node_id"] in result["recheck_node_ids"]


@pytest.mark.parametrize("timing", ["before", "across"])
def test_external_source_cannot_relabel_old_captures_as_fresh(tmp_path: Path, timing: str) -> None:
    request, _validator, _repository, entries = _external(tmp_path)
    result = runtime.resume_after_external_source(request)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    dispatch = {
        **entry["dispatch"],
        "external_metadata_transitions": result["lifecycle_input"]["external_metadata_transitions"],
        "before_state": request["source_state"],
        "after_state": request["source_state"] if timing == "before" else result["current_source_state"],
    }
    with pytest.raises(ValueError, match="fingerprint"):
        runtime.compile_review({"dispatch": dispatch, "payload": _payload(dispatch["owned_paths"], dispatch=dispatch)})


@pytest.mark.parametrize("timing", ["before", "during"])
def test_external_reconciliation_rejects_concurrent_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timing: str) -> None:
    request, _validator, repository, _entries = _external(tmp_path)
    if timing == "before":
        (repository / "tool.py").write_text("concurrent = True\n")
    else:
        original = runtime._metadata_resume_decisions

        def race(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            result = original(*args, **kwargs)
            (repository / "tool.py").write_text("concurrent = True\n")
            return result

        monkeypatch.setattr(runtime, "_metadata_resume_decisions", race)
    with pytest.raises(ValueError, match="source changed during external reconciliation"):
        runtime.resume_after_external_source(request)
    assert not Path(request["artifact_store"]).exists()


def test_external_source_requires_explicit_attribution_and_rejects_expanded_scope(tmp_path: Path) -> None:
    request, _validator, repository, _entries = _external(tmp_path)
    with pytest.raises(ValueError, match="external_source_attribution"):
        runtime.resume_after_external_source({key: value for key, value in request.items() if key != "external_source_attribution"})
    (repository / "new.py").write_text("new = True\n")

    git = shutil.which("git")
    assert git is not None
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    with pytest.raises(ValueError, match="unchanged Git and review selection"):
        runtime.resume_after_external_source(request)


def test_external_source_restores_reused_audit_from_explicit_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request, original_entry, _source = _mutation_with_audit_source(tmp_path)
    advanced = runtime.advance_after_mutation(request)
    assert advanced["reused_evidence_ids"] == [original_entry["dispatch"]["evidence_id"]]
    catalog = tmp_path / "routing-catalog.json"
    shutil.copyfile(ROUTING_CATALOG, catalog)
    monkeypatch.setattr(runtime, "DEFAULT_ROUTING_CATALOG", tmp_path / "unavailable-default.json")
    repository = Path(request["new_capture"]["repository_root"])
    (repository / "tool.py").write_text("value = 42\n")
    git = shutil.which("git")
    assert git is not None
    result = runtime.resume_after_external_source(
        {
            **json.loads(Path(advanced["lifecycle_input_path"]).read_bytes()),
            "previous_capture": advanced["capture"],
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "dispatches_path": advanced["dispatches_path"],
            "journal_path": advanced["journal_path"],
            "artifact_store": str(tmp_path / "external"),
            "routing_catalog_path": str(catalog),
            "external_source_actor": "maintainer",
            "external_source_attribution": "Maintainer updated tool.py during review.",
        }
    )
    replacement = [item for item in result["dispatch_set"]["dispatches"] if item["dispatch"].get("skill_id") == original_entry["dispatch"]["skill_id"]]
    assert len(replacement) == 1
    assert replacement[0]["dispatch"]["evidence_id"] != original_entry["dispatch"]["evidence_id"]
    assert replacement[0]["node_id"] in result["recheck_node_ids"]


def test_live_capture_race_uses_cli_diagnostic_without_publishing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    request, _validator, _repository, _entries = _external(tmp_path)
    capture_error = "captured source changed while deriving path line bounds"

    def race(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(capture_error)

    monkeypatch.setattr(review_graph_source_change, "_scope_data", race)
    with pytest.raises(ValueError, match="recapture the actual state") as failure:
        review_graph_source_change.verify_live_source(request["new_capture"])
    assert isinstance(failure.value.__cause__, RuntimeError)
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request))
    output = tmp_path / "continuation.json"
    assert runtime.main(["resume-after-external-source", "--input", str(input_path), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "recapture the actual state" in captured.err
    assert capture_error in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()
    assert not Path(request["artifact_store"]).exists()


@pytest.mark.parametrize("placement", ["inside", "same", "ancestor", "alias"])
def test_external_source_rejects_overlapping_store_before_writes(tmp_path: Path, placement: str) -> None:
    """An invalid proof destination must not change any repository bytes."""
    request, _validator, repository, _entries = _external(tmp_path)
    if placement == "alias":
        alias = tmp_path / "repository-alias"
        alias.symlink_to(repository, target_is_directory=True)
        store = alias / "proof"
    else:
        store = {"inside": repository / "proof", "same": repository, "ancestor": repository.parent}[placement]
    request["artifact_store"] = str(store)
    before = {str(path.relative_to(repository)): path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="external proof store"):
        runtime.resume_after_external_source(request)
    after = {str(path.relative_to(repository)): path.read_bytes() for path in repository.rglob("*") if path.is_file()}
    assert after == before
    if placement in {"inside", "alias"}:
        assert not store.exists()


@pytest.mark.parametrize("conflict", ["existing", "missing-parent"])
def test_external_source_result_failure_reports_retained_continuation(tmp_path: Path, capsys: pytest.CaptureFixture[str], conflict: str) -> None:
    """Result-file failures retain a usable, explicitly reported continuation."""
    request, _validator, _repository, _entries = _external(tmp_path)
    input_path = tmp_path / "external-request.json"
    input_path.write_text(json.dumps(request))
    output = tmp_path / "existing.json" if conflict == "existing" else tmp_path / "missing" / "result.json"
    if conflict == "existing":
        output.write_text("preserve existing result\n")
    assert runtime.main(["resume-after-external-source", "--input", str(input_path), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "continuation was published" in captured.err
    store = Path(request["artifact_store"])
    for name in ("lifecycle.json", "dispatches.json", "capture.json", "execution.jsonl"):
        assert (store / name).is_file()
        assert str(store / name) in captured.err
    if conflict == "existing":
        assert output.read_text() == "preserve existing result\n"
    else:
        assert not output.exists()
