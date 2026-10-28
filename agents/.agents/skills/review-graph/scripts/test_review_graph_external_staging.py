"""Maintainer source edits and staging compose from actual captured endpoints."""

import json
import shutil
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_reuse import StagedExternalSourceTransition, metadata_transition, source_snapshot
from test_review_graph_external_source import _external
from test_review_graph_lifecycle import _control_args
from test_review_graph_runtime import _baseline_mutation_fixture, _run_test_git
from test_review_graph_transitions import _materialize, _payload


def _staged_external(
    tmp_path: Path, *, changed: str = "README.md", git_dependency: str | None = None
) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    request, validator, repository, entries = _external(tmp_path, changed=changed, repairs_completed=1, git_dependency=git_dependency)
    git = shutil.which("git")
    assert git is not None
    _run_test_git(git, "-C", str(repository), "add", "--all")
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    request["external_staging_attribution"] = "The maintainer confirmed staging these changes while reviewing."
    return git, repository, request, validator, entries


@pytest.mark.parametrize("git_dependency", [None, "source-discovery", "index"])
def test_staged_external_edit_preserves_proven_evidence_and_remaining_repair_budget(tmp_path: Path, git_dependency: str | None) -> None:
    git, repository, request, validator, entries = _staged_external(tmp_path, git_dependency=git_dependency)
    original = deepcopy(request)
    protected = {
        Path(entry[key]): Path(entry[key]).read_bytes()
        for entry in entries["dispatches"]
        for key in ("artifact_path", "metadata_path")
        if Path(entry[key]).exists()
    }
    protected.update({Path(request[key]): Path(request[key]).read_bytes() for key in ("journal_path", "dispatches_path")})
    protected[repository / ".git/index"] = (repository / ".git/index").read_bytes()
    result = runtime.resume_after_external_source(request)
    assert result["transition_kind"] == "staged-external-source-change"
    lifecycle = result["lifecycle_input"]
    assert lifecycle["plan"]["review_lifecycle"] == request["plan"]["review_lifecycle"]
    assert lifecycle["source_state"] == request["source_state"]
    assert json.loads(Path(result["capture_path"]).read_bytes()) == request["new_capture"]
    assert len(lifecycle["external_metadata_transitions"]) == 1
    transition = metadata_transition(lifecycle["external_metadata_transitions"][0])
    assert isinstance(transition, StagedExternalSourceTransition)
    assert transition.before == source_snapshot(request["previous_capture"])
    assert transition.after == source_snapshot(request["new_capture"])
    assert transition.external_source_attribution == request["external_source_attribution"]
    assert transition.external_staging_attribution == request["external_staging_attribution"]
    assert json.loads(json.dumps(asdict(transition))) == lifecycle["external_metadata_transitions"][0]
    tool = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    expected = result["recheck_node_ids"] if git_dependency == "index" else result["preserved_node_ids"]
    assert tool["node_id"] in expected
    assert validator["node_id"] in expected
    assert all(
        entry["node_id"] in result["recheck_node_ids"]
        for entry in entries["dispatches"]
        if entry["dispatch"]["mode"] == "audit" and "README.md" in entry["dispatch"]["owned_paths"]
    )
    control = runtime.review_control(
        {**lifecycle, "action": "begin-repair", "authorization": "review-and-fix", "artifact_store": str(tmp_path / "control")}, _control_args(tmp_path, result)
    )
    assert control["status"] == "repair-authorized"
    assert control["repair_epoch"] == 2
    assert json.loads(json.dumps(control["review_lifecycle"])) == request["plan"]["review_lifecycle"]
    assert all(path.read_bytes() == content for path, content in protected.items())
    assert _scope_data(git, repository, "baseline", None, ()) == request["new_capture"]
    assert request == original


def test_staged_external_semantic_change_rechecks_validation_and_rejects_stale_worker_captures(tmp_path: Path) -> None:
    _git, _repository, request, validator, entries = _staged_external(tmp_path, changed="tool.py")
    result = runtime.resume_after_external_source(request)
    assert validator["node_id"] in result["recheck_node_ids"]
    audit = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit" and item["dispatch"]["owned_paths"] == ["tool.py"])
    assert audit["node_id"] in result["recheck_node_ids"]
    for after in (request["source_state"], result["current_source_state"]):
        dispatch = {
            **audit["dispatch"],
            "before_state": request["source_state"],
            "after_state": after,
            "external_metadata_transitions": result["lifecycle_input"]["external_metadata_transitions"],
        }
        with pytest.raises(ValueError, match="unproven-source-read"):
            runtime.compile_review({"dispatch": dispatch, "payload": _payload(dispatch["owned_paths"], dispatch=dispatch)})


@pytest.mark.parametrize("defect", ["missing-staging", "blank-staging", "missing-source", "blank-source", "blank-actor", "agent-attribution"])
def test_staged_external_change_requires_unambiguous_attribution(tmp_path: Path, defect: str) -> None:
    _git, repository, request, _validator, _entries = _staged_external(tmp_path)
    if defect.startswith("missing-"):
        request.pop("external_staging_attribution" if defect.endswith("staging") else "external_source_attribution")
    elif defect.startswith("blank-"):
        field = {"blank-staging": "external_staging_attribution", "blank-source": "external_source_attribution", "blank-actor": "external_source_actor"}[defect]
        request[field] = " "
    else:
        request["repair_attribution"] = "These were agent repairs."
    index = (repository / ".git/index").read_bytes()
    with pytest.raises(ValueError, match=r"attribution|unchanged Git|external_source_actor"):
        runtime.resume_after_external_source(request)
    assert not Path(request["artifact_store"]).exists()
    assert (repository / ".git/index").read_bytes() == index


