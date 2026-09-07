#!/usr/bin/env python3
"""Tests for skill_validate.py."""

from typing import TYPE_CHECKING

import pytest

import skill_validate

if TYPE_CHECKING:
    from pathlib import Path


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


def test_validate_skill_rejects_malformed_closing_delimiter(tmp_path: Path) -> None:
    """The frontmatter closing delimiter must occupy its complete line."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')
    (skill_dir / "SKILL.md").write_text('---\nname: example-skill\ndescription: "Use for tests."\n---garbage\n', encoding="utf-8")

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Invalid frontmatter format"


def test_validate_skill_rejects_duplicate_frontmatter_key(tmp_path: Path) -> None:
    """Repeated YAML keys must not be resolved with last-key-wins semantics."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: ignored\nname: example-skill\ndescription: "Use for tests."')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Duplicate key in frontmatter: name"


def test_validate_skill_rejects_equivalent_nested_frontmatter_keys(tmp_path: Path) -> None:
    """Constructed YAML keys that compare equally must be rejected at any depth."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."\nmetadata:\n  nested:\n    yes: first\n    true: second')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Duplicate key in frontmatter: true"


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ("{<<: {owner: inherited}, revision: 1}", {"owner": "inherited", "revision": 1}),
        ("{owner: explicit, <<: {owner: inherited}}", {"owner": "explicit"}),
        ("{<<: [{owner: first}, {owner: second, revision: 1}]}", {"owner": "first", "revision": 1}),
        ('{<<: {owner: inherited}, "<<": literal}', {"owner": "inherited", "<<": "literal"}),
        ("{=: literal}", {"=": "literal"}),
    ],
)
def test_parse_frontmatter_preserves_mapping_key_semantics(metadata: str, expected: dict[str, object]) -> None:
    """Merges, explicit overrides, and mapping-context tags retain YAML semantics."""
    frontmatter, message = skill_validate.parse_frontmatter(f"name: example-skill\ndescription: Use for tests.\nmetadata: {metadata}")

    assert message == ""
    assert frontmatter is not None
    assert frontmatter["metadata"] == expected


@pytest.mark.parametrize(
    ("metadata", "duplicate"),
    [
        ("{<<: {owner: first, owner: second}}", "owner"),
        ("{<<: [{owner: first}, {revision: 1, revision: 2}]}", "revision"),
        ("{<<: {owner: inherited}, owner: first, owner: second}", "owner"),
        ("{<<: {owner: first}, <<: {revision: 1}}", "<<"),
        ('{=: first, "=": second}', "="),
        ("[{owner: first, owner: second}]", "owner"),
        ("!!pairs [{? {owner: first, owner: second}: value}]", "owner"),
        ("!!omap [{? {owner: first, owner: second}: value}]", "owner"),
    ],
)
def test_parse_frontmatter_rejects_explicit_duplicates(metadata: str, duplicate: str) -> None:
    """Merge handling must not hide explicit duplicates in source mappings."""
    frontmatter, message = skill_validate.parse_frontmatter(f"name: example-skill\ndescription: Use for tests.\nmetadata: {metadata}")

    assert frontmatter is None
    assert message == f"Duplicate key in frontmatter: {duplicate}"


def test_parse_frontmatter_accepts_recursive_aliases() -> None:
    """The duplicate scan terminates while preserving recursive YAML values."""
    frontmatter, message = skill_validate.parse_frontmatter("name: example-skill\ndescription: Use for tests.\nmetadata: &metadata {self: *metadata}")

    assert message == ""
    assert frontmatter is not None
    metadata = frontmatter["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["self"] is metadata


@pytest.mark.parametrize("key", ["!!map invalid", "!!seq invalid", "!!set invalid", "[unhashable]"])
def test_parse_frontmatter_rejects_malformed_keys(key: str) -> None:
    """Invalid constructed keys return a validation error rather than an exception."""
    frontmatter, message = skill_validate.parse_frontmatter(f"name: example-skill\ndescription: Use for tests.\nmetadata: {{{key}: value}}")

    assert frontmatter is None
    assert message.startswith("Invalid YAML in frontmatter:")


def test_main_accepts_merged_frontmatter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Valid merged metadata retains successful CLI output and exit status."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, "name: example-skill\ndescription: Use for tests.\nmetadata: {<<: {owner: inherited}, owner: explicit}")

    code = skill_validate.main([str(skill_dir)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == "Skill is valid!\n"
    assert captured.err == ""


def test_main_reports_malformed_tagged_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Malformed tagged keys produce a concise CLI failure without a traceback."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, "name: example-skill\ndescription: Use for tests.\nmetadata: {!!map invalid: value}")

    code = skill_validate.main([str(skill_dir)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err.startswith("Invalid YAML in frontmatter:")
    assert "Traceback" not in captured.err


def test_validate_skill_rejects_missing_openai_metadata(tmp_path: Path) -> None:
    """A standalone skill must include user-facing metadata."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."', include_openai_metadata=False)

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "agents/openai.yaml not found"


def test_validate_skill_rejects_name_that_differs_from_directory(tmp_path: Path) -> None:
    """A skill name must match its portable directory identifier."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: different-skill\ndescription: "Use for tests."')

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Frontmatter name 'different-skill' must match skill directory 'example-skill'"


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


def test_validate_skill_rejects_prompt_with_partial_invocation(tmp_path: Path) -> None:
    """A longer skill name must not satisfy the invocation requirement."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')
    (skill_dir / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Example Skill"\n  short_description: "Validate an example skill"\n'
        '  default_prompt: "Use $example-skill-extra to validate this example."\n',
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
