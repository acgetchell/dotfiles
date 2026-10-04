"""Exercise Just's real dependency ordering and coalescing on harmless gates."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).with_name("fixtures")


@pytest.mark.parametrize(
    ("fixture", "recipe", "fail_lint", "expected"),
    [
        ("late-static.just", "ci", True, ["python-tests", "notebook-export", "notebook-lint"]),
        ("early-static.just", "ci", True, ["notebook-export", "notebook-lint"]),
        ("early-static.just", "ci", False, ["notebook-export", "notebook-lint", "python-tests", "notebook-execute"]),
        ("early-static.just", "notebook-check", True, ["notebook-export", "notebook-lint"]),
        ("early-static.just", "notebook-check", False, ["notebook-export", "notebook-lint", "notebook-execute"]),
    ],
)
def test_canonical_gate_order(fixture: str, recipe: str, fail_lint: bool, expected: list[str], tmp_path: Path) -> None:
    just = shutil.which("just")
    assert just is not None, "The repository's pinned Just is required for command-graph fixtures"
    result = subprocess.run(  # noqa: S603
        [just, "--justfile", str(FIXTURES / fixture), "--working-directory", str(tmp_path), recipe],
        env={**os.environ, "FAIL_LINT": "1" if fail_lint else "0"},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.stdout.splitlines() == expected
    assert (result.returncode != 0) == fail_lint
