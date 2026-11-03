#!/usr/bin/env python3
"""Capture a path-bounded, content-based Git review scope manifest."""

__lazy_modules__ = (
    "argparse",
    "subprocess",
    "research_repo_tools.git_inspect",
    "research_repo_tools.process",
    "review_graph_git_objects",
    "review_graph_reuse",
)

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from itertools import batched
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from research_repo_tools.git_inspect import git_diff_paths_bytes, git_status_bytes
from research_repo_tools.process import ExecutableNotFoundError, format_exception_diagnostics, run_command_bytes
from review_graph_capture_timing import collect_timings, phase, timed_phase
from review_graph_git_objects import GitPathIdentity, git_object_id
from review_graph_reuse import SNAPSHOT_FORMAT, source_snapshot

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

_CHUNK_SIZE = 1024 * 1024
_CAPTURE_MODES = frozenset(("branch", "staged", "worktree", "baseline"))
_TIMEOUT_SECONDS = 30
_BLOB_BATCH_BYTES = 16 * 1024 * 1024


class _Digest(Protocol):
    """Minimal digest interface used by the scope hasher."""

    def update(self, value: bytes, /) -> None:
        """Add bytes to the digest."""

    def hexdigest(self) -> str:
        """Return the hexadecimal digest."""


def _run_git(git: str, repo: Path, arguments: Sequence[str], *, payload: bytes | None = None) -> bytes:
    """Run a bounded literal metadata/object query; status/diff use shared inspection."""
    with phase("git." + arguments[0]):
        result = run_command_bytes(
            git, ("--no-optional-locks", "--literal-pathspecs", "-C", os.fspath(repo), *arguments), check=False, input=payload, timeout=_TIMEOUT_SECONDS
        )
        if result.returncode != 0:
            command = " ".join(("git", *arguments))
            detail = result.stderr.decode(errors="replace").strip()
            message = f"{command} failed ({result.returncode}): {detail}"
            raise RuntimeError(message)
        return result.stdout


@timed_phase("git.diff")
def _diff_paths(repo: Path, paths: Sequence[str], *, base: str, cached: bool = False) -> list[str]:
    """Use the published content-based inspection interface with bounded byte transport."""
    return _decode_zlist(git_diff_paths_bytes(repo, base=base, cached=cached, paths=paths, timeout=_TIMEOUT_SECONDS).stdout)


@timed_phase("git.status")
def _status(repo: Path, paths: Sequence[str]) -> list[str]:
    """Use the published index-preserving porcelain observation."""
    return _decode_zlist(git_status_bytes(repo, paths=paths, timeout=_TIMEOUT_SECONDS).stdout)


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
    if explicit_base is not None and explicit_base:
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
    tracked = _decode_zlist(_run_git(git, path, ("ls-files", "-z")))
    tracked.extend(_decode_zlist(_run_git(git, path, ("ls-tree", "--name-only", "-r", "-z", head))))
    untracked = _decode_zlist(_run_git(git, path, ("ls-files", "--others", "--exclude-standard", "-z")))
    return _worktree_fingerprint(
        git=git,
        identity=(("head", head.encode()), ("index-entries", index_entries), ("mode", b"submodule-worktree")),
        pathspecs=(),
        paths=(*tracked, *untracked),
        repo=path,
    )


def _file_blob_id(path: Path, expected_size: int, algorithm: str) -> str:
    """Stream raw worktree bytes using Git framing, without filters or subprocesses."""
    if algorithm not in {"sha1", "sha256"}:
        msg = "Git source identity requires sha1 or sha256"
        raise ValueError(msg)
    digest = hashlib.new(algorithm, f"blob {expected_size}\0".encode(), usedforsecurity=False)
    bytes_read = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
            bytes_read += len(chunk)
    if bytes_read != expected_size:
        msg = f"file changed while capturing scope: {path}"
        raise RuntimeError(msg)
    return digest.hexdigest()


