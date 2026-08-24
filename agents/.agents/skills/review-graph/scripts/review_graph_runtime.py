"""Materialize, compile, schedule, and verify deterministic review-graph artifacts."""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from review_graph_bootstrap import bootstrap_document
from review_graph_plan import (
    DEFAULT_ROUTING_CATALOG,
    DEFAULT_SKILL_ROOT,
    EVIDENCE_SCHEMA_VERSION,
    NATIVE_EVIDENCE_BLOCK_CLOSE,
    NATIVE_EVIDENCE_BLOCK_OPEN,
    ArtifactPayload,
    ExecutionEpoch,
    FingerprintEvidence,
    GraphPlan,
    RepositoryReviewProof,
    ReusedReviewEvidencePlan,
    ReviewEvidence,
    ReviewEvidenceExpectation,
    RoutingDecision,
    TrustedArtifactVerifier,
    ValidationArtifact,
    ValidationEvidence,
    ValidationEvidenceExpectation,
    ValidationEvidenceMapping,
    ValidationUnit,
    WorkerNode,
    _file_identity_digest,
    _native_field_values,
    _native_heading_blockers,
    _native_record_fields,
    _native_records,
    _native_repository_path_list,
    _native_section_bodies,
    _review_native_result_blockers,
    _validation_environment_identity,
    _validation_ledger_expected_fields,
    _validation_native_result_blockers,
    _validation_plan_expected_body,
    _validation_requirements_expected_body,
    assess_evidence_bundle,
    assess_review_evidence,
    assess_validation_evidence,
    build_routing_projection,
    create_artifact_manifest,
    load_routing_catalog,
    plan_from_document,
    repository_review_proof_expectation,
    validation_evidence_expectation,
)
from review_graph_schema import SchemaValidationError, require_schema

_READ_ONLY_MODES = frozenset({"audit", "revalidation", "synthesis"})
_REVIEW_MODES = _READ_ONLY_MODES | {"fix"}
_REVIEW_STATUSES = frozenset({"blocked", "completed", "no-findings"})
_SEVERITIES = frozenset({"P0", "P1", "P2", "P3"})
_JOURNAL_STATUSES = frozenset({"accepted", "awaiting-replan", "blocked", "in-flight", "invalidated"})
_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references" / "schemas"
_PLANNING_INPUT_SCHEMA = _SCHEMA_ROOT / "planning-input-v1.schema.json"
_REVIEW_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "review-payload-v1.schema.json"
_VALIDATION_PAYLOAD_SCHEMA = _SCHEMA_ROOT / "validation-payload-v1.schema.json"
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


@dataclass(frozen=True)
class JournalEventRequest:
    """Runtime facts for one coordinator-owned lifecycle transition."""

    node_id: str
    status: str
    source: dict[str, Any] | None = None
    reason: str | None = None


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write_bytes_once(path: Path, content: bytes) -> None:
    """Create an immutable artifact, permitting only an identical replay."""
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            msg = f"refusing to overwrite non-identical artifact: {path}"
            raise ValueError(msg) from None


