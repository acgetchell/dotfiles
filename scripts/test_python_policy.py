"""Regression tests for the repository-wide Python validation policy."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def just_dump() -> dict[str, Any]:
    """Return Just's parsed representation of the repository command graph."""
    just_executable = shutil.which("just")
    assert just_executable is not None
    result = subprocess.run(  # noqa: S603 - the resolved executable and arguments are repository-controlled.
        [just_executable, "--justfile", str(REPOSITORY_ROOT / "justfile"), "--dump", "--dump-format", "json"],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    return cast("dict[str, Any]", json.loads(result.stdout))


def test_ci_directly_requires_python_fixture_lint() -> None:
    """The canonical CI recipe cannot bypass fixture linting."""
    dependencies = just_dump()["recipes"]["ci"]["dependencies"]

    assert "python-fixture-lint" in {dependency["recipe"] for dependency in dependencies}


def test_python_fixture_lint_uses_the_complete_ruff_configuration() -> None:
    """Fixture linting must not narrow the configured Ruff rule selection."""
    document = just_dump()
    recipe = document["recipes"]["python-fixture-lint"]
    command = recipe["body"][0]

    assert document["assignments"]["python_fixture_paths"]["value"] == "tests/semgrep"
    assert command == ["uv run --locked ruff check ", [["variable", "python_fixture_paths"]]]
