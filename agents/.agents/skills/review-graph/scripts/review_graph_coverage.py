"""Explicit audit coverage partitions and content-bound delta decisions."""

from contextlib import suppress
from pathlib import PurePosixPath
from typing import Any, cast

from review_graph_git import intervening_metadata_blockers
from review_graph_instruction_delta import effective_units, instruction_delta_candidate
from review_graph_integrity import canonical_json, digest_json
from review_graph_read_provenance import normalized_read_provenance
from review_graph_reuse import AuditInputIdentity, AuditReuseTransition, ReuseInputError, ReviewSourceSnapshot, verify_reuse_inputs


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
        **({"validation_reassessment": context["validation_reassessment"]} if context.get("validation_reassessment") else {}),
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


def coverage_diagnostics(payload: dict[str, Any], owned_paths: tuple[str, ...]) -> tuple[str, ...]:
    """Check independent partition facts even when another field is malformed."""
    units = payload.get("coverage_units", [])
    if not isinstance(units, list) or not units or any(not isinstance(unit, dict) for unit in units):
        return ()

    def values(field: str, kind: type) -> list[Any] | None:
        groups = [unit.get(field) for unit in units]
        if any(not isinstance(group, list) or any(type(value) is not kind for value in group) for group in groups):
            return None
        return [value for group in groups for value in group]

    errors: list[str] = []
    paths, findings, dependencies = values("owned_paths", str), values("finding_indices", int), values("dependency_paths", str)
    identities = [unit.get("unit_id") for unit in units]
    if all(isinstance(identity, str) for identity in identities) and len(identities) != len(set(identities)):
        errors.append("coverage units must have unique unit identities")
    if paths is not None and (len(paths) != len(set(paths)) or set(paths) != set(owned_paths)):
        errors.append("coverage units must uniquely partition every owned path")
    if findings is not None and isinstance(payload.get("findings"), list) and sorted(findings) != list(range(1, len(payload["findings"]) + 1)):
        errors.append("coverage units must assign every finding exactly once using one-based indices")
    nearby = payload.get("nearby_contract_owners")
    if dependencies is not None and isinstance(nearby, list) and all(isinstance(path, str) for path in nearby):
        missing = sorted(set(nearby) - set(dependencies))
        if missing:
            errors.append("coverage units must account for every inspected nearby dependency using its recorded spelling; missing: " + ", ".join(missing))
    return (*errors, *_recipe_diagnostics(units))


def _recipe_diagnostics(units: list[dict[str, Any]]) -> tuple[str, ...]:
    errors: list[str] = []
    for unit in units:
        recipes = unit.get("recipe_dependencies", [])
        if not isinstance(recipes, list) or any(not isinstance(item, dict) or not isinstance(item.get("path"), str) for item in recipes):
            continue
        dependencies = unit.get("dependency_paths")
        valid_dependencies = isinstance(dependencies, list) and all(isinstance(path, str) for path in dependencies)
        if len({item["path"] for item in recipes}) != len(recipes) or (valid_dependencies and any(item["path"] not in dependencies for item in recipes)):
            errors.append("recipe dependencies must uniquely name inspected dependency paths")
    return tuple(errors)


def validate_coverage_units(payload: dict[str, Any], owned_paths: tuple[str, ...]) -> None:
    """Check partition semantics after the caller validates the review payload schema."""
    if errors := coverage_diagnostics(payload, owned_paths):
        raise ValueError("; ".join(errors))


def audit_coverage_units(payload: dict[str, Any], inputs: AuditInputIdentity) -> list[dict[str, Any]]:
    """Derive units from a schema-validated payload without changing its sealed bytes."""
    validate_coverage_units(payload, inputs.owned_paths)
    if payload.get("coverage_units"):
        return payload["coverage_units"]
    if payload.get("coverage_reuse"):
        return _continued_coverage_units(payload, inputs)
    return [
        {
            "unit_id": "whole-audit",
            "owned_paths": list(inputs.owned_paths),
            "dependency_paths": sorted(set(inputs.nearby_contract_owners) | set(inputs.command_read_paths)),
            "dependency_uncertainty": "",
            "finding_indices": list(range(1, len(payload["findings"]) + 1)),
        }
    ]