def _write_text_once(path: Path, content: str) -> None:
    _write_bytes_once(path, content.encode("utf-8"))


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
        for field_name in ("owner", "reason", "working_directory", "environment", "expected_evidence", "dependency_policy"):
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
    return "\n".join(
        "\n".join(
            (
                f"- Requirement ID: {requirement_id}",
                f"  - Owner: {record['owner']}",
                f"  - Reason: {record['reason']}",
                f"  - Commands: {' && '.join(record['commands'])}",
                f"  - Working directories: {record['working_directory']}",
                f"  - Environment/configuration: {record['environment']}",
                f"  - Expected evidence: {record['expected_evidence']}",
                f"  - Dependency policy: {record['dependency_policy']}",
                "  - Disposition: required",
                "  - Ledger evidence: none",
            )
        )
        for requirement_id, record in records
    )


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
    findings = _finding_records(payload, evidence.node_id)
    validations = _validation_records(payload)
    handoffs = _handoff_records(payload, evidence.node_id)
    changes = tuple({"change_id": f"{evidence.node_id}-change-{ordinal}", **change} for ordinal, change in enumerate(_records(payload, "changes"), start=1))
    return {
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": evidence.raw_result_artifact_id,
        "changes": list(changes),
        "command_policy_attested": payload.get("command_policy_attested", False),
        "commands_executed": list(_text_list(payload, "commands_executed")),
        "evidence_id": evidence.evidence_id,
        "files_inspected": list(_text_list(payload, "files_inspected")),
        "findings": [{"finding_id": finding_id, **finding} for finding_id, finding in findings],
        "handoffs": [{"handoff_id": handoff_id, **handoff} for handoff_id, handoff in handoffs],
        "limitations": list(_text_list(payload, "limitations")),
        "mode": evidence.mode,
        "node_id": evidence.node_id,
        "nearby_contract_owners": list(_text_list(payload, "nearby_contract_owners")),
        "payload_digest": _sha256_bytes(_canonical_json(payload).encode()),
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
        return () if attested in {None, True} else ("review payload must attest to the dispatched command policy",)
    if not isinstance(raw_policy, dict):
        return ("review dispatch command_policy must be an object",)
    if attested is not True:
        return ("review payload must attest to the dispatched command policy",)
    prohibited = set(_text_list(raw_policy, "prohibited_commands"))
    duplicates = tuple(command for command in commands if command in prohibited)
    if duplicates:
        return ("review payload executed commands owned by planned validators: " + ", ".join(duplicates),)
    return ()


def _review_handoff_catalog_blockers(dispatch: dict[str, Any], handoffs: tuple[tuple[str, dict[str, Any]], ...]) -> tuple[str, ...]:
    raw_catalog_ids = dispatch.get("handoff_catalog_ids")
    if raw_catalog_ids is None:
        catalog_ids = {entry.catalog_id for entry in load_routing_catalog(DEFAULT_ROUTING_CATALOG, skill_roots=(DEFAULT_SKILL_ROOT,))}
    else:
        catalog_ids = set(_text_list(dispatch, "handoff_catalog_ids"))
    unknown = tuple(sorted({_required_text(record, "catalog_id") for _handoff_id, record in handoffs} - catalog_ids))
    return ("review payload contains unknown handoff catalog IDs: " + ", ".join(unknown),) if unknown else ()


def compile_review(document: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:  # noqa: C901, PLR0915
    """Compile one compact semantic payload into the legacy verified artifact."""
    dispatch = document.get("dispatch")
    payload = document.get("payload")
    if not isinstance(dispatch, dict) or not isinstance(payload, dict):
        msg = "compile-review input requires dispatch and payload objects"
        raise TypeError(msg)
    mode = _required_text(dispatch, "mode")
    if mode not in _REVIEW_MODES:
        msg = f"compact compiler does not support mode {mode}"
        raise ValueError(msg)
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
    findings = _finding_records(payload, node_id)
    validations = _validation_records(payload)
    handoffs = _handoff_records(payload, node_id)
    policy_blockers = _review_command_policy_blockers(dispatch, payload)
    handoff_blockers = _review_handoff_catalog_blockers(dispatch, handoffs)
    limitations = _text_list(payload, "limitations")
    if status == "no-findings" and findings:
        msg = "no-findings payload cannot contain findings"
        raise ValueError(msg)
    if status == "blocked" and not limitations:
        msg = "blocked payload requires a limitation"
        raise ValueError(msg)
    files_inspected = _text_list(payload, "files_inspected", required=status != "blocked")
    nearby_contract_owners = _text_list(payload, "nearby_contract_owners")
    requirement_ids = _text_list(dispatch, "requirement_ids")
    predecessor_evidence_ids = _text_list(dispatch, "predecessor_evidence_ids")
    evidence_id = _required_text(dispatch, "evidence_id")
    artifact_id = _required_text(dispatch, "artifact_id")
    fingerprints = FingerprintEvidence(expected=expected, before=before, after=after)
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
    )
    canonical_payload = _canonical_json(payload)
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
        "## Scope Inspected": "\n".join(
            (
                f"- Files: {', '.join(files_inspected) or 'blocked-before-inspection'}",
                f"- Nearby contract owners: {', '.join(nearby_contract_owners) or 'none'}",
                f"- Worker payload digest: {_sha256_bytes(canonical_payload.encode())}",
                f"- Canonical worker payload: {canonical_payload}",
            )
        ),
        "## Findings": _findings_body(findings),
        "## Validation": "none",
        "## Validation Requirements": _validation_body(validations),
        "## Predecessor Coverage": _predecessor_body(dispatch, evidence),
        "## Changes": _changes_body(payload, evidence, changed_paths),
        "## Handoffs": _handoffs_body(handoffs),
        "## Limitations": "; ".join(limitations) or "none",
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
    content = (
        f"# Review Node Result\n\n{_review_header(expectation, evidence)}\n\n{body}\n\n## Machine Evidence\n\n"
        f"{NATIVE_EVIDENCE_BLOCK_OPEN}{_canonical_json(machine_payload)}{NATIVE_EVIDENCE_BLOCK_CLOSE}\n"
    ).encode()
    evidence = replace(evidence, raw_result_digest=_sha256_bytes(content))
    envelope_assessment = assess_review_evidence(expectation, evidence)
    native_blockers = _review_native_result_blockers(content, expectation, evidence)
    blockers = (*policy_blockers, *handoff_blockers, *envelope_assessment.blockers, *native_blockers)
    if blockers:
        msg = "compiled review artifact failed verification: " + "; ".join(blockers)
        raise ValueError(msg)
    metadata = {
        "expectation": asdict(expectation),
        "evidence": asdict(evidence),
        "payload_digest": _sha256_bytes(canonical_payload.encode()),
        "artifact_digest": evidence.raw_result_digest,
        "normalized_record": _review_normalized_record(payload, expectation, evidence),
    }
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
    labels = ("Severity", "Location", "Summary", "Evidence", "Impact", "Owner", "Remediation")
    for ordinal, (_worker_identity, record_body) in enumerate(records, start=1):
        fields, blockers = _native_record_fields(record_body, section=f"independent Finding {ordinal}", labels=labels)
        if blockers:
            msg = "; ".join(blockers)
            raise ValueError(msg)
        severity = fields["Severity"]
        if severity not in _SEVERITIES:
            msg = f"independent Finding {ordinal} has invalid severity {severity}"
            raise ValueError(msg)
        output.append((f"{node_id}-finding-{ordinal}", dict(fields)))
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


def compile_independent_review(document: dict[str, Any], native_content: bytes) -> tuple[bytes, dict[str, Any]]:  # noqa: C901, PLR0912, PLR0915
    """Wrap one conclusion-blind native independent review in verified graph evidence."""
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
        msg = "accepted independent review must not contain limitations"
        raise ValueError(msg)
    sections = _independent_input_sections(native_content)
    node_id = _required_text(dispatch, "node_id")
    if status != "blocked":
        scope_blockers = _independent_scope_blockers(sections["## Scope Inspected"], dispatch)
        if scope_blockers:
            msg = "; ".join(scope_blockers)
            raise ValueError(msg)
    findings = _independent_findings(sections["## Findings"], node_id, status)
    if status == "completed" and not findings:
        msg = "completed independent review requires at least one finding"
        raise ValueError(msg)
    if status == "no-findings":
        inspected_checks = set(_native_field_values(sections["## No-Finding Evidence"], "Inspected"))
        missing_checks = tuple(check for check in _text_list(dispatch, "adversarial_checks") if check not in inspected_checks)
        if missing_checks:
            msg = "independent no-findings evidence omits dispatched adversarial checks: " + ", ".join(missing_checks)
            raise ValueError(msg)
    handoffs = _independent_handoffs(sections["## Routing Handoffs"], node_id, dispatch)
    expected = _state(dispatch, "source_state")
    before = _state(dispatch, "before_state")
    after = _state(dispatch, "after_state")
    skill_path = Path(_required_text(dispatch, "skill_path")).resolve()
    if not skill_path.is_file():
        msg = f"independent review skill file does not exist: {skill_path}"
        raise ValueError(msg)
    reference_paths = tuple(Path(path).resolve() for path in _text_list(dispatch, "reference_paths"))
    if any(not path.is_file() for path in reference_paths):
        msg = "every independent review reference path must exist"
        raise ValueError(msg)
    planned_paths = _text_list(dispatch, "planned_paths", required=True)
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
    fingerprints = FingerprintEvidence(expected=expected, before=before, after=after)
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
    )
    results = tuple("matched" if observed == expected else "mismatched" for observed in (before, after))
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
            f"- Files inspected: {', '.join(planned_paths)}",
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
        "inspected_paths": list(planned_paths),
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
        "## Machine Evidence": f"{NATIVE_EVIDENCE_BLOCK_OPEN}{_canonical_json(machine_payload)}{NATIVE_EVIDENCE_BLOCK_CLOSE}",
    }
    ordered = (*_INDEPENDENT_NATIVE_SECTIONS, "## Review Graph Envelope", "## Machine Evidence")
    content = ("# Repository Independent Review\n\n" + "\n\n".join(f"{section}\n\n{output_sections[section]}" for section in ordered) + "\n").encode()
    evidence = replace(evidence, raw_result_digest=_sha256_bytes(content))
    assessment = assess_review_evidence(expectation, evidence)
    native_blockers = _review_native_result_blockers(content, expectation, evidence)
    blockers = (*assessment.blockers, *native_blockers)
    if blockers:
        msg = "compiled independent review failed verification: " + "; ".join(blockers)
        raise ValueError(msg)
    normalized = {
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": artifact_id,
        "changes": [],
        "evidence_id": evidence_id,
        "files_inspected": list(planned_paths),
        "findings": [
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
            for finding_id, fields in findings
        ],
        "handoffs": [{"handoff_id": handoff_id, **record} for handoff_id, record in handoffs],
        "limitations": list(limitations),
        "mode": "independent-review",
        "node_id": node_id,
        "record_type": "review",
        "requirement_ids": list(evidence.requirement_ids),
        "selection_reason": expectation.selection_reason,
        "skill_id": "repository-independent-review",
        "status": status,
        "validation_requirements": [],
    }
    return content, {
        "artifact_digest": evidence.raw_result_digest,
        "evidence": asdict(evidence),
        "expectation": asdict(expectation),
        "native_input_digest": _sha256_bytes(native_content),
        "normalized_record": normalized,
    }


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
    allowed_artifacts = tuple(
        ValidationArtifact(
            path=_required_text(item, "path"),
            kind=_required_text(item, "kind"),
            repository_status=_required_text(item, "repository_status"),
            status_source=_required_text(item, "status_source"),
            artifact_id=item.get("artifact_id"),
            artifact_digest=item.get("artifact_digest"),
            status_rule=item.get("status_rule"),
        )
        for item in _records(raw, "allowed_artifacts")
    )
    raw_plans = raw.get("requirement_plans", [])
    if not isinstance(raw_plans, list) or any(not isinstance(plan, list) or len(plan) != 7 for plan in raw_plans):
        msg = "validation_unit.requirement_plans must contain seven-field arrays"
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
    return FingerprintEvidence(expected=_state(raw, "expected"), before=_state(raw, "before"), after=_state(raw, "after"))


