"""Repair/staging endpoints remain usable without inventing an intermediate capture."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_results import EvaluationBoundaryError, RejectionKind
from review_graph_reuse import metadata_transition, source_snapshot
from review_graph_schema import SchemaValidationError, require_schema_definition
from test_review_graph_repair_staging import _finish_repair, _staged_repair
from test_review_graph_runtime import SCHEMA_ROOT, _run_test_git


def _interleaved(tmp_path: Path, dependency: str = "source") -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[Path, bytes]]:
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


@pytest.mark.parametrize("dependency", ["source", "source-discovery", "index"])
def test_interleaved_repair_completes_once_preserving_actual_history(tmp_path: Path, dependency: str, capsys: pytest.CaptureFixture[str]) -> None:
    git, repository, request, audit, history = _interleaved(tmp_path, dependency)
    original = deepcopy(request)
    input_path, output_path = tmp_path / "request.json", tmp_path / "result.json"
    input_path.write_text(json.dumps(request))
    assert runtime.main(["advance-after-mutation", "--input", str(input_path), "--output", str(output_path)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    result = json.loads(output_path.read_bytes())
    assert result["capture"] == request["new_capture"]
    assert result["current_source_state"] == result["new_source_state"] == result["lifecycle_input"]["source_state"]
    assert result["new_plan"]["review_lifecycle"] == {**request["plan"]["review_lifecycle"], "repairs_completed": 1, "interleaved_repair_epochs": [1]}
    retained = json.loads(Path(result["repair_transition_path"]).read_bytes())
    assert retained["previous_capture"] == request["previous_capture"]
    assert retained["new_capture"] == request["new_capture"]
    assert retained["missing_intermediate_capture"] is True
    assert any(item["record"]["status"] == "failed" for item in retained["historical_evidence"])
    assert (audit["dispatch"]["evidence_id"] in result["reused_evidence_ids"]) is (dependency != "index")
    assert receipt["next_action"]["kind"] == "continue-review"
    assert receipt["proof_limitations"][0]["kind"] == "missing-intermediate-capture"
    assert "previous_plan" not in receipt
    command = receipt["next_action"]["command"]
    assert runtime.main(command[command.index("next-ready") :]) == 0
    capsys.readouterr()
    _finish_repair(tmp_path, result)
    assert json.loads((tmp_path / "final.json").read_bytes())["proof_limitations"] == result["proof_limitations"]
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    delivery = runtime.report_delivery({**lifecycle, "current_source_state": result["current_source_state"]})
    assert delivery["proof_limitations"] == result["proof_limitations"]
    assert all(path.read_bytes() == content for path, content in history.items())
    assert _scope_data(git, repository, "baseline", None, ()) == request["new_capture"]
    assert request == original


@pytest.mark.parametrize(
    "change",
    [
        "unattributed-source",
        "scope",
        "mode",
        "instructions",
        "head",
        "base",
        "capture-mode",
        "missing-attribution",
        "blank-attribution",
        "extra-attribution",
        "both-paths",
    ],
)
def test_interleaved_repair_rejects_unproven_changes_before_publication(tmp_path: Path, change: str) -> None:
    git, repository, request, _audit, history = _interleaved(tmp_path)
    if change == "unattributed-source":
        (repository / "tool.py").write_text("external = True\n")
    elif change == "mode":
        (repository / "state.rs").chmod(0o755)
    elif change == "instructions":
        (repository / "AGENTS.md").write_text("Changed instructions.\n")
        request["changed_paths"].append("AGENTS.md")
    elif change == "head":
        _run_test_git(git, "-C", str(repository), "commit", "-m", "maintainer commit")
    elif change == "missing-attribution":
        del request["interleaved_staging"]["repair_attribution"]
    elif change == "blank-attribution":
        request["interleaved_staging"]["repair_attribution"] = " "
    elif change == "extra-attribution":
        request["interleaved_staging"]["trust_me"] = True
    elif change == "both-paths":
        request["post_repair_capture"] = request["new_capture"]
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ("state.rs",) if change == "scope" else ())
    if change in {"base", "capture-mode"}:
        field = "base_ref" if change == "base" else "capture_mode"
        request["new_capture"][field] = "HEAD" if change == "base" else "staged"
        snapshot = runtime.source_snapshot(request["new_capture"])
        request["new_capture"]["repository_state_fingerprint"] = snapshot.computed_fingerprint()
    history[repository / ".git" / "index"] = (repository / ".git" / "index").read_bytes()
    with pytest.raises(ValueError, match=r"interleaved|repair_paths|schema|Git path identity"):
        runtime.advance_after_mutation(request)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in history.items())


def test_interleaved_repair_rechecks_live_state_before_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git, repository, request, _audit, history = _interleaved(tmp_path)
    original = runtime._plan_delta_audits

    def race(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        (repository / "tool.py").write_text("concurrent_edit = True\n")
        return result

    monkeypatch.setattr(runtime, "_plan_delta_audits", race)
    with pytest.raises(ValueError, match="source changed during external reconciliation"):
        runtime.advance_after_mutation(request)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in history.items())


@pytest.mark.parametrize("paths", [("journal_path",), ("dispatches_path",), ("journal_path", "dispatches_path")])
def test_interleaved_repair_requires_complete_readable_history_before_publication(tmp_path: Path, paths: tuple[str, ...]) -> None:
    _git, _repository, request, _audit, history = _interleaved(tmp_path)
    request.update({key: str(tmp_path / f"missing-{key}") for key in paths})
    with pytest.raises((ValueError, FileNotFoundError)):
        runtime.advance_after_mutation(request)
    assert not Path(request["artifact_store"]).exists()
    assert all(path.read_bytes() == content for path, content in history.items())


@pytest.mark.parametrize("endpoint", ["previous_capture", "new_capture"])
@pytest.mark.parametrize("identity", ["absent", "submodule:" + "a" * 64, "git:sha1:160000:" + "b" * 40])
def test_interleaved_repair_types_unsupported_endpoint_identities(tmp_path: Path, endpoint: str, identity: str) -> None:
    _git, _repository, request, _audit, _history = _interleaved(tmp_path)
    capture = request[endpoint]
    capture["repository_path_fingerprints"]["state.rs"] = identity
    capture["repository_state_fingerprint"] = source_snapshot(capture).computed_fingerprint()
    with pytest.raises(EvaluationBoundaryError) as failure:
        metadata_transition(
            {
                "before": request["previous_capture"],
                "after": request["new_capture"],
                "repair_epoch": request["repair_epoch"],
                "repair_paths": request["changed_paths"],
                **request["interleaved_staging"],
            }
        )
    assert failure.value.kind is RejectionKind.UNSUPPORTED_TRANSITION


@pytest.mark.parametrize("paths", [(), ("journal_path",), ("dispatches_path",), ("journal_path", "dispatches_path")])
def test_mutation_schema_requires_paired_history_paths(paths: tuple[str, ...]) -> None:
    request = json.loads((SCHEMA_ROOT.parent / "runtime-operation-examples-v1.json").read_bytes())["advance-after-mutation"]
    for key in ("journal_path", "dispatches_path"):
        request.pop(key, None)
    request.update({key: f"history/{key}.json" for key in paths})
    schema_path = SCHEMA_ROOT / "runtime-operation-inputs-v1.schema.json"
    if len(paths) == 1:
        missing = "dispatches_path" if paths[0] == "journal_path" else "journal_path"
        with pytest.raises(SchemaValidationError) as failure:
            require_schema_definition(request, schema_path, "advance-after-mutation")
        assert [(item.path, item.code) for item in failure.value.diagnostics] == [(f"$.{missing}", "required")]
    else:
        require_schema_definition(request, schema_path, "advance-after-mutation")
