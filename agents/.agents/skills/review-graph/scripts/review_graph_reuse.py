"""Content-bound capture identities and immutable audit reuse transitions."""

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, override

from research_repo_tools.evidence import sha256
from review_graph_git_objects import GitPathIdentity, git_object_id, source_tree_id
from review_graph_integrity import canonical_json
from review_graph_read_provenance import verify_runtime_inputs

SNAPSHOT_FORMAT = "review-graph-path-snapshot-v4"
WORKTREE_SELECTION_ALGORITHM = "git-ls-files-cached-others-exclude-standard-v1"


class ReuseInputError(ValueError):
    """Concrete read blockers retained in whole-audit and partition receipts."""

    def __init__(self, rejected_inputs: list[dict[str, str]]) -> None:
        """Name every unproved input and the required owning-audit action."""
        self.rejected_inputs = rejected_inputs
        detail = "; ".join(f"{item['classification']}: {item['path']}" for item in rejected_inputs)
        super().__init__(f"audit reuse input proof failed ({detail}); the owning audit needs fresh inspection")


def regular_file_fingerprint(path: str, content: bytes, *, executable: bool = False, algorithm: str = "sha1") -> str:
    """Reconstruct the captured native Git blob identity from retained bytes."""
    if not _repository_path(path):
        msg = "regular file identity requires a portable repository path"
        raise ValueError(msg)
    return GitPathIdentity(algorithm, "100755" if executable else "100644", git_object_id("blob", content, algorithm)).serialize()


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
    repository_symlink_paths: tuple[str, ...]

    @property
    def repository_selection_paths(self) -> tuple[str, ...] | None:
        """Historical v4 captures do not prove tracked/nonignored selection."""
        return None

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
        if self.repository_selection_paths is None:
            fields.pop("repository_selection_paths", None)  # Preserve historical v4 identities.
        return sha256(canonical_json(fields).encode("utf-8"))

    @property
    def git_tree_id(self) -> str | None:
        """Identify captured current source independently of branch/index metadata."""
        if any(path.startswith(link + "/") for path, _identity in self.repository_path_fingerprints for link in self.repository_symlink_paths):
            return None  # A tracked path reached through a symlink has no native Git tree representation.
        return source_tree_id(self.repository_path_fingerprints)

    def verify(self) -> None:
        """Reject unsupported or internally inconsistent capture identities."""
        if self.repository_state_format != SNAPSHOT_FORMAT:
            msg = "audit reuse requires a content-bound v4 source snapshot; recapture required"
            raise ValueError(msg)
        paths = tuple(path for path, _ in self.repository_path_fingerprints)
        if paths != tuple(sorted(set(paths))) or any(not _repository_path(path) for path in paths):
            msg = "source snapshot requires unique sorted canonical repository paths"
            raise ValueError(msg)
        selected = self.repository_selection_paths
        if selected is not None and (selected != tuple(sorted(set(selected))) or not set(selected) <= set(paths)):
            msg = "source snapshot selection requires unique sorted captured repository paths"
            raise ValueError(msg)
        symlinks = self.repository_symlink_paths
        if symlinks != tuple(sorted(set(symlinks))) or not set(symlinks) <= set(paths):
            msg = "source snapshot requires unique sorted captured symlink paths"
            raise ValueError(msg)
        hashes = (*self.source_state, self.index_fingerprint)
        if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in hashes):
            msg = "source snapshot requires SHA-256 identities"
            raise ValueError(msg)
        if self.repository_state_fingerprint != self.computed_fingerprint():
            msg = "source snapshot path identities do not match its repository fingerprint"
            raise ValueError(msg)
        for _path, identity in self.repository_path_fingerprints:
            if identity == "absent" or re.fullmatch(r"submodule:[0-9a-f]{64}", identity):
                continue
            GitPathIdentity.parse(identity)


@dataclass(frozen=True)
class WorktreeSelectionSnapshot(ReviewSourceSnapshot):
    """Add captured selection without changing historical snapshot serialization."""

    repository_selection_paths: tuple[str, ...] = ()


def source_snapshot(raw: dict[str, Any]) -> ReviewSourceSnapshot:
    """Parse a capture manifest or serialized snapshot without coercing values."""
    fields = dict(raw)
    for field in ("requested_paths", "captured_scope_paths", "repository_symlink_paths"):
        value = fields.get(field)
        if not isinstance(value, (list, tuple)) or any(not isinstance(path, str) for path in value):
            msg = f"source snapshot {field} must contain strings; recapture required"
            raise ValueError(msg)
        fields[field] = tuple(value)
    identities = fields.get("repository_path_fingerprints")
    pairs = tuple(identities.items()) if isinstance(identities, dict) else identities
    if not isinstance(pairs, (list, tuple)) or any(
        not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(not isinstance(value, str) for value in pair) for pair in pairs
    ):
        msg = "source snapshot repository_path_fingerprints requires path/digest pairs"
        raise ValueError(msg)
    fields["repository_path_fingerprints"] = tuple(sorted(tuple(pair) for pair in pairs))
    selected = fields.get("repository_selection_paths")
    if selected is not None and (not isinstance(selected, (list, tuple)) or any(not isinstance(path, str) for path in selected)):
        msg = "source snapshot repository_selection_paths must contain strings"
        raise ValueError(msg)
    for field in ReviewSourceSnapshot.__dataclass_fields__:
        if field in {"requested_paths", "captured_scope_paths", "repository_path_fingerprints", "repository_symlink_paths", "repository_selection_paths"}:
            continue
        value = fields.get(field)
        if not isinstance(value, str) and not (field in {"base_ref", "merge_base", "branch"} and value is None):
            msg = f"source snapshot {field} must be a string"
            raise ValueError(msg)
        fields[field] = value
    constructor = WorktreeSelectionSnapshot if selected is not None else ReviewSourceSnapshot
    if selected is not None:
        fields["repository_selection_paths"] = tuple(selected)
    return constructor(**{field: fields[field] for field in constructor.__dataclass_fields__})