def _review_expectation(raw: dict[str, Any]) -> ReviewEvidenceExpectation:
    expected_after = tuple(raw["expected_after_state"]) if raw.get("expected_after_state") is not None else None
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
    )


def _review_evidence(raw: dict[str, Any]) -> ReviewEvidence:
    fingerprints = raw.get("fingerprints")
    if not isinstance(fingerprints, dict):
        msg = "review evidence fingerprints must be an object"
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
        )
    )


def _validation_artifacts_body(payload: dict[str, Any], unit: ValidationUnit) -> tuple[str, tuple[ValidationArtifact, ...]]:
    raw_artifacts = _records(payload, "artifacts")
    if len(raw_artifacts) != len(unit.allowed_artifacts):
        msg = "validation artifacts must match the dispatched allowed artifacts"
        raise ValueError(msg)
    artifacts: list[ValidationArtifact] = []
    bodies: list[str] = []
    for raw, approved in zip(raw_artifacts, unit.allowed_artifacts, strict=True):
        path = _required_text(raw, "path")
        kind = _required_text(raw, "kind")
        repository_status = _required_text(raw, "repository_status")
        artifact_id = raw.get("artifact_id")
        artifact_digest = _required_text(raw, "artifact_digest")
        if (path, kind, repository_status) != (approved.path, approved.kind, approved.repository_status):
            msg = f"validation artifact {path} does not match its dispatch"
            raise ValueError(msg)
        if approved.artifact_id is not None and artifact_id != approved.artifact_id:
            msg = f"validation artifact {path} changed its approved artifact ID"
            raise ValueError(msg)
        if approved.artifact_digest is not None and artifact_digest != approved.artifact_digest:
            msg = f"validation artifact {path} changed its approved digest"
            raise ValueError(msg)
        artifact = ValidationArtifact(
            path=path,
            kind=kind,
            repository_status=repository_status,
            artifact_id=artifact_id,
            artifact_digest=artifact_digest,
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
    results: list[str] = []
    bodies: list[str] = []
    for ordinal, raw in enumerate(raw_executions, start=1):
        result = _required_text(raw, "result")
        if result not in {"passed", "failed", "blocked", "not-run"}:
            msg = f"validation execution {ordinal} has invalid result {result}"
            raise ValueError(msg)
        result_artifacts = _text_list(raw, "artifact_paths")
        unknown_artifacts = sorted(set(result_artifacts) - set(artifact_by_path))
        if unknown_artifacts:
            msg = f"validation execution {ordinal} references unknown artifacts: {', '.join(unknown_artifacts)}"
            raise ValueError(msg)
        artifact_references = (
            json.dumps(
                [
                    {"artifact_digest": artifact_by_path[path].artifact_digest, "artifact_id": artifact_by_path[path].artifact_id, "path": path}
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
                    f"  - Command: {_required_text(raw, 'command')}",
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


def _validation_normalized_record(payload: dict[str, Any], evidence: ValidationEvidence) -> dict[str, Any]:
    return {
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
        "payload_digest": _sha256_bytes(_canonical_json(payload).encode()),
        "record_type": "validation",
        "requirement_ids": list(evidence.requirement_ids),
        "skill_id": "review-validator",
        "status": evidence.status,
        "validation": [
            {"evidence_id": evidence.evidence_id, "requirement_id": requirement_id, "status": evidence.status} for requirement_id in evidence.requirement_ids
        ],
    }


def _workspace_snapshot(dispatch: dict[str, Any], name: str) -> dict[str, tuple[str, str]]:
    records = _records(dispatch, name)
    snapshot: dict[str, tuple[str, str]] = {}
    for ordinal, raw in enumerate(records, start=1):
        path = _required_text(raw, "path")
        digest = _required_text(raw, "digest")
        status = _required_text(raw, "status")
        if path in snapshot:
            msg = f"{name} contains duplicate path {path}"
            raise ValueError(msg)
        if status not in {"ignored", "outside-repository", "tracked", "untracked"}:
            msg = f"{name} record {ordinal} has invalid status {status}"
            raise ValueError(msg)
        _sha256_digest(digest, f"{name} digest")
        snapshot[path] = (status, digest)
    return snapshot


def _path_allowed(path: str, allowed: tuple[str, ...]) -> bool:
    return any(path == candidate or path.startswith(candidate.rstrip("/") + "/") for candidate in allowed)


def _validation_workspace_audit(dispatch: dict[str, Any], unit: ValidationUnit) -> dict[str, object]:
    required = bool(unit.allowed_artifacts or unit.expected_workspace_effects or unit.requires_isolation)
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
    unsafe = tuple(path for path in changed if after.get(path, before.get(path, ("", "")))[0] not in {"ignored", "outside-repository"})
    if unexpected:
        msg = "validation produced unexpected workspace paths: " + ", ".join(unexpected)
        raise ValueError(msg)
    if unsafe:
        msg = "validation changed tracked or nonignored repository paths: " + ", ".join(unsafe)
        raise ValueError(msg)
    if unit.requires_isolation:
        repository_root = Path(_required_text(dispatch, "repository_root")).resolve()
        inside = tuple(directory for directory in unit.working_directories if Path(directory).resolve(strict=False).is_relative_to(repository_root))
        if inside:
            msg = "source-mutating validation requires working directories outside the captured repository: " + ", ".join(inside)
            raise ValueError(msg)
    return {"changed_paths": list(changed), "observed": True, "unexpected_paths": []}


def compile_validation(document: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:  # noqa: PLR0915
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
    fingerprints = FingerprintEvidence(expected=expected, before=_state(dispatch, "before_state"), after=_state(dispatch, "after_state"))
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
    artifacts_body, artifacts = _validation_artifacts_body(payload, unit)
    workspace_audit = _validation_workspace_audit(dispatch, unit)
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
    canonical_payload = _canonical_json(payload)
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
                f"- Worker payload digest: {_sha256_bytes(canonical_payload.encode())}",
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
        f"{NATIVE_EVIDENCE_BLOCK_OPEN}{_canonical_json(machine_payload)}{NATIVE_EVIDENCE_BLOCK_CLOSE}\n"
    ).encode()
    evidence = replace(evidence, raw_result_digest=_sha256_bytes(content))
    envelope_assessment = assess_validation_evidence(expectation, evidence)
    native_blockers = _validation_native_result_blockers(content, expectation, evidence)
    blockers = (*envelope_assessment.blockers, *native_blockers)
    if blockers:
        msg = "compiled validation artifact failed verification: " + "; ".join(blockers)
        raise ValueError(msg)
    return content, {
        "expectation": asdict(expectation),
        "evidence": asdict(evidence),
        "payload_digest": _sha256_bytes(canonical_payload.encode()),
        "artifact_digest": evidence.raw_result_digest,
        "normalized_record": _validation_normalized_record(payload, evidence),
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
    return GraphPlan(
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
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        msg = f"JSON root must be an object: {path}"
        raise TypeError(msg)
    return value


def _canonical_worker_payload(content: bytes) -> dict[str, Any]:
    prefix = b"- Canonical worker payload: "
    matches = [line.removeprefix(prefix) for line in content.splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        msg = "compiled artifact must contain exactly one canonical worker payload"
        raise ValueError(msg)
    payload = json.loads(matches[0])
    if not isinstance(payload, dict):
        msg = "canonical worker payload must be an object"
        raise TypeError(msg)
    return payload


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
    artifact_digest = _sha256_bytes(content)
    if metadata.get("artifact_digest") != artifact_digest or evidence_raw.get("raw_result_digest") != artifact_digest:
        msg = f"artifact digest does not match evidence metadata: {artifact_path}"
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
                payload = _canonical_worker_payload(content)
                payload_digest = _sha256_bytes(_canonical_json(payload).encode())
                if metadata.get("payload_digest") != payload_digest:
                    msg = f"worker payload digest does not match compiled artifact: {artifact_path}"
                    raise ValueError(msg)
                recomputed = _review_normalized_record(payload, expectation, evidence)
        else:
            if not isinstance(expectation, ValidationEvidenceExpectation) or not isinstance(evidence, ValidationEvidence):
                msg = f"validation metadata has mismatched typed evidence: {metadata_path}"
                raise TypeError(msg)
            payload = _canonical_worker_payload(content)
            payload_digest = _sha256_bytes(_canonical_json(payload).encode())
            if metadata.get("payload_digest") != payload_digest:
                msg = f"worker payload digest does not match compiled artifact: {artifact_path}"
                raise ValueError(msg)
            recomputed = _validation_normalized_record(payload, evidence)
        if normalized != recomputed:
            msg = f"normalized record does not match compiled artifact: {metadata_path}"
            raise ValueError(msg)
    if require_normalized and normalized is None:
        msg = f"synthesis requires compiler-derived normalized metadata: {metadata_path}"
        raise ValueError(msg)
    return kind, expectation, evidence, content, normalized


def build_synthesis_bundle(document: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, hashed synthesis view from accepted compiler artifacts."""
    source_state = _state(document, "source_state")
    raw_sources = _records(document, "sources")
    if not raw_sources:
        msg = "synthesis requires compiler evidence sources"
        raise ValueError(msg)
    derived: list[dict[str, Any]] = []
    for source in raw_sources:
        _kind, expectation, evidence, _content, normalized = _load_evidence_source(source, require_normalized=True)
        if expectation.source_state != source_state or evidence.fingerprints.expected != source_state:
            msg = f"synthesis evidence has a different source state: {evidence.evidence_id}"
            raise ValueError(msg)
        if normalized is None:  # Defensive for type narrowing after require_normalized.
            msg = f"synthesis evidence has no normalized record: {evidence.evidence_id}"
            raise ValueError(msg)
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
        record["record_digest"] = _sha256_bytes(_canonical_json(record).encode())
        records.append(record)
    bundle: dict[str, Any] = {"schema_version": 1, "source_state": list(source_state), "records": sorted(records, key=lambda item: item["evidence_id"])}
    bundle["bundle_digest"] = _sha256_bytes(_canonical_json(bundle).encode())
    return bundle


def build_routing_projection_document(
    document: dict[str, Any], *, catalog_path: Path = DEFAULT_ROUTING_CATALOG, skill_roots: tuple[Path, ...] = (DEFAULT_SKILL_ROOT,)
) -> dict[str, Any]:
    """Load and project the complete consulted routing catalog."""
    catalog = load_routing_catalog(catalog_path, skill_roots=skill_roots)
    return build_routing_projection(
        catalog, consulted_routers=_text_list(document, "consulted_routers", required=True), captured_paths=_text_list(document, "captured_paths")
    )


def _schema_reference(path: Path) -> dict[str, object]:
    raw = _read_json_object(path)
    required = raw.get("required")
    if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
        msg = f"payload schema has no canonical required field list: {path}"
        raise ValueError(msg)
    return {"digest": _file_identity_digest(str(path)), "id": _required_text(raw, "$id"), "path": str(path), "required_fields": required, "version": 1}


def _applicable_instruction_paths(repository_root: Path, owned_paths: tuple[str, ...], declared: tuple[str, ...]) -> tuple[str, ...]:
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
            parent = parent.parent
    return tuple(sorted(str(path) for path in candidates))


def _materialized_command_policy(plan: GraphPlan, node: WorkerNode, authorized_duplicates: tuple[str, ...]) -> dict[str, object]:
    validator_commands = tuple(sorted({command for unit in plan.coalesced_validation_units for command in unit.commands}))
    if node.mode == "validation":
        unit = next(unit for unit in plan.coalesced_validation_units if unit.node_id == node.node_id)
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
        "policy": "planned validators own execution; return validation requirements without rerunning their commands",
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
            groups.setdefault(node.coverage, []).append(node.node_id)
    output: dict[str, dict[str, object]] = {}
    for paths, node_ids in groups.items():
        if len(node_ids) < 2:
            continue
        observations: list[dict[str, object]] = []
        for path in paths:
            candidate = (repository_root / path).resolve()
            if not candidate.is_relative_to(repository_root) or not candidate.is_file():
                observations = []
                break
            content = candidate.read_bytes()
            observations.append(
                {
                    "byte_count": len(content),
                    "content_digest": _sha256_bytes(content),
                    "line_count": content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0),
                    "path": path,
                }
            )
        if not observations:
            continue
        observation_digest = _sha256_bytes(_canonical_json(observations).encode())
        identity = _sha256_bytes(_canonical_json({"observation_digest": observation_digest, "source_state": source_state}).encode())
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
        }
        for node_id in node_ids:
            output[node_id] = record
    return output


def _worker_prompt(contract: str, dispatch: dict[str, Any]) -> str:
    schema = dispatch.get("payload_schema")
    schema_text = _canonical_json(schema) if isinstance(schema, dict) else "native independent-review Markdown contract"
    command_policy = _canonical_json(dispatch.get("command_policy", {}))
    if contract == "native-independent-review":
        return (
            "Perform only the dispatched repository-independent-review in fresh context. Return the six canonical native sections "
            "Scope Inspected, Findings, No-Finding Evidence, Routing Handoffs, Fingerprint Proof, and Git State; do not append graph IDs, "
            "an envelope, or Machine Evidence because compile-independent-review owns those identities. "
            f"Command policy: {command_policy}"
        )
    return (
        f"Return only the canonical {contract} payload using field names from {schema_text}. "
        "Do not author fingerprints, evidence IDs, artifact IDs, or digests. "
        f"Command policy: {command_policy}"
    )


def materialize_dispatches(document: dict[str, Any]) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    """Derive exact per-node dispatch bases from one accepted graph plan."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "materialize-dispatches requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    if not plan.dispatch_allowed:
        msg = "cannot materialize dispatches from a blocked graph plan"
        raise ValueError(msg)
    source_state = _state(document, "source_state")
    repository_root_path = Path(_required_text(document, "repository_root"))
    if not repository_root_path.is_absolute() or not repository_root_path.is_dir():
        msg = "repository_root must be an existing absolute directory"
        raise ValueError(msg)
    repository_root = str(repository_root_path.resolve())
    authorization = _required_text(document, "authorization")
    if authorization not in {"review-only", "review-and-fix"}:
        msg = "authorization must be review-only or review-and-fix"
        raise ValueError(msg)
    if authorization != "review-and-fix" and any(node.mode == "fix" for node in plan.actual_worker_nodes):
        msg = "fix nodes require review-and-fix authorization"
        raise ValueError(msg)
    state_command = _required_text(document, "state_verification_command")
    artifact_store = Path(_required_text(document, "artifact_store")).resolve()
    review_schema = _schema_reference(_REVIEW_PAYLOAD_SCHEMA)
    validation_schema = _schema_reference(_VALIDATION_PAYLOAD_SCHEMA)
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
    validation_units = {unit.node_id: unit for unit in plan.coalesced_validation_units}
    evidence_ids = {node.node_id: f"{'validation' if node.mode == 'validation' else 'review'}:{node.node_id}" for node in plan.actual_worker_nodes}
    line_bounds = dict(plan.captured_path_line_bounds)
    inspection_groups = _inspection_groups(plan, source_state, artifact_store, repository_root_path.resolve())
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
    dispatches: list[dict[str, Any]] = []
    for node in plan.actual_worker_nodes:
        compiler_operation = _COMPILER_BY_MODE.get(node.mode)
        if compiler_operation is None:
            msg = f"no deterministic compiler is registered for planned node mode {node.mode}: {node.node_id}"
            raise ValueError(msg)
        location = locations.get(node.node_id, "coordinator" if node.mode == "fix" else "worker")
        artifact_suffix = "validation.md" if node.mode == "validation" else "review.md"
        artifact_path = artifact_store / f"{node.node_id}.{artifact_suffix}"
        metadata_path = artifact_store / f"{node.node_id}.evidence.json"
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
            "artifact_id": f"artifact://{node.node_id}",
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
            "node_id": node.node_id,
            "owned_paths": list(node.coverage),
            "reference_paths": list(node.static_references),
            "repository_root": repository_root,
            "requirement_ids": list(node.requirement_ids),
            "skill_id": node.skill_id,
            "skill_path": node.skill_path,
            "source_state": list(source_state),
            "state_verification_command": state_command,
            "worker_created": location == "worker",
        }
        if node.node_id in inspection_groups:
            common["shared_inspection_evidence"] = inspection_groups[node.node_id]
        if node.mode == "validation":
            unit = validation_units.get(node.node_id)
            if unit is None:
                msg = f"validation node has no coalesced unit: {node.node_id}"
                raise ValueError(msg)
            if unit.source_state != source_state:
                msg = f"validation unit source state differs from dispatch state: {node.node_id}"
                raise ValueError(msg)
            common["validation_unit"] = json.loads(_canonical_json(asdict(unit)))
            common["payload_schema"] = validation_schema
            common["workspace_policy"] = {
                "allowed_artifacts": [asdict(artifact) for artifact in unit.allowed_artifacts],
                "expected_workspace_effects": list(unit.expected_workspace_effects),
                "requires_isolation": unit.requires_isolation,
                "snapshots_required": bool(unit.allowed_artifacts or unit.expected_workspace_effects or unit.requires_isolation),
            }
            contract = "compact-validation"
        else:
            common.update(
                {
                    "mode": node.mode,
                    "predecessor_evidence_ids": [evidence_ids[predecessor] for predecessor in node.predecessors],
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
                contract = "native-independent-review"
            else:
                common["payload_schema"] = review_schema
                contract = "compact-review"
        dispatches.append(
            {
                "artifact_path": str(artifact_path),
                "compiler_operation": compiler_operation,
                "dispatch": common,
                "journal_operation": "journal-append",
                "metadata_path": str(metadata_path),
                "node_id": node.node_id,
                "result_contract": contract,
                "worker_prompt": _worker_prompt(contract, common),
            }
        )
    output: dict[str, Any] = {"dispatches": dispatches, "plan_digest": _plan_digest(plan), "schema_version": 1, "source_state": list(source_state)}
    output["dispatch_set_digest"] = _sha256_bytes(_canonical_json(output).encode())
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
        actual_worker_nodes=nodes,
        coalesced_validation_units=units,
        current_epoch_node_ids=tuple(node_ids[node_id] for node_id in plan.current_epoch_node_ids),
        execution_epochs=tuple(replace(item, node_ids=tuple(node_ids[node_id] for node_id in item.node_ids)) for item in plan.execution_epochs),
        requirement_to_node=tuple((requirement_id, node_ids[node_id]) for requirement_id, node_id in plan.requirement_to_node),
        selected_validation_units=tuple(node_ids[node_id] for node_id in plan.selected_validation_units),
        synthesis_nodes=tuple(node_ids[node_id] for node_id in plan.synthesis_nodes),
        validation_evidence_mapping=tuple(
            replace(mapping, validation_unit_id=node_ids[mapping.validation_unit_id]) for mapping in plan.validation_evidence_mapping
        ),
    )


def advance_after_mutation(document: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0915
    """Close one repair epoch, recapture once, and emit a fresh final-state graph."""
    raw_plan = document.get("plan")
    new_capture = document.get("new_capture")
    planning_template = document.get("planning_template")
    if not isinstance(raw_plan, dict) or not isinstance(new_capture, dict) or not isinstance(planning_template, dict):
        msg = "advance-after-mutation requires plan, new_capture, and planning_template objects"
        raise TypeError(msg)
    old_plan = _graph_plan(raw_plan)
    old_source_state = _state(document, "source_state")
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
    changed_paths = _text_list(document, "changed_paths", required=True)
    captured_paths = new_capture.get("captured_scope_paths")
    if not isinstance(captured_paths, list) or any(not isinstance(path, str) for path in captured_paths):
        msg = "new_capture captured_scope_paths must be a string array"
        raise ValueError(msg)
    missing_changed = tuple(sorted(set(changed_paths) - set(captured_paths)))
    if missing_changed:
        msg = "changed paths are absent from the new capture: " + ", ".join(missing_changed)
        raise ValueError(msg)
    planning_input = bootstrap_document(new_capture, planning_template)
    planning_input["authorization"] = authorization_after
    require_schema(planning_input, _PLANNING_INPUT_SCHEMA)
    repository_root = Path(_required_text(planning_input, "repository_root")).resolve()
    catalog_path = Path(document.get("routing_catalog_path", DEFAULT_ROUTING_CATALOG)).resolve()
    new_plan = plan_from_document(planning_input, catalog_path=catalog_path, skill_roots=(DEFAULT_SKILL_ROOT,), repository_root=repository_root)
    if not new_plan.dispatch_allowed:
        msg = "recaptured repair epoch produced a blocked final-state plan: " + "; ".join(new_plan.blockers)
        raise ValueError(msg)
    new_plan = _epoch_scoped_plan(new_plan, epoch)
    artifact_store = Path(_required_text(document, "artifact_store")).resolve() / f"repair-epoch-{epoch:03d}"
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(artifact_store),
            "authorization": authorization_after,
            "plan": json.loads(_canonical_json(asdict(new_plan))),
            "repository_root": str(repository_root),
            "routing_catalog_path": str(catalog_path),
            "source_state": list(new_state),
            "state_verification_command": _required_text(document, "state_verification_command"),
        }
    )
    old_paths = {path for node in old_plan.actual_worker_nodes for path in node.coverage}
    newly_touched_paths = tuple(sorted(set(captured_paths) - old_paths))
    old_nodes = tuple(node.node_id for node in old_plan.actual_worker_nodes)
    replacement_lineage: list[dict[str, object]] = []
    for node in new_plan.actual_worker_nodes:
        predecessors = tuple(
            old.node_id
            for old in old_plan.actual_worker_nodes
            if old.skill_id == node.skill_id and old.mode == node.mode and bool(set(old.coverage) & set(node.coverage))
        )
        replacement_lineage.append({"node_id": node.node_id, "replaces_node_ids": list(predecessors)})
    fix_node_id = f"fix-epoch-{epoch:03d}"
    return {
        "authorization_transition": {"after": authorization_after, "before": authorization_before},
        "dispatch_set": dispatch_set,
        "invalidated_nodes": [{"node_id": node_id, "state": "awaiting-replan"} for node_id in old_nodes],
        "new_plan": asdict(new_plan),
        "new_source_state": list(new_state),
        "newly_touched_paths": list(newly_touched_paths),
        "old_source_state": list(old_source_state),
        "repair_epoch": {
            "changed_paths": list(changed_paths),
            "fix_nodes": [{"mode": "fix", "node_id": fix_node_id, "serialized": True}],
            "ordinal": epoch,
            "recapture_count": 1,
        },
        "replacement_lineage": replacement_lineage,
        "schema_version": 1,
        "stale_evidence_ids": [_expected_evidence_id(node) for node in old_plan.actual_worker_nodes],
        "status": "advanced",
    }


def _plan_digest(plan: GraphPlan) -> str:
    return _sha256_bytes(_canonical_json(asdict(plan)).encode())


def _expected_evidence_id(node: WorkerNode) -> str:
    return f"{'validation' if node.mode == 'validation' else 'review'}:{node.node_id}"


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


def _journal_evidence(raw: object, *, node: WorkerNode, status: str) -> dict[str, str] | None:
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
    expected_evidence_id = _expected_evidence_id(node)
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
    if kind != expected_kind or evidence.node_id != node.node_id or evidence.evidence_id != _expected_evidence_id(node):
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
        expected_predecessors = tuple(_expected_evidence_id(by_id[predecessor_id]) for predecessor_id in node.predecessors)
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
    limitations = tuple(cast("list[str]", normalized.get("limitations", [])))
    record = {
        "artifact_digest": evidence.raw_result_digest,
        "artifact_id": evidence.raw_result_artifact_id,
        "evidence_id": evidence.evidence_id,
        "evidence_status": evidence.status,
        "normalized_record_digest": _sha256_bytes(_canonical_json(normalized).encode()),
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
    if set(event) != _JOURNAL_EVENT_KEYS:
        msg = f"journal event {expected_sequence} has unexpected fields"
        raise ValueError(msg)
    if _required_int(event, "schema_version") != 1 or _required_int(event, "sequence") != expected_sequence:
        msg = f"journal event sequence is invalid at record {expected_sequence}"
        raise ValueError(msg)
    if _required_text(event, "plan_digest") != _plan_digest(plan) or _state(event, "source_state") != source_state:
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
    _journal_evidence(event.get("evidence"), node=node, status=status)
    return node_id, status


def _fold_execution_journal(plan: GraphPlan, source_state: tuple[str, str, str], events: tuple[dict[str, Any], ...]) -> tuple[dict[str, str], str | None]:
    state: dict[str, str] = {}
    previous_digest: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        node_id, status = _validated_journal_record(
            event, expected_sequence=expected_sequence, plan=plan, source_state=source_state, previous_digest=previous_digest
        )
        affected = _apply_journal_transition(plan, state, node_id=node_id, status=status)
        if _text_list(event, "affected_node_ids") != affected:
            msg = f"journal event {expected_sequence} has incorrect affected nodes"
            raise ValueError(msg)
        event_digest = _sha256_digest(event.get("event_digest"), "event_digest")
        unsigned = dict(event)
        unsigned.pop("event_digest")
        if event_digest != _sha256_bytes(_canonical_json(unsigned).encode()):
            msg = f"journal event {expected_sequence} digest does not match its content"
            raise ValueError(msg)
        previous_digest = event_digest
    return state, previous_digest


def read_execution_journal(path: Path, *, plan: GraphPlan, source_state: tuple[str, str, str]) -> tuple[tuple[dict[str, Any], ...], dict[str, str], str | None]:
    """Read, validate, and fold a canonical append-only execution journal."""
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        content = b""
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


def _persist_journal_event(path: Path, event: dict[str, Any], *, existing_size: int) -> None:
    if not path.parent.is_dir():
        msg = f"execution journal parent directory does not exist: {path.parent}"
        raise ValueError(msg)
    encoded = (_canonical_json(event) + "\n").encode()
    with path.open("ab") as stream:
        if stream.tell() != existing_size:
            msg = f"execution journal changed during append: {path}"
            raise ValueError(msg)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def append_journal_event(path: Path, document: dict[str, Any], request: JournalEventRequest) -> dict[str, Any]:
    """Append one graph-validated lifecycle event and return its canonical record."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "journal-append requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    existing_size = path.stat().st_size if path.exists() else 0
    events, state, head_digest = read_execution_journal(path, plan=plan, source_state=source_state)
    node = next((candidate for candidate in plan.actual_worker_nodes if candidate.node_id == request.node_id), None)
    if node is None:
        msg = f"journal event references unknown node: {request.node_id}"
        raise ValueError(msg)
    if request.status not in _JOURNAL_STATUSES:
        msg = f"invalid journal status {request.status}"
        raise ValueError(msg)
    evidence, limitations = _new_journal_evidence(request, plan=plan, node=node, source_state=source_state)
    affected = _apply_journal_transition(plan, state, node_id=request.node_id, status=request.status)
    event: dict[str, Any] = {
        "affected_node_ids": list(affected),
        "evidence": evidence,
        "node_id": request.node_id,
        "plan_digest": _plan_digest(plan),
        "previous_event_digest": head_digest,
        "reason": _new_journal_reason(request, limitations),
        "schema_version": 1,
        "sequence": len(events) + 1,
        "source_state": list(source_state),
        "status": request.status,
    }
    event["event_digest"] = _sha256_bytes(_canonical_json(event).encode())
    _persist_journal_event(path, event, existing_size=existing_size)
    return event


def _dispatches_by_node(dispatch_set: dict[str, Any], *, plan: GraphPlan, source_state: tuple[str, str, str]) -> dict[str, dict[str, Any]]:
    if _required_int(dispatch_set, "schema_version") != 1:
        msg = "dispatch set has an unsupported schema version"
        raise ValueError(msg)
    if _required_text(dispatch_set, "plan_digest") != _plan_digest(plan) or _state(dispatch_set, "source_state") != source_state:
        msg = "dispatch set belongs to a different plan or source state"
        raise ValueError(msg)
    expected_digest = _required_text(dispatch_set, "dispatch_set_digest")
    unsigned = dict(dispatch_set)
    unsigned.pop("dispatch_set_digest")
    if expected_digest != _sha256_bytes(_canonical_json(unsigned).encode()):
        msg = "dispatch set digest does not match its content"
        raise ValueError(msg)
    entries: dict[str, dict[str, Any]] = {}
    for entry in _records(dispatch_set, "dispatches"):
        node_id = _required_text(entry, "node_id")
        dispatch = entry.get("dispatch")
        if node_id in entries or not isinstance(dispatch, dict) or dispatch.get("node_id") != node_id:
            msg = f"dispatch set has an invalid or duplicate node entry: {node_id}"
            raise ValueError(msg)
        entries[node_id] = entry
    expected_node_ids = {node.node_id for node in plan.actual_worker_nodes}
    if set(entries) != expected_node_ids:
        msg = "dispatch set does not contain exactly the planned nodes"
        raise ValueError(msg)
    return entries


def next_ready_nodes(document: dict[str, Any], *, journal_events: tuple[dict[str, Any], ...], dispatch_set: dict[str, Any]) -> dict[str, Any]:
    """Return only dependency-ready dispatches from a verified execution journal."""
    raw_plan = document.get("plan")
    if not isinstance(raw_plan, dict):
        msg = "next-ready requires a plan object"
        raise TypeError(msg)
    plan = _graph_plan(raw_plan)
    source_state = _state(document, "source_state")
    current_source_state = _state(document, "current_source_state")
    if current_source_state != source_state:
        msg = "next-ready current recapture differs from the plan-bound source state"
        raise ValueError(msg)
    state, head_digest = _fold_execution_journal(plan, source_state, journal_events)
    dispatches = _dispatches_by_node(dispatch_set, plan=plan, source_state=source_state)
    accepted = {node_id for node_id, lifecycle in state.items() if lifecycle == "accepted"}
    blocked = {node_id for node_id, lifecycle in state.items() if lifecycle == "blocked"}
    invalidated = {node_id for node_id, lifecycle in state.items() if lifecycle == "invalidated"}
    awaiting_replan = {node_id for node_id, lifecycle in state.items() if lifecycle == "awaiting-replan"}
    in_flight = {node_id for node_id, lifecycle in state.items() if lifecycle == "in-flight"}
    blockers = ["blocked nodes prevent completion: " + ", ".join(sorted(blocked))] if blocked else []
    if awaiting_replan:
        blockers.append("source mutation requires a fresh plan: " + ", ".join(sorted(awaiting_replan)))
    ready: list[str] = []
    waiting: list[dict[str, Any]] = []
    for node in plan.actual_worker_nodes:
        if node.node_id in accepted | awaiting_replan | blocked | in_flight:
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
        "schema_version": 1,
        "waiting": waiting,
    }


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
    for source in _records(document, "sources"):
        kind, expectation, evidence, _content, record = _load_evidence_source(source, require_normalized=True)
        if kind != "review" or not isinstance(expectation, ReviewEvidenceExpectation) or not isinstance(evidence, ReviewEvidence):
            continue
        if expectation.source_state != source_state or not assess_review_evidence(expectation, evidence).satisfies_requirements:
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
    source_state = _state(document, "source_state")
    current_source_state = _state(document, "current_source_state")
    if current_source_state != source_state:
        msg = "finalize-proof current recapture differs from the plan-bound source state"
        raise ValueError(msg)
    expectation = repository_review_proof_expectation(plan, source_state=source_state)
    stale_ids = set(_text_list(document, "stale_evidence_ids"))
    sources = _records(document, "sources")
    if not sources:
        msg = "finalize-proof requires persisted evidence sources"
        raise ValueError(msg)

    loaded: dict[
        str, tuple[str, ReviewEvidenceExpectation | ValidationEvidenceExpectation, ReviewEvidence | ValidationEvidence, bytes, dict[str, Any] | None]
    ] = {}
    duplicate_evidence: set[str] = set()
    for source in sources:
        kind, record_expectation, evidence, content, normalized = _load_evidence_source(source)
        if evidence.evidence_id in loaded:
            duplicate_evidence.add(evidence.evidence_id)
        loaded[evidence.evidence_id] = (kind, record_expectation, evidence, content, normalized)
    preblockers: list[str] = []
    if duplicate_evidence:
        preblockers.append("duplicate evidence sources: " + ", ".join(sorted(duplicate_evidence)))

    node_candidates: dict[str, list[str]] = {}
    satisfying_ids: set[str] = set()
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
        if assessment.satisfies_requirements:
            satisfying_ids.add(evidence_id)
            planned_node = planned_by_id.get(evidence.node_id)
            if planned_node is None and evidence_id not in exact_reuse_ids:
                preblockers.append(f"current satisfying evidence maps to an unplanned node: {evidence_id} -> {evidence.node_id}")
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
            preblockers.append(f"multiple current satisfying evidence records map to node {node.node_id}: " + ", ".join(sorted(candidates)))

    reused_mapping = dict(expectation.exact_reused_review_evidence)
    missing_reuse = tuple(sorted(evidence_id for evidence_id in reused_mapping.values() if evidence_id not in satisfying_ids))
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
                *(evidence_id for _requirement_id, evidence_id in expectation.exact_reused_review_evidence if evidence_id in satisfying_ids),
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
    preblockers.extend(handoff_blockers)

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
    elif len(accepted_validation_ids) != len(validation_node_ids):
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
    return {
        "artifact_manifest": asdict(manifest),
        "blockers": list(blockers),
        "graph_proof_status": graph_proof_status,
        "handoff_reconciliation": handoff_reconciliation,
        "independent_review_metrics": {
            "accepted_evidence_count": len(accepted_independent),
            "semantic_agreement": "not-inferred-from-structural-acceptance",
            "specialist_recall": "requires-independent-adjudication",
            "structurally_accepted_evidence_ids": list(accepted_independent),
        },
        "proof": asdict(proof),
        "repository_validation_status": repository_validation_status,
        "schema_version": 1,
        "status": graph_proof_status,
        "summary": {
            "accepted_review_evidence": len(accepted_review_ids),
            "accepted_validation_evidence": len(accepted_validation_ids),
            "planned_nodes": len(plan.actual_worker_nodes),
            "unresolved_handoffs": len(unresolved_handoff_ids),
        },
    }


def _argument_parser() -> argparse.ArgumentParser:  # noqa: PLR0915
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    compile_parser = subparsers.add_parser("compile-review", help="compile a compact review payload")
    compile_parser.add_argument("--input", type=Path, required=True)
    compile_parser.add_argument("--artifact", type=Path, required=True)
    compile_parser.add_argument("--metadata", type=Path, required=True)
    independent_parser = subparsers.add_parser("compile-independent-review", help="compile a native independent review")
    independent_parser.add_argument("--input", type=Path, required=True)
    independent_parser.add_argument("--native-artifact", type=Path, required=True)
    independent_parser.add_argument("--artifact", type=Path, required=True)
    independent_parser.add_argument("--metadata", type=Path, required=True)
    validation_parser = subparsers.add_parser("compile-validation", help="compile a compact validation payload")
    validation_parser.add_argument("--input", type=Path, required=True)
    validation_parser.add_argument("--artifact", type=Path, required=True)
    validation_parser.add_argument("--metadata", type=Path, required=True)
    synthesis_parser = subparsers.add_parser("synthesis-bundle", help="build a compact synthesis bundle")
    synthesis_parser.add_argument("--input", type=Path, required=True)
    synthesis_parser.add_argument("--output", type=Path, required=True)
    routing_parser = subparsers.add_parser("routing-projection", help="project the complete consulted routing catalog")
    routing_parser.add_argument("--input", type=Path, required=True)
    routing_parser.add_argument("--output", type=Path, required=True)
    routing_parser.add_argument("--catalog", type=Path, default=DEFAULT_ROUTING_CATALOG)
    routing_parser.add_argument("--skill-root", type=Path, action="append")
    dispatch_parser = subparsers.add_parser("materialize-dispatches", help="derive exact dispatch bases from a graph plan")
    dispatch_parser.add_argument("--input", type=Path, required=True)
    dispatch_parser.add_argument("--output", type=Path, required=True)
    mutation_parser = subparsers.add_parser("advance-after-mutation", help="recapture and replan one serialized repair epoch")
    mutation_parser.add_argument("--input", type=Path, required=True)
    mutation_parser.add_argument("--output", type=Path, required=True)
    handoff_parser = subparsers.add_parser("reconcile-handoffs", help="resolve covered handoffs and return new routing triggers")
    handoff_parser.add_argument("--input", type=Path, required=True)
    handoff_parser.add_argument("--output", type=Path, required=True)
    journal_parser = subparsers.add_parser("journal-append", help="append one verified graph lifecycle event")
    journal_parser.add_argument("--input", type=Path, required=True)
    journal_parser.add_argument("--journal", type=Path, required=True)
    journal_parser.add_argument("--node-id", required=True)
    journal_parser.add_argument("--status", choices=sorted(_JOURNAL_STATUSES), required=True)
    journal_parser.add_argument("--artifact", type=Path)
    journal_parser.add_argument("--metadata", type=Path)
    journal_parser.add_argument("--kind", choices=("review", "validation"))
    journal_parser.add_argument("--reason")
    ready_parser = subparsers.add_parser("next-ready", help="compute dependency-ready graph nodes")
    ready_parser.add_argument("--dispatches", type=Path, required=True)
    ready_parser.add_argument("--current-capture", type=Path, required=True)
    ready_parser.add_argument("--input", type=Path, required=True)
    ready_parser.add_argument("--journal", type=Path, required=True)
    ready_output = ready_parser.add_mutually_exclusive_group(required=True)
    ready_output.add_argument("--output", type=Path)
    ready_output.add_argument("--output-dir", type=Path, help="runtime-managed immutable next-ready generations")
    final_parser = subparsers.add_parser("finalize-proof", help="derive and verify the repository proof")
    final_parser.add_argument("--current-capture", type=Path, required=True)
    final_parser.add_argument("--input", type=Path, required=True)
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
    return next_ready_nodes(document, journal_events=journal_events, dispatch_set=_read_json_object(args.dispatches))


def _with_current_capture(document: dict[str, Any], capture_path: Path) -> dict[str, Any]:
    capture = _read_json_object(capture_path)
    output = dict(document)
    output["current_source_state"] = [
        capture.get("scope_fingerprint"),
        capture.get("captured_worktree_fingerprint"),
        capture.get("repository_state_fingerprint"),
    ]
    return output


def _json_operation_output(document: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:  # noqa: PLR0911
    if args.operation == "synthesis-bundle":
        return build_synthesis_bundle(document)
    if args.operation == "routing-projection":
        return build_routing_projection_document(document, catalog_path=args.catalog, skill_roots=tuple(args.skill_root or (DEFAULT_SKILL_ROOT,)))
    if args.operation == "materialize-dispatches":
        return materialize_dispatches(document)
    if args.operation == "advance-after-mutation":
        return advance_after_mutation(document)
    if args.operation == "reconcile-handoffs":
        return reconcile_handoffs(document)
    if args.operation == "next-ready":
        return _next_ready_from_files(document, args)
    return finalize_proof(_with_current_capture(document, args.current_capture))


def _run_operation(document: dict[str, Any], args: argparse.Namespace) -> int:
    if args.operation in {"compile-independent-review", "compile-review", "compile-validation"}:
        if args.operation in {"compile-review", "compile-validation"}:
            payload = document.get("payload")
            schema_path = _REVIEW_PAYLOAD_SCHEMA if args.operation == "compile-review" else _VALIDATION_PAYLOAD_SCHEMA
            require_schema(payload, schema_path)
        if args.operation == "compile-review":
            content, metadata = compile_review(document)
        elif args.operation == "compile-validation":
            content, metadata = compile_validation(document)
        else:
            content, metadata = compile_independent_review(document, args.native_artifact.read_bytes())
        _write_bytes_once(args.artifact, content)
        _write_text_once(args.metadata, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        return 0
    if args.operation == "journal-append":
        event = append_journal_event(args.journal, document, _journal_request_from_args(args))
        print(_canonical_json(event))
        return 0
    output = _json_operation_output(document, args)
    output_path = args.output
    if args.operation == "next-ready" and args.output_dir is not None:
        output_directory = args.output_dir.resolve()
        if not output_directory.is_dir():
            msg = f"next-ready output directory does not exist: {output_directory}"
            raise ValueError(msg)
        generation = _required_int(cast("dict[str, Any]", output["journal"]), "event_count")
        output_path = output_directory / f"next-ready.{generation:06d}.json"
        output["output_generation"] = generation
        output["output_path"] = str(output_path)
    _write_text_once(output_path, json.dumps(output, indent=2, sort_keys=True) + "\n")
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
        return _run_operation(document, args)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        if isinstance(error, SchemaValidationError):
            attempt = document.get("handoff_attempt", 1) if isinstance(document, dict) else 1
            retry_allowed = isinstance(attempt, int) and not isinstance(attempt, bool) and attempt == 1
            output = {**error.as_dict(), "handoff_attempt": attempt, "maximum_handoff_attempts": 2, "retry_allowed": retry_allowed}
            print(_canonical_json(output), file=sys.stderr)
        else:
            print(f"review_graph_runtime: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
