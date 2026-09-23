"""Exercise the Jupyter skill's consumer policy through the published CLI."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

POLICY = Path(__file__).resolve().parents[1] / "agents/.agents/skills/jupyter-notebook-review/assets/pyproject.toml"


def code(source: str, cell_id: str = "calculate-value") -> dict[str, Any]:
    """Supply a code cell for a skill workflow fixture."""
    return {"cell_type": "code", "id": cell_id, "metadata": {}, "source": source, "outputs": [], "execution_count": None}


def consumer(root: Path, cells: list[dict[str, Any]], *, minor: int = 5) -> tuple[Path, bytes]:
    """Install the real skill policy into an independent consumer directory."""
    shutil.copy2(POLICY, root / "pyproject.toml")
    notebook = root / "review.ipynb"
    payload = json.dumps({"nbformat": 4, "nbformat_minor": minor, "metadata": {"language_info": {"name": "python"}}, "cells": cells}).encode()
    notebook.write_bytes(payload)
    return notebook, payload


def run_shared(root: Path, action: str, *options: str) -> subprocess.CompletedProcess[str]:
    """Use only the installed public command with explicit consumer selection."""
    executable = shutil.which("research-repo-tools")
    assert executable is not None
    return subprocess.run(  # noqa: S603
        [executable, "--root", str(root), "notebooks", action, "review.ipynb", *options], cwd=root, capture_output=True, text=True, check=False, timeout=30
    )


def test_skill_inspection_supports_repair_without_changing_identity(tmp_path: Path) -> None:
    missing = code("private_source = 1\n")
    del missing["id"]
    cells = [missing, code("value = 2\n", "keep-this-id"), code("value = 3\n", "keep-this-id"), code("value = 4\n", "invalid id")]
    cells[1]["outputs"] = [{"output_type": "stream", "name": "stdout", "text": "private_output"}]
    cells[1]["execution_count"] = 7
    notebook, original = consumer(tmp_path, cells, minor=4)

    inventory = run_shared(tmp_path, "inspect", "--json", "--no-preview")
    assert inventory.returncode == 0, inventory.stderr
    report = json.loads(inventory.stdout)
    assert report["schema"] == 1
    entries = report["notebooks"][0]["cells"]
    assert [cell["number"] for cell in entries] == [1, 2, 3, 4]
    assert [cell["id"] for cell in entries] == [None, "keep-this-id", "keep-this-id", "invalid id"]
    assert [cell["id_status"] for cell in entries] == ["missing", "existing", "duplicate", "invalid"]
    assert entries[1]["output_count"] == 1
    assert entries[1]["execution_count"] == 7
    assert entries[0]["problems"]
    assert entries[2]["problems"]
    assert entries[3]["problems"]
    assert all("preview" not in cell for cell in entries)
    assert "private_source" not in inventory.stdout
    assert "private_output" not in inventory.stdout
    compact = run_shared(tmp_path, "inspect")
    assert compact.returncode == 0, compact.stderr
    assert "keep-this-id" in compact.stdout
    assert "private_source = 1" in compact.stdout
    assert "private_output" not in compact.stdout
    assert len(compact.stdout.splitlines()) < 20
    assert run_shared(tmp_path, "check").returncode == 1
    assert notebook.read_bytes() == original


def test_skill_policy_reports_warnings_with_optional_strict_failure(tmp_path: Path) -> None:
    notebook, original = consumer(
        tmp_path,
        [
            {"cell_type": "markdown", "id": "abcdef12", "metadata": {}, "source": "# Review"},
            code(
                "import pandas\nimport csv\nimport subprocess\n"
                "def calculate(value, *args, **kwargs):\n"
                "    try:\n        return value + 1\n    except Exception:\n        return 0\n"
                "subprocess.run(['program'])\n",
                "cell-2",
            ),
        ],
    )
    warning = run_shared(tmp_path, "advise")
    assert warning.returncode == 0, warning.stderr
    for message in (
        "WARNING",
        "descriptive-id",
        "cell 1 (abcdef12)",
        "cell 2 (cell-2)",
        "ANN001",
        "ANN002",
        "ANN003",
        "ANN201",
        "BLE001",
        "TID251",
        "Prefer Polars",
        "subprocess-timeout",
    ):
        assert message in warning.stderr
    assert "ERROR" not in warning.stderr
    assert run_shared(tmp_path, "advise", "--strict").returncode == 1
    assert notebook.read_bytes() == original


def test_skill_policy_accepts_native_syntax_without_execution(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    notebook, original = consumer(
        tmp_path,
        [
            code("%time value = 1", "time-value"),
            code("%%bash\nprintf 'example'\n", "shell-example"),
            code('from pathlib import Path\n\nPath("must-not-exist").touch()', "write-marker"),
        ],
    )
    advice = run_shared(tmp_path, "advise", "--strict")
    assert advice.returncode == 0, advice.stderr
    assert "INFO" in advice.stderr
    assert "plain-AST timeout advice skipped" in advice.stderr
    assert "WARNING" not in advice.stderr
    lint = run_shared(tmp_path, "lint")
    assert lint.returncode == 0, lint.stderr
    assert not marker.exists()
    assert notebook.read_bytes() == original


def test_skill_native_lint_keeps_shell_execution_a_hard_failure(tmp_path: Path) -> None:
    notebook, original = consumer(tmp_path, [code('import subprocess\n\nsubprocess.run("program", shell=True, timeout=10)', "run-program")])
    lint = run_shared(tmp_path, "lint")
    assert lint.returncode == 1, lint.stderr
    assert "S602" in lint.stderr
    assert "cell 1 (run-program)" in lint.stderr
    assert notebook.read_bytes() == original
