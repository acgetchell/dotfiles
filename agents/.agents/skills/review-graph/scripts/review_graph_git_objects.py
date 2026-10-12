"""Git object identities for captured source, without changing the object store."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass


def git_object_id(kind: str, content: bytes, algorithm: str) -> str:
    """Use Git's object framing and the repository's object-format algorithm."""
    if kind not in {"blob", "tree"} or algorithm not in {"sha1", "sha256"}:
        msg = "Git source identity requires blob/tree and sha1/sha256"
        raise ValueError(msg)
    return hashlib.new(algorithm, f"{kind} {len(content)}\0".encode() + content, usedforsecurity=False).hexdigest()


@dataclass(frozen=True, slots=True)
class GitPathIdentity:
    """A parsed Git mode and object ID with an explicit object format."""

    algorithm: str
    mode: str
    object_id: str

    def __post_init__(self) -> None:
        """Keep object-format, mode, and hexadecimal length consistent."""
        length = {"sha1": 40, "sha256": 64}.get(self.algorithm)
        if length is None or self.mode not in {"100644", "100755", "120000", "160000"} or re.fullmatch(f"[0-9a-f]{{{length}}}", self.object_id) is None:
            msg = "Git path identity requires a supported object format, mode, and matching object ID"
            raise ValueError(msg)

    @classmethod
    def parse(cls, raw: str) -> GitPathIdentity:
        """Parse the versioned capture's native object identity."""
        fields = raw.split(":")
        if len(fields) != 4 or fields[0] != "git":
            msg = "Git path identity must be git:<algorithm>:<mode>:<object-id>"
            raise ValueError(msg)
        return cls(fields[1], fields[2], fields[3])

    def serialize(self) -> str:
        """Export the standard capture transport representation."""
        return f"git:{self.algorithm}:{self.mode}:{self.object_id}"


def source_tree_id(paths: tuple[tuple[str, str], ...]) -> str | None:
    """Derive a native Git tree ID for captured worktree entries without writing it."""
    entries: dict[str, GitPathIdentity] = {}
    for path, identity in paths:
        if identity == "absent":
            continue
        if not identity.startswith("git:"):
            return None  # Dirty/unavailable submodules retain their stronger captured identity.
        entries[path] = GitPathIdentity.parse(identity)
    algorithms = {entry.algorithm for entry in entries.values()}
    if len(algorithms) != 1:
        return None
    algorithm = algorithms.pop()

    return f"git:{algorithm}:tree:{_tree_id(entries, '', algorithm)}"


def _tree_id(entries: dict[str, GitPathIdentity], prefix: str, algorithm: str) -> str:
    children: dict[str, tuple[str, str]] = {}
    for path, entry in entries.items():
        if not path.startswith(prefix):
            continue
        tail = path.removeprefix(prefix)
        name, separator, _rest = tail.partition("/")
        child = ("40000", "") if separator else (entry.mode, entry.object_id)
        if name in children and children[name] != child:
            msg = "Git tree contains a file/directory path collision"
            raise ValueError(msg)
        children[name] = child
    parts = []
    for name, (mode, oid) in sorted(children.items(), key=lambda item: os.fsencode(item[0] + ("/" if item[1][0] == "40000" else ""))):
        object_id = _tree_id(entries, prefix + name + "/", algorithm) if mode == "40000" else oid
        parts.append(mode.encode() + b" " + os.fsencode(name) + b"\0" + bytes.fromhex(object_id))
    return git_object_id("tree", b"".join(parts), algorithm)
