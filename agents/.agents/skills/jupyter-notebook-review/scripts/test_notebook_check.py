"""Tests for retained skill inspection and advisory policy, tracked in #78."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("notebook_check.py")
SPEC = importlib.util.spec_from_file_location("notebook_check", SCRIPT)
if SPEC is None or SPEC.loader is None:
    message = "notebook_check.py could not be loaded"
    raise RuntimeError(message)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_notebook(path: Path, *, source: str = "value = 1\n", cell_id: str | None = "define-value") -> bytes:
    """Supply a notebook awaiting review without a notebook runtime dependency."""
    cell = {"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None}
    if cell_id is not None:
        cell["id"] = cell_id
    payload = json.dumps({"cells": [cell], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}).encode()
    path.write_bytes(payload)
    return payload


def test_summary_inspects_missing_ids_without_repairing_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    notebook = tmp_path / "awaiting-repair.ipynb"
    original = write_notebook(notebook, cell_id=None)

    assert MODULE.main(["--summary", str(notebook)]) == 0

    output = capsys.readouterr()
    assert "cell 001 code" in output.out
    assert "id=<missing>" in output.out
    assert "value = 1" in output.out
    assert not output.err
    assert notebook.read_bytes() == original


@pytest.mark.parametrize("cell_id", ["cell-1", "abcdef12", "ABCDEF12", "123e4567-e89b-42d3-a456-426614174000"])
def test_descriptive_id_advice_is_optional_or_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str], cell_id: str) -> None:
    notebook = tmp_path / "generated-id.ipynb"
    original = write_notebook(notebook, cell_id=cell_id)

    assert MODULE.main(["--advice", str(notebook)]) == 0
    assert MODULE.main(["--advice", "--strict", str(notebook)]) == 1

    assert "looks generated or positional" in capsys.readouterr().out
    assert notebook.read_bytes() == original


def test_advice_keeps_dataframe_and_subprocess_policy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    notebook = tmp_path / "policy.ipynb"
    write_notebook(notebook, source='import pandas\nimport subprocess\nsubprocess.run(["program"])\n')

    assert MODULE.main(["--advice", str(notebook)]) == 0

    output = capsys.readouterr().out
    assert "prefer Polars" in output
    assert "subprocess.run lacks timeout" in output


def test_advice_reports_shell_execution_as_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    notebook = tmp_path / "shell.ipynb"
    write_notebook(notebook, source='import subprocess\nsubprocess.run("program", shell=True, timeout=10)\n')

    assert MODULE.main(["--advice", str(notebook)]) == 1
    assert "cell 1: error: subprocess.run uses shell=True" in capsys.readouterr().err


def test_plain_python_advice_defers_magic_syntax_to_shared_lint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    notebook = tmp_path / "magic.ipynb"
    original = write_notebook(notebook, source="%time value = 1\n")

    assert MODULE.main(["--advice", "--strict", str(notebook)]) == 0

    assert "plain-Python advice skipped" in capsys.readouterr().out
    assert notebook.read_bytes() == original


def test_advice_never_executes_source(tmp_path: Path) -> None:
    notebook = tmp_path / "read-only.ipynb"
    marker = tmp_path / "should-not-exist"
    original = write_notebook(notebook, source=f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")

    assert MODULE.main(["--advice", "--strict", str(notebook)]) == 0

    assert not marker.exists()
    assert notebook.read_bytes() == original


@pytest.mark.parametrize("payload", ["[]", '{"metadata":{},"nbformat":4,"cells":[null]}'])
def test_inspection_rejects_unreadable_cell_containers(tmp_path: Path, capsys: pytest.CaptureFixture[str], payload: str) -> None:
    notebook = tmp_path / "malformed.ipynb"
    notebook.write_text(payload, encoding="utf-8")

    assert MODULE.main(["--summary", str(notebook)]) == 2

    output = capsys.readouterr()
    assert "notebook_check:" in output.err
    assert "Traceback" not in output.err
    assert not output.out


def test_old_execution_mode_cannot_silently_become_advice(tmp_path: Path) -> None:
    notebook = tmp_path / "example.ipynb"
    write_notebook(notebook)

    with pytest.raises(SystemExit) as error:
        MODULE.main(["--execute", str(notebook)])
    assert error.value.code == 2
