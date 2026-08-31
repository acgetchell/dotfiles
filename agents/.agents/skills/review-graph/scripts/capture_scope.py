#!/usr/bin/env python3
"""Capture a path-bounded, content-based Git review scope manifest."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from review_graph_reuse import SNAPSHOT_FORMAT, source_snapshot

if TYPE_CHECKING:
    from collections.abc import Sequence

_CHUNK_SIZE = 1024 * 1024
_CAPTURE_MODES = frozenset(("branch", "staged", "worktree", "baseline"))
_TIMEOUT_SECONDS = 30


class _Digest(Protocol):
    """Minimal digest interface used by the scope hasher."""

    def update(self, value: bytes, /) -> None:
        """Add bytes to the digest."""

    def hexdigest(self) -> str:
        """Return the hexadecimal digest."""


class _PathDigest:
    """Collect a path identity from the same bytes as the repository digest."""

    def __init__(self, parent: _Digest) -> None:
        self.parent = parent
        self.digest = hashlib.sha256()

    def update(self, value: bytes) -> None:
        """Feed bytes to both the parent and per-path digests."""
        self.parent.update(value)
        self.digest.update(value)

    def hexdigest(self) -> str:
        """Return the per-path digest as a hexadecimal string."""
        return self.digest.hexdigest()


def _run_git(git: str, repo: Path, arguments: Sequence[str]) -> bytes:
    """Run one bounded, literal-pathspec Git command and return stdout bytes."""
    result = subprocess.run(  # noqa: S603 - resolved Git executable and fixed argument lists only.
        [git, "--literal-pathspecs", "-C", os.fspath(repo), *arguments], capture_output=True, check=False, timeout=_TIMEOUT_SECONDS
    )
    if result.returncode != 0:
        command = " ".join(("git", *arguments))
        detail = result.stderr.decode(errors="replace").strip()
        message = f"{command} failed ({result.returncode}): {detail}"
        raise RuntimeError(message)
    return result.stdout


def _try_git(git: str, repo: Path, arguments: Sequence[str]) -> bytes | None:
    """Run Git and return None when the ref or query is unavailable."""
    try:
        return _run_git(git, repo, arguments)
    except RuntimeError:
        return None


def _decode(value: bytes) -> str:
    """Decode Git output using the platform filesystem codec."""
    return os.fsdecode(value).rstrip("\r\n")


def _decode_zlist(value: bytes) -> list[str]:
    """Decode a NUL-delimited Git path or status list."""
    return [os.fsdecode(item) for item in value.split(b"\0") if item]


def _with_paths(arguments: Sequence[str], pathspecs: Sequence[str]) -> tuple[str, ...]:
    """Append a literal Git pathspec boundary when paths were requested."""
    return (*arguments, "--", *pathspecs) if pathspecs else tuple(arguments)


def _normalize_pathspecs(repo: Path, requested_repo: Path, requested: Sequence[str]) -> list[str]:
    """Normalize paths through the requested repository alias without following final symlinks."""
    normalized: set[str] = set()
    for raw_path in requested:
        if not raw_path:
            message = "requested path must not be empty; use '.' for the repository root"
            raise RuntimeError(message)
        candidate = Path(raw_path)
        absolute = Path(os.path.abspath(candidate if candidate.is_absolute() else requested_repo / candidate))  # noqa: PTH100
        relative: Path | None = None
        for boundary in (requested_repo, repo):
            try:
                relative = absolute.relative_to(boundary)
                break
            except ValueError:
                continue
        if relative is None:
            resolved = absolute.resolve(strict=False)
            try:
                relative = resolved.relative_to(repo)
            except ValueError as error:
                message = f"requested path is outside the repository: {raw_path}"
                raise RuntimeError(message) from error
        normalized.add(relative.as_posix() if relative.parts else ".")
    return sorted(normalized)


def _resolve_base(git: str, repo: Path, explicit_base: str | None) -> str:
    """Resolve an explicit base or the repository's default branch ref."""
    if explicit_base:
        if _try_git(git, repo, ("rev-parse", "--verify", f"{explicit_base}^{{commit}}")) is None:
            message = f"base ref does not resolve to a commit: {explicit_base}"
            raise RuntimeError(message)
        return explicit_base

    origin_head = _try_git(git, repo, ("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"))
    candidates: list[str] = []
    if origin_head is not None:
        candidates.append(_decode(origin_head))
    candidates.extend(("origin/main", "origin/master", "main", "master"))
    for candidate in candidates:
        if candidate and _try_git(git, repo, ("rev-parse", "--verify", f"{candidate}^{{commit}}")) is not None:
            return candidate

    message = "could not infer a branch review base; pass --base explicitly"
    raise RuntimeError(message)


