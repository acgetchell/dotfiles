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


def test_ci_requires_full_python_inventory_and_shared_baseline() -> None:
    """CI includes fixtures once through the complete Python gate."""
    recipes = just_dump()["recipes"]
    for parent, child in (("ci", "check"), ("check", "python-ci"), ("python-ci", "python-check"), ("python-check", "python-baseline-check")):
        assert child in {dependency["recipe"] for dependency in recipes[parent]["dependencies"]}
    commands = [line[0] for line in recipes["python-check"]["body"]]
    for command in commands[:2]:
        assert "research-repo-tools files run --include '*.py' --include '*.pyi'" in command
        assert "--no-force-exclude" in command
        assert "--exclude" not in command
    assert "--no-fix" in commands[1]


def test_python_fixture_lint_uses_the_complete_ruff_configuration() -> None:
    """Fixture linting must not narrow the configured Ruff rule selection."""
    document = just_dump()
    recipe = document["recipes"]["python-fixture-lint"]
    command = recipe["body"][0]

    assert document["assignments"]["python_fixture_paths"]["value"] == "tests/semgrep"
    assert command == ["uv run --locked ruff check ", [["variable", "python_fixture_paths"]]]


def test_python_fix_excludes_deliberately_invalid_semgrep_fixtures() -> None:
    """The fixer must not rewrite deliberate negative-analysis fixtures."""
    commands = just_dump()["recipes"]["python-fix"]["body"]

    assert commands == [
        ["uv run --locked ruff check ", [["variable", "python_primary_paths"]], " --fix"],
        ["uv run --locked ruff format ", [["variable", "python_primary_paths"]]],
    ]
