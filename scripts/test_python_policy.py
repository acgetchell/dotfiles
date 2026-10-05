"""Regression tests for the repository-wide Python validation policy."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
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


def test_ci_runs_disjoint_prompt_and_remaining_test_phases_once() -> None:
    """Actual Just expansion and pytest collection retain each guard exactly once."""
    just_executable = shutil.which("just")
    assert just_executable is not None
    expanded = subprocess.run([just_executable, "--dry-run", "ci"], cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=True)  # noqa: S603
    commands = expanded.stderr
    assert commands.count("pytest -m review_contract") == 1
    assert commands.count("pytest -m 'not review_contract'") == 1
    assert commands.index("pytest -m review_contract") < commands.index("scripts/skill_validate.py") < commands.index("pytest -m 'not review_contract'")
    inventories = []
    for expression in (None, "review_contract", "not review_contract"):
        args = [sys.executable, "-m", "pytest", "--collect-only", "-q", "--color=no"]
        if expression:
            args += ["-m", expression]
        collected = subprocess.run(args, cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=True)  # noqa: S603 - local collection only.
        inventories.append({line for line in collected.stdout.splitlines() if ".py::" in line})
    complete, early, remaining = inventories
    assert early
    assert remaining
    assert not early & remaining
    assert complete == early | remaining
    assert all(node in early for node in complete if "prompt_budgets" in node)


def test_prompt_regression_stops_recipe_before_remaining_tests(tmp_path: Path) -> None:
    """An actual budget assertion survives recipe propagation without starting phase two."""
    just_executable = shutil.which("just")
    assert just_executable is not None
    test_source = tmp_path / "test_budget_regression.py"
    graph_scripts = REPOSITORY_ROOT / "agents/.agents/skills/review-graph/scripts"
    test_source.write_text(
        f"import sys\nsys.path.insert(0, {str(graph_scripts)!r})\n"
        "import test_review_graph_runtime as contracts\n"
        "def test_regression(monkeypatch):\n"
        "    monkeypatch.setattr(contracts, 'ORDINARY_PROMPT_WORD_BUDGET', 0)\n"
        "    contracts.test_ordinary_validator_and_all_surface_prompt_budgets()\n",
        encoding="utf-8",
    )
    log = tmp_path / "launches.jsonl"
    version = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())["tool"]["uv"]["required-version"].removeprefix("==")
    launcher = tmp_path / "uv"
    launcher.write_text(
        f"#!{sys.executable}\nimport json, subprocess, sys\nfrom pathlib import Path\n"
        f"with Path({str(log)!r}).open('a') as output: output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"if sys.argv[1:] == ['--version']: print('uv {version}'); sys.exit(0)\n"
        "if sys.argv[1:] == ['run', '--locked', 'pytest', '-m', 'review_contract']:\n"
        f"    sys.exit(subprocess.run([sys.executable, '-m', 'pytest', {str(test_source)!r}, '--color=no']).returncode)\n"
        "sys.exit('Unexpected command after failed contract gate')\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    result = subprocess.run(  # noqa: S603 - isolated launcher injects a failing budget, never edits reviewed instructions.
        [just_executable, "test-python"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ordinary coordinator prompt proxy is" in result.stdout
    assert [json.loads(line) for line in log.read_text().splitlines()] == [["--version"], ["run", "--locked", "pytest", "-m", "review_contract"]]
