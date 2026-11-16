"""Exercise the published pin checker through dotfiles' actual offline recipe."""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[1]


def _consumer(tmp_path: Path) -> Path:
    root = tmp_path / "workflow consumer ü"
    shutil.copytree(REPOSITORY / ".github/workflows", root / ".github/workflows")
    shutil.copy2(REPOSITORY / ".github/action-updates.toml", root / ".github/action-updates.toml")
    for name in ("justfile", "pyproject.toml", "uv.lock"):
        shutil.copy2(REPOSITORY / name, root / name)
    return root


def _check(root: Path) -> subprocess.CompletedProcess[str]:
    just = shutil.which("just")
    assert just is not None
    return subprocess.run(  # noqa: S603 - actual consumer recipe against copied policy/workflows and the installed package.
        [just, "actions-check"],
        cwd=root,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": sys.prefix, "UV_CACHE_DIR": str(root / ".uv-cache"), "UV_OFFLINE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_published_checker_accepts_current_workflows_without_changing_inputs(tmp_path: Path) -> None:
    root = _consumer(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    result = _check(root)

    assert result.returncode == 0, result.stderr
    assert "Actions pin consistency passed" in result.stdout
    assert "offline, no files changed" in result.stdout
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize("workflow", ["ci.yml", "zizmor.yml"])
@pytest.mark.parametrize("field", ["sha", "version"])
def test_partial_workflow_bump_fails_with_locations(tmp_path: Path, workflow: str, field: str) -> None:
    root = _consumer(tmp_path)
    path = root / ".github/workflows" / workflow
    original = path.read_text()
    line = next(line for line in original.splitlines() if "uses: astral-sh/setup-uv@" in line)
    previous = line.split("@", 1)[1].split()[0] if field == "sha" else line.split("#", 1)[1].strip()
    replacement = "1" * 40 if field == "sha" else "v99.0.0"
    changed = original.replace(previous, replacement)
    assert changed != original
    path.write_text(changed)
    before = {item: item.read_bytes() for item in (root / ".github").rglob("*") if item.is_file()}

    result = _check(root)

    assert result.returncode != 0
    assert "inconsistent astral-sh/setup-uv@" in result.stderr
    for name in ("ci.yml", "zizmor.yml"):
        source = root / ".github/workflows" / name
        number = next(number for number, text in enumerate(source.read_text().splitlines(), 1) if "uses: astral-sh/setup-uv@" in text)
        assert f"{source}:{number}:" in result.stderr
    assert "passed" not in result.stdout
    assert before == {item: item.read_bytes() for item in before}


def test_pin_gate_reaches_ci_and_matches_dependabot_scope() -> None:
    just = shutil.which("just")
    assert just is not None
    graph = json.loads(
        subprocess.run(  # noqa: S603 - inspect real recipe dependencies without running the full validation gate.
            [just, "--dump", "--dump-format", "json"], cwd=REPOSITORY, capture_output=True, text=True, check=True, timeout=30
        ).stdout
    )
    for parent, child in (("ci", "check"), ("check", "_check-policy"), ("_check-policy", "github-actions-check"), ("github-actions-check", "actions-check")):
        assert any(dependency["recipe"] == child for dependency in graph["recipes"][parent]["dependencies"])
    scope = subprocess.run(  # noqa: S603
        [just, "--evaluate", "actions_inputs"], cwd=REPOSITORY, capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()
    assert scope == "'.github/workflows'"
    assert not list((REPOSITORY / ".github/actions").rglob("action.y*ml"))
    policy = tomllib.loads((REPOSITORY / ".github/action-updates.toml").read_text())
    assert policy["actions"] == {}
    assert "astral-sh/setup-uv" in policy["consistency"]["actions"]
    dependabot = yaml.safe_load((REPOSITORY / ".github/dependabot.yml").read_text())
    updates = [update for update in dependabot["updates"] if update["package-ecosystem"] == "github-actions"]
    assert len(updates) == 1
    assert updates[0]["directory"] == "/"
    assert "ignore" not in updates[0]
    ci = yaml.safe_load((REPOSITORY / ".github/workflows/ci.yml").read_text())
    assert any(step.get("run") == "just ci" for step in ci["jobs"]["verify"]["steps"])
