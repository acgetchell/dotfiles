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
import tarfile
import tempfile
import time
import tomllib
from collections import Counter
from contextlib import nullcontext, suppress
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from capture_scope import captured_head_changes
from research_repo_tools.process import ExecutableNotFoundError, format_exception_diagnostics, run_command_bytes
from review_graph_bench import benchmark_identity, benchmark_recipes, equivalent_recipe
from review_graph_bootstrap import bootstrap_document
from review_graph_commit import (
    commit_node_reasons,
    history_files,
    native_target,
    pin_independent_rechecks,
    reconciliation_policy,
    replacement_native_units,
    verify_commit_identity,
    verify_live_commit,
    verify_native_results,
)
from review_graph_continuation import MissingIntermediateCapture, NextReadyAction
from review_graph_control import control_marker_paths, extend_run_control, read_control_file, require_run_control, run_control_lock, verify_run_control
from review_graph_coverage import (
    combined_findings,
    coverage_decision_report,
    coverage_decisions,
    coverage_diagnostics,
    coverage_execution_view,
    reused_dependency_paths,
    reused_paths,
    validate_coverage_units,
)
from review_graph_doi import captured_doi_inputs, captured_software_inputs, inspect_canonical_recheck
from review_graph_executor import executor_permissions, remedied_features
from review_graph_git import (
    audit_git_context,
    discovery_reconciliation,
    intervening_metadata_blockers,
    metadata_audit_blockers,
    refresh_comparison_scope,
    validate_git_dependencies,
)
from review_graph_git_objects import GitPathIdentity
from review_graph_handoffs import audit_observations, validation_observations
from review_graph_hosted import hosted_coverage
from review_graph_independent import CHECK_LABELS, SCHEMA as _INDEPENDENT_PAYLOAD_SCHEMA, render_independent_payload
from review_graph_instruction_delta import reconcile_instructions, retained_input_texts
from review_graph_integrity import canonical_json, digest_bytes
from review_graph_isolation import ISOLATION_INSTRUCTIONS, IsolationPublicationError, IsolationViolationError, forbidden_artifacts, isolation_violations
from review_graph_lifecycle import ComprehensiveRestart, RepairBudgetExtension, ReviewLifecycle, lifecycle_from_document
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
    ValidationRequirementBinding,
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
from review_graph_provenance import independent_scope_body, metadata_transition_reference, review_scope_body, worker_payload_reference
from review_graph_read_provenance import MissingReadProvenanceError, bind_runtime_reads, normalized_read_provenance
from review_graph_reads import source_read_operands
from review_graph_receipts import artifact_reference, stage_receipt
from review_graph_repair_followup import repair_origin, verify_followup_finding, verify_followup_origin
from review_graph_requirement_delta import reassessment_candidates, reconcile_requirements, verify_reassessment_candidates
from review_graph_results import EvaluationBoundaryError, EvaluationRejection, RejectionKind, parse_json_object
from review_graph_reuse import (
    SNAPSHOT_FORMAT,
    AuditInputIdentity,
    AuditReuseTransition,
    CommitHandoffTransition,
    ExternalMetadataTransition,
    ExternalSourceTransition,
    InterleavedRepairTransition,
    ReuseInputError,
    metadata_states,
    metadata_transition,
    source_snapshot,
    verify_reuse_inputs,
)
from review_graph_scheduling import select_execution_lanes
from review_graph_schema import SchemaDiagnostic, SchemaValidationError, require_schema, require_schema_definition
from review_graph_session import current_execution_context, runtime_command, verify_current_snapshot
from review_graph_source_change import verify_live_source
from review_graph_synthesis import synthesis_fields, validate_synthesis
from review_graph_timing import timing_blocker, timing_documents, timing_prerequisite
from review_graph_usage import digest as usage_digest, measure_call
from review_graph_validation import ArtifactIdentity, ValidationPayload, ValidationRecord, VerifiedValidationRecord, bind_validation_payload
from review_graph_validation_contracts import ContractBinding, load_contract_binding, validation_reuse_prerequisite
from review_graph_validation_outputs import changed_identity_fields, obligation_identity
from review_graph_views import execution_view_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from review_graph_reuse import ReviewSourceSnapshot

_READ_ONLY_MODES = frozenset({"audit", "revalidation", "synthesis"})
_REVIEW_MODES = _READ_ONLY_MODES | {"fix"}
_REVIEW_STATUSES = frozenset({"blocked", "completed", "no-findings"})
_SEVERITIES = frozenset({"P0", "P1", "P2", "P3"})
_JOURNAL_STATUSES = frozenset({"accepted", "awaiting-replan", "blocked", "in-flight", "invalidated"})
_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references" / "schemas"
_PLANNING_INPUT_SCHEMA = _SCHEMA_ROOT / "planning-input-v1.schema.json"
_REVIEW_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "review-payload-v1.schema.json"
_SYNTHESIS_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "synthesis-payload-v1.schema.json"
_VALIDATION_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "validation-payload-v3.schema.json"
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
                (f"- External metadata transitions reference: {canonical_json(metadata_transition_reference(evidence.fingerprints.metadata_transitions))}",)
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
        **normalized_read_provenance(expectation.audit_input_identity),
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
    if violations := isolation_violations(dispatch, payload):
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
    identity = parse_json_object(content)
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
    reused = set(reused_paths(_reconciled_coverage(dispatch, payload)))
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
    if dispatch["mode"] not in {"audit", "independent-review"}:
        return None
    runtime_inputs, protocol_commands = bind_runtime_reads(dispatch, payload)
    context = _reconciled_coverage(dispatch, payload)
    inherited = reused_paths(context)
    if inherited and context is not None:
        proof = _coverage_proof(context)
        _kind, original, _evidence, _content, _record = _load_evidence_source(proof, require_normalized=True)
        if isinstance(original, ReviewEvidenceExpectation) and original.audit_input_identity is not None:
            runtime_inputs = tuple(sorted(set(runtime_inputs) | set(original.audit_input_identity.runtime_inputs)))
    instruction_paths = _text_list(dispatch, "instruction_paths")
    instruction_digests = tuple((path, _file_identity_digest(path)) for path in instruction_paths)
    if "instruction_digests" in dispatch and instruction_digests != _string_pairs(dispatch, "instruction_digests"):
        msg = "audit instructions changed since materialization"
        raise ValueError(msg)
    return AuditInputIdentity(
        _text_list(dispatch, "owned_paths"),
        _text_list(payload, "files_inspected"),
        _text_list(payload, "nearby_contract_owners"),
        instruction_digests,
        retained_input_texts(Path(dispatch["repository_root"]), instruction_paths, payload) if "repository_root" in dispatch else (),
        runtime_inputs,
        protocol_commands,
        tuple(sorted({path for command in payload.get("commands_executed", []) for path in source_read_operands(command) or ()})),
        inherited,
        reused_dependency_paths(context),
    )


