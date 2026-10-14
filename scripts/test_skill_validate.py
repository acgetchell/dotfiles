#!/usr/bin/env python3
"""Tests for skill_validate.py."""

import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
import yaml

import skill_validate

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True, params=list(dict.fromkeys([yaml.SafeLoader, getattr(yaml, "CSafeLoader", yaml.SafeLoader)])))
def safe_loader(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replay validation contracts against every available safe implementation."""
    monkeypatch.setattr(skill_validate, "SAFE_YAML_LOADER", request.param)


def test_import_falls_back_without_libyaml() -> None:
    """An installation without the optional extension still imports and validates."""
    program = (
        "import sys, yaml\n"
        "if hasattr(yaml, 'CSafeLoader'): del yaml.CSafeLoader\n"
        "import skill_validate\n"
        "assert skill_validate.SAFE_YAML_LOADER is yaml.SafeLoader\n"
        "assert skill_validate.parse_frontmatter('name: example\\ndescription: Example.')[0] == {'name': 'example', 'description': 'Example.'}\n"
        "assert 'research_repo_tools.selection' not in sys.modules\n"
    )
    result = subprocess.run(  # noqa: S603 - isolated import probe, no source changes.
        [sys.executable, "-c", program], cwd=skill_validate.Path(__file__).parent, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("filename", ["SKILL.md", "agents/openai.yaml"])
def test_unsafe_yaml_tags_are_rejected(tmp_path: Path, filename: str) -> None:
    """Both input paths reject Python object construction with either loader."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, "name: example-skill\ndescription: Example.")
    content = "!!python/object:builtins.object {}"
    if filename == "SKILL.md":
        content = f"---\n{content}\n---\n"
    (skill_dir / filename).write_text(content, encoding="utf-8")
    valid, message = skill_validate.validate_skill(skill_dir)
    assert not valid
    assert message.startswith("Invalid YAML")


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


@pytest.mark.parametrize("case", ["valid", "malformed", "missing-metadata", "removed", "invalid-encoding"])
def test_batch_matches_single_and_reports_every_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str) -> None:
    """Batch validation retains single-skill semantics and continues after errors."""
    skills = [tmp_path / name for name in ("first-skill", "second-skill")]
    singles = []
    for skill in skills:
        write_skill(skill, f"name: {skill.name}\ndescription: Use for tests.", include_openai_metadata=case != "missing-metadata")
        if case == "malformed":
            (skill / "SKILL.md").write_text("---\nname: [\n---\n", encoding="utf-8")
        elif case == "removed":
            (skill / "SKILL.md").unlink()
        elif case == "invalid-encoding":
            (skill / "SKILL.md").write_bytes(b"\xff")
        singles.append((skill_validate.main([str(skill)]), capsys.readouterr()))

    assert skill_validate.main([str(skill) for skill in skills]) == max(code for code, _output in singles)
    batch = capsys.readouterr()
    for skill, (_code, output) in zip(skills, singles, strict=True):
        assert f"{skill}: {output.out or output.err}" in (batch.out or batch.err)


