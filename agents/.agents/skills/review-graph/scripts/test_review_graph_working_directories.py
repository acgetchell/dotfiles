"""Planning, preflight, and timing share one explicit directory identity."""

import json
import subprocess
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import pytest
import review_graph_runtime as runtime
from review_graph_plan import validation_requirements_from_document
from review_graph_timing import timing_documents
from test_review_graph_efficiency import _preflight_request
from test_review_graph_runtime import SKILL_ROOT, _sparse_plan_document

if TYPE_CHECKING:
    from pathlib import Path


def test_relative_directories_bind_to_repository_before_preflight_and_timing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "repository with spaces"
    subdirectory = repository / "subdirectory"
    subdirectory.mkdir(parents=True)
    caller = tmp_path / "caller"
    caller.mkdir()
    document = _sparse_plan_document()
    document["validation_requirements"][0].update(commands=["true", "false"], working_directories=[".", "subdirectory"])
    monkeypatch.chdir(caller)
    requirement = validation_requirements_from_document(document, repository)[0]
    assert requirement.working_directories == (str(repository), str(subdirectory))
    request = _preflight_request(repository)
    unit = request["plan"]["coalesced_validation_units"][0]
    unit.update(commands=list(requirement.commands), working_directories=list(requirement.working_directories))
    request["command_policy"].append({"command": "false", "disposition": "allowed", "reason": "never executed by preparation"})

    def forbidden_launch(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("preflight and timing preparation must not execute checks")

    monkeypatch.setattr(subprocess, "Popen", forbidden_launch)
    monkeypatch.chdir(tmp_path)
    assert runtime.preflight_validation(request)["status"] == "ready"
    dispatch: dict[str, Any] = {
        "mode": "validation",
        "node_id": unit["node_id"],
        "source_state": unit["source_state"],
        "skill_path": str(SKILL_ROOT / "review-validator/SKILL.md"),
        "timing_prerequisite": {"manifest_path": str(tmp_path / "timing.json")},
        "validation_unit": unit,
    }
    monkeypatch.chdir(repository)
    writes, manifest = timing_documents(dispatch, {"shell_argv": ["/bin/sh", "-c"]})
    assert [(item["command"], item["working_directory"]) for item in manifest["launches"]] == [("true", str(repository)), ("false", str(subdirectory))]
    assert all(json.loads(content) for content in writes.values())
    assert not (tmp_path / "timing.json").exists()
    assert asdict(requirement)["working_directories"] == (str(repository), str(subdirectory))


def test_relative_directory_without_explicit_root_is_rejected() -> None:
    document = _sparse_plan_document()
    document["validation_requirements"][0]["working_directories"] = ["."]
    with pytest.raises(ValueError, match="explicit absolute repository root"):
        validation_requirements_from_document(document, None)


def test_legacy_relative_directory_is_not_reported_ready(tmp_path: Path) -> None:
    request = _preflight_request(tmp_path)
    request["plan"]["coalesced_validation_units"][0]["working_directories"] = ["."]
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    assert any(str(tmp_path) in blocker and "absolute" in blocker for blocker in report["units"][0]["execution_blockers"])