def _update_worktree_path(digest: _Digest, git: str, repo: Path, relative: str, algorithm: str) -> str:
    """Bind one path to its native Git mode/object identity without writing objects."""
    path = repo / relative
    _update_part(digest, "path", os.fsencode(relative))
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        index_entry = _index_entry(git, repo, relative)
        if _is_gitlink(index_entry):
            _update_part(digest, "mode", b"160000-unchecked-out")
            _update_part(digest, "gitlink-index", index_entry)
            identity = "submodule:" + hashlib.sha256(index_entry).hexdigest()
        else:
            _update_part(digest, "mode", b"deleted")
            identity = "absent"
        return identity

    if stat.S_ISLNK(metadata.st_mode):
        _update_part(digest, "mode", b"120000")
        identity = GitPathIdentity(algorithm, "120000", git_object_id("blob", os.fsencode(path.readlink()), algorithm)).serialize()
        _update_part(digest, "git-object", identity.encode())
        return identity
    if stat.S_ISREG(metadata.st_mode):
        mode = b"100755" if metadata.st_mode & stat.S_IXUSR else b"100644"
        _update_part(digest, "mode", mode)
        oid = _file_blob_id(path, metadata.st_size, algorithm)
        identity = GitPathIdentity(algorithm, mode.decode(), oid).serialize()
        _update_part(digest, "git-object", identity.encode())
        final_metadata = path.lstat()
        if (final_metadata.st_mode, final_metadata.st_size, final_metadata.st_mtime_ns) != (metadata.st_mode, metadata.st_size, metadata.st_mtime_ns):
            message = f"file changed while capturing scope: {path}"
            raise RuntimeError(message)
        return identity
    if stat.S_ISDIR(metadata.st_mode):
        index_entry = _index_entry(git, repo, relative)
        if not _is_gitlink(index_entry):
            message = f"unexpected directory in file scope: {relative}"
            raise RuntimeError(message)
        if not (path / ".git").exists():
            if any(path.iterdir()):
                message = f"nonempty gitlink directory has no repository metadata: {relative}"
                raise RuntimeError(message)
            _update_part(digest, "mode", b"160000-unchecked-out")
            _update_part(digest, "gitlink-index", index_entry)
            return "submodule:" + hashlib.sha256(index_entry).hexdigest()
        _update_part(digest, "mode", b"160000")
        _update_part(digest, "gitlink-index", index_entry)
        submodule = _submodule_fingerprint(git, path)
        _update_part(digest, "gitlink-worktree", submodule.encode())
        return "submodule:" + hashlib.sha256(index_entry + submodule.encode()).hexdigest()
    message = f"unsupported filesystem entry in review scope: {relative}"
    raise RuntimeError(message)


@timed_phase("worktree_content_and_modes")
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
    algorithm = _decode(_run_git(git, repo, ("rev-parse", "--show-object-format")))
    for label, value in identity:
        _update_part(digest, label, value)
    _update_part(digest, "requested-paths", json.dumps(pathspecs, separators=(",", ":")).encode())
    for relative in sorted(set(paths)):
        path_identity = _update_worktree_path(digest, git, repo, relative, algorithm)
        if path_fingerprints is not None:
            path_fingerprints[relative] = path_identity
    return digest.hexdigest()


@timed_phase("staged_identity")
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


def _blob_entries(git: str, repo: Path, revision: str) -> dict[str, tuple[bytes, bytes]]:
    """Read one tree/index inventory; unresolved index stages have no current blob."""
    arguments = ("ls-files", "--stage", "-z") if revision == ":index" else ("ls-tree", "-r", "-z", revision)
    entries = {}
    for record in _run_git(git, repo, arguments).split(b"\0"):
        if not record:
            continue
        metadata, relative = record.split(b"\t", 1)
        mode, second, third = metadata.split()
        if revision == ":index":
            if third != b"0":
                continue
            object_id = second
        else:
            object_id = third
        entries[os.fsdecode(relative)] = (mode, object_id)
    return entries


def _batch_blob_size(record: bytes, object_id: bytes) -> int:
    """Require an exact blob identity and decimal byte size in either batch protocol."""
    fields = record.split()
    if len(fields) != 3 or fields[:2] != [object_id, b"blob"] or not fields[2].isdigit():
        message = "could not parse captured Git batch blob identity"
        raise RuntimeError(message)
    return int(fields[2])


def _blob_batches(git: str, repo: Path, object_ids: Sequence[bytes]) -> Generator[tuple[tuple[bytes, int], ...]]:
    """Bound aggregate payload bytes; preserve single reads of oversized blobs."""
    pending: list[tuple[bytes, int]] = []
    pending_bytes = 0
    for identities in batched(dict.fromkeys(object_ids), 1024, strict=False):
        output = _run_git(git, repo, ("cat-file", "--batch-check"), payload=b"\n".join(identities) + b"\n")
        records = output.split(b"\n")
        if len(records) != len(identities) + 1 or records[-1] != b"":
            message = "invalid captured Git batch metadata"
            raise RuntimeError(message)
        for object_id, record in zip(identities, records[:-1], strict=True):
            size = _batch_blob_size(record, object_id)
            if pending and (len(pending) == 64 or pending_bytes + size > _BLOB_BATCH_BYTES):
                yield tuple(pending)
                pending = []
                pending_bytes = 0
            pending.append((object_id, size))
            pending_bytes += size
    if pending:
        yield tuple(pending)


