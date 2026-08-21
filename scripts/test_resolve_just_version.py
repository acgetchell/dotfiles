"""Tests for the pre-just version resolver."""

import subprocess
from pathlib import Path
from shutil import which

import pytest

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
    [('just_version := "1.58.0"', "1.58.0"), ("  just_version  :=  '2.3.4'  # bootstrap pin", "2.3.4"), ("just_version := 5.6.7", "5.6.7")],
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
