"""Explicit source-judgment reassessment when a blocked recipe becomes executable."""

from typing import Any

from review_graph_integrity import digest_json

_EXECUTION_COMPLETION_FIELDS = frozenset(
    {"commands", "working_directories", "allowed_artifacts", "expected_workspace_effects", "planning_blocker", "source_state", "captured_paths"}
)
_JUDGMENT_FIELDS = ("contract_assessment", "native_limitations", "handoff_assessment")


def reassessment_candidates(
    requirements: list[dict[str, Any]], previous: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]], repository_root: str
) -> list[dict[str, Any]] | None:
    """Allow only completion of the same blocked recipe; other changes need wider review."""
    result = []
    for requirement in requirements:
        requirement_id = requirement["requirement_id"]
        before, after = previous.get(requirement_id), current.get(requirement_id)
        if before is None or after is None or digest_json(before) != requirement.get("planned_validation_digest"):
            return None
        if {**after, "source_state": before["source_state"], "captured_paths": before["captured_paths"]} == before:
            continue
        if (
            before["commands"]
            or before["working_directories"]
            or not before["planning_blocker"]
            or not before["canonical_recipe"]
            or after["commands"] != [before["canonical_recipe"]]
            or after["working_directories"] != [repository_root]
            or after["planning_blocker"] is not None
            or not after["required"]
            or {key: value for key, value in before.items() if key not in _EXECUTION_COMPLETION_FIELDS}
            != {key: value for key, value in after.items() if key not in _EXECUTION_COMPLETION_FIELDS}
        ):
            return None
        result.append(
            {
                "requirement_id": requirement_id,
                "original_planned_validation_digest": digest_json(before),
                "replacement_planned_validation_digest": digest_json(after),
                "original_execution_identity": before,
                "replacement_execution_identity": after,
            }
        )
    return result or None


def verify_reassessment_candidates(context: dict[str, Any], *, repository_root: str) -> None:
    """Replay eligibility and both digests from the immutable original requirement."""
    candidates = context.get("validation_reassessment", [])
    if not candidates:
        return
    requirements = {item["requirement_id"]: item for item in context["original_validation_requirements"]}
    ids = [item["requirement_id"] for item in candidates]
    if len(ids) != len(set(ids)) or not set(ids) <= requirements.keys():
        msg = "validation reassessment must bind unique original requirements"
        raise ValueError(msg)
    expected = reassessment_candidates(
        [requirements[key] for key in ids],
        {item["requirement_id"]: item["original_execution_identity"] for item in candidates},
        {item["requirement_id"]: item["replacement_execution_identity"] for item in candidates},
        repository_root,
    )
    if expected != candidates:
        msg = "validation reassessment differs from its bound execution identities"
        raise ValueError(msg)


def reconcile_requirements(context: dict[str, Any] | None, payload: dict[str, Any], *, fresh: bool) -> dict[str, Any] | None:
    """Seal fresh judgments without accepting old validation success or planning blockers."""
    pending = (context or {}).get("validation_reassessment", [])
    judgments = payload.get("validation_reassessments", [])
    if not pending and not judgments:
        return context
    if context is None or not fresh or not pending or len(judgments) != len(pending):
        msg = "validation reassessment requires a fresh judgment for every pending requirement"
        raise ValueError(msg)
    by_id = {item["requirement_id"]: item for item in judgments}
    if len(by_id) != len(judgments) or by_id.keys() != {item["requirement_id"] for item in pending}:
        msg = "validation reassessment must assess each bound requirement exactly once"
        raise ValueError(msg)
    current = {item["requirement_id"]: item for item in payload["validation_requirements"]}
    for candidate in pending:
        judgment = by_id[candidate["requirement_id"]]
        if (
            any(judgment[field] != candidate[field] for field in ("original_planned_validation_digest", "replacement_planned_validation_digest"))
            or current.get(candidate["requirement_id"], {}).get("planned_validation_digest") != candidate["replacement_planned_validation_digest"]
            or any(not judgment[field].strip() for field in _JUDGMENT_FIELDS)
        ):
            msg = "validation reassessment requires exact old/new digests, current obligations, and substantive reasons"
            raise ValueError(msg)
        if judgment["disposition"] == "uncertain" and payload["status"] != "blocked":
            msg = "uncertain validation reassessment blocks audit acceptance"
            raise ValueError(msg)
        owned = {path for unit in context["units"] for path in unit["owned_paths"]}
        if judgment["disposition"] == "reinspect" and not owned <= set(payload["files_inspected"]):
            msg = "material validation reassessment requires full owned-source inspection"
            raise ValueError(msg)
    if context.get("validation_reassessments", judgments) != judgments:
        msg = "validation reassessment differs from its sealed worker payload"
        raise ValueError(msg)
    return {**context, "validation_reassessments": judgments}
