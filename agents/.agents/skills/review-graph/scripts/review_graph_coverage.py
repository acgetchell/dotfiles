"""Explicit audit coverage partitions and content-bound delta decisions."""

from typing import Any, cast

from review_graph_reuse import AuditInputIdentity, AuditReuseTransition, ReviewSourceSnapshot, verify_reuse_inputs


def validate_coverage_units(payload: dict[str, Any], owned_paths: tuple[str, ...]) -> None:
    """Require a complete partition with explicit dependencies and finding ownership."""
    units = payload.get("coverage_units", [])
    if not units:
        return
    paths = [path for unit in units for path in unit["owned_paths"]]
    identities = [unit["unit_id"] for unit in units]
    findings = [ordinal for unit in units for ordinal in unit["finding_indices"]]
    dependencies = {path for unit in units for path in unit["dependency_paths"]}
    if len(identities) != len(set(identities)) or len(paths) != len(set(paths)) or set(paths) != set(owned_paths):
        msg = "coverage units must uniquely partition every owned path"
        raise ValueError(msg)
    if sorted(findings) != list(range(1, len(payload["findings"]) + 1)):
        msg = "coverage units must assign every finding exactly once using one-based indices"
        raise ValueError(msg)
    if not set(payload["nearby_contract_owners"]) <= dependencies:
        msg = "coverage units must account for every inspected nearby dependency"
        raise ValueError(msg)


def coverage_decisions(
    payload: dict[str, Any], origin: ReviewSourceSnapshot, target: ReviewSourceSnapshot, inputs: AuditInputIdentity, transition: AuditReuseTransition
) -> list[dict[str, Any]]:
    """Prove each partition separately; uncertainty always requires fresh inspection."""
    validate_coverage_units(payload, inputs.owned_paths)
    decisions = []
    for unit in payload.get("coverage_units", []):
        reason = unit["dependency_uncertainty"]
        if not reason:
            unit_inputs = AuditInputIdentity(
                tuple(unit["owned_paths"]), tuple(unit["owned_paths"]), tuple(unit["dependency_paths"]), inputs.instruction_digests
            )
            try:
                verify_reuse_inputs(origin, target, unit_inputs, transition)
            except ValueError as error:
                reason = str(error)
        decisions.append(
            {
                **unit,
                "disposition": "recheck" if reason else "reused",
                "reason": reason or "Exact content, modes, dependencies, and instructions are unchanged.",
            }
        )
    return decisions


def reused_paths(context: dict[str, Any] | None) -> tuple[str, ...]:
    """Return only paths proved reusable by a compiler-bound delta context."""
    return tuple(cast("str", path) for unit in (context or {}).get("units", []) if unit["disposition"] == "reused" for path in unit["owned_paths"])


def combined_findings(payload: dict[str, Any], context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Keep reused judgments and original provenance alongside fresh findings."""
    if context is None:
        return payload["findings"]
    indices = {ordinal for unit in context["units"] if unit["disposition"] == "reused" for ordinal in unit["finding_indices"]}
    preserved = [
        {
            **{key: value for key, value in finding.items() if key != "finding_id"},
            "source_findings": [{"evidence_id": context["evidence_id"], "finding_id": finding["finding_id"]}],
        }
        for ordinal, finding in enumerate(context["original_findings"], start=1)
        if ordinal in indices
    ]
    return [*preserved, *payload["findings"]]
