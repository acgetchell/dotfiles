"""Bound audit provenance and compact native scope rendering."""

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from review_graph_coverage import coverage_reference
from review_graph_integrity import canonical_json, digest_bytes, digest_json

if TYPE_CHECKING:
    from review_graph_reuse import AuditInputIdentity


def worker_payload_reference(payload: dict[str, Any]) -> dict[str, Any]:
    """Identify the complete canonical payload in the report's metadata artifact."""
    content = canonical_json(payload).encode()
    return {
        "schema_version": 1,
        "metadata_field": "expectation.canonical_worker_payload",
        "digest": digest_bytes(content),
        "byte_count": len(content),
        "coverage_units": len(payload.get("coverage_units", [])),
    }


def review_scope_body(
    payload: dict[str, Any], *, mode: str, audit_inputs: AuditInputIdentity | None, coverage_reuse: dict[str, Any] | None, compact: bool = False
) -> str:
    """Render exact inline provenance or a bounded, digest-backed metadata view."""
    if compact:
        lines = [
            f"- Files: {len(payload['files_inspected'])} inspected paths; full list in bound worker payload",
            f"- Nearby contract owners: {len(payload['nearby_contract_owners'])} context paths; full list in bound worker payload",
            f"- Worker payload reference: {canonical_json(worker_payload_reference(payload))}",
        ]
    else:
        canonical_payload = canonical_json(payload)
        lines = [
            f"- Files: {', '.join(payload.get('files_inspected', [])) or ('bundle-only synthesis' if mode == 'synthesis' else 'blocked-before-inspection')}",
            f"- Nearby contract owners: {', '.join(payload.get('nearby_contract_owners', [])) or 'none'}",
            f"- Worker payload digest: {digest_bytes(canonical_payload.encode())}",
            f"- Canonical worker payload: {canonical_payload}",
        ]
    if audit_inputs is not None:
        inputs = asdict(audit_inputs)
        if compact:
            reference = {"schema_version": 1, "metadata_field": "expectation.audit_input_identity", "digest": digest_json(inputs)}
            lines.append(f"- Audit input identity reference: {canonical_json(reference)}")
        else:
            lines.append(f"- Audit input identity: {canonical_json(inputs)}")
    if coverage_reuse is not None:
        lines.append(f"- Coverage reuse reference: {canonical_json(coverage_reference(coverage_reuse))}")
    return "\n".join(lines)