def _continued_coverage_units(payload: dict[str, Any], inputs: AuditInputIdentity) -> list[dict[str, Any]]:
    """Retain proved partitions; conservatively group the freshly rechecked surface."""
    context = payload["coverage_reuse"]
    units: list[dict[str, Any]] = []
    assigned: set[int] = set()
    # The compiler has replayed this context and its original evidence. Keep
    # inherited judgments separate from fresh reads; no worker claims new units.
    for unit in effective_units(context):
        if unit["disposition"] != "reused":
            continue
        original_ids = {context["original_findings"][index - 1]["finding_id"] for index in unit["finding_indices"]}
        indices = [
            index
            for index, finding in enumerate(payload["findings"], start=1)
            if any(item["evidence_id"] == context["evidence_id"] and item["finding_id"] in original_ids for item in finding.get("source_findings", []))
        ]
        assigned.update(indices)
        units.append(
            {
                **{key: unit[key] for key in ("unit_id", "owned_paths", "dependency_paths", "dependency_uncertainty")},
                **({"recipe_dependencies": unit["recipe_dependencies"]} if "recipe_dependencies" in unit else {}),
                "finding_indices": indices,
            }
        )
    rechecked = sorted(set(inputs.owned_paths) - {path for unit in units for path in unit["owned_paths"]})
    remaining = sorted(set(range(1, len(payload["findings"]) + 1)) - assigned)
    dependencies = sorted(set(inputs.nearby_contract_owners) | set(inputs.command_read_paths))
    if rechecked:
        units.append(
            {
                "unit_id": "rechecked:" + digest_json([rechecked, dependencies]),
                "owned_paths": rechecked,
                "dependency_paths": dependencies,
                "dependency_uncertainty": "",
                "finding_indices": remaining,
            }
        )
    elif remaining:
        # New findings outside a freshly inspected surface cannot inherit an
        # independence claim. Collapse to a conservative complete audit unit.
        return [
            {
                "unit_id": "whole-audit",
                "owned_paths": list(inputs.owned_paths),
                "dependency_paths": sorted({*dependencies, *(path for unit in units for path in unit["dependency_paths"])}),
                "dependency_uncertainty": "Fresh findings did not have a separately inspected coverage unit.",
                "finding_indices": list(range(1, len(payload["findings"]) + 1)),
            }
        ]
    # Every new reader dependency applies to all retained judgments unless the
    # original partition already assigned it; never silently discard a read.
    declared = {path for unit in units for path in unit["dependency_paths"]}
    unassigned = set(dependencies) - declared
    for unit in units:
        unit["dependency_paths"] = sorted(set(unit["dependency_paths"]) | unassigned)
    validate_coverage_units({**payload, "coverage_units": units}, inputs.owned_paths)
    return units


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
    units = audit_coverage_units(payload, inputs)
    root = PurePosixPath(origin.repository_root)
    declared = {root / path for unit in units for path in (*unit["owned_paths"], *unit["dependency_paths"])}
    decisions = []
    for unit in units:
        unit_paths = {root / path for path in (*unit["owned_paths"], *unit["dependency_paths"])}
        # Declared paths belong to their units; unassigned reader operands
        # remain conservative dependencies of every judgment.
        command_paths = tuple(path for path in inputs.command_read_paths if root / path in unit_paths or root / path not in declared)
        reason = unit["dependency_uncertainty"]
        deltas = []
        rejected_inputs = []
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
                if isinstance(error, ReuseInputError):
                    rejected_inputs = error.rejected_inputs
                # Missing bytes or ambiguous dependencies require source reinspection.
                with suppress(OSError, ValueError, KeyError, UnicodeError):
                    deltas = instruction_delta_candidate(unit, origin, target, unit_inputs, transition, retained_after=retained_after)
        decisions.append(
            {
                **unit,
                "disposition": "instruction-review" if deltas else "recheck" if reason else "reused",
                **({"input_deltas": deltas} if deltas else {}),
                **({"rejected_inputs": rejected_inputs} if rejected_inputs else {}),
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


def reused_dependency_paths(context: dict[str, Any] | None) -> tuple[str, ...]:
    """Keep inherited source dependencies separate from this worker's actual reads."""
    if context is None:
        return ()
    return tuple(sorted({cast("str", path) for unit in effective_units(context) if unit["disposition"] == "reused" for path in unit["dependency_paths"]}))


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
