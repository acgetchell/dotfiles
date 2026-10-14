"""Exercise scanner ownership and production path filters with the pinned tools."""

import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest
import yaml
from research_repo_tools.process import run_command_bytes
from research_repo_tools.semgrep_findings import parse_results

REPOSITORY = Path(__file__).resolve().parents[1]


def _path_fixtures(tmp_path: Path, *, selected: tuple[str, ...] | None = None) -> tuple[list[str], dict[str, list[int]]]:
    """Share literal rule/path expectations across native scanning and the harness."""
    config = yaml.safe_load((REPOSITORY / "semgrep.yaml").read_text())
    retirement_rule_id = "dotfiles.github-actions.no-retired-coderabbit-token"
    rules = [rule for rule in config["rules"] if rule["id"].startswith("dotfiles.review-graph.") or rule["id"] == retirement_rule_id]
    (tmp_path / "semgrep.yaml").write_text(yaml.safe_dump({"rules": rules}))
    source = """def compile_review():
    return {"record_type": "review"}

def recover_validation_launch(path, value):
    path.write_text(value)

def parse(value, items):
    return next(items), value in {True, None}
"""
    owned = "agents/.agents/skills/review-graph/scripts"
    expected = {
        f"{owned}/review_graph_runtime.py": [1, 1, 1, 1, 0],
        f"{owned}/test_runtime.py": [0, 0, 0, 0, 0],
        f"{owned}/other.py": [1, 0, 0, 1, 0],
        "scripts/review_graph_runtime.py": [0, 0, 0, 0, 0],
        ".github/workflows/dependabot-auto-merge.yml": [0, 0, 0, 0, 1],
        "docs/dependabot-auto-merge.yml": [0, 0, 0, 0, 0],
    }
    # Explicit counts below depend on the rule identity, never its configuration order.
    ids = [
        "dotfiles.review-graph.no-bare-next",
        "dotfiles.review-graph.compiler-uses-canonical-normalizer",
        "dotfiles.review-graph.recovery-publication-must-be-atomic",
        "dotfiles.review-graph.boolean-membership-is-not-type-check",
        retirement_rule_id,
    ]
    if selected is not None:
        expected = {path: expected[path] for path in selected}
    # A fixture root containing only source inputs allows the shared harness to
    # retain their real repository-relative paths without reading config as input.
    for fixture in expected:
        path = tmp_path / "inputs" / fixture
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source if path.suffix == ".py" else "env:\n  GH_TOKEN: ${{ secrets.CODERABBIT_REVIEW_TOKEN }}\n")
    return ids, expected