def _batch_blob_line_bounds(git: str, repo: Path, object_ids: Sequence[bytes]) -> dict[bytes, int]:
    """Count exact immutable blobs without combining unbounded payloads in memory."""
    bounds = {}
    for batch in _blob_batches(git, repo, object_ids):
        output = _run_git(git, repo, ("cat-file", "--batch"), payload=b"\n".join(oid for oid, _size in batch) + b"\n")
        offset = 0
        for object_id, expected_size in batch:
            header_end = output.find(b"\n", offset)
            if header_end < offset:
                message = "could not parse captured Git batch blob identity"
                raise RuntimeError(message)
            size = _batch_blob_size(output[offset:header_end], object_id)
            if size != expected_size:
                message = "captured Git batch blob size changed"
                raise RuntimeError(message)
            start, end = header_end + 1, header_end + 1 + size
            if end >= len(output) or output[end : end + 1] != b"\n":
                message = "truncated captured Git batch blob"
                raise RuntimeError(message)
            bounds[object_id] = output.count(b"\n", start, end) + int(end > start and output[end - 1 : end] != b"\n")
            offset = end + 1
        if offset != len(output):
            message = "unexpected trailing captured Git batch bytes"
            raise RuntimeError(message)
    return bounds


def _git_blob_line_bounds(git: str, repo: Path, revision: str, paths: Sequence[str]) -> dict[str, int]:
    """Derive path bounds from one inventory and exact immutable blob contents."""
    entries = _blob_entries(git, repo, revision)
    selected = {path: entries[path] for path in paths if path in entries}
    bounds = _batch_blob_line_bounds(git, repo, [object_id for mode, object_id in selected.values() if mode in {b"100644", b"100755"}])
    return {path: bounds[object_id] if mode in {b"100644", b"100755"} else 0 for path, (mode, object_id) in selected.items()}


@timed_phase("line_bounds")
def _captured_path_line_bounds(*, git: str, repo: Path, mode: str, base_revision: str | None, paths: Sequence[str]) -> dict[str, int]:
    """Derive maximum addressable lines from the exact captured source sides."""
    current_bounds = _git_blob_line_bounds(git, repo, ":index", paths) if mode == "staged" and paths else {}
    base_bounds = _git_blob_line_bounds(git, repo, base_revision, paths) if base_revision is not None and paths else {}
    bounds: dict[str, int] = {}
    for relative in paths:
        current = current_bounds.get(relative) if mode == "staged" else _worktree_line_bound(repo / relative)
        base = base_bounds.get(relative)
        candidates = tuple(bound for bound in (current, base) if bound is not None)
        if not candidates:
            message = f"captured path has no current or base-side source identity: {relative}"
            raise RuntimeError(message)
        bounds[relative] = max(candidates)
    return bounds


@timed_phase("repository_state")
def _repository_state_snapshot(*, git: str, repo: Path, head: str, branch: str, captured_paths: Sequence[str]) -> tuple[str, dict[str, str], str, list[str]]:
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
        algorithm = _decode(_run_git(git, repo, ("rev-parse", "--show-object-format")))
        path_fingerprints[relative] = _update_worktree_path(path_digest, git, repo, relative, algorithm)
    return digest.hexdigest(), path_fingerprints, hashlib.sha256(index_entries).hexdigest(), sorted(set(tracked) | set(untracked))