def _reconciled_coverage(dispatch: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    has_reconciliation = bool(payload.get("instruction_reconciliations") or payload.get("validation_reassessments"))
    if has_reconciliation:
        require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
    bound = _publication_dispatch(dispatch) if has_reconciliation and "compiler_preflight" in dispatch else dispatch
    fresh = bool(bound and bound.get("fresh_context"))
    context = reconcile_instructions(dispatch.get("coverage_reuse"), payload, fresh=fresh)
    return reconcile_requirements(context, payload, fresh=fresh)


def _validate_review_coverage_partitions(dispatch: dict[str, Any], payload: dict[str, Any]) -> None:
    """Apply the same partition contract before publication and compilation."""
    if not payload.get("coverage_units"):
        return
    if dispatch.get("mode") != "audit" or dispatch.get("coverage_reuse") is not None:
        msg = "coverage partitions apply only to complete fresh audits"
        raise ValueError(msg)
    owned = _text_list(dispatch, "owned_paths")
    try:
        require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
    except SchemaValidationError as error:
        diagnostics = tuple(
            SchemaDiagnostic("$.coverage_units", "coverage", message, "complete coverage partition") for message in coverage_diagnostics(payload, owned)
        )
        raise SchemaValidationError(error.schema_id, (*error.diagnostics, *diagnostics)) from error
    validate_coverage_units(payload, owned)


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
    coverage_reuse = _reconciled_coverage(dispatch, payload)
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
    compact_scope = mode == "audit" and (bool(audit_inputs and audit_inputs.inherited_paths) or len(scope_body.encode()) > MAX_NATIVE_SECTION_BYTES)
    if compact_scope:
        require_schema(payload, _REVIEW_PAYLOAD_SCHEMA)
        scope_body = review_scope_body(payload, mode=mode, audit_inputs=audit_inputs, coverage_reuse=coverage_reuse, compact=True)
    requirement_ids = _text_list(dispatch, "requirement_ids")
    predecessor_evidence_ids = _text_list(dispatch, "predecessor_evidence_ids")
    evidence_id = _required_text(dispatch, "evidence_id")
    artifact_id = _required_text(dispatch, "artifact_id")
    fingerprints = _dispatch_fingerprints(dispatch)
    _verify_audit_metadata({**payload, **normalized_read_provenance(audit_inputs)}, fingerprints, coverage_reuse)
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
    audit_inputs = _compiled_audit_inputs(dispatch, _canonical_worker_payload(native_content))
    if audit_inputs is not None:
        sections["## Scope Inspected"] = independent_scope_body(sections["## Scope Inspected"], audit_inputs, section_limit=MAX_NATIVE_SECTION_BYTES)
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
        audit_input_identity=audit_inputs,
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
                (f"- External metadata transitions reference: {canonical_json(metadata_transition_reference(fingerprints.metadata_transitions))}",)
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
    context = _canonical_worker_payload(content) if b"- Canonical worker payload: " in content else {}
    return {
        **{key: context[key] for key in ("commands_executed", "git_dependencies", "git_sensitive", "nearby_contract_owners") if key in context},
        **normalized_read_provenance(expectation.audit_input_identity),
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
        _string_pairs(raw, "retained_inputs") if "retained_inputs" in raw else (),
        _string_pairs(raw, "runtime_inputs") if "runtime_inputs" in raw else (),
        _string_tuple(raw, "protocol_commands") if "protocol_commands" in raw else (),
        _string_tuple(raw, "command_read_paths") if "command_read_paths" in raw else (),
        _string_tuple(raw, "inherited_paths") if "inherited_paths" in raw else (),
        _string_tuple(raw, "inherited_dependency_paths") if "inherited_dependency_paths" in raw else (),
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
                (f"- External metadata transitions reference: {canonical_json(metadata_transition_reference(evidence.fingerprints.metadata_transitions))}",)
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


def _validation_normalized_record(
    payload: dict[str, Any], evidence: ValidationEvidence, capture: dict[str, Any] | None = None, *, contract_binding: ContractBinding | None = None
) -> dict[str, Any]:
    record = {
        "schema_version": 3,
        **({"failure_kind": payload["failure_kind"]} if "failure_kind" in payload else {}),
        **({"git_dependencies": payload["git_dependencies"]} if "git_dependencies" in payload else {}),
        **({"native_ci": payload["native_ci"]} if "native_ci" in payload else {}),
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
    if capture is not None and capture.get("repository_state_format") == SNAPSHOT_FORMAT:
        inputs = source_snapshot(capture)
        inputs.verify()
        if inputs.source_state != evidence.fingerprints.after:
            msg = "validation source capture differs from its observed source state"
            raise ValueError(msg)
        record["source_inputs"] = json.loads(canonical_json(asdict(inputs)))
        selections = [
            {"command": item["command"], "algorithm": item["selection_algorithm"], "paths": list(inputs.repository_selection_paths or ())}
            for item in payload.get("git_dependencies", [])
            if item["kind"] == "input-selection"
        ]
        if selections:
            record["input_selection_bindings"] = selections
        if contract_binding is not None:
            record["contract_binding"] = contract_binding.to_document()
    inputs = captured_software_inputs(record, capture) if capture is not None else {}
    if inputs:
        record["captured_software_inputs"] = inputs
    doi_inputs = captured_doi_inputs(record, capture) if capture is not None else {}
    if doi_inputs:
        record["captured_doi_inputs"] = doi_inputs
    return record


def _workspace_path(path: str, repository_root: Path, *, follow_symlinks: bool = True) -> Path:
    candidate = Path(path)
    absolute = candidate if candidate.is_absolute() else repository_root / candidate
    return absolute.resolve(strict=False) if follow_symlinks else absolute


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


def _workspace_content_digest(path: Path, *, declared_cache: bool = False) -> tuple[bool, str, str]:
    """Bound declared cache directories while retaining file and symlink identities."""
    if not path.exists() and not path.is_symlink():
        return False, digest_bytes(b"absent"), "absent-v1"
    if path.is_symlink():
        return True, digest_bytes(f"symlink:{path.readlink()}".encode()), "symlink-target-v1"
    if path.is_file():
        return True, digest_bytes(path.read_bytes()), "content-sha256-v1"
    if not path.is_dir():
        return True, digest_bytes(f"special:{path.stat().st_mode}".encode()), "special-metadata-v1"
    if declared_cache or path.name in _BOUNDED_WORKSPACE_DIRECTORY_NAMES:
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
        status = _git_path_status(repository_root, resolved)
        artifact = approved.get(raw_path)
        declared_cache = (
            artifact is not None and artifact.kind == "cache" and artifact.repository_status == status and status in {"ignored", "outside-repository"}
        )
        source = _workspace_path(raw_path, repository_root, follow_symlinks=False)
        exists, digest, snapshot_mode = _workspace_content_digest(source, declared_cache=declared_cache)
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
    try:
        require_schema(payload, _VALIDATION_PAYLOAD_SCHEMA)
        parsed_payload = ValidationPayload.from_raw(payload)
    except (ValueError, TypeError) as error:
        msg = "compiled validation artifact failed verification: " + str(error)
        raise ValueError(msg) from error
    raw_unit = dispatch.get("validation_unit")
    if not isinstance(raw_unit, dict):
        msg = "compile-validation dispatch requires validation_unit"
        raise TypeError(msg)
    unit = _validation_unit(raw_unit)
    try:
        bind_validation_payload(parsed_payload, unit)
    except (ValueError, TypeError) as error:
        msg = "compiled validation artifact failed verification: " + str(error)
        raise ValueError(msg) from error
    status = parsed_payload.status.value
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
    verify_native_results(payload, native_target(fingerprints.metadata_transitions, unit.node_id))
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
        "## Reused Evidence": "none",
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
    capture = dispatch.get("source_capture")
    binding = (
        load_contract_binding(source_snapshot(capture), unit.commands, unit.working_directories)
        if isinstance(capture, dict) and capture.get("repository_state_format") == SNAPSHOT_FORMAT
        else None
    )
    normalized = _validation_normalized_record(payload, evidence, capture, contract_binding=binding)
    ValidationRecord.from_raw(normalized)
    return content, {
        "expectation": asdict(expectation),
        "evidence": asdict(evidence),
        "payload_digest": digest_bytes(canonical_payload.encode()),
        "artifact_digest": evidence.raw_result_digest,
        "normalized_record": normalized,
        **(
            {"source_capture": dispatch["source_capture"]}
            if any(key in normalized for key in ("source_inputs", "captured_software_inputs", "captured_doi_inputs"))
            else {}
        ),
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


def _audit_replacement_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Decode a complete history record without retaining caller-owned containers."""
    required = {
        "node_id",
        "skill_id",
        "requirement_ids",
        "reason",
        "source_state",
        "previous_plan_digest",
        "previous_journal_head",
        "invalidated_evidence_id",
        "replacement_node_ids",
        "preserved_files",
        "forbidden_artifacts",
    }
    if missing := required - raw.keys():
        msg = "audit replacement record is missing fields: " + ", ".join(sorted(missing))
        raise ValueError(msg)
    record: dict[str, Any] = {key: _required_text(raw, key) for key in ("node_id", "skill_id", "reason", "invalidated_evidence_id")}
    record["requirement_ids"] = list(_text_list(raw, "requirement_ids", required=True))
    record["source_state"] = list(_state(raw, "source_state"))
    record["previous_plan_digest"] = _sha256_digest(raw["previous_plan_digest"], "previous_plan_digest")
    record["previous_journal_head"] = None if raw["previous_journal_head"] is None else _sha256_digest(raw["previous_journal_head"], "previous_journal_head")
    mapping = raw["replacement_node_ids"]
    if not isinstance(mapping, dict) or not mapping or any(not isinstance(key, str) or not key.strip() for key in mapping):
        msg = "replacement_node_ids must be a non-empty node mapping"
        raise ValueError(msg)
    record["replacement_node_ids"] = {key: _required_text(mapping, key) for key in mapping}
    if record["node_id"] not in mapping or len(set(mapping.values())) != len(mapping) or set(mapping) & set(mapping.values()):
        msg = "replacement_node_ids must map the invalidated node to distinct fresh identities"
        raise ValueError(msg)
    preserved = _records(raw, "preserved_files")
    if not preserved:
        msg = "preserved_files must retain non-empty digest-bound audit history"
        raise ValueError(msg)
    record["preserved_files"] = [
        {"path": _required_text(item, "path"), "digest": _sha256_digest(item.get("digest"), "preserved_files digest")} for item in preserved
    ]
    record["forbidden_artifacts"] = list(_text_list(raw, "forbidden_artifacts", required=True))
    if not {item["path"] for item in record["preserved_files"]}.issubset(record["forbidden_artifacts"]):
        msg = "forbidden_artifacts must include all preserved audit history"
        raise ValueError(msg)
    return record


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
        audit_replacements=tuple(_audit_replacement_record(item) for item in _records(raw, "audit_replacements")),
        pre_review_validation_nodes=_string_tuple(raw, "pre_review_validation_nodes"),
        commit_handoffs=tuple(metadata_transition(item) for item in _records(raw, "commit_handoffs")),
        review_lifecycle=lifecycle_from_document(raw.get("review_lifecycle")),
        independent_review_after_audits=_required_bool({"policy": raw.get("independent_review_after_audits", False)}, "policy"),
        validation_exclusions=tuple(
            ValidationExclusion(
                originating_evidence_id=_required_text(item, "originating_evidence_id"),
                requirement_id=_required_text(item, "requirement_id"),
                requirement_digest=_sha256_digest(item.get("requirement_digest"), "requirement_digest"),
                reason=_required_text(item, "reason"),
            )
            for item in _records(raw, "validation_exclusions")
        ),
        validation_requirement_bindings=tuple(_validation_requirement_binding(item) for item in _records(raw, "validation_requirement_bindings")),
    )
    validate_validation_barrier(plan)
    _validation_binding_map(plan)
    return plan


def _read_json_object(path: Path) -> dict[str, Any]:
    return parse_json_object(path.read_bytes())


def _operation_document(document: dict[str, Any], operation: str) -> dict[str, Any]:
    """Accept a bootstrap bundle directly where it owns the operation input."""
    if operation == "schedule-ready" and "lifecycle_input" in document:
        return {**document["lifecycle_input"], "artifact_store": document["materialization_input"]["artifact_store"]}
    field = {"materialize-dispatches": "materialization_input", "routing-projection": "planning_input", "preflight-validation": "preflight_input"}.get(
        operation
    )
    if field is None and operation in {"compile-node", "finalize-proof", "report-delivery", "journal-append", "next-ready", "snapshot-workspace"}:
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
        if parse_json_object(references[0]) != worker_payload_reference(bound_payload):
            msg = "canonical worker payload reference differs from its bound metadata"
            raise ValueError(msg)
        return bound_payload
    if len(matches) != 1:
        msg = "compiled artifact must contain exactly one canonical worker payload"
        raise ValueError(msg)
    payload = parse_json_object(matches[0])
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
    if "worker_payload_path" in metadata and parse_json_object(Path(metadata["worker_payload_path"]).read_bytes()) != payload:
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
    if expectation.audit_input_identity is not None:
        expected["## Scope Inspected"] = independent_scope_body(
            expected["## Scope Inspected"], expectation.audit_input_identity, section_limit=MAX_NATIVE_SECTION_BYTES
        )
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


type EvidenceRecord = dict[str, Any] | VerifiedValidationRecord


def _record_document(record: EvidenceRecord) -> dict[str, Any]:
    """Export passive report fields; validation policy consumes the typed record."""
    return record.to_document() if isinstance(record, VerifiedValidationRecord) else record


_EVIDENCE_LOAD_STACK: ContextVar[tuple[str, ...]] = ContextVar("review_graph_evidence_load_stack", default=())


def _load_evidence_source(
    raw: dict[str, Any], *, require_normalized: bool = False
) -> tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, EvidenceRecord | None]:
    """Replay acyclic inheritance without treating historical reports as fresh reads."""
    path = str(Path(_required_text(raw, "metadata_path")).resolve())
    stack = _EVIDENCE_LOAD_STACK.get()
    if path in stack:
        msg = f"cyclic audit evidence inheritance: {path}"
        raise ValueError(msg)
    token = _EVIDENCE_LOAD_STACK.set((*stack, path))
    try:
        return _load_evidence_source_once(raw, require_normalized=require_normalized)
    finally:
        _EVIDENCE_LOAD_STACK.reset(token)


def _load_evidence_source_once(  # noqa: C901, PLR0912, PLR0915
    raw: dict[str, Any], *, require_normalized: bool = False
) -> tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, EvidenceRecord | None]:
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
        payload = _canonical_worker_payload(content)
        require_schema(payload, _VALIDATION_PAYLOAD_SCHEMA)
        if payload_bytes is not None:
            submitted = parse_json_object(payload_bytes)
            require_schema(submitted, _VALIDATION_PAYLOAD_SCHEMA)
            submitted_payload = ValidationPayload.from_raw(submitted)
            bind_validation_payload(submitted_payload, expectation.validation_unit)
            if {**submitted, "artifacts": payload.get("artifacts", [])} != payload:
                msg = "compiled validation payload differs from sealed worker bytes"
                raise ValueError(msg)
            observed_artifacts = {artifact["path"]: artifact for artifact in _records(payload, "artifacts")}
            if any(
                any(observed_artifacts.get(artifact["path"], {}).get(key) != value for key, value in artifact.items())
                for artifact in _records(submitted, "artifacts")
            ):
                msg = "sealed worker artifact claims differ from compiled observations"
                raise ValueError(msg)
        assessment = assess_validation_evidence(expectation, evidence)
        blockers = assessment.blockers
    if blockers:
        msg = f"evidence source failed verification {artifact_path}: " + "; ".join(blockers)
        raise ValueError(msg)

    if isinstance(expectation, ReviewEvidenceExpectation) and expectation.canonical_worker_payload is not None:
        bound_payload = _canonical_worker_payload(content, expectation=expectation)
        if metadata.get("payload_digest") != digest_bytes(canonical_json(bound_payload).encode()):
            msg = "bound canonical worker payload digest differs from metadata"
            raise ValueError(msg)
        if payload_bytes is not None and parse_json_object(payload_bytes) != bound_payload:
            msg = "bound canonical worker payload differs from sealed worker bytes"
            raise ValueError(msg)
        _validate_review_coverage_partitions(
            {**expectation_raw, "owned_paths": list(expectation.audit_input_identity.owned_paths) if expectation.audit_input_identity else []}, bound_payload
        )

    if isinstance(expectation, ReviewEvidenceExpectation) and isinstance(evidence, ReviewEvidence) and expectation.mode == "independent-review":
        _verify_independent_payload_binding(content, metadata, expectation, evidence)
    normalized = metadata.get("normalized_record")
    verified_validation: VerifiedValidationRecord | None = None
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
                reconcile_instructions(expectation.coverage_reuse, payload, fresh=evidence.fresh_context)
                reconcile_requirements(expectation.coverage_reuse, payload, fresh=evidence.fresh_context)
                _validate_audit_caveats(
                    {
                        "mode": expectation.mode,
                        "before_state": list(evidence.fingerprints.before),
                        "after_state": list(evidence.fingerprints.after),
                        "git_mutated": evidence.git_mutated,
                    },
                    payload,
                )
                _verify_audit_metadata(
                    {**payload, **normalized_read_provenance(expectation.audit_input_identity)}, evidence.fingerprints, expectation.coverage_reuse
                )
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
            verify_native_results(payload, native_target(evidence.fingerprints.metadata_transitions, evidence.node_id))
            payload_digest = digest_bytes(canonical_json(payload).encode())
            if metadata.get("payload_digest") != payload_digest:
                msg = f"worker payload digest does not match compiled artifact: {artifact_path}"
                raise ValueError(msg)
            binding = ContractBinding.from_raw(normalized["contract_binding"]) if "contract_binding" in normalized else None
            recomputed = _validation_normalized_record(payload, evidence, metadata.get("source_capture"), contract_binding=binding)
            require_schema(payload, _VALIDATION_PAYLOAD_SCHEMA)
            verified_validation = VerifiedValidationRecord(canonical_json(recomputed), expectation, evidence, content)
        if normalized != recomputed:
            msg = f"normalized record does not match compiled artifact: {metadata_path}"
            raise ValueError(msg)
    if (require_normalized or kind == "validation") and normalized is None:
        msg = f"synthesis requires compiler-derived normalized metadata: {metadata_path}"
        raise ValueError(msg)
    return kind, expectation, evidence, content, verified_validation if verified_validation is not None else normalized


def load_validation_record(*, metadata_path: Path, artifact_path: Path) -> VerifiedValidationRecord:
    """Load one standard handoff through the complete provenance trust boundary."""
    _kind, _expectation, _evidence, _content, record = _load_evidence_source(
        {"metadata_path": str(metadata_path), "artifact_path": str(artifact_path)}, require_normalized=True
    )
    if not isinstance(record, VerifiedValidationRecord):
        msg = "validation handoff paths must identify verified version 3 validation evidence"
        raise TypeError(msg)
    return record


def validation_applicability(record: VerifiedValidationRecord, *, target: ReviewSourceSnapshot, current_unit: ValidationUnit) -> list[dict[str, str]]:
    """Assess typed source/execution bindings and observe required artifact roots."""
    if any(not Path(directory).is_dir() for directory in current_unit.working_directories):
        return [
            {"reason_code": "validation-directory-unavailable", "reason": "A dispatched working directory is unavailable in the current execution context."}
        ]

    def observe(artifact: ArtifactIdentity) -> tuple[str, str]:
        path = Path(artifact.path)
        if not path.is_absolute():
            path = Path(target.repository_root) / path
        _exists, digest, mode = _workspace_content_digest(path, declared_cache=artifact.kind == "cache")
        return digest, mode

    return record.applicability_reasons(target, current_unit=current_unit, observe_artifact=observe)


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
    identities = [replace(candidate, source_state=transition.source_state) for candidate in candidates]
    snapshots = {snapshot.source_state: snapshot for snapshot in plan.reuse_source_snapshots}
    origin, target = snapshots.get(transition.source_state), snapshots.get(transition.target_state)
    if origin is not None and target is not None and unit.captured_paths == target.captured_scope_paths:
        origin.verify()
        target.verify()
        identities.extend(replace(candidate, source_state=origin.source_state, captured_paths=origin.captured_scope_paths) for candidate in candidates)
    original = next((identity for identity in identities if _planned_validation_digest(identity) == requirement["planned_validation_digest"]), None)
    output_binding = None
    if original is None:
        if origin is None or target is None:
            return None
        output_binding = _validation_output_relocation(transition, requirement, unit, origin, target)
        if output_binding is None:
            return None
        original = replace(unit, source_state=origin.source_state, captured_paths=tuple(output_binding["original_captured_paths"]))
    path_binding = (
        {"original_captured_paths": list(original.captured_paths), "replacement_captured_paths": list(unit.captured_paths)}
        if original.captured_paths != unit.captured_paths
        else None
    )
    return {
        "original_planned_validation_digest": requirement["planned_validation_digest"],
        "original_source_state": list(transition.source_state),
        "replacement_planned_validation_digest": _planned_validation_digest(unit),
        "replacement_source_state": list(unit.source_state),
        **({"capture_binding": path_binding} if path_binding is not None else {}),
        **({"output_binding": output_binding} if output_binding is not None else {}),
    }


def _validation_output_relocation(
    transition: AuditReuseTransition, requirement: dict[str, Any], unit: ValidationUnit, origin: ReviewSourceSnapshot, target: ReviewSourceSnapshot
) -> dict[str, Any] | None:
    """Verify the historical obligation by its sealed digest, retaining fresh checks."""
    digest = requirement["planned_validation_digest"]
    path = Path(transition.metadata_path).parent / f"planned-validation.{digest.removeprefix('sha256:')}.json"
    if not path.is_file() or path.is_symlink():
        return None
    content = _read_regular_file_no_follow(path)
    if digest_bytes(content) != digest:
        return None
    original = parse_json_object(content)
    current = _planned_validation_identity(unit)
    if original.get("source_state") != list(origin.source_state) or current["source_state"] != list(target.source_state):
        return None
    comparable = {**current, "source_state": original["source_state"]}
    if unit.captured_paths == target.captured_scope_paths and original.get("captured_paths") == list(origin.captured_scope_paths):
        comparable["captured_paths"] = original["captured_paths"]
    if obligation_identity(original, origin.repository_root) != obligation_identity(comparable, target.repository_root):
        return None
    return {
        "original_identity": {"path": str(path), "digest": digest},
        "original_captured_paths": original["captured_paths"],
        "changed_identity_fields": changed_identity_fields(original, current),
    }


def _validation_requirement_binding(raw: dict[str, Any]) -> ValidationRequirementBinding:
    """Parse an exact origin identity without accepting additional claims."""
    if set(raw) != {"originating_evidence_id", "requirement_id", "requirement_digest", "planned_requirement_id"}:
        msg = "validation requirement binding must name its exact origin, ID, digest, and planned ID"
        raise ValueError(msg)
    return ValidationRequirementBinding(
        originating_evidence_id=_required_text(raw, "originating_evidence_id"),
        requirement_id=_required_text(raw, "requirement_id"),
        requirement_digest=_sha256_digest(raw.get("requirement_digest"), "requirement_digest"),
        planned_requirement_id=_required_text(raw, "planned_requirement_id"),
    )


def _validation_binding_map(plan: GraphPlan) -> dict[tuple[str, str, str], ValidationRequirementBinding]:
    """Reject ambiguous origins and aliases before selecting execution units."""
    planned_ids = [requirement for unit in plan.coalesced_validation_units for requirement in unit.requirement_ids]
    if len(planned_ids) != len(set(planned_ids)):
        msg = "planned validation requirement IDs must be unique"
        raise ValueError(msg)
    bindings: dict[tuple[str, str, str], ValidationRequirementBinding] = {}
    for item in plan.validation_requirement_bindings:
        binding = _validation_requirement_binding(asdict(item))
        identity = (binding.originating_evidence_id, binding.requirement_id, binding.requirement_digest)
        if identity in bindings:
            msg = "validation requirement binding origins must be unique"
            raise ValueError(msg)
        if binding.planned_requirement_id not in planned_ids:
            msg = "validation requirement binding names an unknown planned requirement"
            raise ValueError(msg)
        bindings[identity] = binding
    return bindings


def _validation_requirement_unit(
    units: dict[str, tuple[ValidationUnit, str]], requirement_id: str, planned_digest: str | None
) -> tuple[ValidationUnit, str] | None:
    """Bind a new reviewer alias to one exact existing execution contract."""
    planned = units.get(requirement_id)
    if planned is not None or planned_digest is None:
        return planned
    matches = {unit.node_id: (unit, digest) for unit, digest in units.values() if unit.required and digest == planned_digest}
    return next(iter(matches.values()), None) if len(matches) == 1 else None


def _validation_reconciliation(plan: GraphPlan, records: Sequence[EvidenceRecord]) -> dict[str, Any]:
    """Bind discovered needs to exact command plans, never to a generic CI pass."""
    units = {requirement: (unit, _planned_validation_digest(unit)) for unit in plan.coalesced_validation_units for requirement in unit.requirement_ids}
    bindings = _validation_binding_map(plan)
    exclusions = {(item.originating_evidence_id, item.requirement_id, item.requirement_digest): item for item in plan.validation_exclusions}
    results: list[dict[str, Any]] = []
    blockers: list[str] = []
    for record in (item for item in records if isinstance(item, dict)):
        if record.get("status") not in {"completed", "no-findings"}:
            continue
        for requirement_id, requirement in _validation_records(record):
            digest = digest_bytes(canonical_json(requirement).encode())
            origin = _required_text(record, "evidence_id")
            binding = bindings.get((origin, requirement_id, digest))
            planned_id = binding.planned_requirement_id if binding is not None else requirement_id
            planned = _validation_requirement_unit(units, planned_id, requirement.get("planned_validation_digest"))
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
            commit_binding = _commit_validation_reference(plan, record, requirement, unit) if unit is not None else None
            if commit_binding is not None:
                compatible_digests.add(commit_binding["original_planned_validation_digest"])
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
                    **({"planned_requirement_id": planned_id} if binding is not None else {}),
                    **({"reuse_binding": reuse_binding} if reuse_binding is not None else {}),
                    **({"commit_handoff_binding": commit_binding} if commit_binding is not None else {}),
                }
            )
    return {"blockers": blockers, "requirements": sorted(results, key=lambda item: (item["requirement_id"], item["originating_evidence_id"]))}


def _commit_validation_reference(plan: GraphPlan, record: dict[str, Any], requirement: dict[str, Any], unit: ValidationUnit) -> dict[str, Any] | None:
    """Reconcile a retained audit's native obligation with its exact-commit replacement."""
    original_digest = requirement.get("planned_validation_digest")
    if original_digest is None:
        return None
    for transition in reversed(plan.commit_handoffs):
        if not isinstance(transition, CommitHandoffTransition):
            continue
        proof = transition.commit_handoff
        target = proof["native_ci"].get(unit.node_id)
        if target is None or unit.commands != tuple(target["commands"]):
            continue
        prior = _validation_unit(proof["previous_native_units"][unit.node_id])
        identity = proof["source_records"].get(record["evidence_id"])
        if identity != digest_bytes(canonical_json(record).encode()) or metadata_audit_blockers(record, transition):
            continue
        reuse_binding = _reused_validation_reference(plan, record, requirement, prior, None)
        if original_digest == _planned_validation_digest(prior) or reuse_binding is not None:
            return {
                "original_planned_validation_digest": original_digest,
                "replacement_planned_validation_digest": _planned_validation_digest(unit),
                "commit": transition.after.head,
                "reason": "The pending native obligation is superseded by checks of the exact reviewed commit.",
                **({"reuse_binding": reuse_binding} if reuse_binding is not None else {}),
            }
    return None


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
        **(
            {"validation_requirement_bindings": [asdict(item) for item in plan.validation_requirement_bindings]} if plan.validation_requirement_bindings else {}
        ),
        "validation_recoveries": list(plan.validation_recoveries),
        "audit_replacements": list(plan.audit_replacements),
        **({"commit_handoffs": [asdict(item) for item in plan.commit_handoffs]} if plan.commit_handoffs else {}),
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
    immutable_records: list[dict[str, Any]] = []
    for source in raw_sources:
        _kind, expectation, evidence, _content, normalized = _load_evidence_source(source, require_normalized=True)
        normalized = _record_document(normalized) if normalized is not None else None
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
        immutable_records.append(normalized)
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
        # Bind original evidence in bundle order, before bundle-only reuse/digest annotations.
        bundle["plan_context"] = _synthesis_plan_context(plan, sorted(immutable_records, key=lambda item: item["evidence_id"]))
        if document.get("external_metadata_transitions"):
            bundle["plan_context"]["external_metadata_transitions"] = document["external_metadata_transitions"]
    bundle["bundle_digest"] = digest_bytes(canonical_json(bundle).encode())
    return bundle


def _verified_reused_sources(plan: GraphPlan, source_state: tuple[str, str, str], *, check_current_inputs: bool = True) -> tuple[dict[str, str], ...]:
    """Reload immutable reused artifacts and recheck their current instructions."""
    sources: list[dict[str, str]] = []
    snapshots = {item.source_state: item for item in plan.reuse_source_snapshots}
    for transition in plan.audit_reuse_transitions:
        source = {"artifact_path": transition.artifact_path, "metadata_path": transition.metadata_path}
        _kind, expectation, evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        record = _record_document(record) if record is not None else None
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


def _schema_reference(path: Path, *, validation_reassessment: bool = False) -> dict[str, object]:
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
        shapes = ("coverage_units", "instruction_reconciliations", *(("validation_reassessments",) if validation_reassessment else ()))
        reference["optional_shapes"] = {name: _required_schema_shape(raw["properties"][name]) for name in shapes}
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


def _inspection_groups(plan: GraphPlan, source_state: tuple[str, str, str], artifact_store: Path, repository_root: Path) -> dict[str, dict[str, object]]:
    groups: dict[tuple[str, ...], list[str]] = {}
    for node in plan.actual_worker_nodes:
        if node.mode == "audit" and node.coverage:
            groups.setdefault(tuple(sorted(node.coverage)), []).append(node.node_id)
    output: dict[str, dict[str, object]] = {}
    for paths, node_ids in groups.items():
        observations: list[dict[str, object]] = []
        excerpts: list[dict[str, object]] = []
        remaining_bytes = 65536
        for index, path in enumerate(paths):
            candidate = (repository_root / path).resolve()
            if not candidate.is_relative_to(repository_root) or not candidate.is_file():
                observations = []
                break
            content = candidate.read_bytes()
            # Reserve a fair share for every remaining owned path. Broad context
            # cannot consume a narrower specialist group's source budget.
            limit = min(16384, remaining_bytes // (len(paths) - index))
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
            "source_excerpt_status": "available" if any(item["text"] for item in excerpts) else "empty-read-owned-files",
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
    root = Path(dispatch["repository_root"])
    required_owned, required_context = [], []
    for path in dispatch["required_read_paths"]:
        relative = Path(path).relative_to(root).as_posix() if Path(path).is_relative_to(root) else path
        if relative in dispatch["owned_paths"]:
            required_owned.append(relative)
        else:
            required_context.append(path)
    return {
        "owned_read": {"files_inspected": [owned], "commands_executed": [shlex.join(["cat", "--", owned])]},
        "context_read": {"nearby_contract_owners": [context], "commands_executed": [shlex.join(["cat", "--", context])]},
        "required_reads": {
            "files_inspected": required_owned,
            "nearby_contract_owners": required_context,
            "commands_executed": [shlex.join(["cat", "--", path]) for path in dispatch["required_read_paths"]],
        },
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
        " Missing inputs/evidence remain blocked, never empty success. On rejection, follow the typed recovery prerequisite and existing attempt limit; "
        "retry only the affected evaluation after correction. Preserve findings and failed checks."
    )
    provenance_text = (
        " dispatch.provenance_examples contains illustrative fragments, not performed work: merge only actual reads/commands, "
        "account for owned scope under the dispatch contract, and replace origin/main with the captured base when applicable. "
        "files_inspected is owned-only; nearby_contract_owners records inspected dependency/context paths. "
        "Read dispatch.required_read_paths and declare those actual reads before a completed submission; omissions fail before sealing. "
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
        "Run validation_observations.before capture_command then workspace_command before timed launches; repeat with .after afterwards. "
        " Omit artifacts: the runtime captures workspace status and artifact digests before and after execution. "
        "executions[].artifact_paths names only exact validation_unit.allowed_artifacts[].path roots, never generated child files. "
        "Use [] for no output or absent outputs. Child file paths may appear in evidence text; publication checks references before writing."
        " Each git_dependencies.command must name an exact executions[].command and occur in at most one declaration. "
        "Omit command for a dependency applying to the entire unit: Cargo packaging may use command-bound head plus command-less index. "
        "Correct metadata binding errors without rerunning commands; repository-owned contracts remain authoritative."
        " For worktree enumeration, declare kind=input-selection, the exact command, and "
        "selection_algorithm=git-ls-files-cached-others-exclude-standard-v1 only after confirming this selection algorithm; "
        "the runtime binds captured membership. Declare staged-blob, HEAD and history inputs separately."
        if contract == "compact-validation"
        else ""
    )
    audit_scope_text = (
        " For audits, scope_limitations is reserved exclusively for omitted dispatch-owned paths and must equal owned_paths minus "
        "files_inspected and runtime-proved reused paths. When coverage_reuse is present, inspect only recheck units, preserve their prior findings and "
        "reconcile original validation needs/handoffs; do not claim fresh reads of reused paths. Its verified execution view contains unit dependencies "
        "and original finding IDs attributed to evidence_id; proof_reference provides lazy access to the full proof when needed. "
        "For broad fresh audits, use optional coverage_units when "
        "you can partition by language/activity and affected contract with explicit whole-file dependencies and uncertainty: "
        "partition every owned path and every finding exactly once "
        "using one-based finding_indices, give each unit a unique unit_id, and account for every nearby_contract_owners path in dependency_paths. "
        'See payload_schema.optional_shapes.coverage_units; dependency_uncertainty="" means no uncertainty, and [] means no findings/dependencies. '
        "If omitted, the runtime derives one conservative whole-audit unit from all owned paths, findings and recorded dependencies. "
        "An instruction-only repair still requires fresh assessment of rules, commands, applicability and obligations; "
        "any material change reopens the entire derived unit. Unbound external reads remain reuse blockers. "
        "Source-discovery judgments must come from the captured "
        "files_inspected/nearby_contract_owners reads, independent of the staging split; undeclared commands remain conservative. "
        "Legacy git_sensitive=true always requires rechecking. "
        'Put validator-owned nonexecution in execution_facts=["validators-not-executed"]; use source-captures-match and git-not-mutated only when true. '
        "Put platform/evidence caveats in validation_limits bound to an explicit validation_requirements entry: delegated means the validator still owes "
        "that evidence, unavailable blocks readiness and failed reopens its owning contract. "
        "Put unresolved semantic/dependency questions in unresolved_uncertainties (kind, reason), "
        "or a single unit's dependency_uncertainty. Keep unknown caveats in limitations; these conservatively block reuse. Never omit truthful context."
        if dispatch.get("mode") == "audit"
        else ""
    )
    if dispatch.get("coverage_reuse", {}).get("validation_reassessment"):
        audit_scope_text += (
            " Submit validation_reassessments for every listed requirement, copying both supplied digests. "
            "Inspect the old/new execution contracts, native limitations and original handoffs; source-independent retains only proved source judgments, "
            "reinspect requires all owned-source reads, and uncertain blocks acceptance. No disposition reuses old validation success or waives current gates."
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
    return (ISOLATION_INSTRUCTIONS + " " if dispatch.get("fresh_context") and dispatch.get("mode") == "audit" else "") + (
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
    entry = parse_json_object(content)
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
    return parse_json_object(content)


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
        bind_validation_payload(ValidationPayload.from_raw(payload), unit)
        if payload.get("artifacts"):
            observed = capture_workspace_snapshot(dispatch)
            _validation_artifacts_body(payload, unit, _workspace_snapshot({"workspace_after": observed["records"]}, "workspace_after"))
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
        if isinstance(error, (MissingReadProvenanceError, EvaluationBoundaryError)):
            raise
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
        payload = parse_json_object(payload_bytes)
        schema = (
            _INDEPENDENT_PAYLOAD_SCHEMA
            if contract == "compact-independent-review"
            else (_review_payload_schema(contract_document) if contract == "compact-review" else _VALIDATION_PAYLOAD_SCHEMA)
        )
        if contract == "compact-review":
            # This boundary parses its schema before domain use and aggregates
            # independent coverage diagnostics for the same correction attempt.
            _validate_review_coverage_partitions(contract_document, payload)
        require_schema(payload, schema)
        bound = _publication_dispatch(contract_document)
        if bound is not None and (violations := isolation_violations(bound, payload)):
            raise IsolationViolationError("fresh-context review read another node's worker/report/evidence artifact: " + "; ".join(violations))
        if contract == "compact-independent-review":
            if "compiler_preflight" not in contract_document:
                msg = "structured independent publication requires its bound compiler preflight"
                raise EvaluationBoundaryError(RejectionKind.MISSING_EVIDENCE, msg)
        elif contract == "compact-review":
            _validate_audit_caveats(contract_document, payload)
            blockers = _review_scope_coverage_blockers(contract_document, payload, status=_required_text(payload, "status"))
            if blockers:
                msg = "worker payload failed owned-scope validation: " + "; ".join(blockers)
                raise EvaluationBoundaryError(RejectionKind.MISSING_EVIDENCE, msg)
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
            ValidationPayload.from_raw(payload)
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
        inherited = reused_paths(_reconciled_coverage(contract_document, payload))
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
        review["coverage_reuse_policy"] = (
            "existing-delta-proof"
            if contract_document.get("coverage_reuse")
            else "explicit-partition"
            if payload.get("coverage_units")
            else "derived-whole-audit"
        )
    return review


def _approved_worker_payload_write(
    contract_document: dict[str, Any], payload_bytes: bytes, approval_identity: str | None, *, candidate_is_write_target: bool = True
) -> dict[str, Any]:
    try:
        artifact_write_review = review_worker_payload_write(contract_document, payload_bytes, candidate_is_write_target=candidate_is_write_target)
    except IsolationViolationError as error:
        raise IsolationPublicationError(_retain_isolation_rejection(contract_document, payload_bytes, error)) from error
    except MissingReadProvenanceError as error:
        _retain_provenance_rejection(contract_document, payload_bytes, error)
        raise
    _require_isolation_budget(contract_document)
    if len(_provenance_attempts(contract_document)) >= 2:
        msg = "instruction provenance correction exhausted; retain failed attempts and leave this node blocked"
        raise ValueError(msg)
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
        "warnings": _validation_owner_warnings(contract_document, payload_bytes),
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
    _require_running_review(document)
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
    verify_run_control(plan.review_lifecycle.run_control, repository=Path(repository_root))
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
    catalog = load_routing_catalog(catalog_path, skill_roots=_continuation_skill_roots(plan))
    catalog_ids = sorted(entry.catalog_id for entry in catalog)
    handoff_destinations = [{"catalog_id": entry.catalog_id, "skill_id": entry.skill_id} for entry in sorted(catalog, key=lambda entry: entry.catalog_id)]
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
        plan_bytes = canonical_json(
            {
                "plan": asdict(plan),
                "source_state": list(source_state),
                "sources": reuse_sources,
                **({"external_metadata_transitions": document["external_metadata_transitions"]} if document.get("external_metadata_transitions") else {}),
            }
        ).encode()
        plan_path = artifact_store / "synthesis-publication-plan.json"
        _queue_materialized_write(pending_writes, plan_path, plan_bytes, mode=0o444)
        synthesis_plan_reference = {"path": str(plan_path), "digest": digest_bytes(plan_bytes)}
    dispatches: list[dict[str, Any]] = []
    isolation_entries = {
        node.node_id: (preserved_entries or {}).get(node.node_id)
        or {
            "artifact_path": str(artifact_store / f"{node.node_id}.{'validation' if node.mode == 'validation' else 'review'}.md"),
            **{
                field: str(artifact_store / f"{node.node_id}.{suffix}")
                for field, suffix in (
                    ("metadata_path", "evidence.json"),
                    ("worker_input_path", "worker-input.json"),
                    ("worker_execution_path", "execution.json"),
                    ("worker_payload_path", "worker-payload.json"),
                    ("worker_payload_contract_path", "worker-payload-contract.json"),
                )
            },
        }
        for node in plan.actual_worker_nodes
    }
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
        worker_payload_command_prefix = runtime_command(
            Path(__file__), "persist-worker-payload", "--input", str(worker_payload_contract_path), "--payload-stdin"
        )
        worker_payload_review_command = runtime_command(Path(__file__), "review-worker-payload-write", "--input", str(worker_payload_contract_path))
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
            "handoff_destinations": handoff_destinations,
            "instruction_digests": [[path, _file_identity_digest(path)] for path in instruction_paths],
            "instruction_paths": list(instruction_paths),
            "mode": node.mode,
            "selection_reason": "; ".join(node.selection_reasons) or f"planner selected {node.skill_id}",
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
                "publish_command": runtime_command(Path(__file__), "publish-worker-payload", "--input", str(worker_payload_contract_path)),
            },
            "worker_created": location == "worker",
        }
        if (execution_context := current_execution_context()) is not None:
            common["execution_context"] = execution_context
        if (snapshot_reference := verify_current_snapshot()) is not None:
            common["runtime_snapshot"] = snapshot_reference
        if node.mode in {"audit", "independent-review"}:
            if observations := audit_observations(common, worker_payload_contract_path):
                common["audit_observations"] = observations
            common["fresh_context_forbidden_artifacts"] = sorted(
                {
                    *forbidden_artifacts(node.node_id, isolation_entries),
                    *(path for replacement in plan.audit_replacements for path in replacement["forbidden_artifacts"]),
                }
            )
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
            common["timing_prerequisite"] = timing_prerequisite(worker_payload_contract_path, node.node_id)
            common["validation_observations"] = validation_observations(common, worker_payload_contract_path)
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
                if common.get("coverage_reuse", {}).get("validation_reassessment"):
                    common["payload_schema"] = _schema_reference(_REVIEW_PAYLOAD_SCHEMA, validation_reassessment=True)
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
            common["required_read_paths"] = sorted({node.skill_path, *instruction_paths, *node.static_references})
            common["provenance_examples"] = _worker_provenance_examples(common, line_bounds)
            runtime_paths = {*common["required_read_paths"], str(common["payload_schema"]["path"])}
            if shared := common.get("shared_inspection_evidence"):
                runtime_paths.add(shared["source_packet_path"])
            common["runtime_input_digests"] = [
                [path, digest_bytes(pending_writes[Path(path)][0]) if Path(path) in pending_writes else _file_identity_digest(path)]
                for path in sorted(runtime_paths)
            ]
            # These files are written atomically below; their exact bytes are bound
            # during compilation, after the publication contract verifies dispatch.
            common["protocol_input_paths"] = [
                str(artifact_store / f"{node.node_id}.worker-input.json"),
                str(artifact_store / f"{node.node_id}.execution.json"),
                str(worker_payload_contract_path),
            ]
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
            "worker_execution_path": str(artifact_store / f"{node.node_id}.execution.json"),
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
        _queue_materialized_write(pending_writes, Path(entry["worker_execution_path"]), execution_view_bytes(entry, worker_input_bytes), mode=0o444)
        dispatches.append(entry)
    output: dict[str, Any] = {"dispatches": dispatches, "plan_digest": _plan_digest(plan), "schema_version": 1, "source_state": list(source_state)}
    output["telemetry"] = {
        "worker_input_bytes": sum(len((json.dumps(entry, indent=2, sort_keys=True) + "\n").encode()) for entry in dispatches),
        "worker_prompt_bytes": sum(len(entry["worker_prompt"].encode()) for entry in dispatches),
        "worker_execution_bytes": sum(len(execution_view_bytes(entry, (json.dumps(entry, indent=2, sort_keys=True) + "\n").encode())) for entry in dispatches),
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


def _epoch_scoped_plan(plan: GraphPlan, epoch: int, *, suffix: str = "") -> GraphPlan:
    """Give every executable identity a repair-epoch namespace."""
    prefix = f"repair-epoch-{epoch:03d}{suffix}-"
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
    if capture.get("repository_state_format") == SNAPSHOT_FORMAT:
        parsed = source_snapshot(capture)
        parsed.verify()
        paths = dict(parsed.repository_path_fingerprints)
        if not set(parsed.captured_scope_paths) <= paths.keys():
            msg = f"{label} path fingerprints do not cover captured_scope_paths"
            raise ValueError(msg)
        return paths
    raw = capture.get("repository_path_fingerprints")
    if not isinstance(raw, dict) or any(not isinstance(path, str) for path in raw):
        msg = f"{label} requires repository_path_fingerprints; capture before repairing with the current capture_scope.py"
        raise ValueError(msg)
    paths = _normalized_repository_paths(tuple(raw), label=f"{label}.repository_path_fingerprints")
    if tuple(raw) != paths:
        msg = f"{label}.repository_path_fingerprints requires canonical repository paths"
        raise ValueError(msg)
    for value in raw.values():
        if not isinstance(value, str):
            msg = f"{label}.repository_path_fingerprints must contain source identities"
            raise TypeError(msg)
        if value == "absent" or re.fullmatch(r"(?:submodule:)?[0-9a-f]{64}", value):
            continue
        GitPathIdentity.parse(value)
    if not set(_text_list(capture, "captured_scope_paths")) <= set(paths):
        msg = f"{label} path fingerprints do not cover captured_scope_paths"
        raise ValueError(msg)
    return {path: value for path, value in raw.items() if isinstance(value, str)}


def _mutation_path_delta(
    document: dict[str, Any], previous: dict[str, Any], current: dict[str, Any], interleaved: InterleavedRepairTransition | None = None
) -> tuple[str, ...]:
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
    if old_index != new_index and interleaved is None:
        msg = "repair epoch mutated the Git index; for attributed interleaved maintainer staging, supply interleaved_staging with the two actual captures"
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
    if ("journal_path" in document) != ("dispatches_path" in document):
        msg = "repair history requires journal_path and dispatches_path together"
        raise EvaluationBoundaryError(RejectionKind.MISSING_INPUT, msg)
    if document.get("journal_path") and document.get("dispatches_path"):
        state = _state(document, "source_state")
        events, statuses, _head = read_execution_journal(Path(document["journal_path"]), plan=plan, source_state=state)
        if any(status == "in-flight" for status in statuses.values()):
            msg = "repair transition requires quiescent execution"
            raise ValueError(msg)
        entries = _dispatches_by_node(_read_json_object(Path(document["dispatches_path"])), plan=plan, source_state=state)
        accepted, _accepted_records = _accepted_journal_sources(plan, state, events, entries)
        sources = {canonical_json(source): source for source in [*_records(document, "sources"), *accepted.values()]}
        document = {**document, "sources": list(sources.values())}
    by_id = {node.node_id: node for node in plan.actual_worker_nodes}
    result: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    reused_ids = {evidence_id for _, evidence_id in plan.exact_reused_review_evidence}
    for source in _evidence_sources(document, plan, check_current_inputs=False):
        loaded = _load_evidence_source(source, require_normalized=True)
        _kind, expectation, evidence, _content, normalized = loaded
        normalized = _record_document(normalized) if normalized is not None else None
        node = by_id.get(evidence.node_id)
        if (node is None and evidence.evidence_id not in reused_ids) or evidence.node_id in result:
            msg = f"mutation sources contain an unknown or duplicate node: {evidence.node_id}"
            raise ValueError(msg)
        if node is not None:
            _verified_journal_evidence(source, plan=plan, node=node, source_state=_state(document, "source_state"), loaded=loaded)
        elif isinstance(expectation, ReviewEvidenceExpectation) and isinstance(evidence, ReviewEvidence):
            blockers = review_source_state_blockers(plan, expectation, evidence, _state(document, "source_state"))
            if blockers:
                msg = "prior reused audit is not valid for the preceding capture: " + "; ".join(blockers)
                raise ValueError(msg)
        if normalized is None:
            msg = f"mutation source lacks normalized evidence: {evidence.node_id}"
            raise ValueError(msg)
        result[evidence.node_id] = (source, _record_document(normalized))
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
    return ("invalidated-inputs", "Owned inputs, routing, or a predecessor changed.") if invalidated else None


def _failed_validation_limits(record: dict[str, Any]) -> tuple[str, str] | None:
    """Retain actual failures as owning dispositions after assessing source deltas."""
    failed = [_required_text(limit, "requirement_id") for limit in _records(record, "validation_limits") if limit["status"] == "failed"]
    return ("validation-evidence-failed", "Recheck the owning contract for failed requirements: " + ", ".join(failed)) if failed else None


def _carry_forward_audits(  # noqa: C901, PLR0912, PLR0913, PLR0915 - preserve provenance and report every reuse rejection.
    document: dict[str, Any],
    old_plan: GraphPlan,
    candidate_plan: GraphPlan,
    planning_input: dict[str, Any],
    *,
    invalidated: tuple[str, ...],
    sources: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    observed_metadata_transition: ExternalMetadataTransition | None = None,
) -> tuple[GraphPlan, list[dict[str, Any]]]:
    """Convert only proven unchanged leaves into non-executable routed reuse."""
    decisions: dict[str, dict[str, Any]] = {
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
            if isinstance(error, ReuseInputError):
                decisions[node_id]["rejected_inputs"] = error.rejected_inputs
            continue
        if failed := _failed_validation_limits(record):
            decision(node_id, *failed)
            continue
        reconciliation = _validation_reconciliation(
            replace(candidate_plan, audit_reuse_transitions=(transition,), reuse_source_snapshots=(origin, target)), [record]
        )
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
        skill_roots=_continuation_skill_roots(old_plan),
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
    proof = parse_json_object(content)
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
    if {key: value for key, value in context.items() if key not in {"instruction_reconciliations", "validation_reassessments"}} != expected:
        msg = "coverage execution view differs from original immutable findings or verified unit decisions"
        raise ValueError(msg)
    return proof


def _verify_delta_requirements(context: dict[str, Any], dispatch: dict[str, Any]) -> None:
    """Bind reassessment to the source proof and the current dispatched validator."""
    if not context.get("validation_reassessment"):
        return
    origin, target = source_snapshot(context["origin"]), source_snapshot(context["target"])
    verify_reassessment_candidates(context, repository_root=target.repository_root)
    for candidate in context.get("validation_reassessment", []):
        before, after = candidate["original_execution_identity"], candidate["replacement_execution_identity"]
        if (before["source_state"], before["captured_paths"], after["source_state"], after["captured_paths"]) != (
            list(origin.source_state),
            list(origin.captured_scope_paths),
            list(target.source_state),
            list(target.captured_scope_paths),
        ):
            msg = "validation reassessment differs from its captured source identities"
            raise ValueError(msg)
        if "command_policy" in dispatch:
            current = [
                item for item in _records(dispatch["command_policy"], "planned_validation_units") if candidate["requirement_id"] in item["requirement_ids"]
            ]
            if len(current) != 1 or current[0]["planned_validation_digest"] != candidate["replacement_planned_validation_digest"]:
                msg = "validation reassessment differs from the current dispatched requirement"
                raise ValueError(msg)


def _verify_delta_context(context: dict[str, Any], dispatch: dict[str, Any]) -> None:
    """Replay the original immutable partition proof at materialization and acceptance."""
    context = _coverage_proof(context)
    if dispatch.get("mode") != "audit":
        msg = "delta coverage applies only to audit mode"
        raise ValueError(msg)
    origin, target = source_snapshot(context["origin"]), source_snapshot(context["target"])
    _verify_delta_requirements(context, dispatch)
    if target.source_state != _state(dispatch, "source_state"):
        msg = "delta coverage target differs from the dispatched source state"
        raise ValueError(msg)
    _kind, expectation, evidence, _content, record = _load_evidence_source(context, require_normalized=True)
    record = _record_document(record) if record is not None else None
    inputs = expectation.audit_input_identity if isinstance(expectation, ReviewEvidenceExpectation) else None
    if not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence) or inputs is None or record is None:
        msg = "delta coverage requires compiler-bound audit input identities"
        raise ValueError(msg)
    if _audit_reuse_blocker(record, invalidated=False) is not None or _failed_validation_limits(record) is not None:
        msg = "delta coverage origin must have complete verified coverage without unresolved limitations"
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
    retained_after = {delta["path"]: delta["after"] for unit in context["units"] for delta in unit.get("input_deltas", [])}
    decisions = coverage_decisions(record, origin, target, inputs, transition, retained_after=retained_after)
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
    if not any(unit["disposition"] in {"reused", "instruction-review"} for unit in context["units"]):
        msg = "delta coverage has no reusable units"
        raise ValueError(msg)


def _blocked_coverage_reviews(record: dict[str, Any], candidate: GraphPlan) -> list[dict[str, Any]] | None:
    """Expose why a partition, or an audit without one, cannot support reuse."""
    blocker = _audit_reuse_blocker(record, invalidated=False)
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
            units = coverage_decisions(record, audit_origin, target, inputs, transition)
            if failed := _failed_validation_limits(record):
                units = [
                    {**unit, "disposition": "recheck", "reason_code": failed[0], "reason": failed[1]}
                    if unit["disposition"] in {"reused", "instruction-review"}
                    else unit
                    for unit in units
                ]
            reconciliation = _validation_reconciliation(
                replace(candidate, audit_reuse_transitions=(transition,), reuse_source_snapshots=(audit_origin, target)), [record]
            )
            reassessment = (
                reassessment_candidates(
                    record["validation_requirements"],
                    {requirement: _planned_validation_identity(unit) for unit in previous.coalesced_validation_units for requirement in unit.requirement_ids},
                    {requirement: _planned_validation_identity(unit) for unit in candidate.coalesced_validation_units for requirement in unit.requirement_ids},
                    target.repository_root,
                )
                if reconciliation["blockers"]
                else None
            )
            if reconciliation["blockers"] and reassessment is None:
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
            reviews.append(
                {
                    "node_id": node.node_id,
                    "evidence_id": evidence.evidence_id,
                    "units": coverage_decision_report(units, audit_origin, target),
                    **(
                        {"reason_code": "validation-reassessment-required", "reason": "Fresh contract reassessment is required before accepting source reuse."}
                        if reassessment is not None
                        else {}
                    ),
                }
            )
            if not any(unit["disposition"] in {"reused", "instruction-review"} for unit in units):
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
                **({"validation_reassessment": reassessment} if reassessment is not None else {}),
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
    for reuse in _records(document.get("plan", {}), "audit_reuse_transitions"):
        if _state(reuse, "source_state") == state:
            inherited = tuple(metadata_transition(item) for item in _records(reuse, "metadata_transitions"))
            tail = inherited[-1].after.source_state if inherited else state
            for ordinal, transition in enumerate(transitions):
                if transition.before.source_state == tail:
                    return (*inherited, *transitions[ordinal:])
                if transition.before.source_state == _state(reuse, "target_state"):
                    snapshots = tuple(source_snapshot(item) for item in _records(document["plan"], "reuse_source_snapshots"))
                    origin = inherited[-1].after if inherited else next((snapshot for snapshot in snapshots if snapshot.source_state == state), None)
                    if origin is not None:
                        bridge = metadata_transition({"before": asdict(origin), "after": asdict(transition.before), "observed_source_only": True})
                        return (*inherited, bridge, *transitions[ordinal:])
            return inherited
    for ordinal, transition in enumerate(transitions):
        if transition.before.source_state == state:
            return transitions[ordinal:]
    return ()


def _current_metadata_state(document: dict[str, Any]) -> tuple[str, str, str]:
    transitions = tuple(metadata_transition(item) for item in _records(document, "external_metadata_transitions"))
    return metadata_states(_state(document, "source_state"), transitions)[-1]


def _metadata_evidence_blockers(document: dict[str, Any], records: Sequence[EvidenceRecord]) -> list[str]:
    if not document.get("external_metadata_transitions"):
        return []
    current = _current_metadata_state(document)
    transition = metadata_transition(document["external_metadata_transitions"][-1])
    blockers = []
    for record in records:
        report = _record_document(record)
        if tuple(report.get("observed_source_state", ())) != current and (
            reasons := _metadata_node_reasons(report.get("mode", "validation"), (), record, transition)
        ):
            blockers.append(f"Evidence requires revalidation after Git context changed: {report['evidence_id']}: {canonical_json(reasons)}")

    transitions = tuple(metadata_transition(item) for item in _records(document, "external_metadata_transitions"))
    for item in records:
        record = _record_document(item)
        if record.get("mode") == "validation":
            try:
                verify_native_results(record, native_target(transitions, record["node_id"]))
            except ValueError as error:
                blockers.append(str(error))
    return blockers


def _external_source_node_reasons(
    mode: str, predecessors: tuple[str, ...], record: dict[str, Any], transition: ExternalSourceTransition
) -> list[dict[str, str]]:
    """Require complete dependency proof before retaining a source judgment."""
    if (
        mode != "audit"
        or predecessors
        or any(record.get(key) for key in ("limitations", "scope_limitations", "unresolved_uncertainties"))
        or any(unit.get("dependency_uncertainty") for unit in record.get("coverage_units", []))
    ):
        return [{"reason_code": "external-source-review", "reason": "Dependent review or incomplete dependency evidence requires a current judgment."}]
    return metadata_audit_blockers(
        {
            **record,
            "nearby_contract_owners": sorted(
                {*record.get("nearby_contract_owners", []), *(path for unit in record.get("coverage_units", []) for path in unit["dependency_paths"])}
            ),
        },
        transition,
    )


def _metadata_node_reasons(mode: str, predecessors: tuple[str, ...], record: EvidenceRecord, transition: ExternalMetadataTransition) -> list[dict[str, str]]:  # noqa: PLR0911 - separate variant-specific applicability gates.
    """Keep fresh review, execution, and synthesis policies separate from audit dependencies."""
    if isinstance(record, VerifiedValidationRecord):
        reasons = validation_applicability(record, target=transition.after, current_unit=record.expectation.validation_unit)
        if isinstance(transition, CommitHandoffTransition) and record.evidence.node_id in transition.commit_handoff["native_ci"]:
            reasons.append({"reason_code": "native-exact-commit", "reason": "Hosted CI must attest to the new exact commit."})
        return reasons
    if mode == "validation":
        return [{"reason_code": "validation-unverified", "reason": "Validation applicability requires a verified version 3 record from the evidence loader."}]
    if isinstance(transition, ExternalSourceTransition):
        return _external_source_node_reasons(mode, predecessors, record, transition)
    if isinstance(transition, CommitHandoffTransition):
        return commit_node_reasons(mode, record, transition)
    if mode in {"audit", "independent-review"} and (
        transition.before.captured_scope_paths != transition.after.captured_scope_paths
        or (transition.before.base_ref, transition.before.merge_base) != (transition.after.base_ref, transition.after.merge_base)
    ):
        return [{"reason_code": "review-comparison-changed", "reason": "Review scope or comparison base changed; a current review is required."}]
    if (
        transition.before.head != transition.after.head
        and not isinstance(transition, CommitHandoffTransition)
        and (mode == "independent-review" or any(item.get("kind") == "source-discovery" for item in record.get("git_dependencies", [])))
    ):
        return [{"reason_code": "review-head-changed", "reason": "The comparison-based review must inspect the new Git context."}]
    if (
        mode == "independent-review"
        and record.get("status") in {"completed", "no-findings"}
        and "commands_executed" in record
        and not record.get("limitations")
    ):
        return metadata_audit_blockers(record, transition)
    policies = {
        "independent-review": "Fresh independent review must inspect the current change target.",
        "validation": "Validation execution and workspace evidence must bind to the current metadata state.",
        "synthesis": "Synthesis must consume the current accepted evidence bundle.",
    }
    if mode != "audit" or predecessors:
        return [{"reason_code": f"{mode}-policy", "reason": policies.get(mode, "Dependent evidence requires a current-state review.")}]
    return metadata_audit_blockers(record, transition)


def _metadata_resume_decisions(
    plan: GraphPlan, lifecycle: dict[str, str], records: dict[str, EvidenceRecord], transition: ExternalMetadataTransition
) -> list[dict[str, Any]]:
    """Explain both preserved evidence and work awaiting a current-state execution."""
    decisions = []
    inherited = {context["node_id"]: {"coverage_reuse": context} for context in plan.audit_delta_reviews}
    for node in plan.actual_worker_nodes:
        trusted = records.get(node.node_id, inherited.get(node.node_id, {}))
        reasons = _metadata_node_reasons(node.mode, node.predecessors, trusted, transition)
        record = _record_document(trusted)
        status = lifecycle.get(node.node_id, "pending")
        historical_gate = (
            node.node_id in plan.pre_review_validation_nodes
            and status == "accepted"
            and isinstance(trusted, VerifiedValidationRecord)
            and {reason["reason_code"] for reason in reasons} == {"validation-contract-unavailable"}
            and trusted.historical_source_gate(transition.after)
            and all(
                _workspace_content_digest(
                    _workspace_path(artifact.path, Path(transition.after.repository_root), follow_symlinks=False), declared_cache=artifact.kind == "cache"
                )[1:3]
                == (artifact.digest, artifact.digest_mode)
                for artifact in trusted.record.artifacts
            )
        )
        if status not in {"accepted", "blocked", "in-flight"}:
            reasons.append({"reason_code": "no-active-evidence", "reason": f"Node lifecycle is {status}; no accepted or active review to preserve."})
        decisions.append(
            {
                "node_id": node.node_id,
                "mode": node.mode,
                "prior_status": status,
                "disposition": "preserved" if historical_gate else "recheck" if reasons else "preserved",
                **({"scheduling_gate": "historical-source-pass", "formal_reuse": "unproven", "automatic_reexecution": False} if historical_gate else {}),
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
                **(
                    {"reconciliation_policy": transition.commit_handoff["preserved_evidence"].get(record.get("evidence_id"))}
                    if isinstance(transition, CommitHandoffTransition) and not reasons
                    else {}
                ),
            }
        )
    return decisions


def _restart_reused_metadata_audits(
    plan: GraphPlan, records: Sequence[EvidenceRecord], transition: ExternalMetadataTransition, catalog_path: Path
) -> tuple[GraphPlan, list[dict[str, Any]]]:
    """Turn invalidated non-executable audit reuse back into routed review work."""
    records = [item for item in records if isinstance(item, dict)]
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
    catalog = load_routing_catalog(catalog_path, skill_roots=_continuation_skill_roots(plan))
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
    for node_id in set(plan.pre_review_validation_nodes) - set(preserved):
        if state.get(node_id) in {"accepted", "blocked", "in-flight"}:
            append_journal_event(
                path,
                continuation,
                JournalEventRequest(node_id, "invalidated", reason="External metadata changed; historical pre-review validation must be rerun."),
            )


def resume_after_external_metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Publish a new continuation while preserving original audit and Git provenance."""
    _require_running_review(document)
    transition = metadata_transition(
        {
            "before": document["previous_capture"],
            "after": document["new_capture"],
            **({"git_context_authorization": document["git_context_authorization"]} if "git_context_authorization" in document else {}),
        }
    )
    return _resume_metadata(document, transition)


def resume_after_external_source(document: dict[str, Any]) -> dict[str, Any]:
    """Reconcile attributed external edits without granting or spending agent repairs."""
    require_schema_definition(document, _RUNTIME_OPERATION_INPUT_SCHEMA, "resume-after-external-source")
    _require_running_review(document)
    transition = metadata_transition(
        {
            "before": document["previous_capture"],
            "after": document["new_capture"],
            "external_source_actor": document["external_source_actor"],
            "external_source_attribution": document["external_source_attribution"],
        }
    )
    verify_live_source(document["new_capture"])
    plan = _graph_plan(document["plan"])
    _events, statuses, _head = read_execution_journal(Path(document["journal_path"]), plan=plan, source_state=_state(document, "source_state"))
    if "in-flight" in statuses.values():
        msg = "external source reconciliation requires quiescent workers"
        raise ValueError(msg)
    return _resume_metadata(document, transition)


def resume_after_authorized_commit(document: dict[str, Any]) -> dict[str, Any]:
    """Observe an explicitly authorized commit; this operation never mutates Git."""
    _require_running_review(document)
    require_schema_definition(document, _RUNTIME_OPERATION_INPUT_SCHEMA, "resume-after-authorized-commit")
    verify_live_commit(document["previous_capture"], document["new_capture"])
    transition = CommitHandoffTransition(source_snapshot(document["previous_capture"]), source_snapshot(document["new_capture"]), {})
    return _resume_metadata(document, transition)


def _prepare_commit_handoff(  # noqa: PLR0913 - the continuation binds the complete accepted execution context.
    document: dict[str, Any],
    plan: GraphPlan,
    transition: CommitHandoffTransition,
    lifecycle: dict[str, str],
    *,
    sources: dict[str, dict[str, Any]],
    records: dict[str, EvidenceRecord],
    entries: dict[str, dict[str, Any]],
) -> tuple[GraphPlan, CommitHandoffTransition]:
    if any(status in {"in-flight", "awaiting-replan"} for status in lifecycle.values()):
        msg = "commit handoff requires quiescent execution"
        raise ValueError(msg)
    updated = replacement_native_units(document, plan, lifecycle, transition.after.head)
    proof = {
        "authorization": document["authorization"],
        "parent_commit": transition.before.head,
        "commit": transition.after.head,
        "preserved_evidence": {},
        "native_ci": document["native_ci"],
        "previous_native_units": {unit.node_id: asdict(unit) for unit in plan.coalesced_validation_units if unit.node_id in document["native_ci"]},
        "source_records": {
            _record_document(record)["evidence_id"]: digest_bytes(canonical_json(_record_document(record)).encode()) for record in records.values()
        },
    }
    transition = replace(transition, commit_handoff=proof)
    verify_commit_identity(transition)
    proof["preserved_evidence"] = reconciliation_policy(document, records, entries, transition)
    updated = pin_independent_rechecks(updated, transition)
    root = Path(document["artifact_store"]).resolve()
    repository = Path(transition.after.repository_root)
    if root.is_relative_to(repository) or repository.is_relative_to(root):
        msg = "commit handoff artifact store must be outside the repository"
        raise ValueError(msg)
    history = root / "commit-history"
    if history.resolve() != history:
        msg = "commit handoff history directory must not traverse symlinks"
        raise ValueError(msg)
    history.mkdir(parents=True, exist_ok=True)
    retained = []
    history_sources = dict(sources)
    for source in _verified_reused_sources(plan, _state(document, "source_state")):
        key = "reused-" + digest_bytes(canonical_json(source).encode())[7:23]
        history_sources[key] = source
    for name, content in history_files(
        {
            **document,
            "validation_records": {item["node_id"]: item["policy"] for item in proof["preserved_evidence"].values() if item["kind"] == "validation_records"},
        },
        history_sources,
    ).items():
        path = history / name
        _write_bytes_atomically_once(path, content, mode=0o444)
        retained.append({"path": str(path), "digest": digest_bytes(content)})
    proof["preserved_files"] = retained
    transition = replace(transition, commit_handoff=proof)
    transition.verify()
    return replace(updated, commit_handoffs=(*plan.commit_handoffs, transition)), transition


def _log_directory_archive(source: Path) -> bytes:
    """Retain a deterministic directory tree without dereferencing log symlinks."""

    def fail_walk(error: OSError) -> None:
        raise error

    if source.is_symlink():
        msg = f"log archive root must not be a symlink: {source}"
        raise ValueError(msg)
    root = source.resolve()
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w", dereference=False) as archive:
        for directory, directories, files in root.walk(on_error=fail_walk, follow_symlinks=False):
            directories.sort()
            for child in (directory, *(directory / name for name in sorted(files))):
                if child != root and child.parent.resolve() != child.parent:
                    msg = f"log archive source must not traverse symlink directories: {child}"
                    raise ValueError(msg)
                name = child.relative_to(root).as_posix()
                info = archive.gettarinfo(str(child), arcname=name)
                if info is None:
                    msg = f"log archive cannot represent special filesystem entry: {child}"
                    raise ValueError(msg)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.pax_headers = {}
                content = _read_regular_file_no_follow(child) if info.isfile() else b""
                if info.isfile():
                    info.size = len(content)
                archive.addfile(info, BytesIO(content) if info.isfile() else None)
    return stream.getvalue()


def _metadata_log_archive_content(source: Path, artifact: ArtifactIdentity) -> tuple[bytes, str]:
    """Verify original log identity and retain file bytes, link text, or a directory tar."""
    expected = (True, artifact.digest, artifact.digest_mode)
    if _workspace_content_digest(source) != expected:
        msg = f"prior validation log changed before archival: {source}; recover its original bytes before replay"
        raise ValueError(msg)
    if artifact.digest_mode == "content-sha256-v1":
        content, suffix = _read_regular_file_no_follow(source), ".log"
        unchanged = digest_bytes(content) == artifact.digest
    elif artifact.digest_mode == "symlink-target-v1":
        content, suffix = str(source.readlink()).encode(), ".log"
        unchanged = digest_bytes(b"symlink:" + content) == artifact.digest and _workspace_content_digest(source) == expected
    elif artifact.digest_mode in {_RECURSIVE_WORKSPACE_POLICY, _BOUNDED_WORKSPACE_POLICY}:
        content, suffix = _log_directory_archive(source), ".tar"
        unchanged = _workspace_content_digest(source) == expected
    else:
        msg = f"metadata replay requires a regular log file, symlink, or directory for immutable archival: {source}"
        raise ValueError(msg)
    if not unchanged:
        msg = f"prior validation log changed during archival: {source}; recover its original bytes before replay"
        raise ValueError(msg)
    return content, suffix


def _archive_metadata_validation_logs(
    records: dict[str, EvidenceRecord], decisions: list[dict[str, Any]], root: Path, repository: Path
) -> list[dict[str, str]]:
    """Preserve prior raw logs before returning commands that may overwrite them."""
    if root.is_relative_to(repository) or repository.is_relative_to(root) or root.resolve() != root:
        msg = "metadata log archive must use an external proof store without symlink traversal"
        raise ValueError(msg)
    archives = []
    for decision in decisions:
        record = records.get(decision["node_id"])
        if decision["disposition"] != "recheck" or not isinstance(record, VerifiedValidationRecord):
            continue
        for artifact in record.record.artifacts:
            if artifact.kind != "log" or not artifact.exists:
                continue
            source = Path(artifact.path) if Path(artifact.path).is_absolute() else repository / artifact.path
            content, suffix = _metadata_log_archive_content(source, artifact)
            archive_digest = digest_bytes(content)
            path = root / "validation-log-history" / (archive_digest.removeprefix("sha256:") + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.parent.resolve() != path.parent:
                msg = "validation log archive must not traverse symlinks"
                raise ValueError(msg)
            _write_bytes_atomically_once(path, content, mode=0o444)
            archives.append(
                {
                    "node_id": record.record.node_id,
                    "evidence_id": record.record.evidence_id,
                    "original_path": str(source),
                    "path": str(path),
                    "digest": archive_digest,
                    "original_digest": artifact.digest,
                    "original_digest_mode": artifact.digest_mode,
                }
            )
    if archives:
        _write_bytes_atomically_once(root / "validation-log-history" / "manifest.json", (canonical_json(archives) + "\n").encode(), mode=0o444)
    return archives


def _transition_kind(transition: ExternalMetadataTransition) -> str:
    if isinstance(transition, ExternalSourceTransition):
        return "external-source-change"
    return "authorized-commit-handoff" if isinstance(transition, CommitHandoffTransition) else "observed-external-git-metadata"


def _verify_continuation_instructions(plan: GraphPlan, entries: dict[str, dict[str, Any]], transition: ExternalMetadataTransition) -> None:
    """Reject changed instruction contracts before any continuation is published."""
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


def _metadata_proof_store(document: dict[str, Any], transition: ExternalMetadataTransition) -> Path:
    """Reject overlapping continuation destinations before publishing any bytes."""
    root = Path(document["artifact_store"]).resolve()
    repository = Path(transition.after.repository_root).resolve()
    if root.is_relative_to(repository) or repository.is_relative_to(root):
        msg = "metadata continuation requires an external proof store that does not overlap the repository"
        raise ValueError(msg)
    return root


def _resume_metadata(document: dict[str, Any], transition: ExternalMetadataTransition) -> dict[str, Any]:
    """Share publication machinery while retaining distinct transition contracts."""
    root = _metadata_proof_store(document, transition)
    if transition.before.source_state != _current_metadata_state(document):
        msg = "external metadata previous capture differs from the current reviewed state"
        raise ValueError(msg)
    plan = _graph_plan(document["plan"])
    state = _state(document, "source_state")
    entries = _dispatches_by_node(_read_json_object(Path(document["dispatches_path"])), plan=plan, source_state=state)
    events, lifecycle, _head = read_execution_journal(Path(document["journal_path"]), plan=plan, source_state=state)
    sources, records = _accepted_journal_sources(plan, state, events, entries, include_blocked=True)
    by_node = {_record_document(record)["node_id"]: record for record in records}
    for context in plan.audit_delta_reviews:
        _verify_delta_context(context, entries[context["node_id"]]["dispatch"])
    _verify_continuation_instructions(plan, entries, transition)
    if isinstance(transition, CommitHandoffTransition):
        plan, transition = _prepare_commit_handoff(document, plan, transition, lifecycle, sources=sources, records=by_node, entries=entries)
    decisions = _metadata_resume_decisions(plan, lifecycle, by_node, transition)
    preserved = {item["node_id"]: entries[item["node_id"]] for item in decisions if item["disposition"] == "preserved"}
    discarded_coverage = {item["node_id"] for item in decisions if any("evidence_id" in reason for reason in item["reasons"])}
    plan = replace(plan, audit_delta_reviews=tuple(context for context in plan.audit_delta_reviews if context["node_id"] not in discarded_coverage))
    plan, restarted = _restart_reused_metadata_audits(plan, records, transition, Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)))
    decisions.extend(restarted)
    if isinstance(transition, ExternalSourceTransition):
        plan = replace(plan, captured_path_line_bounds=tuple(sorted(document["new_capture"]["captured_path_line_bounds"].items())))
    transitions = [*_records(document, "external_metadata_transitions"), asdict(transition)]
    continuation = json.loads(canonical_json({"plan": asdict(plan), "source_state": list(state), "external_metadata_transitions": transitions}))
    first_entry = next(iter(entries.values()), None)
    if first_entry is None:
        msg = "external metadata resume requires a materialized review graph"
        raise ValueError(msg)
    if isinstance(transition, ExternalSourceTransition):
        verify_live_source(document["new_capture"])
    materialized = materialize_dispatches(
        {
            "plan": continuation["plan"],
            "source_state": list(state),
            "external_metadata_transitions": transitions,
            "artifact_store": str(root / "dispatch" if isinstance(transition, CommitHandoffTransition) else root),
            "repository_root": transition.after.repository_root,
            "authorization": first_entry["dispatch"]["authorization"],
            "state_verification_command": first_entry["dispatch"]["state_verification_command"],
            "routing_catalog_path": str(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)),
            "sources": _continuation_synthesis_sources(entries),
        },
        preserved_entries=preserved,
    )
    log_archives = _archive_metadata_validation_logs(by_node, decisions, root, Path(transition.after.repository_root))
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
        "transition_kind": _transition_kind(transition),
        "lifecycle_input": continuation,
        "dispatch_set": materialized,
        "original_source_state": list(state),
        "current_source_state": list(transition.after.source_state),
        "preserved_node_ids": sorted(preserved),
        "recheck_node_ids": sorted({node.node_id for node in plan.actual_worker_nodes} - set(preserved)),
        "discarded_coverage_node_ids": sorted(discarded_coverage),
        "node_decisions": decisions,
        "validation_log_archives": log_archives,
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


def _review_stop_reason(document: dict[str, Any], journal: Path | None = None) -> str | None:
    """Resolve shared authority even when callers omit or replace their journal."""
    lifecycle = lifecycle_from_document(document["plan"].get("review_lifecycle"))
    if (marker := _review_control_marker(lifecycle)) is not None:
        record = _read_json_object(marker)
        return (
            "budget-generation-superseded: follow the returned child lifecycle"
            if record.get("kind") == "budget-extension"
            else _required_text(record, "stop_reason")
        )
    if lifecycle.stop_reason is not None:
        return lifecycle.stop_reason
    superseded = _audit_replacement_marker(_graph_plan(document["plan"]))
    if superseded.exists() or superseded.is_symlink():
        return "audit-plan-superseded: follow " + _required_text(parse_json_object(read_control_file(superseded)), "continuation_path")
    return None


def _review_control_marker(lifecycle: ReviewLifecycle) -> Path | None:
    """Every generation shares user stopping and retains its own exhausted boundary."""
    binding = require_run_control(lifecycle.run_control)
    verify_run_control(binding, policy=asdict(lifecycle))
    for marker in control_marker_paths(binding):
        if marker.exists() or marker.is_symlink():
            record = parse_json_object(read_control_file(marker))
            if not isinstance(record, dict) or not isinstance(record.get("stop_reason"), str) or not record["stop_reason"].strip():
                msg = "run control terminal marker requires a stopping reason"
                raise ValueError(msg)
            return marker
    extension = Path(binding.generation.path).with_suffix(".extension.json")
    if extension.exists() or extension.is_symlink():
        record = parse_json_object(read_control_file(extension))
        if not isinstance(record, dict) or record.get("kind") != "budget-extension":
            msg = "run control extension marker requires its committed transition"
            raise ValueError(msg)
        return extension
    return None


def _require_running_review(document: dict[str, Any], journal: Path | None = None) -> None:
    if (reason := _review_stop_reason(document, journal)) is not None:
        msg = f"review stopped: {reason}"
        raise ValueError(msg)


def _review_control_inputs(document: dict[str, Any], args: argparse.Namespace) -> tuple[GraphPlan, dict[str, dict[str, Any]], dict[str, Any], Path]:
    """Bind captures and every prospective write to the signed repository boundary."""
    plan = _graph_plan(document["plan"])
    entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=_state(document, "source_state"))
    roots = {str(Path(_required_text(entry["dispatch"], "repository_root")).resolve()) for entry in entries.values()}
    if len(roots) != 1:
        msg = "review control requires one repository_root from the materialized dispatches"
        raise ValueError(msg)
    repository = Path(roots.pop())
    verify_run_control(plan.review_lifecycle.run_control, repository=repository, policy=asdict(plan.review_lifecycle))
    capture = _read_json_object(args.current_capture)
    snapshot = source_snapshot(capture)
    snapshot.verify()
    if Path(snapshot.repository_root).resolve() != repository:
        msg = "review control capture repository_root differs from the materialized dispatches"
        raise ValueError(msg)
    paths = (
        Path(document["artifact_store"]),
        args.journal,
        args.journal.with_name(args.journal.name + ".lock"),
        args.journal.with_name(args.journal.name + ".stop.json"),
        args.output,
    )
    for path in paths:
        resolved = path.resolve()
        if resolved.is_relative_to(repository) or (path == Path(document["artifact_store"]) and repository.is_relative_to(resolved)):
            msg = f"review control artifacts must be outside the reviewed repository: {path}"
            raise ValueError(msg)
    return plan, entries, capture, repository


def _review_control_request_identity(document: dict[str, Any], args: argparse.Namespace, capture: dict[str, Any]) -> str:
    """A corrected output destination does not change an identical control request."""
    return digest_bytes(
        canonical_json(
            {"document": document, "journal_path": str(args.journal.resolve()), "dispatches_path": str(args.dispatches.resolve()), "capture": capture}
        ).encode()
    )


def _replay_review_control(marker: Path, request_identity: str) -> dict[str, Any]:
    """Recover the original complete cancellation result without stopping twice."""
    stopped = parse_json_object(read_control_file(marker))
    if stopped.get("request_identity") != request_identity:
        msg = f"review stopped or control generation superseded: {stopped.get('stop_reason')}"
        raise ValueError(msg)
    retained = parse_json_object(read_control_file(Path(_required_text(stopped, "result_path"))))
    result = retained.get("result")
    if (
        retained.get("schema_version") != 1
        or retained.get("request_identity") != request_identity
        or not isinstance(result, dict)
        or retained.get("result_identity") != digest_bytes(canonical_json(result).encode())
        or retained.get("result_identity") != stopped.get("result_identity")
        or result.get("stop_reason") != stopped.get("stop_reason")
    ):
        msg = "review control retained result differs from its stop marker"
        raise ValueError(msg)
    return result


def _write_review_control_output(path: Path, result: dict[str, Any]) -> None:
    _write_bytes_atomically_once(path, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)


def _review_control_output_destination(args: argparse.Namespace, path: Path, *, store: Path | None = None) -> Path:
    output = path.absolute()
    protected = {
        args.journal.resolve(),
        args.dispatches.resolve(),
        args.current_capture.resolve(),
        args.journal.with_name(args.journal.name + ".stop.json").resolve(),
        args.journal.with_name(args.journal.name + ".lock").resolve(),
    }
    if (store is not None and output.resolve().is_relative_to(store)) or output.resolve() in protected:
        msg = "review control operation-result must be outside the control store and distinct from its inputs and journal"
        raise ValueError(msg)
    return output


def _updated_review_control_policy(document: dict[str, Any], policy: ReviewLifecycle) -> ReviewLifecycle:
    action = document["action"]
    if action == "extend-budget":
        if policy.stop_reason is not None and not policy.stop_reason.startswith("repair-budget-exhausted"):
            msg = f"review stopped: {policy.stop_reason}"
            raise ValueError(msg)
        extension = RepairBudgetExtension(_required_int(document, "additional_epochs"), _required_text(document, "user_authorization"))
        return replace(
            policy, repair_budget=policy.repair_budget + extension.additional_epochs, budget_extensions=(*policy.budget_extensions, extension), stop_reason=None
        )
    if action == "authorize-restart":
        trigger = ComprehensiveRestart.from_document(document["restart_trigger"])
        return replace(policy, comprehensive_restarts=(*policy.comprehensive_restarts, trigger))
    reason = "repair-budget-exhausted: explicit user extension required" if action == "begin-repair" else "user-stop: " + _required_text(document, "reason")
    return replace(policy, stop_reason=reason)


def review_control(document: dict[str, Any], args: argparse.Namespace, *, operation_output_path: Path | None = None) -> dict[str, Any]:
    """Check a batch budget, explicitly extend it, or stop without new audit work."""
    require_schema_definition(document, _RUNTIME_OPERATION_INPUT_SCHEMA, "review-control")
    plan, entries, capture, repository = _review_control_inputs(document, args)
    if operation_output_path is not None:
        if operation_output_path.resolve().is_relative_to(repository):
            msg = "review control operation-result must be outside the reviewed repository"
            raise ValueError(msg)
        operation_output_path = _review_control_output_destination(args, operation_output_path)
    lock_path = args.journal.with_name(args.journal.name + ".lock")
    with run_control_lock(plan.review_lifecycle.run_control), lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            return _review_control_locked(
                document, args, plan=plan, entries=entries, capture=capture, repository=repository, operation_output_path=operation_output_path
            )
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _replayed_extension(
    policy: ReviewLifecycle, args: argparse.Namespace, request_identity: str, marker: Path | None, operation_output_path: Path | None
) -> dict[str, Any] | None:
    """Permit an identical grant retry while preventing sibling budget generations."""
    binding = require_run_control(policy.run_control)
    extension_marker = Path(binding.generation.path).with_suffix(".extension.json")
    if not (extension_marker.exists() or extension_marker.is_symlink()):
        return None
    transition = parse_json_object(read_control_file(extension_marker))
    if not isinstance(transition, dict) or transition.get("request_identity") != request_identity:
        msg = "budget generation already extended; use the returned child lifecycle for another extension"
        raise ValueError(msg)
    if marker is not None and str(_read_json_object(marker).get("stop_reason", "")).startswith("user-stop"):
        msg_0 = f"review stopped: {_required_text(_read_json_object(marker), 'stop_reason')}"
        raise ValueError(msg_0)
    result = _replay_review_control(extension_marker, request_identity)
    if operation_output_path is not None:
        _review_control_output_destination(args, operation_output_path, store=Path(result["control_result_path"]).parent)
        _write_review_control_output(operation_output_path, result)
    return result


def _extension_base(policy: ReviewLifecycle, marker: Path | None) -> tuple[ReviewLifecycle, str | None]:
    """A stale plan cannot discard the exhausted generation's completed repair history."""
    if marker is None:
        return policy, None
    terminal = parse_json_object(read_control_file(marker))
    retained = _replay_review_control(marker, _required_text(terminal, "request_identity"))
    authoritative = lifecycle_from_document(retained["review_lifecycle"])
    if replace(policy, stop_reason=None) != replace(authoritative, stop_reason=None):
        msg = "budget extension requires the authoritative stopped lifecycle counters and history"
        raise ValueError(msg)
    return authoritative, _required_text(terminal, "result_path")


def _require_control_action_active(action: str, reason: str | None) -> None:
    """Stopping older budget generations remains a run-wide user action."""
    if reason is None:
        return
    if action == "stop" and reason.startswith(("repair-budget-exhausted", "budget-generation-superseded")):
        return
    if action == "extend-budget" and reason.startswith("repair-budget-exhausted"):
        return
    msg = f"review stopped: {reason}"
    raise ValueError(msg)


def _begin_repair_result(  # noqa: PLR0913 - explicit source, journal and authority boundaries.
    document: dict[str, Any],
    *,
    plan: GraphPlan,
    entries: dict[str, dict[str, Any]],
    capture: dict[str, Any],
    events: tuple[dict[str, Any], ...],
    active: list[str],
) -> dict[str, Any] | None:
    policy = plan.review_lifecycle
    followup = document.get("verification_followup")
    if followup is None and policy.repairs_completed >= policy.repair_budget:
        return None
    if active:
        msg = "repair batch requires quiescent execution"
        raise ValueError(msg)
    _sources, records = _accepted_journal_sources(plan, _state(document, "source_state"), events, entries)
    if followup is not None:
        previous = verify_followup_origin({**document, "previous_capture": capture}, followup)
        verify_followup_finding(previous, followup, [item for item in records if isinstance(item, dict)])
        return {
            "status": "repair-authorized",
            "repair_epoch": policy.repairs_completed,
            "verification_followup": followup,
            "permitted_paths": previous["repair_epoch"]["changed_paths"],
            "review_lifecycle": asdict(policy),
        }
    return {
        "status": "repair-authorized",
        "repair_epoch": policy.repairs_completed + 1,
        "review_lifecycle": asdict(policy),
        "validation_reconciliation": _validation_reconciliation(plan, records),
        "next_action": (
            "Inspect validation_reconciliation before repair replanning. Reconcile late requirements with "
            "reconcile-validation-requirements on this source state; carry all resulting obligations into the repair template. "
            "Only dispatch-bound coverage_reuse permits inherited judgments; missing coverage_reuse requires complete owned inspection."
        ),
    }


def _review_control_locked(  # noqa: PLR0913
    document: dict[str, Any],
    args: argparse.Namespace,
    *,
    plan: GraphPlan,
    entries: dict[str, dict[str, Any]],
    capture: dict[str, Any],
    repository: Path,
    operation_output_path: Path | None,
) -> dict[str, Any]:
    """Bind the control decision to a stable journal while publishing its stop."""
    action = document["action"]
    policy = plan.review_lifecycle
    request_identity = _review_control_request_identity(document, args, capture)
    marker = _review_control_marker(policy)
    if action == "extend-budget" and (result := _replayed_extension(policy, args, request_identity, marker, operation_output_path)) is not None:
        return result
    if (
        operation_output_path is not None
        and marker is not None
        and action in {"stop", "begin-repair"}
        and _read_json_object(marker).get("request_identity") == request_identity
    ):
        result = _replay_review_control(marker, request_identity)
        _review_control_output_destination(args, operation_output_path, store=Path(result["control_result_path"]).parent)
        _write_review_control_output(operation_output_path, result)
        return result
    reason = _review_stop_reason(document, args.journal)
    _require_control_action_active(action, reason)
    parent_result = None
    if action == "extend-budget":
        policy, parent_result = _extension_base(policy, marker)
    events, state, _head = read_execution_journal(args.journal, plan=plan, source_state=_state(document, "source_state"))
    active = sorted(node_id for node_id, status in state.items() if status == "in-flight")
    if action != "stop" and source_snapshot(capture).source_state != _current_metadata_state(document):
        msg = "review control requires the current reviewed capture before authorizing more work"
        raise ValueError(msg)
    if (
        action == "begin-repair"
        and (result := _begin_repair_result(document, plan=plan, entries=entries, capture=capture, events=events, active=active)) is not None
    ):
        if operation_output_path is not None:
            _write_review_control_output(operation_output_path, result)
        return result
    if action in {"extend-budget", "authorize-restart"} and active:
        msg = "review control extension requires quiescent execution"
        raise ValueError(msg)
    policy = _updated_review_control_policy(document, policy)
    if action == "extend-budget":
        binding = require_run_control(policy.run_control)
        policy = replace(policy, run_control=extend_run_control(binding, asdict(policy), parent_result=parent_result))
    _sources, records = _accepted_journal_sources(plan, _state(document, "source_state"), events, entries, include_blocked=True)
    result = {
        "status": "stopped" if policy.stop_reason is not None else action,
        "review_lifecycle": asdict(policy),
        "stop_reason": policy.stop_reason,
        "cancel_node_ids": active if policy.stop_reason is not None else [],
        "remaining_findings": [
            {"evidence_id": record["evidence_id"], "findings": record.get("findings", [])}
            for record in records
            if isinstance(record, dict) and record.get("findings")
        ],
        "incomplete_node_ids": sorted(node.node_id for node in plan.actual_worker_nodes if state.get(node.node_id) != "accepted"),
        "graph_proof_status": "partial",
    }
    return _publish_review_control(
        document,
        args,
        replace(plan, review_lifecycle=policy),
        events,
        entries,
        result=result,
        repository=repository,
        capture=capture,
        request_identity=request_identity,
        operation_output_path=operation_output_path,
    )


def _publish_review_control(  # noqa: PLR0913
    document: dict[str, Any],
    args: argparse.Namespace,
    plan: GraphPlan,
    events: tuple[dict[str, Any], ...],
    entries: dict[str, dict[str, Any]],
    *,
    result: dict[str, Any],
    repository: Path,
    capture: dict[str, Any],
    request_identity: str,
    operation_output_path: Path | None,
) -> dict[str, Any]:
    """Rebind only lifecycle identity; retain every dispatch and evidence byte."""
    store = (Path(document["artifact_store"]).resolve() / f"control-{_plan_digest(plan)[7:23]}").resolve()
    if store.is_relative_to(repository) or repository.is_relative_to(store):
        msg = "review control artifact store must be outside the repository"
        raise ValueError(msg)
    lifecycle = {key: value for key, value in document.items() if key in {"source_state", "external_metadata_transitions"}}
    lifecycle["plan"] = json.loads(canonical_json(asdict(plan)))
    migrated = []
    for original in events:
        event = {**original, "plan_digest": _plan_digest(plan), "previous_event_digest": migrated[-1]["event_digest"] if migrated else None}
        event.pop("event_digest")
        event["event_digest"] = digest_bytes(canonical_json(event).encode())
        migrated.append(event)
    _fold_execution_journal(plan, _state(document, "source_state"), tuple(migrated))
    dispatches = {"schema_version": 1, "plan_digest": _plan_digest(plan), "source_state": document["source_state"], "dispatches": list(entries.values())}
    dispatches["dispatch_set_digest"] = digest_bytes(canonical_json(dispatches).encode())
    paths = {
        key: str(store / filename)
        for key, filename in (
            ("lifecycle_input_path", "lifecycle.json"),
            ("dispatches_path", "dispatches.json"),
            ("journal_path", "execution.jsonl"),
            ("current_capture_path", "capture.json"),
        )
    }
    result.update(
        **paths,
        continuation_path=str(store / "continuation.json"),
        control_result_path=str(store / "result.json"),
        lifecycle_input=lifecycle,
        dispatch_set=dispatches,
    )
    result_identity = digest_bytes(canonical_json(result).encode())
    retained = {"schema_version": 1, "request_identity": request_identity, "result_identity": result_identity, "result": result}
    outputs = {
        Path(paths["lifecycle_input_path"]): (json.dumps(lifecycle, indent=2, sort_keys=True) + "\n").encode(),
        Path(paths["dispatches_path"]): (json.dumps(dispatches, indent=2, sort_keys=True) + "\n").encode(),
        Path(paths["journal_path"]): "".join(canonical_json(event) + "\n" for event in migrated).encode(),
        Path(paths["current_capture_path"]): (json.dumps(capture, indent=2, sort_keys=True) + "\n").encode(),
        store / "continuation.json": (canonical_json(paths) + "\n").encode(),
        store / "result.json": (canonical_json(retained) + "\n").encode(),
    }
    pending = {path: (content, 0o600 if path.name == "execution.jsonl" else 0o444) for path, content in outputs.items()}
    marker_content = (
        (
            canonical_json(
                {
                    "stop_reason": result["stop_reason"],
                    "continuation_path": result["continuation_path"],
                    "request_identity": request_identity,
                    "result_identity": result_identity,
                    "result_path": result["control_result_path"],
                }
            )
            + "\n"
        ).encode()
        if result["stop_reason"] is not None
        else None
    )
    binding = require_run_control(plan.review_lifecycle.run_control)
    verify_run_control(binding, repository=repository, pending_generation=document["action"] == "extend-budget")
    markers = control_marker_paths(binding)
    control_marker = markers[0] if (result["stop_reason"] or "").startswith("user-stop") else markers[1]
    control_marker_content = marker_content
    if document["action"] == "extend-budget":
        previous_binding = require_run_control(_graph_plan(document["plan"]).review_lifecycle.run_control)
        control_marker = Path(previous_binding.generation.path).with_suffix(".extension.json")
        control_marker_content = (
            canonical_json(
                {
                    "kind": "budget-extension",
                    "stop_reason": None,
                    "request_identity": request_identity,
                    "result_identity": result_identity,
                    "result_path": result["control_result_path"],
                    "next_generation": asdict(binding.generation),
                }
            )
            + "\n"
        ).encode()
    _publish_review_control_transaction(
        args,
        store,
        pending,
        result,
        marker_content=marker_content,
        operation_output_path=operation_output_path,
        control_marker=control_marker,
        control_marker_content=control_marker_content,
    )
    return result


def _publish_review_control_transaction(  # noqa: PLR0913
    args: argparse.Namespace,
    store: Path,
    pending: dict[Path, tuple[bytes, int]],
    result: dict[str, Any],
    *,
    marker_content: bytes | None,
    operation_output_path: Path | None,
    control_marker: Path,
    control_marker_content: bytes | None,
) -> None:
    """Publish a complete immutable result and stop, or remove this attempt's writes."""
    marker = args.journal.with_name(args.journal.name + ".stop.json")
    if control_marker_content is not None:
        _preflight_compile_destination(control_marker, control_marker_content)
    output_created = store_created = False
    try:
        if operation_output_path is not None:
            output = _review_control_output_destination(args, operation_output_path, store=store)
            output_created = _write_bytes_atomically_once(output, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)
        store_created = _publish_materialized_writes(store, pending)
        if control_marker_content is not None:
            _write_bytes_atomically_once(control_marker, control_marker_content, mode=0o444)
    except OSError, ValueError:
        if store_created:
            shutil.rmtree(store)
            _fsync_directory(store.parent)
        if output_created and operation_output_path is not None:
            operation_output_path.unlink()
            _fsync_directory(operation_output_path.parent)
        raise
    if marker_content is not None:
        # Shared terminal authority and its complete retained receipt have
        # already committed. A journal-side copy cannot roll them back.
        with suppress(OSError, ValueError):
            _write_bytes_atomically_once(marker, marker_content, mode=0o444)


def _exhausted_mutation(document: dict[str, Any], plan: GraphPlan) -> dict[str, Any]:
    """Commit budget exhaustion under the same run admission boundary as user stopping."""
    with run_control_lock(plan.review_lifecycle.run_control):
        _require_running_review(document)
        return _exhausted_mutation_locked(document, plan)


def _exhausted_mutation_locked(document: dict[str, Any], plan: GraphPlan) -> dict[str, Any]:
    """Retain a partial result even when a caller edits past the pre-mutation gate."""
    reason = "repair-budget-exhausted: explicit user extension required"
    store = Path(_required_text(document, "artifact_store")).resolve()
    repository = Path(document["previous_capture"]["repository_root"]).resolve()
    verify_run_control(plan.review_lifecycle.run_control, repository=repository)
    if store.is_relative_to(repository) or repository.is_relative_to(store):
        msg = "repair stop artifact store must be outside the repository"
        raise ValueError(msg)
    store.mkdir(parents=True, exist_ok=True)
    sources = _mutation_evidence_sources(document, plan)
    result = {
        "status": "stopped",
        "stop_reason": reason,
        "graph_proof_status": "partial",
        "review_lifecycle": asdict(replace(plan.review_lifecycle, stop_reason=reason)),
        "incomplete_node_ids": [node.node_id for node in plan.actual_worker_nodes],
        "remaining_findings": [
            {"evidence_id": record["evidence_id"], "findings": record.get("findings", [])} for _source, record in sources.values() if record.get("findings")
        ],
        "previous_capture": document["previous_capture"],
        "unverified_capture": document["new_capture"],
        "preserved_sources": [source for source, _record in sources.values()],
    }
    stop_path = store / "repair-budget-exhausted.json"
    result.update(stop_path=str(stop_path), control_result_path=str(stop_path))
    request_identity = digest_bytes(canonical_json(document).encode())
    result_identity = digest_bytes(canonical_json(result).encode())
    retained = {"schema_version": 1, "request_identity": request_identity, "result_identity": result_identity, "result": result}
    _write_bytes_atomically_once(stop_path, (canonical_json(retained) + "\n").encode(), mode=0o444)
    binding = require_run_control(plan.review_lifecycle.run_control)
    marker_content = (
        canonical_json({"stop_reason": reason, "request_identity": request_identity, "result_identity": result_identity, "result_path": str(stop_path)}) + "\n"
    ).encode()
    _write_bytes_atomically_once(control_marker_paths(binding)[1], marker_content, mode=0o444)
    if document.get("journal_path"):
        journal = Path(document["journal_path"])
        _write_bytes_atomically_once(
            journal.with_name(journal.name + ".stop.json"), (canonical_json({"stop_reason": reason, "stop_path": str(stop_path)}) + "\n").encode(), mode=0o444
        )
    return {**result, "stop_path": str(stop_path)}


def _continuation_skill_roots(plan: GraphPlan) -> tuple[Path, ...]:
    """Keep captured skill locations when a compatible newer runtime resumes a run."""
    roots = tuple(sorted({Path(node.skill_path).parent.parent for node in plan.actual_worker_nodes}))
    return roots or (DEFAULT_SKILL_ROOT,)


def _interleaved_repair_transition(document: dict[str, Any], plan: GraphPlan) -> InterleavedRepairTransition | None:
    """Parse explicit endpoint attribution before allowing a mixed repair delta."""
    if "interleaved_staging" not in document:
        return None
    require_schema_definition(document, _RUNTIME_OPERATION_INPUT_SCHEMA, "advance-after-mutation")
    if "post_repair_capture" in document:
        msg = "interleaved_staging and post_repair_capture are alternative continuations; supply only actual captures"
        raise ValueError(msg)
    transition = metadata_transition(
        {
            "before": document["previous_capture"],
            "after": document["new_capture"],
            "repair_epoch": document["repair_epoch"],
            "repair_paths": sorted(_text_list(document, "changed_paths", required=True)),
            **document["interleaved_staging"],
        }
    )
    if not isinstance(transition, InterleavedRepairTransition):
        msg = "interleaved repair attribution did not produce a repair transition"
        raise TypeError(msg)
    root = Path(transition.before.repository_root)
    changed = set(transition.repair_paths)
    protected = {
        str(Path(path).relative_to(root))
        for node in plan.actual_worker_nodes
        for path in (node.skill_path, *node.instruction_paths, *node.static_references)
        if Path(path).is_relative_to(root)
    }
    if changed.intersection(protected):
        msg = "interleaved repair cannot reconcile changed skill, reference or instruction inputs"
        raise ValueError(msg)
    return transition


def _interleaved_repair_history(
    document: dict[str, Any], sources: dict[str, tuple[dict[str, Any], dict[str, Any]]], transition: InterleavedRepairTransition
) -> bytes:
    """Read and serialize all historical inputs before publishing a continuation."""
    history = {
        "transition": asdict(transition),
        "previous_capture": document["previous_capture"],
        "new_capture": document["new_capture"],
        "previous_plan": document["plan"],
        "previous_metadata_transitions": document.get("external_metadata_transitions", []),
        "historical_evidence": [
            {
                "source": source,
                "record": record,
                "files": {
                    key: {"path": source[key], "digest": digest_bytes(_read_regular_file_no_follow(Path(source[key])))}
                    for key in ("artifact_path", "metadata_path")
                },
            }
            for source, record in sources.values()
        ],
        "previous_execution": {
            key: _read_regular_file_no_follow(Path(document[key])).decode() for key in ("journal_path", "dispatches_path") if key in document
        },
        "missing_intermediate_capture": True,
    }
    return (json.dumps(history, indent=2, sort_keys=True) + "\n").encode()


def _retain_interleaved_repair(result: dict[str, Any], history: bytes) -> dict[str, Any]:
    """Retain actual history and expose a small, directly executable continuation."""
    store = Path(result["lifecycle_input_path"]).parent
    history_path = store / "repair-transition.json"
    _write_bytes_atomically_once(history_path, history, mode=0o444)
    action = NextReadyAction(
        tuple(
            runtime_command(
                Path(__file__),
                "next-ready",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--current-capture",
                result["capture_path"],
                "--output-dir",
                str(store / "ready"),
            )
        )
    )
    return {
        **result,
        "transition_kind": "interleaved-repair-and-staging",
        "current_source_state": result["new_source_state"],
        "repair_transition_path": str(history_path),
        "next_action": asdict(action),
        "next_command": action.command,
    }


def advance_after_mutation(document: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - one ordered repair transaction.
    """Close one repair epoch, recapture once, and emit a fresh final-state graph."""
    raw_plan = document.get("plan")
    previous_capture = document.get("previous_capture")
    new_capture = document.get("new_capture")
    planning_template = document.get("planning_template")
    if not isinstance(raw_plan, dict) or not isinstance(previous_capture, dict) or not isinstance(new_capture, dict) or not isinstance(planning_template, dict):
        msg = "advance-after-mutation requires plan, previous_capture, new_capture, and planning_template objects"
        raise TypeError(msg)
    old_plan = _graph_plan(raw_plan)
    _require_running_review(document)
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
    if epoch == old_plan.review_lifecycle.repairs_completed + 1 and epoch > old_plan.review_lifecycle.repair_budget:
        return _exhausted_mutation(document, old_plan)
    followup = document.get("verification_followup")
    repair_lifecycle = old_plan.review_lifecycle if followup is not None else old_plan.review_lifecycle.next_repair(epoch)
    interleaved = _interleaved_repair_transition(document, old_plan)
    if interleaved is not None:
        repair_lifecycle = replace(repair_lifecycle, interleaved_repair_epochs=(*repair_lifecycle.interleaved_repair_epochs, epoch))
    changed_paths = _mutation_path_delta(document, previous_capture, new_capture, interleaved)
    metadata = metadata_transition({"before": new_capture, "after": document["post_repair_capture"]}) if "post_repair_capture" in document else None
    captured_paths = _text_list(new_capture, "captured_scope_paths")
    sources = _mutation_evidence_sources(document, old_plan)
    if followup is not None:
        previous = verify_followup_origin(document, followup)
        verify_followup_finding(previous, followup, [record for _source, record in sources.values()])
        if epoch != repair_lifecycle.repairs_completed or interleaved is not None or not set(changed_paths) <= set(previous["repair_epoch"]["changed_paths"]):
            msg = "verification follow-up must keep the same repair_epoch and already repaired paths; interleaved staging uses its separate continuation"
            raise ValueError(msg)
    interleaved_history = _interleaved_repair_history(document, sources, interleaved) if interleaved is not None else None
    planning_input = bootstrap_document(new_capture, planning_template)
    if new_capture["capture_mode"] == "baseline" and not planning_input.get("change_target"):
        planning_input["concrete_change_target"] = bool(captured_head_changes("git", Path(new_capture["repository_root"]), new_capture))
        if planning_input["concrete_change_target"]:
            planning_input["change_target"] = shlex.join(["git", "--no-pager", "diff", previous_capture["head"], "--", "."])
    if planning_input.get("change_target"):
        planning_input["change_target"] = refresh_comparison_scope(planning_input["change_target"], previous_capture, new_capture)
    planning_input["independent_review_after_audits"] = old_plan.independent_review_after_audits
    planning_input["review_lifecycle"] = json.loads(canonical_json(asdict(old_plan.review_lifecycle)))
    planning_input["planning_purpose"] = "repair-verification"
    planning_input["authorization"] = authorization_after
    _expire_mutation_reuse(planning_input)
    require_schema(planning_input, _PLANNING_INPUT_SCHEMA)
    repository_root = Path(_required_text(planning_input, "repository_root")).resolve()
    catalog_path = Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)).resolve()
    new_plan = plan_from_document(
        planning_input,
        catalog_path=catalog_path,
        skill_roots=_continuation_skill_roots(old_plan),
        repository_root=repository_root,
        observed_metadata_transition=metadata,
    )
    if not new_plan.dispatch_allowed:
        msg = "recaptured repair epoch produced a blocked final-state plan: " + "; ".join(new_plan.blockers)
        raise ValueError(msg)
    invalidated = _mutation_invalidated_nodes(old_plan, new_plan, changed_paths, repository_root, sources)
    reuse_document = (
        {**document, "external_metadata_transitions": [*document.get("external_metadata_transitions", []), asdict(interleaved)]}
        if interleaved is not None
        else document
    )
    new_plan, reuse_decisions = _carry_forward_audits(
        reuse_document, old_plan, new_plan, planning_input, invalidated=invalidated, sources=sources, observed_metadata_transition=metadata
    )
    new_plan, coverage_reviews = _plan_delta_audits(reuse_document, old_plan, new_plan, sources)
    suffix = "-verification" if followup is not None else ""
    new_plan = _epoch_scoped_plan(new_plan, epoch, suffix=suffix)
    new_plan = replace(new_plan, review_lifecycle=repair_lifecycle, audit_replacements=old_plan.audit_replacements)
    reused_ids = {item.evidence_id for item in new_plan.audit_reuse_transitions}
    artifact_store = Path(_required_text(document, "artifact_store")).resolve() / f"repair-epoch-{epoch:03d}{suffix}"
    if interleaved is not None:
        verify_live_source(new_capture)
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
    fix_node_id = f"fix-epoch-{epoch:03d}{suffix}"
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
        "proof_limitations": _proof_limitations(new_plan),
        "reused_evidence_ids": sorted(reused_ids),
        "reuse_decisions": sorted(reuse_decisions, key=lambda item: item["node_id"]),
        "audit_reuse_counts": {"retained": len(reused_ids), "scheduled_audits": sum(node.mode == "audit" for node in new_plan.actual_worker_nodes)},
        "validation_reconciliation": _validation_reconciliation(
            new_plan, [record for _source, record in sources.values() if record["evidence_id"] in reused_ids]
        ),
        "coverage_reuse_decisions": [{**item, "node_id": f"repair-epoch-{epoch:03d}{suffix}-" + item["node_id"]} for item in coverage_reviews],
        "unaffected_node_ids": [node.node_id for node in unaffected],
        "repair_epoch": {
            **({"verification_followup": followup} if followup is not None else {}),
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
    if interleaved_history is not None:
        result = _retain_interleaved_repair(result, interleaved_history)
    elif metadata is not None:
        result = _resume_after_repair_metadata(document, result, sources)
    origin_path, origin_record = repair_origin(result)
    _write_bytes_atomically_once(origin_path, (canonical_json(origin_record) + "\n").encode(), mode=0o400)
    return result


def _resume_after_repair_metadata(
    document: dict[str, Any], repair: dict[str, Any], sources: dict[str, tuple[dict[str, Any], dict[str, Any]]]
) -> dict[str, Any]:
    """Compose two verified transitions without synthesizing captures or changing Git."""
    history_path = Path(repair["lifecycle_input_path"]).parent / "repair-transition.json"
    history = {"previous_capture": document["previous_capture"], "historical_evidence_sources": document.get("sources", []), **repair}
    _write_bytes_atomically_once(history_path, (json.dumps(history, indent=2, sort_keys=True) + "\n").encode("utf-8"), mode=0o444)
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
    resumed_plan = _graph_plan(resumed["lifecycle_input"]["plan"])
    reused_ids = {evidence_id for _requirement, evidence_id in resumed_plan.exact_reused_review_evidence}
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
        "replacement_lineage": _replacement_lineage(_graph_plan(document["plan"]), resumed_plan, sources),
        "capture": document["post_repair_capture"],
        "repair_transition_path": str(history_path),
        "reused_evidence_ids": sorted(reused_ids),
        "audit_reuse_counts": {"retained": len(reused_ids), "scheduled_audits": sum(node.mode == "audit" for node in resumed_plan.actual_worker_nodes)},
        "validation_reconciliation": _validation_reconciliation(
            resumed_plan, [record for _source, record in sources.values() if record["evidence_id"] in reused_ids]
        ),
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


def _historical_validation_evidence(evidence: dict[str, str], plan: GraphPlan, node: WorkerNode) -> bool:
    """Verify an old attempt against the recovery's immutable prior journal."""
    if node.mode != "validation":
        return False
    recovery = next(
        (item for item in plan.validation_recoveries if item["node_id"] == node.node_id and item.get("previous_evidence_id") == evidence["evidence_id"]), None
    )
    if recovery is None:
        return False
    saved = {}
    for filename in ("lifecycle.json", "execution.jsonl"):
        matches = [item for item in recovery["preserved_files"] if Path(item["path"]).name == filename]
        if len(matches) != 1:
            msg = "historical validation evidence requires one preserved lifecycle and journal"
            raise ValueError(msg)
        content = _read_regular_file_no_follow(Path(matches[0]["path"]))
        if digest_bytes(content) != matches[0]["digest"]:
            msg = "preserved validation recovery evidence changed"
            raise ValueError(msg)
        saved[filename] = content
    lifecycle = parse_json_object(saved["lifecycle.json"])
    previous = _graph_plan(lifecycle["plan"])
    source_state = _state(lifecycle, "source_state")
    if _plan_digest(previous) != recovery["previous_plan_digest"] or source_state != tuple(recovery["source_state"]):
        msg = "historical validation evidence differs from its recovery plan"
        raise ValueError(msg)
    events, _state_view, head = _read_execution_journal_content(
        saved["execution.jsonl"], path=Path("execution.jsonl"), plan=previous, source_state=source_state
    )
    if head != recovery["previous_journal_head"]:
        msg = "historical validation evidence differs from its recovery journal"
        raise ValueError(msg)
    return any(event["node_id"] == node.node_id and event["evidence"] == evidence for event in events)


def _journal_evidence(raw: object, *, plan: GraphPlan, node: WorkerNode, status: str, superseded: bool = False) -> dict[str, str] | None:
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
    if evidence["evidence_id"] != expected_evidence_id and not (superseded and _historical_validation_evidence(evidence, plan, node)):
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
    source: dict[str, Any],
    *,
    plan: GraphPlan,
    node: WorkerNode,
    source_state: tuple[str, str, str],
    loaded: tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, EvidenceRecord | None]
    | None = None,
) -> tuple[dict[str, str], tuple[str, ...]]:
    kind, expectation, evidence, _content, normalized = loaded if loaded is not None else _load_evidence_source(source, require_normalized=True)
    normalized = _record_document(normalized) if normalized is not None else None
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


def _validated_journal_record(  # noqa: PLR0913 - bind both chain and historical-attempt position before accepting a record.
    event: dict[str, Any], *, expected_sequence: int, plan: GraphPlan, source_state: tuple[str, str, str], previous_digest: str | None, superseded: bool
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
    _journal_evidence(event.get("evidence"), plan=plan, node=node, status=status, superseded=superseded)
    return node_id, status


def _fold_execution_journal(plan: GraphPlan, source_state: tuple[str, str, str], events: tuple[dict[str, Any], ...]) -> tuple[dict[str, str], str | None]:
    state: dict[str, str] = {}
    latest: dict[str, dict[str, Any]] = {}
    last = {event.get("node_id"): event for event in events}
    previous_digest: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        node_id, status = _validated_journal_record(
            event,
            expected_sequence=expected_sequence,
            plan=plan,
            source_state=source_state,
            previous_digest=previous_digest,
            superseded=event is not last[event.get("node_id")],
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
        value = parse_json_object(line)
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
    if request.status == "in-flight":
        _require_running_review(document, path)
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
    admission = run_control_lock(plan.review_lifecycle.run_control) if request.status == "in-flight" else nullcontext()
    with admission, lock_path.open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            if request.status == "in-flight":
                _require_running_review(document, path)
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
            if "worker_execution_path" in entry and _read_regular_file_no_follow(Path(entry["worker_execution_path"])) != execution_view_bytes(
                entry, expected_input
            ):
                msg = f"worker execution view differs from its canonical dispatch: {node_id}"
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
        record = _record_document(record) if record is not None else None
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
) -> tuple[dict[str, dict[str, Any]], list[EvidenceRecord]]:
    state, _head = _fold_execution_journal(plan, source_state, events)
    latest = {str(event["node_id"]): event for event in events}
    sources: dict[str, dict[str, Any]] = {}
    records: list[EvidenceRecord] = []
    for node in plan.actual_worker_nodes:
        status = state.get(node.node_id)
        if status != "accepted" and not (include_blocked and status == "blocked" and latest[node.node_id]["evidence"] is not None):
            continue
        entry = entries[node.node_id]
        source = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}
        loaded = _load_evidence_source(source, require_normalized=True)
        verified, _limitations = _verified_journal_evidence(source, plan=plan, node=node, source_state=source_state, loaded=loaded)
        if verified != latest[node.node_id]["evidence"]:
            msg = f"{status} artifact differs from journal: {node.node_id}"
            raise ValueError(msg)
        _kind, _expectation, _evidence, _content, record = loaded
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


def next_ready_nodes(document: dict[str, Any], *, journal_events: tuple[dict[str, Any], ...], dispatch_set: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
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
    stop_reason = _review_stop_reason(document)
    if stop_reason is not None:
        blockers.append("review stopped: " + stop_reason)
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
    for node in () if stop_reason is not None else plan.actual_worker_nodes:
        if node.node_id in accepted | awaiting_replan | blocked | in_flight:
            continue
        if plan.independent_review_after_audits and node.mode == "independent-review":
            pending_audits = [audit.node_id for audit in plan.actual_worker_nodes if audit.mode == "audit" and audit.node_id not in accepted]
            if pending_audits:
                waiting.append({"node_id": node.node_id, "pending_source_audits": pending_audits})
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
        elif node.mode == "validation" and (timing := timing_blocker(dispatches[node.node_id]["dispatch"])) is not None:
            waiting.append({"node_id": node.node_id, "timing_prerequisite": timing})
        else:
            ready.append(node.node_id)
    node_ids = {node.node_id for node in plan.actual_worker_nodes}
    complete = not blockers and accepted == node_ids
    return {
        "blockers": blockers,
        "stop_reason": stop_reason,
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
    if "worker_execution_path" in entry:
        entry["worker_execution_path"] = str(store / f"{node_id}.execution.json")
    contract_path = store / f"{node_id}.worker-payload-contract.json"
    entry["worker_payload_contract_path"] = str(contract_path)
    dispatch = entry["dispatch"]
    dispatch.update({"execution_location": "coordinator", "worker_created": False, "fresh_context": False})
    if "protocol_input_paths" in dispatch:
        dispatch["protocol_input_paths"] = [
            entry[field] for field in ("worker_input_path", "worker_execution_path", "worker_payload_contract_path") if field in entry
        ]
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
    if "worker_execution_path" in entry:
        _queue_materialized_write(pending, Path(entry["worker_execution_path"]), execution_view_bytes(entry, entry_bytes), mode=0o444)
    _queue_materialized_write(pending, contract_path, (json.dumps(contract, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)
    return entry


def schedule_ready(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Publish one capacity-aware adaptive schedule and immutable continuation."""
    lock_path = args.journal.with_name(args.journal.name + ".lock")
    binding = _graph_plan(document["plan"]).review_lifecycle.run_control
    with run_control_lock(binding), lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            return _schedule_ready_locked(document, args)
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _schedule_ready_locked(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Select the current lanes without reviving a terminal run."""
    plan = _graph_plan(document["plan"])
    if plan.execution_profile not in {"grouped", "mixed"}:
        msg = "schedule-ready requires an adaptive grouped or mixed profile"
        raise ValueError(msg)
    current = _with_current_capture({**document, "journal_path": str(args.journal)}, args.current_capture)
    source_state = _state(document, "source_state")
    events, _state_view, head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    dispatch_set = _read_json_object(args.dispatches)
    ready = next_ready_nodes(current, journal_events=events, dispatch_set=dispatch_set)
    if ready["stop_reason"] is not None:
        result = {**ready, "status": "stopped", "worker_node_ids": [], "coordinator_node_id": None, "cancel_node_ids": ready["lifecycle"]["in_flight_node_ids"]}
        _write_bytes_atomically_once(args.output, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(), mode=0o444)
        return result
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
        if key not in {"artifact_store", "worker_capacity", "creation_failure", "reserved_node_ids", "preflight_blocked_nodes", "worker_requirements"}
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
        "worker_requirements": selection["worker_requirements"],
    }
    failure = selection["creation_failure"]
    if failure is not None and failure["node_id"] not in selected_ids:
        schedule_input["creation_failure"] = failure
    result = {
        **ready,
        **selection,
        **paths,
        "status": "scheduled" if selected_ids else ("blocked" if selection["creation_failure_blockers"] else "waiting"),
        "blockers": [*ready["blockers"], *selection["creation_failure_blockers"]],
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
    binding = _graph_plan(document["plan"]).review_lifecycle.run_control
    with run_control_lock(binding), lock_path.open("a+b") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        try:
            return _fallback_to_coordinator_locked(document, args)
        finally:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)


def _fallback_to_coordinator_locked(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Rebind one unstarted node only while the review is active."""
    _require_running_review(document, args.journal)
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
    if node_id not in entries or state.get(node_id) not in {None, "invalidated"}:
        msg = "fallback requires a planned node with an unstarted pending or invalidated current attempt"
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


def _expanded_validation_bindings(
    document: dict[str, Any], plan: GraphPlan, discoveries: dict[tuple[str, str, str], dict[str, Any]], addition_ids: set[str]
) -> dict[tuple[str, str, str], ValidationRequirementBinding]:
    """Admit aliases only through verified immutable discovery identities."""
    existing = {requirement for unit in plan.coalesced_validation_units for requirement in unit.requirement_ids}
    bindings = _validation_binding_map(plan)
    declared_bindings: set[tuple[str, str, str]] = set()
    for raw in _records(document, "validation_requirement_bindings"):
        binding = _validation_requirement_binding(raw)
        identity = (binding.originating_evidence_id, binding.requirement_id, binding.requirement_digest)
        discovery = discoveries.get(identity)
        if discovery is None:
            msg = "validation requirement binding does not name an exact accepted requirement"
            raise ValueError(msg)
        if identity in declared_bindings:
            msg = "validation requirement binding origins must be unique"
            raise ValueError(msg)
        declared_bindings.add(identity)
        if identity in bindings and bindings[identity] != binding:
            msg = "validation requirement binding cannot replace an existing origin binding"
            raise ValueError(msg)
        if discovery["resolution"] == "planned" and bindings.get(identity) != binding:
            msg = "validation requirement binding cannot replace an already planned obligation"
            raise ValueError(msg)
        if binding.planned_requirement_id not in existing | addition_ids:
            msg = "validation requirement binding names an unknown planned requirement"
            raise ValueError(msg)
        bindings[identity] = binding
    return bindings


def _expanded_validation_plan(
    document: dict[str, Any], plan: GraphPlan, records: Sequence[EvidenceRecord], repository_root: Path, *, authorization: str
) -> GraphPlan:
    reconciliation = _validation_reconciliation(plan, records)
    pending = {item["requirement_id"] for item in reconciliation["requirements"] if item["resolution"] != "planned"}
    raw_requirements = _records(document, "validation_requirements")
    for raw in raw_requirements:
        require_schema_definition(raw, _PLANNING_INPUT_SCHEMA, "validationRequirement")
    additions = validation_requirements_from_document({"validation_requirements": list(raw_requirements)}, repository_root)
    pending.update(_software_doi_recheck_ids(document, [_record_document(record) for record in records], additions))
    existing = {requirement for unit in plan.coalesced_validation_units for requirement in unit.requirement_ids}
    discoveries = {(item["originating_evidence_id"], item["requirement_id"], item["requirement_digest"]): item for item in reconciliation["requirements"]}
    bindings = _expanded_validation_bindings(document, plan, discoveries, {item.requirement_id for item in additions})
    bound_additions = {binding.planned_requirement_id for binding in bindings.values()}
    source_state = _state(document, "source_state")
    for item in additions:
        quality_blockers = _late_validation_quality_blockers(item, repository_root=repository_root, authorization=authorization)
        if quality_blockers:
            msg = f"late validation requirement {item.requirement_id} failed quality gate: " + "; ".join(quality_blockers)
            raise ValueError(msg)
        if item.requirement_id not in pending | bound_additions or item.requirement_id in existing or item.source_state != source_state or not item.required:
            msg = f"late validation must be a new, required, source-matching discovered identity: {item.requirement_id}"
            raise ValueError(msg)
    units, mappings = coalesce_validation_requirements(additions, reserved_node_ids=tuple(node.node_id for node in plan.actual_worker_nodes))
    exclusions = list(plan.validation_exclusions)
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
        validation_requirement_bindings=tuple(bindings[identity] for identity in sorted(bindings)),
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
    _require_running_review(document, args.journal)
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
    if not document.get("validation_requirements") and not document.get("validation_requirement_bindings") and not document.get("user_exclusions"):
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


def _migrate_validation_journal(
    plan: GraphPlan, source_state: tuple[str, str, str], events: tuple[dict[str, Any], ...], retained: set[str], *, replaced_node_id: str | None
) -> tuple[dict[str, Any], ...]:
    """Preserve admission history in order while leaving replaced validation owed."""
    keep = retained | set(plan.pre_review_validation_nodes)
    migrated: list[dict[str, Any]] = []
    state: dict[str, str] = {}

    def append(original: dict[str, Any]) -> None:
        event = {
            **original,
            "affected_node_ids": list(_apply_journal_transition(plan, state, node_id=original["node_id"], status=original["status"])),
            "plan_digest": _plan_digest(plan),
            "previous_event_digest": migrated[-1]["event_digest"] if migrated else None,
            "sequence": len(migrated) + 1,
        }
        event.pop("event_digest", None)
        event["event_digest"] = digest_bytes(canonical_json(event).encode())
        migrated.append(event)

    for event in events:
        if event["node_id"] in keep:
            append(event)
    if replaced_node_id in state and state[replaced_node_id] in {"accepted", "blocked", "in-flight"}:
        append(
            {
                "node_id": replaced_node_id,
                "status": "invalidated",
                "evidence": None,
                "reason": "Validation recovery preserves prior admission history; the replacement attempt remains required.",
                "schema_version": 1,
                "source_state": list(source_state),
            }
        )
    # The full barrier and attempt-identity checks must pass before publication.
    _fold_execution_journal(plan, source_state, tuple(migrated))
    return tuple(migrated)


def _publish_validation_continuation(  # noqa: PLR0913, PLR0917
    document: dict[str, Any],
    args: argparse.Namespace,
    plan: GraphPlan,
    expanded: GraphPlan,
    entries: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    records: Sequence[EvidenceRecord],
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
    retained = {
        node.node_id: entries[node.node_id]
        for node in plan.actual_worker_nodes
        if state.get(node.node_id) in {"accepted", "blocked"} and node.node_id != replaced_node_id and node.mode != "synthesis"
    }
    for node in expanded.actual_worker_nodes:
        if node.node_id in retained and node.node_id in sources:
            _verified_journal_evidence(sources[node.node_id], plan=expanded, node=node, source_state=source_state)
    migrated = _migrate_validation_journal(expanded, source_state, journal_events, set(retained), replaced_node_id=replaced_node_id)
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


def _audit_replacement_marker(plan: GraphPlan) -> Path:
    binding = require_run_control(plan.review_lifecycle.run_control)
    return Path(binding.identity.path).parent / f"audit-replacement-{_plan_digest(plan)[7:]}.json"


def replace_invalidated_audit(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Retire a mistaken judgment without editing source or sealed evidence."""
    plan = _graph_plan(document["plan"])
    lock_path = args.journal.with_name(args.journal.name + ".lock")
    with run_control_lock(plan.review_lifecycle.run_control), lock_path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            return _replace_invalidated_audit_locked(document, args, plan)
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _replacement_plan(plan: GraphPlan, record: dict[str, Any]) -> GraphPlan:
    """Give the affected dependency closure new node and evidence identities."""
    mapping = record["replacement_node_ids"]
    rename = lambda node_id: mapping.get(node_id, node_id)  # noqa: E731 - local identity projection.
    return replace(
        plan,
        actual_worker_nodes=tuple(
            replace(
                node, node_id=rename(node.node_id), predecessors=tuple(map(rename, node.predecessors)), synthesis_dependency=rename(node.synthesis_dependency)
            )
            for node in plan.actual_worker_nodes
        ),
        requirement_to_node=tuple((requirement, rename(node_id)) for requirement, node_id in plan.requirement_to_node),
        routing_decisions=tuple(replace(decision, synthesis_dependency=rename(decision.synthesis_dependency)) for decision in plan.routing_decisions),
        synthesis_nodes=tuple(map(rename, plan.synthesis_nodes)),
        current_epoch_node_ids=tuple(map(rename, plan.current_epoch_node_ids)),
        execution_epochs=tuple(replace(epoch, node_ids=tuple(map(rename, epoch.node_ids))) for epoch in plan.execution_epochs),
        audit_delta_reviews=tuple(item for item in plan.audit_delta_reviews if item["node_id"] not in mapping),
        audit_replacements=(*plan.audit_replacements, record),
    )


def _replace_invalidated_audit_locked(document: dict[str, Any], args: argparse.Namespace, plan: GraphPlan) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915 - one serialized replacement transaction.
    source_state = _state(document, "source_state")
    if _capture_source_state(args.current_capture) != _current_metadata_state(document):
        msg = "audit replacement requires unchanged source state"
        raise ValueError(msg)
    node_id = _required_text(document, "node_id")
    reason = _required_text(document, "reason")
    request_identity = digest_bytes(canonical_json(document).encode())
    marker = _audit_replacement_marker(plan)
    if marker.exists() or marker.is_symlink():
        prior = parse_json_object(read_control_file(marker))
        if prior["request_identity"] != request_identity:
            msg = "audit plan already superseded; follow the replacement continuation"
            raise ValueError(msg)
        result_bytes = _read_regular_file_no_follow(Path(prior["result_path"]))
        if digest_bytes(result_bytes) != prior["result_digest"]:
            msg = "audit replacement result changed"
            raise ValueError(msg)
        return parse_json_object(result_bytes)
    _require_running_review(document, args.journal)
    events, state, head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
    entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=source_state)
    node = next((node for node in plan.actual_worker_nodes if node.node_id == node_id), None)
    if node is None or node.mode != "audit" or state.get(node_id) != "invalidated":
        msg = "audit replacement requires an explicitly invalidated audit"
        raise ValueError(msg)
    accepted = [event for event in events if event["node_id"] == node_id and event["status"] == "accepted"]
    if not accepted:
        msg = "audit replacement requires prior accepted evidence"
        raise ValueError(msg)
    verified, _limitations = _verified_journal_evidence(entries[node_id], plan=plan, node=node, source_state=source_state)
    if verified != accepted[-1]["evidence"]:
        msg = "invalidated audit evidence differs from its accepted journal record"
        raise ValueError(msg)
    if any(status in {"in-flight", "awaiting-replan"} for status in state.values()):
        msg = "audit replacement requires quiescent execution"
        raise ValueError(msg)
    if any(
        item["skill_id"] == node.skill_id and item["requirement_ids"] == list(node.requirement_ids) and tuple(item["source_state"]) == source_state
        for item in plan.audit_replacements
    ):
        msg = "audit replacement allowance exhausted for this contract and source state"
        raise ValueError(msg)
    affected = {node_id}
    while additions := {node.node_id for node in plan.actual_worker_nodes if set(node.predecessors) & affected} - affected:
        affected.update(additions)
    if any(status == "invalidated" and other_id not in affected for other_id, status in state.items()):
        msg = "audit replacement requires no unrelated invalidated nodes; preserve their invalidation history"
        raise ValueError(msg)
    if any(node.mode == "validation" and node.node_id in affected for node in plan.actual_worker_nodes):
        msg = "audit replacement cannot replace validator execution identities"
        raise ValueError(msg)
    record = {
        "node_id": node_id,
        "skill_id": node.skill_id,
        "requirement_ids": list(node.requirement_ids),
        "reason": reason,
        "source_state": list(source_state),
        "previous_plan_digest": _plan_digest(plan),
        "previous_journal_head": head,
        "invalidated_evidence_id": accepted[-1]["evidence"]["evidence_id"],
    }
    identity = digest_bytes(canonical_json(record).encode())[7:23]
    record["replacement_node_ids"] = {old: f"{old}-replacement-{identity}" for old in sorted(affected)}
    repository = Path(entries[node_id]["dispatch"]["repository_root"]).resolve()
    history = Path(_required_text(document, "artifact_store")).resolve() / f"audit-history-{identity}"
    if history.resolve() != history:
        msg = "audit replacement history directory must not traverse symlinks"
        raise ValueError(msg)
    if history.is_relative_to(repository) or repository.is_relative_to(history):
        msg = "audit replacement history must be outside the repository"
        raise ValueError(msg)
    history.mkdir(parents=True, exist_ok=True)
    preserved = []
    for name, content in {
        "lifecycle.json": canonical_json({key: document[key] for key in ("plan", "source_state", "external_metadata_transitions") if key in document}).encode(),
        "execution.jsonl": _read_regular_file_no_follow(args.journal),
        "dispatches.json": _read_regular_file_no_follow(args.dispatches),
    }.items():
        path = history / name
        _write_bytes_atomically_once(path, content, mode=0o444)
        preserved.append({"path": str(path), "digest": digest_bytes(content)})
    for old in sorted(affected):
        paths = [entries[old][field] for field in ("artifact_path", "metadata_path", "worker_payload_path")]
        if Path(entries[old]["metadata_path"]).exists() and (sealed := _read_json_object(Path(entries[old]["metadata_path"])).get("worker_payload_path")):
            paths.append(sealed)
        for path_text in dict.fromkeys(paths):
            path = Path(path_text)
            if path.exists():
                preserved.append({"path": str(path), "digest": digest_bytes(_read_regular_file_no_follow(path))})
    record["preserved_files"] = preserved
    record["forbidden_artifacts"] = sorted({*forbidden_artifacts("", {old: entries[old] for old in affected}), *(item["path"] for item in preserved)})
    sources, records = _accepted_journal_sources(plan, source_state, events, entries, include_blocked=True)
    expanded = _replacement_plan(plan, record)
    result = _publish_validation_continuation(
        document, args, plan, expanded, entries, sources, records, head, status="audit-replaced", journal_events=events, replaced_node_id=node_id
    )
    result["audit_replacement"] = record
    result_path = history / "result.json"
    result_bytes = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    _write_bytes_atomically_once(result_path, result_bytes, mode=0o444)
    _write_bytes_atomically_once(
        marker,
        canonical_json(
            {
                "request_identity": request_identity,
                "result_path": str(result_path),
                "result_digest": digest_bytes(result_bytes),
                "continuation_path": result["continuation_path"],
            }
        ).encode(),
        mode=0o444,
    )
    return result


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
    for replacement in plan.audit_replacements:
        for artifact in _records(replacement, "preserved_files"):
            if digest_bytes(_read_regular_file_no_follow(Path(artifact["path"]))) != artifact["digest"]:
                msg = "preserved audit replacement evidence changed"
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
        f"executor working directory must be absolute before dispatch: {directory!r}; replan with {_workspace_path(directory, repository_root)}"
        for directory in unit.working_directories
        if not Path(directory).is_absolute()
    )
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
        "validation_reuse_prerequisite": validation_reuse_prerequisite(repository_root),
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
    _require_running_review(document, args.journal)
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
    normalized = _record_document(normalized) if normalized is not None else None
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
    retained_records = [record for record in records if _record_document(record).get("node_id") != node_id]
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
        record = _record_document(record) if record is not None else None
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


def _delivery_validation_coverage(item: dict[str, Any], accepted: dict[str, Any], snapshot: ReviewSourceSnapshot | None) -> dict[str, Any]:
    if item["execution"] != "hosted":
        return item
    return {
        **{key: value for key, value in item.items() if key != "platform"},
        "observer_platform": item["platform"],
        **hosted_coverage(accepted.get(item["node_id"], {}), snapshot),
    }


def _proof_limitations(plan: GraphPlan) -> list[dict[str, Any]]:
    """Keep endpoint proof limits visible through subsequent repair and report steps."""
    epochs = plan.review_lifecycle.interleaved_repair_epochs
    return [{**asdict(MissingIntermediateCapture()), "repair_epochs": list(epochs)}] if epochs else []


def report_delivery(document: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0915 - preserve separate typed evidence, source and plan admission gates.
    """Report verified current evidence and outstanding work without certifying a proof."""
    plan = _graph_plan(document["plan"])
    state = _state(document, "source_state")
    if _state(document, "current_source_state") != _current_metadata_state(document):
        msg = "delivery report requires the current reviewed capture"
        raise ValueError(msg)
    records = []
    rejected = []
    for source in _evidence_sources(document, plan):
        _kind, expectation, evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if isinstance(evidence, ReviewEvidence) and isinstance(expectation, ReviewEvidenceExpectation):
            assessment = assess_review_evidence(expectation, evidence)
            source_blockers = review_source_state_blockers(plan, expectation, evidence, state)
        elif isinstance(evidence, ValidationEvidence) and isinstance(expectation, ValidationEvidenceExpectation):
            assessment = assess_validation_evidence(expectation, evidence)
            source_blockers = ()
        else:
            msg = "delivery source has mismatched typed evidence"
            raise TypeError(msg)
        if record is None or not assessment.feasible:
            rejected.append(evidence.evidence_id)
            continue
        if source_blockers:
            rejected.append(evidence.evidence_id)
            continue
        node = next((item for item in plan.actual_worker_nodes if item.node_id == evidence.node_id), None)
        reused_ids = {identity for _requirement, identity in plan.exact_reused_review_evidence}
        if node is None and evidence.evidence_id not in reused_ids:
            rejected.append(evidence.evidence_id)
            continue
        if node is not None and (evidence.requirement_ids, evidence.skill_digest, evidence.reference_digests) != (
            node.requirement_ids,
            node.skill_digest,
            node.reference_digests,
        ):
            rejected.append(evidence.evidence_id)
            continue
        if isinstance(expectation, ValidationEvidenceExpectation) and expectation.validation_unit not in plan.coalesced_validation_units:
            rejected.append(evidence.evidence_id)
            continue
        records.append(record)
    blockers = [*plan.blockers, *plan.routing_completion_blockers, *_metadata_evidence_blockers(document, records)]
    records = [_record_document(record) for record in records]
    accepted = {record["node_id"]: record for record in records}
    incomplete = [node.node_id for node in plan.actual_worker_nodes if node.node_id not in accepted or accepted[node.node_id]["status"] == "blocked"]
    pending_semantic = [node.node_id for node in plan.actual_worker_nodes if node.mode != "synthesis" and node.node_id in incomplete]
    transitions = tuple(metadata_transition(item) for item in _records(document, "external_metadata_transitions"))
    validations = [
        {
            "node_id": unit.node_id,
            "requirement_ids": list(unit.requirement_ids),
            "platform": unit.platform,
            "execution": "hosted"
            if native_target(transitions, unit.node_id) is not None or not unit.commands or accepted.get(unit.node_id, {}).get("native_ci")
            else "local",
            "required": unit.required,
            "status": accepted.get(unit.node_id, {}).get("status", "pending-or-unavailable"),
        }
        for unit in plan.coalesced_validation_units
    ]
    snapshots = [*plan.reuse_source_snapshots, *(transition.after for transition in transitions)]
    snapshots.extend(source_snapshot(record["source_inputs"]) for record in records if record.get("source_inputs"))
    current_snapshot = next((snapshot for snapshot in snapshots if snapshot.source_state == _current_metadata_state(document)), None)
    validations = [_delivery_validation_coverage(item, accepted, current_snapshot) for item in validations]
    blockers.extend(
        f"required validation {item['node_id']}: {item.get('delivered_source_status', item['status'])}"
        for item in validations
        if item["required"] and item.get("delivered_source_status", item["status"]) not in {"passed", "reused"}
    )
    blockers.extend(f"rejected evidence: {identity}" for identity in rejected)
    handoffs = reconcile_handoffs(document)
    blockers.extend(handoffs["blockers"])
    blockers.extend(_validation_reconciliation(plan, records)["blockers"])
    if (reason := _review_stop_reason(document)) is not None:
        blockers.append("review stopped: " + reason)
    remaining = [{"evidence_id": record["evidence_id"], "findings": record["findings"]} for record in records if record.get("findings")]
    return {
        "schema_version": 1,
        "status": "reported",
        "delivery_profile": "routine",
        "graph_proof_status": "not-certified",
        "proof_limitations": _proof_limitations(plan),
        "review_lifecycle": asdict(plan.review_lifecycle),
        "repairs_completed": plan.review_lifecycle.repairs_completed,
        "current_source_state": list(_current_metadata_state(document)),
        "incomplete_node_ids": incomplete,
        "pending_semantic_node_ids": pending_semantic,
        "validation": validations,
        "local_validation": [item for item in validations if item["execution"] == "local"],
        "hosted_ci": [item for item in validations if item["execution"] == "hosted"],
        "outstanding_hosted_ci": [item for item in validations if item["execution"] == "hosted" and item["delivered_source_status"] != "passed"],
        "remaining_findings": remaining,
        "blockers": blockers,
        "repository_readiness": "blocked" if blockers or pending_semantic or remaining else "verification-complete",
        "summary": {"accepted_evidence": len(records), "pending_nodes": len(incomplete), "remaining_finding_groups": len(remaining)},
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
        str, tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, EvidenceRecord | None]
    ] = {}
    duplicate_evidence: set[str] = set()
    for source in sources:
        kind, record_expectation, evidence, content, normalized = _load_evidence_source(source)
        if evidence.evidence_id in loaded:
            duplicate_evidence.add(evidence.evidence_id)
        loaded[evidence.evidence_id] = (kind, record_expectation, evidence, content, normalized)
    preblockers = list(_text_list(document, "lifecycle_blockers"))
    if (reason := _review_stop_reason(document)) is not None:
        preblockers.append("review stopped: " + reason)
    normalized_records = [_record_document(record) for *_rest, record in loaded.values() if record is not None]
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
        evidence_id: _record_document(normalized)
        for evidence_id, (_kind, _expectation, _evidence, _content, normalized) in loaded.items()
        if normalized is not None
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
    final_record = normalized_by_evidence.get(final_synthesis_evidence_id)
    return {
        "artifact_manifest": asdict(manifest),
        "blockers": list(blockers),
        "graph_proof_status": graph_proof_status,
        "proof_limitations": _proof_limitations(plan),
        "validation_recoveries": list(plan.validation_recoveries),
        "audit_replacements": list(plan.audit_replacements),
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
    control_parser = _runtime_subparser(subparsers, "review-control", "check repair budget, extend it explicitly, authorize a comprehensive restart, or stop")
    for flag in ("input", "output", "journal", "dispatches", "current-capture"):
        control_parser.add_argument("--" + flag, type=Path, required=True)
    resume_parser = _runtime_subparser(subparsers, "resume-after-external-metadata", "resume after verified external staging without changing Git")
    resume_parser.add_argument("--input", type=Path, required=True)
    resume_parser.add_argument("--output", type=Path, required=True)
    commit_parser = _runtime_subparser(subparsers, "resume-after-authorized-commit", "reconcile reviewed bytes with an authorized commit and exact-commit CI")
    commit_parser.add_argument("--input", type=Path, required=True)
    commit_parser.add_argument("--output", type=Path, required=True)
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
    timing_parser = _runtime_subparser(subparsers, "prepare-validation-timing", "bind an explicit execution-tool shell policy before validator creation")
    timing_parser.add_argument("--input", type=Path, required=True, help="materialized validator worker-payload contract")
    timing_parser.add_argument("--shell-policy", type=Path, required=True, help="operator-approved literal shell_argv JSON")
    preflight_parser = _runtime_subparser(subparsers, "preflight-validation", "inspect command policy, caches and validation obligations before fanout")
    preflight_parser.add_argument("--input", type=Path, required=True)
    preflight_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser = _runtime_subparser(subparsers, "snapshot-workspace", "capture runtime-owned validation workspace evidence")
    snapshot_parser.add_argument("--input", type=Path, required=True)
    snapshot_parser.add_argument("--dispatches", type=Path)
    snapshot_parser.add_argument("--node-id")
    snapshot_parser.add_argument("--current-capture", type=Path, required=True)
    snapshot_parser.add_argument("--output", type=Path, required=True)
    mutation_parser = _runtime_subparser(subparsers, "advance-after-mutation", "recapture and replan one serialized repair epoch")
    mutation_parser.add_argument("--input", type=Path, required=True)
    mutation_parser.add_argument("--output", type=Path, required=True)
    external_source_parser = _runtime_subparser(subparsers, "resume-after-external-source", "reconcile attributed source edits without spending agent repairs")
    external_source_parser.add_argument("--input", type=Path, required=True)
    external_source_parser.add_argument("--output", type=Path, required=True)
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
        ("replace-invalidated-audit", "replace an accepted audit invalidated for applying the wrong semantic checklist"),
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
    schedule_parser.add_argument("--worker-capacity", type=Path, help="fresh aggregate capacity JSON; required when scheduling a bootstrap bundle")
    schedule_parser.add_argument("--worker-requirements", type=Path, help="per-node worker/model requirements JSON array, retained in scheduling lineage")
    schedule_parser.add_argument("--artifact-store", type=Path, help="explicit scheduling artifact store override")
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
    delivery_parser = _runtime_subparser(subparsers, "report-delivery", "report fixes, verified evidence and pending CI without formal certification")
    for flag in ("input", "output", "dispatches", "journal", "current-capture"):
        delivery_parser.add_argument("--" + flag, type=Path, required=True)
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
    document = {**document, "journal_path": str(args.journal)}
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
            **{key: entry["dispatch"][key] for key in ("skill_id", "mode", "selection_reason")},
            **({"validation_observations": entry["dispatch"]["validation_observations"]} if "validation_observations" in entry["dispatch"] else {}),
            "node_id": entry["node_id"],
            "result_contract": entry["result_contract"],
            "worker_input_path": entry["worker_input_path"],
            **({"worker_execution_path": entry["worker_execution_path"]} if "worker_execution_path" in entry else {}),
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
    if args.journal is not None:
        output["journal_path"] = str(args.journal)
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
        dispatch["fresh_context_forbidden_artifacts"] = sorted(
            set(dispatch.get("fresh_context_forbidden_artifacts", [])) | set(forbidden_artifacts(node_id, entries))
        )
    return plan, selected


def _snapshot_workspace_from_files(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if "compiler_preflight" in document:
        dispatch = _publication_dispatch(document)
        if dispatch is None or dispatch.get("mode") != "validation" or args.dispatches is not None or args.node_id is not None:
            msg = "contract workspace snapshots require a bound validator identity without caller node overrides"
            raise ValueError(msg)
        expected = _current_metadata_state(dispatch)
    else:
        if args.dispatches is None or args.node_id is None:
            msg = "lifecycle workspace snapshots require --dispatches and --node-id"
            raise ValueError(msg)
        _plan, entry = _lifecycle_dispatch(document, args.dispatches, args.node_id)
        dispatch = entry.get("dispatch")
        expected = _current_metadata_state(document)
    if _capture_source_state(args.current_capture) != expected:
        msg = "workspace snapshot capture differs from the plan-bound source state"
        raise ValueError(msg)
    if not isinstance(dispatch, dict) or dispatch.get("mode") != "validation":
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


def _verify_audit_captures(dispatch: dict[str, Any], before: Path, after: Path) -> None:
    """Bind each complete capture and compact receipt to its dispatched path."""
    for phase, path in (("before", before), ("after", after)):
        observation = dispatch.get("audit_observations", {}).get(phase)
        if observation is None:
            continue
        if str(path.absolute()) != observation["capture_path"]:
            msg = f"audit {phase} capture must use its dispatched artifact path"
            raise ValueError(msg)
        content = _read_regular_file_no_follow(path)
        snapshot = source_snapshot(parse_json_object(content))
        snapshot.verify()
        expected = {
            "schema_version": 1,
            "capture_path": str(path.absolute()),
            "capture_digest": digest_bytes(content),
            "scope_fingerprint": snapshot.scope_fingerprint,
            "captured_worktree_fingerprint": snapshot.captured_worktree_fingerprint,
            "repository_state_fingerprint": snapshot.repository_state_fingerprint,
        }
        if (
            snapshot.repository_root != dispatch["repository_root"]
            or parse_json_object(_read_regular_file_no_follow(Path(observation["receipt_path"]))) != expected
        ):
            msg = f"audit {phase} capture receipt does not match its durable observation"
            raise ValueError(msg)


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
    _verify_audit_captures(raw_dispatch, args.before_capture, args.after_capture)
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
        payload = parse_json_object(payload_bytes)
        require_schema(payload, _review_payload_schema(dispatch) if contract == "compact-review" else _VALIDATION_PAYLOAD_SCHEMA)
        if dispatch.get("mode") == "synthesis":
            events, _lifecycle, _head = read_execution_journal(args.journal, plan=plan, source_state=source_state)
            entries = _dispatches_by_node(_read_json_object(args.dispatches), plan=plan, source_state=source_state)
            sources, _records_view = _accepted_journal_sources(plan, source_state, events, entries)
            dispatch["synthesis_bundle"] = build_synthesis_bundle({**document, "sources": list(sources.values())})
        compiler_input = {"dispatch": dispatch, "payload": payload}
        content, metadata = compile_review(compiler_input) if contract == "compact-review" else compile_validation(compiler_input)
    elif contract == "compact-independent-review":
        payload = parse_json_object(payload_bytes)
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


def _json_operation_output(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:  # noqa: C901, PLR0911, PLR0912
    if args.operation == "review-control":
        return review_control(document, args)
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
    if args.operation == "resume-after-external-source":
        return resume_after_external_source(document)
    if args.operation == "resume-after-authorized-commit":
        return resume_after_authorized_commit(document)
    if args.operation == "reconcile-handoffs":
        return reconcile_handoffs(document)
    if args.operation in {
        "reconcile-validation-requirements",
        "fallback-to-coordinator",
        "recover-validation-launch",
        "recover-validation-execution",
        "replace-invalidated-audit",
    }:
        operation = {
            "reconcile-validation-requirements": reconcile_validation_requirements,
            "fallback-to-coordinator": fallback_to_coordinator,
            "recover-validation-launch": recover_validation_launch,
            "recover-validation-execution": recover_validation_execution,
            "replace-invalidated-audit": replace_invalidated_audit,
        }[args.operation]
        return operation(document, args)
    if args.operation == "next-ready":
        return _next_ready_from_files(document, args)
    if args.operation == "report-delivery":
        return report_delivery(_finalize_document_from_files(document, args))
    return finalize_proof(_finalize_document_from_files(document, args))


def _isolation_attempts(document: dict[str, Any]) -> list[str]:
    target = Path(document["worker_payload_path"])
    return sorted(str(path) for path in target.parent.glob(f"{document['node_id']}.isolation-rejected.*.json") if not path.name.endswith(".receipt.json"))


def _provenance_attempts(document: dict[str, Any]) -> list[Path]:
    return list(Path(document["worker_payload_path"]).parent.glob(f"{document['node_id']}.provenance-rejected.*.json"))


def _retain_provenance_rejection(document: dict[str, Any], content: bytes, error: ValueError) -> None:
    target = Path(document["worker_payload_path"])
    identity = digest_bytes(content).removeprefix("sha256:")
    path = target.with_name(f"{document['node_id']}.provenance-rejected.{identity}.json")
    receipt = {
        "error": str(error),
        "payload": parse_json_object(content),
        "payload_digest": digest_bytes(content),
        "recovery": (
            "Correct the missing declarations from actual reads before acceptance; one correction attempt is allowed. Declarations do not prove comprehension."
        ),
    }
    _write_bytes_atomically_once(path, (canonical_json(receipt) + "\n").encode(), mode=0o400)


def _require_isolation_budget(document: dict[str, Any]) -> None:
    if len(_isolation_attempts(document)) >= 2:
        msg = "audit isolation replacement exhausted; retain rejected attempts and leave only this node blocked"
        raise ValueError(msg)


def _retain_isolation_rejection(document: dict[str, Any], payload_bytes: bytes, error: ValueError) -> dict[str, Any]:
    target = Path(document["worker_payload_path"])
    with target.with_name(f".{document['node_id']}.isolation.lock").open("ab") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        identity = digest_bytes(payload_bytes).removeprefix("sha256:")
        rejected = target.with_name(f"{document['node_id']}.isolation-rejected.{identity}.json")
        _write_bytes_atomically_once(rejected, payload_bytes, mode=0o400)
        receipt = {
            "schema_version": 1,
            "status": "rejected",
            "error": "fresh-audit-isolation",
            "message": str(error),
            "node_id": document["node_id"],
            "rejected_payload": {"path": str(rejected), "digest": digest_bytes(payload_bytes)},
            "maximum_replacement_workers": 1,
            "recovery": (
                "Retain this attempt. Replace only this node with a clean fresh worker using the same dispatch; do not replay accepted nodes or restart review."
            ),
        }
        _write_bytes_atomically_once(rejected.with_suffix(".receipt.json"), (canonical_json(receipt) + "\n").encode(), mode=0o400)
        attempts = _isolation_attempts(document)
        return {**receipt, "rejected_attempts": attempts, "replacement_allowed": len(attempts) == 1}


def _validation_owner_warnings(contract: dict[str, Any], payload_bytes: bytes) -> list[str]:
    """Flag exact alternate specialist names without policing shared owner labels."""
    dispatch = _publication_dispatch(contract)
    if dispatch is None or dispatch.get("mode") != "audit":
        return []
    skill_root = Path(dispatch["skill_path"]).parent.parent
    return [
        f"Validation owner {owner} differs from dispatch skill {dispatch['skill_id']}; verify the applied checklist. Shared validator owners are allowed."
        for requirement in parse_json_object(payload_bytes).get("validation_requirements", [])
        if (owner := requirement["owner"]) not in {dispatch["skill_id"], "review-validator"}
        and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", owner)
        and (skill_root / owner / "SKILL.md").is_file()
    ]


def publish_worker_payload_bytes(document: dict[str, Any], payload_bytes: bytes, *, approval_identity: str | None = None) -> dict[str, Any]:
    """Review and publish identical bound bytes in one supported transaction."""
    review = _approved_worker_payload_write(document, payload_bytes, approval_identity, candidate_is_write_target=False)
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
        "warnings",
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
    if args.operation in {"schedule-ready", "next-ready"}:
        summaries = receipt["launch_manifest"]["nodes"] if args.operation == "schedule-ready" else receipt["ready_dispatches"]
        for summary, entry in zip(summaries, output["ready_dispatches"], strict=True):
            if observations := entry.get("dispatch", entry).get("validation_observations"):
                summary["compile_command"] = runtime_command(
                    Path(__file__),
                    "compile-node",
                    "--input",
                    output.get("lifecycle_input_path", str(args.input.resolve())),
                    "--dispatches",
                    output.get("dispatches_path", str(args.dispatches.resolve())),
                    "--node-id",
                    entry["node_id"],
                    "--before-capture",
                    observations["before"]["capture_path"],
                    "--after-capture",
                    observations["after"]["capture_path"],
                    "--workspace-before",
                    observations["before"]["workspace_path"],
                    "--workspace-after",
                    observations["after"]["workspace_path"],
                    "--journal",
                    str(args.journal.resolve()),
                    "--output",
                    str(Path(entry["worker_input_path"]).with_suffix(".compiled.json")),
                )
    if args.operation == "materialize-dispatches":
        receipt["next_operation_inputs"] = {"dispatches": str(output_path.resolve())}
        bundle = _read_json_object(args.input)
        if "lifecycle_input" in bundle and "capture_path" in bundle and bundle["plan"]["execution_profile"] in {"grouped", "mixed"}:
            capacity_path = args.input.resolve().with_suffix(".capacity.json")
            receipt["next_command"] = runtime_command(
                Path(__file__),
                "schedule-ready",
                "--input",
                str(args.input.resolve()),
                "--dispatches",
                str(output_path.resolve()),
                "--journal",
                str(args.input.resolve().with_suffix(".journal.jsonl")),
                "--current-capture",
                bundle["capture_path"],
                "--worker-capacity",
                str(capacity_path),
                "--output",
                str(args.input.resolve().with_suffix(".schedule.json")),
            )
            receipt["scheduler_prerequisite"] = {
                "path": str(capacity_path),
                "required_fields": ["source", "concurrent_worker_limit", "active_workers"],
                "instruction": "Write a fresh authoritative aggregate capacity observation before executing next_command. Recapture if source changed.",
            }
    if (manifest := receipt.get("launch_manifest")) is not None:
        manifest["next_operation_inputs"] = receipt.get("next_operation_inputs", {})
        if receipt.get("next_command"):
            manifest["next_command"] = receipt["next_command"]
        if args.operation != "next-ready":
            manifest_path = output_path.with_suffix(".launch.json")
            _write_bytes_atomically_once(manifest_path, (canonical_json(manifest) + "\n").encode(), mode=0o444)
            receipt["launch_manifest_reference"] = artifact_reference(manifest_path)
            if args.operation in {"materialize-dispatches", "schedule-ready"}:
                del receipt["launch_manifest"]
    print(canonical_json(output if args.full_output else receipt))


def _prepare_validation_timing(document: dict[str, Any], args: argparse.Namespace) -> int:
    dispatch = _publication_dispatch(document)
    if dispatch is None:
        msg = "timing preparation requires a bound validator publication contract"
        raise ValueError(msg)
    writes, manifest = timing_documents(dispatch, _read_json_object(args.shell_policy))
    for path, content in writes.items():
        _write_bytes_atomically_once(path, content, mode=0o444)
    print(canonical_json({"status": "prepared", "manifest_path": dispatch["timing_prerequisite"]["manifest_path"], "launches": manifest["launches"]}))
    return 0


def _write_json_operation_result(args: argparse.Namespace, output_path: Path, output: dict[str, Any]) -> None:
    """Write the result, retaining recovery paths after a completed source resume."""
    output_text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.operation in {"recover-validation-launch", "recover-validation-execution", "reconcile-validation-requirements", "replace-invalidated-audit"}:
        _write_bytes_atomically_once(output_path, output_text.encode(), mode=0o644)
        return
    try:
        _write_text_once(output_path, output_text)
    except (OSError, ValueError) as error:
        if args.operation != "resume-after-external-source" and not (
            args.operation == "advance-after-mutation" and output.get("transition_kind") == "interleaved-repair-and-staging"
        ):
            raise
        paths = {key: output[key] for key in ("lifecycle_input_path", "dispatches_path", "capture_path", "journal_path")}
        msg = f"result file could not be written: {error}; continuation was published; resume using these retained paths: {canonical_json(paths)}"
        raise ValueError(msg) from error


def _run_operation(document: dict[str, Any], args: argparse.Namespace) -> int:  # noqa: C901, PLR0912, PLR0911
    if args.operation == "prepare-validation-timing":
        return _prepare_validation_timing(document, args)
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
    if args.operation in {"materialize-dispatches", "schedule-ready", "review-control"}:
        if args.operation == "materialize-dispatches":
            output = materialize_dispatches(document, operation_output_path=args.output)
        elif args.operation == "review-control":
            output = review_control(document, args, operation_output_path=args.output)
        else:
            output = schedule_ready(document, args)
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
    _write_json_operation_result(args, output_path, output)
    _print_operation_result(args, output_path, output)
    return 2 if args.operation == "finalize-proof" and output["status"] != "complete" else 0


def _operation_input(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    operation_document = _operation_document(document, args.operation)
    if args.operation == "schedule-ready":
        if "lifecycle_input" in document and args.worker_capacity is None:
            msg = "bootstrap scheduling requires --worker-capacity <fresh-capacity.json>; signed plan identities stay in the retained bundle"
            raise ValueError(msg)
        if args.worker_capacity is not None:
            operation_document["worker_capacity"] = _read_json_object(args.worker_capacity)
        if args.worker_requirements is not None:
            operation_document["worker_requirements"] = json.loads(args.worker_requirements.read_bytes())
        if args.artifact_store is not None:
            operation_document["artifact_store"] = str(args.artifact_store.resolve())
    require_schema_definition(operation_document, _RUNTIME_OPERATION_INPUT_SCHEMA, args.operation)
    return operation_document


def main(argv: list[str] | None = None) -> int:
    """Run one deterministic review-graph compiler operation."""
    args = _argument_parser().parse_args(argv)
    document: object = None
    try:
        document = parse_json_object(args.input.read_bytes())
        operation_document = _operation_input(document, args)
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
        if isinstance(error, IsolationPublicationError):
            print(canonical_json(error.receipt), file=sys.stderr)
        elif isinstance(error, WorkerPayloadWriteError):
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
            output = {
                **error.as_dict(),
                "handoff_attempt": attempt,
                "maximum_handoff_attempts": 2,
                "retry_allowed": retry_allowed,
                "rejection": EvaluationRejection.from_exception(error).as_dict(),
            }
            print(canonical_json(output), file=sys.stderr)
        else:
            print(
                canonical_json(
                    {
                        "status": "rejected",
                        "message": f"review_graph_runtime: {format_exception_diagnostics(error)}",
                        "rejection": EvaluationRejection.from_exception(error).as_dict(),
                    }
                ),
                file=sys.stderr,
            )
        return 2


if __name__ == "__main__":
    from review_graph_session import verify_current_snapshot

    verify_current_snapshot()
    raise SystemExit(main())
