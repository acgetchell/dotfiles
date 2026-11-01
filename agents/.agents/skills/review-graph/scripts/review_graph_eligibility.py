"""Early advisory diagnostics; only a later source comparison can prove reuse."""

from collections import Counter
from pathlib import Path
from typing import Any

from review_graph_git import git_dependency_blockers
from review_graph_reads import source_read_operands


def reuse_eligibility(record: dict[str, Any], repository: str) -> dict[str, Any]:
    """Name command and external-read blockers without rewriting submitted facts."""
    blockers: list[dict[str, Any]] = list(git_dependency_blockers(record))
    commands = record.get("commands_executed", [])
    for blocker in blockers:
        if "command" in blocker:
            blocker["command_entries"] = [index for index, command in enumerate(commands, 1) if command == blocker["command"]]
    reads = {*record.get("files_inspected", []), *record.get("nearby_contract_owners", [])}
    reads.update(path for command in commands for path in source_read_operands(command) or ())
    reads.update(path for unit in record.get("coverage_units", []) for path in unit.get("dependency_paths", []))
    bindings = dict(record.get("runtime_inputs", []))
    root = Path(repository)
    for path in sorted(reads - bindings.keys()):
        target = root / path
        if ".." in Path(path).parts or not target.is_relative_to(root):
            blockers.append({"reason_code": "unbound-external-read", "path": path})
    return {
        "status": "blocked" if blockers else "no-known-ledger-blockers",
        "scope": "command classification and external read bindings only; reuse still requires unchanged captured inputs and complete, certain coverage",
        "blocker_count": len(blockers),
        "reason_counts": dict(sorted(Counter(item["reason_code"] for item in blockers).items())),
        "blockers": blockers,
    }


def compact_eligibility(diagnostic: dict[str, Any]) -> dict[str, Any]:
    """Bound receipt size while retaining exact entries in the linked artifact."""
    samples = [{key: value[:240] if isinstance(value, str) else value for key, value in blocker.items()} for blocker in diagnostic["blockers"][:8]]
    return {**diagnostic, "blockers": samples, "omitted_blockers": max(0, diagnostic["blocker_count"] - len(samples))}
