"""Typed synthesis judgments, distinct from graph completion and validator success."""

from typing import Any


def validate_synthesis(payload: dict[str, Any], predecessors: tuple[str, ...], bundle: dict[str, Any] | None = None) -> None:  # noqa: C901, PLR0912, PLR0915
    """Reconcile coverage and finding provenance without deciding semantic severity."""
    coverage = payload["predecessor_coverage"]
    covered = [item["evidence_id"] for item in coverage]
    if len(covered) != len(set(covered)) or set(covered) != set(predecessors):
        msg = "synthesis coverage must name every dispatched predecessor exactly once"
        raise ValueError(msg)
    references = {(ref["evidence_id"], ref["finding_id"]) for item in payload["findings"] for ref in item["source_findings"]}
    if any(evidence_id not in predecessors for evidence_id, _ in references):
        msg = "synthesis finding provenance references an unknown predecessor"
        raise ValueError(msg)
    validations = payload["validation_reconciliation"]
    validation_ids = [item["evidence_id"] for item in validations]
    if len(validation_ids) != len(set(validation_ids)) or not set(validation_ids) <= set(predecessors):
        msg = "synthesis validation reconciliation has duplicate or unknown evidence"
        raise ValueError(msg)
    if bundle is not None:
        context = bundle.get("plan_context", {})
        exact_reused = {key for _requirement, key in context.get("exact_reused_review_evidence", [])}
        records = {item["evidence_id"]: item for item in bundle["records"] if item["evidence_id"] in predecessors}
        if set(records) != set(predecessors):
            msg = "synthesis bundle does not contain all dispatched predecessors"
            raise ValueError(msg)
        for item in coverage:
            record = records[item["evidence_id"]]
            disposition = "reused" if record.get("reuse") or item["evidence_id"] in exact_reused else "blocked" if record["status"] == "blocked" else "accepted"
            if set(item["requirement_ids"]) != set(record["requirement_ids"]) or item["disposition"] != disposition:
                msg = "synthesis predecessor coverage contradicts accepted evidence"
                raise ValueError(msg)
        source_findings = {(key, finding["finding_id"]) for key, record in records.items() for finding in record.get("findings", [])}
        if references != source_findings:
            msg = "synthesis must preserve every source finding and cannot invent source-finding references"
            raise ValueError(msg)
        expected_validations = {key: record for key, record in records.items() if record["record_type"] == "validation"}
        if set(validation_ids) != set(expected_validations):
            msg = "synthesis must reconcile every predecessor validator"
            raise ValueError(msg)
        for item in validations:
            record = expected_validations[item["evidence_id"]]
            if item["result"] != record["status"] or set(item["requirement_ids"]) != set(record["requirement_ids"]):
                msg = "synthesis validation result contradicts accepted evidence"
                raise ValueError(msg)
            if "validation_environments" in context:
                environment = context["validation_environments"].get(record["node_id"])
                if environment is None or item["platform"] != environment["platform"]:
                    msg = "synthesis validation platform contradicts the bound executor environment"
                    raise ValueError(msg)
        closure = payload["routing_closure"]
        unresolved = context.get("handoff_reconciliation", {}).get("unresolved_handoff_ids", [])
        complete = context.get("routing_catalog_closed", False) and not context.get("routing_completion_blockers") and not unresolved
        if closure != {"complete": complete, "unresolved_handoff_ids": unresolved, "user_excluded_catalog_ids": context.get("user_excluded_catalog_ids", [])}:
            msg = "synthesis routing closure contradicts the plan bundle"
            raise ValueError(msg)
    unfinished = any(item["disposition"] in {"remaining", "blocked"} for item in payload["findings"])
    failed = any(item["result"] in {"failed", "blocked"} or item["execution_mode"] == "unexecuted" for item in validations)
    incomplete = not payload["routing_closure"]["complete"] or bool(payload["routing_closure"]["unresolved_handoff_ids"])
    incomplete |= any(item["disposition"] == "blocked" for item in coverage) or payload["status"] == "blocked"
    if payload["readiness_verdict"] == "ready" and (unfinished or failed or incomplete):
        msg = "ready synthesis contradicts remaining findings, validation gaps, or incomplete coverage"
        raise ValueError(msg)
    if incomplete and payload["readiness_verdict"] != "blocked":
        msg = "incomplete synthesis requires a blocked readiness verdict"
        raise ValueError(msg)


def synthesis_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Retain dedicated judgments in compiler output and downstream bundles."""
    return {
        key: payload[key]
        for key in ("readiness_verdict", "verdict_reasons", "predecessor_coverage", "routing_closure", "validation_reconciliation", "cross_surface_risks")
        if key in payload
    }
