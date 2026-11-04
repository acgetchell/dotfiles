"""Regression tests for the repository-wide Python validation policy."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from research_repo_tools.just_inspect import dry_run, inspect_justfile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_TESTS = "agents/.agents/skills/review-graph/scripts/test_review_graph_contracts.py"


def test_native_scan_uses_configured_scanner_despite_root_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = tmp_path / "independent scanner environment"
    monkeypatch.setenv("DOTFILES_SEMGREP_ENVIRONMENT", str(scanner))
    commands = dry_run(REPOSITORY_ROOT, "semgrep").stderr.splitlines()
    scan = shlex.split(next(line for line in commands if "research-repo-tools files run" in line))
    binary = scanner / ("Scripts/semgrep.exe" if os.name == "nt" else "bin/semgrep")
    assert Path(scan[scan.index("--") + 1]) == binary


def test_ci_requires_full_python_inventory_and_shared_baseline() -> None:
    """CI includes fixtures once through the complete Python gate."""
    recipes = inspect_justfile(REPOSITORY_ROOT).recipes
    for parent, child in (("ci", "check"), ("check", "python-ci"), ("python-ci", "python-check")):
        assert child in {dependency["recipe"] for dependency in recipes[parent]["dependencies"]}
    assert recipes["python-check"]["body"] == [["uv run --locked --group dev research-repo-tools python check"]]
    assert recipes["python-typecheck"]["body"] == [["uv run --locked --group dev research-repo-tools python typecheck"]]


def test_scanner_guard_rejects_executable_in_stale_environment(tmp_path: Path) -> None:
    """An executable alone must not authorize scanning against a stale lock."""
    scanner_environment = Path(os.environ.get("DOTFILES_SEMGREP_ENVIRONMENT", REPOSITORY_ROOT / "tooling/semgrep/.venv"))
    stale = tmp_path / "stale scanner"
    uv = shutil.which("uv")
    just = shutil.which("just")
    assert uv is not None
    assert just is not None
    subprocess.run(  # noqa: S603 - real empty environment in a disposable fixture.
        [uv, "venv", "--python", str(scanner_environment / "bin/python"), str(stale)], check=True, capture_output=True, timeout=30
    )
    scanner = stale / "bin/semgrep"
    scanner.write_text("#!/bin/sh\nexit 0\n")
    scanner.chmod(0o700)

    def snapshot() -> dict[str, tuple[str, bytes | str]]:
        """Preserve object types, file bytes, and literal symlink targets."""
        return {
            str(path.relative_to(stale)): ("symlink", str(path.readlink()))
            if path.is_symlink()
            else ("file", path.read_bytes())
            if path.is_file()
            else ("directory", "")
            for path in stale.rglob("*")
            if path != stale / ".lock"
        }

    before = snapshot()
    result = subprocess.run(  # noqa: S603 - actual recipe validates the isolated stale environment without synchronizing it.
        [just, "_ensure-semgrep"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "DOTFILES_SEMGREP_ENVIRONMENT": str(stale), "UV_OFFLINE": "1"},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "Run just python-sync" in result.stderr
    assert scanner.read_text() == "#!/bin/sh\nexit 0\n"
    # uv may create its synchronization lock even when --check installs nothing.
    assert snapshot() == before


def test_scanner_guard_ignores_root_python_selector() -> None:
    """The real locked scanner check works when the site selects root Python 3.15."""
    just = shutil.which("just")
    assert just is not None
    result = subprocess.run(  # noqa: S603 - read-only locked check of the provisioned scanner environment.
        [just, "_ensure-semgrep"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "UV_PYTHON": sys.executable, "UV_OFFLINE": "1"},
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_python_sync_keeps_root_python_selector_out_of_scanner(tmp_path: Path) -> None:
    """Execute the real recipe and observe selector scope at each uv boundary."""
    just = shutil.which("just")
    assert just is not None
    log = tmp_path / "sync-environments.jsonl"
    version = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())["tool"]["uv"]["required-version"].removeprefix("==")
    launcher = tmp_path / "uv"
    launcher.write_text(
        f"#!{sys.executable}\nimport json, os, sys\nfrom pathlib import Path\n"
        f"if sys.argv[1:] == ['--version']: print('uv {version}'); sys.exit(0)\n"
        "record = {'argv': sys.argv[1:], 'python': os.environ.get('UV_PYTHON'), 'environment': os.environ.get('UV_PROJECT_ENVIRONMENT')}\n"
        f"with Path({str(log)!r}).open('a') as output: output.write(json.dumps(record) + '\\n')\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    scanner_environment = tmp_path / "scanner environment"
    result = subprocess.run(  # noqa: S603 - real recipe with a recording uv launcher; no packages are installed.
        [just, "python-sync"],
        cwd=REPOSITORY_ROOT,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "UV_PYTHON": sys.executable,
            "DOTFILES_SEMGREP_ENVIRONMENT": str(scanner_environment),
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 2
    root, scanner = calls
    assert root["argv"] == ["sync", "--locked", "--group", "dev"]
    assert root["python"] == sys.executable
    assert scanner == {"argv": ["sync", "--locked", "--project", "tooling/semgrep"], "python": None, "environment": str(scanner_environment)}


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


def _assert_focused_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workers: str | None) -> None:
    """Real Just preserves selector arguments and runs each phase once."""
    if workers is None:
        monkeypatch.delenv("DOTFILES_TEST_WORKERS", raising=False)
    else:
        monkeypatch.setenv("DOTFILES_TEST_WORKERS", workers)
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
    selection = [str(tmp_path / "test quoted.py"), "-k", "selected or other", "--durations=25", "-n", "0"]
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
        ["run", "--locked", "pytest", CONTRACT_TESTS, "-n", "0"],
        ["run", "--locked", "pytest", "--ignore", CONTRACT_TESTS, "-n", workers or "4", "--dist", "worksteal", "--max-worker-restart", "0", *selection],
    ]


def test_focused_selection_forwards_arguments_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _assert_focused_selection(tmp_path, monkeypatch, None)


@pytest.mark.parametrize("workers", ["2", "0"])
def test_worker_override_preserves_selection_and_serial_contract_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workers: str) -> None:
    _assert_focused_selection(tmp_path, monkeypatch, workers)


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
        f"if sys.argv[1:] == ['run', '--locked', 'pytest', {CONTRACT_TESTS!r}, '-n', '0']:\n"
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
    assert [json.loads(line) for line in log.read_text().splitlines()] == [["--version"], ["run", "--locked", "pytest", CONTRACT_TESTS, "-n", "0"]]


def test_parallel_recipe_runs_every_case_and_propagates_worker_failure(tmp_path: Path) -> None:
    """Real workers retain passing cases and an intentional assertion failure."""
    just_executable = shutil.which("just")
    assert just_executable is not None
    version = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())["tool"]["uv"]["required-version"].removeprefix("==")
    launcher = tmp_path / "uv"
    delegations = tmp_path / "pytest-arguments.jsonl"
    launcher.write_text(
        f"#!{sys.executable}\nimport json, subprocess, sys\nfrom pathlib import Path\n"
        f"if sys.argv[1:] == ['--version']: print('uv {version}'); sys.exit(0)\n"
        f"if sys.argv[1:] == ['run', '--locked', 'pytest', {CONTRACT_TESTS!r}, '-n', '0']: sys.exit(0)\n"
        "assert sys.argv[1:4] == ['run', '--locked', 'pytest']\n"
        f"with Path({str(delegations)!r}).open('a') as output: output.write(json.dumps(sys.argv[4:]) + '\\n')\n"
        "sys.exit(subprocess.run([sys.executable, '-m', 'pytest', *sys.argv[4:]]).returncode)\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    test_source = tmp_path / "test_parallel_failure.py"
    test_source.write_text(
        "import os\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.mark.parametrize('case', range(8))\n"
        "def test_case(case):\n"
        f"    Path({str(tmp_path)!r}, f'executed-{{case}}').write_text(os.environ['PYTEST_XDIST_WORKER'])\n"
        "    assert case != 3, 'intentional parallel regression'\n",
        encoding="utf-8",
    )
    report = tmp_path / "results.xml"
    result = subprocess.run(  # noqa: S603 - the contract gate is stubbed; real workers execute an isolated failing fixture.
        [just_executable, "test-python", str(test_source), "-n", "2", "--color=no", f"--junitxml={report}"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "PYTEST_ADDOPTS": ""},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert "intentional parallel regression" in result.stdout
    arguments = [json.loads(line) for line in delegations.read_text().splitlines()]
    assert len(arguments) == 1
    assert str(test_source) in arguments[0]
    cases = list(ET.parse(report).iter("testcase"))  # noqa: S314 - generated by this local pytest fixture, never supplied externally.
    assert {case.attrib["name"] for case in cases} == {f"test_case[{index}]" for index in range(8)}
    assert len(cases) == 8
    assert sum(case.find("failure") is not None for case in cases) == 1
    assert not any(case.find("skipped") is not None or case.find("error") is not None for case in cases)
    assert {path.name for path in tmp_path.glob("executed-*")} == {f"executed-{index}" for index in range(8)}
    assert {(tmp_path / f"executed-{index}").read_text() for index in range(8)} == {"gw0", "gw1"}
