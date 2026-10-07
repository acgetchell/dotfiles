"""Effective uv prerequisite regressions without executing recipes or interpreters."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_schema import SchemaValidationError
from test_review_graph_efficiency import _preflight_request


def _executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    path.chmod(0o755)


def _uv_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    request = _preflight_request(tmp_path)
    unit = request["plan"]["coalesced_validation_units"][0]
    unit.update(commands=["just check ci", "just coverage-rust coverage-summary"], working_directories=[str(tmp_path)] * 2)
    request["command_policy"] = [{"command": command, "disposition": "allowed", "reason": "inspected nested locked uv recipes"} for command in unit["commands"]]
    host = tmp_path / "host-bin"
    for name in ("uv", "just"):
        _executable(host / name)
    monkeypatch.setenv("PATH", str(host))
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text('version = 1\nrevision = 3\nrequires-python = ">=3.14"\n', encoding="utf-8")
    environment = tmp_path / "configured-env"
    directory = environment / "bin"
    directory.mkdir(parents=True)
    (environment / "pyvenv.cfg").write_text(f"home = {Path(sys.executable).resolve().parent}\n", encoding="utf-8")
    (directory / "python").symlink_to(Path(sys.executable).resolve())
    _executable(directory / "pytest")
    request["execution_prerequisites"][0].update(
        executables=["just", "uv"], uv_projects=[{"project_directory": ".", "environment_path": "configured-env", "executables": ["python", "pytest"]}]
    )

    def forbidden_launch(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("preflight must not launch a process, sync, or download")

    monkeypatch.setattr(subprocess, "Popen", forbidden_launch)
    return request


def _tree_snapshot(root: Path) -> dict[str, Any]:
    return {
        str(path.relative_to(root)): (
            (path.lstat().st_mode, path.lstat().st_size, path.lstat().st_mtime_ns),
            path.readlink() if path.is_symlink() else path.read_bytes() if path.is_file() else None,
        )
        for path in root.rglob("*")
    }


def test_locked_uv_template_resolves_environment_without_ambient_python_or_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    assert shutil.which("python") is None
    before = _tree_snapshot(tmp_path)

    report = runtime.preflight_validation(request)

    assert report["status"] == "ready"
    assert _tree_snapshot(tmp_path) == before
    observations = report["units"][0]["executor_observations"]
    assert [item["executable"] for item in observations["host_executables"]] == ["just", "uv"]
    project = observations["uv_projects"][0]
    assert project["environment_path"] == str(tmp_path / "configured-env")
    assert [item["executable"] for item in project["executables"]] == ["python", "pytest"]
    assert project["executables"][0]["resolved_path"] == str(Path(sys.executable).resolve())
    assert all(item["available"] for item in project["executables"])
    assert not report["cache_checks"]


def test_uv_console_tool_requires_environment_interpreter_even_when_not_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    request["execution_prerequisites"][0]["uv_projects"][0]["executables"] = ["pytest"]
    (tmp_path / "configured-env" / "bin" / "python").unlink()
    _executable(tmp_path / "host-bin" / "python")
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    observations = report["units"][0]["executor_observations"]["uv_projects"][0]["executables"]
    assert not observations[0]["available"]
    assert observations[1]["available"]
    assert any("/bin/python" in blocker for blocker in report["units"][0]["execution_blockers"])


def test_uv_project_availability_cannot_satisfy_another_declared_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    request["execution_prerequisites"][0]["uv_projects"].append({"project_directory": ".", "environment_path": "another-env", "executables": ["pytest"]})
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    observations = report["units"][0]["executor_observations"]["uv_projects"]
    assert not observations[0]["blockers"]
    assert any("another-env" in blocker for blocker in observations[1]["blockers"])


@pytest.mark.parametrize(
    ("defect", "diagnostic"),
    [
        ("environment", "uv project environment unavailable"),
        ("lock", "uv project metadata unavailable"),
        ("metadata", "uv project metadata unavailable"),
        ("configuration", "has no Python home"),
        ("interpreter", "uv project executable unavailable"),
        ("broken-interpreter", "uv project executable unavailable"),
        ("tool", "uv project executable unavailable"),
        ("non-executable", "uv project executable unavailable"),
    ],
)
def test_invalid_uv_environment_blocks_without_ambient_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str, diagnostic: str) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    environment = tmp_path / "configured-env"
    if defect == "environment":
        request["execution_prerequisites"][0]["uv_projects"][0]["environment_path"] = "missing-env"
    elif defect == "lock":
        (tmp_path / "uv.lock").unlink()
    elif defect == "metadata":
        (tmp_path / "pyproject.toml").write_text("invalid [", encoding="utf-8")
    elif defect == "configuration":
        (environment / "pyvenv.cfg").write_text("version = 3.14\n", encoding="utf-8")
    elif defect in {"interpreter", "broken-interpreter"}:
        (environment / "bin" / "python").unlink()
        if defect == "broken-interpreter":
            (environment / "bin" / "python").symlink_to(tmp_path / "absent-python")
        _executable(tmp_path / "host-bin" / "python")
    else:
        tool = environment / "bin" / "pytest"
        if defect == "tool":
            tool.unlink()
        else:
            tool.chmod(0o644)
        _executable(tmp_path / "host-bin" / "pytest")
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    unit = report["units"][0]
    assert any(diagnostic in blocker for blocker in unit["execution_blockers"])
    assert unit["configuration_errors"] == unit["repository_findings"] == []


@pytest.mark.parametrize("kind", ["missing", "non-executable", "different", "matching"])
def test_configured_interpreter_path_must_match_existing_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    project = request["execution_prerequisites"][0]["uv_projects"][0]
    configured = tmp_path / "selected-python"
    if kind == "matching":
        configured.symlink_to(Path(sys.executable).resolve())
    elif kind in {"non-executable", "different"}:
        _executable(configured)
        if kind == "non-executable":
            configured.chmod(0o644)
    project["configured_python"] = "selected-python"
    report = runtime.preflight_validation(request)
    assert report["status"] == ("ready" if kind == "matching" else "blocked")
    observation = report["units"][0]["executor_observations"]["uv_projects"][0]["configured_python"]
    assert observation["matches_environment"] == (kind == "matching")
    if kind != "matching":
        assert any("configured uv interpreter" in blocker for blocker in report["units"][0]["execution_blockers"])


@pytest.mark.parametrize("blocker", ["host", "native", "cache"])
def test_uv_availability_does_not_satisfy_other_executor_prerequisites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocker: str) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    if blocker == "host":
        (tmp_path / "host-bin" / "uv").unlink()
        _executable(tmp_path / "configured-env" / "bin" / "uv")
        diagnostic = "executor executable unavailable: uv"
    elif blocker == "native":
        request["execution_prerequisites"][0].update(native_available=False, reason="required native runner unavailable")
        diagnostic = "native environment unavailable"
    else:
        request["cache_paths"] = [".uv-cache"]

        def denied(_path: Path) -> None:
            msg = "cache traversal denied"
            raise PermissionError(msg)

        monkeypatch.setattr(runtime.os, "scandir", denied)
        diagnostic = "executor cache is inaccessible"
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    unit = report["units"][0]
    assert unit["executor_observations"]["uv_projects"][0]["blockers"] == []
    assert any(diagnostic in reason for reason in unit["execution_blockers"])
    if blocker == "cache":
        assert not report["cache_checks"][0]["accessible"]


def test_hosted_obligation_remains_blocked_without_inspecting_local_uv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    request["plan"]["coalesced_validation_units"][0].update(commands=[], working_directories=[], canonical_recipe=None)
    request["execution_prerequisites"][0]["uv_projects"][0]["environment_path"] = "missing-env"
    report = runtime.preflight_validation(request)
    assert report["status"] == "blocked"
    unit = report["units"][0]
    assert unit["execution_blockers"] == ["no local command; retain the hosted or unexecutable obligation as blocked"]
    assert unit["executor_observations"] == {"host_executables": [], "uv_projects": []}


def test_uv_projects_resolve_relative_to_declared_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    project = tmp_path / "workspace"
    project.mkdir()
    for name in ("pyproject.toml", "uv.lock", "configured-env"):
        (tmp_path / name).rename(project / name)
    declaration = request["execution_prerequisites"][0]["uv_projects"][0]
    declaration["project_directory"] = "workspace"
    report = runtime.preflight_validation(request)
    assert report["status"] == "ready"
    assert report["units"][0]["executor_observations"]["uv_projects"][0]["environment_path"] == str(project / "configured-env")
    declaration["environment_path"] = str(project / "configured-env")
    assert runtime.preflight_validation(request)["status"] == "ready"


@pytest.mark.parametrize("name", ["", "../python", "/bin/python", "bin/python", "python -m pytest"])
def test_uv_template_rejects_paths_and_commands_in_tool_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    request["execution_prerequisites"][0]["uv_projects"][0]["executables"] = [name]
    with pytest.raises(SchemaValidationError, match="uv_projects"):
        runtime.preflight_validation(request)


def test_published_uv_template_requires_only_environment_path_and_tool_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = _uv_request(tmp_path, monkeypatch)
    example_path = Path(runtime.__file__).parents[1] / "references" / "runtime-operation-examples-v1.json"
    example = json.loads(example_path.read_text(encoding="utf-8"))["preflight-validation"]["execution_prerequisites"][0]
    example["node_id"] = request["execution_prerequisites"][0]["node_id"]
    (tmp_path / "configured-env").rename(tmp_path / ".venv")
    request["execution_prerequisites"] = [example]
    assert runtime.preflight_validation(request)["status"] == "ready"