def _scanner_environment(tmp_path: Path) -> dict[str, str]:
    environment = {
        **os.environ,
        "SEMGREP_SEND_METRICS": "off",
        "OTEL_SDK_DISABLED": "true",
        "SEMGREP_SETTINGS_FILE": str(tmp_path / "settings.yml"),
        "SEMGREP_VERSION_CACHE_PATH": str(tmp_path / "version-cache"),
        "SEMGREP_LOG_FILE": str(tmp_path / "semgrep.log"),
    }
    if Path("/etc/ssl/cert.pem").is_file():
        environment["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
    return environment


def test_production_path_filters_cover_every_owned_rule(tmp_path: Path) -> None:
    """Batch the complete path matrix while retaining the native scanner filters."""
    ids, expected = _path_fixtures(tmp_path)
    executable = shutil.which("semgrep")
    assert executable is not None
    result = run_command_bytes(
        executable,
        (
            "scan",
            "--disable-version-check",
            "--metrics",
            "off",
            "--json",
            "--quiet",
            "--strict",
            "--no-rewrite-rule-ids",
            "--config",
            str(tmp_path / "semgrep.yaml"),
            *expected,
        ),
        cwd=tmp_path / "inputs",
        env=_scanner_environment(tmp_path),
        timeout=120,
    )
    findings = parse_results(result.stdout.decode()).results
    actual = Counter((finding.path, finding.check_id) for finding in findings)
    required = Counter({(Path(path), rule): count for path, counts in expected.items() for rule, count in zip(ids, counts, strict=True) if count})
    assert actual == required


def test_production_paths_with_shared_count_fixtures(tmp_path: Path) -> None:
    """The shared harness enforces positive counts and a production-path exclusion."""
    owned = "agents/.agents/skills/review-graph/scripts"
    ids, expected = _path_fixtures(tmp_path, selected=(f"{owned}/review_graph_runtime.py", f"{owned}/test_runtime.py"))
    manifest = '[tool.research-repo-tools.semgrep]\nconfig = "semgrep.yaml"\nfixtures = "inputs"\ncwd = "inputs"\nnamespace = "dotfiles.review-graph."\n'
    for fixture, counts in expected.items():
        manifest += f'\n[tool.research-repo-tools.semgrep.counts."inputs/{fixture}"]\n'
        manifest += "".join(f'"{rule}" = {count}\n' for rule, count in zip(ids, counts, strict=True))
    (tmp_path / "pyproject.toml").write_text(manifest)
    executable = shutil.which("research-repo-tools")
    assert executable is not None
    result = subprocess.run(  # noqa: S603
        [executable, "--root", str(tmp_path), "semgrep", "check-fixtures"],
        capture_output=True,
        text=True,
        env=_scanner_environment(tmp_path),
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_python315_policy_and_consolidated_lock_rule_cover_production_paths(tmp_path: Path) -> None:
    """Exercise aliases, owned paths, exclusions, and both uv subcommands."""
    ids = [
        "dotfiles.python315.no-global-lazy-imports",
        "dotfiles.skills.safe-yaml-loader",
        "dotfiles.python315.no-global-jit-default",
        "dotfiles.tooling.uv-run-locked",
    ]
    config = yaml.safe_load((REPOSITORY / "semgrep.yaml").read_text())
    rules = [rule for rule in config["rules"] if rule["id"] in ids]
    assert len(rules) == len(ids)
    assert "dotfiles.github-actions.uv-sync-locked-in-workflows" not in {rule["id"] for rule in config["rules"]}
    config_path = tmp_path / "semgrep.yaml"
    config_path.write_text(yaml.safe_dump({"rules": rules}))
    python = """import sys as runtime
import yaml as parser
from yaml import FullLoader
runtime.set_lazy_imports("all")
parser.CFullLoader("")
getattr(parser, "CLoader", parser.SafeLoader)("")
FullLoader("")
"""
    commands = """export PYTHON_JIT := "1"
export PYTHON_JIT := '1' # enable JIT
export PYTHON_JIT := "0" # keep the default
uv sync
uv run pytest
PYTHON_JIT=1 uv sync --locked
UV_CACHE_DIR="cache" uv run --locked pytest
"""
    owned = "agents/.agents/skills/review-graph/scripts"
    expected = {
        "scripts/skill_validate.py": [1, 3, 0, 0],
        "scripts/linux_review.py": [1, 0, 0, 0],
        "scripts/test_runtime.py": [0, 0, 0, 0],
        f"{owned}/capture_scope.py": [1, 0, 0, 0],
        f"{owned}/test_runtime.py": [0, 0, 0, 0],
        "docs/runtime.py": [0, 0, 0, 0],
        "justfile": [0, 0, 2, 2],
        "bin/check.sh": [0, 0, 0, 2],
        ".github/workflows/check.yml": [0, 0, 0, 2],
        "docs/example.sh": [0, 0, 0, 0],
    }
    for name in expected:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(python if path.suffix == ".py" else commands)
    executable = shutil.which("semgrep")
    assert executable is not None
    result = run_command_bytes(
        executable,
        (
            "scan",
            "--disable-version-check",
            "--metrics",
            "off",
            "--json",
            "--quiet",
            "--strict",
            "--no-rewrite-rule-ids",
            "--config",
            str(config_path),
            *expected,
        ),
        cwd=tmp_path,
        env=_scanner_environment(tmp_path),
        timeout=120,
    )
    actual = Counter((finding.path, finding.check_id) for finding in parse_results(result.stdout.decode()).results)
    required = Counter({(Path(path), rule): count for path, counts in expected.items() for rule, count in zip(ids, counts, strict=True) if count})
    assert actual == required


def _zizmor_finding_ids(path: Path) -> set[str]:
    """Run the pinned offline audit with the repository's regular persona."""
    executable = shutil.which("zizmor")
    assert executable is not None
    result = subprocess.run(  # noqa: S603
        [
            executable,
            "--offline",
            "--persona",
            "regular",
            "--no-config",
            "--no-progress",
            "--format",
            "json",
            "--cache-dir",
            str(path.parent / "cache"),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode in {0, 10, 11, 12, 13, 14}, result.stderr
    return {finding["ident"] for finding in json.loads(result.stdout)}


@pytest.mark.parametrize("form", ["named", "shorthand", "reusable"])
def test_zizmor_owns_sha_pinning(tmp_path: Path, form: str) -> None:
    """Removing the Semgrep duplicate preserves the gate for every workflow form."""
    sha = "1111111111111111111111111111111111111111"
    prefix = "name: Audit\non: workflow_dispatch\npermissions: {}\njobs:\n  check:\n"
    if form == "reusable":
        source = (REPOSITORY / ".github/workflows/dependabot-auto-merge.yml").read_text()
        sha = source.split("dependabot-approve.yml@", 1)[1].split()[0]
    else:
        prefix += "    runs-on: ubuntu-latest\n    steps:\n"
        prefix += "      - name: Setup\n        " if form == "named" else "      - "
        source = prefix + f"uses: actions/setup-python@{sha} # v7.0.0\n"
    path = tmp_path / "workflow.yml"
    for revision, expected in ((sha, False), ("v7", True)):
        path.write_text(source.replace(sha, revision))
        assert ("unpinned-uses" in _zizmor_finding_ids(path)) is expected


@pytest.mark.parametrize(
    "declaration",
    ["on:\n  {event}:\n", "on: {event}\n", "on: [push, {event}]\n", "on:\n  - {event}\n", '"on":\n  "{event}":\n'],
    ids=["mapping", "scalar", "flow-list", "block-list", "quoted"],
)
def test_zizmor_owns_dangerous_triggers(tmp_path: Path, declaration: str) -> None:
    """Retain each retired Semgrep trigger case and its compliant counterpart."""
    path = tmp_path / "workflow.yml"
    job = "permissions: {}\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n"
    for event, expected in (("pull_request", False), ("pull_request_target", True)):
        path.write_text("name: Audit\n" + declaration.format(event=event) + job)
        assert ("dangerous-triggers" in _zizmor_finding_ids(path)) is expected
