"""Policy-backed, per-specialist exclusions remain distinct from missing reads."""

from pathlib import PurePosixPath
from typing import Any

from review_graph_coverage import reused_paths


def scope_exclusions(raw: object) -> tuple[dict[str, str], ...]:
    """Decode explicit classifications without guessing from directory names."""
    if not isinstance(raw, (list, tuple)):
        msg = "review_scope_exclusions must be an array"
        raise TypeError(msg)
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"catalog_id", "path", "reason", "policy_source"}
            or any(not isinstance(value, str) or not value.strip() for value in item.values())
        ):
            msg = "scope exclusions require catalog_id, path, reason, and policy_source"
            raise ValueError(msg)
        path = PurePosixPath(item["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in item["path"] or ":" in item["path"] or str(path) != item["path"] or str(path) == ".":
            msg = "scope exclusion path must be a concrete portable repository path"
            raise ValueError(msg)
        identity = (item["catalog_id"], item["path"])
        if identity in seen:
            msg = "scope exclusions must be unique per specialist and path"
            raise ValueError(msg)
        seen.add(identity)
        records.append(dict(item))
    return tuple(records)


def excluded_paths(records: tuple[dict[str, str], ...], catalog_ids: tuple[str, ...]) -> set[str]:
    """Select one specialist's exclusions without granting another lens coverage."""
    return {item["path"] for item in records if item["catalog_id"] in catalog_ids}


def validate_partial_obligations(context: dict[str, Any] | None, payload: dict[str, Any]) -> None:
    """An inspection continuation cannot silently revise inherited obligations."""
    if context is None or not context.get("partial_audit"):
        return
    for original_field, field in (("original_validation_requirements", "validation_requirements"), ("original_handoffs", "handoffs")):
        for original in context[original_field]:
            obligation = {key: value for key, value in original.items() if key != "handoff_id"}
            if obligation not in payload.get(field, []):
                msg = "partial audit must preserve original validation requirements and routing handoffs exactly"
                raise ValueError(msg)


def partial_coverage_units(record: dict[str, Any], owned: tuple[str, ...], excluded: set[str]) -> list[dict[str, Any]]:
    """Partition actual completed reads and remaining work on identical inputs."""
    completed = set(record["files_inspected"]) | set(reused_paths(record.get("coverage_reuse")))
    omitted = set(owned) - completed
    limitations = record["scope_limitations"]
    if len(limitations) != len({item["path"] for item in limitations}) or {item["path"] for item in limitations} != omitted:
        msg = "partial audit requires one scope limitation for every omitted owned path"
        raise ValueError(msg)
    if not omitted or not completed or not excluded <= omitted:
        msg = "partial audit requires completed inspection and only omitted paths may be excluded"
        raise ValueError(msg)
    if record["status"] not in {"blocked", "completed"} or record["limitations"] or record.get("unresolved_uncertainties"):
        msg = "partial continuation cannot clear unclassified limitations or unresolved uncertainties"
        raise ValueError(msg)
    dependencies = sorted(set(record["nearby_contract_owners"]))
    units = [
        {
            "unit_id": "completed-inspection",
            "owned_paths": sorted(completed),
            "dependency_paths": dependencies,
            "dependency_uncertainty": "",
            "finding_indices": list(range(1, len(record["findings"]) + 1)),
            "disposition": "reused",
            "reason": "Completed inspection retained on identical inputs.",
        }
    ]
    if remaining := sorted(omitted - excluded):
        units.append(
            {
                "unit_id": "remaining-inspection",
                "owned_paths": remaining,
                "dependency_paths": dependencies,
                "dependency_uncertainty": "",
                "finding_indices": [],
                "disposition": "recheck",
                "reason": "Fresh inspection required for every remaining applicable path.",
            }
        )
    return units
