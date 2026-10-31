"""Account for captured files separately from semantic specialist routing closure."""

from pathlib import PurePosixPath
from typing import Any, cast

from review_graph_integrity import digest_json


def _disposition(item: Any, selected_catalog_ids: set[str]) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != {"paths", "disposition", "reason", "catalog_ids"}:
        msg = "captured_path_dispositions entries require paths, disposition, reason, and catalog_ids"
        raise ValueError(msg)
    if item["disposition"] not in ("dependency", "historical", "archive", "user-excluded"):
        msg = "captured_path_dispositions disposition must be dependency, historical, archive, or user-excluded"
        raise ValueError(msg)
    if not isinstance(item["reason"], str) or not item["reason"].strip():
        msg = "captured_path_dispositions require a nonblank semantic reason"
        raise ValueError(msg)
    owners = item["catalog_ids"]
    if not isinstance(owners, list) or any(not isinstance(owner, str) or owner not in selected_catalog_ids for owner in owners):
        msg = "captured_path_dispositions catalog_ids must identify selected audit leaves (including exactly reused leaves)"
        raise ValueError(msg)
    if len(owners) != len(set(owners)) or (item["disposition"] == "dependency" and not owners):
        msg = "dependency dispositions require distinct selected audit catalog_ids"
        raise ValueError(msg)
    if item["disposition"] != "dependency" and owners:
        msg = "only dependency dispositions may name audit catalog_ids"
        raise ValueError(msg)
    return {**item, "catalog_ids": sorted(owners)}


def captured_path_inventory(
    captured_paths: tuple[str, ...], owned_paths: dict[str, tuple[str, ...]], selected_catalog_ids: set[str], dispositions: Any
) -> dict[str, Any]:
    """Require explicit assessments for files outside selected or exactly reused audits.

    Ownership comes only from leaf review surfaces. Instructions, dependency reads,
    validators, routers, and synthesis do not establish owned coverage.
    """
    captured = set(captured_paths)
    assigned = {path for paths in owned_paths.values() for path in paths}
    unassigned = captured - assigned
    if not isinstance(dispositions, list):
        msg = "captured_path_dispositions must be an array"
        raise TypeError(msg)
    assessed: set[str] = set()
    records = []
    for raw in dispositions:
        item = _disposition(raw, selected_catalog_ids)
        paths = item["paths"]
        if (
            not isinstance(paths, list)
            or not paths
            or any(not isinstance(path, str) or not path or PurePosixPath(path).as_posix() != path or path not in captured for path in paths)
        ):
            msg = "captured_path_dispositions paths must be nonempty exact captured repository paths"
            raise ValueError(msg)
        if len(paths) != len(set(paths)) or set(paths) & assessed:
            msg = "captured_path_dispositions cannot assess a path more than once"
            raise ValueError(msg)
        if set(paths) & assigned:
            msg = "captured_path_dispositions cannot replace or duplicate audit ownership"
            raise ValueError(msg)
        assessed.update(paths)
        records.append({**item, "paths": sorted(paths)})
    return {
        "captured_path_count": len(captured),
        "captured_paths_digest": digest_json(sorted(captured)),
        "assigned_captured_path_count": len(captured & assigned),
        "unassigned_captured_paths": sorted(unassigned),
        "unassessed_captured_paths": sorted(unassigned - assessed),
        "dispositions": sorted(records, key=lambda item: item["paths"]),
    }


def dependency_paths(inventory: dict[str, Any], catalog_ids: set[str]) -> tuple[str, ...]:
    """Return required context reads without promoting them to owned coverage."""
    return tuple(
        sorted({cast("str", path) for item in inventory.get("dispositions", []) if catalog_ids.intersection(item["catalog_ids"]) for path in item["paths"]})
    )
