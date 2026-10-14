"""Explicit, frozen Python invocation policy for graph helper commands."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

CONTEXT_FILE = "execution-context.json"


def file_digest(path: Path) -> str:
    """Bind an execution prerequisite to its current bytes."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def interpreter_identity() -> dict[str, str]:
    """Identify the actual interpreter, including its version and executable bytes."""
    path = Path(sys.executable).resolve()
    return {"path": str(path), "digest": file_digest(path), "version": sys.version}


def _runner_policy(raw: object, repository: Path) -> dict[str, Any]:
    """Validate the explicit runner without executing it."""
    if not isinstance(raw, dict) or set(raw) != {"argv", "working_directory", "environment", "identity_files"}:
        msg = "Python runner requires argv, working_directory, environment and identity_files"
        raise ValueError(msg)
    argv, environment, files = raw["argv"], raw["environment"], raw["identity_files"]
    if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) or not arg for arg in argv):
        msg = "Python runner argv requires nonempty literal arguments"
        raise ValueError(msg)
    if not isinstance(environment, dict) or any(not isinstance(k, str) or not k or "=" in k or not isinstance(v, str) for k, v in environment.items()):
        msg = "Python runner environment requires string names and values"
        raise ValueError(msg)
    if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
        msg = "Python runner identity_files requires explicit paths"
        raise ValueError(msg)
    if not isinstance(raw["working_directory"], str):
        msg = "Python runner working_directory requires an absolute path"
        raise TypeError(msg)
    directory = Path(raw["working_directory"])
    if not directory.is_absolute() or directory.resolve() != repository.resolve():
        msg = "Python runner working_directory must be the captured repository"
        raise ValueError(msg)
    executable = Path(argv[0])
    if not executable.is_absolute() or not executable.is_file():
        msg = "Python runner executable must be an existing absolute path"
        raise ValueError(msg)
    paths = [Path(path) for path in files]
    if any(not path.is_absolute() or not path.is_file() for path in paths) or len(set(paths)) != len(paths):
        msg = "Python runner identity_files requires unique existing absolute files"
        raise ValueError(msg)
    _check_uv_policy(executable, argv, directory, paths, environment, repository=repository)
    return raw


def _check_uv_policy(  # noqa: PLR0913 - explicit policy components, no ambient runner configuration.
    executable: Path, argv: list[str], directory: Path, paths: list[Path], environment: dict[str, str], *, repository: Path
) -> None:
    if executable.stem == "uv":
        if "run" not in argv or "--locked" not in argv or not {directory / "uv.lock", directory / "pyproject.toml"} <= set(paths):
            msg = "uv runner requires run --locked and both project/lock identities"
            raise ValueError(msg)
        cache = Path(environment.get("UV_CACHE_DIR", ""))
        if not cache.is_absolute() or not cache.is_dir() or cache.resolve().is_relative_to(repository.resolve()) or not os.access(cache, os.W_OK):
            msg = "uv runner requires an explicitly approved, existing writable external UV_CACHE_DIR"
            raise ValueError(msg)


def capture_execution_context(raw: object, repository: Path) -> dict[str, Any]:
    """Probe only the operator-selected runner and retain its prerequisite identities."""
    policy = _runner_policy(raw, repository)
    argv, environment = policy["argv"], policy["environment"]
    executable, directory = Path(argv[0]), Path(policy["working_directory"])
    paths = [Path(path) for path in policy["identity_files"]]
    env_executable = shutil.which("env") if environment else None
    if environment and env_executable is None:
        msg = "environment-bearing Python runner requires an available env executable"
        raise ValueError(msg)
    identities = {str(path): file_digest(path) for path in [executable, *paths, *([Path(env_executable)] if env_executable is not None else [])]}
    probe = (
        "import hashlib,json,sys; from pathlib import Path; p=Path(sys.executable).resolve(); "
        "print(json.dumps(dict(path=str(p),digest='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest(),version=sys.version)))"
    )
    result = subprocess.run(  # noqa: S603 - exact operator-approved runner, only an interpreter identity probe.
        [*argv, "-c", probe], cwd=directory, env={**os.environ, **environment}, capture_output=True, text=True, check=True, timeout=60
    )
    if json.loads(result.stdout) != interpreter_identity():
        msg = "Python runner resolves to a different interpreter than the frozen runtime"
        raise ValueError(msg)
    context = {**policy, "working_directory": str(directory.resolve()), "identities": identities, "env_executable": env_executable}
    verify_execution_context(context)
    return context


def verify_execution_context(context: dict[str, Any]) -> None:
    """Reject changed runner or dependency-lock bytes before helper execution."""
    for path, digest in context["identities"].items():
        if file_digest(Path(path)) != digest:
            raise ValueError(f"Python runner prerequisite identity changed: {path}")


def command_prefix(context: dict[str, Any] | None) -> list[str]:
    """Render the literal operator runner and cache assignment as executable argv."""
    if context is None:
        return [str(Path(sys.executable).absolute())]
    verify_execution_context(context)
    prefix = [context["env_executable"], *(f"{key}={value}" for key, value in sorted(context["environment"].items()))] if context["environment"] else []
    return [*prefix, *context["argv"]]
