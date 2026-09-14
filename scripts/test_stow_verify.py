#!/usr/bin/env python3
"""Tests for stow_verify.py."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import stow_verify


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


def use_no_folding_tree(home: Path, source: Path) -> None:
    """Replace a skill-directory link with file-level Stow links."""
    target = home / ".agents" / "skills" / source.name
    target.unlink()
    target.mkdir()
    for source_file in source.rglob("*"):
        if source_file.is_dir():
            continue
        target_file = target / source_file.relative_to(source)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.symlink_to(source_file)


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


def test_no_folding_skill_tree_fails_codex_discovery_check(tmp_path: Path) -> None:
    """Valid file-level links are insufficient for Codex skill discovery."""
    home, dotfiles = make_env(tmp_path)
    source = dotfiles / "agents" / ".agents" / "skills" / "skill-a"
    use_no_folding_tree(home, source)

    assert any("Codex will skip skill-a" in failure for failure in all_failures(home, dotfiles))


def test_relative_symlinks_resolve_into_repository(tmp_path: Path) -> None:
    """Relative stow-style symlinks are resolved before the containment check."""
    home, dotfiles = make_env(tmp_path)
    (home / ".zshrc").unlink()
    (home / ".zshrc").symlink_to(Path("..") / "dotfiles" / "zsh" / ".zshrc")

    report = stow_verify.check_package_files(home, dotfiles)

    assert report.failures == []


def test_stow_and_verifier_ignore_generated_python_bytecode(tmp_path: Path) -> None:
    """Running Python before or after Stow must not require bytecode links."""
    home, dotfiles = make_env(tmp_path)
    source = dotfiles / "agents" / ".agents" / "skills" / "skill-a"
    (home / ".agents" / "skills" / "skill-a").unlink()
    repository = Path(__file__).resolve().parents[1]
    shutil.copy2(repository / "agents" / ".stow-local-ignore", dotfiles / "agents")
    cache = source / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "tool.cpython-314.pyc").write_bytes(b"bytecode")
    (source / "scripts" / "legacy.pyc").write_bytes(b"bytecode")
    script = source / "scripts" / "tool.py"
    script.write_text("pass\n", encoding="utf-8")
    stow = shutil.which("stow")
    assert stow is not None
    subprocess.run(  # noqa: S603 - resolved Stow executable and isolated test directories.
        [stow, "--no-folding", "-d", str(dotfiles), "-t", str(home), "agents"], check=True, capture_output=True, text=True
    )
    target = home / ".agents" / "skills" / "skill-a" / "scripts"
    assert not (target / "__pycache__").exists()
    assert not (target / "legacy.pyc").exists()
    assert (target / "tool.py").is_symlink()
    (cache / "later.pyc").write_bytes(b"bytecode")
    assert all_failures(home, dotfiles) == ["SKILL.md is a file symlink and Codex will skip skill-a (run: just stow-restow agents)"]
    (target / "tool.py").unlink()
    assert any("tool.py" in failure for failure in all_failures(home, dotfiles))


def prepare_leftover(target: Path, cache: Path, dotfiles: Path, leftover: str) -> Path:
    extra = target / "notes.txt"
    if leftover == "cache-user-file":
        extra = cache / "notes.txt"
    if leftover in {"user-file", "cache-user-file"}:
        extra.write_text("preserve", encoding="utf-8")
    elif leftover == "external-bytecode":
        external = dotfiles.with_name(dotfiles.name + "-external")
        external.mkdir()
        (external / "outside.pyc").write_bytes(b"preserve")
        extra = cache / "outside.pyc"
        extra.symlink_to(external / "outside.pyc")
    elif leftover == "symlink":
        extra.symlink_to(target / "missing")
    return extra


@pytest.mark.parametrize("leftover", ["bytecode", "user-file", "cache-user-file", "symlink", "external-bytecode"])
def test_restow_recipe_migrates_file_links_to_discoverable_directory_links(tmp_path: Path, leftover: str) -> None:
    """Restow fixes legacy links and preserves unrelated user skills."""
    home, dotfiles = make_env(tmp_path)
    source = dotfiles / "agents" / ".agents" / "skills" / "skill-a"
    use_no_folding_tree(home, source)
    legacy_manifest = home / ".agents" / "skills" / "skill-a" / "SKILL.md"
    legacy_manifest.unlink()
    legacy_manifest.symlink_to(os.path.relpath(source / "SKILL.md", legacy_manifest.parent))
    cache = legacy_manifest.parent / "__pycache__"
    cache.mkdir()
    (cache / "old.pyc").write_bytes(b"bytecode")
    (legacy_manifest.parent / "old.pyo").write_bytes(b"bytecode")
    extra = prepare_leftover(legacy_manifest.parent, cache, dotfiles, leftover)
    personal = home / ".agents" / "skills" / "personal" / "SKILL.md"
    personal.parent.mkdir()
    personal.write_text("personal skill\n", encoding="utf-8")
    repository = Path(__file__).resolve().parents[1]
    shutil.copy2(repository / "justfile", dotfiles / "justfile")
    (dotfiles / "bin").mkdir()
    shutil.copy2(repository / "bin" / "restow-agents.sh", dotfiles / "bin")
    just = shutil.which("just")
    assert just is not None
    for _ in range(2):
        result = subprocess.run(  # noqa: S603 - resolved Just executable and isolated test home.
            [just, "stow-restow", "agents"], check=False, capture_output=True, text=True, cwd=dotfiles, env={**os.environ, "HOME": str(home)}
        )
        if leftover != "bytecode":
            assert result.returncode != 0
            assert "manual review" in result.stderr
            if leftover in {"symlink", "external-bytecode"}:
                assert extra.is_symlink()
            else:
                assert extra.read_text(encoding="utf-8") == "preserve"
            assert personal.read_text(encoding="utf-8") == "personal skill\n"
            assert legacy_manifest.is_file()
            assert legacy_manifest.resolve() == source / "SKILL.md"
            continue
        assert result.returncode == 0, result.stderr
    manifest = home / ".agents" / "skills" / "skill-a" / "SKILL.md"
    assert manifest.is_file()
    if leftover != "bytecode":
        return
    assert not manifest.is_symlink()
    assert manifest.resolve() == source / "SKILL.md"
    assert personal.read_text(encoding="utf-8") == "personal skill\n"
    assert all_failures(home, dotfiles) == []


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


def test_symlink_to_wrong_repository_file_fails(tmp_path: Path) -> None:
    """A home link must resolve to its matching package source."""
    home, dotfiles = make_env(tmp_path)
    (home / ".zshrc").unlink()
    (home / ".zshrc").symlink_to(dotfiles / "git" / ".gitconfig")

    failures = stow_verify.check_package_files(home, dotfiles).failures

    assert any(".zshrc" in failure and "wrong repository file" in failure for failure in failures)


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

    assert any("skill file not stowed" in failure and "skill-a" in failure for failure in failures)


def test_no_folding_skill_file_linked_to_foreign_file_fails(tmp_path: Path) -> None:
    """A file-level skill link must resolve to its matching repository file."""
    home, dotfiles = make_env(tmp_path)
    source = dotfiles / "agents" / ".agents" / "skills" / "skill-a"
    use_no_folding_tree(home, source)
    foreign = tmp_path / "elsewhere" / "SKILL.md"
    foreign.parent.mkdir()
    foreign.write_text("foreign\n", encoding="utf-8")
    link = home / ".agents" / "skills" / "skill-a" / "SKILL.md"
    link.unlink()
    link.symlink_to(foreign)

    failures = stow_verify.check_skills(home, dotfiles).failures

    assert any("skill file points to wrong target" in failure for failure in failures)


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


def test_main_reports_missing_home_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An invalid --home path produces a normal failure report."""
    _, dotfiles = make_env(tmp_path)
    missing_home = tmp_path / "missing-home"

    code = stow_verify.main(["--home", str(missing_home), "--dotfiles-dir", str(dotfiles)])

    captured = capsys.readouterr()
    assert code == 1
    assert f"{missing_home} missing or is not a directory" in captured.out
    assert "FAILURES detected" in captured.err


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


