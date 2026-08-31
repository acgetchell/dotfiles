"""Behavioral tests for the review-graph scope capture helper."""

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence  # noqa: TC003 - keep available for runtime annotation evaluation.
from pathlib import Path
from typing import cast

import pytest
from capture_scope import _scope_data
from review_graph_reuse import source_snapshot

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
    payload: object = json.loads(result.stdout)
    assert isinstance(payload, dict)
    assert all(isinstance(key, str) for key in payload)
    return cast("dict[str, object]", payload)


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


def test_baseline_path_identities_detect_repeated_dirty_edits_without_inventing_untouched_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "edited.txt").write_text("initial\n", encoding="utf-8")
    (repo / "LICENSE").write_text("unchanged\n", encoding="utf-8")
    _commit_all(repo)
    (repo / "edited.txt").write_text("first\n", encoding="utf-8")
    first = _capture(repo, "baseline")
    (repo / "edited.txt").write_text("later\n", encoding="utf-8")

    second = _capture(repo, "baseline")

    assert first["status"] == second["status"]
    before = cast("dict[str, str]", first["repository_path_fingerprints"])
    after = cast("dict[str, str]", second["repository_path_fingerprints"])
    assert {path for path in before if before[path] != after[path]} == {"edited.txt"}
    assert first["index_fingerprint"] == second["index_fingerprint"]


@pytest.mark.parametrize("field", ["repository_path_fingerprints", "captured_scope_paths", "requested_paths", "index_fingerprint"])
def test_capture_fingerprint_binds_path_identity_and_context(tmp_path: Path, field: str) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "source.txt").write_text("original\n", encoding="utf-8")
    _commit_all(repo)
    capture = _capture(repo, "baseline")
    source_snapshot(capture).verify()
    if field == "repository_path_fingerprints":
        capture[field] = {"source.txt": "f" * 64}
    elif field == "index_fingerprint":
        capture[field] = "f" * 64
    else:
        capture[field] = ["substituted.txt"]

    with pytest.raises(ValueError, match="do not match its repository fingerprint"):
        source_snapshot(capture).verify()


def test_baseline_path_identities_cover_rename_deletion_and_executable_mode(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    for name in ("old.txt", "deleted.txt", "script.sh"):
        (repo / name).write_text("content\n", encoding="utf-8")
    _commit_all(repo)
    first = _capture(repo, "baseline")
    (repo / "old.txt").rename(repo / "new.txt")
    (repo / "deleted.txt").unlink()
    (repo / "script.sh").chmod(0o755)

    second = _capture(repo, "baseline")

    before = cast("dict[str, str]", first["repository_path_fingerprints"])
    after = cast("dict[str, str]", second["repository_path_fingerprints"])
    assert {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)} == {"old.txt", "new.txt", "deleted.txt", "script.sh"}
    assert first["index_fingerprint"] == second["index_fingerprint"]


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


def test_captured_line_bounds_cover_base_deletions_and_no_final_newline(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\ntwo\nthree\n", encoding="utf-8")
    _commit_all(repo)

    tracked.write_text("short\nlast", encoding="utf-8")
    modified = _capture(repo, "worktree", "--path", "tracked.txt")
    tracked.unlink()
    deleted = _capture(repo, "worktree", "--path", "tracked.txt")
    untracked = repo / "untracked.txt"
    untracked.write_text("first\nsecond", encoding="utf-8")
    no_final_newline = _capture(repo, "worktree", "--path", "untracked.txt")

    assert modified["captured_path_line_bounds"] == {"tracked.txt": 3}
    assert deleted["captured_path_line_bounds"] == {"tracked.txt": 3}
    assert no_final_newline["captured_path_line_bounds"] == {"untracked.txt": 2}


def test_staged_line_bounds_use_head_and_index_not_unstaged_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    deleted = repo / "deleted.txt"
    tracked.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    deleted.write_text("one\ntwo\nthree\n", encoding="utf-8")
    _commit_all(repo)

    tracked.write_text("staged\nlast", encoding="utf-8")
    added = repo / "added.txt"
    added.write_text("first\nsecond", encoding="utf-8")
    link = repo / "linked.txt"
    link.symlink_to("tracked.txt")
    deleted.unlink()
    _git(repo, "add", "tracked.txt", "added.txt", "linked.txt", "deleted.txt")
    tracked.write_text("unstaged\nhas\nmany\nmore\nlines\nthan-index\n", encoding="utf-8")
    added.write_text("unstaged\ncontent\nthat\nmust\nnot-count\n", encoding="utf-8")

    manifest = _capture(repo, "staged")

    assert manifest["captured_path_line_bounds"] == {"added.txt": 2, "deleted.txt": 3, "linked.txt": 0, "tracked.txt": 4}
    identities = manifest["repository_path_fingerprints"]
    assert isinstance(identities, dict)
    assert {"added.txt", "deleted.txt", "linked.txt", "tracked.txt"} <= identities.keys()


def test_branch_line_bounds_use_numeric_maximum_of_base_and_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    _commit_all(repo)
    tracked.write_text("short\nlast", encoding="utf-8")
    _commit_all(repo)

    manifest = _capture(repo, "branch", "--base", "HEAD~1", "--path", "tracked.txt")

    assert manifest["captured_path_line_bounds"] == {"tracked.txt": 4}


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
