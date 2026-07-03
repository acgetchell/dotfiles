#!/usr/bin/env python3
"""Tests for semgrep_fixture_config.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import semgrep_fixture_config as fixture_config

if TYPE_CHECKING:
    from pathlib import Path


def write_source_config(path: Path) -> None:
    """Write a small repository-style Semgrep config."""
    path.write_text(
        """rules:
  - id: dotfiles.one
    languages:
      - regex
    severity: WARNING
    message: one
    pattern-regex: one
  - id: dotfiles.two
    languages:
      - regex
    severity: WARNING
    message: two
    pattern-regex: two
""",
        encoding="utf-8",
    )


def test_build_fixture_config_keeps_unique_annotated_rules(tmp_path: Path) -> None:
    """Duplicate fixture annotations are emitted once and in fixture order."""
    fixture = tmp_path / "fixture.sh"
    source_config = tmp_path / "semgrep.yaml"
    fixture.write_text("# ruleid: dotfiles.one\n# ok: dotfiles.one, dotfiles.two\n", encoding="utf-8")
    write_source_config(source_config)

    generated = fixture_config.build_fixture_config(fixture, source_config)

    assert generated.count("id: dotfiles.one") == 1
    assert generated.count("id: dotfiles.two") == 1
    assert generated.index("id: dotfiles.one") < generated.index("id: dotfiles.two")


def test_build_fixture_config_rejects_missing_rule_ids(tmp_path: Path) -> None:
    """Fixtures cannot reference rules absent from the source config."""
    fixture = tmp_path / "fixture.sh"
    source_config = tmp_path / "semgrep.yaml"
    fixture.write_text("# ruleid: dotfiles.missing\n", encoding="utf-8")
    write_source_config(source_config)

    with pytest.raises(ValueError, match="missing Semgrep rules"):
        fixture_config.build_fixture_config(fixture, source_config)


def test_build_fixture_config_rejects_missing_annotations(tmp_path: Path) -> None:
    """Fixtures must declare at least one repository-owned Semgrep rule."""
    fixture = tmp_path / "fixture.sh"
    source_config = tmp_path / "semgrep.yaml"
    fixture.write_text("# no annotations here\n", encoding="utf-8")
    write_source_config(source_config)

    with pytest.raises(ValueError, match="fixture has no dotfiles Semgrep annotations"):
        fixture_config.build_fixture_config(fixture, source_config)


def test_main_reports_missing_fixture_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI file errors are concise stderr messages."""
    fixture = tmp_path / "missing.sh"
    source_config = tmp_path / "semgrep.yaml"
    output_config = tmp_path / "fixture.yaml"
    write_source_config(source_config)

    code = fixture_config.main([str(fixture), str(source_config), str(output_config)])

    captured = capsys.readouterr()
    assert code == 1
    assert "failed to build fixture config" in captured.err
    assert str(fixture) in captured.err
    assert not output_config.exists()


def test_main_writes_fixture_config(tmp_path: Path) -> None:
    """CLI writes the selected rule config to the requested path."""
    fixture = tmp_path / "fixture.sh"
    source_config = tmp_path / "semgrep.yaml"
    output_config = tmp_path / "fixture.yaml"
    fixture.write_text("# ruleid: dotfiles.two\n", encoding="utf-8")
    write_source_config(source_config)

    code = fixture_config.main([str(fixture), str(source_config), str(output_config)])

    assert code == 0
    assert output_config.read_text(encoding="utf-8").count("id: dotfiles.two") == 1
