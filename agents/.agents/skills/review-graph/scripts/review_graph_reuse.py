"""Content-bound capture identities and immutable audit reuse transitions."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any

SNAPSHOT_FORMAT = "review-graph-path-snapshot-v2"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _repository_path(path: str) -> bool:
    return bool(path) and not path.startswith("/") and "\\" not in path and PurePosixPath(path).as_posix() == path and not {"..", "."} & set(path.split("/"))


@dataclass(frozen=True)
class ReviewSourceSnapshot:
    """A capture whose repository fingerprint commits to its path identities."""

    repository_state_format: str
    repository_root: str
    capture_mode: str
    head: str
    branch: str | None
    base_ref: str | None
    merge_base: str | None
    requested_paths: tuple[str, ...]
    captured_scope_paths: tuple[str, ...]
    scope_fingerprint: str
    captured_worktree_fingerprint: str
    repository_state_fingerprint: str
    index_fingerprint: str
    repository_path_fingerprints: tuple[tuple[str, str], ...]

    @property
    def source_state(self) -> tuple[str, str, str]:
        """Return the same source triple used by review evidence."""
        return self.scope_fingerprint, self.captured_worktree_fingerprint, self.repository_state_fingerprint

    @property
    def boundary(self) -> tuple[object, ...]:
        """Return identities that a source-only repair must preserve."""
        return self.repository_root, self.capture_mode, self.head, self.branch, self.base_ref, self.merge_base, self.requested_paths, self.index_fingerprint

    def computed_fingerprint(self) -> str:
        """Bind capture context and the complete repository path map."""
        fields = asdict(self)
        fields.pop("repository_state_fingerprint")
        return _digest(fields)

    def verify(self) -> None:
        """Reject unsupported or internally inconsistent capture identities."""
        if self.repository_state_format != SNAPSHOT_FORMAT:
            msg = "audit reuse requires a content-bound v2 source snapshot"
            raise ValueError(msg)
        paths = tuple(path for path, _ in self.repository_path_fingerprints)
        if paths != tuple(sorted(set(paths))) or any(not _repository_path(path) for path in paths):
            msg = "source snapshot requires unique sorted canonical repository paths"
            raise ValueError(msg)
        hashes = (*self.source_state, self.index_fingerprint, *(digest for _, digest in self.repository_path_fingerprints))
        if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in hashes):
            msg = "source snapshot requires SHA-256 identities"
            raise ValueError(msg)
        if self.repository_state_fingerprint != self.computed_fingerprint():
            msg = "source snapshot path identities do not match its repository fingerprint"
            raise ValueError(msg)


def source_snapshot(raw: dict[str, Any]) -> ReviewSourceSnapshot:
    """Parse a capture manifest or serialized snapshot without coercing values."""
    fields = dict(raw)
    for field in ("requested_paths", "captured_scope_paths"):
        value = fields.get(field)
        if not isinstance(value, (list, tuple)) or any(not isinstance(path, str) for path in value):
            msg = f"source snapshot {field} must contain strings"
            raise ValueError(msg)
        fields[field] = tuple(value)
    identities = fields.get("repository_path_fingerprints")
    pairs = tuple(identities.items()) if isinstance(identities, dict) else identities
    if not isinstance(pairs, (list, tuple)) or any(
        not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(not isinstance(value, str) for value in pair) for pair in pairs
    ):
        msg = "source snapshot requires path/digest pairs"
        raise ValueError(msg)
    fields["repository_path_fingerprints"] = tuple(sorted(tuple(pair) for pair in pairs))
    for field in ReviewSourceSnapshot.__dataclass_fields__:
        if field in {"requested_paths", "captured_scope_paths", "repository_path_fingerprints"}:
            continue
        value = fields.get(field)
        if not isinstance(value, str) and not (field in {"base_ref", "merge_base", "branch"} and value is None):
            msg = f"source snapshot {field} must be a string"
            raise ValueError(msg)
        fields[field] = value
    return ReviewSourceSnapshot(**{field: fields[field] for field in ReviewSourceSnapshot.__dataclass_fields__})


@dataclass(frozen=True)
class AuditInputIdentity:
    """Compiler-bound ownership, inspected dependencies, and loaded instructions."""

    owned_paths: tuple[str, ...]
    inspected_paths: tuple[str, ...]
    nearby_contract_owners: tuple[str, ...]
    instruction_digests: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AuditReuseTransition:
    """A non-executable claim retaining the original artifact and source state."""

    evidence_id: str
    source_state: tuple[str, str, str]
    target_state: tuple[str, str, str]
    artifact_digest: str
    artifact_path: str
    metadata_path: str
    instruction_digests: tuple[tuple[str, str], ...]


def verify_reuse_inputs(origin: ReviewSourceSnapshot, target: ReviewSourceSnapshot, inputs: AuditInputIdentity, transition: AuditReuseTransition) -> None:
    """Prove unchanged review inputs across two independently bound captures."""
    origin.verify()
    target.verify()
    if origin.source_state != transition.source_state or target.source_state != transition.target_state or origin.boundary != target.boundary:
        msg = "audit reuse changes source identity, capture boundary, or Git state"
        raise ValueError(msg)
    if not inputs.owned_paths or set(inputs.inspected_paths) != set(inputs.owned_paths):
        msg = "audit reuse requires complete inspection of the owned surface"
        raise ValueError(msg)
    if inputs.instruction_digests != transition.instruction_digests:
        msg = "audit reuse instruction identities changed"
        raise ValueError(msg)
    paths = {*inputs.owned_paths, *inputs.inspected_paths, *inputs.nearby_contract_owners}
    root = PurePosixPath(origin.repository_root)
    for path, _digest_value in inputs.instruction_digests:
        instruction = PurePosixPath(path)
        if instruction.is_relative_to(root):
            paths.add(instruction.relative_to(root).as_posix())
    if any(not _repository_path(path) for path in paths):
        msg = "audit reuse dependencies must be concrete repository-relative paths"
        raise ValueError(msg)
    before = dict(origin.repository_path_fingerprints)
    after = dict(target.repository_path_fingerprints)
    if any(path not in before or path not in after or before[path] != after[path] for path in paths):
        msg = "audit reuse inspected paths or dependencies changed or are not captured"
        raise ValueError(msg)
    changed_instructions = (path for path in before.keys() | after.keys() if PurePosixPath(path).name == "AGENTS.md" and before.get(path) != after.get(path))
    if any(any(PurePosixPath(owned).is_relative_to(PurePosixPath(path).parent) for owned in inputs.owned_paths) for path in changed_instructions):
        msg = "audit reuse applicable repository instructions changed"
        raise ValueError(msg)
