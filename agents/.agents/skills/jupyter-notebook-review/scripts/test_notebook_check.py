#!/usr/bin/env python3
"""Tests for the Jupyter notebook review skill helper."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

SCRIPT = Path(__file__).with_name("notebook_check.py")
SPEC = importlib.util.spec_from_file_location("notebook_check", SCRIPT)
if SPEC is None or SPEC.loader is None:
    message = "notebook_check.py could not be loaded"
    raise RuntimeError(message)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def notebook_with_ids(*cell_ids: Any) -> dict[str, Any]:
    """Return a minimal notebook-shaped mapping with the requested cell IDs."""
    cells = []
    for cell_id in cell_ids:
        cell = {"cell_type": "markdown", "metadata": {}, "source": []}
        if cell_id is not None:
            cell["id"] = cell_id
        cells.append(cell)
    return {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def test_cell_id_diagnostics_accepts_unique_nbformat_ids() -> None:
    """Valid descriptive IDs should pass without diagnostics."""
    assert MODULE.cell_id_diagnostics(notebook_with_ids("setup-code", "Render_Plot", "load_data")) == []


def test_cell_id_diagnostics_rejects_missing_malformed_and_duplicate_ids() -> None:
    """Presence, nbformat shape, and uniqueness are hard requirements."""
    diagnostics = MODULE.cell_id_diagnostics(notebook_with_ids(None, "bad id", "load-data", "load-data"))

    assert [(item.severity, item.cell) for item in diagnostics] == [("error", 1), ("error", 2), ("error", 4)]


def test_cell_id_diagnostics_warns_on_generated_and_positional_ids() -> None:
    """Generated and positional IDs should prompt descriptive replacements."""
    diagnostics = MODULE.cell_id_diagnostics(notebook_with_ids("abcdef12", "123e4567-e89b-42d3-a456-426614174000", "cell-3", "load-data"))

    assert [(item.severity, item.cell) for item in diagnostics] == [("warning", 1), ("warning", 2), ("warning", 3)]


def test_lint_enforces_cell_id_diagnostics(tmp_path: Path) -> None:
    """Cell ID errors should fail lint, while warnings fail only in strict mode."""
    notebook_path = tmp_path / "example.ipynb"
    options = MODULE.LintOptions(run_ruff=False, run_format=False, run_ty=False)

    notebook_path.write_text(json.dumps(notebook_with_ids(None)), encoding="utf-8")
    assert MODULE.lint(notebook_path, options) == 1

    notebook_path.write_text(json.dumps(notebook_with_ids("cell-1")), encoding="utf-8")
    assert MODULE.lint(notebook_path, options) == 0
    assert MODULE.lint(notebook_path, MODULE.LintOptions(strict=True, run_ruff=False, run_format=False, run_ty=False)) == 1


def test_summary_displays_cell_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Summary output should expose stable IDs for notebook review."""
    notebook_path = tmp_path / "example.ipynb"
    notebook_path.write_text(json.dumps(notebook_with_ids("setup-code")), encoding="utf-8")

    MODULE.summarize(notebook_path)

    assert "id=setup-code" in capsys.readouterr().out