def test_repository_batch_preserves_inventory_and_git_state(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Deleted/ignored/nested entrypoints are omitted, while every selected error is reported."""
    git = shutil.which("git")
    assert git is not None

    def run_git(*args: str) -> bytes:
        return subprocess.run([git, "-C", str(tmp_path), *args], check=True, capture_output=True).stdout  # noqa: S603 - isolated fixture Git.

    run_git("init", "-q")
    root = tmp_path / "agents/.agents/skills"
    root.mkdir(parents=True)
    for name in ("tracked", "removed"):
        write_skill(root / name, f"name: {name}\ndescription: Fixture.")
    run_git("add", ".")
    (root / "removed/SKILL.md").unlink()
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    for name in ("untracked", "ignored", "malformed", "missing-metadata"):
        write_skill(root / name, f"name: {name}\ndescription: Fixture.", include_openai_metadata=name != "missing-metadata")
    (root / "malformed/SKILL.md").write_text("No frontmatter", encoding="utf-8")
    write_skill(root / "tracked/nested", "name: nested\ndescription: Fixture.")
    before = (run_git("status", "--porcelain=v1", "-z"), run_git("ls-files", "--stage", "-z"))
    assert skill_validate.main(["--repository", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert output.out.count("Skill is valid!") == 2
    assert f"{root / 'malformed'}: No YAML frontmatter found" in output.err
    assert f"{root / 'missing-metadata'}: agents/openai.yaml not found" in output.err
    assert all(name not in output.out + output.err for name in ("removed", "ignored", "nested"))
    assert before == (run_git("status", "--porcelain=v1", "-z"), run_git("ls-files", "--stage", "-z"))


def test_repository_inventory_failure_is_not_empty_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A directory outside Git cannot silently pass as an empty skill inventory."""
    assert skill_validate.main(["--repository", str(tmp_path)]) == 1
    output = capsys.readouterr()
    assert output.err.startswith("failed to inventory skills:")
    assert not output.out


def test_validate_skill_rejects_malformed_closing_delimiter(tmp_path: Path) -> None:
    """The frontmatter closing delimiter must occupy its complete line."""
    skill_dir = tmp_path / "example-skill"
    write_skill(skill_dir, 'name: example-skill\ndescription: "Use for tests."')
    (skill_dir / "SKILL.md").write_text('---\nname: example-skill\ndescription: "Use for tests."\n---garbage\n', encoding="utf-8")

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    assert message == "Invalid frontmatter format"


@pytest.mark.parametrize(
    ("directory_name", "frontmatter", "expected_message", "exact_message"),
    [
        pytest.param(
            "example-skill",
            'name: ignored\nname: example-skill\ndescription: "Use for tests."',
            "Duplicate key in frontmatter: name",
            True,
            id="duplicate_frontmatter_key",
        ),
        pytest.param(
            "example-skill",
            'name: example-skill\ndescription: "Use for tests."\nmetadata:\n  nested:\n    yes: first\n    true: second',
            "Duplicate key in frontmatter: true",
            True,
            id="equivalent_nested_frontmatter_keys",
        ),
        pytest.param(
            "example-skill",
            'name: different-skill\ndescription: "Use for tests."',
            "Frontmatter name 'different-skill' must match skill directory 'example-skill'",
            True,
            id="name_that_differs_from_directory",
        ),
        pytest.param("bad-skill", 'name: bad-skill\ndescription: "Use for tests."\nextra: nope', "Unexpected key", False, id="unexpected_frontmatter_key"),
        pytest.param(
            "bad-skill", 'name: bad-skill\ndescription: "Use for tests."\n1: nope', "Frontmatter keys must be strings: 1", True, id="non_string_frontmatter_key"
        ),
        pytest.param("bad-skill", 'name: Bad_Skill\ndescription: "Use for tests."', "hyphen-case", False, id="invalid_name"),
        pytest.param("bad-skill", 'name: ""\ndescription: "Use for tests."', "Name cannot be empty", True, id="empty_name"),
        pytest.param("bad-skill", 'name: bad-skill\ndescription: "Use for <tests>."', "angle brackets", False, id="angle_brackets_in_description"),
        pytest.param("bad-skill", 'name: bad-skill\ndescription: ""', "Description cannot be empty", True, id="empty_description"),
    ],
)
def test_validate_skill_rejects_invalid_frontmatter(tmp_path: Path, directory_name: str, frontmatter: str, expected_message: str, exact_message: bool) -> None:
    """Each malformed frontmatter case retains its original diagnostic contract."""
    skill_dir = tmp_path / directory_name
    write_skill(skill_dir, frontmatter)

    valid, message = skill_validate.validate_skill(skill_dir)

    assert not valid
    if exact_message:
        assert message == expected_message
    else:
        assert expected_message in message


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