@pytest.mark.parametrize("suffix", [".pyc", ".pyo"])
def test_restow_removes_legacy_repository_bytecode_symlinks(tmp_path: Path, suffix: str) -> None:
    """Clean ignored legacy links without touching their repository targets."""
    root = tmp_path / "paths with spaces"
    home, dotfiles = make_env(root)
    source = dotfiles / "agents" / ".agents" / "skills" / "skill-a"
    use_no_folding_tree(home, source)
    manifest = home / ".agents" / "skills" / "skill-a" / "SKILL.md"
    manifest.unlink()
    manifest.symlink_to(os.path.relpath(source / "SKILL.md", manifest.parent))
    repository = Path(__file__).resolve().parents[1]
    shutil.copy2(repository / "agents" / ".stow-local-ignore", dotfiles / "agents")
    cache = source / "__pycache__"
    cache.mkdir()
    artifact = cache / f"legacy file{suffix}"
    artifact.write_bytes(b"repository bytecode")
    target_cache = manifest.parent / "__pycache__"
    target_cache.mkdir()
    (target_cache / artifact.name).symlink_to(os.path.relpath(artifact, target_cache))
    for _ in range(2):
        result = subprocess.run(  # noqa: S603 - fixed repository helper and isolated fixture.
            ["/bin/bash", str(repository / "bin" / "restow-agents.sh"), str(dotfiles)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(home)},
        )
        assert result.returncode == 0, result.stderr
        assert manifest.is_file()
        assert not manifest.is_symlink()
        assert artifact.read_bytes() == b"repository bytecode"