@dataclass(frozen=True)
class AuditInputIdentity:
    """Compiler-bound ownership, inspected dependencies, and loaded instructions."""

    owned_paths: tuple[str, ...]
    inspected_paths: tuple[str, ...]
    nearby_contract_owners: tuple[str, ...]
    instruction_digests: tuple[tuple[str, str], ...]
    retained_inputs: tuple[tuple[str, str], ...] = ()
    runtime_inputs: tuple[tuple[str, str], ...] = ()
    protocol_commands: tuple[str, ...] = ()
    command_read_paths: tuple[str, ...] = ()


def audit_inputs_document(inputs: AuditInputIdentity) -> dict[str, Any]:
    """Keep legacy evidence serialization unchanged when no text was retained."""
    document = asdict(inputs)
    if not inputs.retained_inputs:
        document.pop("retained_inputs")
    for field in ("runtime_inputs", "protocol_commands", "command_read_paths"):
        if not getattr(inputs, field):
            document.pop(field)
    return document


@dataclass(frozen=True)
class ExternalMetadataTransition:
    """Observed external staging, retaining both complete captures unchanged."""

    before: ReviewSourceSnapshot
    after: ReviewSourceSnapshot

    def verify(self) -> None:
        """Permit branch/index metadata changes with identical source and comparison."""
        self.before.verify()
        self.after.verify()
        if self.before.capture_mode not in {"baseline", "worktree", "branch", "staged"}:
            msg = "external metadata resume requires a supported captured scope"
            raise ValueError(msg)
        before, after = asdict(self.before), asdict(self.after)
        for field in ("branch", "index_fingerprint", "repository_state_fingerprint"):
            before.pop(field)
            after.pop(field)
        if before != after or (self.before.branch, self.before.index_fingerprint) == (self.after.branch, self.after.index_fingerprint):
            msg = "external metadata transition must change only the index or branch, preserving all content, modes, scope, instructions, HEAD, and base"
            raise ValueError(msg)