@timed_phase("scope_capture")
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
    branch = _decode(branch_bytes) if branch_bytes is not None else ""
    untracked_arguments = _with_paths(("ls-files", "--others", "--exclude-standard", "-z"), pathspecs)
    selected_untracked = _decode_zlist(_run_git(git, repo, untracked_arguments))

    base_ref: str | None = None
    merge_base: str | None = None

    if mode == "branch":
        base_ref = _resolve_base(git, repo, base)
        merge_base = _decode(_run_git(git, repo, ("merge-base", "HEAD", base_ref)))
        paths = _diff_paths(repo, pathspecs, base=merge_base)
        paths.extend(selected_untracked)
    elif mode == "staged":
        paths = _diff_paths(repo, pathspecs, base="HEAD", cached=True)
        selected_untracked = []
    elif mode == "worktree":
        paths = _diff_paths(repo, pathspecs, base="HEAD")
        paths.extend(selected_untracked)
    elif mode == "baseline":
        path_arguments = _with_paths(("ls-files", "-z"), pathspecs)
        paths = _decode_zlist(_run_git(git, repo, path_arguments))
        # Staged deletions disappear from ls-files but remain part of a repair.
        paths.extend(_decode_zlist(_run_git(git, repo, _with_paths(("ls-tree", "--name-only", "-r", "-z", head), pathspecs))))
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

    captured_worktree_paths = _diff_paths(repo, pathspecs, base="HEAD")
    captured_worktree_paths.extend(_decode_zlist(_run_git(git, repo, untracked_arguments)))
    captured_worktree_fingerprint = _worktree_fingerprint(
        git=git,
        identity=(("head", head.encode()), ("mode", b"worktree"), ("base-ref", b""), ("merge-base", b"")),
        pathspecs=pathspecs,
        paths=captured_worktree_paths,
        repo=repo,
    )
    status = _status(repo, pathspecs)
    repository_state_fingerprint, repository_path_fingerprints, index_fingerprint, selection_paths = _repository_state_snapshot(
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
        "repository_selection_paths": selection_paths,
        # Symlink hashes bind link text, not bytes read through the link. Record
        # traversal separately so later proof replay never consults the live tree.
        "repository_symlink_paths": [
            relative
            for relative in sorted(repository_path_fingerprints)
            if any((repo / component).is_symlink() for component in (Path(relative), *Path(relative).parents) if component != Path())
        ],
        "repository_state_fingerprint": repository_state_fingerprint,
        "repository_state_format": SNAPSHOT_FORMAT,
        "requested_paths": list(pathspecs),
        "scope_fingerprint": scope_fingerprint,
        "status": status,
        "untracked_paths": selected_untracked,
    }
    snapshot = source_snapshot(manifest)
    manifest["repository_git_tree_id"] = snapshot.git_tree_id
    manifest["repository_state_fingerprint"] = snapshot.computed_fingerprint()
    return manifest


def _committed_tree(git: str, repo: Path, revision: str) -> dict[str, GitPathIdentity]:
    """Read immutable tree entries using their repository's object format."""
    algorithm = _decode(_run_git(git, repo, ("rev-parse", "--show-object-format")))
    entries = {}
    for record in _run_git(git, repo, ("ls-tree", "-r", "-z", revision)).split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            mode, _kind, object_id = metadata.split()
            entries[os.fsdecode(path)] = GitPathIdentity(algorithm, mode.decode(), object_id.decode())
    return entries


def _committed_gitlink(git: str, repo: Path, relative: str, identity: GitPathIdentity) -> tuple[str, str | None]:
    """Reconstruct a clean gitlink identity from the parent's immutable commit."""
    index_entry = f"160000 {identity.object_id} 0\t".encode() + os.fsencode(relative) + b"\0"
    path = repo / relative
    if not path.exists() or (path.is_dir() and not any(path.iterdir())):
        return "submodule:" + hashlib.sha256(index_entry).hexdigest(), None
    # A different checkout can lack the target commit. It cannot prove clean.
    if not path.is_dir() or _try_git(git, path, ("cat-file", "-e", f"{identity.object_id}^{{commit}}")) is None:
        return identity.serialize(), None
    entries = _committed_tree(git, path, identity.object_id)
    index_entries = b"".join(f"{entry.mode} {entry.object_id} 0\t".encode() + os.fsencode(name) + b"\0" for name, entry in entries.items())
    digest = hashlib.sha256()
    for label, value in (("head", identity.object_id.encode()), ("index-entries", index_entries), ("mode", b"submodule-worktree")):
        _update_part(digest, label, value)
    _update_part(digest, "requested-paths", b"[]")
    for name in sorted(entries):
        entry = entries[name]
        _update_part(digest, "path", os.fsencode(name))
        if entry.mode == "160000":
            _nested_identity, nested = _committed_gitlink(git, path, name, entry)
            if nested is None and (path / name / ".git").exists():
                return identity.serialize(), None
            _update_part(digest, "mode", b"160000" if nested is not None else b"160000-unchecked-out")
            _update_part(digest, "gitlink-index", f"160000 {entry.object_id} 0\t".encode() + os.fsencode(name) + b"\0")
            if nested is not None:
                _update_part(digest, "gitlink-worktree", nested.encode())
        else:
            _update_part(digest, "mode", entry.mode.encode())
            _update_part(digest, "git-object", entry.serialize().encode())
    clean = digest.hexdigest()
    return "submodule:" + hashlib.sha256(index_entry + clean.encode()).hexdigest(), clean