def _update_part(digest: _Digest, label: str, value: bytes) -> None:
    """Add one length-delimited value to a digest."""
    label_bytes = label.encode()
    digest.update(len(label_bytes).to_bytes(8, "big"))
    digest.update(label_bytes)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _update_file(digest: _Digest, path: Path, expected_size: int) -> None:
    """Stream a regular file into a length-delimited digest part."""
    label = b"file-content"
    digest.update(len(label).to_bytes(8, "big"))
    digest.update(label)
    digest.update(expected_size.to_bytes(8, "big"))
    bytes_read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
            bytes_read += len(chunk)
    if bytes_read != expected_size:
        message = f"file changed while capturing scope: {path}"
        raise RuntimeError(message)


def _index_entry(git: str, repo: Path, relative: str) -> bytes:
    """Return canonical index metadata for one literal path."""
    return _run_git(git, repo, _with_paths(("ls-files", "--stage", "-z"), (relative,)))


def _is_gitlink(index_entry: bytes) -> bool:
    """Return whether an index entry contains a stage-zero Git link."""
    return any(record.startswith(b"160000 ") and b" 0\t" in record for record in index_entry.split(b"\0"))


def _submodule_fingerprint(git: str, path: Path) -> str:
    """Hash a checked-out submodule commit plus tracked and untracked changes."""
    head = _decode(_run_git(git, path, ("rev-parse", "HEAD")))
    index_entries = _run_git(git, path, ("ls-files", "--stage", "-z"))
    changed = _decode_zlist(_run_git(git, path, ("diff", "--name-only", "--no-renames", "-z", "HEAD")))
    untracked = _decode_zlist(_run_git(git, path, ("ls-files", "--others", "--exclude-standard", "-z")))
    return _worktree_fingerprint(
        git=git,
        identity=(("head", head.encode()), ("index-entries", index_entries), ("mode", b"submodule-worktree")),
        pathspecs=(),
        paths=(*changed, *untracked),
        repo=path,
    )


def _update_worktree_path(digest: _Digest, git: str, repo: Path, relative: str) -> None:
    """Hash one worktree path using Git-relevant type, mode, and content."""
    path = repo / relative
    index_entry = _index_entry(git, repo, relative)
    _update_part(digest, "path", os.fsencode(relative))
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if _is_gitlink(index_entry):
            _update_part(digest, "mode", b"160000-unchecked-out")
            _update_part(digest, "gitlink-index", index_entry)
        else:
            _update_part(digest, "mode", b"deleted")
        return

    if stat.S_ISLNK(metadata.st_mode):
        _update_part(digest, "mode", b"120000")
        _update_part(digest, "symlink-target", os.fsencode(path.readlink()))
        return
    if stat.S_ISREG(metadata.st_mode):
        mode = b"100755" if metadata.st_mode & 0o111 else b"100644"
        _update_part(digest, "mode", mode)
        _update_file(digest, path, metadata.st_size)
        final_metadata = path.lstat()
        if (final_metadata.st_mode, final_metadata.st_size, final_metadata.st_mtime_ns) != (metadata.st_mode, metadata.st_size, metadata.st_mtime_ns):
            message = f"file changed while capturing scope: {path}"
            raise RuntimeError(message)
        return
    if stat.S_ISDIR(metadata.st_mode):
        if not _is_gitlink(index_entry):
            message = f"unexpected directory in file scope: {relative}"
            raise RuntimeError(message)
        _update_part(digest, "mode", b"160000")
        _update_part(digest, "gitlink-index", index_entry)
        _update_part(digest, "gitlink-worktree", _submodule_fingerprint(git, path).encode())
        return
    message = f"unsupported filesystem entry in review scope: {relative}"
    raise RuntimeError(message)


