"""Validate substantive independent-review evidence and render the native contract."""

import json
from pathlib import Path
from typing import Any

from review_graph_git import validate_git_dependencies
from review_graph_schema import require_schema, require_schema_definition

SCHEMA = Path(__file__).resolve().parents[1] / "references/schemas/independent-payload-v1.schema.json"
CHECK_LABELS = {
    "fallback": "fallback absence and failure",
    "platform": "platform seams",
    "parser-errors": "parser suffixes and error branches",
    "unexpected-exceptions": "unexpected exception types",
    "test-boundaries": "changed tests and boundary cases",
}


def _context_blockers(context: list[str], owned: list[str]) -> list[str]:
    if len(context) != len(set(context)) or set(context) & set(owned):
        return ["$.nearby_contract_owners must contain unique dependency/context paths outside dispatch ownership"]
    return []


def _evidence_blockers(payload: dict[str, Any], dispatch: dict[str, Any]) -> list[str]:
    """Check supplied coverage and observations separately from presentation."""
    blockers = []
    checks = {check["check_id"]: check for check in payload["adversarial_checks"]}
    if len(checks) != len(payload["adversarial_checks"]):
        blockers.append("$.adversarial_checks contains duplicate check_id values")
    required = {key for key, label in CHECK_LABELS.items() if label in dispatch.get("adversarial_checks", [])}
    unknown_labels = set(dispatch.get("adversarial_checks", [])) - set(CHECK_LABELS.values())
    if unknown_labels:
        blockers.append("dispatch contains unsupported adversarial check labels")
    accepted = payload["status"] != "blocked"
    if accepted and required - checks.keys():
        blockers.append("$.adversarial_checks missing dispatched checks: " + ", ".join(sorted(required - checks.keys())))
    paths = set(payload["files_inspected"])
    if len(paths) != len(payload["files_inspected"]) or (accepted and paths != set(dispatch["planned_paths"])):
        blockers.append("$.files_inspected must equal the exact dispatched paths without duplicates")
    if not paths <= set(dispatch["planned_paths"]):
        blockers.append("$.files_inspected contains paths outside the dispatch")
    context = payload.get("nearby_contract_owners", [])
    blockers.extend(_context_blockers(context, dispatch["planned_paths"]))
    for index, check in enumerate(payload["adversarial_checks"]):
        if len(check["inspected_paths"]) != len(set(check["inspected_paths"])):
            blockers.append(f"$.adversarial_checks[{index}].inspected_paths contains duplicate paths")
        if not set(check["inspected_paths"]) <= paths:
            blockers.append(f"$.adversarial_checks[{index}].inspected_paths must refer to inspected files")
    blockers.extend(
        f"$.{field} differs from the independently captured dispatch state" for field in ("before_state", "after_state") if payload[field] != dispatch[field]
    )
    if payload["status"] == "no-findings" and not (checks or payload["no_finding_evidence"]):
        blockers.append("$.no_finding_evidence requires substantive inspection evidence")
    return blockers


def render_independent_payload(payload: dict[str, Any], dispatch: dict[str, Any]) -> bytes:
    """Render supplied judgments only; neither infer missing checks nor repair evidence."""
    require_schema(payload, SCHEMA)
    validate_git_dependencies(payload)
    require_schema_definition(dispatch, SCHEMA, "dispatch")
    if blockers := _evidence_blockers(payload, dispatch):
        raise ValueError("; ".join(blockers))

    inspected = set(payload["files_inspected"])
    rendered_paths = [path for path in dispatch["planned_paths"] if path in inspected]
    scope = "\n".join(
        (
            f"- Change target: {dispatch['change_target']}",
            f"- Files: {', '.join(rendered_paths) or 'none'}",
            *((f"- Dependency/context reads: {', '.join(payload['nearby_contract_owners'])}",) if payload.get("nearby_contract_owners") else ()),
            *(f"- {label}: {payload[key]}" for label, key in (("Branches", "branches"), ("Boundary cases", "boundary_cases"), ("Tests", "tests"))),
        )
    )
    findings = (
        "\n".join(
            "\n".join(
                (
                    f"- Finding: {index}",
                    *(f"  - {key.title()}: {finding[key]}" for key in ("severity", "location", "summary", "evidence", "impact", "owner", "remediation")),
                )
            )
            for index, finding in enumerate(payload["findings"], 1)
        )
        or "No findings."
    )
    evidence = [f"- Inspected: {text}" for text in payload["no_finding_evidence"]]
    for check in payload["adversarial_checks"]:
        key = check["check_id"]
        evidence.extend((f"- Inspected: {CHECK_LABELS[key]}", f"  - Evidence: {check['evidence']}", f"  - Files: {', '.join(check['inspected_paths'])}"))
    evidence.append("- Canonical worker payload: " + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    handoffs = (
        "\n".join(
            "\n".join(
                (
                    f"- Catalog ID: {item['catalog_id']}",
                    f"  - Observed trigger: {item['observed_trigger']}",
                    f"  - Reason: {item['reason']}",
                    f"  - Scope: {', '.join(item['scope'])}",
                )
            )
            for item in payload["handoffs"]
        )
        or "none"
    )
    fingerprints = "\n".join(
        "\n".join(
            (
                f"- {label}:",
                *(
                    f"  - {key}: {value}"
                    for key, value in zip(("Scope fingerprint", "Worktree fingerprint", "Repository state fingerprint"), state, strict=True)
                ),
            )
        )
        for label, state in (("Expected", dispatch["source_state"]), ("Before", payload["before_state"]), ("After", payload["after_state"]))
    )
    sections = (
        ("Scope Inspected", scope),
        ("Findings", findings),
        ("No-Finding Evidence", "\n".join(evidence)),
        ("Routing Handoffs", handoffs),
        ("Fingerprint Proof", fingerprints),
        ("Git State", "- Source-controlled files changed: none\n- Git state mutated: no"),
    )
    return ("# Repository Independent Review\n\n" + "\n\n".join(f"## {label}\n\n{body}" for label, body in sections) + "\n").encode()