@dataclass(frozen=True)
class AuthorizedGitContextTransition(ExternalMetadataTransition):
    """An authorized externally performed commit/rebase with identical source."""

    git_context_authorization: str

    @override
    def verify(self) -> None:
        """Separate source equality from changed HEAD, branch and comparison state."""
        self.before.verify()
        self.after.verify()
        if "staged" in (self.before.capture_mode, self.after.capture_mode):
            msg = "authorized Git context handoff cannot preserve staged capture scopes; replan from the new capture"
            raise ValueError(msg)
        if not isinstance(self.git_context_authorization, str) or not self.git_context_authorization.strip():
            msg = "changed Git context requires explicit user authorization"
            raise ValueError(msg)
        before, after = self.before, self.after

        def identity(snapshot: ReviewSourceSnapshot) -> tuple[object, ...]:
            return (
                snapshot.repository_root,
                snapshot.capture_mode,
                snapshot.requested_paths,
                snapshot.captured_scope_paths,
                snapshot.base_ref,
                snapshot.merge_base,
                snapshot.git_tree_id,
                snapshot.repository_symlink_paths,
            )

        if before.git_tree_id is None or identity(before) != identity(after) or before.source_state == after.source_state:
            msg = (
                "authorized Git context handoff requires identical complete source tree, scope and comparison boundary; "
                "changed review scope/base requires replanning"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class CommitHandoffTransition(ExternalMetadataTransition):
    """An authorized commit of reviewed bytes, with immutable reconciliation proof."""

    commit_handoff: dict[str, Any]

    @override
    def verify(self) -> None:
        """Verify the separate commit contract without relaxing index-only resumes."""
        from review_graph_commit import verify_commit_transition  # noqa: PLC0415 - avoid the snapshot type import cycle.

        self.before.verify()
        self.after.verify()
        verify_commit_transition(self)


def metadata_transition(raw: dict[str, Any]) -> ExternalMetadataTransition:
    """Parse and verify an externally observed metadata transition."""
    if not isinstance(raw, dict) or any(not isinstance(raw.get(field), dict) for field in ("before", "after")):
        msg = "external metadata transition requires before and after snapshot objects"
        raise ValueError(msg)
    before, after = source_snapshot(raw["before"]), source_snapshot(raw["after"])
    result: ExternalMetadataTransition
    if "commit_handoff" in raw:
        result = CommitHandoffTransition(before, after, raw["commit_handoff"])
    elif "git_context_authorization" in raw:
        authorization = raw["git_context_authorization"]
        if not isinstance(authorization, str):
            msg = "Git context authorization must be text"
            raise TypeError(msg)
        result = AuthorizedGitContextTransition(before, after, authorization)
    else:
        result = ExternalMetadataTransition(before, after)
    result.verify()
    return result


def metadata_states(origin: tuple[str, str, str], transitions: tuple[ExternalMetadataTransition, ...]) -> tuple[tuple[str, str, str], ...]:
    """Follow a verified chain without relabeling any historical source triple."""
    states = [origin]
    for transition in transitions:
        transition.verify()
        if transition.before.source_state != states[-1]:
            msg = "external metadata transitions do not form a chain from the reviewed source"
            raise ValueError(msg)
        states.append(transition.after.source_state)
    return tuple(states)


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
    metadata_transitions: tuple[ExternalMetadataTransition, ...] = ()


def verify_reuse_inputs(  # noqa: C901 - fail-closed source, metadata, instruction and dependency proof.
    origin: ReviewSourceSnapshot,
    target: ReviewSourceSnapshot,
    inputs: AuditInputIdentity,
    transition: AuditReuseTransition,
    *,
    instruction_delta_paths: frozenset[str] = frozenset(),
) -> None:
    """Prove unchanged review inputs across two independently bound captures."""
    origin.verify()
    target.verify()
    metadata_states(origin.source_state, transition.metadata_transitions)
    boundary = transition.metadata_transitions[-1].after.boundary if transition.metadata_transitions else origin.boundary
    if origin.source_state != transition.source_state or target.source_state != transition.target_state or boundary != target.boundary:
        msg = "audit reuse changes source identity, capture boundary, or Git state"
        raise ValueError(msg)
    if not inputs.owned_paths or set(inputs.inspected_paths) != set(inputs.owned_paths):
        msg = "audit reuse requires complete inspection of the owned surface"
        raise ValueError(msg)
    root = PurePosixPath(origin.repository_root)
    old_instructions, new_instructions = dict(inputs.instruction_digests), dict(transition.instruction_digests)
    if instruction_delta_paths.intersection(inputs.owned_paths):
        msg = "instruction reconciliation cannot waive changed owned source"
        raise ValueError(msg)
    changed_instructions = {path for path in old_instructions.keys() | new_instructions.keys() if old_instructions.get(path) != new_instructions.get(path)}
    allowed_instructions = {str(root / path) for path in instruction_delta_paths}
    paths = {*inputs.owned_paths, *inputs.inspected_paths, *inputs.nearby_contract_owners, *inputs.command_read_paths}
    for binding in inputs.runtime_inputs:
        try:
            verify_runtime_inputs((binding,), origin.repository_root)
        except (OSError, ValueError) as error:
            raise ReuseInputError([{"path": binding[0], "classification": "invalid-frozen-runtime-binding"}]) from error
    paths.difference_update(path for path, _digest in inputs.runtime_inputs)
    paths = {str(PurePosixPath(path).relative_to(root)) if PurePosixPath(path).is_relative_to(root) else path for path in paths}
    for path, _digest_value in inputs.instruction_digests:
        instruction = PurePosixPath(path)
        if instruction.is_relative_to(root):
            paths.add(instruction.relative_to(root).as_posix())
    rejected = [
        {
            "path": path,
            "classification": "missing-frozen-runtime-binding"
            if path in old_instructions
            else "unbound-external-source"
            if PurePosixPath(path).is_absolute()
            else "invalid-repository-path",
        }
        for path in sorted(paths)
        if not _repository_path(path)
    ]
    if rejected:
        raise ReuseInputError(rejected)
    if list(old_instructions) != list(new_instructions) or changed_instructions - allowed_instructions:
        msg = "audit reuse instruction identities changed"
        raise ValueError(msg)
    before = dict(origin.repository_path_fingerprints)
    after = dict(target.repository_path_fingerprints)
    if any(path not in before or path not in after or (before[path] != after[path] and path not in instruction_delta_paths) for path in paths):
        msg = "audit reuse inspected paths or dependencies changed or are not captured"
        raise ValueError(msg)
    if any(paths.intersection(snapshot.repository_symlink_paths) for snapshot in (origin, target)):
        msg = "audit reuse requires captured proof that inspected paths do not traverse symlinks"
        raise ValueError(msg)
    changed_instructions = (path for path in before.keys() | after.keys() if PurePosixPath(path).name == "AGENTS.md" and before.get(path) != after.get(path))
    if any(
        path not in instruction_delta_paths and any(PurePosixPath(owned).is_relative_to(PurePosixPath(path).parent) for owned in inputs.owned_paths)
        for path in changed_instructions
    ):
        msg = "audit reuse applicable repository instructions changed"
        raise ValueError(msg)
