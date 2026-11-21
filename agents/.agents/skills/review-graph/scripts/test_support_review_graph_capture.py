"""Temporary Git repositories and capture CLI invocations for scope tests."""

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence  # noqa: TC003 - keep available for runtime annotation evaluation.
from pathlib import Path
from typing import cast

_TIMEOUT_SECONDS = 30


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a fixture command in the given directory and surface stderr on failure."""
    result = subprocess.run(  # noqa: S603 - tests invoke resolved Git and the current Python executable only.
        command, cwd=cwd, check=False, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
    )
    assert result.returncode == 0, result.stderr
    return result


def _git(repo: Path, *arguments: str) -> str:
    """Return Git stdout with automatic maintenance disabled for the fixture repository."""
    git = shutil.which("git")
    assert git is not None
    # Keep the complete object/index mutation oracle independent of asynchronous
    # maintenance started by fixture commits, including inherited Git settings.
    return _run((git, "-c", "maintenance.auto=false", "-c", "gc.auto=0", *arguments), repo).stdout


def _init_repo(repo: Path) -> None:
    """Initialize the temporary repository with a local commit identity."""
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Review Graph Test")
    _git(repo, "config", "user.email", "review-graph@example.invalid")


def _commit_all(repo: Path) -> None:
    """Commit the fixture tree to give the capture a comparison point."""
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=Review Graph Test", "-c", "user.email=review-graph@example.invalid", "commit", "--quiet", "-m", "fixture")


def _capture(repo: Path, mode: str, *arguments: str) -> dict[str, object]:
    """Run the scope CLI and decode its successful JSON response."""
    script = Path(__file__).with_name("capture_scope.py")
    result = _run((sys.executable, str(script), "--repo", str(repo), "--mode", mode, *arguments), repo)
    payload: object = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert all(isinstance(key, str) for key in payload)
    return cast("dict[str, object]", payload)


def _capture_result(repo: Path, mode: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Preserve exit status and both output streams for CLI failure assertions."""
    script = Path(__file__).with_name("capture_scope.py")
    return subprocess.run(  # noqa: S603 - tests invoke the current Python executable only.
        (sys.executable, str(script), "--repo", str(repo), "--mode", mode, *arguments),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )
