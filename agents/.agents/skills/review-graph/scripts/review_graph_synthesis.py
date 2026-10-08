"""Typed synthesis judgments, distinct from graph completion and validator success."""

from typing import Any

from review_graph_doi import validate_scholarly_doi_resolution, validate_software_doi_resolution


def synthesis_binding_blockers(  # noqa: C901, PLR0912, PLR0915
    payload: dict[str, Any], predecessors: tuple[str, ...], bundle: dict[str, Any] | None = None
) -> tuple[str, ...]:
    """Report all evidence-binding errors together without changing judgments."""
    blockers: list[str] = []
    coverage = payload["predecessor_coverage"]
    covered = [item["evidence_id"] for item in coverage]
    if len(covered) != len(set(covered)) or set(covered) != set(predecessors):
        blockers.append("synthesis coverage must name every dispatched predecessor exactly once: " + ", ".join(predecessors))
    requirement_ids = [item["requirement_id"] for item in payload.get("validation_requirements", [])]
    if len(requirement_ids) != len(set(requirement_ids)):
        blockers.append("validation requirement IDs must be unique; merge repeated inherited needs by requirement_id, retaining owners, reasons and provenance")
    references = {(ref["evidence_id"], ref["finding_id"]) for item in payload["findings"] for ref in item["source_findings"]}
    if any(evidence_id not in predecessors for evidence_id, _ in references):
        blockers.append("synthesis finding provenance references an unknown predecessor")
    validations = payload["validation_reconciliation"]
    validation_ids = [item["evidence_id"] for item in validations]
    if len(validation_ids) != len(set(validation_ids)) or not set(validation_ids) <= set(predecessors):
        blockers.append("synthesis validation reconciliation has duplicate or unknown evidence; use one row per accepted validator ID")
    for field in ("predecessor_coverage", "validation_reconciliation"):
        for index, item in enumerate(payload[field]):
            if len(item["requirement_ids"]) != len(set(item["requirement_ids"])):
                blockers.append(f"{field}[{index}].requirement_ids must be unique")
    for item in validations:
        scholarly = item.get("scholarly_doi_resolution")
        if scholarly is not None:
            software_references = [check["software_verification"]["evidence_id"] for check in scholarly["checks"] if "software_verification" in check]
            if item["result"] != "failed" or any(key not in validation_ids for key in software_references) or "software_doi_resolution" in item:
                blockers.append("scholarly DOI resolution requires failed evidence, accepted follow-ups, and one resolution type")
        resolution = item.get("software_doi_resolution")
        if resolution is not None and (
            item["result"] != "failed" or any(check["verification_evidence_id"] not in validation_ids for check in resolution["checks"])
        ):
            blockers.append("software DOI resolution requires failed evidence and a dispatched verification validator")
    if bundle is not None:
        context = bundle.get("plan_context", {})
        exact_reused = {key for _requirement, key in context.get("exact_reused_review_evidence", [])}
        records = {item["evidence_id"]: item for item in bundle["records"] if item["evidence_id"] in predecessors}
        if set(records) != set(predecessors):
            blockers.append("synthesis bundle does not contain all dispatched predecessors")
        for item in coverage:
            record = records.get(item["evidence_id"])
            if record is None:
                continue
            disposition = "reused" if record.get("reuse") or item["evidence_id"] in exact_reused else "blocked" if record["status"] == "blocked" else "accepted"
            if set(item["requirement_ids"]) != set(record["requirement_ids"]) or item["disposition"] != disposition:
                blockers.append(
                    f"synthesis predecessor coverage contradicts accepted evidence {item['evidence_id']}: "
                    f"requirement_ids={record['requirement_ids']}, disposition={disposition}; reused requires runtime-proved reuse across source states"
                )
        source_findings = {(key, finding["finding_id"]) for key, record in records.items() for finding in record.get("findings", [])}
        if references != source_findings:
            blockers.append("synthesis must preserve every source finding and cannot invent source-finding references")
        expected_validations = {key: record for key, record in records.items() if record["record_type"] == "validation"}
        if set(validation_ids) != set(expected_validations):
            blockers.append("synthesis must reconcile every predecessor validator exactly once: " + ", ".join(expected_validations))
        for item in validations:
            record = expected_validations.get(item["evidence_id"])
            if record is None:
                continue
            if item["result"] != record["status"] or set(item["requirement_ids"]) != set(record["requirement_ids"]):
                blockers.append(
                    f"synthesis validation result contradicts accepted evidence {item['evidence_id']}: "
                    f"requirement_ids={record['requirement_ids']}, result={record['status']}"
                )
            if "software_doi_resolution" in item:
                try:
                    validate_software_doi_resolution(item["software_doi_resolution"], record, records)
                except ValueError as error:
                    blockers.append(str(error))
            if "scholarly_doi_resolution" in item:
                try:
                    validate_scholarly_doi_resolution(item["scholarly_doi_resolution"], record, records)
                except (KeyError, OSError, TypeError, ValueError) as error:
                    blockers.append(f"scholarly DOI resolution: {error}")
            if "validation_environments" in context:
                environment = context["validation_environments"].get(record["node_id"])
                if environment is None or item["platform"] != environment["platform"]:
                    blockers.append(
                        f"synthesis validation platform contradicts the bound executor environment for {item['evidence_id']}: {environment}; "
                        "put unexecuted platforms without separate accepted evidence in limitations/cross_surface_risks"
                    )
        closure = payload["routing_closure"]
        unresolved = context.get("handoff_reconciliation", {}).get("unresolved_handoff_ids", [])
        complete = context.get("routing_catalog_closed", False) and not context.get("routing_completion_blockers") and not unresolved
        if closure != {"complete": complete, "unresolved_handoff_ids": unresolved, "user_excluded_catalog_ids": context.get("user_excluded_catalog_ids", [])}:
            blockers.append("synthesis routing closure contradicts the plan bundle")
    unfinished = any(item["disposition"] in {"remaining", "blocked"} for item in payload["findings"])
    failed = any(
        item["result"] == "blocked"
        or (item["result"] == "failed" and (bundle is None or not {"software_doi_resolution", "scholarly_doi_resolution"} & item.keys()))
        or item["execution_mode"] == "unexecuted"
        for item in validations
    )
    incomplete = not payload["routing_closure"]["complete"] or bool(payload["routing_closure"]["unresolved_handoff_ids"])
    incomplete |= any(item["disposition"] == "blocked" for item in coverage) or payload["status"] == "blocked"
    if payload["readiness_verdict"] == "ready" and (unfinished or failed or incomplete):
        blockers.append("ready synthesis contradicts remaining findings, validation gaps, or incomplete coverage")
    if incomplete and payload["readiness_verdict"] != "blocked":
        blockers.append("incomplete synthesis requires a blocked readiness verdict")
    return tuple(blockers)


def validate_synthesis(payload: dict[str, Any], predecessors: tuple[str, ...], bundle: dict[str, Any] | None = None) -> None:
    """Reconcile coverage and finding provenance without deciding semantic severity."""
    blockers = synthesis_binding_blockers(payload, predecessors, bundle)
    if blockers:
        raise ValueError("; ".join(blockers))


def synthesis_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Retain dedicated judgments in compiler output and downstream bundles."""
    return {
        key: payload[key]
        for key in ("readiness_verdict", "verdict_reasons", "predecessor_coverage", "routing_closure", "validation_reconciliation", "cross_surface_risks")
        if key in payload
    }
