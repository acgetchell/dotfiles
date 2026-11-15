"""Verify whole-directory skill installation without changing user configuration."""

import json
import subprocess
from pathlib import Path

import pytest

import skills_install


def sources(tmp_path: Path) -> Path:
    """Make two complete portable skills with sibling resources."""
    root = tmp_path / "alternate checkout/skills"
    for name in ("first", "second"):
        skill = root / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Exercise portable installation behavior.\n---\n")
        (skill / "resource.txt").write_text(name)
    return root


def test_repeat_install_preserves_unrelated_content_and_complete_resources(tmp_path: Path) -> None:
    root = sources(tmp_path)
    destination = tmp_path / "isolated discovery"
    unrelated = destination / "my-skill"
    unrelated.mkdir(parents=True)
    (unrelated / "SKILL.md").write_text("local skill")
    for _ in range(2):
        skills_install.link_skills(root, destination)
        skills_install.inspect_links(root, destination, installed=True)
    assert (destination / "first").is_symlink()
    assert (destination / "first").samefile(root / "first")
    assert not (destination / "first/SKILL.md").is_symlink()
    assert (destination / "first/resource.txt").read_text() == "first"
    assert (unrelated / "SKILL.md").read_text() == "local skill"


@pytest.mark.parametrize("collision", ["directory", "file", "broken-link", "other-link", "stale-link"])
def test_preflight_rejects_every_collision_before_adding_any_link(tmp_path: Path, collision: str) -> None:
    root = sources(tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    conflict = destination / ("obsolete" if collision == "stale-link" else "second")
    if collision == "directory":
        conflict.mkdir()
        (conflict / "keep").write_text("preserve")
    elif collision == "file":
        conflict.write_text("preserve")
    elif collision == "stale-link":
        conflict.symlink_to(root / "removed", target_is_directory=True)
    else:
        target = tmp_path / "other"
        if collision == "other-link":
            target.mkdir()
        conflict.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match=r"collision|Stale"):
        skills_install.link_skills(root, destination)
    assert not (destination / "first").exists()
    assert conflict.exists() or conflict.is_symlink()
    if collision == "directory":
        assert (conflict / "keep").read_text() == "preserve"
    if collision == "file":
        assert conflict.read_text() == "preserve"


def test_source_as_destination_is_rejected_without_self_links(tmp_path: Path) -> None:
    root = sources(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    for destination in (root, alias, root / "nested"):
        with pytest.raises(ValueError, match="separate"):
            skills_install.link_skills(root, destination)
    assert not (root / "nested").exists()


def test_partial_link_failure_rolls_back_only_new_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = sources(tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = destination / "unrelated"
    marker.write_text("preserve")
    original = Path.symlink_to

    def fail_second(path: Path, target: Path, target_is_directory: bool = False) -> None:
        if path.name == "second":
            msg = "fixture permission denial"
            raise PermissionError(msg)
        original(path, target, target_is_directory=target_is_directory)

    monkeypatch.setattr(Path, "symlink_to", fail_second)
    with pytest.raises(PermissionError, match="fixture"):
        skills_install.link_skills(root, destination)
    assert list(destination.iterdir()) == [marker]
    assert marker.read_text() == "preserve"


@pytest.mark.parametrize("report", [[], {}, {"version": "0.0.0"}, "invalid JSON"])
def test_helper_rejects_malformed_or_incomplete_origin_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, report: object) -> None:
    helper = tmp_path / "helper"
    helper.touch()
    output = report if isinstance(report, str) else json.dumps(report)
    monkeypatch.setattr(skills_install.subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, output, ""))
    with pytest.raises((ValueError, TypeError)):
        skills_install.check_helper(helper)


def test_missing_helper_does_not_create_skill_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = sources(tmp_path)
    monkeypatch.setattr(skills_install, "SKILLS", root)
    destination = tmp_path / "destination"
    assert skills_install.main(["install", "--destination", str(destination), "--helper", str(tmp_path / "missing")]) == 2
    assert not destination.exists()