@pytest.mark.parametrize("defect", ["head", "branch", "base", "scope", "inventory", "mode", "instructions", "staged-scope", "unknown-selection"])
def test_staged_external_change_rejects_unsupported_boundaries_before_publication(tmp_path: Path, defect: str) -> None:
    git, repository, request, _validator, _entries = _staged_external(tmp_path)
    if defect == "head":
        _run_test_git(git, "-C", str(repository), "commit", "-m", "Maintainer commit")
    elif defect == "branch":
        _run_test_git(git, "-C", str(repository), "checkout", "-b", "maintainer-branch")
    elif defect == "inventory":
        (repository / "new.py").write_text("new = True\n")
    elif defect == "mode":
        (repository / "README.md").chmod(0o755)
    elif defect == "instructions":
        (repository / "AGENTS.md").write_text("Changed instructions.\n")
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ("README.md",) if defect == "scope" else ())
    if defect in {"base", "staged-scope", "unknown-selection"}:
        for endpoint in ("previous_capture", "new_capture") if defect != "base" else ("new_capture",):
            capture = request[endpoint]
            if defect == "base":
                capture["base_ref"] = "HEAD"
            elif defect == "staged-scope":
                capture["capture_mode"] = "staged"
            else:
                capture.pop("repository_selection_paths")
            capture["repository_state_fingerprint"] = source_snapshot(capture).computed_fingerprint()
    index = (repository / ".git/index").read_bytes()
    with pytest.raises(ValueError, match=r"external source|unchanged Git"):
        runtime.resume_after_external_source(request)
    assert not Path(request["artifact_store"]).exists()
    assert (repository / ".git/index").read_bytes() == index


def test_staged_external_change_rechecks_live_index_before_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git, repository, request, _validator, _entries = _staged_external(tmp_path)
    original = runtime._metadata_resume_decisions

    def race(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        result = original(*args, **kwargs)
        _run_test_git(git, "-C", str(repository), "reset", "HEAD", "--", "README.md")
        return result

    monkeypatch.setattr(runtime, "_metadata_resume_decisions", race)
    with pytest.raises(ValueError, match="source changed during external reconciliation"):
        runtime.resume_after_external_source(request)
    assert not Path(request["artifact_store"]).exists()


def test_staged_external_change_composes_between_two_authorized_repairs(tmp_path: Path) -> None:
    git, repository, template, capture, plan = _baseline_mutation_fixture(tmp_path)
    lifecycle, _entries, _dispatches = _materialize(tmp_path, capture, plan)

    def repair(document: dict[str, Any], previous: dict[str, Any], epoch: int) -> dict[str, Any]:
        (repository / "tool.py").write_text(f"value = {epoch + 1}\n")
        return runtime.advance_after_mutation(
            {
                **document,
                "previous_capture": previous,
                "new_capture": _scope_data(git, repository, "baseline", None, ()),
                "planning_template": template,
                "changed_paths": ["tool.py"],
                "authorization_before": "review-and-fix",
                "authorization_after": "review-and-fix",
                "repair_epoch": epoch,
                "artifact_store": str(tmp_path / f"repair-{epoch}"),
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )

    first = repair(lifecycle, capture, 1)
    (repository / "state.rs").write_text("pub fn state() { assert_eq!(1, 1); }\n")
    _run_test_git(git, "-C", str(repository), "add", "--all")
    external = _scope_data(git, repository, "baseline", None, ())
    resumed = runtime.resume_after_external_source(
        {
            **first["lifecycle_input"],
            "previous_capture": first["capture"],
            "new_capture": external,
            "dispatches_path": first["dispatches_path"],
            "journal_path": first["journal_path"],
            "artifact_store": str(tmp_path / "external"),
            "external_source_actor": "maintainer",
            "external_source_attribution": "The maintainer confirmed the state.rs edit.",
            "external_staging_attribution": "The maintainer confirmed staging while reviewing.",
        }
    )
    control = runtime.review_control(
        {**resumed["lifecycle_input"], "action": "begin-repair", "authorization": "review-and-fix", "artifact_store": str(tmp_path / "control")},
        _control_args(tmp_path, resumed),
    )
    assert control["status"] == "repair-authorized"
    assert control["repair_epoch"] == 2
    index = (repository / ".git/index").read_bytes()
    second = repair(
        {**resumed["lifecycle_input"], "dispatches_path": resumed["dispatches_path"], "journal_path": resumed["journal_path"]},
        external,
        control["repair_epoch"],
    )
    policy = second["new_plan"]["review_lifecycle"]
    assert policy == {**first["new_plan"]["review_lifecycle"], "repairs_completed": 2}
    assert policy["run_control"] == lifecycle["plan"]["review_lifecycle"]["run_control"]
    assert second["repair_epoch"]["changed_paths"] == ["tool.py"]
    assert (repository / ".git/index").read_bytes() == index
    assert json.loads(Path(resumed["capture_path"]).read_bytes()) == external
