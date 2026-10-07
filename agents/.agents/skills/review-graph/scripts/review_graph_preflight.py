"""Read-only executable observations for explicitly inspected uv project recipes."""

import os
import shutil
import tomllib
from pathlib import Path
from typing import Any


def _project_path(raw: str, root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _environment_executable(name: str, directory: Path) -> dict[str, Any]:
    candidates = [directory / name]
    if os.name == "nt" and Path(name).suffix.lower() not in {".exe", ".com", ".bat", ".cmd"}:
        candidates = [directory / (name + suffix) for suffix in (".exe", ".com", ".bat", ".cmd")]
    path = next((candidate for candidate in candidates if candidate.is_file() and os.access(candidate, os.X_OK)), None)
    return {"executable": name, "path": str(path or candidates[0]), "resolved_path": str(path.resolve()) if path else None, "available": path is not None}


def _project_files(project: Path, environment: Path) -> list[str]:
    blockers: list[str] = []
    for name in ("pyproject.toml", "uv.lock"):
        path = project / name
        try:
            metadata = tomllib.loads(path.read_text(encoding="utf-8"))
            if name == "uv.lock" and (type(metadata.get("version")) is not int or not isinstance(metadata.get("requires-python"), str)):
                blockers.append(f"uv project metadata invalid: {path}: expected integer version and string requires-python fields")
        except (OSError, UnicodeError, ValueError) as error:
            blockers.append(f"uv project metadata unavailable: {path}: {error}")
    try:
        configuration = (environment / "pyvenv.cfg").read_text(encoding="utf-8")
        if not any(line.partition("=")[0].strip() == "home" and line.partition("=")[2].strip() for line in configuration.splitlines()):
            blockers.append(f"uv project environment invalid: {environment}/pyvenv.cfg has no Python home")
    except (OSError, UnicodeError) as error:
        blockers.append(f"uv project environment unavailable: {environment}: {error}")
    return blockers


def _inspect_uv_project(declaration: dict[str, Any], repository_root: Path) -> dict[str, Any]:
    project = _project_path(declaration["project_directory"], repository_root)
    environment = _project_path(declaration["environment_path"], project)
    blockers = _project_files(project, environment)
    directory = environment / ("Scripts" if os.name == "nt" else "bin")
    # Every environment requires its own interpreter, even for console tools.
    executables = [_environment_executable(name, directory) for name in dict.fromkeys(("python", *declaration["executables"]))]
    blockers.extend(f"uv project executable unavailable: {item['path']}" for item in executables if not item["available"])
    configured_python = declaration.get("configured_python")
    configured_observation = None
    if configured_python is not None:
        path = _project_path(configured_python, project)
        available = path.is_file() and os.access(path, os.X_OK)
        matches = available and executables[0]["available"] and path.resolve() == Path(executables[0]["resolved_path"])
        configured_observation = {"path": str(path), "available": available, "matches_environment": matches}
        if not matches:
            blockers.append(f"configured uv interpreter unavailable or differs from project environment: {path}")
    return {
        "project_directory": str(project),
        "environment_path": str(environment),
        "executables": executables,
        "configured_python": configured_observation,
        "blockers": blockers,
    }


def inspect_executor_executables(prerequisite: dict[str, Any], repository_root: Path) -> tuple[dict[str, Any], list[str]]:
    """Resolve declared host tools and uv tools separately without launching either."""
    host = [{"executable": name, "resolved_path": shutil.which(name)} for name in prerequisite["executables"]]
    projects = [_inspect_uv_project(item, repository_root) for item in prerequisite.get("uv_projects", [])]
    blockers = [f"executor executable unavailable: {item['executable']}" for item in host if item["resolved_path"] is None]
    blockers.extend(blocker for project in projects for blocker in project["blockers"])
    return {"host_executables": host, "uv_projects": projects}, blockers
