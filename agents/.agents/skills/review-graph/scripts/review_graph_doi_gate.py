"""Same-source DOI follow-ups can reconcile, but never erase, early failures."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from review_graph_doi import _canonical_report_path, inspect_canonical_recheck, validate_software_doi_resolution
from review_graph_integrity import digest_bytes, digest_json
from review_graph_results import parse_json_object
from review_graph_validation_contracts import object_fields

if TYPE_CHECKING:
    from review_graph_plan import GraphPlan
    from review_graph_validation import ValidationRecord


def _text(raw: object, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"software DOI {label} must be nonempty text")
    return raw


@lru_cache(maxsize=128)
def _failure_record(report_json: str) -> ValidationRecord:
    """Reuse the compiler's immutable record model; filesystem facts are checked at use."""
    from review_graph_validation import ValidationRecord, ValidationStatus  # noqa: PLC0415 - validation models depend on the plan module.

    record = ValidationRecord.from_raw(parse_json_object(report_json))
    if record.status is not ValidationStatus.FAILED:
        msg = "software DOI original record must remain failed"
        raise ValueError(msg)
    return record


@dataclass(frozen=True, slots=True)
class SoftwareDoiRecheck:
    """A new validator bound to one immutable original failed execution."""

    node_id: str
    requirement_id: str
    execution_index: int
    original_report: str
    original_record_json: str

    def __post_init__(self) -> None:
        """Protect direct construction, restoration and replacement from invalid state."""
        for label in ("node_id", "requirement_id", "original_report", "original_record_json"):
            _text(getattr(self, label), label)
        original = self.original
        if type(self.execution_index) is not int or not 0 <= self.execution_index < len(original.executions):
            msg = "software DOI execution index must identify an original failed command"
            raise ValueError(msg)
        execution = original.executions[self.execution_index]
        if execution.result.value != "failed" or str(execution.exit_code) != "1" or self.original_report not in execution.artifact_paths:
            msg = "software DOI binding requires an exit-1 execution and its retained report"
            raise ValueError(msg)

    @property
    def original(self) -> ValidationRecord:
        """Expose typed immutable facts, without a mutable alias to the saved JSON."""
        return _failure_record(self.original_record_json)

    def original_document(self) -> dict[str, Any]:
        """Export detached transport only for the existing DOI report reconciliation API."""
        return parse_json_object(self.original_record_json)

    @classmethod
    def parse(cls, raw: object) -> SoftwareDoiRecheck:
        """Reject malformed persisted relations before inspecting any report."""
        fields = {"node_id", "requirement_id", "execution_index", "original_report", "original_record_json"}
        data = object_fields(raw, "software DOI recheck binding", required=fields)
        index = data["execution_index"]
        if type(index) is not int:
            msg = "software DOI execution index must be an integer"
            raise ValueError(msg)
        return cls(
            _text(data["node_id"], "node_id"),
            _text(data["requirement_id"], "requirement_id"),
            index,
            _text(data["original_report"], "original_report"),
            _text(data["original_record_json"], "original_record_json"),
        )


def validate_rechecks(plan: GraphPlan) -> None:
    """Recheck command, source, and original report bindings when loading plans."""
    units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
    seen: set[tuple[str, int]] = set()
    for binding in plan.software_doi_rechecks:
        unit = units.get(binding.node_id)
        original = binding.original
        identity = (original.evidence_id, binding.execution_index)
        if (
            unit is None
            or identity in seen
            or binding.requirement_id not in unit.requirement_ids
            or original.node_id not in units
            or binding.node_id == original.node_id
            or original.source_state != unit.source_state
            or len(unit.commands) != 1
            or len(unit.working_directories) != 1
            or not unit.required
        ):
            msg = "software DOI recheck differs from its planned source or validator"
            raise ValueError(msg)
        seen.add(identity)
        inspect_canonical_recheck(
            binding.original_document(),
            {"execution_index": binding.execution_index, "original_report": binding.original_report},
            unit.commands[0],
            unit.working_directories[0],
        )


def bound_failure(binding: SoftwareDoiRecheck, state: dict[str, str], latest: dict[str, dict[str, Any]]) -> bool:
    """A follow-up exception applies only to the exact accepted failed record."""
    original = binding.original
    evidence = latest.get(original.node_id, {}).get("evidence") or {}
    return bool(
        state.get(original.node_id) == "accepted"
        and evidence.get("evidence_status") == "failed"
        and evidence.get("evidence_id") == original.evidence_id
        and evidence.get("normalized_record_digest") == digest_json(binding.original_document())
    )


def resolved_records(plan: GraphPlan, records: dict[str, dict[str, Any]]) -> set[str]:
    """Require the existing complete canonical reconciliation before releasing work."""
    groups: dict[str, list[SoftwareDoiRecheck]] = {}
    for binding in plan.software_doi_rechecks:
        groups.setdefault(binding.original.node_id, []).append(binding)
    resolved: set[str] = set()
    for node_id, bindings in groups.items():
        original = bindings[0].original_document()
        if records.get(node_id) != original:
            continue
        checks = []
        for binding in bindings:
            verified = records.get(binding.node_id, {})
            executions = verified.get("executions", [])
            if len(executions) != 1:
                continue
            # The declared output must be the one report captured by this command.
            report = _canonical_report_path(verified, executions[0])
            if report is None:
                continue
            checks.append(
                {
                    "execution_index": binding.execution_index,
                    "original_report": binding.original_report,
                    "verification_evidence_id": verified["evidence_id"],
                    "verification_execution_index": 0,
                    "verification_report": report,
                }
            )
        try:
            validate_software_doi_resolution({"checks": checks}, original, {record["evidence_id"]: record for record in records.values()})
        except OSError, ValueError, KeyError, TypeError:
            continue  # A passing command alone never proves canonical resolution.
        resolved.add(node_id)
    return resolved


def journal_resolutions(plan: GraphPlan, state: dict[str, str], latest: dict[str, dict[str, Any]]) -> set[str]:
    """Bind retained normalized records and output bytes back to the journal."""
    records = {binding.original.node_id: binding.original_document() for binding in plan.software_doi_rechecks if bound_failure(binding, state, latest)}
    for node_id in {binding.node_id for binding in plan.software_doi_rechecks}:
        evidence = latest.get(node_id, {}).get("evidence") or {}
        source = evidence.get("canonical_doi_source")
        if state.get(node_id) != "accepted" or not source:
            continue
        if not isinstance(source, dict) or set(source) != {"metadata_path", "artifact_path"}:
            msg = "invalid canonical DOI journal source"
            raise ValueError(msg)
        metadata = parse_json_object(Path(source["metadata_path"]).read_bytes())
        record = metadata["normalized_record"]
        if (
            digest_json(record) != evidence["normalized_record_digest"]
            or digest_bytes(Path(source["artifact_path"]).read_bytes()) != evidence["artifact_digest"]
            or record["node_id"] != node_id
            or record["evidence_id"] != evidence["evidence_id"]
            or record["status"] != evidence["evidence_status"]
        ):
            msg = "canonical DOI evidence differs from its accepted journal identity"
            raise ValueError(msg)
        records[node_id] = record
    return resolved_records(plan, records)