def _worktree_fingerprint(  # noqa: PLR0913 - optional path identities share the canonical fingerprint traversal.
    *,
    git: str,
    identity: Sequence[tuple[str, bytes]],
    pathspecs: Sequence[str],
    paths: Sequence[str],
    repo: Path,
    path_fingerprints: dict[str, str] | None = None,
) -> str:
    """Hash the selected worktree state from canonical path content and modes."""
    digest = hashlib.sha256()
    for label, value in identity:
        _update_part(digest, label, value)
    _update_part(digest, "requested-paths", json.dumps(pathspecs, separators=(",", ":")).encode())
    for relative in sorted(set(paths)):
        if path_fingerprints is None:
            _update_worktree_path(digest, git, repo, relative)
        else:
            path_digest = _PathDigest(digest)
            _update_worktree_path(path_digest, git, repo, relative)
            path_fingerprints[relative] = path_digest.hexdigest()
    return digest.hexdigest()


def _staged_fingerprint(*, git: str, repo: Path, head: str, pathspecs: Sequence[str], paths: Sequence[str]) -> str:
    """Hash the selected index state from canonical mode and object identities."""
    digest = hashlib.sha256()
    _update_part(digest, "head", head.encode())
    _update_part(digest, "mode", b"staged")
    _update_part(digest, "requested-paths", json.dumps(pathspecs, separators=(",", ":")).encode())
    for relative in sorted(set(paths)):
        _update_part(digest, "path", os.fsencode(relative))
    entries = _run_git(git, repo, _with_paths(("ls-files", "--stage", "-z"), pathspecs))
    _update_part(digest, "index-entries", entries)
    return digest.hexdigest()


def _bytes_line_bound(value: bytes) -> int:
    """Return the greatest one-based text line addressable in exact bytes."""
    return value.count(b"\n") + int(bool(value) and not value.endswith(b"\n"))


def _worktree_line_bound(path: Path) -> int | None:
    """Return a stable regular-file line bound, zero for non-files, or None when absent."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return 0
    newlines = 0
    bytes_read = 0
    last_byte = b""
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            newlines += chunk.count(b"\n")
            bytes_read += len(chunk)
            last_byte = chunk[-1:]
    final_metadata = path.lstat()
    if (final_metadata.st_mode, final_metadata.st_size, final_metadata.st_mtime_ns) != (
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    ) or bytes_read != metadata.st_size:
        message = f"file changed while deriving captured line bounds: {path}"
        raise RuntimeError(message)
    return newlines + int(bytes_read > 0 and last_byte != b"\n")


def _git_blob_line_bound(git: str, repo: Path, revision: str, relative: str) -> int | None:
    """Return one tree/index blob's line bound without interpreting symlinks as text."""
    if revision == ":index":
        records = tuple(record for record in _index_entry(git, repo, relative).split(b"\0") if record)
        record = next((entry for entry in records if b" 0\t" in entry), None)
        if record is None:
            return None
        metadata = record.split(b"\t", 1)[0].split()
        if len(metadata) != 3:
            message = f"could not parse captured Git index identity for {relative}"
            raise RuntimeError(message)
        mode, object_id, _stage = metadata
        object_type = b"blob"
    else:
        records = tuple(record for record in _run_git(git, repo, _with_paths(("ls-tree", "-z", revision), (relative,))).split(b"\0") if record)
        if not records:
            return None
        metadata = records[0].split(b"\t", 1)[0].split()
        if len(metadata) < 3:
            message = f"could not parse captured Git object identity for {relative}"
            raise RuntimeError(message)
        mode, object_type, object_id = metadata[:3]
    if mode not in {b"100644", b"100755"} or object_type != b"blob":
        return 0
    return _bytes_line_bound(_run_git(git, repo, ("cat-file", "blob", os.fsdecode(object_id))))


def _captured_path_line_bounds(*, git: str, repo: Path, mode: str, base_revision: str | None, paths: Sequence[str]) -> dict[str, int]:
    """Derive maximum addressable lines from the exact captured source sides."""
    bounds: dict[str, int] = {}
    for relative in paths:
        current = _git_blob_line_bound(git, repo, ":index", relative) if mode == "staged" else _worktree_line_bound(repo / relative)
        base = _git_blob_line_bound(git, repo, base_revision, relative) if base_revision is not None else None
        candidates = tuple(bound for bound in (current, base) if bound is not None)
        if not candidates:
            message = f"captured path has no current or base-side source identity: {relative}"
            raise RuntimeError(message)
        bounds[relative] = max(candidates)
    return bounds


