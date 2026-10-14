"""Regression tests for the repository-wide Python validation policy."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from research_repo_tools.just_inspect import dry_run, inspect_justfile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_TESTS = "agents/.agents/skills/review-graph/scripts/test_review_graph_contracts.py"


def test_ci_requires_full_python_inventory_and_shared_baseline() -> None:
    """CI includes fixtures once through the complete Python gate."""
    recipes = inspect_justfile(REPOSITORY_ROOT).recipes
    for parent, child in (("ci", "check"), ("check", "python-ci"), ("python-ci", "python-check")):
        assert child in {dependency["recipe"] for dependency in recipes[parent]["dependencies"]}
    assert recipes["python-check"]["body"] == [["uv run --locked --group dev research-repo-tools python check"]]
    assert recipes["python-typecheck"]["body"] == [["uv run --locked --group dev research-repo-tools python typecheck"]]


@pytest.mark.parametrize("overrides", [False, True])
def test_python_updater_rejects_lost_project_overrides_before_mutation(tmp_path: Path, *, overrides: bool) -> None:
    """A real preflight process protects the manifest/lock before shared resolution."""
    content = "[tool.uv]\n" + ("override-dependencies = [\"pywin32==312; sys_platform == 'win32'\"]\n" if overrides else "")
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(content)
    lock = tmp_path / "uv.lock"
    lock.write_text("preserved lock\n")
    result = subprocess.run(  # noqa: S603 - fixed local guard in an isolated consumer directory.
        [sys.executable, str(REPOSITORY_ROOT / "scripts/python_update_preflight.py")], cwd=tmp_path, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == int(overrides)
    assert result.stdout == ""
    assert ("isolated resolver" in result.stderr) == overrides
    assert manifest.read_text() == content
    assert lock.read_text() == "preserved lock\n"
    recipe = inspect_justfile(REPOSITORY_ROOT).recipes["update-python-dependencies"]
    commands = "\n".join(line[0] for line in recipe["body"] if line and isinstance(line[0], str))
    assert commands.index("python_update_preflight.py") < commands.index("just _shared-deps update-python")


@pytest.mark.parametrize(
    ("content", "diagnostic"),
    [
        ('"""Fixture."""\n\nvalue=1\n', "would be reformatted"),
        ('"""Fixture."""\n\nprint(undefined_value)\n', "F821"),
        ('"""Fixture."""\n\nvalue: int = "wrong"\n', "invalid-assignment"),
    ],
)
def test_shared_python_gate_checks_excluded_consumer_fixtures(tmp_path: Path, content: str, diagnostic: str) -> None:
    """The published command catches each failure even under native tool exclusions."""
    for name in ("pyproject.toml", ".python-version"):
        shutil.copy2(REPOSITORY_ROOT / name, tmp_path)
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(manifest.read_text().replace("[tool.ruff]\n", '[tool.ruff]\nexclude = ["tests/semgrep"]\n'), encoding="utf-8")
    fixture = tmp_path / "tests/semgrep/negative.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(content, encoding="utf-8")
    git = shutil.which("git")
    executable = shutil.which("research-repo-tools")
    assert git is not None
    assert executable is not None
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True, capture_output=True)  # noqa: S603 - isolated consumer repository.
    result = subprocess.run(  # noqa: S603 - installed public checker against a disposable consumer fixture.
        [executable, "--root", str(tmp_path), "python", "check"], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode != 0
    assert diagnostic in result.stdout + result.stderr, result.stdout + result.stderr
    assert fixture.read_text() == content


def test_python_fixture_lint_uses_the_complete_ruff_configuration() -> None:
    """Fixture linting must not narrow the configured Ruff rule selection."""
    recipe = inspect_justfile(REPOSITORY_ROOT).recipes["python-fixture-lint"]
    command = recipe["body"][0]

    assert "ruff check tests/semgrep" in dry_run(REPOSITORY_ROOT, "python-fixture-lint").stderr
    assert command == ["uv run --locked ruff check ", [["variable", "python_fixture_paths"]]]


def test_python_fix_excludes_deliberately_invalid_semgrep_fixtures() -> None:
    """The fixer must not rewrite deliberate negative-analysis fixtures."""
    commands = inspect_justfile(REPOSITORY_ROOT).recipes["python-fix"]["body"]

    assert commands == [
        ["uv run --locked ruff check ", [["variable", "python_primary_paths"]], " --fix"],
        ["uv run --locked ruff format ", [["variable", "python_primary_paths"]]],
    ]


def test_ci_runs_disjoint_prompt_and_remaining_test_phases_once(request: pytest.FixtureRequest) -> None:
    """Actual Just expansion partitions the inventory already collected by this run."""
    expanded = dry_run(REPOSITORY_ROOT, "ci")
    commands = expanded.stderr
    early_command = f"pytest {CONTRACT_TESTS}"
    remaining_command = f"pytest --ignore {CONTRACT_TESTS}"
    assert commands.count(early_command) == 1
    assert commands.count(remaining_command) == 1
    assert commands.index(early_command) < commands.index("scripts/skill_validate.py") < commands.index(remaining_command)
    contract_path = REPOSITORY_ROOT / CONTRACT_TESTS
    for item in request.session.items:
        is_contract = item.path == contract_path
        assert (item.get_closest_marker("review_contract") is not None) == is_contract, item.nodeid
        if "prompt_budgets" in item.name:
            assert is_contract, item.nodeid


def test_contract_gate_collects_only_its_module() -> None:
    """The bounded early collector must not import other review-graph test modules."""
    arguments = [CONTRACT_TESTS, "--collect-only", "-q", "--color=no"]
    program = (
        "import sys, pytest\n"
        f"code = pytest.main({arguments!r})\n"
        "unexpected = [name for name in sys.modules if name.startswith('test_review_graph_') and name != 'test_review_graph_contracts']\n"
        "assert not unexpected, unexpected\n"
        "raise SystemExit(code)\n"
    )
    result = subprocess.run(  # noqa: S603 - only the explicit local contract module is collected.
        [sys.executable, "-c", program], cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    nodes = [line for line in result.stdout.splitlines() if ".py::" in line]
    assert nodes
    assert all(Path(node.split("::", 1)[0]) == Path(CONTRACT_TESTS) for node in nodes)
    assert any("test_ordinary_validator_and_all_surface_prompt_budgets" in node for node in nodes)


def test_focused_selection_forwards_arguments_once(tmp_path: Path) -> None:
    """Real Just preserves selector arguments and runs each phase once."""
    just_executable = shutil.which("just")
    assert just_executable is not None
    log = tmp_path / "launches.jsonl"
    version = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())["tool"]["uv"]["required-version"].removeprefix("==")
    launcher = tmp_path / "uv"
    launcher.write_text(
        f"#!{sys.executable}\nimport json, sys\nfrom pathlib import Path\n"
        f"with Path({str(log)!r}).open('a') as output: output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"if sys.argv[1:] == ['--version']: print('uv {version}')\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    selection = [str(tmp_path / "test quoted.py"), "-k", "selected or other", "--durations=25"]
    result = subprocess.run(  # noqa: S603 - real recipe uses a recording launcher instead of running tests.
        [just_executable, "test-python", *selection],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert [json.loads(line) for line in log.read_text().splitlines()] == [
        ["--version"],
        ["run", "--locked", "pytest", CONTRACT_TESTS],
        ["run", "--locked", "pytest", "--ignore", CONTRACT_TESTS, *selection],
    ]


def test_prompt_regression_stops_recipe_before_remaining_tests(tmp_path: Path) -> None:
    """An actual budget assertion survives recipe propagation without starting phase two."""
    just_executable = shutil.which("just")
    assert just_executable is not None
    test_source = tmp_path / "test_budget_regression.py"
    graph_scripts = REPOSITORY_ROOT / "agents/.agents/skills/review-graph/scripts"
    test_source.write_text(
        f"import sys\nsys.path.insert(0, {str(graph_scripts)!r})\n"
        "import test_review_graph_contracts as contracts\n"
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
        f"if sys.argv[1:] == ['run', '--locked', 'pytest', {CONTRACT_TESTS!r}]:\n"
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
    assert [json.loads(line) for line in log.read_text().splitlines()] == [["--version"], ["run", "--locked", "pytest", CONTRACT_TESTS]]
