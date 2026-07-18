#!/usr/bin/env python3
"""Tests for stow_verify.py."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import stow_verify

if TYPE_CHECKING:
    import pytest


def make_env(tmp_path: Path) -> tuple[Path, Path]:
    """Create a fake home and dotfiles repository with valid stow symlinks."""
    home = tmp_path / "home"
    dotfiles = tmp_path / "dotfiles"
    (dotfiles / "zsh").mkdir(parents=True)
    (dotfiles / "git").mkdir()
    (dotfiles / "zsh" / ".zshrc").write_text("# zshrc\n", encoding="utf-8")
    (dotfiles / "git" / ".gitconfig").write_text("[user]\n", encoding="utf-8")
    skill_dir = dotfiles / "agents" / ".agents" / "skills" / "skill-a"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: skill-a\n---\n", encoding="utf-8")

    home_skills = home / ".agents" / "skills"
    home_skills.mkdir(parents=True)
    (home / ".zshrc").symlink_to(dotfiles / "zsh" / ".zshrc")
    (home / ".gitconfig").symlink_to(dotfiles / "git" / ".gitconfig")
    (home_skills / "skill-a").symlink_to(skill_dir)
    return home, dotfiles


def all_failures(home: Path, dotfiles: Path) -> list[str]:
    """Collect failures from every check section."""
    return [
        *stow_verify.check_package_files(home, dotfiles).failures,
        *stow_verify.check_skills(home, dotfiles).failures,
        *stow_verify.check_home_links(home, dotfiles).failures,
    ]


def test_valid_layout_has_no_failures(tmp_path: Path) -> None:
    """A fully stowed layout passes every check."""
    home, dotfiles = make_env(tmp_path)

    assert all_failures(home, dotfiles) == []


def test_relative_symlinks_resolve_into_repository(tmp_path: Path) -> None:
    """Relative stow-style symlinks are resolved before the containment check."""
    home, dotfiles = make_env(tmp_path)
    (home / ".zshrc").unlink()
    (home / ".zshrc").symlink_to(Path("..") / "dotfiles" / "zsh" / ".zshrc")

    report = stow_verify.check_package_files(home, dotfiles)

    assert report.failures == []


def test_missing_stowed_file_fails(tmp_path: Path) -> None:
    """A package file without a home symlink is reported."""
    home, dotfiles = make_env(tmp_path)
    (home / ".gitconfig").unlink()

    failures = stow_verify.check_package_files(home, dotfiles).failures

    assert any(".gitconfig missing" in failure for failure in failures)


def test_regular_file_instead_of_symlink_fails(tmp_path: Path) -> None:
    """A real file shadowing a stow target is reported."""
    home, dotfiles = make_env(tmp_path)
    (home / ".zshrc").unlink()
    (home / ".zshrc").write_text("# local\n", encoding="utf-8")

    failures = stow_verify.check_package_files(home, dotfiles).failures

    assert any("not a stow symlink" in failure for failure in failures)


def test_symlink_outside_repository_fails(tmp_path: Path) -> None:
    """A stow target linked to a foreign file is reported."""
    home, dotfiles = make_env(tmp_path)
    foreign = tmp_path / "elsewhere" / ".gitconfig"
    foreign.parent.mkdir()
    foreign.write_text("[user]\n", encoding="utf-8")
    (home / ".gitconfig").unlink()
    (home / ".gitconfig").symlink_to(foreign)

    failures = stow_verify.check_package_files(home, dotfiles).failures

    assert any("points outside" in failure for failure in failures)


def test_dangling_stowed_file_fails(tmp_path: Path) -> None:
    """A stow symlink whose repository file was removed is reported.

    The removed file no longer appears in the package, so the stale home link
    is caught by the top-level dangling-symlink check rather than the
    package-derived check.
    """
    home, dotfiles = make_env(tmp_path)
    (dotfiles / "git" / ".gitconfig").unlink()

    failures = all_failures(home, dotfiles)

    assert any("dangling symlink" in failure and ".gitconfig" in failure for failure in failures)


def test_zshrc_local_only_required_when_package_copy_exists(tmp_path: Path) -> None:
    """The gitignored zsh/.zshrc.local is only expected when present locally."""
    home, dotfiles = make_env(tmp_path)

    assert stow_verify.check_package_files(home, dotfiles).failures == []

    (dotfiles / "zsh" / ".zshrc.local").write_text("# local\n", encoding="utf-8")
    failures = stow_verify.check_package_files(home, dotfiles).failures
    assert any(".zshrc.local missing" in failure for failure in failures)

    (home / ".zshrc.local").symlink_to(dotfiles / "zsh" / ".zshrc.local")
    assert stow_verify.check_package_files(home, dotfiles).failures == []


def test_dangling_skill_symlink_fails(tmp_path: Path) -> None:
    """A skill link left behind after a rename or removal is reported."""
    home, dotfiles = make_env(tmp_path)
    (home / ".agents" / "skills" / "skill-gone").symlink_to(dotfiles / "agents" / ".agents" / "skills" / "skill-gone")

    failures = stow_verify.check_skills(home, dotfiles).failures

    assert any("dangling skill symlink" in failure for failure in failures)


def test_unstowed_repo_skill_fails(tmp_path: Path) -> None:
    """A repository skill without a home symlink is reported."""
    home, dotfiles = make_env(tmp_path)
    skill_b = dotfiles / "agents" / ".agents" / "skills" / "skill-b"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text("---\nname: skill-b\n---\n", encoding="utf-8")

    failures = stow_verify.check_skills(home, dotfiles).failures

    assert any("skill not stowed: skill-b" in failure for failure in failures)


def test_repo_skill_linked_to_foreign_directory_fails(tmp_path: Path) -> None:
    """A same-named skill symlink must resolve to the repository skill."""
    home, dotfiles = make_env(tmp_path)
    foreign_skill = tmp_path / "elsewhere" / "skill-a"
    foreign_skill.mkdir(parents=True)
    skill_link = home / ".agents" / "skills" / "skill-a"
    skill_link.unlink()
    skill_link.symlink_to(foreign_skill)

    failures = stow_verify.check_skills(home, dotfiles).failures

    assert any("skill points to wrong target" in failure and "skill-a" in failure for failure in failures)


def test_repo_skill_shadowed_by_regular_directory_fails(tmp_path: Path) -> None:
    """A same-named directory cannot stand in for a stowed skill symlink."""
    home, dotfiles = make_env(tmp_path)
    skill_link = home / ".agents" / "skills" / "skill-a"
    skill_link.unlink()
    skill_link.mkdir()

    failures = stow_verify.check_skills(home, dotfiles).failures

    assert any("exists but is not a symlink" in failure and "skill-a" in failure for failure in failures)


def test_missing_skills_dir_fails(tmp_path: Path) -> None:
    """A home without ~/.agents/skills is reported."""
    home, dotfiles = make_env(tmp_path)
    (home / ".agents" / "skills" / "skill-a").unlink()
    (home / ".agents" / "skills").rmdir()

    failures = stow_verify.check_skills(home, dotfiles).failures

    assert any("skills missing" in failure for failure in failures)


def test_dangling_home_link_into_repository_fails(tmp_path: Path) -> None:
    """A dangling top-level home symlink pointing into the repository is reported."""
    home, dotfiles = make_env(tmp_path)
    (home / ".old-config").symlink_to(dotfiles / "old" / ".old-config")

    failures = stow_verify.check_home_links(home, dotfiles).failures

    assert any(".old-config" in failure for failure in failures)


def test_dangling_home_link_elsewhere_is_ignored(tmp_path: Path) -> None:
    """Dangling home symlinks unrelated to the repository are not reported."""
    home, dotfiles = make_env(tmp_path)
    (home / ".unrelated").symlink_to(tmp_path / "elsewhere" / "gone")

    assert stow_verify.check_home_links(home, dotfiles).failures == []


def test_main_returns_zero_for_valid_layout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exits 0 and prints a success summary for a valid layout."""
    home, dotfiles = make_env(tmp_path)

    code = stow_verify.main(["--home", str(home), "--dotfiles-dir", str(dotfiles)])

    captured = capsys.readouterr()
    assert code == 0
    assert "all stow symlinks verified" in captured.out
    assert captured.err == ""


def test_main_returns_one_and_reports_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI exits 1 and prints failures to stderr when checks fail."""
    home, dotfiles = make_env(tmp_path)
    (home / ".zshrc").unlink()

    code = stow_verify.main(["--home", str(home), "--dotfiles-dir", str(dotfiles)])

    captured = capsys.readouterr()
    assert code == 1
    assert ".zshrc missing" in captured.out
    assert "FAILURES detected" in captured.err
