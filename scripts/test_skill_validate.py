#!/usr/bin/env python3
"""Tests for skill_validate.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

import skill_validate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def write_skill(skill_dir: Path, frontmatter: str, *, include_openai_metadata: bool = True) -> None:
    """Write a minimal skill file."""
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n# Skill\n", encoding="utf-8")
    if include_openai_metadata:
        agents_dir = skill_dir / "agents"
        agents_dir.mkdir()
        (agents_dir / "openai.yaml").write_text(
            "interface:\n"
            '  display_name: "Example Skill"\n'
            '  short_description: "Validate an example skill"\n'
            f'  default_prompt: "Use ${skill_dir.name} to validate this example."\n',
            encoding="utf-8",
        )


def test_validate_skill_accepts_minimal_frontmatter(tmp_path: Path) -> None:
    """A skill with name and description is valid."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert valid
    assert message == "Skill is valid!"


def test_validate_skill_rejects_missing_skill_file(tmp_path: Path) -> None:
    """A skill directory must contain SKILL.md."""
    valid, message = skill_validate.validate_skill(tmp_path / "missing-skill")

    assert not valid
    assert message == "SKILL.md not found"


def test_validate_skill_rejects_missing_openai_metadata(tmp_path: Path) -> None:
    """A standalone skill must include user-facing metadata."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."', include_openai_metadata=False)

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "agents/openai.yaml not found"


def test_validate_skill_rejects_short_ui_description(tmp_path: Path) -> None:
    """UI descriptions must remain useful when shown in skill lists."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')
    (skill_dir / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Example Skill"\n  short_description: "Too short"\n  default_prompt: "Use $example-skill to validate this example."\n',
        encoding="utf-8",
    )

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "interface.short_description must be 25-64 characters"


def test_validate_skill_rejects_prompt_without_invocation(tmp_path: Path) -> None:
    """Default prompts must explicitly invoke their owning skill."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')
    (skill_dir / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Example Skill"\n  short_description: "Validate an example skill"\n  default_prompt: "Validate this example."\n',
        encoding="utf-8",
    )

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "interface.default_prompt must mention $example-skill"


def test_validate_skill_rejects_unexpected_frontmatter_key(tmp_path: Path) -> None:
    """Only supported skill frontmatter keys are accepted."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: bad-skill\ndescription: "Use for tests."\nextra: nope')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert "Unexpected key" in message


def test_validate_skill_rejects_non_string_frontmatter_key(tmp_path: Path) -> None:
    """Frontmatter keys must be strings for deterministic diagnostics."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: bad-skill\ndescription: "Use for tests."\n1: nope')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Frontmatter keys must be strings: 1"


def test_validate_skill_rejects_invalid_name(tmp_path: Path) -> None:
    """Skill names must use hyphen-case."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: Bad_Skill\ndescription: "Use for tests."')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert "hyphen-case" in message


def test_validate_skill_rejects_empty_name(tmp_path: Path) -> None:
    """Required name values must be present and non-empty."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: ""\ndescription: "Use for tests."')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Name cannot be empty"


def test_validate_skill_rejects_angle_brackets_in_description(tmp_path: Path) -> None:
    """Skill descriptions cannot contain angle brackets."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: bad-skill\ndescription: "Use for <tests>."')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert "angle brackets" in message


def test_validate_skill_rejects_empty_description(tmp_path: Path) -> None:
    """Required description values must be present and non-empty."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: bad-skill\ndescription: ""')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Description cannot be empty"


def test_main_reports_invalid_skill_on_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Invalid skill diagnostics are written to stderr."""
    skill_dir = tmp_path / "bad-skill"
    write_skill(skill_dir, 'name: bad-skill\ndescription: "Use for <tests>."')

    code = skill_validate.main([str(skill_dir)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "angle brackets" in captured.err


def test_main_reports_decode_errors_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Unreadable text files fail with concise stderr diagnostics."""
    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_bytes(b"\xff")

    code = skill_validate.main([str(skill_dir)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "failed to validate skill" in captured.err


def test_main_prints_validation_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI prints the validator message and exits zero for valid skills."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')

    code = skill_validate.main([str(skill_dir)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "Skill is valid!\n"