def _repository_state_snapshot(*, git: str, repo: Path, head: str, branch: str, captured_paths: Sequence[str]) -> tuple[str, dict[str, str], str]:
    """Hash HEAD, branch, index, tracked worktree, and nonignored untracked content."""
    tracked = _decode_zlist(_run_git(git, repo, ("ls-files", "-z")))
    untracked = _decode_zlist(_run_git(git, repo, ("ls-files", "--others", "--exclude-standard", "-z")))
    path_fingerprints: dict[str, str] = {}
    worktree = _worktree_fingerprint(
        git=git,
        identity=(("head", head.encode()), ("branch", branch.encode()), ("mode", b"repository-state")),
        pathspecs=(),
        paths=(*tracked, *untracked),
        repo=repo,
        path_fingerprints=path_fingerprints,
    )
    index_entries = _run_git(git, repo, ("ls-files", "--stage", "-z"))
    digest = hashlib.sha256()
    _update_part(digest, "head", head.encode())
    _update_part(digest, "branch", branch.encode())
    _update_part(digest, "index-entries", index_entries)
    _update_part(digest, "worktree", worktree.encode())
    # Deleted branch/index paths remain in the review scope but not ls-files.
    for relative in sorted(set(captured_paths) - path_fingerprints.keys()):
        path_digest = hashlib.sha256()
        _update_worktree_path(path_digest, git, repo, relative)
        path_fingerprints[relative] = path_digest.hexdigest()
    return digest.hexdigest(), path_fingerprints, hashlib.sha256(index_entries).hexdigest()


