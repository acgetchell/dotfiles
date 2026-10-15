"""Explicit audit coverage partitions and content-bound delta decisions."""

from contextlib import suppress
from pathlib import PurePosixPath
from typing import Any, cast

from review_graph_git import intervening_metadata_blockers
from review_graph_instruction_delta import effective_units, instruction_delta_candidate
from review_graph_integrity import canonical_json, digest_json
from review_graph_read_provenance import normalized_read_provenance
from review_graph_reuse import AuditInputIdentity, AuditReuseTransition, ReviewSourceSnapshot, verify_reuse_inputs


def coverage_execution_view(context: dict[str, Any], reference: dict[str, str]) -> dict[str, Any]:
    """Project verified work and inherited obligations without capture arrays."""
    return {
        "schema_version": 1,
        "proof_reference": reference,
        "evidence_id": context["evidence_id"],
        "units": [
            {
                **{key: value for key, value in unit.items() if key not in {"reason", "input_deltas"}},
                **(
                    {"input_deltas": [{key: value for key, value in delta.items() if key not in {"before", "after"}} for delta in unit["input_deltas"]]}
                    if "input_deltas" in unit
                    else {}
                ),
            }
            for unit in context["units"]
        ],
        "original_findings": context["original_findings"],
        "original_validation_requirements": context["original_validation_requirements"],
        "original_handoffs": context["original_handoffs"],
        "original_audit_context": context.get("original_audit_context", {}),
        "original_git_context": context.get("original_git_context", {}),
    }


def coverage_reference(context: dict[str, Any]) -> dict[str, Any]:
    """Bind native output to verified metadata and its external proof, if any."""
    return {
        "schema_version": 1,
        "metadata_field": "expectation.coverage_reuse",
        "digest": digest_json(context),
        "reused_units": sum(unit["disposition"] == "reused" for unit in effective_units(context)),
        "recheck_units": sum(unit["disposition"] == "recheck" for unit in effective_units(context)),
    }


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
    missing_dependencies = sorted(set(payload["nearby_contract_owners"]) - dependencies)
    if missing_dependencies:
        msg = "coverage units must account for every inspected nearby dependency; missing: " + ", ".join(missing_dependencies)
        raise ValueError(msg)
    for unit in units:
        recipes = unit.get("recipe_dependencies", [])
        if len({item["path"] for item in recipes}) != len(recipes) or any(item["path"] not in unit["dependency_paths"] for item in recipes):
            msg_0 = "recipe dependencies must uniquely name inspected dependency paths"
            raise ValueError(msg_0)


def coverage_decisions(  # noqa: PLR0913 - shared provenance proof plus optional retained replay bytes.
    payload: dict[str, Any],
    origin: ReviewSourceSnapshot,
    target: ReviewSourceSnapshot,
    inputs: AuditInputIdentity,
    transition: AuditReuseTransition,
    *,
    retained_after: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Prove each partition separately; uncertainty always requires fresh inspection."""
    validate_coverage_units(payload, inputs.owned_paths)
    root = PurePosixPath(origin.repository_root)
    declared = {root / path for unit in payload.get("coverage_units", []) for path in (*unit["owned_paths"], *unit["dependency_paths"])}
    decisions = []
    for unit in payload.get("coverage_units", []):
        unit_paths = {root / path for path in (*unit["owned_paths"], *unit["dependency_paths"])}
        # Declared paths belong to their units; unassigned reader operands
        # remain conservative dependencies of every judgment.
        command_paths = tuple(path for path in inputs.command_read_paths if root / path in unit_paths or root / path not in declared)
        reason = unit["dependency_uncertainty"]
        deltas = []
        metadata_blockers = intervening_metadata_blockers(
            {**payload, **normalized_read_provenance(inputs), "files_inspected": unit["owned_paths"], "nearby_contract_owners": unit["dependency_paths"]},
            transition.metadata_transitions,
        )
        if metadata_blockers:
            reason = canonical_json(metadata_blockers)
        if not reason:
            unit_inputs = AuditInputIdentity(
                tuple(unit["owned_paths"]),
                tuple(unit["owned_paths"]),
                tuple(unit["dependency_paths"]),
                inputs.instruction_digests,
                inputs.retained_inputs,
                inputs.runtime_inputs,
                inputs.protocol_commands,
                command_paths,
            )
            try:
                verify_reuse_inputs(origin, target, unit_inputs, transition)
            except ValueError as error:
                reason = str(error)
                # Missing bytes or ambiguous dependencies require source reinspection.
                with suppress(OSError, ValueError, KeyError, UnicodeError):
                    deltas = instruction_delta_candidate(unit, origin, target, unit_inputs, transition, retained_after=retained_after)
        decisions.append(
            {
                **unit,
                "disposition": "instruction-review" if deltas else "recheck" if reason else "reused",
                **({"input_deltas": deltas} if deltas else {}),
                "reason": reason or "Exact content, modes, dependencies, and instructions are unchanged.",
            }
        )
    return decisions


def coverage_decision_report(units: list[dict[str, Any]], origin: ReviewSourceSnapshot, target: ReviewSourceSnapshot) -> list[dict[str, Any]]:
    """Explain changed whole-file inputs without changing immutable proof decisions."""
    before, after = dict(origin.repository_path_fingerprints), dict(target.repository_path_fingerprints)
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    return [
        {
            **unit,
            "reason_code": unit.get("reason_code")
            or ("dependency-uncertainty" if unit["dependency_uncertainty"] else "verified" if unit["disposition"] == "reused" else "input-proof-failed"),
            "input_changes": {role: sorted(changed.intersection(unit[role])) for role in ("owned_paths", "dependency_paths")},
        }
        for unit in units
    ]


def reused_paths(context: dict[str, Any] | None) -> tuple[str, ...]:
    """Return only paths proved reusable by a compiler-bound delta context."""
    return (
        tuple(cast("str", path) for unit in effective_units(context) if unit["disposition"] == "reused" for path in unit["owned_paths"])
        if context is not None
        else ()
    )


def combined_findings(payload: dict[str, Any], context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Keep reused judgments and original provenance alongside fresh findings."""
    if context is None:
        return payload["findings"]
    indices = {ordinal for unit in effective_units(context) if unit["disposition"] == "reused" for ordinal in unit["finding_indices"]}
    preserved = [
        {
            **{key: value for key, value in finding.items() if key != "finding_id"},
            "source_findings": [{"evidence_id": context["evidence_id"], "finding_id": finding["finding_id"]}],
        }
        for ordinal, finding in enumerate(context["original_findings"], start=1)
        if ordinal in indices
    ]
    return [*preserved, *payload["findings"]]
