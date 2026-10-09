"""Semantic Git dependencies and content-equivalent staging decisions."""

import re
import shlex
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from review_graph_reuse import ExternalMetadataTransition

_DIFF_OPTIONS = frozenset(
    {
        "--cached",
        "--staged",
        "--stat",
        "--numstat",
        "--shortstat",
        "--name-only",
        "--name-status",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--patch",
        "--raw",
        "--summary",
        "--check",
        "--exit-code",
        "--quiet",
        "--binary",
        "--full-index",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "-p",
        "-s",
        "-U0",
        "-z",
        "HEAD",
    }
)


def _source_discovery_command(command: str) -> bool:
    """Recognize plain local diffs; never interpret arbitrary shell or Git options."""
    if re.search(r"[;&|`$\n<>]", command):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    if words[:2] == ["git", "--no-pager"]:
        words.pop(1)
    if words[:2] != ["git", "diff"]:
        return False
    args = words[2:]
    boundary = args.index("--") if "--" in args else len(args)
    return all(arg in _DIFF_OPTIONS or re.fullmatch(r"(?:-U|--unified=)\d+", arg) for arg in args[:boundary]) and all(
        path and not PurePosixPath(path).is_absolute() and ".." not in PurePosixPath(path).parts and not path.startswith(":") for path in args[boundary + 1 :]
    )


def validate_git_dependencies(payload: dict[str, Any]) -> None:
    """Check semantic declarations against the actual command ledger after schema validation."""
    commands = payload.get("commands_executed", [])
    declared: set[str] = set()
    for dependency in payload.get("git_dependencies", []):
        command = dependency.get("command")
        if not dependency["reason"].strip():
            msg = "git_dependencies require a substantive reason"
            raise ValueError(msg)
        if command is not None:
            if command not in commands or command in declared:
                msg = "git_dependencies commands must occur exactly once in declarations and match commands_executed"
                raise ValueError(msg)
            declared.add(command)
        if dependency["kind"] == "source-discovery" and (command is None or not _source_discovery_command(command)):
            msg = (
                "source-discovery requires a plain local git diff command (optional HEAD, --cached/--staged, and -- relative/path); "
                "split compound invocations into separate command ledger entries. For a branch/revision diff such as git diff origin/main, "
                "declare kind=head with the exact executed command and a reason; use index/history for those semantic dependencies"
            )
            raise ValueError(msg)


def git_dependency_blockers(record: dict[str, Any]) -> list[dict[str, str]]:
    """Explain every metadata-sensitive judgment or unclassified executed command."""
    blockers: list[dict[str, str]] = []
    if record.get("git_sensitive", False):
        blockers.append({"reason_code": "legacy-git-sensitive", "dependency": "git_sensitive", "reason": "The audit explicitly depends on Git metadata."})
    declared = {dependency["command"] for dependency in record.get("git_dependencies", []) if "command" in dependency}
    blockers.extend(
        {"reason_code": "semantic-git-dependency", "dependency": dependency["kind"], **dependency}
        for dependency in record.get("git_dependencies", [])
        if dependency["kind"] != "source-discovery"
    )
    blockers.extend(
        {"reason_code": "unclassified-command", "command": command, "reason": "The command has no verified source-only dependency classification."}
        for command in record.get("commands_executed", [])
        if command not in declared and (not re.match(r"^(?:cat|rg|head|tail|wc|ls)\s", command) or re.search(r"[;&|`$\n]|\bgit\b|--pre", command))
    )
    return blockers


def audit_git_context(record: dict[str, Any]) -> dict[str, Any]:
    """Retain audit-wide dependencies; no unit-specific Git attribution exists."""
    return {key: record[key] for key in ("git_sensitive", "git_dependencies", "commands_executed") if record.get(key)}


def _inherited_metadata_context(record: dict[str, Any]) -> dict[str, Any] | None:
    context = record.get("coverage_reuse")
    if not context:
        return None
    units = [unit for unit in context["units"] if unit["disposition"] == "reused"]
    return {
        **context.get("original_git_context", {}),
        "evidence_id": context["evidence_id"],
        "files_inspected": sorted({path for unit in units for path in unit["owned_paths"]}),
        "nearby_contract_owners": sorted({path for unit in units for path in unit["dependency_paths"]}),
    }


def _metadata_context_blockers(record: dict[str, Any], transition: ExternalMetadataTransition) -> list[dict[str, str]]:
    blockers = git_dependency_blockers(record)
    paths = set(record.get("files_inspected", [])) | set(record.get("nearby_contract_owners", []))
    before = dict(transition.before.repository_path_fingerprints)
    after = dict(transition.after.repository_path_fingerprints)
    root = PurePosixPath(transition.before.repository_root)
    for path in sorted(paths):
        relative = PurePosixPath(path)
        if relative.is_relative_to(root):
            relative = relative.relative_to(root)
        key = str(relative)
        if ".." in relative.parts or key not in before or before.get(key) != after.get(key):
            blockers.append({"reason_code": "unproven-source-read", "path": path, "reason": "The read is outside the unchanged captured path identities."})
        elif any(key in snapshot.repository_symlink_paths for snapshot in (transition.before, transition.after)):
            blockers.append({"reason_code": "unproven-source-read", "path": path, "reason": "The capture does not prove a read without symlink traversal."})
    return blockers


def metadata_audit_blockers(record: dict[str, Any], transition: ExternalMetadataTransition, *, fresh_current: bool = False) -> list[dict[str, str]]:
    """Check fresh and inherited judgments without presenting old reads as fresh."""
    blockers = [] if fresh_current else _metadata_context_blockers(record, transition)
    inherited = _inherited_metadata_context(record)
    if inherited is not None:
        blockers.extend({**blocker, "evidence_id": inherited["evidence_id"]} for blocker in _metadata_context_blockers(inherited, transition))
    return blockers


def intervening_metadata_blockers(record: dict[str, Any], transitions: tuple[ExternalMetadataTransition, ...]) -> list[dict[str, str]]:
    """Reject stale judgments when content reuse crosses a staging transition."""
    if not transitions:
        return []
    return metadata_audit_blockers(record, transitions[-1], fresh_current=tuple(record.get("observed_source_state", ())) == transitions[-1].after.source_state)


def discovery_reconciliation(record: dict[str, Any], transition: ExternalMetadataTransition) -> dict[str, Any]:
    """Bind discovery to the combined HEAD-to-worktree change, retaining the original commands."""
    return {
        "basis": "combined-staged-and-unstaged-content",
        "head": transition.after.head,
        "before_worktree_fingerprint": transition.before.captured_worktree_fingerprint,
        "after_worktree_fingerprint": transition.after.captured_worktree_fingerprint,
        "commands": [dependency["command"] for dependency in record.get("git_dependencies", []) if dependency["kind"] == "source-discovery"],
        "inspected_paths": record.get("files_inspected", []),
        "nearby_contract_owners": record.get("nearby_contract_owners", []),
        **(
            {"inherited": discovery_reconciliation(inherited, transition), "inherited_evidence_id": inherited["evidence_id"]}
            if (inherited := _inherited_metadata_context(record)) is not None
            else {}
        ),
    }