def _scope_data(git: str, repo: Path, mode: str, base: str | None, pathspecs: Sequence[str]) -> dict[str, object]:  # noqa: PLR0915
    """Build the manifest fields for the requested review mode and path boundary."""
    if mode not in _CAPTURE_MODES:
        message = f"unsupported capture mode: {mode}"
        raise RuntimeError(message)
    if base is not None and mode != "branch":
        message = "--base is valid only with --mode branch"
        raise RuntimeError(message)

    head = _decode(_run_git(git, repo, ("rev-parse", "HEAD")))
    branch_bytes = _try_git(git, repo, ("branch", "--show-current"))
    branch = _decode(branch_bytes) if branch_bytes else ""
    untracked_arguments = _with_paths(("ls-files", "--others", "--exclude-standard", "-z"), pathspecs)
    selected_untracked = _decode_zlist(_run_git(git, repo, untracked_arguments))

    base_ref: str | None = None
    merge_base: str | None = None

    if mode == "branch":
        base_ref = _resolve_base(git, repo, base)
        merge_base = _decode(_run_git(git, repo, ("merge-base", "HEAD", base_ref)))
        path_arguments = _with_paths(("diff", "--name-only", "--no-renames", "-z", merge_base), pathspecs)
        paths = _decode_zlist(_run_git(git, repo, path_arguments))
        paths.extend(selected_untracked)
    elif mode == "staged":
        path_arguments = _with_paths(("diff", "--cached", "--name-only", "--no-renames", "-z", "HEAD"), pathspecs)
        paths = _decode_zlist(_run_git(git, repo, path_arguments))
        selected_untracked = []
    elif mode == "worktree":
        path_arguments = _with_paths(("diff", "--name-only", "--no-renames", "-z", "HEAD"), pathspecs)
        paths = _decode_zlist(_run_git(git, repo, path_arguments))
        paths.extend(selected_untracked)
    elif mode == "baseline":
        path_arguments = _with_paths(("ls-files", "-z"), pathspecs)
        paths = _decode_zlist(_run_git(git, repo, path_arguments))
        paths.extend(selected_untracked)
    else:
        message = f"unsupported capture mode: {mode}"
        raise RuntimeError(message)

    captured_scope_paths = sorted(set(paths))
    if mode == "staged":
        scope_fingerprint = _staged_fingerprint(git=git, repo=repo, head=head, pathspecs=pathspecs, paths=captured_scope_paths)
    else:
        scope_fingerprint = _worktree_fingerprint(
            git=git,
            identity=(("head", head.encode()), ("mode", mode.encode()), ("base-ref", (base_ref or "").encode()), ("merge-base", (merge_base or "").encode())),
            pathspecs=pathspecs,
            paths=captured_scope_paths,
            repo=repo,
        )

    captured_path_line_bounds = _captured_path_line_bounds(
        git=git, repo=repo, mode=mode, base_revision=merge_base if mode == "branch" else head, paths=captured_scope_paths
    )
    confirmed_scope_fingerprint = (
        _staged_fingerprint(git=git, repo=repo, head=head, pathspecs=pathspecs, paths=captured_scope_paths)
        if mode == "staged"
        else _worktree_fingerprint(
            git=git,
            identity=(("head", head.encode()), ("mode", mode.encode()), ("base-ref", (base_ref or "").encode()), ("merge-base", (merge_base or "").encode())),
            pathspecs=pathspecs,
            paths=captured_scope_paths,
            repo=repo,
        )
    )
    if confirmed_scope_fingerprint != scope_fingerprint:
        message = "captured source changed while deriving path line bounds"
        raise RuntimeError(message)

    worktree_paths_arguments = _with_paths(("diff", "--name-only", "--no-renames", "-z", "HEAD"), pathspecs)
    captured_worktree_paths = _decode_zlist(_run_git(git, repo, worktree_paths_arguments))
    captured_worktree_paths.extend(_decode_zlist(_run_git(git, repo, untracked_arguments)))
    captured_worktree_fingerprint = _worktree_fingerprint(
        git=git,
        identity=(("head", head.encode()), ("mode", b"worktree"), ("base-ref", b""), ("merge-base", b"")),
        pathspecs=pathspecs,
        paths=captured_worktree_paths,
        repo=repo,
    )
    status_arguments = _with_paths(("status", "--porcelain=v1", "-z", "--untracked-files=all"), pathspecs)
    status = _decode_zlist(_run_git(git, repo, status_arguments))
    repository_state_fingerprint, repository_path_fingerprints, index_fingerprint = _repository_state_snapshot(
        git=git, repo=repo, head=head, branch=branch, captured_paths=captured_scope_paths
    )

    manifest = {
        "base_ref": base_ref,
        "branch": branch or None,
        "capture_mode": mode,
        "captured_path_line_bounds": captured_path_line_bounds,
        "captured_scope_paths": captured_scope_paths,
        "captured_worktree_fingerprint": captured_worktree_fingerprint,
        "head": head,
        "index_fingerprint": index_fingerprint,
        "merge_base": merge_base,
        "repository_root": os.fspath(repo),
        "repository_path_fingerprints": repository_path_fingerprints,
        "repository_state_fingerprint": repository_state_fingerprint,
        "repository_state_format": SNAPSHOT_FORMAT,
        "requested_paths": list(pathspecs),
        "scope_fingerprint": scope_fingerprint,
        "status": status,
        "untracked_paths": selected_untracked,
    }
    manifest["repository_state_fingerprint"] = source_snapshot(manifest).computed_fingerprint()
    return manifest


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path inside the Git repository")
    parser.add_argument("--mode", choices=("branch", "staged", "worktree", "baseline"), default="branch", help="Review scope to fingerprint")
    parser.add_argument("--base", help="Explicit base ref for branch mode")
    parser.add_argument("--path", action="append", default=[], help="Repository-relative or absolute path boundary; repeat for multiple paths")
    return parser


def main() -> int:
    """Print the captured review scope as JSON."""
    arguments = _parser().parse_args()
    git = shutil.which("git")
    if git is None:
        print("capture_scope.py: git is unavailable", file=sys.stderr)
        return 2

    try:
        requested_repo = Path(os.path.abspath(arguments.repo))  # noqa: PTH100 - preserve a user-provided symlink alias for path translation.
        root = Path(_decode(_run_git(git, requested_repo, ("rev-parse", "--show-toplevel"))))
        pathspecs = _normalize_pathspecs(root, requested_repo, arguments.path)
        manifest = _scope_data(git, root, arguments.mode, arguments.base, pathspecs)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"capture_scope.py: {error}", file=sys.stderr)
        return 2

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
