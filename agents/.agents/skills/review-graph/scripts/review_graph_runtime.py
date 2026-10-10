"""Materialize, compile, schedule, and verify deterministic review-graph artifacts."""

import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from research_repo_tools.process import ExecutableNotFoundError, format_exception_diagnostics, run_command_bytes
from review_graph_bench import benchmark_identity, benchmark_recipes, equivalent_recipe
from review_graph_bootstrap import bootstrap_document
from review_graph_coverage import combined_findings, coverage_decisions, coverage_execution_view, reused_paths, validate_coverage_units
from review_graph_doi import captured_doi_inputs, captured_software_inputs, inspect_canonical_recheck
from review_graph_executor import executor_permissions, remedied_features
from review_graph_git import audit_git_context, discovery_reconciliation, intervening_metadata_blockers, metadata_audit_blockers, validate_git_dependencies
from review_graph_independent import CHECK_LABELS, SCHEMA as _INDEPENDENT_PAYLOAD_SCHEMA, render_independent_payload
from review_graph_integrity import canonical_json, digest_bytes
from review_graph_metrics import projected_waves, source_demand
from review_graph_phases import pending_validation_barrier, phase_accounting, require_validation_barrier, validate_validation_barrier
from review_graph_plan import (
    _COMPACT_ROUTING_OVERRIDE_FIELDS,
    DEFAULT_ROUTING_CATALOG,
    DEFAULT_SKILL_ROOT,
    EVIDENCE_SCHEMA_VERSION,
    MAX_NATIVE_RESULT_BYTES,
    MAX_NATIVE_SECTION_BYTES,
    NATIVE_EVIDENCE_BLOCK_CLOSE,
    NATIVE_EVIDENCE_BLOCK_OPEN,
    VALIDATION_ARTIFACT_DIGEST_MODES,
    ArtifactPayload,
    ExecutionEpoch,
    FingerprintEvidence,
    GraphPlan,
    RepositoryReviewProof,
    ReusedReviewEvidencePlan,
    ReviewEvidence,
    ReviewEvidenceExpectation,
    RoutingDecision,
    RoutingDiscovery,
    TrustedArtifactVerifier,
    ValidationArtifact,
    ValidationEvidence,
    ValidationEvidenceExpectation,
    ValidationEvidenceMapping,
    ValidationExclusion,
    ValidationRequirement,
    ValidationUnit,
    WorkerBudget,
    WorkerNode,
    _bind_worker_node_provenance,
    _file_identity_digest,
    _native_field_values,
    _native_fingerprint_proof_blockers,
    _native_heading_blockers,
    _native_mutation_blockers,
    _native_record_fields,
    _native_records,
    _native_repository_path_list,
    _native_section_bodies,
    _normalized_repository_paths,
    _partition_execution_epochs,
    _review_native_result_blockers,
    _schedule_with_validation_barrier,
    _synthesis_reused_evidence_ids,
    _validation_environment_identity,
    _validation_ledger_expected_fields,
    _validation_native_result_blockers,
    _validation_nodes,
    _validation_plan_expected_body,
    _validation_requirements_expected_body,
    _verified_artifact_status,
    assess_evidence_bundle,
    assess_review_evidence,
    assess_validation_evidence,
    build_routing_projection,
    coalesce_review_requirements,
    coalesce_validation_requirements,
    create_artifact_manifest,
    graph_plan_digest,
    graph_plan_digest_matches,
    load_routing_catalog,
    plan_from_document,
    repository_review_proof_expectation,
    review_requirements_from_routing,
    review_source_state_blockers,
    validation_command_field,
    validation_evidence_expectation,
    validation_execution_result_blockers,
    validation_requirements_from_document,
)
from review_graph_preflight import inspect_executor_executables
from review_graph_provenance import review_scope_body, worker_payload_reference
from review_graph_receipts import stage_receipt
from review_graph_reuse import (
    SNAPSHOT_FORMAT,
    AuditInputIdentity,
    AuditReuseTransition,
    ExternalMetadataTransition,
    metadata_states,
    metadata_transition,
    source_snapshot,
    verify_reuse_inputs,
)
from review_graph_scheduling import select_execution_lanes
from review_graph_schema import SchemaValidationError, require_schema, require_schema_definition
from review_graph_synthesis import synthesis_fields, validate_synthesis
from review_graph_usage import digest as usage_digest, measure_call

if TYPE_CHECKING:
    from collections.abc import Iterable

_READ_ONLY_MODES = frozenset({"audit", "revalidation", "synthesis"})
_REVIEW_MODES = _READ_ONLY_MODES | {"fix"}
_REVIEW_STATUSES = frozenset({"blocked", "completed", "no-findings"})
_SEVERITIES = frozenset({"P0", "P1", "P2", "P3"})
_JOURNAL_STATUSES = frozenset({"accepted", "awaiting-replan", "blocked", "in-flight", "invalidated"})
_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references" / "schemas"
_PLANNING_INPUT_SCHEMA = _SCHEMA_ROOT / "planning-input-v1.schema.json"
_REVIEW_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "review-payload-v1.schema.json"
_SYNTHESIS_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "synthesis-payload-v1.schema.json"
_VALIDATION_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "validation-payload-v2.schema.json"
_RUNTIME_OPERATION_INPUT_SCHEMA = _SCHEMA_ROOT / "runtime-operation-inputs-v1.schema.json"
_RUNTIME_OPERATION_EXAMPLES = Path(__file__).resolve().parents[1] / "references" / "runtime-operation-examples-v1.json"
_INITIAL_JOURNAL_HELP = (
    "execution JSONL path; a missing or zero-byte file is an empty journal, while any nonempty file must contain canonical records without blank lines"
)
_COMPILER_BY_MODE = {
    "audit": "compile-review",
    "fix": "compile-review",
    "independent-review": "compile-independent-review",
    "revalidation": "compile-review",
    "synthesis": "compile-review",
    "validation": "compile-validation",
}
_INDEPENDENT_NATIVE_SECTIONS = ("## Scope Inspected", "## Findings", "## No-Finding Evidence", "## Routing Handoffs", "## Fingerprint Proof", "## Git State")
_JOURNAL_EVENT_KEYS = frozenset(
    {
        "affected_node_ids",
        "event_digest",
        "evidence",
        "node_id",
        "plan_digest",
        "previous_event_digest",
        "reason",
        "schema_version",
        "sequence",
        "source_state",
        "status",
    }
)
_JOURNAL_EVIDENCE_KEYS = frozenset({"artifact_digest", "artifact_id", "evidence_id", "evidence_status", "normalized_record_digest"})
_BOUNDED_WORKSPACE_DIRECTORY_NAMES = frozenset(
    {".cache", ".gradle", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".venv", "build", "node_modules", "target"}
)
_BOUNDED_WORKSPACE_ENTRY_LIMIT = 256
_BOUNDED_WORKSPACE_POLICY = "bounded-directory-metadata-v3"
_RECURSIVE_WORKSPACE_POLICY = "recursive-content-sha256-v2"
_SCHEMA_ID_VERSION_RE = re.compile(r"(?P<name>[^/]+)-v(?P<version>[1-9][0-9]*)\.schema\.json\Z")
_PLANNED_VALIDATION_IDENTITY_KEYS = frozenset(
    {
        "allowed_artifacts",
        "artifact_owner",
        "baseline",
        "canonical_recipe",
        "capture_command",
        "captured_paths",
        "commands",
        "dependency_policy",
        "environment",
        "execution_strategy",
        "expected_workspace_effects",
        "features",
        "independence_basis",
        "isolation_root",
        "mutation_lock",
        "planning_blocker",
        "platform",
        "requested_scope",
        "required",
        "requires_isolation",
        "source_state",
        "toolchain",
        "working_directories",
    }
)
_PLANNED_VALIDATION_REFERENCE_KEYS = frozenset({"expected_evidence", "owner", "planned_validation_digest", "reason", "requirement_id"})
_LEGACY_VALIDATION_REQUIREMENT_KEYS = frozenset(
    {"commands", "dependency_policy", "environment", "expected_evidence", "owner", "reason", "requirement_id", "working_directory"}
)


@dataclass(frozen=True)
class JournalEventRequest:
    """Runtime facts for one coordinator-owned lifecycle transition."""

    node_id: str
    status: str
    source: dict[str, Any] | None = None
    reason: str | None = None


class WorkerPayloadWriteError(OSError):
    """Preserve validated artifact evidence when review storage or payload publication fails."""

    def __init__(self, message: str, artifact_write_review: dict[str, Any], review_reference: dict[str, Any] | None = None) -> None:
        """Attach the safety review and any persisted evidence to the write failure."""
        super().__init__(message)
        self.artifact_write_review = artifact_write_review
        self.review_reference = review_reference


def _read_regular_file_no_follow(path: Path) -> bytes:
    """Read an existing regular file without following a replaceable symlink."""
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        msg = f"immutable artifact target must be a regular non-symlink file: {path}"
        raise ValueError(msg) from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            msg = f"immutable artifact target must be a regular non-symlink file: {path}"
            raise ValueError(msg)
        stream = os.fdopen(descriptor, "rb")
        descriptor = -1
        with stream:
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes_once(path: Path, content: bytes) -> None:
    """Create an immutable artifact, permitting only an identical replay."""
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if _read_regular_file_no_follow(path) != content:
            msg = f"refusing to overwrite non-identical artifact: {path}"
            raise ValueError(msg) from None


def _write_text_once(path: Path, content: str) -> None:
    _write_bytes_once(path, content.encode("utf-8"))


def _write_bytes_atomically_once(path: Path, content: bytes, *, mode: int) -> bool:
    """Atomically create immutable content and report whether this call published it."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    created = False
    completed = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        try:
            path.hardlink_to(temporary_path)
            created = True
        except FileExistsError:
            if _read_regular_file_no_follow(path) != content:
                msg = f"refusing to overwrite non-identical immutable artifact: {path}"
                raise ValueError(msg) from None
        if created:
            _fsync_directory(path.parent)
        completed = True
        return created
    finally:
        temporary_path.unlink(missing_ok=True)
        if created and not completed:
            path.unlink(missing_ok=True)


def _queue_materialized_write(pending: dict[Path, tuple[bytes, int]], path: Path, content: bytes, *, mode: int) -> None:
    """Queue one immutable materialization output without touching its final store."""
    existing = pending.get(path)
    candidate = (content, mode)
    if existing is not None and existing != candidate:
        msg = f"materialization produced conflicting content for immutable artifact: {path}"
        raise ValueError(msg)
    pending[path] = candidate


def _publish_materialized_writes(artifact_store: Path, pending: dict[Path, tuple[bytes, int]]) -> bool:
    """Stage a complete materialization and report whether a new store was published."""
    artifact_store.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{artifact_store.name}.materialize.", dir=artifact_store.parent))
    try:
        for final_path, (content, mode) in pending.items():
            try:
                relative = final_path.relative_to(artifact_store)
            except ValueError:
                msg = f"materialized artifact escapes its requested store: {final_path}"
                raise ValueError(msg) from None
            staged_path = staging_root / relative
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            _write_bytes_atomically_once(staged_path, content, mode=mode)

        if artifact_store.exists() and not artifact_store.is_dir():
            msg = f"artifact_store is not a directory: {artifact_store}"
            raise ValueError(msg)
        # Check every conflict before publishing any new immutable output. This
        # keeps corrected retries safe even when a prior store already exists.
        for final_path, (content, _mode) in pending.items():
            if final_path.exists() and _read_regular_file_no_follow(final_path) != content:
                msg = f"refusing to overwrite non-identical immutable artifact: {final_path}"
                raise ValueError(msg)

        if not artifact_store.exists() or not any(artifact_store.iterdir()):
            if artifact_store.exists():
                artifact_store.rmdir()
            staging_root.rename(artifact_store)
            try:
                _fsync_directory(artifact_store.parent)
            except OSError:
                artifact_store.rename(staging_root)
                raise
            return True
        missing = tuple(final_path for final_path in pending if not final_path.exists())
        if missing:
            msg = "existing materialization store is incomplete; refusing a partial immutable publish: " + ", ".join(map(str, missing))
            raise ValueError(msg)
        return False
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _publish_materialization_with_result(
    artifact_store: Path, pending: dict[Path, tuple[bytes, int]], operation_output_path: Path, output: dict[str, Any]
) -> None:
    """Publish a CLI result and its immutable store as one rollback-safe operation."""
    output_path = operation_output_path.absolute()
    output_bytes = (json.dumps(output, indent=2, sort_keys=True) + "\n").encode()
    _preflight_compile_destination(output_path, output_bytes)
    resolved_output_path = output_path.resolve()
    if resolved_output_path == artifact_store or resolved_output_path.is_relative_to(artifact_store):
        msg = "materialize-dispatches operation-result path must be outside the artifact store"
        raise ValueError(msg)
    output_created = _write_bytes_atomically_once(output_path, output_bytes, mode=0o444)
    materialization_completed = False
    try:
        _publish_materialized_writes(artifact_store, pending)
        materialization_completed = True
    finally:
        if not materialization_completed and output_created:
            output_path.unlink()
            _fsync_directory(output_path.parent)


def _required_text(item: dict[str, Any], name: str) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value.strip() or "\n" in value:
        msg = f"{name} must be one non-empty line"
        raise ValueError(msg)
    return value


def _defaulted_text(item: dict[str, Any], name: str, default: str) -> str:
    value = item.get(name, default)
    if not isinstance(value, str) or not value.strip() or "\n" in value:
        msg = f"{name} must be one non-empty line"
        raise ValueError(msg)
    return value


def _required_bool(item: dict[str, Any], name: str) -> bool:
    value = item.get(name)
    if not isinstance(value, bool):
        msg = f"{name} must be a boolean"
        raise TypeError(msg)
    return value


def _required_int(item: dict[str, Any], name: str) -> int:
    value = item.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{name} must be an integer"
        raise TypeError(msg)
    return value


def _text_list(item: dict[str, Any], name: str, *, required: bool = False) -> tuple[str, ...]:
    value = item.get(name, [])
    if not isinstance(value, list) or any(not isinstance(entry, str) or not entry.strip() for entry in value):
        msg = f"{name} must be a list of non-empty strings"
        raise ValueError(msg)
    if required and not value:
        msg = f"{name} must not be empty"
        raise ValueError(msg)
    return tuple(cast("list[str]", value))


def _records(item: dict[str, Any], name: str) -> tuple[dict[str, Any], ...]:
    value = item.get(name, [])
    if not isinstance(value, list) or any(not isinstance(entry, dict) for entry in value):
        msg = f"{name} must be a list of objects"
        raise ValueError(msg)
    return tuple(value)


def _state(item: dict[str, Any], name: str) -> tuple[str, str, str]:
    value = _text_list(item, name)
    if len(value) != 3:
        msg = f"{name} must contain scope, worktree, and repository-state fingerprints"
        raise ValueError(msg)
    return value


def _finding_records(payload: dict[str, Any], node_id: str) -> tuple[tuple[str, dict[str, Any]], ...]:
    records: list[tuple[str, dict[str, Any]]] = []
    for ordinal, finding in enumerate(_records(payload, "findings"), start=1):
        severity = _required_text(finding, "severity")
        if severity not in _SEVERITIES:
            msg = f"finding {ordinal} has invalid severity {severity}"
            raise ValueError(msg)
        for field_name in ("location", "summary", "evidence", "remediation"):
            _required_text(finding, field_name)
        records.append((f"{node_id}-finding-{ordinal}", finding))
    return tuple(records)


def _validation_records(payload: dict[str, Any]) -> tuple[tuple[str, dict[str, Any]], ...]:
    records: list[tuple[str, dict[str, Any]]] = []
    for requirement in _records(payload, "validation_requirements"):
        requirement_id = _required_text(requirement, "requirement_id")
        for field_name in ("owner", "reason", "expected_evidence"):
            _required_text(requirement, field_name)
        if "planned_validation_digest" in requirement:
            if frozenset(requirement) != _PLANNED_VALIDATION_REFERENCE_KEYS:
                msg = f"planned validation reference {requirement_id} must contain only its ID, digest, owner, reason, and expected evidence"
                raise ValueError(msg)
            _sha256_digest(_required_text(requirement, "planned_validation_digest"), "planned validation digest")
        else:
            if frozenset(requirement) != _LEGACY_VALIDATION_REQUIREMENT_KEYS:
                msg = f"validation requirement {requirement_id} must contain the complete legacy execution identity"
                raise ValueError(msg)
            for field_name in ("working_directory", "environment", "dependency_policy"):
                _required_text(requirement, field_name)
            _text_list(requirement, "commands", required=True)
        records.append((requirement_id, requirement))
    identifiers = tuple(requirement_id for requirement_id, _ in records)
    if len(identifiers) != len(set(identifiers)):
        msg = "validation requirement IDs must be unique"
        raise ValueError(msg)
    return tuple(records)


def _handoff_records(payload: dict[str, Any], node_id: str) -> tuple[tuple[str, dict[str, Any]], ...]:
    records: list[tuple[str, dict[str, Any]]] = []
    for ordinal, handoff in enumerate(_records(payload, "handoffs"), start=1):
        for field_name in ("catalog_id", "observed_trigger", "reason"):
            _required_text(handoff, field_name)
        _text_list(handoff, "scope", required=True)
        records.append((f"{node_id}-handoff-{ordinal}", handoff))
    return tuple(records)


def _review_header(expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> str:
    return "\n".join(
        (
            f"- Node ID: {evidence.node_id}",
            f"- Skill: {evidence.skill_id}",
            f"- Mode: {evidence.mode}",
            f"- Evidence schema version: {EVIDENCE_SCHEMA_VERSION}",
            f"- Execution profile: {evidence.execution_profile}",
            f"- Execution location: {evidence.execution_location}",
            f"- Status: {evidence.status}",
            f"- Selection reason: {expectation.selection_reason}",
            f"- Scope fingerprint: {evidence.fingerprints.expected[0]}",
            f"- Worktree fingerprint: {evidence.fingerprints.expected[1]}",
            f"- Repository state fingerprint: {evidence.fingerprints.expected[2]}",
            f"- Authorization: {expectation.authorization}",
        )
    )


def _state_verification(dispatch: dict[str, Any], evidence: ReviewEvidence, changed_paths: tuple[str, ...]) -> str:
    before_result = "blocked" if evidence.status == "blocked" else "matched"
    after_result = "blocked" if evidence.status == "blocked" else "changed-as-reported" if evidence.source_mutated else "matched"
    return "\n".join(
        (
            f"- Command: {_required_text(dispatch, 'state_verification_command')}",
            "- Before:",
            f"  - Observed scope fingerprint: {evidence.fingerprints.before[0]}",
            f"  - Observed worktree fingerprint: {evidence.fingerprints.before[1]}",
            f"  - Observed repository state fingerprint: {evidence.fingerprints.before[2]}",
            f"  - Result: {before_result}",
            "- After:",
            f"  - Observed scope fingerprint: {evidence.fingerprints.after[0]}",
            f"  - Observed worktree fingerprint: {evidence.fingerprints.after[1]}",
            f"  - Observed repository state fingerprint: {evidence.fingerprints.after[2]}",
            f"  - Result: {after_result}",
            f"- Changed repository paths: {', '.join(changed_paths) or 'none'}",
            f"- HEAD, branch, or index mutated: {'yes' if evidence.git_mutated else 'no'}",
            *(
                (f"- External metadata transitions: {canonical_json([asdict(item) for item in evidence.fingerprints.metadata_transitions])}",)
                if evidence.fingerprints.metadata_transitions
                else ()
            ),
        )
    )


def _findings_body(findings: tuple[tuple[str, dict[str, Any]], ...]) -> str:
    if not findings:
        return "none"
    return "\n".join(
        "\n".join(
            (
                f"- ID: {finding_id}",
                f"  - Severity: {finding['severity']}",
                f"  - Location: {finding['location']}",
                f"  - Summary: {finding['summary']}",
                f"  - Evidence: {finding['evidence']}",
                f"  - Remediation: {finding['remediation']}",
            )
        )
        for finding_id, finding in findings
    )


def _validation_body(records: tuple[tuple[str, dict[str, Any]], ...]) -> str:
    if not records:
        return "none"
    rendered: list[str] = []
    for requirement_id, record in records:
        if "planned_validation_digest" in record:
            identity = (f"  - Planned validation digest: {record['planned_validation_digest']}", "  - Execution identity: dispatch-planned validation unit")
        else:
            identity = (
                f"  - Commands: {' && '.join(record['commands'])}",
                f"  - Working directories: {record['working_directory']}",
                f"  - Environment/configuration: {record['environment']}",
                f"  - Dependency policy: {record['dependency_policy']}",
            )
        rendered.append(
            "\n".join(
                (
                    f"- Requirement ID: {requirement_id}",
                    f"  - Owner: {record['owner']}",
                    f"  - Reason: {record['reason']}",
                    *identity,
                    f"  - Expected evidence: {record['expected_evidence']}",
                    "  - Disposition: required",
                    "  - Ledger evidence: none",
                )
            )
        )
    return "\n".join(rendered)


def _handoffs_body(records: tuple[tuple[str, dict[str, Any]], ...]) -> str:
    if not records:
        return "none"
    return "\n".join(
        "\n".join(
            (
                f"- Handoff ID: {handoff_id}",
                f"  - Catalog ID: {record['catalog_id']}",
                f"  - Observed trigger: {record['observed_trigger']}",
                f"  - Reason: {record['reason']}",
                f"  - Scope: {', '.join(record['scope'])}",
            )
        )
        for handoff_id, record in records
    )


def _changes_body(payload: dict[str, Any], evidence: ReviewEvidence, changed_paths: tuple[str, ...]) -> str:
    changes = _records(payload, "changes")
    if not evidence.source_mutated:
        if changes:
            msg = "read-only payload cannot contain changes"
            raise ValueError(msg)
        return "none"
    if not changes:
        msg = "source-mutating payload requires change records"
        raise TypeError(msg)
    reported_paths: list[str] = []
    bodies: list[str] = []
    for ordinal, change in enumerate(changes, start=1):
        finding_ids = _text_list(change, "finding_ids", required=True)
        files = _text_list(change, "files", required=True)
        for field_name in ("what_changed", "why", "contract_preserved"):
            _required_text(change, field_name)
        reported_paths.extend(files)
        bodies.append(
            "\n".join(
                (
                    f"- Change ID: {evidence.node_id}-change-{ordinal}",
                    f"  - Finding IDs: {', '.join(finding_ids)}",
                    f"  - Files: {', '.join(files)}",
                    f"  - What changed: {change['what_changed']}",
                    f"  - Why: {change['why']}",
                    f"  - Contract preserved: {change['contract_preserved']}",
                )
            )
        )
    if tuple(dict.fromkeys(reported_paths)) != changed_paths:
        msg = "change record files must equal changed_paths in first-seen order"
        raise TypeError(msg)
    return "\n".join(bodies)


def _predecessor_body(dispatch: dict[str, Any], evidence: ReviewEvidence) -> str:
    if evidence.mode != "synthesis":
        return "none"
    node_ids = _text_list(dispatch, "predecessor_node_ids")
    if node_ids and len(node_ids) != len(evidence.predecessor_evidence_ids):
        msg = "predecessor_node_ids must align with predecessor_evidence_ids"
        raise ValueError(msg)
    if not node_ids:
        node_ids = tuple(f"evidence:{evidence_id}" for evidence_id in evidence.predecessor_evidence_ids)
    return (
        "\n".join(
            f"- Node: {node_id}\n  - Disposition: consumed\n  - Contribution: normalized accepted evidence {evidence_id}"
            for node_id, evidence_id in zip(node_ids, evidence.predecessor_evidence_ids, strict=True)
        )
        or "none"
    )


def _review_normalized_record(payload: dict[str, Any], expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> dict[str, Any]:
    findings = _finding_records({**payload, "findings": combined_findings(payload, expectation.coverage_reuse)}, evidence.node_id)
    validations = _validation_records(payload)
    handoffs = _handoff_records(payload, evidence.node_id)
    changes = tuple({"change_id": f"{evidence.node_id}-change-{ordinal}", **change} for ordinal, change in enumerate(_records(payload, "changes"), start=1))
    inherited_context = (expectation.coverage_reuse or {}).get("original_audit_context", {})
    return {
        **(synthesis_fields(payload) if evidence.mode == "synthesis" else {}),
        **({"coverage_units": payload["coverage_units"]} if "coverage_units" in payload else {}),
        **({"coverage_reuse": expectation.coverage_reuse} if expectation.coverage_reuse is not None else {}),
        **{key: payload[key] for key in ("execution_facts", "validation_limits", "unresolved_uncertainties") if key in payload},
        **(
            {"inherited_audit_context": {**inherited_context, "evidence_id": expectation.coverage_reuse["evidence_id"]}}
            if inherited_context and expectation.coverage_reuse is not None
            else {}
        ),
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": evidence.raw_result_artifact_id,
        "changes": list(changes),
        "command_policy_attested": payload.get("command_policy_attested", False),
        **({"git_sensitive": payload["git_sensitive"]} if "git_sensitive" in payload else {}),
        **({"git_dependencies": payload["git_dependencies"]} if "git_dependencies" in payload else {}),
        "commands_executed": list(_text_list(payload, "commands_executed")),
        "evidence_id": evidence.evidence_id,
        "files_inspected": list(_text_list(payload, "files_inspected")),
        "observed_source_state": list(evidence.fingerprints.after),
        "findings": [{"finding_id": finding_id, **finding} for finding_id, finding in findings],
        "handoffs": [{"handoff_id": handoff_id, **handoff} for handoff_id, handoff in handoffs],
        "limitations": list(_text_list(payload, "limitations")),
        "scope_limitations": [{"path": path, "reason": reason} for path, reason in _scope_limitation_records(payload)],
        "mode": evidence.mode,
        "node_id": evidence.node_id,
        "nearby_contract_owners": list(_text_list(payload, "nearby_contract_owners")),
        "payload_digest": digest_bytes(canonical_json(payload).encode()),
        "record_type": "review",
        "requirement_ids": list(evidence.requirement_ids),
        "selection_reason": expectation.selection_reason,
        "skill_id": evidence.skill_id,
        "status": evidence.status,
        "validation_requirements": [{"requirement_id": requirement_id, **requirement} for requirement_id, requirement in validations],
    }


def _review_command_policy_blockers(dispatch: dict[str, Any], payload: dict[str, Any]) -> tuple[str, ...]:
    attested = payload.get("command_policy_attested")
    commands = _text_list(payload, "commands_executed")
    raw_policy = dispatch.get("command_policy")
    if raw_policy is None:
        return () if attested is None or attested is True else ("review payload must attest to the dispatched command policy",)
    if not isinstance(raw_policy, dict):
        return ("review dispatch command_policy must be an object",)
    if attested is not True:
        return ("review payload must attest to the dispatched command policy",)
    prohibited = set(_text_list(raw_policy, "prohibited_commands"))
    duplicates = tuple(command for command in commands if command in prohibited)
    if duplicates:
        return ("review payload executed commands owned by planned validators: " + ", ".join(duplicates),)
    if dispatch.get("fresh_context") is True:
        forbidden = _text_list(dispatch, "fresh_context_forbidden_artifacts")
        violations = tuple(f"{command} -> {path}" for command in commands for path in forbidden if path in command)
        if violations:
            return ("fresh-context review read another node's worker/report/evidence artifact: " + "; ".join(violations),)
    return ()


def _planned_validation_identity(unit: ValidationUnit) -> dict[str, Any]:
    """Return the exact non-narrative identity used to coalesce validator work."""
    return {
        "allowed_artifacts": [asdict(artifact) for artifact in unit.allowed_artifacts],
        "artifact_owner": unit.artifact_owner,
        "baseline": unit.baseline,
        "canonical_recipe": unit.canonical_recipe,
        "capture_command": unit.capture_command,
        "captured_paths": list(unit.captured_paths),
        "commands": list(unit.commands),
        "dependency_policy": unit.dependency_policy,
        "environment": unit.environment,
        "execution_strategy": unit.execution_strategy,
        "expected_workspace_effects": list(unit.expected_workspace_effects),
        "features": list(unit.features),
        "independence_basis": unit.independence_basis,
        "isolation_root": unit.isolation_root,
        "mutation_lock": unit.mutation_lock,
        "planning_blocker": unit.planning_blocker,
        "platform": unit.platform,
        "requested_scope": unit.requested_scope,
        "required": unit.required,
        "requires_isolation": unit.requires_isolation,
        "source_state": list(unit.source_state),
        "toolchain": unit.toolchain,
        "working_directories": list(unit.working_directories),
    }


def _planned_validation_digest(unit: ValidationUnit) -> str:
    return digest_bytes(canonical_json(_planned_validation_identity(unit)).encode())


def _planned_validation_units(plan: GraphPlan) -> list[dict[str, Any]]:
    return [
        {
            "execution_identity": _planned_validation_identity(unit),
            "planned_validation_digest": _planned_validation_digest(unit),
            "requirement_ids": list(unit.requirement_ids),
            "validation_unit_id": unit.node_id,
        }
        for unit in sorted(plan.coalesced_validation_units, key=lambda item: item.node_id)
    ]


def _validation_identity_summary(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: identity[key] for key in ("commands", "working_directories", "requested_scope", "platform", "required")},
        "captured_path_count": len(identity["captured_paths"]),
    }


def _resolve_planned_validation_record(record: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {"execution_identity_reference", "execution_summary", "planned_validation_digest", "requirement_ids", "validation_unit_id"}
    if set(record) != expected_keys:
        msg = "planned validation reference contains missing or unknown fields"
        raise ValueError(msg)
    reference = record["execution_identity_reference"]
    if not isinstance(reference, dict) or set(reference) != {"path", "digest"}:
        msg = "planned validation identity reference requires path and digest"
        raise ValueError(msg)
    path = Path(_required_text(reference, "path"))
    if not path.is_absolute():
        msg = "planned validation identity reference path must be absolute"
        raise ValueError(msg)
    content = _read_regular_file_no_follow(path)
    if digest_bytes(content) != reference["digest"] or reference["digest"] != record["planned_validation_digest"]:
        msg = "planned validation identity sidecar digest mismatch"
        raise ValueError(msg)
    identity = json.loads(content)
    if not isinstance(identity, dict) or set(identity) != _PLANNED_VALIDATION_IDENTITY_KEYS:
        msg = "planned validation identity sidecar is incomplete"
        raise ValueError(msg)
    if record["execution_summary"] != _validation_identity_summary(identity):
        msg = "planned validation summary differs from its bound identity"
        raise ValueError(msg)
    return {**{key: record[key] for key in ("planned_validation_digest", "requirement_ids", "validation_unit_id")}, "execution_identity": identity}


def _dispatched_planned_validations(dispatch: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    raw_policy = dispatch.get("command_policy")
    if raw_policy is None:
        return {}
    if not isinstance(raw_policy, dict):
        msg = "review dispatch command_policy must be an object"
        raise TypeError(msg)
    by_requirement: dict[str, tuple[str, str, dict[str, Any]]] = {}
    unit_ids: set[str] = set()
    for raw_record in _records(raw_policy, "planned_validation_units"):
        record = _resolve_planned_validation_record(raw_record)
        if frozenset(record) != frozenset({"execution_identity", "planned_validation_digest", "requirement_ids", "validation_unit_id"}):
            msg = "planned validation unit dispatch records must contain only unit ID, requirement IDs, identity, and digest"
            raise ValueError(msg)
        unit_id = _required_text(record, "validation_unit_id")
        if unit_id in unit_ids:
            msg = f"planned validation unit dispatch contains duplicate unit ID {unit_id}"
            raise ValueError(msg)
        unit_ids.add(unit_id)
        requirement_ids = _text_list(record, "requirement_ids", required=True)
        identity = record.get("execution_identity")
        if not isinstance(identity, dict) or frozenset(identity) != _PLANNED_VALIDATION_IDENTITY_KEYS:
            msg = f"planned validation unit {unit_id} has an incomplete execution identity"
            raise ValueError(msg)
        digest = _required_text(record, "planned_validation_digest")
        _sha256_digest(digest, "planned validation digest")
        if digest != digest_bytes(canonical_json(identity).encode()):
            msg = f"planned validation unit {unit_id} digest does not match its execution identity"
            raise ValueError(msg)
        for requirement_id in requirement_ids:
            if requirement_id in by_requirement:
                msg = f"planned validation dispatch maps requirement {requirement_id} more than once"
                raise ValueError(msg)
            by_requirement[requirement_id] = (unit_id, digest, identity)
    return by_requirement


def _review_validation_requirement_blockers(dispatch: dict[str, Any], validations: tuple[tuple[str, dict[str, Any]], ...]) -> tuple[str, ...]:
    try:
        planned = _dispatched_planned_validations(dispatch)
    except (OSError, TypeError, ValueError) as error:
        return (str(error),)
    blockers: list[str] = []
    for requirement_id, requirement in validations:
        planned_record = planned.get(requirement_id)
        if "planned_validation_digest" in requirement:
            if planned_record is None:
                blockers.append(f"validation requirement {requirement_id} references an unplanned validation identity")
            elif requirement["planned_validation_digest"] != planned_record[1]:
                blockers.append(f"validation requirement {requirement_id} planned validation digest conflicts with its dispatch")
            continue
        if planned_record is None:
            continue
        identity = planned_record[2]
        matches = (
            identity["commands"] == list(_text_list(requirement, "commands"))
            and identity["working_directories"] == [requirement["working_directory"]] * len(cast("list[str]", identity["commands"]))
            and identity["environment"] == requirement["environment"]
            and identity["dependency_policy"] == requirement["dependency_policy"]
            and identity["required"] is True
        )
        if not matches:
            blockers.append(f"validation requirement {requirement_id} restates a conflicting planned validation identity")
    return tuple(blockers)


def _review_handoff_catalog_blockers(dispatch: dict[str, Any], handoffs: tuple[tuple[str, dict[str, Any]], ...]) -> tuple[str, ...]:
    raw_catalog_ids = dispatch.get("handoff_catalog_ids")
    if raw_catalog_ids is None:
        catalog_ids = {entry.catalog_id for entry in load_routing_catalog(DEFAULT_ROUTING_CATALOG, skill_roots=(DEFAULT_SKILL_ROOT,))}
    else:
        catalog_ids = set(_text_list(dispatch, "handoff_catalog_ids"))
    unknown = tuple(sorted({_required_text(record, "catalog_id") for _handoff_id, record in handoffs} - catalog_ids))
    return ("review payload contains unknown handoff catalog IDs: " + ", ".join(unknown),) if unknown else ()


def _scope_limitation_records(payload: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    records: list[tuple[str, str]] = []
    for ordinal, record in enumerate(_records(payload, "scope_limitations"), start=1):
        if set(record) != {"path", "reason"}:
            msg = f"scope limitation {ordinal} must contain only path and reason"
            raise ValueError(msg)
        records.append((_required_text(record, "path"), _required_text(record, "reason")))
    return tuple(records)


def _review_scope_coverage_blockers(dispatch: dict[str, Any], payload: dict[str, Any], *, status: str) -> tuple[str, ...]:
    """Bind audit completion claims to the exact paths owned by the dispatch."""
    mode = _required_text(dispatch, "mode")
    limitations = _scope_limitation_records(payload)
    if mode != "audit":
        return ("scope_limitations apply only to audit payloads",) if limitations else ()
    owned_paths = _text_list(dispatch, "owned_paths", required=True)
    inspected_paths = _text_list(payload, "files_inspected")
    blockers: list[str] = []
    if len(owned_paths) != len(set(owned_paths)):
        blockers.append("audit dispatch owned_paths must be unique")
    if len(inspected_paths) != len(set(inspected_paths)):
        blockers.append("audit files_inspected must be unique")
    owned = set(owned_paths)
    inspected = set(inspected_paths)
    reused = set(reused_paths(dispatch.get("coverage_reuse")))
    if reused - owned or reused & inspected:
        blockers.append("delta audit must inspect only recheck paths and preserve its bound reused coverage")
    outside = tuple(path for path in inspected_paths if path not in owned)
    if outside:
        blockers.append("audit files_inspected contains paths outside dispatch ownership: " + ", ".join(outside))
    limitation_paths = tuple(path for path, _reason in limitations)
    if len(limitation_paths) != len(set(limitation_paths)):
        blockers.append("audit scope_limitations paths must be unique")
    invalid_limitations = tuple(path for path in limitation_paths if path not in owned or path in inspected)
    if invalid_limitations:
        blockers.append("audit scope_limitations must name omitted owned paths: " + ", ".join(invalid_limitations))
    omitted = tuple(path for path in owned_paths if path not in inspected | reused)
    if status == "no-findings" and omitted:
        blockers.append("audit no-findings requires inspection of every owned path; omitted: " + ", ".join(omitted))
    elif status == "completed" and set(limitation_paths) != set(omitted):
        missing = tuple(path for path in omitted if path not in set(limitation_paths))
        extra = tuple(path for path in limitation_paths if path not in set(omitted))
        detail = ", ".join((*missing, *extra)) or "scope limitation mismatch"
        blockers.append("completed audit must provide one structured scope limitation for every omitted owned path: " + detail)
    return tuple(blockers)


def _compiled_audit_inputs(dispatch: dict[str, Any], payload: dict[str, Any]) -> AuditInputIdentity | None:
    if dispatch["mode"] != "audit":
        return None
    instruction_paths = _text_list(dispatch, "instruction_paths")
    instruction_digests = tuple((path, _file_identity_digest(path)) for path in instruction_paths)
    if "instruction_digests" in dispatch and instruction_digests != _string_pairs(dispatch, "instruction_digests"):
        msg = "audit instructions changed since materialization"
        raise ValueError(msg)
    return AuditInputIdentity(
        _text_list(dispatch, "owned_paths"), _text_list(payload, "files_inspected"), _text_list(payload, "nearby_contract_owners"), instruction_digests
    )


def _validate_review_coverage_partitions(dispatch: dict[str, Any], payload: dict[str, Any]) -> None:
    """Apply the same partition contract before publication and compilation."""
    if not payload.get("coverage_units"):
        return
    if dispatch.get("mode") != "audit" or dispatch.get("coverage_reuse") is not None:
        msg = "coverage partitions apply only to complete fresh audits"
        raise ValueError(msg)
    require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
    validate_coverage_units(payload, _text_list(dispatch, "owned_paths"))


def _validate_audit_caveats(dispatch: dict[str, Any], payload: dict[str, Any]) -> None:
    """Retain typed attestations and reject contradictions with dispatch facts."""
    if not any(key in payload for key in ("execution_facts", "validation_limits", "unresolved_uncertainties", "git_dependencies")):
        return
    if dispatch.get("mode") != "audit":
        msg = "typed audit caveats apply only to audit payloads"
        raise ValueError(msg)
    require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
    validate_git_dependencies(payload)
    facts = payload.get("execution_facts", [])
    policy = dispatch.get("command_policy")
    planned_commands = (
        set(_text_list(policy, "prohibited_commands")) | set(_text_list(policy, "validator_owned_commands")) if isinstance(policy, dict) else set()
    )
    if "validators-not-executed" in facts and planned_commands.intersection(payload["commands_executed"]):
        msg = "validators-not-executed contradicts the planned validator command ledger"
        raise ValueError(msg)
    if "source-captures-match" in facts and "before_state" in dispatch and _state(dispatch, "before_state") != _state(dispatch, "after_state"):
        msg = "source-captures-match contradicts supplied captures"
        raise ValueError(msg)
    if "git-not-mutated" in facts and dispatch.get("git_mutated", False):
        msg = "git-not-mutated contradicts the dispatch mutation record"
        raise ValueError(msg)
    for caveat in (*_records(payload, "unresolved_uncertainties"), *_records(payload, "validation_limits")):
        _required_text(caveat, "reason")
    requirements = {record["requirement_id"] for record in payload["validation_requirements"]}
    if any(limit["requirement_id"] not in requirements for limit in payload.get("validation_limits", [])):
        msg = "validation_limits must reference explicit validation_requirements"
        raise ValueError(msg)


def _review_limitation_reasons(payload: dict[str, Any]) -> tuple[str, ...]:
    """Retain material typed caveats in blocked-node journal explanations."""
    return (
        *_text_list(payload, "limitations"),
        *(reason for _path, reason in _scope_limitation_records(payload)),
        *(_required_text(item, "reason") for item in payload.get("unresolved_uncertainties", [])),
        *(_required_text(item, "reason") for item in payload.get("validation_limits", []) if item["status"] != "delegated"),
    )


def compile_review(document: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:  # noqa: C901, PLR0912, PLR0915
    """Compile one compact semantic payload into the verified proof artifact."""
    dispatch = document.get("dispatch")
    payload = document.get("payload")
    if not isinstance(dispatch, dict) or not isinstance(payload, dict):
        msg = "compile-review input requires dispatch and payload objects"
        raise TypeError(msg)
    mode = _required_text(dispatch, "mode")
    if mode not in _REVIEW_MODES:
        msg = f"compact compiler does not support mode {mode}"
        raise ValueError(msg)
    if mode == "synthesis":
        require_schema(payload, _SYNTHESIS_PAYLOAD_SCHEMA)
        validate_synthesis(payload, _text_list(dispatch, "predecessor_evidence_ids"), dispatch.get("synthesis_bundle"))
    coverage_reuse = dispatch.get("coverage_reuse")
    if coverage_reuse is not None:
        _verify_delta_context(coverage_reuse, dispatch)
        old_requirements = {item["requirement_id"] for item in coverage_reuse["original_validation_requirements"]}
        old_handoffs = {item["catalog_id"] for item in coverage_reuse["original_handoffs"]}
        if not old_requirements <= {item["requirement_id"] for item in payload["validation_requirements"]} or not old_handoffs <= {
            item["catalog_id"] for item in payload["handoffs"]
        }:
            msg = "delta review must reconcile original validation requirements and routing handoffs"
            raise ValueError(msg)
    _validate_review_coverage_partitions(dispatch, payload)
    _validate_audit_caveats(dispatch, payload)
    status = _required_text(payload, "status")
    if status not in _REVIEW_STATUSES:
        msg = f"invalid review status {status}"
        raise ValueError(msg)
    node_id = _required_text(dispatch, "node_id")
    skill_id = _required_text(dispatch, "skill_id")
    skill_path = Path(_required_text(dispatch, "skill_path")).resolve()
    if not skill_path.is_file():
        msg = f"skill file does not exist: {skill_path}"
        raise ValueError(msg)
    reference_paths = tuple(Path(path).resolve() for path in _text_list(dispatch, "reference_paths"))
    if any(not path.is_file() for path in reference_paths):
        msg = "every reference path must exist"
        raise ValueError(msg)
    reference_digests = tuple((str(path), _file_identity_digest(str(path))) for path in reference_paths)
    expected = _state(dispatch, "source_state")
    before = _state(dispatch, "before_state")
    after = _state(dispatch, "after_state")
    expected_after = _state(dispatch, "expected_after_state") if dispatch.get("expected_after_state") is not None else None
    execution_profile = _required_text(dispatch, "execution_profile")
    execution_location = _required_text(dispatch, "execution_location")
    worker_created = dispatch.get("worker_created")
    fresh_context = dispatch.get("fresh_context")
    if not isinstance(worker_created, bool) or not isinstance(fresh_context, bool):
        msg = "worker_created and fresh_context must be booleans"
        raise TypeError(msg)
    if execution_location == "worker" and fresh_context is not True:
        msg = "every compact worker payload requires fresh_context=true"
        raise ValueError(msg)
    source_mutated = dispatch.get("source_mutated", False)
    git_mutated = dispatch.get("git_mutated", False)
    if not isinstance(source_mutated, bool) or not isinstance(git_mutated, bool):
        msg = "source_mutated and git_mutated must be booleans"
        raise TypeError(msg)
    if mode in _READ_ONLY_MODES and source_mutated:
        msg = f"{mode} is read-only"
        raise ValueError(msg)
    authorization = _required_text(dispatch, "authorization")
    planned_paths = _text_list(dispatch, "planned_paths") if mode == "fix" else ()
    changed_paths = _text_list(dispatch, "changed_paths") if source_mutated else ()
    findings = _finding_records({**payload, "findings": combined_findings(payload, coverage_reuse)}, node_id)
    validations = _validation_records(payload)
    handoffs = _handoff_records(payload, node_id)
    policy_blockers = _review_command_policy_blockers(dispatch, payload)
    validation_requirement_blockers = _review_validation_requirement_blockers(dispatch, validations)
    handoff_blockers = _review_handoff_catalog_blockers(dispatch, handoffs)
    scope_blockers = _review_scope_coverage_blockers(dispatch, payload, status=status)
    limitations = _text_list(payload, "limitations")
    if status == "no-findings" and findings:
        msg = "no-findings payload cannot contain findings"
        raise ValueError(msg)
    if status == "blocked" and not _review_limitation_reasons(payload):
        msg = "blocked payload requires a limitation"
        raise ValueError(msg)
    _text_list(payload, "files_inspected", required=status != "blocked" and mode != "synthesis" and not reused_paths(coverage_reuse))
    _text_list(payload, "nearby_contract_owners")
    audit_inputs = _compiled_audit_inputs(dispatch, payload)
    scope_body = review_scope_body(payload, mode=mode, audit_inputs=audit_inputs, coverage_reuse=coverage_reuse)
    compact_scope = mode == "audit" and len(scope_body.encode()) > MAX_NATIVE_SECTION_BYTES
    if compact_scope:
        require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
        scope_body = review_scope_body(payload, mode=mode, audit_inputs=audit_inputs, coverage_reuse=coverage_reuse, compact=True)
    requirement_ids = _text_list(dispatch, "requirement_ids")
    predecessor_evidence_ids = _text_list(dispatch, "predecessor_evidence_ids")
    evidence_id = _required_text(dispatch, "evidence_id")
    artifact_id = _required_text(dispatch, "artifact_id")
    fingerprints = _dispatch_fingerprints(dispatch)
    _verify_audit_metadata(payload, fingerprints, coverage_reuse)
    expectation = ReviewEvidenceExpectation(
        node_id=node_id,
        requirement_ids=requirement_ids,
        skill_id=skill_id,
        mode=mode,
        skill_path=str(skill_path),
        skill_digest=_file_identity_digest(str(skill_path)),
        reference_digests=reference_digests,
        source_state=expected,
        execution_profile=execution_profile,
        selection_reason=_required_text(dispatch, "selection_reason"),
        authorization=authorization,
        expected_after_state=expected_after,
        source_mutation_allowed=source_mutated,
        predecessor_evidence_ids=predecessor_evidence_ids,
        planned_paths=planned_paths,
        audit_input_identity=audit_inputs,
        coverage_reuse=coverage_reuse,
        canonical_worker_payload=payload if compact_scope else None,
    )
    evidence = ReviewEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id=evidence_id,
        node_id=node_id,
        requirement_ids=requirement_ids,
        skill_id=skill_id,
        mode=mode,
        skill_path=str(skill_path),
        skill_digest=expectation.skill_digest,
        reference_digests=reference_digests,
        fingerprints=fingerprints,
        execution_profile=execution_profile,
        execution_location=execution_location,
        worker_created=worker_created,
        fresh_context=fresh_context,
        status=status,
        finding_ids=tuple(finding_id for finding_id, _ in findings),
        validation_requirement_ids=tuple(requirement_id for requirement_id, _ in validations),
        handoff_ids=tuple(handoff_id for handoff_id, _ in handoffs),
        raw_result_artifact_id=artifact_id,
        raw_result_digest="pending",
        report_complete=True,
        source_mutated=source_mutated,
        git_mutated=git_mutated,
        predecessor_evidence_ids=predecessor_evidence_ids,
        routing_discoveries=tuple(
            RoutingDiscovery(
                handoff_id=handoff_id,
                source_node_id=node_id,
                catalog_id=_required_text(record, "catalog_id"),
                evidence=_required_text(record, "observed_trigger"),
            )
            for handoff_id, record in handoffs
        ),
    )
    canonical_payload = canonical_json(payload)
    machine_payload = {
        "after_repository_state_fingerprint": after[2],
        "after_scope_fingerprint": after[0],
        "after_worktree_fingerprint": after[1],
        "artifact_id": artifact_id,
        "before_repository_state_fingerprint": before[2],
        "before_scope_fingerprint": before[0],
        "before_worktree_fingerprint": before[1],
        "evidence_id": evidence_id,
        "finding_ids": list(evidence.finding_ids),
        "git_mutated": git_mutated,
        "mode": mode,
        "node_id": node_id,
        "predecessor_evidence_ids": list(predecessor_evidence_ids),
        "repository_state_fingerprint": expected[2],
        "requirement_ids": list(requirement_ids),
        "result_type": "review-node-result",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scope_fingerprint": expected[0],
        "skill_id": skill_id,
        "source_mutated": source_mutated,
        "status": status,
        "validation_requirement_ids": list(evidence.validation_requirement_ids),
        "worktree_fingerprint": expected[1],
    }
    section_bodies = {
        "## Skill Loading": "\n".join(
            (
                f"- Skill file: {skill_path}",
                f"- Skill digest: {expectation.skill_digest}",
                f"- References loaded: {', '.join(str(path) for path in reference_paths) or 'none'}",
                f"- Reference digests: {', '.join(f'{path}={digest}' for path, digest in reference_digests) or 'none'}",
            )
        ),
        "## State Verification": _state_verification(dispatch, evidence, changed_paths),
        "## Scope Inspected": scope_body,
        "## Findings": _findings_body(findings),
        "## Validation": "none",
        "## Validation Requirements": _validation_body(validations),
        "## Predecessor Coverage": _predecessor_body(dispatch, evidence),
        "## Changes": _changes_body(payload, evidence, changed_paths),
        "## Handoffs": _handoffs_body(handoffs),
        "## Limitations": "\n".join(
            (
                f"- General: {'; '.join(limitations) or 'none'}",
                "- Owned-path omissions: " + ("; ".join(f"{path}: {reason}" for path, reason in _scope_limitation_records(payload)) or "none"),
                *((f"- Execution facts: {canonical_json(payload['execution_facts'])}",) if "execution_facts" in payload else ()),
                *((f"- Validation limits: {canonical_json(payload['validation_limits'])}",) if "validation_limits" in payload else ()),
                *((f"- Unresolved uncertainties: {canonical_json(payload['unresolved_uncertainties'])}",) if "unresolved_uncertainties" in payload else ()),
            )
        ),
    }
    sections = (
        "## Skill Loading",
        "## State Verification",
        "## Scope Inspected",
        "## Findings",
        "## Validation",
        "## Validation Requirements",
        "## Predecessor Coverage",
        "## Changes",
        "## Handoffs",
        "## Limitations",
        "## Machine Evidence",
    )
    body = "\n\n".join(f"{section}\n\n{section_bodies[section]}" for section in sections[:-1])
    if mode == "synthesis":
        body += "\n\n### Readiness Verdict\n\n" + payload["readiness_verdict"] + "\n\n" + "; ".join(payload["verdict_reasons"])
        body += "\n\n### Synthesis Reconciliation\n\n" + canonical_json(synthesis_fields(payload))
    content = (
        f"# Review Node Result\n\n{_review_header(expectation, evidence)}\n\n{body}\n\n## Machine Evidence\n\n"
        f"{NATIVE_EVIDENCE_BLOCK_OPEN}{canonical_json(machine_payload)}{NATIVE_EVIDENCE_BLOCK_CLOSE}\n"
    ).encode()
    evidence = replace(evidence, raw_result_digest=digest_bytes(content))
    envelope_assessment = assess_review_evidence(expectation, evidence)
    native_blockers = _review_native_result_blockers(content, expectation, evidence)
    blockers = (*policy_blockers, *validation_requirement_blockers, *handoff_blockers, *scope_blockers, *envelope_assessment.blockers, *native_blockers)
    if blockers:
        msg = "compiled review artifact failed verification: " + "; ".join(blockers)
        raise ValueError(msg)
    metadata = {
        "expectation": asdict(expectation),
        "evidence": asdict(evidence),
        "payload_digest": digest_bytes(canonical_payload.encode()),
        "artifact_digest": evidence.raw_result_digest,
        "normalized_record": _review_normalized_record(payload, expectation, evidence),
    }
    if mode == "synthesis" and any({"software_doi_resolution", "scholarly_doi_resolution"} & item.keys() for item in payload["validation_reconciliation"]):
        # Retain the evidence needed to reverify resolutions when loading this artifact.
        metadata["synthesis_bundle"] = dispatch.get("synthesis_bundle")
    return content, metadata


def _independent_input_sections(content: bytes) -> dict[str, str]:
    if len(content) > 1_048_576:
        msg = "independent native artifact exceeds the maximum size"
        raise ValueError(msg)
    text = content.decode("utf-8", errors="strict")
    blockers = list(_native_heading_blockers(text, expected_heading="# Repository Independent Review", required_sections=_INDEPENDENT_NATIVE_SECTIONS))
    lines = text.splitlines()
    first_position = lines.index(_INDEPENDENT_NATIVE_SECTIONS[0]) if _INDEPENDENT_NATIVE_SECTIONS[0] in lines else -1
    if first_position >= 0 and "\n".join(lines[1:first_position]).strip():
        blockers.append("independent native artifact must not contain untyped preamble content")
    sections: dict[str, str] = {}
    positions = [lines.index(section) for section in _INDEPENDENT_NATIVE_SECTIONS if section in lines]
    if len(positions) == len(_INDEPENDENT_NATIVE_SECTIONS):
        for ordinal, section in enumerate(_INDEPENDENT_NATIVE_SECTIONS):
            start = positions[ordinal] + 1
            end = positions[ordinal + 1] if ordinal + 1 < len(positions) else len(lines)
            sections[section] = "\n".join(lines[start:end]).strip()
    if blockers:
        msg = "independent native artifact failed structural validation: " + "; ".join(blockers)
        raise ValueError(msg)
    return sections


def _independent_findings(body: str, node_id: str, status: str) -> tuple[tuple[str, dict[str, str]], ...]:
    if status == "no-findings":
        if body != "No findings.":
            msg = "independent no-findings artifact requires the exact No findings. assertion"
            raise ValueError(msg)
        return ()
    if body in {"", "none", "No findings."}:
        return ()
    records = _native_records(body, "Finding") or _native_records(body, "ID")
    if not records:
        msg = "independent Findings must contain ordered Finding records"
        raise ValueError(msg)
    output: list[tuple[str, dict[str, str]]] = []
    blockers: list[str] = []
    labels = ("Severity", "Location", "Summary", "Evidence", "Impact", "Owner", "Remediation")
    for ordinal, (worker_identity, record_body) in enumerate(records, start=1):
        if not worker_identity:
            blockers.append(f"independent Finding {ordinal} requires a non-empty value on the same line as - Finding:")
        fields, field_blockers = _native_record_fields(record_body, section=f"independent Finding {ordinal}", labels=labels)
        blockers.extend(field_blockers)
        severity = fields.get("Severity")
        if severity is not None and severity not in _SEVERITIES:
            blockers.append(f"independent Finding {ordinal} has invalid severity {severity}; expected P0, P1, P2, or P3")
        if not field_blockers and worker_identity and severity in _SEVERITIES:
            output.append((f"{node_id}-finding-{ordinal}", dict(fields)))
    if blockers:
        raise ValueError("; ".join(blockers))
    return tuple(output)


def _independent_scope_blockers(body: str, dispatch: dict[str, Any]) -> tuple[str, ...]:
    blockers: list[str] = []
    expected_target = _required_text(dispatch, "change_target")
    expected_paths = _text_list(dispatch, "planned_paths", required=True)
    values = {label: _native_field_values(body, label) for label in ("Change target", "Files", "Branches", "Boundary cases", "Tests")}
    for label, observed in values.items():
        if len(observed) != 1 or not observed[0].strip():
            blockers.append(f"independent Scope Inspected requires exactly one non-empty {label} field")
    if values["Change target"] and values["Change target"][0] != expected_target:
        blockers.append("independent Scope Inspected change target differs from its dispatch")
    if values["Files"]:
        paths, path_blockers = _native_repository_path_list(values["Files"][0], label="independent Scope Inspected Files")
        blockers.extend(path_blockers)
        if not path_blockers and paths != expected_paths:
            blockers.append("independent Scope Inspected files do not equal the exact planned paths")
    return tuple(blockers)


def _independent_handoffs(body: str, node_id: str, dispatch: dict[str, Any]) -> tuple[tuple[str, dict[str, Any]], ...]:
    if body == "none":
        return ()
    records = _native_records(body, "Catalog ID")
    if not records:
        msg = "independent Routing Handoffs must contain Catalog ID records or exact none"
        raise ValueError(msg)
    output: list[tuple[str, dict[str, Any]]] = []
    for ordinal, (catalog_id, record_body) in enumerate(records, start=1):
        if len(catalog_id) >= 2 and catalog_id.startswith("`") and catalog_id.endswith("`"):
            catalog_id = catalog_id[1:-1]
        fields, blockers = _native_record_fields(record_body, section=f"independent Handoff {ordinal}", labels=("Observed trigger", "Reason", "Scope"))
        if blockers:
            msg = "; ".join(blockers)
            raise ValueError(msg)
        scope, scope_blockers = _native_repository_path_list(fields["Scope"], label=f"independent Handoff {ordinal} Scope")
        if scope_blockers or not scope:
            msg = "; ".join(scope_blockers or (f"independent Handoff {ordinal} Scope must not be empty",))
            raise ValueError(msg)
        output.append(
            (
                f"{node_id}-handoff-{ordinal}",
                {"catalog_id": catalog_id, "observed_trigger": fields["Observed trigger"], "reason": fields["Reason"], "scope": list(scope)},
            )
        )
    blockers = _review_handoff_catalog_blockers(dispatch, tuple(output))
    if blockers:
        raise ValueError(blockers[0])
    return tuple(output)


def _independent_findings_body(findings: tuple[tuple[str, dict[str, str]], ...], status: str) -> str:
    if status == "no-findings":
        return "No findings."
    if not findings:
        return "none"
    labels = ("Severity", "Location", "Summary", "Evidence", "Impact", "Owner", "Remediation")
    return "\n".join("\n".join((f"- ID: {finding_id}", *(f"  - {label}: {fields[label]}" for label in labels))) for finding_id, fields in findings)


def _independent_handoffs_body(handoffs: tuple[tuple[str, dict[str, Any]], ...]) -> str:
    if not handoffs:
        return "none"
    return "\n".join(
        "\n".join(
            (
                f"- Handoff ID: {handoff_id}",
                f"  - Catalog ID: {record['catalog_id']}",
                f"  - Observed trigger: {record['observed_trigger']}",
                f"  - Reason: {record['reason']}",
                f"  - Scope: {', '.join(record['scope'])}",
            )
        )
        for handoff_id, record in handoffs
    )


def _compile_independent_native(document: dict[str, Any], native_content: bytes) -> tuple[bytes, dict[str, Any]]:  # noqa: C901, PLR0912, PLR0915
    """Verify and envelope generated independent-review sections."""
    dispatch = document.get("dispatch")
    if not isinstance(dispatch, dict):
        msg = "compile-independent-review input requires a dispatch object"
        raise TypeError(msg)
    if _required_text(dispatch, "mode") != "independent-review" or _required_text(dispatch, "skill_id") != "repository-independent-review":
        msg = "compile-independent-review requires the planned repository-independent-review node"
        raise ValueError(msg)
    status = _required_text(document, "status")
    if status not in _REVIEW_STATUSES:
        msg = f"invalid independent review status {status}"
        raise ValueError(msg)
    limitations = _text_list(document, "limitations")
    if status == "blocked" and not limitations:
        msg = "blocked independent review requires one concrete limitation"
        raise ValueError(msg)
    if status != "blocked" and limitations:
        msg = (
            "accepted independent review must not contain limitations; incomplete inspection or unresolved semantic uncertainty requires blocked status. "
            "Record only non-blocking validation execution context in tests"
        )
        raise ValueError(msg)
    sections = _independent_input_sections(native_content)
    node_id = _required_text(dispatch, "node_id")
    input_blockers: list[str] = []
    if status != "blocked":
        input_blockers.extend(_independent_scope_blockers(sections["## Scope Inspected"], dispatch))
    try:
        findings = _independent_findings(sections["## Findings"], node_id, status)
    except (TypeError, ValueError) as error:
        findings = ()
        input_blockers.append(str(error))
    if status == "completed" and not findings:
        input_blockers.append("completed independent review requires at least one finding")
    if status == "no-findings":
        inspected_checks = set(_native_field_values(sections["## No-Finding Evidence"], "Inspected"))
        missing_checks = tuple(check for check in _text_list(dispatch, "adversarial_checks") if check not in inspected_checks)
        if missing_checks:
            input_blockers.append("independent no-findings evidence omits dispatched adversarial checks: " + ", ".join(missing_checks))
    try:
        handoffs = _independent_handoffs(sections["## Routing Handoffs"], node_id, dispatch)
    except (TypeError, ValueError) as error:
        handoffs = ()
        input_blockers.append(str(error))
    expected = _state(dispatch, "source_state")
    before = _state(dispatch, "before_state")
    after = _state(dispatch, "after_state")
    native_state_blockers = (
        *_native_fingerprint_proof_blockers(sections["## Fingerprint Proof"], FingerprintEvidence(expected=expected, before=before, after=after)),
        *_native_mutation_blockers(
            sections["## Git State"],
            section="Git State",
            source_label="Source-controlled files changed",
            git_label="Git state mutated",
            source_mutated=False,
            git_mutated=False,
        ),
    )
    observed_fingerprints = _dispatch_fingerprints(dispatch)
    if not observed_fingerprints.matches(before) or not observed_fingerprints.matches(after) or before != after:
        native_state_blockers = (*native_state_blockers, "independent review observed fingerprints differ from the dispatched expected fingerprints")
    if native_state_blockers:
        input_blockers.append("independent native state proof failed validation: " + "; ".join(native_state_blockers))
    if input_blockers:
        msg = "independent native artifact failed contract validation: " + "; ".join(input_blockers)
        raise ValueError(msg)
    skill_path = Path(_required_text(dispatch, "skill_path")).resolve()
    if not skill_path.is_file():
        msg = f"independent review skill file does not exist: {skill_path}"
        raise ValueError(msg)
    reference_paths = tuple(Path(path).resolve() for path in _text_list(dispatch, "reference_paths"))
    if any(not path.is_file() for path in reference_paths):
        msg = "every independent review reference path must exist"
        raise ValueError(msg)
    planned_paths = _text_list(dispatch, "planned_paths", required=True)
    inspected_values = _native_field_values(sections["## Scope Inspected"], "Files")
    inspected_paths, _ = _native_repository_path_list(inspected_values[0], label="independent Files") if len(inspected_values) == 1 else ((), ())
    change_target = _required_text(dispatch, "change_target")
    execution_profile = _required_text(dispatch, "execution_profile")
    execution_location = _required_text(dispatch, "execution_location")
    worker_created = _required_bool(dispatch, "worker_created")
    fresh_context = _required_bool(dispatch, "fresh_context")
    if execution_location == "worker" and not fresh_context:
        msg = "independent review workers require fresh_context=true"
        raise ValueError(msg)
    evidence_id = _required_text(dispatch, "evidence_id")
    artifact_id = _required_text(dispatch, "artifact_id")
    reference_digests = tuple((str(path), _file_identity_digest(str(path))) for path in reference_paths)
    fingerprints = observed_fingerprints
    expectation = ReviewEvidenceExpectation(
        node_id=node_id,
        requirement_ids=_text_list(dispatch, "requirement_ids"),
        skill_id="repository-independent-review",
        mode="independent-review",
        skill_path=str(skill_path),
        skill_digest=_file_identity_digest(str(skill_path)),
        reference_digests=reference_digests,
        source_state=expected,
        execution_profile=execution_profile,
        selection_reason=_required_text(dispatch, "selection_reason"),
        authorization=_required_text(dispatch, "authorization"),
        change_target=change_target,
        planned_paths=planned_paths,
        planned_path_line_bounds=_path_line_bounds(dispatch, "planned_path_line_bounds"),
    )
    evidence = ReviewEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id=evidence_id,
        node_id=node_id,
        requirement_ids=expectation.requirement_ids,
        skill_id="repository-independent-review",
        mode="independent-review",
        skill_path=str(skill_path),
        skill_digest=expectation.skill_digest,
        reference_digests=reference_digests,
        fingerprints=fingerprints,
        execution_profile=execution_profile,
        execution_location=execution_location,
        worker_created=worker_created,
        fresh_context=fresh_context,
        status=status,
        finding_ids=tuple(finding_id for finding_id, _fields in findings),
        validation_requirement_ids=(),
        handoff_ids=tuple(handoff_id for handoff_id, _record in handoffs),
        raw_result_artifact_id=artifact_id,
        raw_result_digest="pending",
        report_complete=True,
        routing_discoveries=tuple(
            RoutingDiscovery(
                handoff_id=handoff_id,
                source_node_id=node_id,
                catalog_id=_required_text(record, "catalog_id"),
                evidence=_required_text(record, "observed_trigger"),
            )
            for handoff_id, record in handoffs
        ),
    )
    results = tuple("matched" if fingerprints.matches(observed) else "mismatched" for observed in (before, after))
    envelope = "\n".join(
        (
            f"- Node ID: {node_id}",
            "- Skill: repository-independent-review",
            "- Mode: independent-review",
            f"- Status: {status}",
            f"- Scope fingerprint: {expected[0]}",
            f"- Worktree fingerprint: {expected[1]}",
            f"- Repository state fingerprint: {expected[2]}",
            f"- Skill file: {skill_path}",
            f"- Change target: {change_target}",
            f"- Files inspected: {', '.join(inspected_paths) or 'none'}",
            "- State verification before:",
            f"  - Observed scope fingerprint: {before[0]}",
            f"  - Observed worktree fingerprint: {before[1]}",
            f"  - Observed repository state fingerprint: {before[2]}",
            f"  - Result: {results[0]}",
            "- State verification after:",
            f"  - Observed scope fingerprint: {after[0]}",
            f"  - Observed worktree fingerprint: {after[1]}",
            f"  - Observed repository state fingerprint: {after[2]}",
            f"  - Result: {results[1]}",
            "- Source-controlled files changed: none",
            "- Git state mutated: no",
            *(
                (f"- External metadata transitions: {canonical_json([asdict(item) for item in fingerprints.metadata_transitions])}",)
                if fingerprints.metadata_transitions
                else ()
            ),
            f"- Limitations: {'; '.join(limitations) or 'none'}",
        )
    )
    machine_payload = {
        "after_repository_state_fingerprint": after[2],
        "after_scope_fingerprint": after[0],
        "after_worktree_fingerprint": after[1],
        "artifact_id": artifact_id,
        "before_repository_state_fingerprint": before[2],
        "before_scope_fingerprint": before[0],
        "before_worktree_fingerprint": before[1],
        "change_target": change_target,
        "evidence_id": evidence_id,
        "finding_ids": list(evidence.finding_ids),
        "git_mutated": False,
        "handoff_ids": list(evidence.handoff_ids),
        "inspected_paths": list(inspected_paths),
        "mode": "independent-review",
        "node_id": node_id,
        "predecessor_evidence_ids": [],
        "repository_state_fingerprint": expected[2],
        "requirement_ids": list(evidence.requirement_ids),
        "result_type": "independent-review-result",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scope_fingerprint": expected[0],
        "skill_id": "repository-independent-review",
        "source_mutated": False,
        "status": status,
        "validation_requirement_ids": [],
        "worktree_fingerprint": expected[1],
    }
    output_sections = {
        **sections,
        "## Findings": _independent_findings_body(findings, status),
        "## Routing Handoffs": _independent_handoffs_body(handoffs),
        "## Review Graph Envelope": envelope,
        "## Machine Evidence": f"{NATIVE_EVIDENCE_BLOCK_OPEN}{canonical_json(machine_payload)}{NATIVE_EVIDENCE_BLOCK_CLOSE}",
    }
    ordered = (*_INDEPENDENT_NATIVE_SECTIONS, "## Review Graph Envelope", "## Machine Evidence")
    content = ("# Repository Independent Review\n\n" + "\n\n".join(f"{section}\n\n{output_sections[section]}" for section in ordered) + "\n").encode()
    evidence = replace(evidence, raw_result_digest=digest_bytes(content))
    assessment = assess_review_evidence(expectation, evidence)
    native_blockers = _review_native_result_blockers(content, expectation, evidence)
    blockers = (*assessment.blockers, *native_blockers)
    if blockers:
        msg = "compiled independent review failed verification: " + "; ".join(blockers)
        raise ValueError(msg)
    normalized = _independent_normalized_record(content, expectation, evidence)
    return content, {
        "artifact_digest": evidence.raw_result_digest,
        "evidence": asdict(evidence),
        "expectation": asdict(expectation),
        "native_input_digest": digest_bytes(native_content),
        "normalized_record": normalized,
    }


def compile_independent_payload(document: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Compile structured judgments through the existing native evidence verifier."""
    dispatch, payload = document.get("dispatch"), document.get("payload")
    if not isinstance(dispatch, dict) or not isinstance(payload, dict):
        msg = "compile-independent-review input requires dispatch and payload objects"
        raise TypeError(msg)
    native = render_independent_payload(payload, dispatch)
    blockers = _review_command_policy_blockers(dispatch, payload)
    if blockers:
        raise ValueError("; ".join(blockers))
    content, metadata = _compile_independent_native({"dispatch": dispatch, "status": payload["status"], "limitations": payload["limitations"]}, native)
    metadata["payload_digest"] = digest_bytes(canonical_json(payload).encode())
    return content, metadata


def _independent_normalized_record(content: bytes, expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> dict[str, Any]:
    text = content.decode("utf-8", errors="strict")
    ordered = (*_INDEPENDENT_NATIVE_SECTIONS, "## Review Graph Envelope", "## Machine Evidence")
    sections, blockers = _native_section_bodies(text, ordered)
    heading_blockers = _native_heading_blockers(text, expected_heading="# Repository Independent Review", required_sections=ordered)
    if blockers or heading_blockers or sections is None:
        msg = "cannot derive normalized independent review from malformed native sections"
        raise ValueError(msg)
    findings: list[dict[str, str]] = []
    for finding_id, body in _native_records(sections["## Findings"], "ID"):
        fields, field_blockers = _native_record_fields(
            body, section=f"independent Finding {finding_id}", labels=("Severity", "Location", "Summary", "Evidence", "Impact", "Owner", "Remediation")
        )
        if field_blockers:
            msg = "; ".join(field_blockers)
            raise ValueError(msg)
        findings.append(
            {
                "evidence": fields["Evidence"],
                "finding_id": finding_id,
                "impact": fields["Impact"],
                "location": fields["Location"],
                "owner": fields["Owner"],
                "remediation": fields["Remediation"],
                "severity": fields["Severity"],
                "summary": fields["Summary"],
            }
        )
    handoffs: list[dict[str, Any]] = []
    for handoff_id, body in _native_records(sections["## Routing Handoffs"], "Handoff ID"):
        fields, field_blockers = _native_record_fields(
            body, section=f"independent Handoff {handoff_id}", labels=("Catalog ID", "Observed trigger", "Reason", "Scope")
        )
        if field_blockers:
            msg = "; ".join(field_blockers)
            raise ValueError(msg)
        scope, scope_blockers = _native_repository_path_list(fields["Scope"], label=f"independent Handoff {handoff_id} Scope")
        if scope_blockers:
            msg = "; ".join(scope_blockers)
            raise ValueError(msg)
        handoffs.append(
            {
                "catalog_id": fields["Catalog ID"],
                "handoff_id": handoff_id,
                "observed_trigger": fields["Observed trigger"],
                "reason": fields["Reason"],
                "scope": list(scope),
            }
        )
    limitations = _native_field_values(sections["## Review Graph Envelope"], "Limitations")
    return {
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": evidence.raw_result_artifact_id,
        "changes": [],
        "evidence_id": evidence.evidence_id,
        "files_inspected": list(expectation.planned_paths),
        "observed_source_state": list(evidence.fingerprints.after),
        "findings": findings,
        "handoffs": handoffs,
        "limitations": [] if limitations == ("none",) else list(limitations),
        "mode": "independent-review",
        "node_id": evidence.node_id,
        "record_type": "review",
        "requirement_ids": list(evidence.requirement_ids),
        "selection_reason": expectation.selection_reason,
        "skill_id": evidence.skill_id,
        "status": evidence.status,
        "validation_requirements": [],
    }


def _validation_unit(raw: dict[str, Any]) -> ValidationUnit:
    executor_permissions(_text_list(raw, "features"))
    allowed_artifacts = tuple(
        ValidationArtifact(
            path=_required_text(item, "path"),
            kind=_required_text(item, "kind"),
            repository_status=_required_text(item, "repository_status"),
            status_source=_required_text(item, "status_source"),
            artifact_id=item.get("artifact_id"),
            artifact_digest=item.get("artifact_digest"),
            artifact_digest_mode=item.get("artifact_digest_mode"),
            status_rule=item.get("status_rule"),
        )
        for item in _records(raw, "allowed_artifacts")
    )
    raw_plans = raw.get("requirement_plans", [])
    if not isinstance(raw_plans, list) or any(not isinstance(plan, list) or len(plan) != 7 for plan in raw_plans):
        msg = "validation_unit.requirement_plans must contain seven-field arrays"
        raise ValueError(msg)
    isolation_root = raw.get("isolation_root")
    if isolation_root is not None and (not isinstance(isolation_root, str) or not isolation_root.strip()):
        msg = "validation_unit.isolation_root must be a non-empty string or null"
        raise ValueError(msg)
    if isinstance(isolation_root, str) and not Path(isolation_root).is_absolute():
        msg = "validation_unit.isolation_root must be absolute"
        raise ValueError(msg)
    if raw.get("requires_isolation", False) and isolation_root is None:
        msg = "validation_unit requiring isolation must declare isolation_root"
        raise ValueError(msg)
    return ValidationUnit(
        node_id=_required_text(raw, "node_id"),
        requirement_ids=_text_list(raw, "requirement_ids"),
        source_state=_state(raw, "source_state"),
        commands=_text_list(raw, "commands"),
        working_directories=_text_list(raw, "working_directories"),
        environment=_required_text(raw, "environment"),
        toolchain=_required_text(raw, "toolchain"),
        features=_text_list(raw, "features"),
        platform=_required_text(raw, "platform"),
        artifact_owner=_required_text(raw, "artifact_owner"),
        mutation_lock=_required_text(raw, "mutation_lock"),
        request=_required_text(raw, "request"),
        requested_scope=_required_text(raw, "requested_scope"),
        capture_command=_required_text(raw, "capture_command"),
        captured_paths=_text_list(raw, "captured_paths"),
        requirement_plans=tuple(tuple(value for value in plan) for plan in raw_plans),
        dependency_policy=_required_text(raw, "dependency_policy"),
        meaningful_skips=_text_list(raw, "meaningful_skips"),
        execution_strategy=_required_text(raw, "execution_strategy"),
        independence_basis=_required_text(raw, "independence_basis"),
        planning_blocker=raw.get("planning_blocker"),
        allowed_artifacts=allowed_artifacts,
        canonical_recipe=raw.get("canonical_recipe"),
        evidence_ids=_text_list(raw, "evidence_ids"),
        required=raw.get("required", True),
        baseline=raw.get("baseline", False),
        requirement_requests=_string_pairs(raw, "requirement_requests"),
        expected_workspace_effects=_string_tuple(raw, "expected_workspace_effects"),
        requires_isolation=raw.get("requires_isolation", False),
        isolation_root=isolation_root,
    )


def _string_tuple(raw: dict[str, Any], name: str) -> tuple[str, ...]:
    value = raw.get(name, [])
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        msg = f"{name} must be a string array"
        raise ValueError(msg)
    return tuple(cast("list[str] | tuple[str, ...]", value))


def _string_pairs(raw: dict[str, Any], name: str) -> tuple[tuple[str, str], ...]:
    value = raw.get(name, [])
    if not isinstance(value, (list, tuple)):
        msg = f"{name} must be an array"
        raise TypeError(msg)
    pairs = tuple(tuple(item) for item in value)
    if any(len(item) != 2 or any(not isinstance(part, str) for part in item) for item in pairs):
        msg = f"{name} must contain string pairs"
        raise ValueError(msg)
    return tuple((cast("str", item[0]), cast("str", item[1])) for item in pairs)


def _path_line_bounds(raw: dict[str, Any], name: str) -> tuple[tuple[str, int], ...]:
    value = raw.get(name, [])
    if not isinstance(value, (list, tuple)):
        msg = f"{name} must be an array"
        raise TypeError(msg)
    bounds = tuple(tuple(item) for item in value)
    if any(len(item) != 2 or not isinstance(item[0], str) or not isinstance(item[1], int) for item in bounds):
        msg = f"{name} must contain path and integer pairs"
        raise ValueError(msg)
    return tuple((cast("str", item[0]), cast("int", item[1])) for item in bounds)


def _fingerprint_evidence(raw: dict[str, Any]) -> FingerprintEvidence:
    return FingerprintEvidence(
        expected=_state(raw, "expected"),
        before=_state(raw, "before"),
        after=_state(raw, "after"),
        metadata_transitions=tuple(metadata_transition(item) for item in _records(raw, "metadata_transitions")),
    )


def _dispatch_fingerprints(dispatch: dict[str, Any]) -> FingerprintEvidence:
    return _fingerprint_evidence(
        {
            "expected": dispatch["source_state"],
            "before": dispatch["before_state"],
            "after": dispatch["after_state"],
            "metadata_transitions": dispatch.get("external_metadata_transitions", []),
        }
    )


def _audit_input_identity(raw: object) -> AuditInputIdentity | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        msg = "audit input identity must be an object"
        raise TypeError(msg)
    return AuditInputIdentity(
        _string_tuple(raw, "owned_paths"),
        _string_tuple(raw, "inspected_paths"),
        _string_tuple(raw, "nearby_contract_owners"),
        _string_pairs(raw, "instruction_digests"),
    )


def _review_expectation(raw: dict[str, Any]) -> ReviewEvidenceExpectation:
    expected_after = tuple(raw["expected_after_state"]) if raw.get("expected_after_state") is not None else None
    payload = raw.get("canonical_worker_payload")
    if payload is not None:
        require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
    return ReviewEvidenceExpectation(
        node_id=_required_text(raw, "node_id"),
        requirement_ids=_string_tuple(raw, "requirement_ids"),
        skill_id=_required_text(raw, "skill_id"),
        mode=_required_text(raw, "mode"),
        skill_path=_required_text(raw, "skill_path"),
        skill_digest=_required_text(raw, "skill_digest"),
        reference_digests=_string_pairs(raw, "reference_digests"),
        source_state=_state(raw, "source_state"),
        execution_profile=_required_text(raw, "execution_profile"),
        selection_reason=_required_text(raw, "selection_reason"),
        authorization=_required_text(raw, "authorization"),
        expected_after_state=expected_after,  # type: ignore[arg-type]
        source_mutation_allowed=raw.get("source_mutation_allowed", False),
        predecessor_evidence_ids=_string_tuple(raw, "predecessor_evidence_ids"),
        change_target=raw.get("change_target"),
        planned_paths=_string_tuple(raw, "planned_paths"),
        planned_path_line_bounds=_path_line_bounds(raw, "planned_path_line_bounds"),
        audit_input_identity=_audit_input_identity(raw.get("audit_input_identity")),
        coverage_reuse=raw.get("coverage_reuse"),
        canonical_worker_payload=payload,
    )


def _review_evidence(raw: dict[str, Any]) -> ReviewEvidence:
    fingerprints = raw.get("fingerprints")
    if not isinstance(fingerprints, dict):
        msg = "review evidence fingerprints must be an object"
        raise TypeError(msg)
    raw_discoveries = raw.get("routing_discoveries", [])
    if not isinstance(raw_discoveries, list) or any(not isinstance(discovery, dict) for discovery in raw_discoveries):
        msg = "review evidence routing_discoveries must be an object array"
        raise TypeError(msg)
    return ReviewEvidence(
        schema_version=_required_int(raw, "schema_version"),
        evidence_id=_required_text(raw, "evidence_id"),
        node_id=_required_text(raw, "node_id"),
        requirement_ids=_string_tuple(raw, "requirement_ids"),
        skill_id=_required_text(raw, "skill_id"),
        mode=_required_text(raw, "mode"),
        skill_path=_required_text(raw, "skill_path"),
        skill_digest=_required_text(raw, "skill_digest"),
        reference_digests=_string_pairs(raw, "reference_digests"),
        fingerprints=_fingerprint_evidence(fingerprints),
        execution_profile=_required_text(raw, "execution_profile"),
        execution_location=_required_text(raw, "execution_location"),
        worker_created=_required_bool(raw, "worker_created"),
        fresh_context=_required_bool(raw, "fresh_context"),
        status=_required_text(raw, "status"),
        finding_ids=_string_tuple(raw, "finding_ids"),
        validation_requirement_ids=_string_tuple(raw, "validation_requirement_ids"),
        handoff_ids=_string_tuple(raw, "handoff_ids"),
        raw_result_artifact_id=_required_text(raw, "raw_result_artifact_id"),
        raw_result_digest=_required_text(raw, "raw_result_digest"),
        report_complete=_required_bool(raw, "report_complete"),
        source_mutated=_required_bool(raw, "source_mutated"),
        git_mutated=_required_bool(raw, "git_mutated"),
        predecessor_evidence_ids=_string_tuple(raw, "predecessor_evidence_ids"),
        routing_discoveries=tuple(
            RoutingDiscovery(
                handoff_id=_required_text(discovery, "handoff_id"),
                source_node_id=_required_text(discovery, "source_node_id"),
                catalog_id=_required_text(discovery, "catalog_id"),
                evidence=_required_text(discovery, "evidence"),
            )
            for discovery in raw_discoveries
        ),
    )


def _validation_expectation(raw: dict[str, Any]) -> ValidationEvidenceExpectation:
    unit = raw.get("validation_unit")
    if not isinstance(unit, dict):
        msg = "validation expectation requires validation_unit"
        raise TypeError(msg)
    return ValidationEvidenceExpectation(
        node_id=_required_text(raw, "node_id"),
        requirement_ids=_string_tuple(raw, "requirement_ids"),
        skill_path=_required_text(raw, "skill_path"),
        skill_digest=_required_text(raw, "skill_digest"),
        reference_digests=_string_pairs(raw, "reference_digests"),
        source_state=_state(raw, "source_state"),
        execution_profile=_required_text(raw, "execution_profile"),
        execution_location=_required_text(raw, "execution_location"),
        validation_unit=_validation_unit(unit),
    )


def _validation_evidence(raw: dict[str, Any]) -> ValidationEvidence:
    fingerprints = raw.get("fingerprints")
    if not isinstance(fingerprints, dict):
        msg = "validation evidence fingerprints must be an object"
        raise TypeError(msg)
    return ValidationEvidence(
        schema_version=_required_int(raw, "schema_version"),
        evidence_id=_required_text(raw, "evidence_id"),
        node_id=_required_text(raw, "node_id"),
        requirement_ids=_string_tuple(raw, "requirement_ids"),
        skill_digest=_required_text(raw, "skill_digest"),
        reference_digests=_string_pairs(raw, "reference_digests"),
        fingerprints=_fingerprint_evidence(fingerprints),
        execution_profile=_required_text(raw, "execution_profile"),
        execution_location=_required_text(raw, "execution_location"),
        worker_created=_required_bool(raw, "worker_created"),
        fresh_context=_required_bool(raw, "fresh_context"),
        status=_required_text(raw, "status"),
        command_identity_digest=_required_text(raw, "command_identity_digest"),
        environment_digest=_required_text(raw, "environment_digest"),
        raw_result_artifact_id=_required_text(raw, "raw_result_artifact_id"),
        raw_result_digest=_required_text(raw, "raw_result_digest"),
        source_mutated=_required_bool(raw, "source_mutated"),
        git_mutated=_required_bool(raw, "git_mutated"),
    )


def _validation_state_verification(dispatch: dict[str, Any], evidence: ValidationEvidence) -> str:
    result = "blocked" if evidence.status == "blocked" else "matched"
    return "\n".join(
        (
            f"- Before command: {_required_text(dispatch, 'state_verification_command')}",
            f"  - Observed scope fingerprint: {evidence.fingerprints.before[0]}",
            f"  - Observed worktree fingerprint: {evidence.fingerprints.before[1]}",
            f"  - Observed repository state fingerprint: {evidence.fingerprints.before[2]}",
            f"  - Result: {result}",
            f"- After command: {_required_text(dispatch, 'state_verification_command')}",
            f"  - Observed scope fingerprint: {evidence.fingerprints.after[0]}",
            f"  - Observed worktree fingerprint: {evidence.fingerprints.after[1]}",
            f"  - Observed repository state fingerprint: {evidence.fingerprints.after[2]}",
            f"  - Result: {result}",
            *(
                (f"- External metadata transitions: {canonical_json([asdict(item) for item in evidence.fingerprints.metadata_transitions])}",)
                if evidence.fingerprints.metadata_transitions
                else ()
            ),
        )
    )


def _validation_artifacts_body(  # noqa: C901
    payload: dict[str, Any], unit: ValidationUnit, workspace_after: dict[str, tuple[str, str, bool, str]]
) -> tuple[str, tuple[ValidationArtifact, ...]]:
    raw_artifacts = _records(payload, "artifacts") if "artifacts" in payload else ()
    raw_by_path = {_required_text(raw, "path"): raw for raw in raw_artifacts}
    if len(raw_by_path) != len(raw_artifacts):
        msg = "validation payload contains duplicate artifact paths"
        raise ValueError(msg)
    approved_paths = {artifact.path for artifact in unit.allowed_artifacts}
    unknown_paths = tuple(sorted(set(raw_by_path) - approved_paths))
    if unknown_paths:
        msg = "validation payload contains artifacts absent from its dispatch: " + ", ".join(unknown_paths)
        raise ValueError(msg)
    artifacts: list[ValidationArtifact] = []
    bodies: list[str] = []
    for approved in unit.allowed_artifacts:
        raw = raw_by_path.get(approved.path)
        observed = workspace_after.get(approved.path)
        if observed is None:
            msg = f"trusted workspace_after snapshot lacks validation artifact {approved.path}"
            raise ValueError(msg)
        observed_status, observed_digest, exists, observed_digest_mode = observed
        if not exists and raw is not None:
            msg = f"validation payload claims an artifact absent from the trusted snapshot: {approved.path}"
            raise ValueError(msg)
        path = approved.path
        kind = approved.kind
        repository_status = approved.repository_status
        artifact_id = approved.artifact_id
        artifact_digest = observed_digest
        if observed_status != repository_status:
            msg = f"validation artifact {path} repository status differs from trusted snapshot"
            raise ValueError(msg)
        if raw is not None:
            worker_identity = (_required_text(raw, "path"), _required_text(raw, "kind"), _required_text(raw, "repository_status"))
            if worker_identity != (path, kind, repository_status):
                msg = f"validation artifact {path} does not match its dispatch"
                raise ValueError(msg)
            if (
                raw.get("artifact_id") != artifact_id
                or _required_text(raw, "artifact_digest") != artifact_digest
                or _required_text(raw, "artifact_digest_mode") != observed_digest_mode
            ):
                msg = f"validation artifact {path} identity differs from the trusted workspace snapshot"
                raise ValueError(msg)
        if approved.artifact_digest is not None and (artifact_digest, observed_digest_mode) != (approved.artifact_digest, approved.artifact_digest_mode):
            msg = f"validation artifact {path} changed its approved digest or digest mode"
            raise ValueError(msg)
        artifact = ValidationArtifact(
            path=path,
            kind=kind,
            repository_status=repository_status,
            artifact_id=artifact_id,
            artifact_digest=artifact_digest,
            artifact_digest_mode=observed_digest_mode,
            status_source=approved.status_source,
            status_rule=approved.status_rule,
        )
        artifacts.append(artifact)
        bodies.append(
            "\n".join(
                (
                    f"- Path: {path}",
                    f"  - Artifact ID: {artifact_id or 'none'}",
                    f"  - Artifact digest: {artifact_digest}",
                    f"  - Artifact digest mode: {observed_digest_mode}",
                    f"  - Kind: {kind}",
                    f"  - Repository status: {repository_status}",
                    f"  - Status source: {approved.status_source}",
                    f"  - Status rule: {approved.status_rule or 'none'}",
                )
            )
        )
    return "\n".join(bodies) or "none", tuple(artifacts)


def _validation_executions_body(
    payload: dict[str, Any], evidence: ValidationEvidence, expectation_environment: str, artifacts: tuple[ValidationArtifact, ...]
) -> tuple[str, tuple[str, ...]]:
    raw_executions = _records(payload, "executions")
    artifact_by_path = {artifact.path: artifact for artifact in artifacts}
    blockers = _validation_artifact_reference_blockers(
        payload, tuple(artifact_by_path), tuple(path for path, artifact in artifact_by_path.items() if artifact.artifact_digest_mode == "absent-v1")
    )
    if blockers:
        raise ValueError("; ".join(blockers))
    results: list[str] = []
    bodies: list[str] = []
    for ordinal, raw in enumerate(raw_executions, start=1):
        command_label, command_text = validation_command_field(raw.get("command"))
        result = _required_text(raw, "result")
        if result not in {"passed", "failed", "blocked", "not-run"}:
            msg = f"validation execution {ordinal} has invalid result {result}"
            raise ValueError(msg)
        result_artifacts = _text_list(raw, "artifact_paths")
        artifact_references = (
            json.dumps(
                [
                    {
                        "artifact_digest": artifact_by_path[path].artifact_digest,
                        "artifact_digest_mode": artifact_by_path[path].artifact_digest_mode,
                        "artifact_id": artifact_by_path[path].artifact_id,
                        "path": path,
                    }
                    for path in result_artifacts
                ],
                sort_keys=True,
                separators=(",", ":"),
            )
            if result_artifacts
            else "none"
        )
        results.append(result)
        exit_code = raw.get("exit_code")
        exit_code_text = "none" if exit_code is None or exit_code == "none" else str(exit_code)
        elapsed = raw.get("elapsed")
        elapsed_text = "none" if elapsed is None or elapsed == "none" else str(elapsed)
        bodies.append(
            "\n".join(
                (
                    f"- Execution ID: {evidence.node_id}-exec-{ordinal}",
                    f"  - Executor: {_required_text(raw, 'executor')}",
                    f"  - {command_label}: {command_text}",
                    f"  - Working directory: {_required_text(raw, 'working_directory')}",
                    f"  - Environment/configuration: {expectation_environment}",
                    f"  - Result: {result}",
                    f"  - Exit code: {exit_code_text}",
                    f"  - Elapsed: {elapsed_text}",
                    f"  - Evidence: {_required_text(raw, 'evidence')}",
                    f"  - Log or artifact: {artifact_references}",
                )
            )
        )
    return "\n".join(bodies) or "none", tuple(results)


def _validation_artifact_reference_blockers(payload: dict[str, Any], permitted_paths: tuple[str, ...], absent_paths: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Use exact declared roots for typed references; narrative child paths are evidence."""
    blockers: list[str] = []
    for index, execution in enumerate(_records(payload, "executions")):
        references = set(_text_list(execution, "artifact_paths"))
        unknown = sorted(references - set(permitted_paths))
        absent = sorted(references & set(absent_paths))
        if unknown:
            blockers.append(
                f"$.executions[{index}].artifact_paths references unknown artifacts: {', '.join(unknown)}; "
                f"permitted roots (exact paths only, no generated children): {', '.join(permitted_paths) or 'none'}"
            )
        if absent:
            blockers.append(f"$.executions[{index}].artifact_paths references absent outputs: {', '.join(absent)}; omit absent output references")
    return tuple(blockers)


def _validation_reuse_body(unit: ValidationUnit, evidence: ValidationEvidence, command_digest: str, environment_digest: str) -> str:
    if evidence.status != "reused":
        return "none"
    bodies: list[str] = []
    for evidence_id in unit.evidence_ids:
        requirement_ids = tuple(requirement_id for requirement_id, *_rest, mapped_evidence_id in unit.requirement_plans if mapped_evidence_id == evidence_id)
        requirements = ", ".join(requirement_ids)
        bodies.append(
            "\n".join(
                (
                    f"- Ledger entry: {evidence_id}",
                    f"  - Requirement IDs: {requirements}",
                    (
                        f"  - Match basis: source={evidence.fingerprints.expected[2]}; command={command_digest}; "
                        f"environment={environment_digest}; selection={requirements}"
                    ),
                )
            )
        )
    return "\n".join(bodies) or "none"


def _validation_normalized_record(payload: dict[str, Any], evidence: ValidationEvidence, capture: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        "observed_source_state": list(evidence.fingerprints.after),
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": evidence.raw_result_artifact_id,
        "artifacts": list(_records(payload, "artifacts")),
        "command_identity_digest": evidence.command_identity_digest,
        "environment_digest": evidence.environment_digest,
        "evidence_id": evidence.evidence_id,
        "executions": list(_records(payload, "executions")),
        "findings": [],
        "handoffs": [],
        "limitations": list(_text_list(payload, "limitations")),
        "mode": "validation",
        "node_id": evidence.node_id,
        "payload_digest": digest_bytes(canonical_json(payload).encode()),
        "record_type": "validation",
        "requirement_ids": list(evidence.requirement_ids),
        "skill_id": "review-validator",
        "status": evidence.status,
        "validation": [
            {"evidence_id": evidence.evidence_id, "requirement_id": requirement_id, "status": evidence.status} for requirement_id in evidence.requirement_ids
        ],
    }
    inputs = captured_software_inputs(record, capture) if capture is not None else {}
    if inputs:
        record["captured_software_inputs"] = inputs
    doi_inputs = captured_doi_inputs(record, capture) if capture is not None else {}
    if doi_inputs:
        record["captured_doi_inputs"] = doi_inputs
    return record


def _workspace_path(path: str, repository_root: Path) -> Path:
    candidate = Path(path)
    return candidate.resolve(strict=False) if candidate.is_absolute() else (repository_root / candidate).resolve(strict=False)


def _bounded_workspace_directory_digest(path: Path) -> str:
    """Hash bounded root metadata for cache/build trees without reading contents."""
    root_stat = path.stat()
    all_entry_metadata: list[dict[str, object]] = []
    truncated = False
    with os.scandir(path) as stream:
        ordered_entries = sorted(stream, key=lambda item: item.name)
        truncated = len(ordered_entries) > _BOUNDED_WORKSPACE_ENTRY_LIMIT
        for entry in ordered_entries:
            stat = entry.stat(follow_symlinks=False)
            if entry.is_symlink():
                kind = "symlink"
            elif entry.is_file(follow_symlinks=False):
                kind = "file"
            elif entry.is_dir(follow_symlinks=False):
                kind = "directory"
            else:
                kind = "special"
            all_entry_metadata.append({"kind": kind, "mode": stat.st_mode, "mtime_ns": stat.st_mtime_ns, "name": entry.name, "size": stat.st_size})
    manifest = {
        "entry_limit": _BOUNDED_WORKSPACE_ENTRY_LIMIT,
        "entry_count": len(all_entry_metadata),
        "entry_metadata_digest": digest_bytes(canonical_json(all_entry_metadata).encode()),
        "entry_name_digest": digest_bytes(canonical_json([entry["name"] for entry in all_entry_metadata]).encode()),
        "policy": _BOUNDED_WORKSPACE_POLICY,
        "root": {"mode": root_stat.st_mode, "mtime_ns": root_stat.st_mtime_ns, "size": root_stat.st_size},
        "sampled_entries": all_entry_metadata[:_BOUNDED_WORKSPACE_ENTRY_LIMIT],
        "truncated": truncated,
    }
    return digest_bytes(canonical_json(manifest).encode())


def _recursive_workspace_directory_digest(path: Path) -> str:
    """Hash recursive contents while pruning known cache and build subtrees."""
    records: list[dict[str, object]] = []
    for directory, directory_names, file_names in path.walk(top_down=True, follow_symlinks=False):
        retained_directories: list[str] = []
        for name in sorted(directory_names):
            child = directory / name
            relative = child.relative_to(path).as_posix()
            if name in _BOUNDED_WORKSPACE_DIRECTORY_NAMES:
                records.append(
                    {"digest": _bounded_workspace_directory_digest(child), "digest_mode": _BOUNDED_WORKSPACE_POLICY, "kind": "directory", "path": relative}
                )
            else:
                records.append({"kind": "directory", "path": relative})
                retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in sorted(file_names):
            child = directory / name
            relative = child.relative_to(path).as_posix()
            if child.is_symlink():
                records.append({"kind": "symlink", "path": relative, "target": str(child.readlink())})
            elif child.is_file():
                records.append({"digest": digest_bytes(child.read_bytes()), "kind": "file", "path": relative})
            else:
                records.append({"kind": "special", "mode": child.stat().st_mode, "path": relative})
    records.sort(key=lambda item: str(item["path"]))
    return digest_bytes(canonical_json(records).encode())


def _workspace_content_digest(path: Path) -> tuple[bool, str, str]:
    if not path.exists() and not path.is_symlink():
        return False, digest_bytes(b"absent"), "absent-v1"
    if path.is_symlink():
        return True, digest_bytes(f"symlink:{path.readlink()}".encode()), "symlink-target-v1"
    if path.is_file():
        return True, digest_bytes(path.read_bytes()), "content-sha256-v1"
    if not path.is_dir():
        return True, digest_bytes(f"special:{path.stat().st_mode}".encode()), "special-metadata-v1"
    if path.name in _BOUNDED_WORKSPACE_DIRECTORY_NAMES:
        return True, _bounded_workspace_directory_digest(path), _BOUNDED_WORKSPACE_POLICY
    return True, _recursive_workspace_directory_digest(path), _RECURSIVE_WORKSPACE_POLICY


def _git_path_status(repository_root: Path, path: Path) -> str:
    if not path.is_relative_to(repository_root):
        return "outside-repository"
    git = shutil.which("git")
    if git is None:
        msg = "git is required to classify validation workspace paths"
        raise ValueError(msg)
    relative = path.relative_to(repository_root).as_posix()
    tracked = run_command_bytes(
        git, ("--literal-pathspecs", "-C", str(repository_root), "ls-files", "--error-unmatch", "--", relative), check=False, timeout=10
    )
    if tracked.returncode not in {0, 1}:
        tracked.check_returncode()
    if tracked.returncode == 0:
        return "tracked"
    try:
        status_source, status_rule = _verified_artifact_status(relative, "ignored", repository_root)
    except ValueError:
        return "untracked"
    return "ignored" if status_source == "repository-rule" and status_rule is not None else "untracked"


def capture_workspace_snapshot(dispatch: dict[str, Any]) -> dict[str, Any]:
    """Capture canonical digests for one materialized validation workspace policy."""
    raw_unit = dispatch.get("validation_unit")
    if not isinstance(raw_unit, dict):
        msg = "workspace snapshots require a materialized validation dispatch"
        raise TypeError(msg)
    unit = _validation_unit(raw_unit)
    repository_root = Path(_required_text(dispatch, "repository_root")).resolve()
    if unit.requires_isolation:
        _validate_isolated_workspace_paths(dispatch, unit, ())
    approved = {artifact.path: artifact for artifact in unit.allowed_artifacts}
    paths = tuple(dict.fromkeys((*unit.expected_workspace_effects, *approved)))
    records: list[dict[str, object]] = []
    for raw_path in paths:
        resolved = _workspace_path(raw_path, repository_root)
        exists, digest, snapshot_mode = _workspace_content_digest(resolved)
        status = _git_path_status(repository_root, resolved)
        records.append({"digest": digest, "exists": exists, "path": raw_path, "snapshot_mode": snapshot_mode, "status": status})
    return {"node_id": unit.node_id, "records": records, "schema_version": 1, "source_state": list(unit.source_state)}


def _workspace_snapshot(dispatch: dict[str, Any], name: str) -> dict[str, tuple[str, str, bool, str]]:
    records = _records(dispatch, name)
    snapshot: dict[str, tuple[str, str, bool, str]] = {}
    for ordinal, raw in enumerate(records, start=1):
        path = _required_text(raw, "path")
        digest = _required_text(raw, "digest")
        status = _required_text(raw, "status")
        snapshot_mode = _required_text(raw, "snapshot_mode")
        exists = raw.get("exists", True)
        if not isinstance(exists, bool):
            msg = f"{name} record {ordinal} exists must be a boolean"
            raise TypeError(msg)
        if path in snapshot:
            msg = f"{name} contains duplicate path {path}"
            raise ValueError(msg)
        if status not in {"ignored", "outside-repository", "tracked", "untracked"}:
            msg = f"{name} record {ordinal} has invalid status {status}"
            raise ValueError(msg)
        _sha256_digest(digest, f"{name} digest")
        if snapshot_mode not in VALIDATION_ARTIFACT_DIGEST_MODES | {"absent-v1"}:
            msg = f"{name} record {ordinal} has invalid snapshot mode {snapshot_mode}"
            raise ValueError(msg)
        if exists == (snapshot_mode == "absent-v1") or (not exists and digest != digest_bytes(b"absent")):
            msg = f"{name} record {ordinal} has inconsistent existence and snapshot identity"
            raise ValueError(msg)
        snapshot[path] = (status, digest, exists, snapshot_mode)
    return snapshot


def _path_allowed(path: str, allowed: tuple[str, ...]) -> bool:
    return any(path == candidate or path.startswith(candidate.rstrip("/") + "/") for candidate in allowed)


def _validate_isolated_workspace_paths(dispatch: dict[str, Any], unit: ValidationUnit, changed: tuple[str, ...]) -> None:
    repository_root = Path(_required_text(dispatch, "repository_root")).resolve()
    inside = tuple(directory for directory in unit.working_directories if Path(directory).resolve(strict=False).is_relative_to(repository_root))
    if inside:
        msg = "source-mutating validation requires working directories outside the captured repository: " + ", ".join(inside)
        raise ValueError(msg)
    isolation_root = Path(unit.isolation_root or "").resolve(strict=False)
    if isolation_root.is_relative_to(repository_root) or repository_root.is_relative_to(isolation_root):
        msg = f"isolated validation root overlaps the captured repository: {isolation_root}"
        raise ValueError(msg)
    outside_root = tuple(directory for directory in unit.working_directories if not Path(directory).resolve(strict=False).is_relative_to(isolation_root))
    if outside_root:
        msg = "isolated validation working directories must be under the dispatched isolation root: " + ", ".join(outside_root)
        raise ValueError(msg)
    outside_artifacts = tuple(
        artifact.path
        for artifact in unit.allowed_artifacts
        if artifact.repository_status == "outside-repository" and not Path(artifact.path).resolve(strict=False).is_relative_to(isolation_root)
    )
    if outside_artifacts:
        msg = "isolated validation artifacts must be under the dispatched isolation root: " + ", ".join(outside_artifacts)
        raise ValueError(msg)
    outside_changes = tuple(path for path in changed if not Path(path).resolve(strict=False).is_relative_to(isolation_root))
    if outside_changes:
        msg = "isolated validation changed workspace paths must be under the dispatched isolation root: " + ", ".join(outside_changes)
        raise ValueError(msg)


def _validation_workspace_audit(dispatch: dict[str, Any], unit: ValidationUnit) -> dict[str, object]:
    required = bool(unit.allowed_artifacts or unit.expected_workspace_effects or unit.requires_isolation or unit.isolation_root)
    if not required and "workspace_before" not in dispatch and "workspace_after" not in dispatch:
        return {"observed": False, "unexpected_paths": []}
    if "workspace_before" not in dispatch or "workspace_after" not in dispatch:
        msg = "validation with declared workspace effects requires trusted workspace_before and workspace_after snapshots"
        raise ValueError(msg)
    before = _workspace_snapshot(dispatch, "workspace_before")
    after = _workspace_snapshot(dispatch, "workspace_after")
    changed = tuple(sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path)))
    allowed = (*unit.expected_workspace_effects, *(artifact.path for artifact in unit.allowed_artifacts))
    unexpected = tuple(path for path in changed if not _path_allowed(path, allowed))
    unsafe = tuple(path for path in changed if after.get(path, before.get(path, ("", "", False, "absent-v1")))[0] not in {"ignored", "outside-repository"})
    if unexpected:
        msg = "validation produced unexpected workspace paths: " + ", ".join(unexpected)
        raise ValueError(msg)
    if unsafe:
        msg = "validation changed tracked or nonignored repository paths: " + ", ".join(unsafe)
        raise ValueError(msg)
    if unit.requires_isolation:
        _validate_isolated_workspace_paths(dispatch, unit, changed)
    return {
        "changed_paths": list(changed),
        "observed": True,
        "snapshot_modes": {path: (after[path] if path in after else before[path])[3] for path in sorted(set(before) | set(after))},
        "unexpected_paths": [],
    }


def compile_validation(document: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:  # noqa: C901, PLR0915
    """Compile one exact validation execution payload into verified evidence."""
    dispatch = document.get("dispatch")
    payload = document.get("payload")
    if not isinstance(dispatch, dict) or not isinstance(payload, dict):
        msg = "compile-validation input requires dispatch and payload objects"
        raise TypeError(msg)
    raw_unit = dispatch.get("validation_unit")
    if not isinstance(raw_unit, dict):
        msg = "compile-validation dispatch requires validation_unit"
        raise TypeError(msg)
    unit = _validation_unit(raw_unit)
    status = _required_text(payload, "status")
    if status not in {"passed", "failed", "blocked", "reused", "not-applicable"}:
        msg = f"invalid validation status {status}"
        raise ValueError(msg)
    skill_path = Path(_required_text(dispatch, "skill_path")).resolve()
    reference_paths = tuple(Path(path).resolve() for path in _text_list(dispatch, "reference_paths"))
    if not skill_path.is_file() or any(not path.is_file() for path in reference_paths):
        msg = "validation skill and reference paths must exist"
        raise ValueError(msg)
    execution_location = _required_text(dispatch, "execution_location")
    worker_created = dispatch.get("worker_created")
    fresh_context = dispatch.get("fresh_context")
    if not isinstance(worker_created, bool) or not isinstance(fresh_context, bool):
        msg = "worker_created and fresh_context must be booleans"
        raise TypeError(msg)
    if execution_location == "worker" and fresh_context is not True:
        msg = "every compact validator worker requires fresh_context=true"
        raise ValueError(msg)
    expected = unit.source_state
    fingerprints = _dispatch_fingerprints({**dispatch, "source_state": list(expected)})
    if fingerprints.metadata_transitions and (
        fingerprints.before != fingerprints.after or fingerprints.after != fingerprints.metadata_transitions[-1].after.source_state or status == "reused"
    ):
        msg = "validation must execute entirely on the current external metadata state"
        raise ValueError(msg)
    expectation = validation_evidence_expectation(
        unit,
        skill_path=str(skill_path),
        skill_digest=_file_identity_digest(str(skill_path)),
        reference_digests=tuple((str(path), _file_identity_digest(str(path))) for path in reference_paths),
        execution_profile=_required_text(dispatch, "execution_profile"),
        execution_location=execution_location,
    )
    evidence = ValidationEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id=_required_text(dispatch, "evidence_id"),
        node_id=unit.node_id,
        requirement_ids=unit.requirement_ids,
        skill_digest=expectation.skill_digest,
        reference_digests=expectation.reference_digests,
        fingerprints=fingerprints,
        execution_profile=expectation.execution_profile,
        execution_location=execution_location,
        worker_created=worker_created,
        fresh_context=fresh_context,
        status=status,
        command_identity_digest=expectation.command_identity_digest,
        environment_digest=expectation.environment_digest,
        raw_result_artifact_id=_required_text(dispatch, "artifact_id"),
        raw_result_digest="pending",
    )
    limitations = _text_list(payload, "limitations")
    if status == "blocked" and not limitations:
        msg = "blocked validation payload requires a limitation"
        raise ValueError(msg)
    workspace_audit = _validation_workspace_audit(dispatch, unit)
    workspace_after = _workspace_snapshot(dispatch, "workspace_after") if workspace_audit["observed"] else {}
    artifacts_body, artifacts = _validation_artifacts_body(payload, unit, workspace_after)
    payload = {
        **payload,
        "artifacts": [
            {
                "artifact_digest": artifact.artifact_digest,
                "artifact_digest_mode": artifact.artifact_digest_mode,
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind,
                "path": artifact.path,
                "repository_status": artifact.repository_status,
            }
            for artifact in artifacts
        ],
    }
    environment_identity = _validation_environment_identity(unit)
    executions_body, execution_results = _validation_executions_body(payload, evidence, environment_identity, artifacts)
    if status in {"passed", "failed"} and len(execution_results) != len(unit.commands):
        msg = "executed validation payload must account for every command"
        raise ValueError(msg)
    disposition = status if status in {"passed", "failed", "blocked", "reused"} else "blocked"
    requirement_dispositions = tuple(disposition for _ in unit.requirement_ids)
    requirement_counts = {item: requirement_dispositions.count(item) for item in ("passed", "failed", "blocked", "reused")}
    execution_counts = {item: execution_results.count(item) for item in ("passed", "failed", "blocked", "not-run")}
    overall = {"passed": "PASSED", "failed": "FAILED", "blocked": "BLOCKED", "reused": "REUSED", "not-applicable": "NOT-APPLICABLE"}[status]
    canonical_payload = canonical_json(payload)
    machine_payload = {
        "after_repository_state_fingerprint": fingerprints.after[2],
        "after_scope_fingerprint": fingerprints.after[0],
        "after_worktree_fingerprint": fingerprints.after[1],
        "artifact_id": evidence.raw_result_artifact_id,
        "before_repository_state_fingerprint": fingerprints.before[2],
        "before_scope_fingerprint": fingerprints.before[0],
        "before_worktree_fingerprint": fingerprints.before[1],
        "command_identity_digest": expectation.command_identity_digest,
        "environment_digest": expectation.environment_digest,
        "evidence_id": evidence.evidence_id,
        "git_mutated": False,
        "mode": "validation",
        "node_id": evidence.node_id,
        "repository_state_fingerprint": expected[2],
        "requirement_ids": list(unit.requirement_ids),
        "result_type": "validation-result",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scope_fingerprint": expected[0],
        "skill_id": "review-validator",
        "source_mutated": False,
        "status": status,
        "validation_status": status,
        "worktree_fingerprint": expected[1],
    }
    header = "\n".join(
        (
            f"- Node ID: {evidence.node_id}",
            "- Skill: review-validator",
            "- Invocation: graph-dispatched",
            f"- Evidence schema version: {EVIDENCE_SCHEMA_VERSION}",
            f"- Execution profile: {evidence.execution_profile}",
            f"- Execution location: {evidence.execution_location}",
            f"- Status: {status}",
            f"- Scope fingerprint: {expected[0]}",
            f"- Worktree fingerprint: {expected[1]}",
            f"- Repository state fingerprint: {expected[2]}",
        )
    )
    section_bodies = {
        "## Outcome Summary": "\n".join(
            (
                f"- Overall: {overall}",
                "- Requirements: " + "; ".join(f"{item} {requirement_counts[item]}" for item in ("passed", "failed", "blocked", "reused")),
                "- Executions: " + "; ".join(f"{item} {execution_counts[item]}" for item in ("passed", "failed", "blocked", "not-run")),
                "- Review findings: not evaluated (validation-only)",
                "- Review severities: P0 not evaluated; P1 not evaluated; P2 not evaluated; P3 not evaluated",
            )
        ),
        "## Skill Loading": "\n".join(
            (
                f"- Skill file: {skill_path}",
                f"- Skill digest: {expectation.skill_digest}",
                f"- References loaded: {', '.join(str(path) for path in reference_paths) or 'none'}",
                f"- Reference digests: {', '.join(f'{path}={digest}' for path, digest in expectation.reference_digests) or 'none'}",
            )
        ),
        "## Validation Plan": _validation_plan_expected_body(expectation),
        "## State Verification": _validation_state_verification(dispatch, evidence),
        "## Requirements": _validation_requirements_expected_body(expectation, evidence),
        "## Executions": executions_body,
        "## Reused Evidence": _validation_reuse_body(unit, evidence, expectation.command_identity_digest, expectation.environment_digest),
        "## Artifacts": artifacts_body,
        "## Source And Git State": "- Source-controlled files changed: none\n- Git state mutated: no",
        "## Validation Ledger Export": "\n".join(f"- {label}: {value}" for label, value in _validation_ledger_expected_fields(expectation, evidence)),
        "## Limitations": "\n".join(
            (
                f"- Worker payload digest: {digest_bytes(canonical_payload.encode())}",
                f"- Canonical worker payload: {canonical_payload}",
                *(limitations or ("none",)),
            )
        ),
    }
    sections = (
        "## Outcome Summary",
        "## Skill Loading",
        "## Validation Plan",
        "## State Verification",
        "## Requirements",
        "## Executions",
        "## Reused Evidence",
        "## Artifacts",
        "## Source And Git State",
        "## Validation Ledger Export",
        "## Limitations",
        "## Machine Evidence",
    )
    body = "\n\n".join(f"{section}\n\n{section_bodies[section]}" for section in sections[:-1])
    content = (
        f"# Validation Result\n\n{header}\n\n{body}\n\n## Machine Evidence\n\n"
        f"{NATIVE_EVIDENCE_BLOCK_OPEN}{canonical_json(machine_payload)}{NATIVE_EVIDENCE_BLOCK_CLOSE}\n"
    ).encode()
    evidence = replace(evidence, raw_result_digest=digest_bytes(content))
    envelope_assessment = assess_validation_evidence(expectation, evidence)
    native_blockers = _validation_native_result_blockers(content, expectation, evidence)
    blockers = (*envelope_assessment.blockers, *native_blockers)
    if blockers:
        msg = "compiled validation artifact failed verification: " + "; ".join(blockers)
        raise ValueError(msg)
    normalized = _validation_normalized_record(payload, evidence, dispatch.get("source_capture"))
    return content, {
        "expectation": asdict(expectation),
        "evidence": asdict(evidence),
        "payload_digest": digest_bytes(canonical_payload.encode()),
        "artifact_digest": evidence.raw_result_digest,
        "normalized_record": normalized,
        **({"source_capture": dispatch["source_capture"]} if "captured_software_inputs" in normalized or "captured_doi_inputs" in normalized else {}),
        "workspace_audit": workspace_audit,
    }


def _worker_node(raw: dict[str, Any]) -> WorkerNode:
    return WorkerNode(
        node_id=_required_text(raw, "node_id"),
        skill_id=_required_text(raw, "skill_id"),
        skill_path=_required_text(raw, "skill_path"),
        mode=_required_text(raw, "mode"),
        priority=_required_text(raw, "priority"),
        required=_required_bool(raw, "required"),
        requirement_ids=_string_tuple(raw, "requirement_ids"),
        coverage=_string_tuple(raw, "coverage"),
        predecessors=_string_tuple(raw, "predecessors"),
        synthesis_dependency=raw.get("synthesis_dependency"),
        router_ids=_string_tuple(raw, "router_ids"),
        rule_ids=_string_tuple(raw, "rule_ids"),
        selection_reasons=_string_tuple(raw, "selection_reasons"),
        owners=_string_tuple(raw, "owners"),
        instruction_paths=_string_tuple(raw, "instruction_paths"),
        static_references=_string_tuple(raw, "static_references"),
        change_target=raw.get("change_target"),
        skill_digest=_required_text(raw, "skill_digest"),
        reference_digests=_string_pairs(raw, "reference_digests"),
    )


def _routing_decision(raw: dict[str, Any]) -> RoutingDecision:
    return RoutingDecision(
        catalog_id=_required_text(raw, "catalog_id"),
        requirement_id=_required_text(raw, "requirement_id"),
        router_id=_required_text(raw, "router_id"),
        rule_id=_required_text(raw, "rule_id"),
        skill_id=_required_text(raw, "skill_id"),
        skill_path=_required_text(raw, "skill_path"),
        disposition=_required_text(raw, "disposition"),
        reason=_required_text(raw, "reason"),
        applicability_evidence=_string_tuple(raw, "applicability_evidence"),
        review_surface=_string_tuple(raw, "review_surface"),
        instruction_paths=_string_tuple(raw, "instruction_paths"),
        static_references=_string_tuple(raw, "static_references"),
        validation_requirement_ids=_string_tuple(raw, "validation_requirement_ids"),
        synthesis_dependency=raw.get("synthesis_dependency"),
        priority=raw.get("priority"),
        owners=_string_tuple(raw, "owners"),
        evidence_id=raw.get("evidence_id"),
    )


def _reused_review_identity(raw: dict[str, Any]) -> ReusedReviewEvidencePlan:
    return ReusedReviewEvidencePlan(
        requirement_id=_required_text(raw, "requirement_id"),
        evidence_id=_required_text(raw, "evidence_id"),
        skill_id=_required_text(raw, "skill_id"),
        skill_path=_required_text(raw, "skill_path"),
        mode=_required_text(raw, "mode"),
        static_references=_string_tuple(raw, "static_references"),
        skill_digest=_required_text(raw, "skill_digest"),
        reference_digests=_string_pairs(raw, "reference_digests"),
        change_target=raw.get("change_target"),
        planned_paths=_string_tuple(raw, "planned_paths"),
        planned_path_line_bounds=_path_line_bounds(raw, "planned_path_line_bounds"),
    )


def _graph_plan(raw: dict[str, Any]) -> GraphPlan:
    worker_nodes = _records(raw, "actual_worker_nodes")
    epochs = _records(raw, "execution_epochs")
    validation_units = _records(raw, "coalesced_validation_units")
    validation_mappings = _records(raw, "validation_evidence_mapping")
    routing_decisions = _records(raw, "routing_decisions")
    reuse_identities = _records(raw, "reused_review_identities")
    plan = GraphPlan(
        execution_profile=_required_text(raw, "execution_profile"),
        worker_budget=_required_int(raw, "worker_budget"),
        recovery_finalization_reserve=_required_int(raw, "recovery_finalization_reserve"),
        selected_review_requirements=_string_tuple(raw, "selected_review_requirements"),
        complete_node_count=_required_int(raw, "complete_node_count"),
        actual_worker_nodes=tuple(_worker_node(node) for node in worker_nodes),
        execution_epochs=tuple(
            ExecutionEpoch(
                ordinal=_required_int(epoch, "ordinal"),
                node_ids=_string_tuple(epoch, "node_ids"),
                worker_budget=_required_int(epoch, "worker_budget"),
                recovery_finalization_reserve=_required_int(epoch, "recovery_finalization_reserve"),
                requires_fresh_root=_required_bool(epoch, "requires_fresh_root"),
            )
            for epoch in epochs
        ),
        current_epoch_node_ids=_string_tuple(raw, "current_epoch_node_ids"),
        requires_continuation=_required_bool(raw, "requires_continuation"),
        coalesced_validation_units=tuple(_validation_unit(unit) for unit in validation_units),
        selected_validation_units=_string_tuple(raw, "selected_validation_units"),
        synthesis_nodes=_string_tuple(raw, "synthesis_nodes"),
        requirement_to_node=_string_pairs(raw, "requirement_to_node"),
        validation_evidence_mapping=tuple(
            ValidationEvidenceMapping(
                requirement_id=_required_text(mapping, "requirement_id"),
                validation_unit_id=_required_text(mapping, "validation_unit_id"),
                evidence_id=mapping.get("evidence_id"),
            )
            for mapping in validation_mappings
        ),
        captured_path_line_bounds=_path_line_bounds(raw, "captured_path_line_bounds"),
        routing_catalog_closed=_required_bool(raw, "routing_catalog_closed"),
        consulted_routers=_string_tuple(raw, "consulted_routers"),
        routing_decisions=tuple(_routing_decision(decision) for decision in routing_decisions),
        exact_reused_review_evidence=_string_pairs(raw, "exact_reused_review_evidence"),
        reused_review_identities=tuple(_reused_review_identity(identity) for identity in reuse_identities),
        user_excluded_catalog_ids=_string_tuple(raw, "user_excluded_catalog_ids"),
        routing_completion_blockers=_string_tuple(raw, "routing_completion_blockers"),
        dispatch_allowed=_required_bool(raw, "dispatch_allowed"),
        blockers=_string_tuple(raw, "blockers"),
        audit_reuse_transitions=tuple(
            AuditReuseTransition(
                evidence_id=_required_text(item, "evidence_id"),
                source_state=_state(item, "source_state"),
                target_state=_state(item, "target_state"),
                artifact_digest=_required_text(item, "artifact_digest"),
                artifact_path=_required_text(item, "artifact_path"),
                metadata_path=_required_text(item, "metadata_path"),
                instruction_digests=_string_pairs(item, "instruction_digests"),
                metadata_transitions=tuple(metadata_transition(raw) for raw in _records(item, "metadata_transitions")),
            )
            for item in _records(raw, "audit_reuse_transitions")
        ),
        reuse_source_snapshots=tuple(source_snapshot(item) for item in _records(raw, "reuse_source_snapshots")),
        audit_delta_reviews=_records(raw, "audit_delta_reviews"),
        validation_recoveries=_records(raw, "validation_recoveries"),
        pre_review_validation_nodes=_string_tuple(raw, "pre_review_validation_nodes"),
        validation_exclusions=tuple(
            ValidationExclusion(
                originating_evidence_id=_required_text(item, "originating_evidence_id"),
                requirement_id=_required_text(item, "requirement_id"),
                requirement_digest=_sha256_digest(item.get("requirement_digest"), "requirement_digest"),
                reason=_required_text(item, "reason"),
            )
            for item in _records(raw, "validation_exclusions")
        ),
    )
    validate_validation_barrier(plan)
    return plan


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        msg = f"JSON root must be an object: {path}"
        raise TypeError(msg)
    return value


def _operation_document(document: dict[str, Any], operation: str) -> dict[str, Any]:
    """Accept a bootstrap bundle directly where it owns the operation input."""
    field = {"materialize-dispatches": "materialization_input", "routing-projection": "planning_input", "preflight-validation": "preflight_input"}.get(
        operation
    )
    if field is None and operation in {"compile-node", "finalize-proof", "journal-append", "next-ready", "snapshot-workspace"}:
        field = "lifecycle_input"
    if field is None or field not in document:
        return document
    nested = document.get(field)
    if not isinstance(nested, dict):
        msg = f"bootstrap bundle {field} must be an object"
        raise TypeError(msg)
    return dict(nested)


def _canonical_worker_payload(content: bytes, *, expectation: ReviewEvidenceExpectation | None = None) -> dict[str, Any]:
    prefix = b"- Canonical worker payload: "
    matches = [line.removeprefix(prefix) for line in content.splitlines() if line.startswith(prefix)]
    reference_prefix = b"- Worker payload reference: "
    references = [line.removeprefix(reference_prefix) for line in content.splitlines() if line.startswith(reference_prefix)]
    bound_payload = expectation.canonical_worker_payload if expectation else None
    if references or bound_payload is not None:
        if len(references) != 1 or matches or bound_payload is None:
            msg = "compiled artifact must contain exactly one reference to its bound canonical worker payload"
            raise ValueError(msg)
        if json.loads(references[0]) != worker_payload_reference(bound_payload):
            msg = "canonical worker payload reference differs from its bound metadata"
            raise ValueError(msg)
        return bound_payload
    if len(matches) != 1:
        msg = "compiled artifact must contain exactly one canonical worker payload"
        raise ValueError(msg)
    payload = json.loads(matches[0])
    if not isinstance(payload, dict):
        msg = "canonical worker payload must be an object"
        raise TypeError(msg)
    return payload


def _verify_independent_payload_binding(content: bytes, metadata: dict[str, Any], expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> None:
    """Bind structured judgments to sealed bytes and every rendered native section."""
    payload = _canonical_worker_payload(content)
    if metadata.get("payload_digest") != digest_bytes(canonical_json(payload).encode()):
        msg = "independent canonical payload digest differs from metadata"
        raise ValueError(msg)
    if "worker_payload_path" in metadata and json.loads(Path(metadata["worker_payload_path"]).read_bytes()) != payload:
        msg = "independent canonical payload differs from sealed worker bytes"
        raise ValueError(msg)
    native = render_independent_payload(
        payload,
        {
            "planned_paths": list(expectation.planned_paths),
            "change_target": expectation.change_target,
            "source_state": list(expectation.source_state),
            "before_state": list(evidence.fingerprints.before),
            "after_state": list(evidence.fingerprints.after),
            "adversarial_checks": list(_independent_adversarial_checks(expectation.planned_paths)),
        },
    )
    if digest_bytes(native) != metadata.get("native_input_digest") or payload["status"] != evidence.status:
        msg = "independent rendered payload differs from its bound native input"
        raise ValueError(msg)
    expected = _independent_input_sections(native)
    findings = _independent_findings(expected["## Findings"], evidence.node_id, evidence.status)
    handoffs = _independent_handoffs(expected["## Routing Handoffs"], evidence.node_id, {})
    expected["## Findings"] = _independent_findings_body(findings, evidence.status)
    expected["## Routing Handoffs"] = _independent_handoffs_body(handoffs)
    sections, blockers = _native_section_bodies(content.decode(), (*_INDEPENDENT_NATIVE_SECTIONS, "## Review Graph Envelope", "## Machine Evidence"))
    if blockers or sections is None or any(sections[key] != value for key, value in expected.items()):
        msg = "independent native evidence differs from its canonical payload"
        raise ValueError(msg)
    limitations = _native_field_values(sections["## Review Graph Envelope"], "Limitations")
    if limitations != ("; ".join(payload["limitations"]) or "none",):
        msg = "independent limitations differ from its canonical payload"
        raise ValueError(msg)


def _load_evidence_source(  # noqa: C901, PLR0912, PLR0915
    raw: dict[str, Any], *, require_normalized: bool = False
) -> tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, dict[str, Any] | None]:
    metadata_path = Path(_required_text(raw, "metadata_path")).resolve()
    artifact_path = Path(_required_text(raw, "artifact_path")).resolve()
    metadata = _read_json_object(metadata_path)
    expectation_raw = metadata.get("expectation")
    evidence_raw = metadata.get("evidence")
    if not isinstance(expectation_raw, dict) or not isinstance(evidence_raw, dict):
        msg = f"evidence metadata lacks expectation or evidence: {metadata_path}"
        raise TypeError(msg)
    content = artifact_path.read_bytes()
    artifact_digest = digest_bytes(content)
    if metadata.get("artifact_digest") != artifact_digest or evidence_raw.get("raw_result_digest") != artifact_digest:
        msg = f"artifact digest does not match evidence metadata: {artifact_path}"
        raise ValueError(msg)
    payload_bytes: bytes | None = None
    worker_payload_fields = (metadata.get("worker_payload_path"), metadata.get("worker_payload_digest"), metadata.get("worker_payload_byte_count"))
    if any(value is not None for value in worker_payload_fields):
        payload_path, payload_digest, payload_byte_count = worker_payload_fields
        if not isinstance(payload_path, str) or not isinstance(payload_digest, str) or not isinstance(payload_byte_count, int):
            msg = f"worker payload provenance is incomplete: {metadata_path}"
            raise TypeError(msg)
        payload_bytes = Path(payload_path).read_bytes()
        if digest_bytes(payload_bytes) != payload_digest or len(payload_bytes) != payload_byte_count:
            msg = f"worker payload bytes do not match evidence metadata: {payload_path}"
            raise ValueError(msg)

    kind = raw.get("kind")
    inferred_kind = "validation" if "validation_unit" in expectation_raw else "review"
    if kind is None:
        kind = inferred_kind
    if kind not in {"review", "validation"} or kind != inferred_kind:
        msg = f"evidence source kind does not match metadata: {metadata_path}"
        raise ValueError(msg)
    if kind == "review":
        expectation = _review_expectation(expectation_raw)
        evidence = _review_evidence(evidence_raw)
        if expectation.coverage_reuse is not None:
            _verify_delta_context(
                expectation.coverage_reuse,
                {**expectation_raw, "owned_paths": list(expectation.audit_input_identity.owned_paths) if expectation.audit_input_identity else []},
            )
        assessment = assess_review_evidence(expectation, evidence)
        blockers = (*assessment.blockers, *_review_native_result_blockers(content, expectation, evidence))
    else:
        expectation = _validation_expectation(expectation_raw)
        evidence = _validation_evidence(evidence_raw)
        assessment = assess_validation_evidence(expectation, evidence)
        blockers = (*assessment.blockers, *_validation_native_result_blockers(content, expectation, evidence))
    if blockers:
        msg = f"evidence source failed verification {artifact_path}: " + "; ".join(blockers)
        raise ValueError(msg)

    if isinstance(expectation, ReviewEvidenceExpectation) and expectation.canonical_worker_payload is not None:
        bound_payload = _canonical_worker_payload(content, expectation=expectation)
        if metadata.get("payload_digest") != digest_bytes(canonical_json(bound_payload).encode()):
            msg = "bound canonical worker payload digest differs from metadata"
            raise ValueError(msg)
        if payload_bytes is not None and json.loads(payload_bytes) != bound_payload:
            msg = "bound canonical worker payload differs from sealed worker bytes"
            raise ValueError(msg)
        _validate_review_coverage_partitions(
            {**expectation_raw, "owned_paths": list(expectation.audit_input_identity.owned_paths) if expectation.audit_input_identity else []}, bound_payload
        )

    if isinstance(expectation, ReviewEvidenceExpectation) and isinstance(evidence, ReviewEvidence) and expectation.mode == "independent-review":
        _verify_independent_payload_binding(content, metadata, expectation, evidence)
    normalized = metadata.get("normalized_record")
    if normalized is not None and not isinstance(normalized, dict):
        msg = f"normalized record must be an object: {metadata_path}"
        raise ValueError(msg)
    if normalized is not None:
        if kind == "review":
            if not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence):
                msg = f"review metadata has mismatched typed evidence: {metadata_path}"
                raise TypeError(msg)
            if expectation.mode == "independent-review":
                recomputed = _independent_normalized_record(content, expectation, evidence)
            else:
                payload = _canonical_worker_payload(content, expectation=expectation)
                _validate_audit_caveats(
                    {
                        "mode": expectation.mode,
                        "before_state": list(evidence.fingerprints.before),
                        "after_state": list(evidence.fingerprints.after),
                        "git_mutated": evidence.git_mutated,
                    },
                    payload,
                )
                _verify_audit_metadata(payload, evidence.fingerprints, expectation.coverage_reuse)
                if expectation.mode == "synthesis":
                    require_schema(payload, _SYNTHESIS_PAYLOAD_SCHEMA)
                    validate_synthesis(payload, expectation.predecessor_evidence_ids, metadata.get("synthesis_bundle"))
                payload_digest = digest_bytes(canonical_json(payload).encode())
                if metadata.get("payload_digest") != payload_digest:
                    msg = f"worker payload digest does not match compiled artifact: {artifact_path}"
                    raise ValueError(msg)
                recomputed = _review_normalized_record(payload, expectation, evidence)
        else:
            if not isinstance(expectation, ValidationEvidenceExpectation) or not isinstance(evidence, ValidationEvidence):
                msg = f"validation metadata has mismatched typed evidence: {metadata_path}"
                raise TypeError(msg)
            payload = _canonical_worker_payload(content)
            payload_digest = digest_bytes(canonical_json(payload).encode())
            if metadata.get("payload_digest") != payload_digest:
                msg = f"worker payload digest does not match compiled artifact: {artifact_path}"
                raise ValueError(msg)
            recomputed = _validation_normalized_record(payload, evidence, metadata.get("source_capture"))
        if normalized != recomputed:
            msg = f"normalized record does not match compiled artifact: {metadata_path}"
            raise ValueError(msg)
    if require_normalized and normalized is None:
        msg = f"synthesis requires compiler-derived normalized metadata: {metadata_path}"
        raise ValueError(msg)
    return kind, expectation, evidence, content, normalized


def _reused_validation_reference(
    plan: GraphPlan, record: dict[str, Any], requirement: dict[str, Any], unit: ValidationUnit, prior: ValidationUnit | None
) -> dict[str, Any] | None:
    """Bind an accepted audit's old digest through its verified source-only reuse."""
    transitions = tuple(item for item in plan.audit_reuse_transitions if item.evidence_id == record["evidence_id"])
    if len(transitions) != 1:
        return None
    transition = transitions[0]
    if (
        transition.target_state != unit.source_state
        or transition.artifact_digest != record.get("artifact_digest")
        or tuple(record.get("observed_source_state", ())) not in metadata_states(transition.source_state, transition.metadata_transitions)
    ):
        return None
    # Reconstruct the original digest without changing any execution-contract field.
    # Callers have already verified the immutable record and audit reuse transition.
    candidates = (unit,) if prior is None else (unit, prior)
    if requirement["planned_validation_digest"] not in {
        _planned_validation_digest(replace(candidate, source_state=transition.source_state)) for candidate in candidates
    }:
        return None
    return {
        "original_planned_validation_digest": requirement["planned_validation_digest"],
        "original_source_state": list(transition.source_state),
        "replacement_planned_validation_digest": _planned_validation_digest(unit),
        "replacement_source_state": list(unit.source_state),
    }


def _validation_reconciliation(plan: GraphPlan, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind discovered needs to exact command plans, never to a generic CI pass."""
    units = {requirement: (unit, _planned_validation_digest(unit)) for unit in plan.coalesced_validation_units for requirement in unit.requirement_ids}
    exclusions = {(item.originating_evidence_id, item.requirement_id, item.requirement_digest): item for item in plan.validation_exclusions}
    results: list[dict[str, Any]] = []
    blockers: list[str] = []
    for record in records:
        if record.get("status") not in {"completed", "no-findings"}:
            continue
        for requirement_id, requirement in _validation_records(record):
            digest = digest_bytes(canonical_json(requirement).encode())
            origin = _required_text(record, "evidence_id")
            planned = units.get(requirement_id)
            unit = planned[0] if planned is not None else None
            original = next(
                (
                    item
                    for item in plan.validation_recoveries
                    if unit is not None and item["node_id"] == unit.node_id and tuple(item["source_state"]) == unit.source_state
                ),
                None,
            )
            prior = (
                replace(unit, environment=original["previous_environment"], features=tuple(original.get("previous_features", unit.features)))
                if unit is not None and original is not None
                else None
            )
            compatible_digests = {planned[1]} if planned is not None else set()
            if prior is not None:
                compatible_digests.add(_planned_validation_digest(prior))
            exclusion = exclusions.get((origin, requirement_id, digest))
            reuse_binding = None
            if "planned_validation_digest" in requirement:
                if unit is not None and unit.required:
                    reuse_binding = _reused_validation_reference(plan, record, requirement, unit, prior)
                    if reuse_binding is not None:
                        compatible_digests.add(reuse_binding["original_planned_validation_digest"])
                matches = requirement["planned_validation_digest"] in compatible_digests and unit is not None and unit.required
            else:
                matches = unit is not None and (
                    unit.commands == _text_list(requirement, "commands")
                    and unit.working_directories == (requirement["working_directory"],) * len(unit.commands)
                    and requirement["environment"] in {unit.environment, prior.environment if prior is not None else unit.environment}
                    and unit.dependency_policy == requirement["dependency_policy"]
                    and unit.required
                )
            resolution = "planned" if matches else "user-excluded" if exclusion else "identity-conflict" if unit else "requires-expansion"
            if resolution in {"identity-conflict", "requires-expansion"}:
                blockers.append(f"validation requirement {requirement_id} from {origin} needs exact validation reconciliation ({resolution})")
            results.append(
                {
                    "originating_evidence_id": origin,
                    "requirement": requirement,
                    "requirement_digest": digest,
                    "requirement_id": requirement_id,
                    "resolution": resolution,
                    "reason": exclusion.reason if exclusion and not matches else None,
                    "validation_unit_id": unit.node_id if matches and unit else None,
                    **({"reuse_binding": reuse_binding} if reuse_binding is not None else {}),
                }
            )
    return {"blockers": blockers, "requirements": sorted(results, key=lambda item: (item["requirement_id"], item["originating_evidence_id"]))}


def _synthesis_plan_context(plan: GraphPlan, records: list[dict[str, Any]]) -> dict[str, Any]:
    by_evidence = {str(record["evidence_id"]): record for record in records}
    review_ids = tuple(str(record["evidence_id"]) for record in records if record.get("record_type") == "review")
    handoffs, unresolved, blockers = _reconciled_handoffs(plan, by_evidence, review_ids)
    return {
        "plan_digest": _plan_digest(plan),
        "consulted_routers": list(plan.consulted_routers),
        "routing_catalog_closed": plan.routing_catalog_closed,
        "routing_completion_blockers": list(plan.routing_completion_blockers),
        "routing_counts": dict(sorted(Counter(item.disposition for item in plan.routing_decisions).items())),
        "routing_exceptions": [
            {"catalog_id": item.catalog_id, "disposition": item.disposition, "reason": item.reason, "evidence_id": item.evidence_id}
            for item in plan.routing_decisions
            if item.disposition not in {"selected", "not-applicable"}
        ],
        "user_excluded_catalog_ids": list(plan.user_excluded_catalog_ids),
        "exact_reused_review_evidence": [list(item) for item in plan.exact_reused_review_evidence],
        "requirement_to_node": [list(item) for item in plan.requirement_to_node],
        "validation_evidence_mapping": [asdict(item) for item in plan.validation_evidence_mapping],
        "validation_environments": {unit.node_id: json.loads(_validation_environment_identity(unit)) for unit in plan.coalesced_validation_units},
        "validation_exclusions": [asdict(item) for item in plan.validation_exclusions],
        "validation_recoveries": list(plan.validation_recoveries),
        "validation_reconciliation": _validation_reconciliation(plan, records),
        "handoff_reconciliation": {"handoffs": handoffs, "unresolved_handoff_ids": list(unresolved), "blockers": list(blockers)},
    }


def build_synthesis_bundle(document: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Create a compact, hashed synthesis view from accepted compiler artifacts."""
    source_state = _state(document, "source_state")
    plan = _graph_plan(document["plan"]) if isinstance(document.get("plan"), dict) else None
    raw_sources = _evidence_sources(document, plan)
    if not raw_sources:
        msg = "synthesis requires compiler evidence sources"
        raise ValueError(msg)
    derived: list[dict[str, Any]] = []
    for source in raw_sources:
        _kind, expectation, evidence, _content, normalized = _load_evidence_source(source, require_normalized=True)
        if expectation.source_state != source_state:
            blockers = (
                review_source_state_blockers(plan, expectation, evidence, source_state)
                if plan is not None and isinstance(expectation, ReviewEvidenceExpectation) and isinstance(evidence, ReviewEvidence)
                else ("different source state without a planner-bound reuse transition",)
            )
            if blockers:
                msg = f"synthesis evidence has a different source state: {evidence.evidence_id}: " + "; ".join(blockers)
                raise ValueError(msg)
        if normalized is None:  # Defensive for type narrowing after require_normalized.
            msg = f"synthesis evidence has no normalized record: {evidence.evidence_id}"
            raise ValueError(msg)
        if expectation.source_state != source_state:
            normalized = {**normalized, "reuse": {"original_source_state": list(expectation.source_state), "verified_source_state": list(source_state)}}
        derived.append(normalized)
    records: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    artifact_ids: set[str] = set()
    for raw in derived:
        evidence_id = _required_text(raw, "evidence_id")
        if evidence_id in evidence_ids:
            msg = f"duplicate synthesis evidence ID: {evidence_id}"
            raise ValueError(msg)
        evidence_ids.add(evidence_id)
        _required_text(raw, "artifact_digest")
        artifact_id = _required_text(raw, "artifact_id")
        if artifact_id in artifact_ids:
            msg = f"duplicate synthesis artifact ID: {artifact_id}"
            raise ValueError(msg)
        artifact_ids.add(artifact_id)
        _required_text(raw, "status")
        _text_list(raw, "requirement_ids")
        record = dict(raw)
        record["record_digest"] = digest_bytes(canonical_json(record).encode())
        records.append(record)
    bundle: dict[str, Any] = {"schema_version": 1, "source_state": list(source_state), "records": sorted(records, key=lambda item: item["evidence_id"])}
    if plan is not None:
        bundle["plan_context"] = _synthesis_plan_context(plan, bundle["records"])
    bundle["bundle_digest"] = digest_bytes(canonical_json(bundle).encode())
    return bundle


def _verified_reused_sources(plan: GraphPlan, source_state: tuple[str, str, str], *, check_current_inputs: bool = True) -> tuple[dict[str, str], ...]:
    """Reload immutable reused artifacts and recheck their current instructions."""
    sources: list[dict[str, str]] = []
    snapshots = {item.source_state: item for item in plan.reuse_source_snapshots}
    for transition in plan.audit_reuse_transitions:
        source = {"artifact_path": transition.artifact_path, "metadata_path": transition.metadata_path}
        _kind, expectation, evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence):
            msg = "audit reuse source must contain review evidence"
            raise TypeError(msg)
        if evidence.evidence_id != transition.evidence_id or evidence.raw_result_digest != transition.artifact_digest:
            msg = "audit reuse source differs from its bound evidence identity"
            raise ValueError(msg)
        blockers = list(review_source_state_blockers(plan, expectation, evidence, source_state))
        blockers.extend(
            "invalidated metadata dependency: " + canonical_json(blocker)
            for blocker in intervening_metadata_blockers(record or {}, transition.metadata_transitions)
        )
        if blockers:
            msg = f"audit reuse failed verification: {transition.evidence_id}: " + "; ".join(blockers)
            raise ValueError(msg)
        if not check_current_inputs:
            # Mutation planning loads historical evidence before checking the new capture.
            sources.append(source)
            continue
        inputs = expectation.audit_input_identity
        if inputs is None:  # Narrowed by the reuse gate.
            msg = "audit reuse lacks compiler-bound inputs"
            raise ValueError(msg)
        if source_state not in snapshots:
            msg = "audit reuse lacks a source snapshot for current source_state"
            raise ValueError(msg)
        explicit = tuple(path for decision in plan.routing_decisions if decision.evidence_id == evidence.evidence_id for path in decision.instruction_paths)
        paths = _applicable_instruction_paths(Path(snapshots[source_state].repository_root), inputs.owned_paths, explicit)
        if tuple((path, _file_identity_digest(path)) for path in paths) != transition.instruction_digests:
            msg = "audit reuse instructions changed; recapture and replan"
            raise ValueError(msg)
        if _file_identity_digest(evidence.skill_path) != evidence.skill_digest or any(
            _file_identity_digest(path) != digest for path, digest in evidence.reference_digests
        ):
            msg = "audit reuse skill or references changed; recapture and replan"
            raise ValueError(msg)
        sources.append(source)
    return tuple(sources)


def _evidence_sources(document: dict[str, Any], plan: GraphPlan | None, *, check_current_inputs: bool = True) -> tuple[dict[str, Any], ...]:
    sources = _records(document, "sources")
    if plan is None:
        return sources
    supplied = {(str(Path(_required_text(item, "artifact_path")).resolve()), str(Path(_required_text(item, "metadata_path")).resolve())) for item in sources}
    return (
        *sources,
        *(
            item
            for item in _verified_reused_sources(plan, _state(document, "source_state"), check_current_inputs=check_current_inputs)
            if (item["artifact_path"], item["metadata_path"]) not in supplied
        ),
    )


def build_routing_projection_document(
    document: dict[str, Any], *, catalog_path: Path = DEFAULT_ROUTING_CATALOG, skill_roots: tuple[Path, ...] = (DEFAULT_SKILL_ROOT,)
) -> dict[str, Any]:
    """Load and project the complete consulted routing catalog."""
    catalog = load_routing_catalog(catalog_path, skill_roots=skill_roots)
    return build_routing_projection(
        catalog, consulted_routers=_text_list(document, "consulted_routers", required=True), captured_paths=_text_list(document, "captured_paths")
    )


def _required_schema_shape(node: dict[str, Any]) -> object:
    """Return a compact recursive description of every schema-required field."""
    shape: object
    if isinstance(node.get("oneOf"), list):
        shape = {"oneOf": [_required_schema_shape(branch) for branch in node["oneOf"] if isinstance(branch, dict)]}
    elif isinstance(node.get("enum"), list):
        shape = " | ".join(str(value) for value in node["enum"])
    elif "const" in node:
        shape = node["const"]
    elif node.get("type") == "object":
        properties = node.get("properties", {})
        required = node.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            shape = "object"
        else:
            shape = {name: _required_schema_shape(properties[name]) for name in required if name in properties}
    elif node.get("type") == "array":
        items = node.get("items")
        shape = [_required_schema_shape(items)] if isinstance(items, dict) else []
    elif isinstance(node.get("type"), list):
        shape = " | ".join(str(value) for value in node["type"])
    else:
        shape = str(node.get("type") or "value")
    return shape


def _schema_reference(path: Path) -> dict[str, object]:
    raw = _read_json_object(path)
    required = raw.get("required")
    if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
        msg = f"payload schema has no canonical required field list: {path}"
        raise ValueError(msg)
    schema_id = _required_text(raw, "$id")
    match = _SCHEMA_ID_VERSION_RE.search(schema_id)
    if match is None:
        msg = f"payload schema $id has no canonical version suffix: {schema_id}"
        raise ValueError(msg)
    if path.name != match.group(0):
        msg = f"payload schema filename does not match its canonical $id: {path.name} != {match.group(0)}"
        raise ValueError(msg)
    reference: dict[str, object] = {
        "digest": _file_identity_digest(str(path)),
        "id": schema_id,
        "path": str(path),
        "required_fields": required,
        "required_shape": _required_schema_shape(raw),
        "version": int(match.group("version")),
    }
    if path == _REVIEW_PAYLOAD_SCHEMA:
        reference["optional_shapes"] = {"coverage_units": _required_schema_shape(raw["properties"]["coverage_units"])}
    return reference


def _applicable_instruction_paths(repository_root: Path, owned_paths: tuple[str, ...], declared: tuple[str, ...]) -> tuple[str, ...]:
    owned_paths = _normalized_repository_paths(owned_paths, label="instruction discovery owned_paths")
    candidates = {Path(path).resolve() for path in declared}
    root_instruction = repository_root / "AGENTS.md"
    if root_instruction.is_file():
        candidates.add(root_instruction.resolve())
    for raw_path in owned_paths:
        relative = Path(raw_path)
        parent = relative if (repository_root / relative).is_dir() else relative.parent
        while parent != Path():
            instruction = repository_root / parent / "AGENTS.md"
            if instruction.is_file():
                candidates.add(instruction.resolve())
            if parent == parent.parent:
                break
            parent = parent.parent
    return tuple(sorted(str(path) for path in candidates))


def _materialized_command_policy(plan: GraphPlan, node: WorkerNode, authorized_duplicates: tuple[str, ...]) -> dict[str, object]:
    validator_commands = tuple(sorted({command for unit in plan.coalesced_validation_units for command in unit.commands}))
    if node.mode == "validation":
        unit = next((unit for unit in plan.coalesced_validation_units if unit.node_id == node.node_id), None)
        if unit is None:
            msg = f"validation node has no coalesced unit: {node.node_id}"
            raise ValueError(msg)
        return {
            "allowed_commands": list(unit.commands),
            "authorized_duplicate_commands": [],
            "attestation_required": True,
            "policy": "execute exactly the coalesced validation unit; do not add review commands",
            "prohibited_commands": [],
            "validator_owned_commands": list(unit.commands),
        }
    prohibited = tuple(command for command in validator_commands if command not in authorized_duplicates)
    return {
        "allowed_commands": ["read-only inspection commands that do not execute a planned validator recipe"],
        "authorized_duplicate_commands": list(authorized_duplicates),
        "attestation_required": True,
        "planned_validation_units": _planned_validation_units(plan),
        "policy": (
            "planned validators own execution; for a covered need, return the planned-reference validation requirement variant with the exact "
            "requirement_id and planned_validation_digest while keeping owner, reason, and expected_evidence audit-specific; use the full execution "
            "variant only for a genuinely new validation identity; do not rerun validator commands"
        ),
        "prohibited_commands": list(prohibited),
        "validator_owned_commands": list(validator_commands),
    }


def _independent_adversarial_checks(paths: tuple[str, ...]) -> tuple[str, ...]:
    code_suffixes = {".c", ".cc", ".cpp", ".h", ".hpp", ".py", ".rs"}
    checks: list[str] = []
    if any(Path(path).suffix in code_suffixes for path in paths):
        checks.extend(("fallback absence and failure", "platform seams", "parser suffixes and error branches", "unexpected exception types"))
    if any("test" in Path(path).name.lower() or "tests" in Path(path).parts for path in paths):
        checks.append("changed tests and boundary cases")
    return tuple(checks)


def _inspection_groups(plan: GraphPlan, source_state: tuple[str, str, str], artifact_store: Path, repository_root: Path) -> dict[str, dict[str, object]]:  # noqa: C901
    audit_nodes = [node for node in plan.actual_worker_nodes if node.mode == "audit" and node.coverage]
    remaining = {node.node_id: node for node in audit_nodes}
    groups: list[tuple[tuple[str, ...], list[str]]] = []
    while remaining:
        _seed_id, seed = remaining.popitem()
        members = [seed]
        paths = set(seed.coverage)
        changed = True
        while changed:
            changed = False
            for node_id, node in tuple(remaining.items()):
                if paths.intersection(node.coverage):
                    members.append(remaining.pop(node_id))
                    paths.update(node.coverage)
                    changed = True
        groups.append((tuple(sorted(paths)), [node.node_id for node in members]))
    output: dict[str, dict[str, object]] = {}
    for paths, node_ids in groups:
        if len(node_ids) < 2:
            continue
        observations: list[dict[str, object]] = []
        excerpts: list[dict[str, object]] = []
        remaining_bytes = 65536
        for path in paths:
            candidate = (repository_root / path).resolve()
            if not candidate.is_relative_to(repository_root) or not candidate.is_file():
                observations = []
                break
            content = candidate.read_bytes()
            limit = min(16384, remaining_bytes)
            excerpt = content[:limit].decode("utf-8", errors="ignore")
            remaining_bytes -= len(content[:limit])
            excerpts.append({"path": path, "content_digest": digest_bytes(content), "text": excerpt, "complete": excerpt.encode() == content})
            observations.append(
                {
                    "byte_count": len(content),
                    "content_digest": digest_bytes(content),
                    "line_count": content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0),
                    "path": path,
                }
            )
        if not observations:
            continue
        observation_digest = digest_bytes(canonical_json(observations).encode())
        identity = digest_bytes(canonical_json({"observation_digest": observation_digest, "source_state": source_state}).encode())
        record: dict[str, object] = {
            "artifact_path": str(artifact_store / f"inspection.{identity.removeprefix('sha256:')[:16]}.json"),
            "group_id": f"inspection:{identity.removeprefix('sha256:')[:16]}",
            "member_node_ids": sorted(node_ids),
            "observation_digest": observation_digest,
            "observations": observations,
            "paths": list(paths),
            "producer_node_id": min(node_ids),
            "reuse_policy": "trusted read-only observations may be reused; semantic findings and payloads remain node-specific",
            "source_state": list(source_state),
            "source_packet": {"source_state": list(source_state), "scope": "structural source only; no reviewer conclusions", "excerpts": excerpts},
        }
        for node_id in node_ids:
            output[node_id] = record
    return output


def _worker_provenance_examples(dispatch: dict[str, Any], captured_paths: Iterable[str]) -> dict[str, Any]:
    """Supply illustrative fragments, never prefilled claims of performed work."""
    owned = dispatch["owned_paths"][0]
    context = next((path for path in captured_paths if path not in dispatch["owned_paths"]), dispatch["skill_path"])
    local_diff = shlex.join(["git", "diff", "HEAD", "--", owned])
    branch_diff = shlex.join(["git", "diff", "origin/main", "--", owned])
    return {
        "owned_read": {"files_inspected": [owned], "commands_executed": [shlex.join(["cat", "--", owned])]},
        "context_read": {"nearby_contract_owners": [context], "commands_executed": [shlex.join(["cat", "--", context])]},
        "local_diff": {
            "commands_executed": [local_diff],
            "git_dependencies": [{"kind": "source-discovery", "command": local_diff, "reason": "Located reads; judgments use captured source, not staging."}],
        },
        "branch_diff": {
            "commands_executed": [branch_diff],
            "git_dependencies": [{"kind": "head", "command": branch_diff, "reason": "Comparison depends on the base revision."}],
        },
    }


def _synthesis_examples(dispatch: dict[str, Any]) -> dict[str, Any]:
    """Show reference placement without asserting execution or runtime reuse."""
    examples = {
        "fresh_coverage": {"evidence_id": "validation:local", "requirement_ids": ["repository-gate"], "disposition": "accepted"},
        "proved_reuse_coverage": {"evidence_id": "review:prior-audit", "requirement_ids": ["python.parse"], "disposition": "reused"},
        "shared_validator": {
            "evidence_id": "validation:local",
            "requirement_ids": ["repository-gate"],
            "result": "passed",
            "platform": "copy bound validator platform",
            "execution_mode": "native",
        },
        "unexecuted_platform": {"limitations": ["Hosted Linux/macOS matrix has no separate accepted evidence."], "cross_surface_risks": []},
    }
    planned = dispatch["command_policy"].get("planned_validation_units", [])
    if planned:
        examples["merged_need"] = {
            "requirement_id": planned[0]["requirement_ids"][0],
            "planned_validation_digest": planned[0]["planned_validation_digest"],
            "owner": "reviewer-a; reviewer-b",
            "reason": "review:a needs boundary checks; review:b needs regression checks",
            "expected_evidence": "Retain both source requests and consume the shared validator's actual results.",
        }
    return examples


def _worker_prompt(contract: str, dispatch: dict[str, Any]) -> str:
    schema = dispatch.get("payload_schema")
    schema_text = (
        "dispatch.payload_schema (open its path only when more schema detail is needed)"
        if isinstance(schema, dict)
        else "native independent-review Markdown contract"
    )
    command_policy = "obey dispatch.command_policy"
    shared = dispatch.get("shared_inspection_evidence")
    shared_text = (
        " Treat shared_inspection_evidence as trusted read-only structural observation only; derive semantic conclusions independently."
        if isinstance(shared, dict)
        else ""
    )
    worker_payload_path = _required_text(dispatch, "worker_payload_path")
    persistence = dispatch.get("worker_payload_persistence")
    if not isinstance(persistence, dict) or persistence.get("operation") != "persist-worker-payload":
        msg = "worker dispatch lacks its runtime-owned payload persistence contract"
        raise ValueError(msg)
    persistence_input = _required_text(persistence, "input_path")
    persistence_command = _text_list(persistence, "command", required=True)
    review_command = _text_list(persistence, "review_command")
    if persistence.get("publish_command"):
        persistence_text = (
            " Serialize result bytes once. Stream them to dispatch.worker_payload_persistence.publish_command; "
            "it validates, reviews, and atomically publishes the identical bytes. "
            "Return only its receipt, not a second copy of the payload. Keep the bytes for any approved retry with --approval-identity; "
            "do not rewrite evidence to obtain approval. "
            "For payload publication, only the bound worker_payload_path is a write target; paths within evidence are read provenance."
        )
    elif persistence.get("input_mode") == "stdin" and review_command:
        persistence_text = (
            " Before returning, hold the exact result bytes in memory. Stream them on standard input to the runtime-owned "
            f"safety-review command unchanged: {shlex.join(review_command)}. It validates the bound contract at {persistence_input} before any artifact write "
            "and returns an approval_identity. Then stream the identical bytes to the persistence command "
            f"{shlex.join(persistence_command)} with --approval-identity <reviewed identity>. "
            f"For payload publication, only {worker_payload_path} is an artifact write target; path strings "
            "inside the payload are evidence. If publication is blocked and the user approves that identity, retry identical bytes and the same command; never "
            f"rewrite evidence to obtain approval. Only after the runtime atomically publishes {worker_payload_path} may you return those same bytes. "
            "Serialize payload_bytes once and retain them for both calls and any retry. Python example (dispatch is the supplied dispatch object):\n"
            "```python\n"
            "import json\n"
            "import subprocess\n"
            "p = dispatch['worker_payload_persistence']\n"
            "review = subprocess.run(p['review_command'], input=payload_bytes, capture_output=True, check=True)\n"
            "identity = json.loads(review.stdout)['approval_identity']\n"
            "subprocess.run([*p['command'], '--approval-identity', identity], input=payload_bytes, capture_output=True, check=True)\n"
            "```\n"
        )
    else:
        persistence_candidate = _required_text(persistence, "candidate_path")
        persistence_text = (
            f" Before returning, write the exact result bytes to temporary sibling {persistence_candidate}, then invoke the runtime-owned "
            f"persistence command unchanged: {shlex.join(persistence_command)}. "
            f"Its bound input is {persistence_input} and candidate is {persistence_candidate}. "
            f"For payload publication, only {persistence_candidate} and {worker_payload_path} are write targets; path strings inside the payload are evidence. "
            "The persistence receipt or a publication-block diagnostic supplies an approval_identity bound to the exact bytes and both paths. "
            "If publication is blocked and the user approves that identity, preserve the candidate bytes and retry the same command with "
            "--approval-identity <approved identity>; "
            "never rewrite evidence to obtain approval. "
            f"Only after it atomically publishes {worker_payload_path} may you return those same bytes."
        )
    persistence_text += (
        " Source captures and other graph proof artifacts still belong under the workflow's authorized external temporary store; "
        "this payload restriction does not prohibit those writes."
    )
    provenance_text = (
        " dispatch.provenance_examples contains illustrative fragments, not performed work: merge only actual reads/commands, "
        "account for owned scope under the dispatch contract, and replace origin/main with the captured base when applicable. "
        "files_inspected is owned-only; nearby_contract_owners records inspected dependency/context paths. "
        "Record each Git invocation separately and bind git_dependencies.command to its exact commands_executed entry. "
        "source-discovery supports plain git diff with optional HEAD, --cached/--staged, and -- relative/path; "
        "other revisions use conservative head (or index/history for those judgments). Never classify a compound command as source-discovery."
        if dispatch.get("mode") in {"audit", "independent-review"}
        else ""
    )
    if contract == "compact-independent-review":
        return (
            "Perform only the dispatched repository-independent-review in fresh context. Publish the structured JSON payload from "
            "dispatch.payload_schema and its template. Supply substantive evidence and inspected_paths for each dispatched stable check_id. "
            "Use dispatch.payload_schema.completed_example for field placement, replacing its illustrative observations with actual evidence. "
            "Put test inspection, delegated/unexecuted validator commands, and pending hosted/platform checks in tests; put inspected source branches "
            "and source-level platform observations in branches (or the platform adversarial check). Do not describe pending or delegated checks as passed. "
            "commands_executed lists only commands actually run. limitations contains incomplete owned inspection, unresolved semantic uncertainty, "
            "or unclassified caveats; any such limitation requires status=blocked. Completed inspection uses limitations=[] and status=completed "
            "with findings, or status=no-findings without findings, even when validator-owned execution remains pending. Never hide an inspection gap "
            "or semantic uncertainty in tests/branches to obtain acceptance. "
            "Record observed before_state/after_state and truthful mutation and command attestations. The compiler renders native headings, "
            "labels and graph identities; never supply an unperformed check or borrow other reviewers' conclusions. "
            f"Command policy: {command_policy}{provenance_text}{persistence_text}"
        )
    validation_text = (
        " Apply dispatch.executor_requirements.sandbox_permissions to the execution tool; it is a requirement, not an approval grant. "
        "If unavailable or denied, report blocked without silently using a different permission mode. "
        " Omit artifacts: the runtime captures workspace status and artifact digests before and after execution. "
        "executions[].artifact_paths names only exact validation_unit.allowed_artifacts[].path roots, never generated child files. "
        "Use [] for no output or absent outputs. Child file paths may appear in evidence text; publication checks references before writing."
        if contract == "compact-validation"
        else ""
    )
    audit_scope_text = (
        " For audits, scope_limitations is reserved exclusively for omitted dispatch-owned paths and must equal owned_paths minus "
        "files_inspected and runtime-proved reused paths. When coverage_reuse is present, inspect only recheck units, preserve their prior findings and "
        "reconcile original validation needs/handoffs; do not claim fresh reads of reused paths. Its verified execution view contains unit dependencies "
        "and original finding IDs attributed to evidence_id; proof_reference provides lazy access to the full proof when needed. "
        "For broad fresh audits, use optional coverage_units when "
        "you can partition contracts with explicit dependencies and uncertainty: partition every owned path and every finding exactly once "
        "using one-based finding_indices, give each unit a unique unit_id, and account for every nearby_contract_owners path in dependency_paths. "
        'See payload_schema.optional_shapes.coverage_units; dependency_uncertainty="" means no uncertainty, and [] means no findings/dependencies. '
        "Source-discovery judgments must come from the captured "
        "files_inspected/nearby_contract_owners reads, independent of the staging split; undeclared commands remain conservative. "
        "Legacy git_sensitive=true always requires rechecking. "
        'Put validator-owned nonexecution in execution_facts=["validators-not-executed"]; use source-captures-match and git-not-mutated only when true. '
        "Put platform/evidence caveats in validation_limits bound to an explicit validation_requirements entry: delegated means the validator still owes "
        "that evidence, unavailable/failed block reuse. Put unresolved semantic/dependency questions in unresolved_uncertainties (kind, reason), "
        "or a single unit's dependency_uncertainty. Keep unknown caveats in limitations; these conservatively block reuse. Never omit truthful context."
        if dispatch.get("mode") == "audit"
        else ""
    )
    synthesis_text = (
        " Use dispatch.synthesis_examples for field placement, replacing illustrative IDs/claims with accepted bundle evidence. "
        "synthesis_plan_reference/synthesis_sources are runtime-only preflight inputs. predecessor_coverage has one row per dispatched evidence ID; "
        "validation_reconciliation has one row per accepted validator ID, even when several reviewers share it. Fresh evidence is accepted; "
        "reused requires runtime proof across source states. Merge inherited validation needs by unique requirement_id, retaining each source "
        "evidence ID, owner and reason in reason/expected_evidence. Different IDs remain separate. A platform without its own accepted evidence "
        "belongs in limitations/cross_surface_risks; genuine required unexecuted validators remain blockers. Publication verifies predecessor "
        "artifacts and reports binding errors together. Keep every failed diagnostic; repair metadata without rerunning validators. "
        "Schema mismatches permit one diagnostic-guided retry. Semantic binding errors separately permit one consolidated correction; "
        "a second failure of either kind blocks the node. Neither counter resets the other."
        if dispatch.get("mode") == "synthesis"
        else ""
    )
    return (
        "Read dispatch.skill_path and the dispatched instruction/reference files before performing this node; "
        "follow the skill's conditional reference requirements. For review nodes, record actual skill/reference reads in nearby_contract_owners. "
        "Routing selection and captured skill digests do not attest that instructions were read. "
        f"Publish the canonical {contract} payload using field names from {schema_text}. "
        "Every field shown in payload_schema.required_shape is required whenever its parent object is present. "
        "Do not author fingerprints, evidence IDs, artifact IDs, or digests. Copy supplied evidence/finding IDs only into schema-defined reference fields. "
        f"Command policy: {command_policy}{validation_text}{provenance_text}{audit_scope_text}{synthesis_text}{persistence_text}{shared_text}"
    )


def _review_payload_schema(dispatch: dict[str, Any]) -> Path:
    return _SYNTHESIS_PAYLOAD_SCHEMA if dispatch.get("mode") == "synthesis" else _REVIEW_PAYLOAD_SCHEMA


def _publication_dispatch(contract: dict[str, Any]) -> dict[str, Any] | None:
    """Reload the immutable dispatch bound to publication, never worker-authored context."""
    reference = contract.get("compiler_preflight")
    if reference is None:
        if "proof_reference" in contract.get("coverage_reuse", {}):
            msg = "external coverage proof requires its bound compiler preflight before publication"
            raise ValueError(msg)
        # Saved contracts remain usable; compile-node applies the current verifier.
        return None
    content = Path(reference["worker_input_path"]).read_bytes()
    if digest_bytes(content) != reference["digest"]:
        msg = "compiler preflight worker input digest differs from its publication contract"
        raise ValueError(msg)
    entry = json.loads(content)
    dispatch = entry["dispatch"]
    if any(dispatch.get(key) != contract.get(key) for key in ("mode", "node_id", "owned_paths", "worker_payload_path", "coverage_reuse")):
        msg = "compiler preflight dispatch differs from its publication contract"
        raise ValueError(msg)
    return dispatch


def _synthesis_publication_plan(dispatch: dict[str, Any]) -> dict[str, Any]:
    """Reload the immutable plan and coordinator-bound reuse source references."""
    reference = dispatch["synthesis_plan_reference"]
    content = _read_regular_file_no_follow(Path(reference["path"]))
    if digest_bytes(content) != reference["digest"]:
        msg = "synthesis publication plan digest differs from its bound dispatch"
        raise ValueError(msg)
    return json.loads(content)


def _synthesis_publication_bundle(dispatch: dict[str, Any]) -> dict[str, Any]:
    """Verify compiled predecessor artifacts with the immutable materialized plan."""
    plan = _synthesis_publication_plan(dispatch)
    return build_synthesis_bundle({**plan, "sources": [*_records(plan, "sources"), *dispatch["synthesis_sources"]]})


def _continuation_synthesis_sources(entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain explicit reuse bindings when a continuation rematerializes synthesis."""
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries.values():
        if "synthesis_plan_reference" in entry["dispatch"]:
            for source in _records(_synthesis_publication_plan(entry["dispatch"]), "sources"):
                sources[(_required_text(source, "artifact_path"), _required_text(source, "metadata_path"))] = source
    return list(sources.values())


def _preflight_audit_payload(contract: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Preflight references or dry-compile before authorizing payload publication."""
    dispatch = _publication_dispatch(contract)
    if dispatch is None:
        if contract.get("mode") == "synthesis":
            validate_synthesis(payload, tuple(item["evidence_id"] for item in payload["predecessor_coverage"]))
        return None
    if contract.get("mode") == "validation":
        unit = _validation_unit(dispatch["validation_unit"])
        paths = tuple(artifact.path for artifact in unit.allowed_artifacts)
        root = Path(dispatch["repository_root"])
        absent = tuple(path for path in paths if not _workspace_path(path, root).exists(follow_symlinks=False))
        blockers = _validation_artifact_reference_blockers(payload, paths, absent)
        if blockers:
            raise ValueError("worker payload failed execution-artifact validation before publication: " + "; ".join(blockers))
        return None
    if contract.get("mode") == "synthesis":
        bundle = _synthesis_publication_bundle(dispatch)
        validate_synthesis(payload, _text_list(dispatch, "predecessor_evidence_ids"), bundle)
        dispatch = {**dispatch, "synthesis_bundle": bundle}
    # These are hypothetical equal captures, never published as evidence. The
    # actual compile still requires independently supplied before/after captures.
    try:
        compiler = compile_independent_payload if contract.get("mode") == "independent-review" else compile_review
        current_state = list(_current_metadata_state(dispatch))
        native, metadata = compiler({"dispatch": {**dispatch, "before_state": current_state, "after_state": current_state}, "payload": payload})
    except (ValueError, TypeError) as error:
        msg = f"{contract.get('mode')} compiler preflight failed before publication: {error}"
        raise ValueError(msg) from error
    headings = tuple(line for line in native.decode().splitlines() if line.startswith("## "))
    sections, _blockers = _native_section_bodies(native.decode(), headings)
    return {
        "result_byte_count": len(native),
        "result_limit": MAX_NATIVE_RESULT_BYTES,
        "section_byte_counts": {heading.removeprefix("## "): len(body.encode()) for heading, body in (sections or {}).items()},
        "section_limit": MAX_NATIVE_SECTION_BYTES,
        "scope_rendering": "reference" if metadata["expectation"].get("canonical_worker_payload") is not None else "inline",
    }


def _validate_worker_payload_bytes(contract_document: dict[str, Any], payload_bytes: bytes) -> dict[str, Any] | None:
    """Reject incomplete worker output before it can replace a persisted payload."""
    contract = _required_text(contract_document, "result_contract")
    if contract in {"compact-review", "compact-validation", "compact-independent-review"}:
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            msg = "compact worker payload root must be an object"
            raise TypeError(msg)
        schema = (
            _INDEPENDENT_PAYLOAD_SCHEMA
            if contract == "compact-independent-review"
            else (_review_payload_schema(contract_document) if contract == "compact-review" else _VALIDATION_PAYLOAD_SCHEMA)
        )
        require_schema(payload, schema)
        if contract == "compact-independent-review":
            if "compiler_preflight" not in contract_document:
                msg = "structured independent publication requires its bound compiler preflight"
                raise ValueError(msg)
        elif contract == "compact-review":
            _validate_review_coverage_partitions(contract_document, payload)
            _validate_audit_caveats(contract_document, payload)
            blockers = _review_scope_coverage_blockers(contract_document, payload, status=_required_text(payload, "status"))
            if blockers:
                msg = "worker payload failed owned-scope validation: " + "; ".join(blockers)
                raise ValueError(msg)
        else:
            blockers = tuple(
                blocker
                for index, execution in enumerate(payload["executions"])
                for blocker in validation_execution_result_blockers(
                    result=execution["result"], exit_code=execution["exit_code"], elapsed=execution["elapsed"], label=f"$.executions[{index}]"
                )
            )
            if blockers:
                msg = "worker payload failed execution-result validation: " + "; ".join(blockers)
                raise ValueError(msg)
        return payload
    msg = f"unsupported worker payload result contract: {contract}"
    raise ValueError(msg)


def review_worker_payload_write(contract_document: dict[str, Any], payload_bytes: bytes, *, candidate_is_write_target: bool = False) -> dict[str, Any]:
    """Validate bytes and bind their publication to the complete persistence contract."""
    definition = "legacyWorkerPayloadContract" if candidate_is_write_target else "stdinWorkerPayloadContract"
    require_schema_definition(contract_document, _RUNTIME_OPERATION_INPUT_SCHEMA, definition)
    node_id = _required_text(contract_document, "node_id")
    result_contract = _required_text(contract_document, "result_contract")
    target = Path(_required_text(contract_document, "worker_payload_path")).resolve()
    target_path = str(target)
    payload = _validate_worker_payload_bytes(contract_document, payload_bytes)
    preflight = _preflight_audit_payload(contract_document, payload) if payload is not None else None
    payload_digest = digest_bytes(payload_bytes)
    identity_record: dict[str, object] = {
        "contract_digest": digest_bytes(canonical_json(contract_document).encode()),
        "node_id": node_id,
        "payload_byte_count": len(payload_bytes),
        "payload_digest": payload_digest,
        "payload_input": "candidate-path" if candidate_is_write_target else "stdin",
        "result_contract": result_contract,
        "worker_payload_path": target_path,
    }
    write_targets = [target_path]
    if candidate_is_write_target:
        candidate = Path(_required_text(contract_document, "candidate_path")).resolve()
        if candidate == target or candidate.parent != target.parent:
            msg = "worker payload candidate binding must be a distinct sibling of the materialized target"
            raise ValueError(msg)
        candidate_path = str(candidate)
        identity_record["candidate_path"] = candidate_path
        write_targets.insert(0, candidate_path)
    review: dict[str, Any] = {
        "approval_identity": digest_bytes(canonical_json(identity_record).encode()),
        "artifact_write_targets": write_targets,
        "decision": "valid-bound-artifact-write",
        **identity_record,
        **({"native_size_preflight": preflight} if preflight is not None else {}),
    }
    if result_contract == "compact-review" and contract_document.get("mode") == "audit" and payload is not None:
        owned_paths = _text_list(contract_document, "owned_paths", required=True)
        inspected_paths = _text_list(payload, "files_inspected")
        inspected = set(inspected_paths)
        inherited = reused_paths(contract_document.get("coverage_reuse"))
        review["audit_path_roles"] = {
            "dispatch_owned_paths": list(owned_paths),
            "inspected_dispatch_owned_paths": list(inspected_paths),
            "nearby_context_paths": list(_text_list(payload, "nearby_contract_owners")),
            "omitted_dispatch_owned_paths": [path for path in owned_paths if path not in inspected and path not in inherited],
            **({"runtime_reused_paths": list(inherited)} if inherited else {}),
            "scope_limitation_paths": [path for path, _reason in _scope_limitation_records(payload)],
        }
        review["payload_field_semantics"] = {
            "limitations": "unclassified-reuse-blocker",
            "execution_facts": "typed-execution-attestations",
            "validation_limits": "requirement-bound-environmental-evidence",
            "unresolved_uncertainties": "semantic-or-dependency-reuse-blocker",
            "nearby_contract_owners": "inspected-context-only",
            "scope_limitations": "omitted-dispatch-owned-only",
        }
    return review


def _approved_worker_payload_write(
    contract_document: dict[str, Any], payload_bytes: bytes, approval_identity: str | None, *, candidate_is_write_target: bool = True
) -> dict[str, Any]:
    artifact_write_review = review_worker_payload_write(contract_document, payload_bytes, candidate_is_write_target=candidate_is_write_target)
    if approval_identity is not None:
        _sha256_digest(approval_identity, "worker payload approval identity")
        if approval_identity != artifact_write_review["approval_identity"]:
            msg = "worker payload differs from the explicitly approved artifact write"
            raise ValueError(msg)
    return artifact_write_review


def _persist_worker_write_review(artifact_write_review: dict[str, Any]) -> dict[str, Any]:
    """Keep complete write evidence in an immutable, digest-addressed sibling."""
    content = (canonical_json(artifact_write_review) + "\n").encode()
    digest = digest_bytes(content)
    target = Path(artifact_write_review["worker_payload_path"])
    path = target.with_name(f"write-review.{digest.removeprefix('sha256:')}.json")
    _write_bytes_atomically_once(path, content, mode=0o400)
    return {"path": str(path), "digest": digest, "byte_count": len(content)}


def _worker_payload_receipt(
    contract_document: dict[str, Any], payload_bytes: bytes, artifact_write_review: dict[str, Any], review_reference: dict[str, Any]
) -> dict[str, Any]:
    return {
        "node_id": _required_text(contract_document, "node_id"),
        "result_contract": _required_text(contract_document, "result_contract"),
        "schema_version": 1,
        "status": "published",
        "approval_identity": artifact_write_review["approval_identity"],
        "worker_payload_byte_count": len(payload_bytes),
        "worker_payload_digest": digest_bytes(payload_bytes),
        "worker_payload_path": str(Path(_required_text(contract_document, "worker_payload_path")).resolve()),
        "artifact_write_review": artifact_write_review,
        "artifact_write_review_reference": review_reference,
    }


def persist_worker_payload_bytes(contract_document: dict[str, Any], payload_bytes: bytes, *, approval_identity: str) -> dict[str, Any]:
    """Validate and atomically publish payload bytes received without a staging write."""
    _sha256_digest(approval_identity, "worker payload approval identity")
    target_path = Path(_required_text(contract_document, "worker_payload_path")).resolve()
    if not target_path.parent.is_dir():
        msg = f"worker payload target directory does not exist: {target_path.parent}"
        raise ValueError(msg)
    artifact_write_review = _approved_worker_payload_write(contract_document, payload_bytes, approval_identity, candidate_is_write_target=False)
    try:
        review_reference = _persist_worker_write_review(artifact_write_review)
    except OSError as error:
        msg = f"worker payload write-review persistence failed: {error}"
        raise WorkerPayloadWriteError(msg, artifact_write_review) from error
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target_path.name}.", suffix=".tmp", dir=target_path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(target_path)
            _fsync_directory(target_path.parent)
            if target_path.read_bytes() != payload_bytes:
                msg = f"atomically published worker payload bytes differ from the validated input: {target_path}"
                raise ValueError(msg)
        finally:
            temporary_path.unlink(missing_ok=True)
    except OSError as error:
        msg = f"worker payload artifact publication failed: {error}"
        raise WorkerPayloadWriteError(msg, artifact_write_review, review_reference) from error
    return _worker_payload_receipt(contract_document, payload_bytes, artifact_write_review, review_reference)


def persist_worker_payload(contract_document: dict[str, Any], candidate_path: Path, *, approval_identity: str | None = None) -> dict[str, Any]:
    """Validate and atomically publish one dispatch-bound worker payload."""
    target_path = Path(_required_text(contract_document, "worker_payload_path")).resolve()
    expected_candidate = Path(_required_text(contract_document, "candidate_path")).resolve()
    candidate = candidate_path.resolve()
    if candidate != expected_candidate:
        msg = f"worker payload candidate differs from its materialized contract: {candidate}"
        raise ValueError(msg)
    if candidate == target_path or candidate.parent != target_path.parent:
        msg = "worker payload candidate must be a distinct sibling of the materialized target"
        raise ValueError(msg)
    if candidate_path.is_symlink() or not candidate.is_file():
        msg = f"worker payload candidate must be a regular non-symlink file: {candidate}"
        raise ValueError(msg)
    if not target_path.parent.is_dir():
        msg = f"worker payload target directory does not exist: {target_path.parent}"
        raise ValueError(msg)

    with candidate.open("rb+") as stream:
        payload_bytes = stream.read()
        artifact_write_review = _approved_worker_payload_write(contract_document, payload_bytes, approval_identity)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        review_reference = _persist_worker_write_review(artifact_write_review)
    except OSError as error:
        msg = f"worker payload write-review persistence failed: {error}"
        raise WorkerPayloadWriteError(msg, artifact_write_review) from error
    try:
        candidate.replace(target_path)
    except OSError as error:
        msg = f"worker payload artifact publication failed: {error}"
        raise WorkerPayloadWriteError(msg, artifact_write_review, review_reference) from error
    if target_path.read_bytes() != payload_bytes:
        msg = f"atomically published worker payload bytes differ from the validated candidate: {target_path}"
        raise ValueError(msg)
    return _worker_payload_receipt(contract_document, payload_bytes, artifact_write_review, review_reference)


def materialize_dispatches(  # noqa: C901, PLR0912, PLR0915
    document: dict[str, Any], *, preserved_entries: dict[str, dict[str, Any]] | None = None, operation_output_path: Path | None = None
) -> dict[str, Any]:
    """Derive exact per-node dispatch bases from one accepted graph plan."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "materialize-dispatches requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    _verify_validation_recoveries(plan)
    if not plan.dispatch_allowed:
        msg = "cannot materialize dispatches from a blocked graph plan"
        raise ValueError(msg)
    source_state = _state(document, "source_state")
    if source_state == ("scope", "worktree", "repository"):
        planned_states = {unit.source_state for unit in plan.coalesced_validation_units}
        if len(planned_states) > 1:
            msg = "symbolic materialization source_state requires one unambiguous plan-bound fingerprint triple"
            raise ValueError(msg)
        if planned_states:
            source_state = planned_states.pop()
    _current_metadata_state({**document, "source_state": list(source_state)})
    _verified_reused_sources(plan, source_state)
    repository_root_path = Path(_required_text(document, "repository_root"))
    if not repository_root_path.is_absolute() or not repository_root_path.is_dir():
        msg = "repository_root must be an existing absolute directory"
        raise ValueError(msg)
    repository_root = str(repository_root_path.resolve())
    for unit in plan.coalesced_validation_units:
        if unit.requires_isolation:
            _validate_isolated_workspace_paths({"repository_root": repository_root}, unit, ())
    authorization = _required_text(document, "authorization")
    if authorization not in {"review-only", "review-and-fix"}:
        msg = "authorization must be review-only or review-and-fix"
        raise ValueError(msg)
    if authorization != "review-and-fix" and any(node.mode == "fix" for node in plan.actual_worker_nodes):
        msg = "fix nodes require review-and-fix authorization"
        raise ValueError(msg)
    state_command = _required_text(document, "state_verification_command")
    artifact_store = Path(_required_text(document, "artifact_store")).resolve()
    if artifact_store.exists() and not artifact_store.is_dir():
        msg = f"artifact_store is not a directory: {artifact_store}"
        raise ValueError(msg)
    pending_writes: dict[Path, tuple[bytes, int]] = {}
    inspection_profile = document.get("inspection_profile", "shared-read-only")
    if inspection_profile not in {"independent-source", "shared-read-only"}:
        msg = "inspection_profile must be independent-source or shared-read-only"
        raise ValueError(msg)
    review_schema = _schema_reference(_REVIEW_PAYLOAD_SCHEMA)
    synthesis_schema = _schema_reference(_SYNTHESIS_PAYLOAD_SCHEMA)
    validation_schema = _schema_reference(_VALIDATION_PAYLOAD_SCHEMA)
    independent_schema = _schema_reference(_INDEPENDENT_PAYLOAD_SCHEMA)
    template_path = _SCHEMA_ROOT.parent / "independent-payload-template.json"
    independent_schema["template"] = {"path": str(template_path), "digest": _file_identity_digest(str(template_path))}
    example_path = _SCHEMA_ROOT.parent / "independent-payload-completed-example.json"
    independent_schema["completed_example"] = {"path": str(example_path), "digest": _file_identity_digest(str(example_path))}
    catalog_path = Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)).resolve()
    if not catalog_path.is_file():
        msg = f"routing catalog does not exist: {catalog_path}"
        raise ValueError(msg)
    catalog_ids = sorted(entry.catalog_id for entry in load_routing_catalog(catalog_path, skill_roots=(DEFAULT_SKILL_ROOT,)))
    locations = document.get("execution_locations", {})
    if not isinstance(locations, dict) or any(not isinstance(key, str) or value not in {"worker", "coordinator"} for key, value in locations.items()):
        msg = "execution_locations must map node IDs to worker or coordinator"
        raise ValueError(msg)
    node_ids = {node.node_id for node in plan.actual_worker_nodes}
    unknown_locations = tuple(sorted(set(locations) - node_ids))
    if unknown_locations:
        msg = "execution_locations reference unknown nodes: " + ", ".join(unknown_locations)
        raise ValueError(msg)
    if plan.execution_profile in {"isolated", "isolated-only"} and any(location == "coordinator" for location in locations.values()):
        msg = "isolated dispatches require worker execution locations"
        raise ValueError(msg)
    validation_units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
    evidence_ids = {node.node_id: _expected_evidence_id(node, plan) for node in plan.actual_worker_nodes}
    execution_attempts = {
        item["node_id"]: item["attempt_id"].removeprefix("validation-recovery:")
        for item in plan.validation_recoveries
        if item.get("checks_started") and tuple(item["source_state"]) == source_state
    }
    line_bounds = dict(plan.captured_path_line_bounds)
    inspection_groups = (
        _inspection_groups(plan, source_state, artifact_store, repository_root_path.resolve()) if inspection_profile == "shared-read-only" else {}
    )
    for record in {str(record["artifact_path"]): record for record in inspection_groups.values()}.values():
        packet_bytes = (canonical_json(record.pop("source_packet")) + "\n").encode()
        packet_path = Path(cast("str", record["artifact_path"])).with_suffix(".source.json")
        _queue_materialized_write(pending_writes, packet_path, packet_bytes, mode=0o444)
        record["source_packet_path"] = str(packet_path)
        record["source_packet_digest"] = digest_bytes(packet_bytes)
        observation_bytes = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
        _queue_materialized_write(pending_writes, Path(cast("str", record["artifact_path"])), observation_bytes, mode=0o444)
        record["artifact_digest"] = digest_bytes(observation_bytes)
    raw_duplicate_authorizations = document.get("duplicate_command_authorizations", {})
    if not isinstance(raw_duplicate_authorizations, dict) or any(
        not isinstance(node_id, str)
        or not isinstance(commands, list)
        or any(not isinstance(command, str) or not command.strip() or "\n" in command for command in commands)
        for node_id, commands in raw_duplicate_authorizations.items()
    ):
        msg = "duplicate_command_authorizations must map node IDs to command arrays"
        raise ValueError(msg)
    unknown_authorizations = tuple(sorted(set(raw_duplicate_authorizations) - node_ids))
    if unknown_authorizations:
        msg = "duplicate command authorizations reference unknown nodes: " + ", ".join(unknown_authorizations)
        raise ValueError(msg)
    validator_commands = {command for unit in plan.coalesced_validation_units for command in unit.commands}
    validation_references = []
    for record in _planned_validation_units(plan):
        identity = record.pop("execution_identity")
        digest = record["planned_validation_digest"]
        identity_path = artifact_store / f"planned-validation.{digest.removeprefix('sha256:')}.json"
        _queue_materialized_write(pending_writes, identity_path, canonical_json(identity).encode(), mode=0o444)
        validation_references.append(
            {
                **record,
                "execution_identity_reference": {"path": str(identity_path), "digest": digest},
                "execution_summary": _validation_identity_summary(identity),
            }
        )
    synthesis_plan_reference = None
    if plan.synthesis_nodes:
        reused_ids = {evidence_id for _requirement, evidence_id in plan.exact_reused_review_evidence}
        reuse_sources = []
        for source in _records(document, "sources"):
            _kind, _expectation, evidence, _content, _record = _load_evidence_source(source, require_normalized=True)
            if evidence.evidence_id in reused_ids:
                reuse_sources.append(source)
        plan_bytes = canonical_json({"plan": asdict(plan), "source_state": list(source_state), "sources": reuse_sources}).encode()
        plan_path = artifact_store / "synthesis-publication-plan.json"
        _queue_materialized_write(pending_writes, plan_path, plan_bytes, mode=0o444)
        synthesis_plan_reference = {"path": str(plan_path), "digest": digest_bytes(plan_bytes)}
    dispatches: list[dict[str, Any]] = []
    for node in plan.actual_worker_nodes:
        if preserved_entries is not None and node.node_id in preserved_entries:
            dispatches.append(preserved_entries[node.node_id])
            continue
        compiler_operation = _COMPILER_BY_MODE.get(node.mode)
        if compiler_operation is None:
            msg = f"no deterministic compiler is registered for planned node mode {node.mode}: {node.node_id}"
            raise ValueError(msg)
        location = locations.get(node.node_id, "coordinator" if node.mode == "fix" else "worker")
        artifact_suffix = "validation.md" if node.mode == "validation" else "review.md"
        artifact_path = artifact_store / f"{node.node_id}.{artifact_suffix}"
        metadata_path = artifact_store / f"{node.node_id}.evidence.json"
        worker_payload_path = artifact_store / f"{node.node_id}.worker-payload.json"
        worker_payload_contract_path = artifact_store / f"{node.node_id}.worker-payload-contract.json"
        worker_payload_command_prefix = [
            str(Path(sys.executable).absolute()),
            str(Path(__file__).resolve()),
            "persist-worker-payload",
            "--input",
            str(worker_payload_contract_path),
            "--payload-stdin",
        ]
        worker_payload_review_command = [
            str(Path(sys.executable).absolute()),
            str(Path(__file__).resolve()),
            "review-worker-payload-write",
            "--input",
            str(worker_payload_contract_path),
        ]
        instruction_paths = _applicable_instruction_paths(repository_root_path.resolve(), node.coverage, node.instruction_paths)
        authorized_duplicates = tuple(sorted(set(raw_duplicate_authorizations.get(node.node_id, ()))))
        if node.mode == "validation" and authorized_duplicates:
            msg = f"duplicate command authorization applies only to review nodes: {node.node_id}"
            raise ValueError(msg)
        unknown_commands = tuple(command for command in authorized_duplicates if command not in validator_commands)
        if unknown_commands:
            msg = f"duplicate command authorization for {node.node_id} is not validator-owned: " + ", ".join(unknown_commands)
            raise ValueError(msg)
        common = {
            "artifact_id": f"artifact://{node.node_id}" + (f"/{execution_attempts[node.node_id]}" if node.node_id in execution_attempts else ""),
            "authorization": authorization,
            "evidence_id": evidence_ids[node.node_id],
            "execution_location": location,
            "execution_profile": plan.execution_profile,
            "fresh_context": location == "worker",
            "command_policy": _materialized_command_policy(plan, node, authorized_duplicates),
            "handoff_catalog_digest": _file_identity_digest(str(catalog_path)),
            "handoff_catalog_ids": catalog_ids,
            "instruction_digests": [[path, _file_identity_digest(path)] for path in instruction_paths],
            "instruction_paths": list(instruction_paths),
            "mode": node.mode,
            "node_id": node.node_id,
            "owned_paths": list(node.coverage),
            "reference_paths": list(node.static_references),
            "repository_root": repository_root,
            "requirement_ids": list(node.requirement_ids),
            "skill_id": node.skill_id,
            "skill_path": node.skill_path,
            "source_state": list(source_state),
            "state_verification_command": state_command,
            "worker_payload_path": str(worker_payload_path),
            "worker_payload_persistence": {
                "command": worker_payload_command_prefix,
                "input_mode": "stdin",
                "input_path": str(worker_payload_contract_path),
                "operation": "persist-worker-payload",
                "review_command": worker_payload_review_command,
                "publish_command": [
                    str(Path(sys.executable).absolute()),
                    str(Path(__file__).resolve()),
                    "publish-worker-payload",
                    "--input",
                    str(worker_payload_contract_path),
                ],
            },
            "worker_created": location == "worker",
        }
        if document.get("external_metadata_transitions"):
            common["external_metadata_transitions"] = document["external_metadata_transitions"]
        if node.mode != "validation":
            common["command_policy"]["planned_validation_units"] = validation_references
        deltas = [item for item in plan.audit_delta_reviews if item["node_id"] == node.node_id]
        if deltas:
            if len(deltas) != 1:
                msg = "delta audit requires exactly one bound coverage context"
                raise ValueError(msg)
            _verify_delta_context(deltas[0], common)
            proof_bytes = canonical_json(deltas[0]).encode()
            proof_path = artifact_store / f"{node.node_id}.coverage-proof.json"
            _queue_materialized_write(pending_writes, proof_path, proof_bytes, mode=0o444)
            common["coverage_reuse"] = coverage_execution_view(deltas[0], {"path": str(proof_path), "digest": digest_bytes(proof_bytes)})
        if node.node_id in inspection_groups:
            # Keep shared observations in one immutable artifact, not every wrapper.
            common["shared_inspection_evidence"] = {
                key: value
                for key, value in inspection_groups[node.node_id].items()
                if key not in {"observations", "member_node_ids", "paths", "producer_node_id"}
            }
        if node.mode == "validation":
            unit = validation_units.get(node.node_id)
            if unit is None:
                msg = f"validation node has no coalesced unit: {node.node_id}"
                raise ValueError(msg)
            if unit.source_state != source_state:
                msg = f"validation unit source state differs from dispatch state: {node.node_id}"
                raise ValueError(msg)
            common["validation_unit"] = json.loads(canonical_json(asdict(unit)))
            common["executor_requirements"] = {"sandbox_permissions": executor_permissions(unit.features)}
            recovery = next(
                (item for item in plan.validation_recoveries if item["node_id"] == node.node_id and tuple(item["source_state"]) == source_state), None
            )
            if recovery is not None:
                recovery_key = "execution_recovery" if recovery.get("checks_started") else "launch_recovery"
                common[recovery_key] = {key: recovery[key] for key in ("failure_kind", "reason", "remedy", "environment", "permission_change")}
            common["payload_schema"] = validation_schema
            common["workspace_policy"] = {
                "allowed_artifacts": [asdict(artifact) for artifact in unit.allowed_artifacts],
                "expected_workspace_effects": list(unit.expected_workspace_effects),
                "isolation_root": unit.isolation_root,
                "requires_isolation": unit.requires_isolation,
                "snapshots_required": bool(unit.allowed_artifacts or unit.expected_workspace_effects or unit.requires_isolation or unit.isolation_root),
            }
            contract = "compact-validation"
        else:
            common.update(
                {
                    "mode": node.mode,
                    "predecessor_evidence_ids": [
                        *(evidence_ids[predecessor] for predecessor in node.predecessors),
                        *_synthesis_reused_evidence_ids(plan, node.node_id),
                    ],
                    "selection_reason": "; ".join(node.selection_reasons) or f"planner selected {node.skill_id}",
                }
            )
            if node.mode in {"fix", "independent-review"}:
                common["change_target"] = node.change_target
                common["planned_paths"] = list(node.coverage)
            if node.mode == "independent-review":
                missing_bounds = tuple(path for path in node.coverage if path not in line_bounds)
                if missing_bounds:
                    msg = f"independent-review node {node.node_id} lacks captured line bounds: " + ", ".join(missing_bounds)
                    raise ValueError(msg)
                common["planned_path_line_bounds"] = [[path, line_bounds[path]] for path in node.coverage]
                common["adversarial_checks"] = list(_independent_adversarial_checks(node.coverage))
                common["adversarial_check_ids"] = [key for key, label in CHECK_LABELS.items() if label in common["adversarial_checks"]]
                contract = "compact-independent-review"
                common["payload_schema"] = independent_schema
            else:
                common["payload_schema"] = synthesis_schema if node.mode == "synthesis" else review_schema
                contract = "compact-review"
            if node.mode == "synthesis":
                common["synthesis_plan_reference"] = synthesis_plan_reference
                common["synthesis_sources"] = [
                    {
                        "artifact_path": (
                            preserved_entries[predecessor]["artifact_path"]
                            if preserved_entries is not None and predecessor in preserved_entries
                            else str(artifact_store / f"{predecessor}.{'validation' if predecessor in validation_units else 'review'}.md")
                        ),
                        "metadata_path": (
                            preserved_entries[predecessor]["metadata_path"]
                            if preserved_entries is not None and predecessor in preserved_entries
                            else str(artifact_store / f"{predecessor}.evidence.json")
                        ),
                    }
                    for predecessor in node.predecessors
                ]
                common["synthesis_examples"] = _synthesis_examples(common)
        if node.mode in {"audit", "independent-review"} and common["owned_paths"]:
            common["provenance_examples"] = _worker_provenance_examples(common, line_bounds)
        persistence_contract = {
            **({"coverage_reuse": common["coverage_reuse"]} if "coverage_reuse" in common else {}),
            "mode": node.mode,
            "node_id": node.node_id,
            "owned_paths": list(node.coverage),
            "result_contract": contract,
            "schema_version": 1,
            "worker_payload_path": str(worker_payload_path),
        }
        worker_input_path = artifact_store / f"{node.node_id}.worker-input.json"
        entry = {
            "artifact_path": str(artifact_path),
            "compiler_operation": compiler_operation,
            "dispatch": common,
            "journal_operation": "journal-append",
            "metadata_path": str(metadata_path),
            "node_id": node.node_id,
            "result_contract": contract,
            "worker_input_path": str(worker_input_path),
            "worker_payload_contract_path": str(worker_payload_contract_path),
            "worker_payload_path": str(worker_payload_path),
            "worker_prompt": _worker_prompt(contract, common),
        }
        worker_input_bytes = (json.dumps(entry, indent=2, sort_keys=True) + "\n").encode()
        if node.mode in {"audit", "synthesis", "validation"} or contract == "compact-independent-review":
            persistence_contract["compiler_preflight"] = {"worker_input_path": str(worker_input_path), "digest": digest_bytes(worker_input_bytes)}
        _queue_materialized_write(
            pending_writes, worker_payload_contract_path, (json.dumps(persistence_contract, indent=2, sort_keys=True) + "\n").encode(), mode=0o444
        )
        _queue_materialized_write(pending_writes, worker_input_path, worker_input_bytes, mode=0o444)
        dispatches.append(entry)
    output: dict[str, Any] = {"dispatches": dispatches, "plan_digest": _plan_digest(plan), "schema_version": 1, "source_state": list(source_state)}
    output["telemetry"] = {
        "worker_input_bytes": sum(len((json.dumps(entry, indent=2, sort_keys=True) + "\n").encode()) for entry in dispatches),
        "worker_prompt_bytes": sum(len(entry["worker_prompt"].encode()) for entry in dispatches),
        "shared_source_packets": len({str(record["artifact_path"]) for record in inspection_groups.values()}),
        "publication_invocations_per_worker": 1,
        "nodes": len(dispatches),
        "nodes_by_mode": dict(Counter(node.mode for node in plan.actual_worker_nodes)),
        "source_demand": source_demand([asdict(node) for node in plan.actual_worker_nodes], repository_root_path.resolve()),
        "concurrent_worker_limit": document.get("concurrent_worker_limit"),
        "projected_waves": (
            projected_waves(
                [asdict(node) for node in plan.actual_worker_nodes], document["concurrent_worker_limit"], early_validation=plan.pre_review_validation_nodes
            )
            if "concurrent_worker_limit" in document
            else None
        ),
        "observed_worker_reads": None,
        "observed_review_seconds": None,
        "measurement_scope": (
            "Serialized context and planned demand; waves assume equal durations and serialize validation/fixes. Unknown observations remain null."
        ),
    }
    output["dispatch_set_digest"] = digest_bytes(canonical_json(output).encode())
    if operation_output_path is None:
        _publish_materialized_writes(artifact_store, pending_writes)
    else:
        _publish_materialization_with_result(artifact_store, pending_writes, operation_output_path, output)
    return output


def _epoch_scoped_plan(plan: GraphPlan, epoch: int) -> GraphPlan:
    """Give every executable identity a repair-epoch namespace."""
    prefix = f"repair-epoch-{epoch:03d}-"
    node_ids = {node.node_id: prefix + node.node_id for node in plan.actual_worker_nodes}

    def mapped(node_id: str | None) -> str | None:
        return node_ids.get(node_id, node_id) if node_id is not None else None

    nodes = tuple(
        replace(
            node,
            node_id=node_ids[node.node_id],
            predecessors=tuple(node_ids[predecessor] for predecessor in node.predecessors),
            synthesis_dependency=mapped(node.synthesis_dependency),
        )
        for node in plan.actual_worker_nodes
    )
    units = tuple(replace(unit, node_id=node_ids[unit.node_id]) for unit in plan.coalesced_validation_units)
    return replace(
        plan,
        audit_delta_reviews=tuple({**item, "node_id": node_ids[item["node_id"]]} for item in plan.audit_delta_reviews),
        actual_worker_nodes=nodes,
        coalesced_validation_units=units,
        current_epoch_node_ids=tuple(node_ids[node_id] for node_id in plan.current_epoch_node_ids),
        execution_epochs=tuple(replace(item, node_ids=tuple(node_ids[node_id] for node_id in item.node_ids)) for item in plan.execution_epochs),
        requirement_to_node=tuple((requirement_id, node_ids[node_id]) for requirement_id, node_id in plan.requirement_to_node),
        selected_validation_units=tuple(node_ids[node_id] for node_id in plan.selected_validation_units),
        pre_review_validation_nodes=tuple(node_ids[node_id] for node_id in plan.pre_review_validation_nodes),
        synthesis_nodes=tuple(node_ids[node_id] for node_id in plan.synthesis_nodes),
        validation_evidence_mapping=tuple(
            replace(mapping, validation_unit_id=node_ids[mapping.validation_unit_id]) for mapping in plan.validation_evidence_mapping
        ),
        routing_decisions=tuple(replace(decision, synthesis_dependency=mapped(decision.synthesis_dependency)) for decision in plan.routing_decisions),
    )


def _capture_path_fingerprints(capture: dict[str, Any], *, label: str) -> dict[str, str]:
    raw = capture.get("repository_path_fingerprints")
    if not isinstance(raw, dict) or any(not isinstance(path, str) for path in raw):
        msg = f"{label} requires repository_path_fingerprints; capture before repairing with the current capture_scope.py"
        raise ValueError(msg)
    paths = _normalized_repository_paths(tuple(raw), label=f"{label}.repository_path_fingerprints")
    if tuple(raw) != paths:
        msg = f"{label}.repository_path_fingerprints requires canonical repository paths"
        raise ValueError(msg)
    if any(not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in raw.values()):
        msg = f"{label}.repository_path_fingerprints must contain SHA-256 identities"
        raise ValueError(msg)
    if not set(_text_list(capture, "captured_scope_paths")) <= set(paths):
        msg = f"{label} path fingerprints do not cover captured_scope_paths"
        raise ValueError(msg)
    if capture.get("repository_state_format") == SNAPSHOT_FORMAT:
        source_snapshot(capture).verify()
    return cast("dict[str, str]", raw)


def _mutation_path_delta(document: dict[str, Any], previous: dict[str, Any], current: dict[str, Any]) -> tuple[str, ...]:
    previous_state = tuple(_required_text(previous, field) for field in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint"))
    if previous_state != _current_metadata_state(document):
        msg = "previous_capture must match the immediately prior plan source_state"
        raise ValueError(msg)
    for field in ("repository_root", "capture_mode", "base_ref", "merge_base", "requested_paths", "head", "branch"):
        if previous.get(field) != current.get(field):
            msg = f"mutation captures differ in {field}; repair epochs cannot change capture boundaries or Git state"
            raise ValueError(msg)
    old_index = _required_text(previous, "index_fingerprint")
    new_index = _required_text(current, "index_fingerprint")
    if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in (old_index, new_index)):
        msg = "mutation captures require SHA-256 index_fingerprint identities"
        raise ValueError(msg)
    if old_index != new_index:
        msg = "repair epoch mutated the Git index"
        raise ValueError(msg)
    before = _capture_path_fingerprints(previous, label="previous_capture")
    after = _capture_path_fingerprints(current, label="new_capture")
    changed = tuple(sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path)))
    declared = _normalized_repository_paths(_text_list(document, "changed_paths", required=True), label="changed_paths")
    if set(declared) != set(changed):
        msg = "changed_paths differs from the immediately prior capture delta: " + ", ".join(changed)
        raise ValueError(msg)
    captured = set(_text_list(previous, "captured_scope_paths")) | set(_text_list(current, "captured_scope_paths"))
    if not set(changed) <= captured:
        msg = "repair changed paths outside both captured scopes: " + ", ".join(sorted(set(changed) - captured))
        raise ValueError(msg)
    return changed


def _mutation_evidence_sources(document: dict[str, Any], plan: GraphPlan) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """Verify historical evidence without relabeling it as final-state evidence."""
    by_id = {node.node_id: node for node in plan.actual_worker_nodes}
    result: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    reused_ids = {evidence_id for _, evidence_id in plan.exact_reused_review_evidence}
    for source in _evidence_sources(document, plan, check_current_inputs=False):
        _kind, expectation, evidence, _content, normalized = _load_evidence_source(source, require_normalized=True)
        node = by_id.get(evidence.node_id)
        if (node is None and evidence.evidence_id not in reused_ids) or evidence.node_id in result:
            msg = f"mutation sources contain an unknown or duplicate node: {evidence.node_id}"
            raise ValueError(msg)
        if node is not None:
            _verified_journal_evidence(source, plan=plan, node=node, source_state=_state(document, "source_state"))
        elif isinstance(expectation, ReviewEvidenceExpectation) and isinstance(evidence, ReviewEvidence):
            blockers = review_source_state_blockers(plan, expectation, evidence, _state(document, "source_state"))
            if blockers:
                msg = "prior reused audit is not valid for the preceding capture: " + "; ".join(blockers)
                raise ValueError(msg)
        if normalized is None:
            msg = f"mutation source lacks normalized evidence: {evidence.node_id}"
            raise ValueError(msg)
        result[evidence.node_id] = (source, normalized)
    return result


def _mutation_invalidated_nodes(
    plan: GraphPlan, replacement: GraphPlan, changed_paths: tuple[str, ...], repository_root: Path, sources: dict[str, tuple[dict[str, Any], dict[str, Any]]]
) -> tuple[str, ...]:
    """Invalidate path owners, inspected dependencies, and their downstream nodes."""
    changed = set(changed_paths)
    units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
    roots: set[str] = set()
    for node in plan.actual_worker_nodes:
        paths = set(units[node.node_id].captured_paths if node.node_id in units else node.coverage)
        for raw in (node.skill_path, *node.instruction_paths, *node.static_references):
            path = Path(raw)
            if not path.is_absolute():
                paths.add(raw)
            elif path.is_relative_to(repository_root):
                paths.add(path.relative_to(repository_root).as_posix())
        if node.node_id in sources:
            _source, record = sources[node.node_id]
            for raw in (*_text_list(record, "files_inspected"), *_text_list(record, "nearby_contract_owners")):
                path = Path(raw)
                paths.add(path.relative_to(repository_root).as_posix() if path.is_absolute() and path.is_relative_to(repository_root) else raw)
        replacements = tuple(
            candidate
            for candidate in replacement.actual_worker_nodes
            if candidate.skill_id == node.skill_id and candidate.mode == node.mode and set(candidate.requirement_ids).intersection(node.requirement_ids)
        )
        routing_changed = node.mode == "audit" and not any(
            (candidate.coverage, candidate.skill_digest, candidate.reference_digests, candidate.instruction_paths)
            == (node.coverage, node.skill_digest, node.reference_digests, node.instruction_paths)
            for candidate in replacements
        )
        instruction_changed = any(
            Path(path).name == "AGENTS.md" and any(Path(owned).is_relative_to(Path(path).parent) for owned in node.coverage) for path in changed
        )
        if changed & paths or instruction_changed or routing_changed or node.mode in {"fix", "revalidation"}:
            roots.add(node.node_id)
    affected = set(roots)
    while True:
        expanded = affected | {node.node_id for node in plan.actual_worker_nodes if affected.intersection(node.predecessors)}
        if expanded == affected:
            break
        affected = expanded
    return tuple(node.node_id for node in plan.actual_worker_nodes if node.node_id in affected)


def _expire_mutation_reuse(planning_input: dict[str, Any]) -> None:
    """A new global source triple cannot inherit old exact-reuse assertions."""
    for field in ("routing_overrides", "routing_decisions"):
        records = []
        for record in _records(planning_input, field):
            updated = dict(record)
            if updated.get("disposition") == "exact-evidence-reused":
                updated.update({"disposition": "selected", "reason": "recaptured source state requires fresh verification"})
                updated.pop("evidence_id", None)
            records.append(updated)
        if field in planning_input:
            planning_input[field] = records
    planning_input["validation_requirements"] = [{**record, "evidence_id": None} for record in _records(planning_input, "validation_requirements")]


def _compact_reuse_overrides(plan: GraphPlan, reused_requirements: dict[str, str]) -> list[dict[str, Any]]:
    """Preserve routing choices in schema-valid JSON while replacing audited leaves."""
    overrides = []
    for decision in plan.routing_decisions:
        if decision.requirement_id in reused_requirements:
            decision = replace(
                decision,
                disposition="exact-evidence-reused",
                evidence_id=reused_requirements[decision.requirement_id],
                review_surface=tuple(sorted(decision.review_surface)),
            )
        overrides.append({key: value for key, value in asdict(decision).items() if key in _COMPACT_ROUTING_OVERRIDE_FIELDS and value is not None})
    return json.loads(canonical_json(overrides))


def _audit_reuse_blocker(record: dict[str, Any], *, invalidated: bool) -> tuple[str, str] | None:
    if record.get("mode") != "audit" or record.get("status") not in {"completed", "no-findings"}:
        return "ineligible-evidence", "Only completed audit leaves can be reused across captures."
    if record.get("scope_limitations"):
        return "coverage-limitations", "The audit declares incomplete owned-path coverage."
    if record.get("limitations"):
        return "unclassified-limitations", "Free-text caveats cannot prove independence from changed inputs or prior validation."
    if record.get("unresolved_uncertainties"):
        return "unresolved-uncertainty", "The audit declares unresolved semantic or dependency uncertainty."
    if any(limit["status"] != "delegated" for limit in record.get("validation_limits", [])):
        return "validation-evidence-limits", "Required environmental validation evidence is unavailable or failed."
    return ("invalidated-inputs", "Owned inputs, routing, or a predecessor changed.") if invalidated else None


def _carry_forward_audits(  # noqa: C901, PLR0912, PLR0913, PLR0915 - preserve provenance and report every reuse rejection.
    document: dict[str, Any],
    old_plan: GraphPlan,
    candidate_plan: GraphPlan,
    planning_input: dict[str, Any],
    *,
    invalidated: tuple[str, ...],
    sources: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    observed_metadata_transition: ExternalMetadataTransition | None = None,
) -> tuple[GraphPlan, list[dict[str, str]]]:
    """Convert only proven unchanged leaves into non-executable routed reuse."""
    decisions = {
        node.node_id: {"node_id": node.node_id, "disposition": "not-reused", "reason_code": "missing-evidence", "reason": "No accepted source was supplied."}
        for node in old_plan.actual_worker_nodes
    }

    def decision(node_id: str, code: str, reason: str) -> None:
        decisions[node_id] = {"node_id": node_id, "disposition": "reused" if code == "verified" else "not-reused", "reason_code": code, "reason": reason}

    previous, current = document["previous_capture"], document["new_capture"]
    if current.get("repository_state_format") != SNAPSHOT_FORMAT:
        for node_id in sources:
            decision(node_id, "unsupported-snapshot", "The current capture lacks content-bound path identities.")
        return candidate_plan, list(decisions.values())
    target = source_snapshot(current)
    target.verify()
    snapshots = {item.source_state: item for item in old_plan.reuse_source_snapshots}
    for item in _records(document, "external_metadata_transitions"):
        transition = metadata_transition(item)
        snapshots.update({transition.before.source_state: transition.before, transition.after.source_state: transition.after})
    if previous.get("repository_state_format") == SNAPSHOT_FORMAT:
        origin = source_snapshot(previous)
        origin.verify()
        snapshots[origin.source_state] = origin
    snapshots[target.source_state] = target
    root = Path(target.repository_root)
    transitions: list[AuditReuseTransition] = []
    records: list[tuple[ReviewEvidenceExpectation, ReviewEvidence]] = []
    reused_requirements: dict[str, str] = {}
    for node_id, (source, record) in sources.items():
        blocker = _audit_reuse_blocker(record, invalidated=node_id in invalidated)
        if blocker is not None:
            decision(node_id, *blocker)
            continue
        _kind, expectation, evidence, _content, _normalized = _load_evidence_source(source, require_normalized=True)
        if not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence):
            decision(node_id, "ineligible-evidence", "The source is not typed review evidence.")
            continue
        inputs = expectation.audit_input_identity
        origin = snapshots.get(expectation.source_state)
        if inputs is None or origin is None or evidence.predecessor_evidence_ids or expectation.execution_profile != candidate_plan.execution_profile:
            decision(node_id, "unproven-inputs", "Bound origin/inputs, predecessor independence, or the execution profile do not permit reuse.")
            continue
        candidates = tuple(
            node
            for node in candidate_plan.actual_worker_nodes
            if node.mode == "audit"
            and not node.predecessors
            and node.requirement_ids == evidence.requirement_ids
            and (node.skill_id, node.skill_path, node.skill_digest, node.reference_digests, node.coverage)
            == (evidence.skill_id, evidence.skill_path, evidence.skill_digest, evidence.reference_digests, inputs.owned_paths)
        )
        if len(candidates) != 1:
            decision(node_id, "routing-identity-changed", "No unique unchanged audit leaf owns the same requirements and inputs.")
            continue
        candidate = candidates[0]
        instructions = _applicable_instruction_paths(root, candidate.coverage, candidate.instruction_paths)
        transition = AuditReuseTransition(
            evidence_id=evidence.evidence_id,
            source_state=expectation.source_state,
            target_state=target.source_state,
            artifact_digest=evidence.raw_result_digest,
            artifact_path=str(Path(_required_text(source, "artifact_path")).resolve()),
            metadata_path=str(Path(_required_text(source, "metadata_path")).resolve()),
            instruction_digests=tuple((path, _file_identity_digest(path)) for path in instructions),
            metadata_transitions=_metadata_chain_from(document, origin.source_state),
        )
        metadata_blockers = intervening_metadata_blockers(record, transition.metadata_transitions)
        if metadata_blockers:
            decision(node_id, "metadata-dependencies-changed", canonical_json(metadata_blockers))
            continue
        try:
            verify_reuse_inputs(origin, target, inputs, transition)
        except ValueError as error:
            # Incomplete/changed inputs are ordinary fresh review work, not reuse.
            decision(node_id, "input-proof-failed", str(error))
            continue
        reconciliation = _validation_reconciliation(replace(candidate_plan, audit_reuse_transitions=(transition,)), [record])
        if reconciliation["blockers"]:
            decision(node_id, "validation-requirements-changed", "; ".join(reconciliation["blockers"]))
            continue
        decision(node_id, "verified", "Complete audit inputs and dependencies are unchanged.")
        transitions.append(transition)
        records.append((expectation, evidence))
        reused_requirements.update(dict.fromkeys(evidence.requirement_ids, evidence.evidence_id))
    if not transitions:
        return candidate_plan, list(decisions.values())
    planning_input.pop("routing_decisions", None)
    planning_input["routing_overrides"] = _compact_reuse_overrides(candidate_plan, reused_requirements)
    require_schema(planning_input, _PLANNING_INPUT_SCHEMA)
    routed = plan_from_document(
        planning_input,
        catalog_path=Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)),
        skill_roots=(DEFAULT_SKILL_ROOT,),
        repository_root=root,
        observed_metadata_transition=observed_metadata_transition,
    )
    needed_states = {state for transition in transitions for state in (transition.source_state, transition.target_state)}
    routed = replace(
        routed,
        audit_reuse_transitions=tuple(sorted(transitions, key=lambda item: item.evidence_id)),
        reuse_source_snapshots=tuple(snapshots[state] for state in sorted(needed_states)),
    )
    for expectation, evidence in records:
        blockers = review_source_state_blockers(routed, expectation, evidence, target.source_state)
        if blockers:
            msg = "rerouted audit reuse is inconsistent: " + "; ".join(blockers)
            raise ValueError(msg)
    return routed, list(decisions.values())


def _coverage_proof(context: dict[str, Any]) -> dict[str, Any]:
    """Load a digest-bound full proof and reject a divergent worker projection."""
    if "proof_reference" not in context:
        # Saved inline dispatches and evidence retain their original representation.
        return context
    reference = context["proof_reference"]
    if not isinstance(reference, dict) or set(reference) != {"path", "digest"}:
        msg = "coverage proof reference requires only path and digest"
        raise ValueError(msg)
    path = Path(_required_text(reference, "path"))
    if not path.is_absolute():
        msg = "coverage proof reference requires an absolute artifact path"
        raise ValueError(msg)
    content = _read_regular_file_no_follow(path)
    if digest_bytes(content) != _required_text(reference, "digest"):
        msg = "coverage proof digest differs from its bound execution view"
        raise ValueError(msg)
    proof = json.loads(content)
    if not isinstance(proof, dict) or "proof_reference" in proof:
        msg = "coverage proof artifact must contain a complete inline proof object"
        raise ValueError(msg)
    required_fields = {
        "node_id": str,
        "evidence_id": str,
        "artifact_path": str,
        "metadata_path": str,
        "artifact_digest": str,
        "origin": dict,
        "target": dict,
        "units": list,
        "original_findings": list,
        "original_validation_requirements": list,
        "original_handoffs": list,
        "instruction_digests": list,
        "metadata_transitions": list,
    }
    for field, expected_type in required_fields.items():
        if not isinstance(proof.get(field), expected_type):
            msg = f"coverage proof {field} must be a {expected_type.__name__}"
            raise TypeError(msg)
    try:
        expected = coverage_execution_view(proof, reference)
    except (KeyError, TypeError, AttributeError) as error:
        msg = "coverage proof artifact lacks complete execution context"
        raise ValueError(msg) from error
    if context != expected:
        msg = "coverage execution view differs from original immutable findings or verified unit decisions"
        raise ValueError(msg)
    return proof


def _verify_delta_context(context: dict[str, Any], dispatch: dict[str, Any]) -> None:
    """Replay the original immutable partition proof at materialization and acceptance."""
    context = _coverage_proof(context)
    if dispatch.get("mode") != "audit":
        msg = "delta coverage applies only to audit mode"
        raise ValueError(msg)
    origin, target = source_snapshot(context["origin"]), source_snapshot(context["target"])
    if target.source_state != _state(dispatch, "source_state"):
        msg = "delta coverage target differs from the dispatched source state"
        raise ValueError(msg)
    _kind, expectation, evidence, _content, record = _load_evidence_source(context, require_normalized=True)
    inputs = expectation.audit_input_identity if isinstance(expectation, ReviewEvidenceExpectation) else None
    if not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence) or inputs is None or record is None:
        msg = "delta coverage requires compiler-bound audit input identities"
        raise ValueError(msg)
    if expectation.coverage_reuse is not None or _audit_reuse_blocker(record, invalidated=False) is not None:
        msg = "delta coverage origin must be a complete fresh audit without unresolved limitations"
        raise ValueError(msg)
    if (origin.source_state, inputs.owned_paths, evidence.skill_id, evidence.skill_path, evidence.requirement_ids) != (
        expectation.source_state,
        _text_list(dispatch, "owned_paths"),
        dispatch["skill_id"],
        dispatch["skill_path"],
        _text_list(dispatch, "requirement_ids"),
    ):
        msg = "delta coverage changes original routing, ownership, or source identity"
        raise ValueError(msg)
    transition = AuditReuseTransition(
        evidence.evidence_id,
        origin.source_state,
        target.source_state,
        evidence.raw_result_digest,
        context["artifact_path"],
        context["metadata_path"],
        _string_pairs(context, "instruction_digests"),
        tuple(metadata_transition(item) for item in _records(context, "metadata_transitions")),
    )
    decisions = coverage_decisions(record, origin, target, inputs, transition)
    if (
        context["units"] != decisions
        or context["original_findings"] != record["findings"]
        or context["original_validation_requirements"] != record["validation_requirements"]
        or context["original_handoffs"] != record["handoffs"]
        or context["evidence_id"] != evidence.evidence_id
        or context["artifact_digest"] != evidence.raw_result_digest
        or context.get("original_audit_context", {})
        != {key: record[key] for key in ("execution_facts", "validation_limits", "unresolved_uncertainties") if key in record}
        or context.get("original_git_context", {}) != audit_git_context(record)
    ):
        msg = "delta coverage differs from original immutable findings or verified unit decisions"
        raise ValueError(msg)
    if not reused_paths(context):
        msg = "delta coverage has no reusable units"
        raise ValueError(msg)


def _blocked_coverage_reviews(record: dict[str, Any], candidate: GraphPlan) -> list[dict[str, Any]] | None:
    """Expose why a partition, or an audit without one, cannot support reuse."""
    blocker = _audit_reuse_blocker(record, invalidated=False)
    if blocker is None and not record.get("coverage_units"):
        blocker = ("no-coverage-partition", "The audit did not supply a complete coverage partition.")
    if blocker is None and record.get("coverage_reuse"):
        blocker = ("derived-coverage-origin", "A partial recheck cannot replace its original fresh partition proof.")
    if blocker is None:
        return None
    decision = {"disposition": "recheck", "reason_code": blocker[0], "reason": blocker[1]}
    return [
        {
            "node_id": node.node_id,
            "evidence_id": record["evidence_id"],
            **decision,
            "units": [{**unit, **decision} for unit in record.get("coverage_units", [])],
        }
        for node in candidate.actual_worker_nodes
        if node.mode == "audit" and node.requirement_ids == tuple(record["requirement_ids"])
    ]


def _plan_delta_audits(  # noqa: C901 - keep source and validation eligibility gates together before publishing a reuse proof.
    document: dict[str, Any], previous: GraphPlan, candidate: GraphPlan, sources: dict[str, tuple[dict[str, Any], dict[str, Any]]]
) -> tuple[GraphPlan, list[dict[str, Any]]]:
    """Retain full specialist ownership while dispatching only stale partitions for reads."""
    if any(document[field].get("repository_state_format") != SNAPSHOT_FORMAT for field in ("previous_capture", "new_capture")):
        return candidate, []
    origin, target = (source_snapshot(document[field]) for field in ("previous_capture", "new_capture"))
    snapshots = {item.source_state: item for item in previous.reuse_source_snapshots}
    snapshots[origin.source_state] = origin
    for item in _records(document, "external_metadata_transitions"):
        transition = metadata_transition(item)
        snapshots.update({transition.before.source_state: transition.before, transition.after.source_state: transition.after})
    contexts = []
    reviews = []
    for source, record in sources.values():
        blocked = _blocked_coverage_reviews(record, candidate)
        if blocked is not None:
            reviews.extend(blocked)
            continue
        _kind, expectation, evidence, _content, _record = _load_evidence_source(source, require_normalized=True)
        if not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence) or expectation.audit_input_identity is None:
            continue
        for node in candidate.actual_worker_nodes:
            if node.mode != "audit" or node.predecessors or node.requirement_ids != evidence.requirement_ids:
                continue
            inputs = expectation.audit_input_identity
            chain = _metadata_chain_from(document, expectation.source_state)
            audit_origin = snapshots.get(expectation.source_state)
            if audit_origin is None or (node.skill_digest, node.reference_digests, node.coverage) != (
                evidence.skill_digest,
                evidence.reference_digests,
                inputs.owned_paths,
            ):
                continue
            instructions = _applicable_instruction_paths(Path(target.repository_root), node.coverage, node.instruction_paths)
            transition = AuditReuseTransition(
                evidence.evidence_id,
                origin.source_state,
                target.source_state,
                evidence.raw_result_digest,
                source["artifact_path"],
                source["metadata_path"],
                tuple((path, _file_identity_digest(path)) for path in instructions),
                chain,
            )
            transition = replace(transition, source_state=audit_origin.source_state)
            reconciliation = _validation_reconciliation(replace(candidate, audit_reuse_transitions=(transition,)), [record])
            if reconciliation["blockers"]:
                reviews.append(
                    {
                        "node_id": node.node_id,
                        "evidence_id": evidence.evidence_id,
                        "disposition": "recheck",
                        "reason_code": "validation-requirements-changed",
                        "reason": "; ".join(reconciliation["blockers"]),
                        "units": [],
                    }
                )
                continue
            units = coverage_decisions(record, audit_origin, target, inputs, transition)
            reviews.append(
                {
                    "node_id": node.node_id,
                    "evidence_id": evidence.evidence_id,
                    "units": [
                        {
                            **unit,
                            "reason_code": (
                                "dependency-uncertainty"
                                if unit["dependency_uncertainty"]
                                else "verified"
                                if unit["disposition"] == "reused"
                                else "input-proof-failed"
                            ),
                        }
                        for unit in units
                    ],
                }
            )
            if not any(unit["disposition"] == "reused" for unit in units):
                continue
            context = {
                **source,
                "node_id": node.node_id,
                "origin": asdict(audit_origin),
                "target": asdict(target),
                "units": units,
                "evidence_id": evidence.evidence_id,
                "artifact_digest": evidence.raw_result_digest,
                "original_findings": record["findings"],
                "original_validation_requirements": record["validation_requirements"],
                "original_handoffs": record["handoffs"],
                "original_audit_context": {key: record[key] for key in ("execution_facts", "validation_limits", "unresolved_uncertainties") if key in record},
                "original_git_context": audit_git_context(record),
                "instruction_digests": list(transition.instruction_digests),
                "metadata_transitions": [asdict(item) for item in chain],
            }
            contexts.append(json.loads(canonical_json(context)))
    return replace(candidate, audit_delta_reviews=tuple(contexts)), reviews


def _verify_audit_metadata(payload: dict[str, Any], fingerprints: FingerprintEvidence, coverage_reuse: dict[str, Any] | None = None) -> None:
    """Apply the same dependency/read proof at compilation and artifact verification."""
    if not fingerprints.metadata_transitions:
        return
    latest = fingerprints.metadata_transitions[-1]
    blockers = metadata_audit_blockers(
        {**payload, "coverage_reuse": coverage_reuse}, latest, fresh_current=fingerprints.before == fingerprints.after == latest.after.source_state
    )
    if blockers:
        msg = "Audit must be rechecked entirely on the current metadata state: " + canonical_json(blockers)
        raise ValueError(msg)


def _metadata_chain_from(document: dict[str, Any], state: tuple[str, str, str]) -> tuple[ExternalMetadataTransition, ...]:
    transitions = tuple(metadata_transition(item) for item in _records(document, "external_metadata_transitions"))
    for ordinal, transition in enumerate(transitions):
        if transition.before.source_state == state:
            return transitions[ordinal:]
    for reuse in _records(document.get("plan", {}), "audit_reuse_transitions"):
        if _state(reuse, "source_state") == state:
            return tuple(metadata_transition(item) for item in _records(reuse, "metadata_transitions"))
    return ()


def _current_metadata_state(document: dict[str, Any]) -> tuple[str, str, str]:
    transitions = tuple(metadata_transition(item) for item in _records(document, "external_metadata_transitions"))
    return metadata_states(_state(document, "source_state"), transitions)[-1]


def _metadata_evidence_blockers(document: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    if not document.get("external_metadata_transitions"):
        return []
    current = _current_metadata_state(document)
    transition = metadata_transition(document["external_metadata_transitions"][-1])
    return [
        f"Evidence requires revalidation after external staging: {record['evidence_id']}: {canonical_json(reasons)}"
        for record in records
        if tuple(record.get("observed_source_state", ())) != current
        if (reasons := _metadata_node_reasons(record.get("mode", "validation"), (), record, transition))
    ]


def _metadata_node_reasons(mode: str, predecessors: tuple[str, ...], record: dict[str, Any], transition: ExternalMetadataTransition) -> list[dict[str, str]]:
    """Keep fresh review, execution, and synthesis policies separate from audit dependencies."""
    policies = {
        "independent-review": "Fresh independent review must inspect the current change target.",
        "validation": "Validation execution and workspace evidence must bind to the current metadata state.",
        "synthesis": "Synthesis must consume the current accepted evidence bundle.",
    }
    if mode != "audit" or predecessors:
        return [{"reason_code": f"{mode}-policy", "reason": policies.get(mode, "Dependent evidence requires a current-state review.")}]
    return metadata_audit_blockers(record, transition)


def _metadata_resume_decisions(
    plan: GraphPlan, lifecycle: dict[str, str], records: dict[str, dict[str, Any]], transition: ExternalMetadataTransition
) -> list[dict[str, Any]]:
    """Explain both preserved evidence and work awaiting a current-state execution."""
    decisions = []
    inherited = {context["node_id"]: {"coverage_reuse": context} for context in plan.audit_delta_reviews}
    for node in plan.actual_worker_nodes:
        record = records.get(node.node_id, inherited.get(node.node_id, {}))
        reasons = _metadata_node_reasons(node.mode, node.predecessors, record, transition)
        status = lifecycle.get(node.node_id, "pending")
        if status not in {"accepted", "in-flight"}:
            reasons.append({"reason_code": "no-active-evidence", "reason": f"Node lifecycle is {status}; no accepted or active review to preserve."})
        decisions.append(
            {
                "node_id": node.node_id,
                "mode": node.mode,
                "prior_status": status,
                "disposition": "recheck" if reasons else "preserved",
                "reasons": reasons
                or [
                    {
                        "reason_code": "pending-payload-verification" if status == "in-flight" else "unchanged-source-inputs",
                        "reason": "Compiler will verify actual dependencies and reads."
                        if status == "in-flight"
                        else "Source reads and combined content are unchanged.",
                    }
                ],
                **({"discovery_reconciliation": discovery_reconciliation(record, transition)} if not reasons and record else {}),
            }
        )
    return decisions


def _restart_reused_metadata_audits(
    plan: GraphPlan, records: list[dict[str, Any]], transition: ExternalMetadataTransition, catalog_path: Path
) -> tuple[GraphPlan, list[dict[str, Any]]]:
    """Turn invalidated non-executable audit reuse back into routed review work."""
    reused_ids = {evidence_id for _requirement_id, evidence_id in plan.exact_reused_review_evidence}
    stale = {
        record["evidence_id"]: reasons
        for record in records
        if record["evidence_id"] in reused_ids
        if (reasons := _metadata_node_reasons(record.get("mode", "validation"), (), record, transition))
    }
    if not stale:
        return plan, []
    routing = tuple(replace(item, disposition="selected", evidence_id=None) if item.evidence_id in stale else item for item in plan.routing_decisions)
    requirement_sources = {requirement_id: evidence_id for requirement_id, evidence_id in plan.exact_reused_review_evidence if evidence_id in stale}
    selected = tuple(item for item in routing if item.requirement_id in requirement_sources)
    catalog = load_routing_catalog(catalog_path, skill_roots=(DEFAULT_SKILL_ROOT,))
    requirements = review_requirements_from_routing(catalog, selected)
    if {item.requirement_id for item in requirements} != set(requirement_sources):
        msg = "external metadata resume cannot restore the invalidated reused review routing; replan required"
        raise ValueError(msg)
    reserved = tuple(node.node_id for node in plan.actual_worker_nodes) + tuple(evidence_id.removeprefix("review:") for evidence_id in reused_ids)
    fresh, mappings = coalesce_review_requirements(requirements, reserved_node_ids=reserved)
    fresh = tuple(_bind_worker_node_provenance(node) for node in fresh)
    connected = []
    for node in plan.actual_worker_nodes:
        if node.mode == "synthesis":
            restored = tuple(
                audit.node_id
                for audit in fresh
                if node.skill_id == "repository-production-review"
                or any(item.synthesis_dependency == node.node_id and item.requirement_id in audit.requirement_ids for item in selected)
            )
            node = replace(node, predecessors=tuple(dict.fromkeys((*node.predecessors, *restored))))
        connected.append(node)
    nodes = _schedule_with_validation_barrier((*connected, *fresh), plan.pre_review_validation_nodes)
    epochs = _partition_execution_epochs(nodes, WorkerBudget(plan.worker_budget, plan.recovery_finalization_reserve)) if plan.execution_epochs else ()
    updated = replace(
        plan,
        actual_worker_nodes=nodes,
        complete_node_count=len(nodes),
        selected_review_requirements=tuple(sorted({*plan.selected_review_requirements, *requirement_sources})),
        requirement_to_node=tuple(sorted((*plan.requirement_to_node, *mappings))),
        routing_decisions=routing,
        exact_reused_review_evidence=tuple(item for item in plan.exact_reused_review_evidence if item[1] not in stale),
        reused_review_identities=tuple(item for item in plan.reused_review_identities if item.evidence_id not in stale),
        audit_reuse_transitions=tuple(item for item in plan.audit_reuse_transitions if item.evidence_id not in stale),
        execution_epochs=epochs,
        current_epoch_node_ids=epochs[0].node_ids if epochs else (),
        requires_continuation=len(epochs) > 1,
    )
    decisions = [
        {
            "node_id": node.node_id,
            "mode": node.mode,
            "prior_status": "reused",
            "disposition": "recheck",
            "replaced_evidence_ids": sorted({requirement_sources[requirement] for requirement in node.requirement_ids}),
            "reasons": [
                {**reason, "evidence_id": evidence_id}
                for evidence_id in sorted({requirement_sources[requirement] for requirement in node.requirement_ids})
                for reason in stale[evidence_id]
            ],
        }
        for node in fresh
    ]
    return updated, decisions


def _preserve_metadata_barrier_history(
    path: Path, continuation: dict[str, Any], events: tuple[dict[str, Any], ...], preserved: dict[str, dict[str, Any]]
) -> None:
    """Retain the verified history that admitted preserved audits, including prior resets."""
    plan = _graph_plan(continuation["plan"])
    keep = set(plan.pre_review_validation_nodes) | set(preserved)
    migrated: list[dict[str, Any]] = []
    state: dict[str, str] = {}
    for original in events:
        if original["node_id"] not in keep:
            continue
        event = {
            **original,
            "affected_node_ids": list(_apply_journal_transition(plan, state, node_id=original["node_id"], status=original["status"])),
            "plan_digest": _plan_digest(plan),
            "previous_event_digest": migrated[-1]["event_digest"] if migrated else None,
            "sequence": len(migrated) + 1,
        }
        event.pop("event_digest")
        event["event_digest"] = digest_bytes(canonical_json(event).encode())
        migrated.append(event)
    _fold_execution_journal(plan, _state(continuation, "source_state"), tuple(migrated))
    _write_text_once(path, "".join(canonical_json(event) + "\n" for event in migrated))
    for node_id in plan.pre_review_validation_nodes:
        if state.get(node_id) in {"accepted", "blocked", "in-flight"}:
            append_journal_event(
                path,
                continuation,
                JournalEventRequest(node_id, "invalidated", reason="External metadata changed; historical pre-review validation must be rerun."),
            )


def resume_after_external_metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Publish a new continuation while preserving original audit and Git provenance."""
    transition = metadata_transition({"before": document["previous_capture"], "after": document["new_capture"]})
    if transition.before.source_state != _current_metadata_state(document):
        msg = "external metadata previous capture differs from the current reviewed state"
        raise ValueError(msg)
    plan = _graph_plan(document["plan"])
    state = _state(document, "source_state")
    entries = _dispatches_by_node(_read_json_object(Path(document["dispatches_path"])), plan=plan, source_state=state)
    events, lifecycle, _head = read_execution_journal(Path(document["journal_path"]), plan=plan, source_state=state)
    sources, records = _accepted_journal_sources(plan, state, events, entries, include_blocked=True)
    by_node = {record["node_id"]: record for record in records}
    for context in plan.audit_delta_reviews:
        _verify_delta_context(context, entries[context["node_id"]]["dispatch"])
    for node in plan.actual_worker_nodes:
        dispatch = entries[node.node_id]["dispatch"]
        current_instructions = _applicable_instruction_paths(Path(transition.after.repository_root), node.coverage, node.instruction_paths)
        expected_instructions = _string_pairs(dispatch, "instruction_digests")
        if (
            tuple((path, _file_identity_digest(path)) for path in current_instructions) != expected_instructions
            or _file_identity_digest(node.skill_path) != node.skill_digest
            or any(_file_identity_digest(path) != digest for path, digest in node.reference_digests)
        ):
            msg = "external metadata resume requires unchanged applicable instructions, skills, and references"
            raise ValueError(msg)
    decisions = _metadata_resume_decisions(plan, lifecycle, by_node, transition)
    preserved = {item["node_id"]: entries[item["node_id"]] for item in decisions if item["disposition"] == "preserved"}
    discarded_coverage = {item["node_id"] for item in decisions if any("evidence_id" in reason for reason in item["reasons"])}
    plan = replace(plan, audit_delta_reviews=tuple(context for context in plan.audit_delta_reviews if context["node_id"] not in discarded_coverage))
    plan, restarted = _restart_reused_metadata_audits(plan, records, transition, Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)))
    decisions.extend(restarted)
    transitions = [*_records(document, "external_metadata_transitions"), asdict(transition)]
    continuation = json.loads(canonical_json({"plan": asdict(plan), "source_state": list(state), "external_metadata_transitions": transitions}))
    root = Path(document["artifact_store"]).resolve()
    first_entry = next(iter(entries.values()), None)
    if first_entry is None:
        msg = "external metadata resume requires a materialized review graph"
        raise ValueError(msg)
    materialized = materialize_dispatches(
        {
            "plan": continuation["plan"],
            "source_state": list(state),
            "external_metadata_transitions": transitions,
            "artifact_store": str(root),
            "repository_root": transition.after.repository_root,
            "authorization": first_entry["dispatch"]["authorization"],
            "state_verification_command": first_entry["dispatch"]["state_verification_command"],
            "sources": _continuation_synthesis_sources(entries),
        },
        preserved_entries=preserved,
    )
    paths = {
        "lifecycle_input_path": root / "lifecycle.json",
        "dispatches_path": root / "dispatches.json",
        "capture_path": root / "capture.json",
        "journal_path": root / "execution.jsonl",
    }
    for field, value in (("lifecycle_input_path", continuation), ("dispatches_path", materialized), ("capture_path", document["new_capture"])):
        _write_text_once(paths[field], json.dumps(value, indent=2, sort_keys=True) + "\n")
    if plan.pre_review_validation_nodes:
        _preserve_metadata_barrier_history(paths["journal_path"], continuation, events, preserved)
    else:
        _write_text_once(paths["journal_path"], "")
        for node_id in preserved:
            request = JournalEventRequest(node_id, lifecycle[node_id], source=sources.get(node_id))
            append_journal_event(paths["journal_path"], continuation, request)
    return {
        "status": "resumed",
        "transition_kind": "observed-external-git-metadata",
        "lifecycle_input": continuation,
        "dispatch_set": materialized,
        "original_source_state": list(state),
        "current_source_state": list(transition.after.source_state),
        "preserved_node_ids": sorted(preserved),
        "recheck_node_ids": sorted({node.node_id for node in plan.actual_worker_nodes} - set(preserved)),
        "discarded_coverage_node_ids": sorted(discarded_coverage),
        "node_decisions": decisions,
        "node_counts": {
            "preserved": len(preserved),
            "recheck": len(plan.actual_worker_nodes) - len(preserved),
            "in_flight_pending_verification": sum(item["disposition"] == "preserved" and item["prior_status"] == "in-flight" for item in decisions),
        },
        "recheck_reason_counts": dict(Counter(reason["reason_code"] for item in decisions if item["disposition"] == "recheck" for reason in item["reasons"])),
        **{key: str(path) for key, path in paths.items()},
    }


def _replacement_lineage(previous: GraphPlan, current: GraphPlan, sources: dict[str, tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, object]]:
    """Map every final executable node to the prior contracts it replaces."""
    contracts = {node.node_id: asdict(node) for node in previous.actual_worker_nodes}
    contracts.update({node_id: record for node_id, (_source, record) in sources.items() if node_id not in contracts})
    return [
        {
            "node_id": node.node_id,
            "replaces_node_ids": [
                node_id
                for node_id, old in contracts.items()
                if old.get("skill_id") == node.skill_id
                and old.get("mode") == node.mode
                and (set(old["requirement_ids"]).intersection(node.requirement_ids) or node.mode == "synthesis")
            ],
        }
        for node in current.actual_worker_nodes
    ]


def advance_after_mutation(document: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0915
    """Close one repair epoch, recapture once, and emit a fresh final-state graph."""
    raw_plan = document.get("plan")
    previous_capture = document.get("previous_capture")
    new_capture = document.get("new_capture")
    planning_template = document.get("planning_template")
    if not isinstance(raw_plan, dict) or not isinstance(previous_capture, dict) or not isinstance(new_capture, dict) or not isinstance(planning_template, dict):
        msg = "advance-after-mutation requires plan, previous_capture, new_capture, and planning_template objects"
        raise TypeError(msg)
    old_plan = _graph_plan(raw_plan)
    old_source_state = _state(document, "source_state")
    if any(unit.source_state != old_source_state for unit in old_plan.coalesced_validation_units):
        msg = "prior plan validation units differ from source_state"
        raise ValueError(msg)
    new_source_state = (new_capture.get("scope_fingerprint"), new_capture.get("captured_worktree_fingerprint"), new_capture.get("repository_state_fingerprint"))
    if any(not isinstance(value, str) or not value.strip() for value in new_source_state):
        msg = "advance-after-mutation new_capture lacks the complete source fingerprint triple"
        raise ValueError(msg)
    new_state = cast("tuple[str, str, str]", new_source_state)
    if new_state == old_source_state:
        msg = "advance-after-mutation requires a source-changing recapture"
        raise ValueError(msg)
    authorization_before = _required_text(document, "authorization_before")
    authorization_after = _required_text(document, "authorization_after")
    if (authorization_before, authorization_after) not in {("review-and-fix", "review-and-fix"), ("review-only", "review-and-fix")}:
        msg = "mutation epochs require review-and-fix authorization, optionally upgraded from review-only"
        raise ValueError(msg)
    epoch = _required_int(document, "repair_epoch")
    if epoch < 1:
        msg = "repair_epoch must be positive"
        raise ValueError(msg)
    changed_paths = _mutation_path_delta(document, previous_capture, new_capture)
    metadata = metadata_transition({"before": new_capture, "after": document["post_repair_capture"]}) if "post_repair_capture" in document else None
    captured_paths = _text_list(new_capture, "captured_scope_paths")
    sources = _mutation_evidence_sources(document, old_plan)
    planning_input = bootstrap_document(new_capture, planning_template)
    planning_input["authorization"] = authorization_after
    _expire_mutation_reuse(planning_input)
    require_schema(planning_input, _PLANNING_INPUT_SCHEMA)
    repository_root = Path(_required_text(planning_input, "repository_root")).resolve()
    catalog_path = Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)).resolve()
    new_plan = plan_from_document(
        planning_input, catalog_path=catalog_path, skill_roots=(DEFAULT_SKILL_ROOT,), repository_root=repository_root, observed_metadata_transition=metadata
    )
    if not new_plan.dispatch_allowed:
        msg = "recaptured repair epoch produced a blocked final-state plan: " + "; ".join(new_plan.blockers)
        raise ValueError(msg)
    invalidated = _mutation_invalidated_nodes(old_plan, new_plan, changed_paths, repository_root, sources)
    new_plan, reuse_decisions = _carry_forward_audits(
        document, old_plan, new_plan, planning_input, invalidated=invalidated, sources=sources, observed_metadata_transition=metadata
    )
    new_plan, coverage_reviews = _plan_delta_audits(document, old_plan, new_plan, sources)
    new_plan = _epoch_scoped_plan(new_plan, epoch)
    reused_ids = {item.evidence_id for item in new_plan.audit_reuse_transitions}
    artifact_store = Path(_required_text(document, "artifact_store")).resolve() / f"repair-epoch-{epoch:03d}"
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(artifact_store),
            "authorization": authorization_after,
            "plan": json.loads(canonical_json(asdict(new_plan))),
            "repository_root": str(repository_root),
            "routing_catalog_path": str(catalog_path),
            "source_state": list(new_state),
            "state_verification_command": _required_text(document, "state_verification_command"),
        }
    )
    lifecycle = json.loads(canonical_json({"plan": asdict(new_plan), "source_state": list(new_state)}))
    continuation = {
        "lifecycle_input_path": artifact_store / "lifecycle.json",
        "dispatches_path": artifact_store / "dispatches.json",
        "capture_path": artifact_store / "capture.json",
        "journal_path": artifact_store / "execution.jsonl",
    }
    for key, value in (("lifecycle_input_path", lifecycle), ("dispatches_path", dispatch_set), ("capture_path", new_capture)):
        _write_text_once(continuation[key], json.dumps(value, indent=2, sort_keys=True) + "\n")
    _write_text_once(continuation["journal_path"], "")
    old_paths = set(_text_list(previous_capture, "captured_scope_paths"))
    newly_touched_paths = tuple(sorted(set(captured_paths) - old_paths))
    unaffected = tuple(node for node in old_plan.actual_worker_nodes if node.node_id not in invalidated)
    fix_node_id = f"fix-epoch-{epoch:03d}"
    result = {
        "authorization_transition": {"after": authorization_after, "before": authorization_before},
        "dispatch_set": dispatch_set,
        "invalidated_nodes": [{"node_id": node_id, "state": "awaiting-replan"} for node_id in invalidated],
        "capture": new_capture,
        "lifecycle_input": lifecycle,
        **{key: str(path) for key, path in continuation.items()},
        "new_plan": asdict(new_plan),
        "new_source_state": list(new_state),
        "newly_touched_paths": list(newly_touched_paths),
        "old_source_state": list(old_source_state),
        "preserved_evidence": [
            {"node_id": node_id, "source": source, "evidence_id": record["evidence_id"]}
            for node_id, (source, record) in sources.items()
            if record["evidence_id"] in reused_ids
        ],
        "preservation_policy": "verified-unchanged-audit-inputs",
        "reused_evidence_ids": sorted(reused_ids),
        "reuse_decisions": sorted(reuse_decisions, key=lambda item: item["node_id"]),
        "coverage_reuse_decisions": [{**item, "node_id": f"repair-epoch-{epoch:03d}-" + item["node_id"]} for item in coverage_reviews],
        "unaffected_node_ids": [node.node_id for node in unaffected],
        "repair_epoch": {
            "changed_paths": list(changed_paths),
            "fix_nodes": [{"mode": "fix", "node_id": fix_node_id, "serialized": True}],
            "ordinal": epoch,
            "recapture_count": 1,
        },
        "replacement_lineage": _replacement_lineage(old_plan, new_plan, sources),
        "schema_version": 1,
        "stale_evidence_ids": [
            *(_expected_evidence_id(node, old_plan) for node in old_plan.actual_worker_nodes if _expected_evidence_id(node, old_plan) not in reused_ids),
            *dict.fromkeys(evidence_id for _requirement_id, evidence_id in old_plan.exact_reused_review_evidence if evidence_id not in reused_ids),
        ],
        "status": "advanced",
    }
    return _resume_after_repair_metadata(document, result, sources) if metadata is not None else result


def _resume_after_repair_metadata(
    document: dict[str, Any], repair: dict[str, Any], sources: dict[str, tuple[dict[str, Any], dict[str, Any]]]
) -> dict[str, Any]:
    """Compose two verified transitions without synthesizing captures or changing Git."""
    history_path = Path(repair["lifecycle_input_path"]).parent / "repair-transition.json"
    history = {"previous_capture": document["previous_capture"], "historical_evidence_sources": document.get("sources", []), **repair}
    _write_text_once(history_path, json.dumps(history, indent=2, sort_keys=True) + "\n")
    resumed = resume_after_external_metadata(
        {
            **repair["lifecycle_input"],
            "previous_capture": repair["capture"],
            "new_capture": document["post_repair_capture"],
            "dispatches_path": repair["dispatches_path"],
            "journal_path": repair["journal_path"],
            "artifact_store": str(Path(repair["lifecycle_input_path"]).parent / "external-metadata"),
            "routing_catalog_path": document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG),
        }
    )
    reused_ids = {evidence_id for _requirement, evidence_id in resumed["lifecycle_input"]["plan"]["exact_reused_review_evidence"]}
    invalidated_nodes = {item["node_id"] for item in repair["preserved_evidence"] if item["evidence_id"] not in reused_ids}
    discarded_coverage = set(resumed["discarded_coverage_node_ids"])
    coverage_recheck = {
        "disposition": "recheck",
        "reason_code": "metadata-dependencies-changed",
        "reason": "External staging requires a fresh Git-sensitive judgment; see node_decisions.",
    }
    return {
        **repair,
        **{
            key: resumed[key]
            for key in (
                "lifecycle_input",
                "dispatch_set",
                "lifecycle_input_path",
                "dispatches_path",
                "journal_path",
                "capture_path",
                "current_source_state",
                "node_decisions",
            )
        },
        "new_plan": resumed["lifecycle_input"]["plan"],
        "replacement_lineage": _replacement_lineage(_graph_plan(document["plan"]), _graph_plan(resumed["lifecycle_input"]["plan"]), sources),
        "capture": document["post_repair_capture"],
        "repair_transition_path": str(history_path),
        "reused_evidence_ids": sorted(reused_ids),
        "invalidated_nodes": [
            {"node_id": node_id, "state": "awaiting-replan"}
            for node_id in sorted({item["node_id"] for item in repair["invalidated_nodes"]} | invalidated_nodes)
        ],
        "unaffected_node_ids": [node_id for node_id in repair["unaffected_node_ids"] if node_id not in invalidated_nodes],
        "reuse_decisions": [
            {
                **item,
                "disposition": "not-reused",
                "reason_code": "metadata-dependencies-changed",
                "reason": "External staging requires a fresh Git-sensitive judgment; see node_decisions.",
            }
            if item["node_id"] in invalidated_nodes
            else item
            for item in repair["reuse_decisions"]
        ],
        "coverage_reuse_decisions": [
            {**item, **coverage_recheck, "units": [{**unit, **coverage_recheck} for unit in item["units"]]} if item["node_id"] in discarded_coverage else item
            for item in repair["coverage_reuse_decisions"]
        ],
        "preserved_evidence": [item for item in repair["preserved_evidence"] if item["evidence_id"] in reused_ids],
        "stale_evidence_ids": sorted(set(repair["stale_evidence_ids"]) | (set(repair["reused_evidence_ids"]) - reused_ids)),
        "transition_kind": "repair-then-observed-external-git-metadata",
    }


def _plan_digest(plan: GraphPlan) -> str:
    return graph_plan_digest(plan)


def _expected_evidence_id(node: WorkerNode, plan: GraphPlan) -> str:
    identity = f"{'validation' if node.mode == 'validation' else 'review'}:{node.node_id}"
    unit = next((item for item in plan.coalesced_validation_units if item.node_id == node.node_id), None)
    recovery = next(
        (
            item
            for item in plan.validation_recoveries
            if item["node_id"] == node.node_id and item.get("checks_started") and unit is not None and tuple(item["source_state"]) == unit.source_state
        ),
        None,
    )
    return identity + (":" + _required_text(recovery, "attempt_id").removeprefix("validation-recovery:") if recovery is not None else "")


def _sha256_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        msg = f"{name} must be a sha256 digest"
        raise ValueError(msg)
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError:
        msg = f"{name} must be a sha256 digest"
        raise ValueError(msg) from None
    return value


def _journal_evidence(raw: object, *, plan: GraphPlan, node: WorkerNode, status: str) -> dict[str, str] | None:
    if raw is None:
        if status == "accepted":
            msg = f"accepted journal event requires verified evidence: {node.node_id}"
            raise ValueError(msg)
        return None
    if not isinstance(raw, dict) or set(raw) != _JOURNAL_EVIDENCE_KEYS:
        msg = "journal evidence record has unexpected fields"
        raise ValueError(msg)
    record = cast("dict[str, Any]", raw)
    evidence = {name: _required_text(record, name) for name in _JOURNAL_EVIDENCE_KEYS}
    _sha256_digest(evidence["artifact_digest"], "journal artifact_digest")
    _sha256_digest(evidence["normalized_record_digest"], "journal normalized_record_digest")
    expected_evidence_id = _expected_evidence_id(node, plan)
    if evidence["evidence_id"] != expected_evidence_id:
        msg = f"journal evidence ID differs from plan for {node.node_id}"
        raise ValueError(msg)
    valid_statuses = {"passed", "failed", "blocked", "reused", "not-applicable"} if node.mode == "validation" else _REVIEW_STATUSES
    if evidence["evidence_status"] not in valid_statuses:
        msg = f"journal evidence status is invalid for {node.node_id}"
        raise ValueError(msg)
    blocked_status = evidence["evidence_status"] in {"blocked", "not-applicable"}
    if status == "accepted" and blocked_status:
        msg = f"accepted journal event contains blocked evidence: {node.node_id}"
        raise ValueError(msg)
    if status == "blocked" and not blocked_status:
        msg = f"blocked journal event contains non-blocked evidence: {node.node_id}"
        raise ValueError(msg)
    if status not in {"accepted", "blocked"}:
        msg = f"{status} journal event must not contain evidence"
        raise ValueError(msg)
    return evidence


def _verified_journal_evidence(
    source: dict[str, Any], *, plan: GraphPlan, node: WorkerNode, source_state: tuple[str, str, str]
) -> tuple[dict[str, str], tuple[str, ...]]:
    kind, expectation, evidence, _content, normalized = _load_evidence_source(source, require_normalized=True)
    if normalized is None:  # Defensive for type narrowing after require_normalized.
        msg = f"journal evidence has no normalized record: {node.node_id}"
        raise ValueError(msg)
    expected_kind = "validation" if node.mode == "validation" else "review"
    if kind != expected_kind or evidence.node_id != node.node_id or evidence.evidence_id != _expected_evidence_id(node, plan):
        msg = f"journal evidence identity differs from plan for {node.node_id}"
        raise ValueError(msg)
    if expectation.source_state != source_state or evidence.fingerprints.expected != source_state:
        msg = f"journal evidence has a different source state: {node.node_id}"
        raise ValueError(msg)
    if evidence.requirement_ids != node.requirement_ids:
        msg = f"journal evidence requirements differ from plan for {node.node_id}"
        raise ValueError(msg)
    if isinstance(evidence, ReviewEvidence):
        by_id = {candidate.node_id: candidate for candidate in plan.actual_worker_nodes}
        expected_predecessors = (
            *(_expected_evidence_id(by_id[predecessor_id], plan) for predecessor_id in node.predecessors),
            *_synthesis_reused_evidence_ids(plan, node.node_id),
        )
        if (
            not isinstance(expectation, ReviewEvidenceExpectation)
            or evidence.skill_id != node.skill_id
            or evidence.mode != node.mode
            or evidence.predecessor_evidence_ids != expected_predecessors
        ):
            msg = f"journal review evidence differs from plan for {node.node_id}"
            raise ValueError(msg)
    elif isinstance(evidence, ValidationEvidence):
        units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
        unit = units.get(node.node_id)
        if not isinstance(expectation, ValidationEvidenceExpectation) or unit is None or expectation.validation_unit != unit:
            msg = f"journal validation evidence differs from plan for {node.node_id}"
            raise ValueError(msg)
    else:  # Defensive for future evidence variants.
        msg = f"journal evidence has an unsupported type for {node.node_id}"
        raise TypeError(msg)
    limitations = _review_limitation_reasons(normalized)
    record = {
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": evidence.raw_result_artifact_id,
        "evidence_id": evidence.evidence_id,
        "evidence_status": evidence.status,
        "normalized_record_digest": digest_bytes(canonical_json(normalized).encode()),
    }
    return record, limitations


def _journal_affected_nodes(plan: GraphPlan, state: dict[str, str], node_id: str) -> tuple[str, ...]:
    descendants = {node_id}
    changed = True
    while changed:
        changed = False
        for node in plan.actual_worker_nodes:
            if node.node_id not in descendants and any(predecessor in descendants for predecessor in node.predecessors):
                descendants.add(node.node_id)
                changed = True
    return tuple(
        node.node_id
        for node in plan.actual_worker_nodes
        if node.node_id == node_id or (node.node_id in descendants and state.get(node.node_id) in {"accepted", "blocked", "in-flight"})
    )


def _apply_journal_transition(plan: GraphPlan, state: dict[str, str], *, node_id: str, status: str) -> tuple[str, ...]:
    by_id = {node.node_id: node for node in plan.actual_worker_nodes}
    node = by_id.get(node_id)
    if node is None:
        msg = f"journal event references unknown node: {node_id}"
        raise ValueError(msg)
    if status not in _JOURNAL_STATUSES:
        msg = f"invalid journal status {status}"
        raise ValueError(msg)
    current = state.get(node_id)
    if status in {"awaiting-replan", "invalidated"}:
        if current not in {"accepted", "blocked", "in-flight"}:
            msg = f"cannot transition {node_id} to {status} from lifecycle state {current or 'pending'}"
            raise ValueError(msg)
        affected = _journal_affected_nodes(plan, state, node_id)
        for affected_id in affected:
            state[affected_id] = status
        return affected
    allowed_from = {None, "invalidated"} if status == "in-flight" else {None, "in-flight", "invalidated"}
    if current not in allowed_from:
        msg = f"cannot transition {node_id} from {current or 'pending'} to {status}"
        raise ValueError(msg)
    missing = tuple(predecessor for predecessor in node.predecessors if state.get(predecessor) != "accepted")
    if missing:
        msg = f"cannot transition {node_id} to {status}; missing accepted predecessors: " + ", ".join(missing)
        raise ValueError(msg)
    state[node_id] = status
    return (node_id,)


def _validated_journal_record(
    event: dict[str, Any], *, expected_sequence: int, plan: GraphPlan, source_state: tuple[str, str, str], previous_digest: str | None
) -> tuple[str, str]:
    if set(event) - {"recorded_at_unix_ns"} != _JOURNAL_EVENT_KEYS:
        msg = f"journal event {expected_sequence} has unexpected fields"
        raise ValueError(msg)
    if "recorded_at_unix_ns" in event and (type(event["recorded_at_unix_ns"]) is not int or event["recorded_at_unix_ns"] < 0):
        msg = "journal timestamp must be a nonnegative integer"
        raise ValueError(msg)
    if _required_int(event, "schema_version") != 1 or _required_int(event, "sequence") != expected_sequence:
        msg = f"journal event sequence is invalid at record {expected_sequence}"
        raise ValueError(msg)
    if not graph_plan_digest_matches(plan, _required_text(event, "plan_digest")) or _state(event, "source_state") != source_state:
        msg = f"journal event {expected_sequence} belongs to a different plan or source state"
        raise ValueError(msg)
    if event.get("previous_event_digest") != previous_digest:
        msg = f"journal event {expected_sequence} breaks the digest chain"
        raise ValueError(msg)
    node_id = _required_text(event, "node_id")
    status = _required_text(event, "status")
    node = next((candidate for candidate in plan.actual_worker_nodes if candidate.node_id == node_id), None)
    if node is None:
        msg = f"journal event references unknown node: {node_id}"
        raise ValueError(msg)
    reason = event.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip() or "\n" in reason):
        msg = f"journal event {expected_sequence} reason must be null or one non-empty line"
        raise ValueError(msg)
    requires_reason = status in {"awaiting-replan", "blocked", "invalidated"}
    if requires_reason != (reason is not None):
        requirement = "requires" if requires_reason else "must not contain"
        msg = f"{status} journal event {requirement} a reason: {node_id}"
        raise ValueError(msg)
    _journal_evidence(event.get("evidence"), plan=plan, node=node, status=status)
    return node_id, status


def _fold_execution_journal(plan: GraphPlan, source_state: tuple[str, str, str], events: tuple[dict[str, Any], ...]) -> tuple[dict[str, str], str | None]:
    state: dict[str, str] = {}
    latest: dict[str, dict[str, Any]] = {}
    previous_digest: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        node_id, status = _validated_journal_record(
            event, expected_sequence=expected_sequence, plan=plan, source_state=source_state, previous_digest=previous_digest
        )
        require_validation_barrier(plan, state, latest, node_id=node_id, status=status)
        affected = _apply_journal_transition(plan, state, node_id=node_id, status=status)
        if _text_list(event, "affected_node_ids") != affected:
            msg = f"journal event {expected_sequence} has incorrect affected nodes"
            raise ValueError(msg)
        event_digest = _sha256_digest(event.get("event_digest"), "event_digest")
        unsigned = dict(event)
        unsigned.pop("event_digest")
        if event_digest != digest_bytes(canonical_json(unsigned).encode()):
            msg = f"journal event {expected_sequence} digest does not match its content"
            raise ValueError(msg)
        previous_digest = event_digest
        latest[node_id] = event
    return state, previous_digest


def read_execution_journal(path: Path, *, plan: GraphPlan, source_state: tuple[str, str, str]) -> tuple[tuple[dict[str, Any], ...], dict[str, str], str | None]:
    """Read, validate, and fold a canonical append-only execution journal."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        content = b""
    return _read_execution_journal_content(content, path=path, plan=plan, source_state=source_state)


def _read_execution_journal_content(
    content: bytes, *, path: Path, plan: GraphPlan, source_state: tuple[str, str, str]
) -> tuple[tuple[dict[str, Any], ...], dict[str, str], str | None]:
    """Validate journal bytes already protected by the caller's file lock."""
    if content and not content.endswith(b"\n"):
        msg = f"execution journal ends with a partial record: {path}"
        raise ValueError(msg)
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            msg = f"execution journal contains a blank record at line {line_number}"
            raise ValueError(msg)
        value = json.loads(line)
        if not isinstance(value, dict):
            msg = f"execution journal record {line_number} must be an object"
            raise TypeError(msg)
        events.append(value)
    state, head_digest = _fold_execution_journal(plan, source_state, tuple(events))
    return tuple(events), state, head_digest


def _new_journal_evidence(
    request: JournalEventRequest, *, plan: GraphPlan, node: WorkerNode, source_state: tuple[str, str, str]
) -> tuple[dict[str, str] | None, tuple[str, ...]]:
    if request.source is None:
        if request.status == "accepted":
            msg = f"accepted journal event requires verified evidence: {request.node_id}"
            raise ValueError(msg)
        return None, ()
    if request.status not in {"accepted", "blocked"}:
        msg = f"{request.status} journal event must not contain evidence"
        raise ValueError(msg)
    evidence, limitations = _verified_journal_evidence(request.source, plan=plan, node=node, source_state=source_state)
    blocked_evidence = evidence["evidence_status"] in {"blocked", "not-applicable"}
    if request.status == "accepted" and blocked_evidence:
        msg = f"accepted journal event contains blocked evidence: {request.node_id}"
        raise ValueError(msg)
    if request.status == "blocked" and not blocked_evidence:
        msg = f"blocked journal event contains non-blocked evidence: {request.node_id}"
        raise ValueError(msg)
    return evidence, limitations


def _new_journal_reason(request: JournalEventRequest, limitations: tuple[str, ...]) -> str | None:
    reason = request.reason
    if request.status == "blocked" and reason is None:
        reason = "; ".join(limitations) or None
    if request.status in {"awaiting-replan", "blocked", "invalidated"}:
        if not isinstance(reason, str) or not reason.strip() or "\n" in reason:
            msg = f"{request.status} journal event requires a one-line reason: {request.node_id}"
            raise ValueError(msg)
    elif reason is not None:
        msg = f"{request.status} journal event must not contain a reason: {request.node_id}"
        raise ValueError(msg)
    return reason


def _persist_journal_event(stream: Any, path: Path, event: dict[str, Any], *, existing_size: int) -> None:
    encoded = (canonical_json(event) + "\n").encode()
    stream.seek(0, os.SEEK_END)
    if stream.tell() != existing_size:
        msg = f"execution journal changed during append: {path}"
        raise ValueError(msg)
    stream.write(encoded)
    stream.flush()
    os.fsync(stream.fileno())


def _prepare_journal_event(
    path: Path, *, plan: GraphPlan, source_state: tuple[str, str, str], request: JournalEventRequest, content: bytes
) -> tuple[dict[str, Any], int]:
    """Validate and build a journal event without committing it."""
    existing_size = len(content)
    events, state, head_digest = _read_execution_journal_content(content, path=path, plan=plan, source_state=source_state)
    node = next((candidate for candidate in plan.actual_worker_nodes if candidate.node_id == request.node_id), None)
    if node is None:
        msg = f"journal event references unknown node: {request.node_id}"
        raise ValueError(msg)
    if request.status not in _JOURNAL_STATUSES:
        msg = f"invalid journal status {request.status}"
        raise ValueError(msg)
    evidence, limitations = _new_journal_evidence(request, plan=plan, node=node, source_state=source_state)
    require_validation_barrier(plan, state, {event["node_id"]: event for event in events}, node_id=request.node_id, status=request.status)
    affected = _apply_journal_transition(plan, state, node_id=request.node_id, status=request.status)
    event: dict[str, Any] = {
        "affected_node_ids": list(affected),
        "evidence": evidence,
        "node_id": request.node_id,
        "plan_digest": events[0]["plan_digest"] if events else _plan_digest(plan),
        "previous_event_digest": head_digest,
        "reason": _new_journal_reason(request, limitations),
        "recorded_at_unix_ns": time.time_ns(),
        "schema_version": 1,
        "sequence": len(events) + 1,
        "source_state": list(source_state),
        "status": request.status,
    }
    event["event_digest"] = digest_bytes(canonical_json(event).encode())
    return event, existing_size


def append_journal_event(path: Path, document: dict[str, Any], request: JournalEventRequest) -> dict[str, Any]:
    """Append one graph-validated lifecycle event and return its canonical record."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "journal-append requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    if not path.parent.is_dir():
        msg = f"execution journal parent directory does not exist: {path.parent}"
        raise ValueError(msg)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            try:
                content = path.read_bytes()
            except FileNotFoundError:
                content = b""
            event, existing_size = _prepare_journal_event(path, plan=plan, source_state=source_state, request=request, content=content)
            with path.open("ab") as journal_stream:
                _persist_journal_event(journal_stream, path, event, existing_size=existing_size)
            return event
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def _dispatches_by_node(dispatch_set: dict[str, Any], *, plan: GraphPlan, source_state: tuple[str, str, str]) -> dict[str, dict[str, Any]]:  # noqa: C901
    _verify_validation_recoveries(plan)
    if _required_int(dispatch_set, "schema_version") != 1:
        msg = "dispatch set has an unsupported schema version"
        raise ValueError(msg)
    if not graph_plan_digest_matches(plan, _required_text(dispatch_set, "plan_digest")) or _state(dispatch_set, "source_state") != source_state:
        msg = "dispatch set belongs to a different plan or source state"
        raise ValueError(msg)
    expected_digest = _required_text(dispatch_set, "dispatch_set_digest")
    unsigned = dict(dispatch_set)
    unsigned.pop("dispatch_set_digest")
    if expected_digest != digest_bytes(canonical_json(unsigned).encode()):
        msg = "dispatch set digest does not match its content"
        raise ValueError(msg)
    entries: dict[str, dict[str, Any]] = {}
    for entry in _records(dispatch_set, "dispatches"):
        node_id = _required_text(entry, "node_id")
        dispatch = entry.get("dispatch")
        if node_id in entries or not isinstance(dispatch, dict) or dispatch.get("node_id") != node_id:
            msg = f"dispatch set has an invalid or duplicate node entry: {node_id}"
            raise ValueError(msg)
        if "worker_input_path" in entry:
            worker_input = Path(_required_text(entry, "worker_input_path"))
            expected_input = (json.dumps(entry, indent=2, sort_keys=True) + "\n").encode()
            if _read_regular_file_no_follow(worker_input) != expected_input:
                msg = f"worker input differs from its materialized dispatch: {node_id} ({worker_input})"
                raise ValueError(msg)
        planned_coverage = next((context for context in plan.audit_delta_reviews if context["node_id"] == node_id), None)
        coverage = dispatch.get("coverage_reuse")
        if (None if coverage is None else _coverage_proof(coverage)) != planned_coverage:
            msg = f"dispatch coverage proof differs from its bound plan: {node_id}"
            raise ValueError(msg)
        shared = dispatch.get("shared_inspection_evidence")
        if isinstance(shared, dict) and "source_packet_path" in shared:
            packet = _read_regular_file_no_follow(Path(_required_text(shared, "source_packet_path")))
            if digest_bytes(packet) != _required_text(shared, "source_packet_digest"):
                msg = f"shared source packet differs from its materialized identity: {node_id}"
                raise ValueError(msg)
        entries[node_id] = entry
    expected_node_ids = {node.node_id for node in plan.actual_worker_nodes}
    if set(entries) != expected_node_ids:
        msg = "dispatch set does not contain exactly the planned nodes"
        raise ValueError(msg)
    return entries


def _explicit_synthesis_reuse_sources(
    plan: GraphPlan, source_state: tuple[str, str, str], entries: dict[str, dict[str, Any]]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Verify same-state source bindings for journal-driven consumers too."""
    reused_ids = {evidence_id for _requirement, evidence_id in plan.exact_reused_review_evidence}
    reused_ids -= {transition.evidence_id for transition in plan.audit_reuse_transitions}
    sources = []
    for source in _continuation_synthesis_sources(entries):
        _kind, expectation, evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if evidence.evidence_id not in reused_ids:
            continue
        if not isinstance(evidence, ReviewEvidence) or evidence.mode != "audit" or evidence.status not in {"completed", "no-findings"}:
            msg = "explicit synthesis reuse requires completed audit evidence"
            raise ValueError(msg)
        if expectation.source_state != source_state:
            msg = "explicit synthesis reuse requires the same source state or a planner-bound audit reuse transition"
            raise ValueError(msg)
        if record is not None:
            sources.append((source, record))
    return sources


def _accepted_journal_sources(
    plan: GraphPlan,
    source_state: tuple[str, str, str],
    events: tuple[dict[str, Any], ...],
    entries: dict[str, dict[str, Any]],
    *,
    include_blocked: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    state, _head = _fold_execution_journal(plan, source_state, events)
    latest = {str(event["node_id"]): event for event in events}
    sources: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for node in plan.actual_worker_nodes:
        status = state.get(node.node_id)
        if status != "accepted" and not (include_blocked and status == "blocked" and latest[node.node_id]["evidence"] is not None):
            continue
        entry = entries[node.node_id]
        source = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}
        verified, _limitations = _verified_journal_evidence(source, plan=plan, node=node, source_state=source_state)
        if verified != latest[node.node_id]["evidence"]:
            msg = f"{status} artifact differs from journal: {node.node_id}"
            raise ValueError(msg)
        _kind, _expectation, _evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if record is not None:
            records.append(record)
        sources[node.node_id] = source
    for source in _verified_reused_sources(plan, source_state):
        _kind, _expectation, _evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if record is not None:
            records.append(record)
    for source, record in _explicit_synthesis_reuse_sources(plan, source_state, entries):
        sources[record["node_id"]] = source
        records.append(record)
    return sources, records


def next_ready_nodes(document: dict[str, Any], *, journal_events: tuple[dict[str, Any], ...], dispatch_set: dict[str, Any]) -> dict[str, Any]:
    """Return only dependency-ready dispatches from a verified execution journal."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "next-ready requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    current_source_state = _state(document, "current_source_state")
    if current_source_state != _current_metadata_state(document):
        msg = "next-ready current recapture differs from the plan-bound source state"
        raise ValueError(msg)
    reused_sources = _verified_reused_sources(plan, source_state)
    state, head_digest = _fold_execution_journal(plan, source_state, journal_events)
    dispatches = _dispatches_by_node(dispatch_set, plan=plan, source_state=source_state)
    _sources, records = _accepted_journal_sources(plan, source_state, journal_events, dispatches)
    validation_reconciliation = _validation_reconciliation(plan, records)
    metadata_blockers = _metadata_evidence_blockers(document, records)
    accepted = {node_id for node_id, lifecycle in state.items() if lifecycle == "accepted"}
    blocked = {node_id for node_id, lifecycle in state.items() if lifecycle == "blocked"}
    invalidated = {node_id for node_id, lifecycle in state.items() if lifecycle == "invalidated"}
    awaiting_replan = {node_id for node_id, lifecycle in state.items() if lifecycle == "awaiting-replan"}
    in_flight = {node_id for node_id, lifecycle in state.items() if lifecycle == "in-flight"}
    latest = {event["node_id"]: event for event in journal_events}
    blockers = ["blocked nodes prevent completion: " + ", ".join(sorted(blocked))] if blocked else []
    blockers.extend(validation_reconciliation["blockers"])
    blockers.extend(metadata_blockers)
    failed_early = [
        node_id for node_id in plan.pre_review_validation_nodes if (latest.get(node_id, {}).get("evidence") or {}).get("evidence_status") == "failed"
    ]
    if failed_early:
        blockers.append("pre-review validation failed: " + ", ".join(failed_early))
    pending_validation = sorted(
        {item["validation_unit_id"] for item in validation_reconciliation["requirements"] if item["resolution"] == "planned"} - accepted
    )
    if awaiting_replan:
        blockers.append("source mutation requires a fresh plan: " + ", ".join(sorted(awaiting_replan)))
    ready: list[str] = []
    waiting: list[dict[str, Any]] = []
    for node in plan.actual_worker_nodes:
        if node.node_id in accepted | awaiting_replan | blocked | in_flight:
            continue
        barrier = pending_validation_barrier(plan, state, latest, node.node_id)
        if barrier:
            waiting.append({"node_id": node.node_id, "pre_review_validation_blockers": list(barrier)})
            continue
        if node.mode == "synthesis" and (validation_reconciliation["blockers"] or pending_validation):
            waiting.append({"node_id": node.node_id, "validation_blockers": validation_reconciliation["blockers"], "missing_validators": pending_validation})
            continue
        missing = tuple(predecessor for predecessor in node.predecessors if predecessor not in accepted)
        if missing:
            waiting.append({"missing_predecessors": list(missing), "node_id": node.node_id})
        else:
            ready.append(node.node_id)
    node_ids = {node.node_id for node in plan.actual_worker_nodes}
    complete = not blockers and accepted == node_ids
    return {
        "blockers": blockers,
        "complete": complete,
        "journal": {"event_count": len(journal_events), "head_digest": head_digest, "plan_digest": _plan_digest(plan), "source_state": list(source_state)},
        "lifecycle": {
            "accepted_node_ids": sorted(accepted),
            "awaiting_replan_node_ids": sorted(awaiting_replan),
            "blocked_node_ids": sorted(blocked),
            "in_flight_node_ids": sorted(in_flight),
            "invalidated_node_ids": sorted(invalidated),
        },
        "ready_dispatches": [dispatches[node_id] for node_id in ready],
        "ready_node_ids": ready,
        "reused_evidence_ids": [item.evidence_id for item in plan.audit_reuse_transitions],
        "reused_sources": list(reused_sources),
        "schema_version": 1,
        **({"phase_accounting": phase_accounting(plan, journal_events, dispatches)} if plan.pre_review_validation_nodes else {}),
        "validation_reconciliation": validation_reconciliation,
        "waiting": waiting,
    }


def _coordinator_lane_entry(original: dict[str, Any], store: Path, pending: dict[Path, tuple[bytes, int]]) -> dict[str, Any]:
    """Rebind an unstarted adaptive node and its preflight, preserving outputs."""
    if any(
        Path(original[field]).exists(follow_symlinks=False)
        for field in ("artifact_path", "metadata_path", "worker_payload_path", "worker_payload_candidate_path")
        if field in original
    ):
        msg = f"coordinator lane node already has execution output: {original['node_id']}"
        raise ValueError(msg)
    entry = json.loads(canonical_json(original))
    node_id = entry["node_id"]
    entry["worker_input_path"] = str(store / f"{node_id}.worker-input.json")
    contract_path = store / f"{node_id}.worker-payload-contract.json"
    entry["worker_payload_contract_path"] = str(contract_path)
    dispatch = entry["dispatch"]
    dispatch.update({"execution_location": "coordinator", "worker_created": False, "fresh_context": False})
    persistence = dispatch["worker_payload_persistence"]
    persistence["input_path"] = str(contract_path)
    for field in ("command", "review_command", "publish_command"):
        command = persistence[field]
        command[command.index("--input") + 1] = str(contract_path)
    entry["worker_prompt"] = _worker_prompt(entry["result_contract"], dispatch)
    entry_bytes = (json.dumps(entry, indent=2, sort_keys=True) + "\n").encode()
    contract = _read_json_object(Path(original["worker_payload_contract_path"]))
    if "compiler_preflight" in contract:
        contract["compiler_preflight"] = {"worker_input_path": entry["worker_input_path"], "digest": digest_bytes(entry_bytes)}
    _queue_materialized_write(pending, Path(entry["worker_input_path"]), entry_bytes, mode=0o444)
    _queue_materialized_write(pending, contract_path, (json.dumps(contract, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)
    return entry


def schedule_ready(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Publish one capacity-aware adaptive schedule and immutable continuation."""
    lock_path = args.journal.with_name(args.journal.name + ".lock")
    with lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            return _schedule_ready_locked(document, args)
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _schedule_ready_locked(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    plan = _graph_plan(document["plan"])
    if plan.execution_profile not in {"grouped", "mixed"}:
        msg = "schedule-ready requires an adaptive grouped or mixed profile"
        raise ValueError(msg)
    current = _with_current_capture(document, args.current_capture)
    source_state = _state(document, "source_state")
    events, _state_view, head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    dispatch_set = _read_json_object(args.dispatches)
    ready = next_ready_nodes(current, journal_events=events, dispatch_set=dispatch_set)
    entries = {entry["node_id"]: entry for entry in dispatch_set["dispatches"]}
    selection = select_execution_lanes(document, modes={node.node_id: node.mode for node in plan.actual_worker_nodes}, entries=entries, ready=ready)
    identity = digest_bytes(
        canonical_json({"input": document, "previous_dispatch_set_digest": dispatch_set["dispatch_set_digest"], "journal_head": head}).encode()
    )
    store = Path(_required_text(document, "artifact_store")).resolve() / f"schedule-{identity[7:23]}"
    pending: dict[Path, tuple[bytes, int]] = {}
    coordinator_id = selection["coordinator_node_id"]
    lineage = {
        "previous_dispatch_set_digest": dispatch_set["dispatch_set_digest"],
        "previous_dispatches_path": str(args.dispatches.resolve()),
        "journal_head": head,
        "scheduling_input": document,
    }
    if coordinator_id is not None and entries[coordinator_id]["dispatch"]["execution_location"] == "worker":
        entries[coordinator_id] = _coordinator_lane_entry(entries[coordinator_id], store, pending)
        dispatch_set = {**dispatch_set, "dispatches": [entries[entry["node_id"]] for entry in dispatch_set["dispatches"]], "scheduling_lineage": lineage}
        dispatch_set.pop("dispatch_set_digest")
        dispatch_set["dispatch_set_digest"] = digest_bytes(canonical_json(dispatch_set).encode())
    lifecycle = {
        key: value
        for key, value in document.items()
        if key not in {"artifact_store", "worker_capacity", "creation_failure", "reserved_node_ids", "preflight_blocked_nodes"}
    }
    paths = {
        "dispatches_path": str(store / "dispatches.json"),
        "lifecycle_input_path": str(store / "lifecycle.json"),
        "schedule_input_path": str(store / "schedule-input.json"),
        "journal_path": str(args.journal.resolve()),
        "current_capture_path": str(args.current_capture.resolve()),
    }
    selected_ids = [*selection["worker_node_ids"], *([coordinator_id] if coordinator_id is not None else [])]
    schedule_input = {
        **lifecycle,
        "artifact_store": document["artifact_store"],
        "reserved_node_ids": selection["reserved_node_ids"],
        "preflight_blocked_nodes": selection["preflight_blocked_nodes"],
    }
    failure = selection["creation_failure"]
    if failure is not None and failure["node_id"] not in selected_ids:
        schedule_input["creation_failure"] = failure
    result = {
        **ready,
        **selection,
        **paths,
        "status": "scheduled" if selected_ids else "waiting",
        "ready_node_ids": selected_ids,
        "ready_dispatches": [entries[node_id] for node_id in selected_ids],
        "lineage": lineage,
        "continuation_path": str(store / "continuation.json"),
    }
    for filename, content in (
        ("dispatches.json", dispatch_set),
        ("lifecycle.json", lifecycle),
        ("schedule-input.json", schedule_input),
        ("continuation.json", {**paths, **selection, "lineage": lineage}),
    ):
        _queue_materialized_write(pending, store / filename, (json.dumps(content, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)
    _publish_materialization_with_result(store, pending, args.output, result)
    return result


def fallback_to_coordinator(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Publish one unstarted adaptive fallback while preserving the current journal."""
    lock_path = args.journal.with_name(args.journal.name + ".lock")
    with lock_path.open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            return _fallback_to_coordinator_locked(document, args)
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def _fallback_to_coordinator_locked(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    plan = _graph_plan(document["plan"])
    source_state = _state(document, "source_state")
    current_state = _current_metadata_state(document)
    if _capture_source_state(args.current_capture) != current_state:
        msg = "fallback current capture differs from plan-bound source state"
        raise ValueError(msg)
    if plan.execution_profile not in {"grouped", "mixed"} or document.get("worker_created") is not False:
        msg = "coordinator fallback requires an adaptive profile and worker_created=false"
        raise ValueError(msg)
    reason = _required_text(document, "reason")
    node_id = _required_text(document, "node_id")
    events, state, head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    dispatch_set = _read_json_object(args.dispatches)
    entries = _dispatches_by_node(dispatch_set, plan=plan, source_state=source_state)
    _sources, records = _accepted_journal_sources(plan, source_state, events, entries, include_blocked=True)
    if blockers := _metadata_evidence_blockers(document, records):
        raise ValueError("; ".join(blockers))
    if node_id not in entries or node_id in state:
        msg = "fallback requires a planned node with no prior execution or lifecycle event"
        raise ValueError(msg)
    ready = next_ready_nodes({**document, "current_source_state": list(current_state)}, journal_events=events, dispatch_set=dispatch_set)
    if node_id not in ready["ready_node_ids"]:
        msg = f"fallback node is not dependency-ready: {node_id}"
        raise ValueError(msg)
    original = entries[node_id]
    if original["dispatch"]["execution_location"] != "worker":
        msg = f"fallback node is not assigned to a worker: {node_id}"
        raise ValueError(msg)
    identity = digest_bytes(canonical_json({"dispatch_set_digest": dispatch_set["dispatch_set_digest"], "node_id": node_id, "journal_head": head}).encode())
    store = Path(_required_text(document, "artifact_store")).resolve() / f"fallback-{identity[7:23]}"
    pending: dict[Path, tuple[bytes, int]] = {}
    entry = _coordinator_lane_entry(original, store, pending)
    updated = {**dispatch_set, "dispatches": [entry if item["node_id"] == node_id else item for item in dispatch_set["dispatches"]]}
    updated.pop("dispatch_set_digest")
    updated["dispatch_set_digest"] = digest_bytes(canonical_json(updated).encode())
    lifecycle = {"plan": document["plan"], "source_state": list(source_state)}
    if "external_metadata_transitions" in document:
        lifecycle["external_metadata_transitions"] = document["external_metadata_transitions"]
    dispatches_path = store / "dispatches.json"
    lifecycle_path = store / "lifecycle.json"
    for path, content in ((dispatches_path, updated), (lifecycle_path, lifecycle)):
        _queue_materialized_write(pending, path, (json.dumps(content, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)
    _publish_materialized_writes(store, pending)
    return {
        "schema_version": 1,
        "status": "transitioned",
        "node_id": node_id,
        "execution_location": "coordinator",
        "worker_created": False,
        "reason": reason,
        "source_state": list(source_state),
        "dispatches_path": str(dispatches_path),
        "lifecycle_input_path": str(lifecycle_path),
        "journal_path": str(args.journal.resolve()),
        "worker_input_path": entry["worker_input_path"],
        "lineage": {"previous_dispatch_set_digest": dispatch_set["dispatch_set_digest"], "journal_head": head},
    }


def _late_validation_quality_blockers(requirement: ValidationRequirement, *, repository_root: Path, authorization: str) -> tuple[str, ...]:  # noqa: C901, PLR0912
    """Reject audit-authored proof obligations that cannot validate the captured epoch."""
    blockers: list[str] = []
    recipes = benchmark_recipes(repository_root)
    cargo_manifest = repository_root / "Cargo.toml"
    benches: dict[str, set[str]] = {}
    if cargo_manifest.is_file():
        manifest = tomllib.loads(cargo_manifest.read_text(encoding="utf-8"))
        for raw in manifest.get("bench", []):
            if isinstance(raw, dict) and isinstance(raw.get("name"), str):
                required = raw.get("required-features", [])
                if isinstance(required, list) and all(isinstance(item, str) for item in required):
                    benches[raw["name"]] = set(cast("list[str]", required))
    for command in requirement.commands:
        identity = benchmark_identity(command)
        if identity is None:
            continue
        for target in identity.targets:
            required = benches.get(target, set())
            canonical_name = f"bench-{target.replace('_', '-')}"
            recipe = recipes.get(canonical_name)
            missing = [] if identity.all_features else sorted(required - identity.features)
            if missing:
                detail = f"cargo benchmark target {target} is missing required features: {', '.join(missing)}"
                if recipe is not None:
                    detail += f"; inspect the repository canonical recipe just {canonical_name}"
                blockers.append(detail)
            elif recipe is not None and (canonical := equivalent_recipe(identity, recipe, canonical_name)) is not None:
                if command != canonical or requirement.canonical_recipe != canonical:
                    blockers.append(f"cargo benchmark target {target} must use the repository canonical recipe {canonical}")
    if not requirement.requires_isolation:
        blockers.extend(
            f"working directory does not exist in the captured current state: {directory}"
            for directory in requirement.working_directories
            if not Path(directory).is_dir()
        )
    epoch_text = f"{requirement.request} {requirement.selection_reason} {requirement.expected_evidence}"
    post_remediation = r"\b(?:post[- ]remediation|(?:after|following|once)\s+(?:the\s+)?(?:remediation|repair|fix(?:es|ed)?))\b"
    if authorization == "review-only" and re.search(post_remediation, epoch_text, re.IGNORECASE):
        blockers.append("review-only late validation cannot require post-remediation evidence from the unchanged source epoch")
    return tuple(blockers)


def _software_doi_recheck_ids(document: dict[str, Any], records: list[dict[str, Any]], additions: tuple[ValidationRequirement, ...]) -> set[str]:
    """Bind requested canonical follow-ups to accepted failed executions."""
    doi_rechecks = _records(document, "software_doi_rechecks")
    recheck_ids: set[str] = set()
    for recheck in doi_rechecks:
        requirement_id = _required_text(recheck, "requirement_id")
        original = next((record for record in records if record["evidence_id"] == recheck["evidence_id"]), None)
        addition = next((item for item in additions if item.requirement_id == requirement_id), None)
        if original is None or addition is None or requirement_id in recheck_ids or len(addition.commands) != 1 or len(addition.working_directories) != 1:
            msg = "software DOI recheck requires accepted original evidence and one new canonical command"
            raise ValueError(msg)
        inspect_canonical_recheck(original, recheck, addition.commands[0], addition.working_directories[0])
        recheck_ids.add(requirement_id)
    return recheck_ids


def _expanded_validation_plan(
    document: dict[str, Any], plan: GraphPlan, records: list[dict[str, Any]], repository_root: Path, *, authorization: str
) -> GraphPlan:
    reconciliation = _validation_reconciliation(plan, records)
    pending = {item["requirement_id"] for item in reconciliation["requirements"] if item["resolution"] != "planned"}
    raw_requirements = _records(document, "validation_requirements")
    for raw in raw_requirements:
        require_schema_definition(raw, _PLANNING_INPUT_SCHEMA, "validationRequirement")
    additions = validation_requirements_from_document({"validation_requirements": list(raw_requirements)}, repository_root)
    pending.update(_software_doi_recheck_ids(document, records, additions))
    existing = {requirement for unit in plan.coalesced_validation_units for requirement in unit.requirement_ids}
    source_state = _state(document, "source_state")
    for item in additions:
        quality_blockers = _late_validation_quality_blockers(item, repository_root=repository_root, authorization=authorization)
        if quality_blockers:
            msg = f"late validation requirement {item.requirement_id} failed quality gate: " + "; ".join(quality_blockers)
            raise ValueError(msg)
        if item.requirement_id not in pending or item.requirement_id in existing or item.source_state != source_state or not item.required:
            msg = f"late validation must be a new, required, source-matching discovered identity: {item.requirement_id}"
            raise ValueError(msg)
    units, mappings = coalesce_validation_requirements(additions, reserved_node_ids=tuple(node.node_id for node in plan.actual_worker_nodes))
    exclusions = list(plan.validation_exclusions)
    discoveries = {(item["originating_evidence_id"], item["requirement_id"], item["requirement_digest"]): item for item in reconciliation["requirements"]}
    for raw in _records(document, "user_exclusions"):
        exclusion = ValidationExclusion(
            _required_text(raw, "originating_evidence_id"),
            _required_text(raw, "requirement_id"),
            _sha256_digest(raw.get("requirement_digest"), "requirement_digest"),
            _required_text(raw, "reason"),
        )
        if (exclusion.originating_evidence_id, exclusion.requirement_id, exclusion.requirement_digest) not in discoveries:
            msg = "user exclusion does not name an exact accepted validation requirement"
            raise ValueError(msg)
        if exclusion not in exclusions:
            exclusions.append(exclusion)
    validator = next((node for node in plan.actual_worker_nodes if node.mode == "validation"), None)
    if validator is None:
        msg = "validation expansion requires the existing baseline validator"
        raise ValueError(msg)
    added_nodes = _validation_nodes(units, skill_path=validator.skill_path, skill_digest=validator.skill_digest, reference_digests=validator.reference_digests)
    nodes = _schedule_with_validation_barrier(
        (
            *(
                replace(node, predecessors=(*node.predecessors, *(unit.node_id for unit in units))) if node.mode == "synthesis" else node
                for node in plan.actual_worker_nodes
            ),
            *added_nodes,
        ),
        plan.pre_review_validation_nodes,
    )
    epochs = _partition_execution_epochs(nodes, WorkerBudget(plan.worker_budget, plan.recovery_finalization_reserve)) if plan.execution_epochs else ()
    expanded = replace(
        plan,
        actual_worker_nodes=nodes,
        complete_node_count=len(nodes),
        coalesced_validation_units=(*plan.coalesced_validation_units, *units),
        selected_validation_units=(*plan.selected_validation_units, *(unit.node_id for unit in units)),
        validation_evidence_mapping=(*plan.validation_evidence_mapping, *mappings),
        validation_exclusions=tuple(exclusions),
        execution_epochs=epochs,
        current_epoch_node_ids=epochs[0].node_ids if epochs else tuple(node.node_id for node in nodes),
        requires_continuation=len(epochs) > 1,
    )
    remaining = _validation_reconciliation(expanded, records)
    if remaining["blockers"]:
        msg = "validation expansion leaves unresolved identities: " + "; ".join(remaining["blockers"])
        raise ValueError(msg)
    return expanded


def reconcile_validation_requirements(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Inspect late requirements or publish a source-preserving plan revision."""
    plan = _graph_plan(document["plan"])
    source_state = _state(document, "source_state")
    if _capture_source_state(args.current_capture) != _current_metadata_state(document):
        msg = "validation reconciliation current capture differs from plan-bound source state"
        raise ValueError(msg)
    events, state, head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=source_state)
    sources, records = _accepted_journal_sources(plan, source_state, events, entries)
    if blockers := _metadata_evidence_blockers(document, records):
        raise ValueError("; ".join(blockers))
    reconciliation = _validation_reconciliation(plan, records)
    if document.get("software_doi_rechecks") and not document.get("validation_requirements"):
        msg = "software DOI rechecks require new canonical validation requirements"
        raise ValueError(msg)
    if not document.get("validation_requirements") and not document.get("user_exclusions"):
        return {"schema_version": 1, "status": "requires-expansion" if reconciliation["blockers"] else "resolved", **reconciliation}
    if any(status in {"in-flight", "blocked", "awaiting-replan"} for status in state.values()):
        msg = "validation expansion requires quiescent execution without blocked or source-mutated nodes; preserve the current dispatches and journal"
        raise ValueError(msg)
    first_entry = next(iter(entries.values()), None)
    if first_entry is None:
        msg = "validation expansion requires an existing dispatch"
        raise ValueError(msg)
    sample = first_entry["dispatch"]
    expanded = _expanded_validation_plan(document, plan, records, Path(sample["repository_root"]), authorization=_required_text(sample, "authorization"))
    if expanded == plan:
        return {"schema_version": 1, "status": "resolved", **reconciliation}
    return _publish_validation_continuation(document, args, plan, expanded, entries, sources, records, head, status="expanded", journal_events=events)


def _publish_validation_continuation(  # noqa: PLR0913, PLR0917
    document: dict[str, Any],
    args: argparse.Namespace,
    plan: GraphPlan,
    expanded: GraphPlan,
    entries: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
    head: str | None,
    *,
    status: str,
    journal_events: tuple[dict[str, Any], ...],
    replaced_node_id: str | None = None,
) -> dict[str, Any]:
    """Publish a continuation, preserving verified acceptance and unrelated blocks."""
    source_state = _state(document, "source_state")
    first_entry = next(iter(entries.values()), None)
    if first_entry is None:
        msg = "validation continuation requires an existing dispatch"
        raise ValueError(msg)
    sample = first_entry["dispatch"]
    store = Path(_required_text(document, "artifact_store")).resolve() / f"validation-{status}-{_plan_digest(expanded)[7:23]}"
    state, _head = _fold_execution_journal(plan, source_state, journal_events)
    latest = {event["node_id"]: event for event in journal_events}
    retained = {
        node.node_id: entries[node.node_id]
        for node in plan.actual_worker_nodes
        if state.get(node.node_id) in {"accepted", "blocked"} and node.node_id != replaced_node_id and node.mode != "synthesis"
    }
    dispatches = materialize_dispatches(
        {
            "artifact_store": str(store / "artifacts"),
            "authorization": sample["authorization"],
            "plan": json.loads(canonical_json(asdict(expanded))),
            "repository_root": sample["repository_root"],
            "source_state": list(source_state),
            "external_metadata_transitions": document.get("external_metadata_transitions", []),
            "state_verification_command": sample["state_verification_command"],
            "sources": _continuation_synthesis_sources(entries),
        },
        preserved_entries=retained,
    )
    lifecycle = {"plan": json.loads(canonical_json(asdict(expanded))), "source_state": list(source_state)}
    if "external_metadata_transitions" in document:
        lifecycle["external_metadata_transitions"] = document["external_metadata_transitions"]
    # Rebind verified states to the new plan, preserving every original artifact.
    # Publish this journal once; never append to or rewrite the historical journal.
    migrated: list[dict[str, Any]] = []
    migrated_state: dict[str, str] = {}
    for node in expanded.actual_worker_nodes:
        if node.node_id not in retained:
            continue
        previous = latest[node.node_id]
        evidence = None
        if previous["evidence"] is not None:
            evidence, _limitations = _verified_journal_evidence(sources[node.node_id], plan=expanded, node=node, source_state=source_state)
        affected = _apply_journal_transition(expanded, migrated_state, node_id=node.node_id, status=previous["status"])
        event: dict[str, Any] = {
            "affected_node_ids": list(affected),
            "evidence": evidence,
            "node_id": node.node_id,
            "plan_digest": _plan_digest(expanded),
            "previous_event_digest": migrated[-1]["event_digest"] if migrated else None,
            "reason": previous["reason"],
            "schema_version": 1,
            "sequence": len(migrated) + 1,
            "source_state": list(source_state),
            "status": previous["status"],
            **({"recorded_at_unix_ns": previous["recorded_at_unix_ns"]} if "recorded_at_unix_ns" in previous else {}),
        }
        event["event_digest"] = digest_bytes(canonical_json(event).encode())
        migrated.append(event)
    paths = {
        "dispatches_path": store / "dispatches.json",
        "lifecycle_input_path": store / "lifecycle.json",
        "journal_path": store / "execution.jsonl",
        "current_capture_path": store / "capture.json",
    }
    continuation = {**{key: str(path) for key, path in paths.items()}, "next_ready_output_dir": str(store / "ready")}
    # Publish the manifest last: partial progress is retryable, never a complete continuation.
    outputs = {
        paths["dispatches_path"]: (json.dumps(dispatches, indent=2, sort_keys=True) + "\n").encode(),
        paths["lifecycle_input_path"]: (json.dumps(lifecycle, indent=2, sort_keys=True) + "\n").encode(),
        paths["journal_path"]: "".join(canonical_json(event) + "\n" for event in migrated).encode(),
        paths["current_capture_path"]: _read_regular_file_no_follow(args.current_capture),
        store / "continuation.json": (json.dumps(continuation, indent=2, sort_keys=True) + "\n").encode(),
    }
    for path, content in outputs.items():
        _write_bytes_atomically_once(path, content, mode=0o600 if path == paths["journal_path"] else 0o444)
    return {
        "schema_version": 1,
        "status": status,
        "source_state": list(source_state),
        "lifecycle_input": lifecycle,
        **{key: str(path) for key, path in paths.items()},
        "continuation": continuation,
        "continuation_path": str(store / "continuation.json"),
        "retained_node_ids": sorted(retained),
        "superseded_synthesis_node_ids": [node.node_id for node in plan.actual_worker_nodes if node.mode == "synthesis"],
        "lineage": {"previous_plan_digest": _plan_digest(plan), "previous_journal_head": head, "previous_journal_path": str(args.journal.resolve())},
        "validation_reconciliation": _validation_reconciliation(expanded, records),
    }


def _verify_validation_recoveries(plan: GraphPlan) -> None:
    """Keep every failed attempt available and bound to its revision."""
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for recovery in plan.validation_recoveries:
        identity = (_required_text(recovery, "node_id"), _text_list(recovery, "source_state", required=True))
        if identity in seen:
            msg = "validation recovery budget exhausted for this node and source state"
            raise ValueError(msg)
        seen.add(identity)
        for artifact in _records(recovery, "preserved_files"):
            content = _read_regular_file_no_follow(Path(_required_text(artifact, "path")))
            if digest_bytes(content) != _required_text(artifact, "digest"):
                msg = "preserved validation recovery evidence changed"
                raise ValueError(msg)


def _preflight_executor(unit: ValidationUnit, prerequisite: dict[str, Any] | None, repository_root: Path) -> tuple[dict[str, Any], list[str]]:
    observations: dict[str, Any] = {"host_executables": [], "uv_projects": []}
    if not unit.commands:
        return observations, []
    blockers: list[str] = []
    if prerequisite is None:
        blockers.append("executor/native availability has not been inspected for this unit")
    else:
        permissions = executor_permissions(unit.features)
        if prerequisite.get("sandbox_permissions", "use_default") != permissions:
            blockers.append(f"executor permission requirement not selected: sandbox_permissions={permissions}")
        if not prerequisite["native_available"]:
            blockers.append("native environment unavailable: " + prerequisite["reason"])
        if not prerequisite["executables"]:
            blockers.append("executor executables have not been declared for this command-bearing unit")
        # Explicit contexts avoid pretending that shell parsing finds nested tools.
        observations, executable_blockers = inspect_executor_executables(prerequisite, repository_root)
        blockers.extend(executable_blockers)
    blockers.extend(
        f"executor working directory unavailable: {directory}"
        for directory in unit.working_directories
        if not _workspace_path(directory, repository_root).is_dir()
    )
    return observations, blockers


def _preflight_outputs(unit: ValidationUnit, repository_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    observations: list[dict[str, Any]] = []
    blockers: list[str] = []
    approved = {artifact.path: artifact for artifact in unit.allowed_artifacts}
    effect_root = Path(unit.isolation_root) if unit.requires_isolation and unit.isolation_root is not None else repository_root
    for path in dict.fromkeys((*unit.expected_workspace_effects, *approved)):
        try:
            resolved = _workspace_path(path, effect_root if path in unit.expected_workspace_effects else repository_root)
            if not resolved.is_relative_to(repository_root) or (unit.requires_isolation and path in unit.expected_workspace_effects):
                _verified_artifact_status(str(resolved), "outside-repository", repository_root, unit.isolation_root)
            status = _git_path_status(repository_root, resolved)
            exists = resolved.exists() or resolved.is_symlink()
        except (ExecutableNotFoundError, OSError, ValueError, subprocess.SubprocessError) as error:
            blockers.append(f"cannot inspect output {path}: {format_exception_diagnostics(error)}")
            continue
        observations.append(
            {"path": path, "exists": exists, "repository_status": status, "required": path in approved and approved[path].artifact_digest is not None}
        )
        if status not in {"ignored", "outside-repository"}:
            blockers.append(f"expected_workspace_effects must name concrete ignored/output paths, not prose or source files: {path} ({status})")
        if path in approved and status != approved[path].repository_status:
            blockers.append(f"permitted output status differs from plan: {path}")
    return observations, blockers


def preflight_validation(document: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Inspect launch prerequisites without running recipes or changing the plan."""
    require_schema_definition(document, _RUNTIME_OPERATION_INPUT_SCHEMA, "preflight-validation")
    plan = _graph_plan(document["plan"])
    repository_root = Path(_required_text(document, "repository_root"))
    if not repository_root.is_absolute() or not repository_root.is_dir():
        msg = "preflight repository_root must be an existing absolute directory"
        raise ValueError(msg)
    repository_root = repository_root.resolve()
    policy = {item["command"]: item for item in _records(document, "command_policy")}
    if len(policy) != len(document["command_policy"]):
        msg = "preflight command policy contains duplicate commands"
        raise ValueError(msg)
    prerequisites = {item["node_id"]: item for item in _records(document, "execution_prerequisites")}
    if len(prerequisites) != len(document.get("execution_prerequisites", [])) or set(prerequisites) - {
        unit.node_id for unit in plan.coalesced_validation_units
    }:
        msg = "execution_prerequisites must name unique planned validation nodes"
        raise ValueError(msg)
    cache_checks: list[dict[str, Any]] = []
    for raw in _text_list(document, "cache_paths"):
        path = _workspace_path(raw, repository_root)
        ancestor = path
        try:
            while not ancestor.exists() and ancestor.parent != ancestor:
                ancestor = ancestor.parent
            # Test traversal in this process, not just mode bits; sandbox denial
            # can differ from os.access. Never create or delete a cache entry.
            with os.scandir(ancestor) as entries:
                next(entries, None)
            accessible = os.access(ancestor, os.R_OK | os.W_OK | os.X_OK)
            reason = "read/traversal succeeded; write mode available" if accessible else "cache parent is not writable/traversable"
        except OSError as error:
            accessible, reason = False, str(error)
        cache_checks.append({"path": str(path), "accessible": accessible, "evidence": reason})
    units: list[dict[str, Any]] = []
    for unit in plan.coalesced_validation_units:
        blockers = [unit.planning_blocker] if unit.planning_blocker is not None else []
        if not unit.commands:
            blockers.append("no local command; retain the hosted or unexecutable obligation as blocked")
        for command in unit.commands:
            decision = policy.get(command)
            if decision is None or decision["disposition"] != "allowed":
                blockers.append(
                    f"command policy: {command}: {decision['reason'] if decision is not None else 'not reviewed, including nested recipes and fixtures'}"
                )
        executor_observations, executor_blockers = _preflight_executor(unit, prerequisites.get(unit.node_id), repository_root)
        blockers.extend(executor_blockers)
        outputs, output_blockers = _preflight_outputs(unit, repository_root)
        if any(not item["accessible"] for item in cache_checks):
            blockers.append("declared executor cache is inaccessible; remedy it before dispatch")
        units.append(
            {
                "node_id": unit.node_id,
                "blockers": [*blockers, *output_blockers],
                "status": "blocked" if blockers or output_blockers else "ready",
                "expected_outputs": [artifact.path for artifact in unit.allowed_artifacts],
                "output_observations": outputs,
                "executor_observations": executor_observations,
                "executor_requirements": {"sandbox_permissions": executor_permissions(unit.features)},
                "configuration_errors": output_blockers,
                "execution_blockers": blockers,
                "repository_findings": [],
            }
        )
    return {
        "schema_version": 1,
        "plan_digest": _plan_digest(plan),
        "status": "blocked" if any(unit["blockers"] for unit in units) else "ready",
        "units": units,
        "cache_checks": cache_checks,
        "limits": (
            "Read-only prerequisite observations; do not certify command execution or sandbox write permission. "
            "Capture blocked evidence and continue independent audits when authorized."
        ),
    }


def recover_validation_launch(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Replace one proven unstarted validator after an explicit executor remedy."""
    return _recover_validation(document, args, checks_started=False)


def recover_validation_execution(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Retry one failed aggregate with recorded executor-denial evidence."""
    return _recover_validation(document, args, checks_started=True)


def _execution_failure_snapshots(
    document: dict[str, Any], entry: dict[str, Any], metadata: dict[str, Any], evidence: ValidationEvidence, normalized: dict[str, Any]
) -> dict[str, bytes]:
    """Bind a permission diagnosis to the failed execution, log, and snapshots."""
    unit = _validation_unit(entry["dispatch"]["validation_unit"])
    executions = normalized.get("executions", [])
    # A failed aggregate may contain passed subchecks. Separately successful
    # commands are not retryable; this path never rewrites or splices a ledger.
    if len(unit.commands) != 1 or len(executions) != 1 or executions[0].get("result") != "failed" or evidence.status != "failed":
        msg = "execution recovery requires one failed command; never replay separately passed commands"
        raise ValueError(msg)
    failure = document["failure_evidence"]
    diagnostic = _required_text(failure, "diagnostic")
    if not re.search(r"PermissionError: \[Errno (?:1|13)\]|Operation not permitted|Permission denied|EACCES|EPERM", diagnostic):
        msg = "execution recovery requires a concrete executor permission-denial diagnostic"
        raise ValueError(msg)
    log_path = _required_text(failure, "log_path")
    log = next((artifact for artifact in normalized["artifacts"] if artifact["path"] == log_path and artifact["kind"] == "log"), None)
    if log is None or log["artifact_digest_mode"] != "content-sha256-v1" or log_path not in executions[0].get("artifact_paths", []):
        msg = "execution recovery log must be an exact recorded log artifact of the failed command"
        raise ValueError(msg)
    root = Path(entry["dispatch"]["repository_root"])
    log_bytes = _read_regular_file_no_follow(_workspace_path(log_path, root))
    if digest_bytes(log_bytes) != log["artifact_digest"] or diagnostic.encode("utf-8") not in log_bytes or diagnostic not in executions[0]["evidence"]:
        msg = "execution recovery diagnostic or log differs from compiled failure evidence"
        raise ValueError(msg)
    snapshots = {"failure.log": log_bytes}
    dispatch = {**entry["dispatch"]}
    current_state = _current_metadata_state(document)
    for phase in ("before", "after"):
        capture_path = Path(failure[f"{phase}_capture"])
        if _capture_source_state(capture_path) != current_state:
            msg = "execution recovery requires unchanged before/after source captures"
            raise ValueError(msg)
        workspace_path = Path(failure[f"workspace_{phase}"])
        dispatch[f"workspace_{phase}"] = _workspace_records(
            workspace_path,
            node_id=unit.node_id,
            source_state=unit.source_state,
            observed_state=current_state if document.get("external_metadata_transitions") else None,
        )
        snapshots[f"{phase}-capture.json"] = _read_regular_file_no_follow(capture_path)
        snapshots[f"{phase}-workspace.json"] = _read_regular_file_no_follow(workspace_path)
    if _validation_workspace_audit(dispatch, unit) != metadata.get("workspace_audit"):
        msg = "execution recovery workspace snapshots differ from the compiled audit"
        raise ValueError(msg)
    _body, artifacts = _validation_artifacts_body({}, unit, _workspace_snapshot(dispatch, "workspace_after"))
    if len(artifacts) != len(normalized["artifacts"]) or any(
        any(asdict(artifact).get(key) != value for key, value in recorded.items())
        for artifact, recorded in zip(artifacts, normalized["artifacts"], strict=True)
    ):
        msg = "execution recovery workspace snapshots differ from compiled artifact identities"
        raise ValueError(msg)
    return snapshots


def _recover_validation(document: dict[str, Any], args: argparse.Namespace, *, checks_started: bool) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    """Publish one source-preserving attempt without relaxing either entry gate."""
    operation = "recover-validation-execution" if checks_started else "recover-validation-launch"
    require_schema_definition(document, _RUNTIME_OPERATION_INPUT_SCHEMA, operation)
    plan = _graph_plan(document["plan"])
    _verify_validation_recoveries(plan)
    source_state = _state(document, "source_state")
    if _capture_source_state(args.current_capture) != _current_metadata_state(document):
        msg = "validation recovery requires unchanged source state"
        raise ValueError(msg)
    events, state, head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=source_state)
    node_id = _required_text(document, "node_id")
    unit = next((item for item in plan.coalesced_validation_units if item.node_id == node_id), None)
    expected_status = "accepted" if checks_started else "blocked"
    if unit is None or state.get(node_id) != expected_status or not unit.commands or unit.planning_blocker is not None:
        msg = (
            "execution recovery requires accepted failed owner evidence from an executable validator"
            if checks_started
            else "recovery requires a blocked executable validator, not a planning or check failure"
        )
        raise ValueError(msg)
    if any(status in {"in-flight", "awaiting-replan"} for status in state.values()):
        msg = "validation recovery requires quiescent execution without active or source-mutated nodes"
        raise ValueError(msg)
    if any(item["node_id"] == node_id and tuple(item["source_state"]) == source_state for item in plan.validation_recoveries):
        msg = "validation recovery budget exhausted for this node and source state"
        raise ValueError(msg)
    environment = _required_text(document, "environment")
    permission_change = _required_text(document, "permission_change")
    if permission_change.strip().casefold() != "none" and "executor_permissions" not in document:
        msg = "permission recovery requires explicit executor_permissions for the replacement dispatch"
        raise ValueError(msg)
    features = remedied_features(unit.features, document["executor_permissions"]) if "executor_permissions" in document else unit.features
    if permission_change.strip().casefold() == "none" and executor_permissions(features) != executor_permissions(unit.features):
        msg = "changed executor permissions require an explicit permission remedy"
        raise ValueError(msg)
    if checks_started and (
        permission_change.strip().casefold() == "none"
        or (environment == unit.environment and executor_permissions(features) == executor_permissions(unit.features))
    ):
        msg = "execution recovery requires an explicit permission remedy and changed executor identity"
        raise ValueError(msg)
    if environment == unit.environment and permission_change == "none":
        msg = "recovery requires a recorded environment or permission change"
        raise ValueError(msg)
    sources, records = _accepted_journal_sources(plan, source_state, events, entries, include_blocked=True)
    if blockers := _metadata_evidence_blockers(document, records):
        raise ValueError("; ".join(blockers))
    failed_source = sources.get(node_id)
    if failed_source is None:
        msg = "recovery requires compiled, journal-bound launch-failure evidence"
        raise ValueError(msg)
    _kind, _expectation, evidence, _content, normalized = _load_evidence_source(failed_source, require_normalized=True)
    if not isinstance(evidence, ValidationEvidence) or normalized is None:
        msg = "recovery requires normalized validation evidence"
        raise ValueError(msg)
    metadata = _read_json_object(Path(failed_source["metadata_path"]))
    execution_snapshots = {}
    if checks_started:
        execution_snapshots = _execution_failure_snapshots(document, entries[node_id], metadata, evidence, normalized)
    elif evidence.status != "blocked" or any(item.get("result") in {"passed", "failed"} for item in normalized.get("executions", [])):
        msg = "checks already started; preserve their results as owner evidence"
        raise ValueError(msg)
    elif metadata.get("workspace_audit", {}).get("changed_paths"):
        msg = "launch recovery requires an unchanged validation workspace"
        raise ValueError(msg)
    recovery = {key: document[key] for key in ("node_id", "failure_kind", "checks_started", "reason", "remedy", "environment", "permission_change")}
    if "executor_permissions" in document:
        recovery.update(executor_permissions=document["executor_permissions"], previous_features=list(unit.features))
    if checks_started:
        recovery.update(failure_evidence=document["failure_evidence"], previous_evidence_id=evidence.evidence_id)
    recovery.update(
        {
            "source_state": list(source_state),
            "previous_environment": unit.environment,
            "previous_plan_digest": _plan_digest(plan),
            "previous_journal_head": head,
        }
    )
    identity = digest_bytes(canonical_json(recovery).encode())[7:23]
    recovery["attempt_id"] = f"validation-recovery:{identity}"
    history_kind = "execution" if checks_started else "launch"
    history = Path(_required_text(document, "artifact_store")).resolve() / f"{history_kind}-history-{identity}"
    history.mkdir(parents=True, exist_ok=True)
    preserved: list[dict[str, str]] = []
    # Snapshot the journal: future appends must not invalidate historical evidence.
    snapshots = {
        **execution_snapshots,
        "lifecycle.json": canonical_json({key: document[key] for key in ("plan", "source_state", "external_metadata_transitions") if key in document}).encode(),
        "execution.jsonl": _read_regular_file_no_follow(args.journal),
        "dispatches.json": _read_regular_file_no_follow(args.dispatches),
    }
    for name, content in snapshots.items():
        path = history / name
        _write_bytes_atomically_once(path, content, mode=0o444)
        preserved.append({"path": str(path), "digest": digest_bytes(content)})
    for path_text in [failed_source["artifact_path"], failed_source["metadata_path"], metadata.get("worker_payload_path")]:
        if path_text is not None:
            path = Path(path_text).resolve()
            preserved.append({"path": str(path), "digest": digest_bytes(_read_regular_file_no_follow(path))})
    recovery["preserved_files"] = preserved
    expanded = replace(
        plan,
        validation_recoveries=(*plan.validation_recoveries, recovery),
        coalesced_validation_units=tuple(
            replace(item, environment=environment, features=features) if item.node_id == node_id else item for item in plan.coalesced_validation_units
        ),
    )
    retained_sources = {key: value for key, value in sources.items() if key != node_id}
    retained_records = [record for record in records if record.get("node_id") != node_id]
    return _publish_validation_continuation(
        document, args, plan, expanded, entries, retained_sources, retained_records, head, status="recovered", journal_events=events, replaced_node_id=node_id
    )


def _reconciled_handoffs(
    plan: GraphPlan, normalized_by_evidence: dict[str, dict[str, Any]], accepted_review_ids: tuple[str, ...]
) -> tuple[list[dict[str, Any]], tuple[str, ...], tuple[str, ...]]:
    decisions = {decision.catalog_id: decision for decision in plan.routing_decisions}
    requirement_nodes = dict(plan.requirement_to_node)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    blockers: list[str] = []
    unresolved: list[str] = []
    resolved_dispositions = {"exact-evidence-reused", "selected", "user-excluded"}
    for evidence_id in accepted_review_ids:
        normalized = normalized_by_evidence.get(evidence_id, {})
        for raw in normalized.get("handoffs", []):
            if not isinstance(raw, dict):
                continue
            handoff_id = _required_text(raw, "handoff_id")
            catalog_id = _required_text(raw, "catalog_id")
            if handoff_id in seen:
                blockers.append(f"duplicate handoff identity {handoff_id}")
                continue
            seen.add(handoff_id)
            decision = decisions.get(catalog_id)
            disposition = decision.disposition if decision is not None else "unknown-catalog"
            resolved = disposition in resolved_dispositions
            routed_node_id = requirement_nodes.get(decision.requirement_id) if decision is not None else None
            record = {
                "catalog_id": catalog_id,
                "disposition": disposition,
                "handoff_id": handoff_id,
                "originating_evidence_id": evidence_id,
                "originating_node_id": normalized.get("node_id"),
                "resolution": "resolved-by-current-plan" if resolved else "new-routing-trigger",
                "routed_node_id": routed_node_id,
            }
            records.append(record)
            if not resolved:
                unresolved.append(handoff_id)
                blockers.append(
                    f"handoff {handoff_id} from {catalog_id} on node {normalized.get('node_id')} remains {disposition} and requires routing expansion"
                )
    return sorted(records, key=lambda item: str(item["handoff_id"])), tuple(sorted(unresolved)), tuple(blockers)


def reconcile_handoffs(document: dict[str, Any]) -> dict[str, Any]:
    """Resolve already-covered handoffs and return only genuine routing triggers."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "reconcile-handoffs requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    planned_node_ids = {node.node_id for node in plan.actual_worker_nodes}
    exact_reuse_ids = {evidence_id for _requirement_id, evidence_id in plan.exact_reused_review_evidence}
    normalized: dict[str, dict[str, Any]] = {}
    accepted: list[str] = []
    for source in _evidence_sources(document, plan):
        kind, expectation, evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if kind != "review" or not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence):
            continue
        if review_source_state_blockers(plan, expectation, evidence, source_state) or not assess_review_evidence(expectation, evidence).satisfies_requirements:
            continue
        if evidence.node_id not in planned_node_ids and evidence.evidence_id not in exact_reuse_ids:
            continue
        if record is not None:
            normalized[evidence.evidence_id] = record
            accepted.append(evidence.evidence_id)
    records, unresolved, blockers = _reconciled_handoffs(plan, normalized, tuple(sorted(accepted)))
    return {
        "blockers": list(blockers),
        "handoffs": records,
        "new_routing_triggers": [record for record in records if record["handoff_id"] in unresolved],
        "schema_version": 1,
        "status": "resolved" if not unresolved else "requires-expansion",
        "unresolved_handoff_ids": list(unresolved),
    }


def finalize_proof(document: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    """Derive and verify the final repository proof from persisted evidence sources."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "finalize-proof requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    _verify_validation_recoveries(plan)
    source_state = _state(document, "source_state")
    current_source_state = _state(document, "current_source_state")
    if current_source_state != _current_metadata_state(document):
        msg = "finalize-proof current recapture differs from the plan-bound source state"
        raise ValueError(msg)
    expectation = repository_review_proof_expectation(plan, source_state=source_state)
    stale_ids = set(_text_list(document, "stale_evidence_ids"))
    sources = _evidence_sources(document, plan)

    loaded: dict[
        str, tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, dict[str, Any] | None]
    ] = {}
    duplicate_evidence: set[str] = set()
    for source in sources:
        kind, record_expectation, evidence, content, normalized = _load_evidence_source(source)
        if evidence.evidence_id in loaded:
            duplicate_evidence.add(evidence.evidence_id)
        loaded[evidence.evidence_id] = (kind, record_expectation, evidence, content, normalized)
    preblockers = list(_text_list(document, "lifecycle_blockers"))
    normalized_records = [record for *_rest, record in loaded.values() if record is not None]
    successful_validation = {
        record["node_id"] for record in normalized_records if record.get("mode") == "validation" and record["status"] in {"passed", "reused"}
    }
    preblockers.extend(
        f"pre-review validation has not passed: {node_id}" for node_id in plan.pre_review_validation_nodes if node_id not in successful_validation
    )
    synthesis_bundle = {"records": normalized_records, "plan_context": _synthesis_plan_context(plan, normalized_records)}
    for _kind, record_expectation, evidence, content, _record in loaded.values():
        if isinstance(record_expectation, ReviewEvidenceExpectation) and record_expectation.mode == "synthesis":
            try:
                validate_synthesis(_canonical_worker_payload(content), record_expectation.predecessor_evidence_ids, synthesis_bundle)
            except ValueError as error:
                preblockers.append(f"synthesis reconciliation failed for {evidence.evidence_id}: {error}")
    preblockers.extend(_metadata_evidence_blockers(document, [record for *_rest, record in loaded.values() if record is not None]))
    if duplicate_evidence:
        preblockers.append("duplicate evidence sources: " + ", ".join(sorted(duplicate_evidence)))

    node_candidates: dict[str, list[str]] = {}
    eligible_ids: set[str] = set()
    planned_by_id = {node.node_id: node for node in plan.actual_worker_nodes}
    exact_reuse_ids = {evidence_id for _requirement_id, evidence_id in expectation.exact_reused_review_evidence}
    for evidence_id, (kind, record_expectation, evidence, _content, _normalized) in loaded.items():
        if evidence_id in stale_ids:
            continue
        if kind == "review":
            if not isinstance(record_expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence):
                msg = f"review source has mismatched typed evidence: {evidence_id}"
                raise TypeError(msg)
            assessment = assess_review_evidence(record_expectation, evidence)
        else:
            if not isinstance(record_expectation, ValidationEvidenceExpectation) or not isinstance(evidence, ValidationEvidence):
                msg = f"validation source has mismatched typed evidence: {evidence_id}"
                raise TypeError(msg)
            assessment = assess_validation_evidence(record_expectation, evidence)
        # Proof completeness records a verified failed execution without calling it a pass.
        if assessment.satisfies_requirements or (kind == "validation" and assessment.feasible and evidence.status == "failed"):
            eligible_ids.add(evidence_id)
            planned_node = planned_by_id.get(evidence.node_id)
            if planned_node is None and evidence_id not in exact_reuse_ids:
                preblockers.append(f"current proof-eligible evidence maps to an unplanned node: {evidence_id} -> {evidence.node_id}")
                continue
            if planned_node is not None and record_expectation.requirement_ids != planned_node.requirement_ids:
                preblockers.append(f"evidence requirement IDs do not match planned node {evidence.node_id}: {evidence_id}")
                continue
            if isinstance(record_expectation, ReviewEvidenceExpectation) and planned_node is not None:
                expected_reason = "; ".join(planned_node.selection_reasons) or f"planner selected {planned_node.skill_id}"
                if record_expectation.selection_reason != expected_reason:
                    preblockers.append(f"evidence selection reason does not match planned node {evidence.node_id}: {evidence_id}")
                    continue
            node_candidates.setdefault(evidence.node_id, []).append(evidence_id)

    node_evidence: dict[str, str] = {}
    for node in plan.actual_worker_nodes:
        candidates = node_candidates.get(node.node_id, [])
        if len(candidates) == 1:
            node_evidence[node.node_id] = candidates[0]
        elif len(candidates) > 1:
            preblockers.append(f"multiple current proof-eligible evidence records map to node {node.node_id}: " + ", ".join(sorted(candidates)))

    reused_mapping = dict(expectation.exact_reused_review_evidence)
    missing_reuse = tuple(sorted(evidence_id for evidence_id in reused_mapping.values() if evidence_id not in eligible_ids))
    if missing_reuse:
        preblockers.append("exact routed reuse lacks current satisfying evidence: " + ", ".join(missing_reuse))

    review_requirement_evidence = tuple(
        sorted(
            (
                *((requirement_id, node_evidence[node_id]) for requirement_id, node_id in expectation.review_requirement_nodes if node_id in node_evidence),
                *expectation.exact_reused_review_evidence,
            )
        )
    )
    validation_requirement_evidence = tuple(
        sorted((requirement_id, node_evidence[node_id]) for requirement_id, node_id in expectation.validation_requirement_nodes if node_id in node_evidence)
    )
    planned_node_evidence = tuple((node.node_id, node_evidence[node.node_id]) for node in plan.actual_worker_nodes if node.node_id in node_evidence)
    review_node_ids = {node.node_id for node in plan.actual_worker_nodes if node.mode != "validation"}
    validation_node_ids = {node.node_id for node in plan.actual_worker_nodes if node.mode == "validation"}
    accepted_review_ids = tuple(
        sorted(
            {
                *(evidence_id for node_id, evidence_id in planned_node_evidence if node_id in review_node_ids),
                *(evidence_id for _requirement_id, evidence_id in expectation.exact_reused_review_evidence if evidence_id in eligible_ids),
            }
        )
    )
    accepted_validation_ids = tuple(sorted(evidence_id for node_id, evidence_id in planned_node_evidence if node_id in validation_node_ids))
    accepted_ids = set(accepted_review_ids) | set(accepted_validation_ids)
    normalized_by_evidence = {
        evidence_id: normalized for evidence_id, (_kind, _expectation, _evidence, _content, normalized) in loaded.items() if normalized is not None
    }
    handoff_reconciliation, unresolved_handoff_ids, handoff_blockers = _reconciled_handoffs(plan, normalized_by_evidence, accepted_review_ids)
    resolved_handoff_ids = tuple(sorted(str(record["handoff_id"]) for record in handoff_reconciliation if record["resolution"] == "resolved-by-current-plan"))
    routing_discoveries = tuple(
        sorted(
            (
                discovery
                for evidence_id in accepted_review_ids
                if isinstance(loaded[evidence_id][2], ReviewEvidence)
                for discovery in cast("ReviewEvidence", loaded[evidence_id][2]).routing_discoveries
            ),
            key=lambda discovery: discovery.handoff_id,
        )
    )
    preblockers.extend(handoff_blockers)
    validation_reconciliation = _validation_reconciliation(
        plan, [normalized_by_evidence[evidence_id] for evidence_id in accepted_review_ids if evidence_id in normalized_by_evidence]
    )
    preblockers.extend(validation_reconciliation["blockers"])
    for evidence_id in accepted_review_ids:
        evidence = loaded[evidence_id][2]
        if isinstance(evidence, ReviewEvidence) and evidence.validation_requirement_ids and evidence_id not in normalized_by_evidence:
            preblockers.append(f"validation requirements lack compiler-bound normalized context: {evidence_id}")

    verifier_id = _defaulted_text(document, "verifier_id", "review-graph-runtime")
    manifest_id = _defaulted_text(document, "manifest_id", f"manifest:{expectation.plan_digest.removeprefix('sha256:')[:16]}")
    manifest = create_artifact_manifest(
        manifest_id=manifest_id,
        verifier_id=verifier_id,
        artifacts=tuple((evidence_id, loaded[evidence_id][2].raw_result_artifact_id, loaded[evidence_id][3]) for evidence_id in sorted(accepted_ids)),
    )
    final_synthesis_evidence_id = node_evidence.get(expectation.final_synthesis_identity[0], "missing:repository-synthesis")
    proof = RepositoryReviewProof(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        proof_id=_defaulted_text(document, "proof_id", f"proof:{expectation.plan_digest.removeprefix('sha256:')[:16]}"),
        plan_digest=expectation.plan_digest,
        source_state=source_state,
        planned_node_evidence=planned_node_evidence,
        required_review_requirement_ids=expectation.required_review_requirement_ids,
        review_requirement_evidence=review_requirement_evidence,
        exact_reused_review_evidence=expectation.exact_reused_review_evidence,
        accepted_review_evidence_ids=accepted_review_ids,
        required_validation_requirement_ids=expectation.required_validation_requirement_ids,
        validation_requirement_evidence=validation_requirement_evidence,
        accepted_validation_evidence_ids=accepted_validation_ids,
        stale_evidence_ids=tuple(sorted(stale_ids)),
        unresolved_handoff_ids=unresolved_handoff_ids,
        final_synthesis_evidence_id=final_synthesis_evidence_id,
        artifact_manifest_id=manifest.manifest_id,
        artifact_manifest_digest=manifest.manifest_digest,
        verifier_id=verifier_id,
        resolved_handoff_ids=resolved_handoff_ids,
        routing_discoveries=routing_discoveries,
    )
    review_record_list: list[tuple[ReviewEvidenceExpectation, ReviewEvidence]] = []
    for evidence_id in accepted_review_ids:
        record_expectation, evidence = loaded[evidence_id][1:3]
        if isinstance(record_expectation, ReviewEvidenceExpectation) and isinstance(evidence, ReviewEvidence):
            review_record_list.append((record_expectation, evidence))
    review_records = tuple(review_record_list)
    validation_record_list: list[tuple[ValidationEvidenceExpectation, ValidationEvidence]] = []
    for evidence_id in accepted_validation_ids:
        record_expectation, evidence = loaded[evidence_id][1:3]
        if isinstance(record_expectation, ValidationEvidenceExpectation) and isinstance(evidence, ValidationEvidence):
            validation_record_list.append((record_expectation, evidence))
    validation_records = tuple(validation_record_list)
    verifier = TrustedArtifactVerifier(
        verifier_id=verifier_id,
        digest_algorithm="sha256",
        artifacts=tuple(
            ArtifactPayload(artifact_id=loaded[evidence_id][2].raw_result_artifact_id, content=loaded[evidence_id][3]) for evidence_id in sorted(accepted_ids)
        ),
    )
    assessment = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    blockers = (*preblockers, *assessment.blockers)
    validation_statuses = tuple(
        evidence.status
        for _evidence_id, (kind, _expectation, evidence, _content, _normalized) in loaded.items()
        if kind == "validation" and isinstance(evidence, ValidationEvidence) and evidence.node_id in validation_node_ids
    )
    if "failed" in validation_statuses:
        repository_validation_status = "failed"
    elif "blocked" in validation_statuses or "not-applicable" in validation_statuses:
        repository_validation_status = "blocked"
    elif len(accepted_validation_ids) != len(validation_node_ids) or validation_reconciliation["blockers"]:
        repository_validation_status = "incomplete"
    else:
        repository_validation_status = "passed"
    graph_proof_status = "complete" if not blockers else "incomplete"
    accepted_independent_list: list[str] = []
    for evidence_id in accepted_review_ids:
        evidence = loaded[evidence_id][2]
        if isinstance(evidence, ReviewEvidence) and evidence.mode == "independent-review":
            accepted_independent_list.append(evidence_id)
    accepted_independent = tuple(accepted_independent_list)
    final_record = loaded[final_synthesis_evidence_id][4] if final_synthesis_evidence_id in loaded else None
    return {
        "artifact_manifest": asdict(manifest),
        "blockers": list(blockers),
        "graph_proof_status": graph_proof_status,
        "validation_recoveries": list(plan.validation_recoveries),
        "handoff_reconciliation": handoff_reconciliation,
        "independent_review_metrics": {
            "accepted_evidence_count": len(accepted_independent),
            "semantic_agreement": "not-inferred-from-structural-acceptance",
            "specialist_recall": "requires-independent-adjudication",
            "structurally_accepted_evidence_ids": list(accepted_independent),
        },
        "proof": asdict(proof),
        "repository_validation_status": repository_validation_status,
        "repository_readiness": final_record.get("readiness_verdict", "blocked") if final_record is not None and not blockers else "blocked",
        "software_doi_resolutions": [item for item in final_record.get("validation_reconciliation", []) if "software_doi_resolution" in item]
        if final_record is not None and not blockers
        else [],
        "scholarly_doi_resolutions": [item for item in final_record.get("validation_reconciliation", []) if "scholarly_doi_resolution" in item]
        if final_record is not None and not blockers
        else [],
        "reviewed_source_state": list(source_state),
        "current_source_state": list(current_source_state),
        "external_metadata_transitions": document.get("external_metadata_transitions", []),
        "validation_reconciliation": validation_reconciliation,
        "schema_version": 1,
        "status": graph_proof_status,
        "summary": {
            "accepted_review_evidence": len(accepted_review_ids),
            "accepted_validation_evidence": len(accepted_validation_ids),
            "planned_nodes": len(plan.actual_worker_nodes),
            "unresolved_handoffs": len(unresolved_handoff_ids),
        },
    }


def _runtime_subparser(subparsers: Any, operation: str, help_text: str, *, contract_text: str | None = None) -> argparse.ArgumentParser:
    schema_reference = f"{_RUNTIME_OPERATION_INPUT_SCHEMA}#/$defs/{operation}"
    example_reference = f"{_RUNTIME_OPERATION_EXAMPLES}#/{operation}"
    epilog = f"Input schema: {schema_reference}\nValid example: {example_reference}"
    if contract_text is not None:
        epilog += "\n\n" + contract_text
    parser = subparsers.add_parser(operation, description=help_text, epilog=epilog, formatter_class=argparse.RawDescriptionHelpFormatter, help=help_text)
    if not isinstance(parser, argparse.ArgumentParser):
        msg = f"runtime parser factory returned an invalid parser for {operation}"
        raise TypeError(msg)
    parser.add_argument("--full-output", action="store_true", help="print the complete result instead of a compact artifact receipt")
    return parser


def _argument_parser() -> argparse.ArgumentParser:  # noqa: PLR0915
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    resume_parser = _runtime_subparser(subparsers, "resume-after-external-metadata", "resume after verified external staging without changing Git")
    resume_parser.add_argument("--input", type=Path, required=True)
    resume_parser.add_argument("--output", type=Path, required=True)
    compile_parser = _runtime_subparser(subparsers, "compile-review", "compile a compact review payload")
    compile_parser.add_argument("--input", type=Path, required=True)
    compile_parser.add_argument("--artifact", type=Path, required=True)
    compile_parser.add_argument("--metadata", type=Path, required=True)
    independent_parser = _runtime_subparser(subparsers, "compile-independent-review", "compile a structured independent review")
    independent_parser.add_argument("--input", type=Path, required=True)
    independent_parser.add_argument("--artifact", type=Path, required=True)
    independent_parser.add_argument("--metadata", type=Path, required=True)
    validation_parser = _runtime_subparser(subparsers, "compile-validation", "compile a compact validation payload")
    validation_parser.add_argument("--input", type=Path, required=True)
    validation_parser.add_argument("--artifact", type=Path, required=True)
    validation_parser.add_argument("--metadata", type=Path, required=True)
    node_parser = _runtime_subparser(subparsers, "compile-node", "compile and journal one materialized node by node ID")
    node_parser.add_argument("--input", type=Path, required=True)
    node_parser.add_argument("--dispatches", type=Path, required=True)
    node_parser.add_argument("--node-id", required=True)
    node_parser.add_argument("--payload", type=Path, help="deprecated; when supplied, must equal the materialized worker payload path")
    node_parser.add_argument("--before-capture", type=Path, required=True)
    node_parser.add_argument("--after-capture", type=Path, required=True)
    node_parser.add_argument("--workspace-before", type=Path)
    node_parser.add_argument("--workspace-after", type=Path)
    node_parser.add_argument("--journal", type=Path, required=True, help=_INITIAL_JOURNAL_HELP)
    node_parser.add_argument("--status", choices=sorted(_REVIEW_STATUSES))
    node_parser.add_argument("--limitation", action="append")
    node_parser.add_argument(
        "--output", type=Path, required=True, help="operation-result JSON path; must be distinct from the compiled artifact and metadata paths"
    )
    persist_parser = _runtime_subparser(subparsers, "persist-worker-payload", "validate and atomically publish one materialized worker payload")
    persist_parser.add_argument("--input", type=Path, required=True)
    payload_source = persist_parser.add_mutually_exclusive_group(required=True)
    payload_source.add_argument("--payload", type=Path, help="legacy materialized candidate path")
    payload_source.add_argument("--payload-stdin", action="store_true", help="read candidate bytes from standard input before any artifact write")
    persist_parser.add_argument(
        "--approval-identity", help="bind an explicitly approved retry to the exact validated payload bytes, input mode, and materialized target"
    )
    review_write_parser = _runtime_subparser(
        subparsers, "review-worker-payload-write", "validate standard-input worker payload bytes and emit their artifact-write review without publishing"
    )
    review_write_parser.add_argument("--input", type=Path, required=True)
    publish_parser = _runtime_subparser(subparsers, "publish-worker-payload", "review and publish identical standard-input bytes in one invocation")
    publish_parser.add_argument("--input", type=Path, required=True)
    publish_parser.add_argument("--approval-identity")
    synthesis_parser = _runtime_subparser(subparsers, "synthesis-bundle", "build a compact synthesis bundle")
    synthesis_parser.add_argument("--input", type=Path, required=True)
    synthesis_parser.add_argument("--output", type=Path, required=True)
    routing_parser = _runtime_subparser(subparsers, "routing-projection", "project the complete consulted routing catalog")
    routing_parser.add_argument("--input", type=Path, required=True)
    routing_parser.add_argument("--output", type=Path, required=True)
    routing_parser.add_argument("--catalog", type=Path, default=DEFAULT_ROUTING_CATALOG)
    routing_parser.add_argument("--skill-root", type=Path, action="append")
    dispatch_parser = _runtime_subparser(subparsers, "materialize-dispatches", "derive exact dispatch bases from a graph plan")
    dispatch_parser.add_argument("--input", type=Path, required=True)
    dispatch_parser.add_argument("--output", type=Path, required=True, help="operation-result JSON path; must be outside the artifact store")
    preflight_parser = _runtime_subparser(subparsers, "preflight-validation", "inspect command policy, caches and validation obligations before fanout")
    preflight_parser.add_argument("--input", type=Path, required=True)
    preflight_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser = _runtime_subparser(subparsers, "snapshot-workspace", "capture runtime-owned validation workspace evidence")
    snapshot_parser.add_argument("--input", type=Path, required=True)
    snapshot_parser.add_argument("--dispatches", type=Path, required=True)
    snapshot_parser.add_argument("--node-id", required=True)
    snapshot_parser.add_argument("--current-capture", type=Path, required=True)
    snapshot_parser.add_argument("--output", type=Path, required=True)
    mutation_parser = _runtime_subparser(subparsers, "advance-after-mutation", "recapture and replan one serialized repair epoch")
    mutation_parser.add_argument("--input", type=Path, required=True)
    mutation_parser.add_argument("--output", type=Path, required=True)
    handoff_parser = _runtime_subparser(subparsers, "reconcile-handoffs", "resolve covered handoffs and return new routing triggers")
    handoff_parser.add_argument("--input", type=Path, required=True)
    handoff_parser.add_argument("--output", type=Path, required=True)
    validation_parser = _runtime_subparser(subparsers, "reconcile-validation-requirements", "inspect or expand late validation without changing source state")
    validation_parser.add_argument("--input", type=Path, required=True)
    validation_parser.add_argument("--journal", type=Path, required=True)
    validation_parser.add_argument("--dispatches", type=Path, required=True)
    validation_parser.add_argument("--current-capture", type=Path, required=True)
    validation_parser.add_argument("--output", type=Path, required=True)
    for operation, description in (
        ("recover-validation-launch", "retry one proven unstarted validator after an executor remedy"),
        ("recover-validation-execution", "retry one failed aggregate after a proven executor permission denial"),
    ):
        recovery_parser = _runtime_subparser(subparsers, operation, description)
        recovery_parser.add_argument("--input", type=Path, required=True)
        recovery_parser.add_argument("--journal", type=Path, required=True)
        recovery_parser.add_argument("--dispatches", type=Path, required=True)
        recovery_parser.add_argument("--current-capture", type=Path, required=True)
        recovery_parser.add_argument("--output", type=Path, required=True)
    fallback_parser = _runtime_subparser(subparsers, "fallback-to-coordinator", "transition one unstarted adaptive node without rebinding accepted evidence")
    fallback_parser.add_argument("--input", type=Path, required=True)
    fallback_parser.add_argument("--journal", type=Path, required=True)
    fallback_parser.add_argument("--dispatches", type=Path, required=True)
    fallback_parser.add_argument("--current-capture", type=Path, required=True)
    fallback_parser.add_argument("--output", type=Path, required=True)
    schedule_parser = _runtime_subparser(subparsers, "schedule-ready", "reserve an adaptive coordinator audit lane alongside available workers")
    schedule_parser.add_argument("--input", type=Path, required=True)
    schedule_parser.add_argument("--journal", type=Path, required=True)
    schedule_parser.add_argument("--dispatches", type=Path, required=True)
    schedule_parser.add_argument("--current-capture", type=Path, required=True)
    schedule_parser.add_argument("--output", type=Path, required=True)
    journal_parser = _runtime_subparser(
        subparsers,
        "journal-append",
        "append one verified graph lifecycle event",
        contract_text=(
            "Status field contract:\n"
            "  in-flight       artifact/metadata/kind/reason forbidden\n"
            "  accepted        artifact and metadata required; kind optional; reason forbidden\n"
            "  blocked         artifact and metadata optional as a pair; kind optional with evidence; reason required\n"
            "  invalidated     artifact/metadata/kind forbidden; reason required\n"
            "  awaiting-replan artifact/metadata/kind forbidden; reason required"
        ),
    )
    journal_parser.add_argument("--input", type=Path, required=True)
    journal_parser.add_argument("--journal", type=Path, required=True, help=_INITIAL_JOURNAL_HELP)
    journal_parser.add_argument("--node-id", required=True)
    journal_parser.add_argument("--status", choices=sorted(_JOURNAL_STATUSES), required=True, help="lifecycle status; see the status field contract below")
    journal_parser.add_argument("--artifact", type=Path, help="compiled evidence artifact; paired with --metadata")
    journal_parser.add_argument("--metadata", type=Path, help="compiled evidence metadata; paired with --artifact")
    journal_parser.add_argument("--kind", choices=("review", "validation"), help="optional evidence kind; requires artifact and metadata")
    journal_parser.add_argument("--reason", help="required for blocked, invalidated, and awaiting-replan; forbidden otherwise")
    ready_parser = _runtime_subparser(subparsers, "next-ready", "compute dependency-ready graph nodes")
    ready_parser.add_argument("--dispatches", type=Path, required=True)
    ready_parser.add_argument("--current-capture", type=Path, required=True)
    ready_parser.add_argument("--input", type=Path, required=True)
    ready_parser.add_argument("--journal", type=Path, required=True, help=_INITIAL_JOURNAL_HELP)
    ready_parser.add_argument("--compact", action="store_true", help="return node IDs and immutable worker-input references without embedded dispatches")
    ready_output = ready_parser.add_mutually_exclusive_group(required=True)
    ready_output.add_argument("--output", type=Path)
    ready_output.add_argument(
        "--output-dir", type=Path, help="runtime-managed immutable next-ready generations; receipt reports output.path, output.digest and output_generation"
    )
    final_parser = _runtime_subparser(subparsers, "finalize-proof", "derive and verify the repository proof")
    final_parser.add_argument("--current-capture", type=Path, required=True)
    final_parser.add_argument("--dispatches", type=Path)
    final_parser.add_argument("--input", type=Path, required=True)
    final_parser.add_argument("--journal", type=Path, help=_INITIAL_JOURNAL_HELP)
    final_parser.add_argument("--output", type=Path, required=True)
    return parser


def _journal_request_from_args(args: argparse.Namespace) -> JournalEventRequest:
    if (args.artifact is None) != (args.metadata is None):
        msg = "journal evidence requires both --artifact and --metadata"
        raise ValueError(msg)
    source = None
    if args.artifact is not None and args.metadata is not None:
        source = {"artifact_path": str(args.artifact), "metadata_path": str(args.metadata)}
        if args.kind is not None:
            source["kind"] = args.kind
    elif args.kind is not None:
        msg = "--kind requires --artifact and --metadata"
        raise ValueError(msg)
    has_evidence = source is not None
    if args.status == "accepted" and not has_evidence:
        msg = "accepted journal event requires --artifact and --metadata"
        raise ValueError(msg)
    if args.status in {"in-flight", "invalidated", "awaiting-replan"} and has_evidence:
        msg = f"{args.status} journal event forbids --artifact, --metadata, and --kind"
        raise ValueError(msg)
    if args.status in {"blocked", "invalidated", "awaiting-replan"} and args.reason is None:
        msg = f"{args.status} journal event requires --reason"
        raise ValueError(msg)
    if args.status in {"in-flight", "accepted"} and args.reason is not None:
        msg = f"{args.status} journal event forbids --reason"
        raise ValueError(msg)
    return JournalEventRequest(args.node_id, args.status, source=source, reason=args.reason)


def _next_ready_from_files(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "next-ready requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    capture = _read_json_object(args.current_capture)
    document = dict(document)
    document["current_source_state"] = [
        capture.get("scope_fingerprint"),
        capture.get("captured_worktree_fingerprint"),
        capture.get("repository_state_fingerprint"),
    ]
    journal_events, _state_view, _head_digest = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    result = next_ready_nodes(document, journal_events=journal_events, dispatch_set=_read_json_object(args.dispatches))
    if not getattr(args, "compact", False):
        return result
    compact = dict(result)
    compact["compact"] = True
    compact["ready_dispatches"] = [
        {
            "execution_location": entry["dispatch"]["execution_location"],
            "node_id": entry["node_id"],
            "result_contract": entry["result_contract"],
            "worker_input_path": entry["worker_input_path"],
        }
        for entry in result["ready_dispatches"]
    ]
    return compact


def _with_current_capture(document: dict[str, Any], capture_path: Path) -> dict[str, Any]:
    capture = _read_json_object(capture_path)
    output = dict(document)
    output["current_source_state"] = [
        capture.get("scope_fingerprint"),
        capture.get("captured_worktree_fingerprint"),
        capture.get("repository_state_fingerprint"),
    ]
    return output


def _finalize_document_from_files(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    output = _with_current_capture(document, args.current_capture)
    if (args.dispatches is None) != (args.journal is None):
        msg = "finalize-proof source discovery requires both --dispatches and --journal"
        raise ValueError(msg)
    if args.dispatches is None or "sources" in output:
        return output
    raw_plan = output.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "finalize-proof requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(output, "source_state")
    events, lifecycle, _head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=source_state)
    sources, _records = _accepted_journal_sources(plan, source_state, events, entries, include_blocked=True)
    output["sources"] = list(sources.values())
    latest = {str(event["node_id"]): event for event in events}
    output["lifecycle_blockers"] = [
        f"{status} node {node_id}: {latest[node_id].get('reason') or 'execution has not completed'}"
        for node_id, status in lifecycle.items()
        if status in {"blocked", "in-flight", "awaiting-replan", "invalidated"}
    ]
    return output


def _capture_source_state(path: Path) -> tuple[str, str, str]:
    capture = _read_json_object(path)
    state = (capture.get("scope_fingerprint"), capture.get("captured_worktree_fingerprint"), capture.get("repository_state_fingerprint"))
    if any(not isinstance(value, str) or not value for value in state):
        msg = f"capture lacks canonical source-state fingerprints: {path}"
        raise ValueError(msg)
    return cast("tuple[str, str, str]", state)


def _lifecycle_dispatch(document: dict[str, Any], dispatches_path: Path, node_id: str) -> tuple[GraphPlan, dict[str, Any]]:
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "lifecycle operation requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    entries = _dispatches_by_node(_read_json_object(dispatches_path), plan=plan, source_state=source_state)
    try:
        selected = json.loads(canonical_json(entries[node_id]))
    except KeyError:
        msg = f"dispatch set has no planned node {node_id}"
        raise ValueError(msg) from None
    dispatch = selected.get("dispatch")
    if isinstance(dispatch, dict) and dispatch.get("fresh_context") is True:
        forbidden: set[str] = set()
        for other_id, entry in entries.items():
            if other_id == node_id:
                continue
            for field in (
                "artifact_path",
                "metadata_path",
                "worker_input_path",
                "worker_payload_candidate_path",
                "worker_payload_contract_path",
                "worker_payload_path",
            ):
                value = entry.get(field)
                if isinstance(value, str) and value:
                    path = Path(value)
                    forbidden.update((str(path), path.name))
        dispatch["fresh_context_forbidden_artifacts"] = sorted(forbidden)
    return plan, selected


def _snapshot_workspace_from_files(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    _plan, entry = _lifecycle_dispatch(document, args.dispatches, args.node_id)
    source_state = _state(document, "source_state")
    if _capture_source_state(args.current_capture) != _current_metadata_state(document):
        msg = "workspace snapshot capture differs from the plan-bound source state"
        raise ValueError(msg)
    dispatch = entry.get("dispatch")
    if not isinstance(dispatch, dict) or entry.get("result_contract") != "compact-validation":
        msg = f"workspace snapshots apply only to validation nodes: {args.node_id}"
        raise ValueError(msg)
    return {**capture_workspace_snapshot(dispatch), "observed_source_state": list(_capture_source_state(args.current_capture))}


def _workspace_records(
    path: Path, *, node_id: str, source_state: tuple[str, str, str], observed_state: tuple[str, str, str] | None = None
) -> list[dict[str, Any]]:
    snapshot = _read_json_object(path)
    if observed_state is not None and tuple(snapshot.get("observed_source_state", ())) != observed_state:
        msg = "workspace snapshot predates the current external metadata state"
        raise ValueError(msg)
    if snapshot.get("node_id") != node_id or _state(snapshot, "source_state") != source_state:
        msg = f"workspace snapshot belongs to a different node or source state: {path}"
        raise ValueError(msg)
    return list(_records(snapshot, "records"))


def _preflight_compile_destination(path: Path, content: bytes) -> None:
    """Reject an immutable destination conflict before any compile output is published."""
    if path.is_symlink():
        msg = f"compile-node destination must not be a symlink: {path}"
        raise ValueError(msg)
    if path.exists() and _read_regular_file_no_follow(path) != content:
        msg = f"refusing to overwrite non-identical artifact: {path}"
        raise ValueError(msg)


def _rollback_compile_journal(path: Path, *, existing_size: int, remove_after_truncate: bool) -> None:
    """Remove a failed append while preserving the pre-attempt journal prefix."""
    with path.open("r+b") as stream:
        stream.truncate(existing_size)
        stream.flush()
        os.fsync(stream.fileno())
    if remove_after_truncate:
        path.unlink()
        _fsync_directory(path.parent)


def _remove_attempt_created_files(paths: list[Path]) -> None:
    """Remove only immutable files published by the current failed attempt."""
    parents: set[Path] = set()
    for path in reversed(paths):
        path.unlink(missing_ok=True)
        parents.add(path.parent)
    for parent in parents:
        _fsync_directory(parent)


def _compile_node_from_files(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    plan, entry = _lifecycle_dispatch(document, args.dispatches, args.node_id)
    source_state = _state(document, "source_state")
    before_state = _capture_source_state(args.before_capture)
    after_state = _capture_source_state(args.after_capture)
    states = metadata_states(source_state, tuple(metadata_transition(item) for item in _records(document, "external_metadata_transitions")))
    raw_dispatch = entry.get("dispatch")
    if not isinstance(raw_dispatch, dict):
        msg = f"materialized node has no dispatch object: {args.node_id}"
        raise TypeError(msg)
    if (
        before_state not in states
        or after_state not in states
        or states.index(before_state) > max(ordinal for ordinal, state in enumerate(states) if state == after_state)
        or (raw_dispatch.get("mode") != "audit" and after_state != states[-1])
    ):
        msg = "compile-node capture differs from the plan-bound source state"
        raise ValueError(msg)
    dispatch = {
        **raw_dispatch,
        "after_state": list(after_state),
        "before_state": list(before_state),
        "external_metadata_transitions": document.get("external_metadata_transitions", []),
    }
    contract = _required_text(entry, "result_contract")
    payload_path = Path(_required_text(entry, "worker_payload_path")).resolve()
    if _required_text(raw_dispatch, "worker_payload_path") != str(payload_path):
        msg = f"materialized worker payload path differs between entry and dispatch: {args.node_id}"
        raise ValueError(msg)
    if args.payload is not None and args.payload.resolve() != payload_path:
        msg = "compile-node accepts only the materialized worker payload path"
        raise ValueError(msg)
    if not payload_path.is_file():
        msg = f"worker result was not persisted before compilation: {payload_path}"
        raise ValueError(msg)
    payload_bytes = payload_path.read_bytes()
    if contract == "compact-validation":
        dispatch["source_capture"] = _read_json_object(args.after_capture)
        if args.workspace_before is None or args.workspace_after is None:
            msg = "validation compile-node requires --workspace-before and --workspace-after"
            raise ValueError(msg)
        dispatch["workspace_before"] = _workspace_records(
            args.workspace_before, node_id=args.node_id, source_state=source_state, observed_state=before_state if len(states) > 1 else None
        )
        dispatch["workspace_after"] = _workspace_records(
            args.workspace_after, node_id=args.node_id, source_state=source_state, observed_state=after_state if len(states) > 1 else None
        )
    elif args.workspace_before is not None or args.workspace_after is not None:
        msg = "workspace snapshots apply only to validation compile-node operations"
        raise ValueError(msg)

    if contract in {"compact-review", "compact-validation"}:
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict):
            msg = "compact worker payload root must be an object"
            raise TypeError(msg)
        require_schema(payload, _review_payload_schema(dispatch) if contract == "compact-review" else _VALIDATION_PAYLOAD_SCHEMA)
        if dispatch.get("mode") == "synthesis":
            events, _lifecycle, _head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
            entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=source_state)
            sources, _records_view = _accepted_journal_sources(plan, source_state, events, entries)
            dispatch["synthesis_bundle"] = build_synthesis_bundle({**document, "sources": list(sources.values())})
        compiler_input = {"dispatch": dispatch, "payload": payload}
        content, metadata = compile_review(compiler_input) if contract == "compact-review" else compile_validation(compiler_input)
    elif contract == "compact-independent-review":
        payload = json.loads(payload_bytes)
        require_schema(payload, _INDEPENDENT_PAYLOAD_SCHEMA)
        if (args.status is not None and args.status != payload.get("status")) or (
            args.limitation is not None and args.limitation != payload.get("limitations")
        ):
            msg = "independent status and limitations must match the canonical structured payload"
            raise ValueError(msg)
        content, metadata = compile_independent_payload({"dispatch": dispatch, "payload": payload})
    else:
        msg = f"compile-node does not support result contract {contract}"
        raise ValueError(msg)

    artifact_path = Path(_required_text(entry, "artifact_path")).resolve()
    metadata_path = Path(_required_text(entry, "metadata_path")).resolve()
    worker_payload_digest = digest_bytes(payload_bytes)
    sealed_payload_path = payload_path.with_name(f"{payload_path.stem}.{worker_payload_digest.removeprefix('sha256:')}.sealed{payload_path.suffix}")
    metadata = {
        **metadata,
        "worker_payload_byte_count": len(payload_bytes),
        "worker_payload_digest": worker_payload_digest,
        "worker_payload_path": str(sealed_payload_path),
        "worker_payload_staging_path": str(payload_path),
    }
    metadata_bytes = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    evidence = metadata.get("evidence")
    if not isinstance(evidence, dict):
        msg = "compiler metadata lacks evidence"
        raise TypeError(msg)
    evidence_status = _required_text(evidence, "status")
    journal_status = "blocked" if evidence_status in {"blocked", "not-applicable"} else "accepted"
    source = {"artifact_path": str(artifact_path), "metadata_path": str(metadata_path)}
    operation_output_path = args.output.resolve()
    destinations = {
        "compiled artifact": artifact_path,
        "compiled metadata": metadata_path,
        "operation result": operation_output_path,
        "sealed worker payload": sealed_payload_path,
    }
    if len(set(destinations.values())) != len(destinations):
        aliases = ", ".join(f"{label}={path}" for label, path in destinations.items())
        msg = f"compile-node destinations must be distinct; --output is the operation-result path: {aliases}"
        raise ValueError(msg)
    if operation_output_path.exists() or operation_output_path.is_symlink():
        msg = f"compile-node operation-result --output already exists: {operation_output_path}"
        raise ValueError(msg)
    _preflight_compile_destination(sealed_payload_path, payload_bytes)
    _preflight_compile_destination(artifact_path, content)
    _preflight_compile_destination(metadata_path, metadata_bytes)
    for parent in {artifact_path.parent, metadata_path.parent, payload_path.parent, args.journal.parent.resolve(), operation_output_path.parent}:
        parent.mkdir(parents=True, exist_ok=True)

    request = JournalEventRequest(args.node_id, journal_status, source=source, reason="; ".join(args.limitation or ()) or None)
    lock_path = args.journal.with_name(args.journal.name + ".lock")
    with lock_path.open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            try:
                journal_content = args.journal.read_bytes()
                journal_existed = True
            except FileNotFoundError:
                journal_content = b""
                journal_existed = False
            _events, lifecycle_state, _head = _read_execution_journal_content(journal_content, path=args.journal, plan=plan, source_state=source_state)
            _apply_journal_transition(plan, lifecycle_state, node_id=request.node_id, status=request.status)
            normalized = metadata.get("normalized_record")
            journal_limitations = _review_limitation_reasons(normalized) if isinstance(normalized, dict) else ()
            _new_journal_reason(request, journal_limitations)
            existing_size = len(journal_content)
            created_paths: list[Path] = []
            journal_append_started = False
            completed = False
            try:
                for path, output_bytes in ((sealed_payload_path, payload_bytes), (artifact_path, content), (metadata_path, metadata_bytes)):
                    if _write_bytes_atomically_once(path, output_bytes, mode=0o444):
                        created_paths.append(path)
                event, existing_size = _prepare_journal_event(args.journal, plan=plan, source_state=source_state, request=request, content=journal_content)
                result = {
                    "artifact_path": str(artifact_path),
                    "journal_event": event,
                    "metadata_path": str(metadata_path),
                    "node_id": args.node_id,
                    "schema_version": 1,
                    "worker_payload_path": str(sealed_payload_path),
                }
                result_bytes = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
                if _write_bytes_atomically_once(operation_output_path, result_bytes, mode=0o444):
                    created_paths.append(operation_output_path)
                with args.journal.open("ab") as journal_stream:
                    journal_stream.seek(0, os.SEEK_END)
                    if journal_stream.tell() != existing_size:
                        msg = f"execution journal changed during append: {args.journal}"
                        raise ValueError(msg)
                    journal_append_started = True
                    _persist_journal_event(journal_stream, args.journal, event, existing_size=existing_size)
                completed = True
                return result
            finally:
                if not completed:
                    try:
                        if journal_append_started:
                            _rollback_compile_journal(args.journal, existing_size=existing_size, remove_after_truncate=not journal_existed)
                    finally:
                        _remove_attempt_created_files(created_paths)
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def _json_operation_output(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:  # noqa: C901, PLR0911
    if args.operation == "preflight-validation":
        return preflight_validation(document)
    if args.operation == "compile-node":
        return _compile_node_from_files(document, args)
    if args.operation == "snapshot-workspace":
        return _snapshot_workspace_from_files(document, args)
    if args.operation == "synthesis-bundle":
        return build_synthesis_bundle(document)
    if args.operation == "routing-projection":
        return build_routing_projection_document(document, catalog_path=args.catalog, skill_roots=tuple(args.skill_root or (DEFAULT_SKILL_ROOT,)))
    if args.operation == "advance-after-mutation":
        return advance_after_mutation(document)
    if args.operation == "resume-after-external-metadata":
        return resume_after_external_metadata(document)
    if args.operation == "reconcile-handoffs":
        return reconcile_handoffs(document)
    if args.operation in {"reconcile-validation-requirements", "fallback-to-coordinator", "recover-validation-launch", "recover-validation-execution"}:
        operation = {
            "reconcile-validation-requirements": reconcile_validation_requirements,
            "fallback-to-coordinator": fallback_to_coordinator,
            "recover-validation-launch": recover_validation_launch,
            "recover-validation-execution": recover_validation_execution,
        }[args.operation]
        return operation(document, args)
    if args.operation == "next-ready":
        return _next_ready_from_files(document, args)
    return finalize_proof(_finalize_document_from_files(document, args))


def publish_worker_payload_bytes(document: dict[str, Any], payload_bytes: bytes, *, approval_identity: str | None = None) -> dict[str, Any]:
    """Review and publish identical bound bytes in one supported transaction."""
    review = review_worker_payload_write(document, payload_bytes)
    return persist_worker_payload_bytes(document, payload_bytes, approval_identity=approval_identity or review["approval_identity"])


def _worker_payload_cli_output(receipt: dict[str, Any], *, full_output: bool) -> dict[str, Any]:
    """Leave path inventories on disk unless the caller requests full output."""
    fields = (
        "schema_version",
        "status",
        "error",
        "message",
        "node_id",
        "result_contract",
        "worker_payload_path",
        "worker_payload_digest",
        "worker_payload_byte_count",
        "approval_identity",
        "artifact_write_review_reference",
    )
    return receipt if full_output else {key: receipt[key] for key in fields if key in receipt}


def _run_worker_payload_operation(document: dict[str, Any], args: argparse.Namespace) -> int:
    if args.operation == "publish-worker-payload":
        payload_bytes = sys.stdin.buffer.read()
        receipt = publish_worker_payload_bytes(document, payload_bytes, approval_identity=args.approval_identity)
        print(canonical_json(_worker_payload_cli_output(receipt, full_output=args.full_output)))
        return 0
    if args.operation == "review-worker-payload-write":
        payload_bytes = sys.stdin.buffer.read()
        print(canonical_json(review_worker_payload_write(document, payload_bytes, candidate_is_write_target=False)))
        return 0
    if args.payload_stdin:
        if args.approval_identity is None:
            msg = "persist-worker-payload --payload-stdin requires the artifact-write review approval identity"
            raise ValueError(msg)
        payload_bytes = sys.stdin.buffer.read()
        receipt = persist_worker_payload_bytes(document, payload_bytes, approval_identity=args.approval_identity)
        print(canonical_json(_worker_payload_cli_output(receipt, full_output=args.full_output)))
        return 0
    receipt = persist_worker_payload(document, args.payload, approval_identity=args.approval_identity)
    print(canonical_json(_worker_payload_cli_output(receipt, full_output=args.full_output)))
    return 0


def _print_operation_result(args: argparse.Namespace, output_path: Path, output: dict[str, Any]) -> None:
    receipt = stage_receipt(args.operation, output_path, output)
    if args.operation == "materialize-dispatches":
        receipt["next_operation_inputs"] = {"dispatches": str(output_path.resolve())}
    print(canonical_json(output if args.full_output else receipt))


def _run_operation(document: dict[str, Any], args: argparse.Namespace) -> int:  # noqa: C901, PLR0912
    if args.operation in {"persist-worker-payload", "review-worker-payload-write", "publish-worker-payload"}:
        return _run_worker_payload_operation(document, args)
    if args.operation in {"compile-independent-review", "compile-review", "compile-validation"}:
        if args.operation in {"compile-review", "compile-validation"}:
            payload = document.get("payload")
            schema_path = _review_payload_schema(document["dispatch"]) if args.operation == "compile-review" else _VALIDATION_PAYLOAD_SCHEMA
            require_schema(payload, schema_path)
        if args.operation == "compile-review":
            content, metadata = compile_review(document)
        elif args.operation == "compile-validation":
            content, metadata = compile_validation(document)
        else:
            content, metadata = compile_independent_payload(document)
        _write_bytes_once(args.artifact, content)
        _write_text_once(args.metadata, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        _print_operation_result(
            args,
            args.metadata,
            {**metadata, "artifact_path": str(args.artifact), "metadata_path": str(args.metadata), "status": metadata["evidence"]["status"]},
        )
        return 0
    if args.operation == "journal-append":
        event = append_journal_event(args.journal, document, _journal_request_from_args(args))
        print(canonical_json(event))
        return 0
    if args.operation == "compile-node":
        output = _compile_node_from_files(document, args)
        _print_operation_result(args, args.output, output)
        return 0
    if args.operation in {"materialize-dispatches", "schedule-ready"}:
        output = (
            materialize_dispatches(document, operation_output_path=args.output)
            if args.operation == "materialize-dispatches"
            else schedule_ready(document, args)
        )
        _print_operation_result(args, args.output, output)
        return 0
    output = _json_operation_output(document, args)
    output_path = args.output
    if args.operation == "next-ready" and args.output_dir is not None:
        output_directory = args.output_dir.resolve()
        output_directory.mkdir(parents=True, exist_ok=True)
        if not output_directory.is_dir():
            msg = f"next-ready output path is not a directory: {output_directory}"
            raise ValueError(msg)
        generation = _required_int(cast("dict[str, Any]", output["journal"]), "event_count")
        identity = digest_bytes(canonical_json(output).encode()).removeprefix("sha256:")[:16]
        output_path = output_directory / f"next-ready.{generation:06d}.{identity}.json"
        output["output_generation"] = generation
        output["output_path"] = str(output_path)
    output_text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.operation in {"recover-validation-launch", "recover-validation-execution", "reconcile-validation-requirements"}:
        _write_bytes_atomically_once(output_path, output_text.encode(), mode=0o644)
    else:
        _write_text_once(output_path, output_text)
    _print_operation_result(args, output_path, output)
    return 2 if args.operation == "finalize-proof" and output["status"] != "complete" else 0


def main(argv: list[str] | None = None) -> int:
    """Run one deterministic review-graph compiler operation."""
    args = _argument_parser().parse_args(argv)
    document: object = None
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            msg = "input root must be an object"
            raise TypeError(msg)
        operation_document = _operation_document(document, args.operation)
        require_schema_definition(operation_document, _RUNTIME_OPERATION_INPUT_SCHEMA, args.operation)
        usage_ledger = os.environ.get("REVIEW_GRAPH_USAGE_LEDGER", "")
        if usage_ledger:
            return measure_call(
                lambda: _run_operation(operation_document, args),
                Path(usage_ledger),
                stage=f"runtime:{args.operation}",
                scope_digest=usage_digest(operation_document),
            )
        return _run_operation(operation_document, args)
    except (ExecutableNotFoundError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, subprocess.SubprocessError) as error:
        if isinstance(error, WorkerPayloadWriteError):
            review = error.artifact_write_review
            output = {
                "schema_version": 1,
                "status": "blocked",
                "error": "artifact-write-blocked",
                "message": str(error),
                "node_id": review["node_id"],
                "worker_payload_path": review["worker_payload_path"],
                "worker_payload_digest": review["payload_digest"],
                "worker_payload_byte_count": review["payload_byte_count"],
                "approval_identity": review["approval_identity"],
                "artifact_write_review_reference": error.review_reference,
                "artifact_write_review": review,
            }
            print(canonical_json(_worker_payload_cli_output(output, full_output=args.full_output)), file=sys.stderr)
        elif isinstance(error, SchemaValidationError):
            attempt = document.get("handoff_attempt", 1) if isinstance(document, dict) else 1
            retry_allowed = isinstance(attempt, int) and not isinstance(attempt, bool) and attempt == 1
            output = {**error.as_dict(), "handoff_attempt": attempt, "maximum_handoff_attempts": 2, "retry_allowed": retry_allowed}
            print(canonical_json(output), file=sys.stderr)
        else:
            print(f"review_graph_runtime: {format_exception_diagnostics(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