def captured_head_changes(git: str, repo: Path, manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Compare captured raw identities with immutable HEAD, bypassing clean filters."""
    snapshot = source_snapshot(dict(manifest))
    captured_paths = set(snapshot.captured_scope_paths)
    committed = {
        path: _committed_gitlink(git, repo, path, identity)[0] if identity.mode == "160000" else identity.serialize()
        for path, identity in _committed_tree(git, repo, manifest["head"]).items()
        if path in captured_paths
    }
    fingerprints = dict(snapshot.repository_path_fingerprints)
    return tuple(path for path in snapshot.captured_scope_paths if fingerprints[path] != committed.get(path, "absent"))


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path inside the Git repository")
    parser.add_argument("--mode", choices=("branch", "staged", "worktree", "baseline"), default="branch", help="Review scope to fingerprint")
    parser.add_argument("--base", help="Explicit base ref for branch mode")
    parser.add_argument("--path", action="append", default=[], help="Repository-relative or absolute path boundary; repeat for multiple paths")
    parser.add_argument("--output", type=Path, help="Atomically save the complete capture outside the repository and print a compact receipt")
    parser.add_argument("--timings", action="store_true", help="Write inclusive phase/Git timings to stderr, separately from source evidence")
    return parser


@timed_phase("persistence")
def persist_capture(manifest: dict[str, Any], output: Path) -> dict[str, Any]:
    """Persist immutable capture bytes before returning all observed fingerprints."""
    from review_graph_runtime import _write_bytes_atomically_once  # noqa: PLC0415 - shared durable artifact writer, loaded only for persistence.

    snapshot = source_snapshot(manifest)
    snapshot.verify()
    path = output.absolute()
    if path.resolve() != path or path.is_relative_to(Path(snapshot.repository_root)):
        msg = "capture output must be an absolute external artifact path without symlinks"
        raise ValueError(msg)
    content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    receipt = {
        "schema_version": 1,
        "capture_path": str(path),
        "capture_digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "scope_fingerprint": snapshot.scope_fingerprint,
        "captured_worktree_fingerprint": snapshot.captured_worktree_fingerprint,
        "repository_state_fingerprint": snapshot.repository_state_fingerprint,
    }
    _write_bytes_atomically_once(path, content, mode=0o444)
    _write_bytes_atomically_once(path.with_suffix(".receipt.json"), (json.dumps(receipt, sort_keys=True) + "\n").encode(), mode=0o444)
    return receipt


def main() -> int:
    """Print the captured review scope as JSON."""
    from review_graph_session import verify_current_snapshot  # noqa: PLC0415 - verify frozen resources before parsing the command.

    with collect_timings() as timing:
        code = 1
        try:
            with phase("runtime_verification"):
                verify_current_snapshot()
            arguments = _parser().parse_args()
            code = _capture_main(arguments)
            return code
        except SystemExit as error:
            code = error.code if isinstance(error.code, int) else int(error.code is not None)
            raise
        finally:
            if "--timings" in sys.argv[1:]:
                print(json.dumps(timing.as_raw(code), sort_keys=True), file=sys.stderr)


def _capture_main(arguments: argparse.Namespace) -> int:
    """Capture and publish only successful observations."""
    git = shutil.which("git")
    if git is None:
        print("capture_scope.py: git is unavailable", file=sys.stderr)
        return 2

    try:
        requested_repo = Path(os.path.abspath(arguments.repo))  # noqa: PTH100 - preserve a user-provided symlink alias for path translation.
        with phase("git_discovery"):
            root = Path(_decode(_run_git(git, requested_repo, ("rev-parse", "--show-toplevel"))))
            pathspecs = _normalize_pathspecs(root, requested_repo, arguments.path)
        manifest = _scope_data(git, root, arguments.mode, arguments.base, pathspecs)
        result = persist_capture(manifest, arguments.output) if arguments.output is not None else manifest
    except (ExecutableNotFoundError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"capture_scope.py: {format_exception_diagnostics(error)}", file=sys.stderr)
        return 2

    with phase("serialization"):
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
