"""Test bootstrap and workflow consumers of repository tool-version pins."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from shutil import which

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = REPOSITORY_ROOT / "bin" / "resolve-just-version.sh"
BASH = "/bin/bash"
JUST = which("just")


def resolve(path: Path) -> subprocess.CompletedProcess[str]:
    """Run the resolver against one candidate justfile."""
    return subprocess.run([BASH, str(RESOLVER), str(path)], check=False, capture_output=True, text=True)  # noqa: S603


def test_repository_pin_matches_just_evaluation() -> None:
    assert JUST is not None
    expected = subprocess.run(  # noqa: S603
        [JUST, "--justfile", str(REPOSITORY_ROOT / "justfile"), "--evaluate", "just_version"], check=True, capture_output=True, text=True
    ).stdout.strip()

    result = resolve(REPOSITORY_ROOT / "justfile")

    assert result.returncode == 0
    assert result.stdout.strip() == expected


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        ('just_version := "1.58.0"', "1.58.0"),
        ("  just_version  :=  '2.3.4'  # bootstrap pin", "2.3.4"),
        ("just_version := 5.6.7", "5.6.7"),
        ('just_version := "2.0.0-rc.1+build.2"', "2.0.0-rc.1+build.2"),
    ],
)
def test_supported_declaration_forms(tmp_path: Path, declaration: str, expected: str) -> None:
    candidate = tmp_path / "justfile"
    candidate.write_text(f'other := "ignored"\n{declaration}\n', encoding="utf-8")

    result = resolve(candidate)

    assert result.returncode == 0
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("declaration", ["", 'just_version := ""', 'just_version := "latest"'])
def test_missing_or_invalid_pin_fails(tmp_path: Path, declaration: str) -> None:
    candidate = tmp_path / "justfile"
    candidate.write_text(f"{declaration}\n", encoding="utf-8")

    result = resolve(candidate)

    assert result.returncode == 1
    assert "Invalid or missing just_version" in result.stderr


@pytest.mark.parametrize("cargo_version", ["1.2.3", "2.0.0-rc.1+build.2", "latest"])
def test_ci_resolver_preserves_supported_cargo_versions(tmp_path: Path, cargo_version: str) -> None:
    """Run the actual workflow step against candidate Just pins, without installs."""
    source = (REPOSITORY_ROOT / "justfile").read_text()
    for tool in ("dprint", "rumdl"):
        source = re.sub(rf'^{tool}_version := "[^"]+"', f'{tool}_version := "{cargo_version}"', source, flags=re.MULTILINE)
    (tmp_path / "justfile").write_text(source)
    shutil.copy2(REPOSITORY_ROOT / "pyproject.toml", tmp_path)
    workflow = yaml.safe_load((REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text())
    step = next(item for item in workflow["jobs"]["verify"]["steps"] if item.get("id") == "tool_versions")
    outputs = tmp_path / "outputs"

    result = subprocess.run(  # noqa: S603 - actual workflow code with temporary pins and output file.
        [BASH, "-c", step["run"]], cwd=tmp_path, env={**os.environ, "GITHUB_OUTPUT": str(outputs)}, capture_output=True, text=True, check=False
    )

    if cargo_version == "latest":
        assert result.returncode != 0
        assert "Invalid dprint_version" in result.stderr
        assert not outputs.exists()
    else:
        assert result.returncode == 0, result.stderr
        values = dict(line.split("=", 1) for line in outputs.read_text().splitlines())
        assert values["dprint_version"] == cargo_version
        assert values["rumdl_version"] == cargo_version
