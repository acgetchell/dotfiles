"""Behavioral tests for the review-graph scope capture helper."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from capture_scope import _scope_data

if TYPE_CHECKING:
    from collections.abc import Sequence

_TIMEOUT_SECONDS = 30


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 - tests invoke resolved Git and the current Python executable only.
        command, cwd=cwd, check=False, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
    )
    assert result.returncode == 0, result.stderr
    return result


def _git(repo: Path, *arguments: str) -> str:
    git = shutil.which("git")
    assert git is not None
    return _run((git, *arguments), repo).stdout


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.name", "Review Graph Test")
    _git(repo, "config", "user.email", "review-graph@example.invalid")


def _commit_all(repo: Path) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "--quiet", "-m", "fixture")


def _capture(repo: Path, mode: str, *arguments: str) -> dict[str, object]:
    script = Path(__file__).with_name("capture_scope.py")
    result = _run((sys.executable, str(script), "--repo", str(repo), "--mode", mode, *arguments), repo)
    return json.loads(result.stdout)


def _capture_result(repo: Path, mode: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).with_name("capture_scope.py")
    return subprocess.run(  # noqa: S603 - tests invoke the current Python executable only.
        (sys.executable, str(script), "--repo", str(repo), "--mode", mode, *arguments),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )


def test_path_boundary_excludes_unrelated_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    scoped = repo / "scoped"
    unrelated = repo / "unrelated"
    scoped.mkdir()
    unrelated.mkdir()
    (scoped / "tracked.txt").write_text("one\n", encoding="utf-8")
    (unrelated / "tracked.txt").write_text("one\n", encoding="utf-8")
    _commit_all(repo)

    (scoped / "tracked.txt").write_text("two\n", encoding="utf-8")
    (scoped / "new.txt").write_text("new\n", encoding="utf-8")
    (unrelated / "tracked.txt").write_text("two\n", encoding="utf-8")
    (unrelated / "new.txt").write_text("new\n", encoding="utf-8")

    manifest = _capture(repo, "worktree", "--path", "scoped")

    assert manifest["requested_paths"] == ["scoped"]
    assert manifest["captured_scope_paths"] == ["scoped/new.txt", "scoped/tracked.txt"]
    assert manifest["untracked_paths"] == ["scoped/new.txt"]
    status = manifest["status"]
    assert isinstance(status, list)
    assert all(isinstance(entry, str) and "unrelated" not in entry for entry in status)


def test_repository_state_fingerprint_covers_content_outside_path_boundary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    scoped = repo / "scoped.txt"
    unrelated = repo / "unrelated.txt"
    scoped.write_text("one\n", encoding="utf-8")
    unrelated.write_text("one\n", encoding="utf-8")
    _commit_all(repo)
    scoped.write_text("two\n", encoding="utf-8")

    first = _capture(repo, "worktree", "--path", "scoped.txt")
    unrelated.write_text("two\n", encoding="utf-8")
    second = _capture(repo, "worktree", "--path", "scoped.txt")

    assert first["scope_fingerprint"] == second["scope_fingerprint"]
    assert first["captured_worktree_fingerprint"] == second["captured_worktree_fingerprint"]
    assert first["repository_state_fingerprint"] != second["repository_state_fingerprint"]


def test_repository_state_fingerprint_covers_index_with_same_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    _commit_all(repo)
    tracked.write_text("two\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")

    staged = _capture(repo, "worktree")
    _git(repo, "restore", "--staged", "tracked.txt")
    unstaged = _capture(repo, "worktree")

    assert staged["captured_worktree_fingerprint"] == unstaged["captured_worktree_fingerprint"]
    assert staged["repository_state_fingerprint"] != unstaged["repository_state_fingerprint"]


def test_repository_state_fingerprint_covers_untracked_content_outside_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "scoped.txt").write_text("tracked\n", encoding="utf-8")
    _commit_all(repo)
    untracked = repo / "outside.txt"
    untracked.write_text("one\n", encoding="utf-8")

    first = _capture(repo, "worktree", "--path", "scoped.txt")
    untracked.write_text("two\n", encoding="utf-8")
    second = _capture(repo, "worktree", "--path", "scoped.txt")

    assert first["scope_fingerprint"] == second["scope_fingerprint"]
    assert first["captured_worktree_fingerprint"] == second["captured_worktree_fingerprint"]
    assert first["repository_state_fingerprint"] != second["repository_state_fingerprint"]


def test_baseline_includes_untracked_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _commit_all(repo)
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    manifest = _capture(repo, "baseline")

    assert manifest["captured_scope_paths"] == ["new.txt", "tracked.txt"]
    assert manifest["untracked_paths"] == ["new.txt"]


def test_untracked_executable_mode_changes_fingerprint(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _commit_all(repo)
    script = repo / "untracked.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)

    regular = _capture(repo, "worktree", "--path", "untracked.sh")
    script.chmod(0o755)
    executable = _capture(repo, "worktree", "--path", "untracked.sh")

    assert regular["scope_fingerprint"] != executable["scope_fingerprint"]


def test_git_diff_presentation_config_does_not_change_fingerprint(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    _commit_all(repo)
    tracked.write_text("two\n", encoding="utf-8")

    default = _capture(repo, "worktree")
    _git(repo, "config", "diff.noprefix", "true")
    configured = _capture(repo, "worktree")

    assert default["scope_fingerprint"] == configured["scope_fingerprint"]


def test_staged_fingerprint_ignores_unstaged_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    _commit_all(repo)
    tracked.write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    tracked.write_text("unstaged one\n", encoding="utf-8")

    first = _capture(repo, "staged")
    tracked.write_text("unstaged two\n", encoding="utf-8")
    second = _capture(repo, "staged")

    assert first["scope_fingerprint"] == second["scope_fingerprint"]
    assert first["captured_worktree_fingerprint"] != second["captured_worktree_fingerprint"]


def test_absolute_path_through_repository_symlink_is_accepted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    _commit_all(repo)
    tracked.write_text("two\n", encoding="utf-8")
    alias = tmp_path / "repo-alias"
    alias.symlink_to(repo, target_is_directory=True)

    manifest = _capture(alias, "worktree", "--path", str(alias / "tracked.txt"))

    assert manifest["requested_paths"] == ["tracked.txt"]
    assert manifest["captured_scope_paths"] == ["tracked.txt"]


def test_invalid_mode_and_base_combination_are_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _commit_all(repo)
    git = shutil.which("git")
    assert git is not None

    with pytest.raises(RuntimeError, match="unsupported capture mode"):
        _scope_data(git, repo, "typo", None, ())

    result = _capture_result(repo, "worktree", "--base", "HEAD")
    assert result.returncode == 2
    assert "--base is valid only with --mode branch" in result.stderr


def test_empty_path_is_rejected_without_widening_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _commit_all(repo)

    empty = _capture_result(repo, "baseline", "--path", "")
    explicit_root = _capture(repo, "baseline", "--path", ".")

    assert empty.returncode == 2
    assert "requested path must not be empty; use '.' for the repository root" in empty.stderr
    assert explicit_root["requested_paths"] == ["."]


def test_repository_root_preserves_trailing_space(tmp_path: Path) -> None:
    repo = tmp_path / "repo "
    _init_repo(repo)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _commit_all(repo)

    manifest = _capture(repo, "baseline")

    assert manifest["repository_root"] == str(repo)


def test_baseline_hashes_checked_out_submodule_state(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    _init_repo(nested)
    nested_file = nested / "nested.txt"
    nested_file.write_text("one\n", encoding="utf-8")
    _commit_all(nested)

    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(nested), "vendor/nested")
    _commit_all(repo)
    checkout_file = repo / "vendor" / "nested" / "nested.txt"

    clean = _capture(repo, "baseline")
    checkout_file.write_text("two\n", encoding="utf-8")
    dirty = _capture(repo, "baseline")

    assert clean["scope_fingerprint"] != dirty["scope_fingerprint"]


def test_repository_state_fingerprint_covers_submodule_index(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    _init_repo(nested)
    nested_file = nested / "nested.txt"
    nested_file.write_text("one\n", encoding="utf-8")
    _commit_all(nested)

    repo = tmp_path / "repo"
    _init_repo(repo)
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(nested), "vendor/nested")
    _commit_all(repo)
    checkout = repo / "vendor" / "nested"
    checkout_file = checkout / "nested.txt"
    checkout_file.write_text("two\n", encoding="utf-8")
    _git(checkout, "add", "nested.txt")

    staged = _capture(repo, "baseline")
    _git(checkout, "restore", "--staged", "nested.txt")
    unstaged = _capture(repo, "baseline")

    assert staged["repository_state_fingerprint"] != unstaged["repository_state_fingerprint"]
