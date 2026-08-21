"""Regression tests for deterministic review-graph planning contracts."""

import hashlib
import json
import shutil
from dataclasses import asdict, replace
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import cast

import pytest
from capture_scope import _scope_data
from review_graph_plan import (
    EVIDENCE_SCHEMA_VERSION,
    NATIVE_EVIDENCE_BLOCK_CLOSE,
    NATIVE_EVIDENCE_BLOCK_OPEN,
    ArtifactManifest,
    ArtifactPayload,
    CompletionEvidence,
    CreationFailure,
    ExecutionLedger,
    FingerprintEvidence,
    MigrationTrial,
    NodeAcceptanceEvidence,
    PlanNode,
    RepositoryReviewProof,
    RepositoryReviewProofExpectation,
    ReviewEvidence,
    ReviewEvidenceExpectation,
    ReviewRequirement,
    RoutingDecision,
    RoutingDiscovery,
    RoutingLedgerAssessment,
    TimeBudget,
    TrustedArtifactVerifier,
    ValidationArtifact,
    ValidationEvidence,
    ValidationEvidenceExpectation,
    ValidationRequirement,
    ValidationUnit,
    WorkerBudget,
    WorkerNode,
    _review_native_result_blockers,
    _validation_coalescing_identity,
    _validation_environment_identity,
    _validation_ledger_expected_fields,
    _validation_native_result_blockers,
    _validation_plan_expected_body,
    _validation_requirements_expected_body,
    assess_completion,
    assess_evidence_bundle,
    assess_migration_trials,
    assess_node_acceptance,
    assess_repository_classifier_floor,
    assess_repository_review_proof,
    assess_review_evidence,
    assess_routing_discoveries,
    assess_time_budget,
    assess_validation_evidence,
    assess_worker_capacity,
    bounded_node_dispatch_seconds,
    classify_repository_paths,
    coalesce_review_requirements,
    coalesce_validation_requirements,
    create_artifact_manifest,
    guard_packaged_python_routing,
    independent_nodes_from_routing,
    load_routing_catalog,
    main,
    plan_from_document,
    plan_graph,
    reconcile_execution,
    repository_review_proof_expectation,
    select_execution_profile,
    stop_after_worker_creation_failure,
    validate_routing_ledger,
    validation_command_identity_digest,
    validation_environment_digest,
    validation_evidence_expectation,
)

SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
RUST_FIXTURE_PATH = "agents/.agents/skills/review-graph/scripts/fixtures/state.rs"


@cache
def _rust_fixture_capture_manifest() -> dict[str, object]:
    git = shutil.which("git")
    assert git is not None
    return _scope_data(git, REPOSITORY_ROOT, "branch", None, (RUST_FIXTURE_PATH,))


def _native_markdown(heading: str, sections: tuple[str, ...], payload: dict[str, object], section_bodies: dict[str, str], *, preamble: str = "") -> bytes:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    body = "\n\n".join(f"{section}\n\n{section_bodies[section]}" for section in sections[:-1])
    prefix = f"{heading}\n\n{preamble}\n\n" if preamble else f"{heading}\n\n"
    return f"{prefix}{body}\n\n{sections[-1]}\n\n{NATIVE_EVIDENCE_BLOCK_OPEN}{canonical}{NATIVE_EVIDENCE_BLOCK_CLOSE}\n".encode()


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


def _validation_header(evidence: ValidationEvidence) -> str:
    return "\n".join(
        (
            f"- Node ID: {evidence.node_id}",
            "- Skill: review-validator",
            "- Invocation: graph-dispatched",
            f"- Evidence schema version: {EVIDENCE_SCHEMA_VERSION}",
            f"- Execution profile: {evidence.execution_profile}",
            f"- Execution location: {evidence.execution_location}",
            f"- Status: {evidence.status}",
            f"- Scope fingerprint: {evidence.fingerprints.expected[0]}",
            f"- Worktree fingerprint: {evidence.fingerprints.expected[1]}",
            f"- Repository state fingerprint: {evidence.fingerprints.expected[2]}",
        )
    )


def _fingerprint_proof(fingerprints: FingerprintEvidence) -> str:
    return "\n".join(
        (
            "- Expected:",
            f"  - Scope fingerprint: {fingerprints.expected[0]}",
            f"  - Worktree fingerprint: {fingerprints.expected[1]}",
            f"  - Repository state fingerprint: {fingerprints.expected[2]}",
            "- Before:",
            f"  - Scope fingerprint: {fingerprints.before[0]}",
            f"  - Worktree fingerprint: {fingerprints.before[1]}",
            f"  - Repository state fingerprint: {fingerprints.before[2]}",
            "- After:",
            f"  - Scope fingerprint: {fingerprints.after[0]}",
            f"  - Worktree fingerprint: {fingerprints.after[1]}",
            f"  - Repository state fingerprint: {fingerprints.after[2]}",
        )
    )


def _state_verification(evidence: ReviewEvidence | ValidationEvidence) -> str:
    after_result = "changed-as-reported" if isinstance(evidence, ReviewEvidence) and evidence.source_mutated else "matched"
    if evidence.status == "blocked":
        after_result = "blocked"
    return "\n".join(
        (
            "- Command: capture_scope.py --mode branch",
            "- Before:",
            f"  - Observed scope fingerprint: {evidence.fingerprints.before[0]}",
            f"  - Observed worktree fingerprint: {evidence.fingerprints.before[1]}",
            f"  - Observed repository state fingerprint: {evidence.fingerprints.before[2]}",
            f"  - Result: {'blocked' if evidence.status == 'blocked' else 'matched'}",
            "- After:",
            f"  - Observed scope fingerprint: {evidence.fingerprints.after[0]}",
            f"  - Observed worktree fingerprint: {evidence.fingerprints.after[1]}",
            f"  - Observed repository state fingerprint: {evidence.fingerprints.after[2]}",
            f"  - Result: {after_result}",
        )
    )


def _findings(evidence: ReviewEvidence, *, independent: bool, location: str = "assigned-scope:1") -> str:
    if evidence.status == "no-findings":
        return "No findings." if independent else "none"
    if not evidence.finding_ids:
        return "Blocked: inspection could not complete." if evidence.status == "blocked" else "none"
    records = []
    for finding_id in evidence.finding_ids:
        fields = [
            f"- ID: {finding_id}",
            "  - Severity: P1",
            f"  - Location: {location}",
            "  - Summary: observed contract violation",
            "  - Evidence: observed contract violation",
        ]
        if independent:
            fields.extend(("  - Impact: accepted behavior could be incorrect", "  - Owner: fixture-owner"))
        fields.append("  - Remediation: apply the smallest safe correction")
        records.append("\n".join(fields))
    return "\n".join(records)


def _review_result_payload(expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> bytes:
    independent = evidence.mode == "independent-review"
    changed_paths = expectation.planned_paths if evidence.source_mutated else ()
    sections = (
        (
            "## Scope Inspected",
            "## Findings",
            "## No-Finding Evidence",
            "## Routing Handoffs",
            "## Fingerprint Proof",
            "## Git State",
            "## Review Graph Envelope",
            "## Machine Evidence",
        )
        if independent
        else (
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
    )
    payload: dict[str, object] = {
        "after_repository_state_fingerprint": evidence.fingerprints.after[2],
        "after_scope_fingerprint": evidence.fingerprints.after[0],
        "after_worktree_fingerprint": evidence.fingerprints.after[1],
        "artifact_id": evidence.raw_result_artifact_id,
        "before_repository_state_fingerprint": evidence.fingerprints.before[2],
        "before_scope_fingerprint": evidence.fingerprints.before[0],
        "before_worktree_fingerprint": evidence.fingerprints.before[1],
        "evidence_id": evidence.evidence_id,
        "finding_ids": list(evidence.finding_ids),
        "git_mutated": evidence.git_mutated,
        "mode": evidence.mode,
        "node_id": evidence.node_id,
        "predecessor_evidence_ids": list(expectation.predecessor_evidence_ids),
        "repository_state_fingerprint": evidence.fingerprints.expected[2],
        "requirement_ids": list(evidence.requirement_ids),
        "result_type": "independent-review-result" if independent else "review-node-result",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scope_fingerprint": evidence.fingerprints.expected[0],
        "skill_id": evidence.skill_id,
        "source_mutated": evidence.source_mutated,
        "status": evidence.status,
        "validation_requirement_ids": list(evidence.validation_requirement_ids),
        "worktree_fingerprint": evidence.fingerprints.expected[1],
    }
    if independent:
        planned_paths = ", ".join(expectation.planned_paths)
        payload.update(
            {"change_target": expectation.change_target, "handoff_ids": list(evidence.handoff_ids), "inspected_paths": list(expectation.planned_paths)}
        )
        envelope = "\n".join(
            (
                f"- Node ID: {evidence.node_id}",
                f"- Skill: {evidence.skill_id}",
                f"- Mode: {evidence.mode}",
                f"- Status: {evidence.status}",
                f"- Scope fingerprint: {evidence.fingerprints.expected[0]}",
                f"- Worktree fingerprint: {evidence.fingerprints.expected[1]}",
                f"- Repository state fingerprint: {evidence.fingerprints.expected[2]}",
                f"- Skill file: {expectation.skill_path}",
                f"- Change target: {expectation.change_target}",
                f"- Files inspected: {planned_paths}",
                "- State verification before:",
                f"  - Observed scope fingerprint: {evidence.fingerprints.before[0]}",
                f"  - Observed worktree fingerprint: {evidence.fingerprints.before[1]}",
                f"  - Observed repository state fingerprint: {evidence.fingerprints.before[2]}",
                f"  - Result: {'blocked' if evidence.status == 'blocked' else 'matched'}",
                "- State verification after:",
                f"  - Observed scope fingerprint: {evidence.fingerprints.after[0]}",
                f"  - Observed worktree fingerprint: {evidence.fingerprints.after[1]}",
                f"  - Observed repository state fingerprint: {evidence.fingerprints.after[2]}",
                f"  - Result: {'blocked' if evidence.status == 'blocked' else 'matched'}",
                f"- Source-controlled files changed: {'reported-change' if evidence.source_mutated else 'none'}",
                f"- Git state mutated: {'yes' if evidence.git_mutated else 'no'}",
                "- Limitations: blocked inspection" if evidence.status == "blocked" else "- Limitations: none",
            )
        )
        section_bodies = {
            "## Scope Inspected": f"- Change target: {expectation.change_target}\n- Files: {planned_paths}",
            "## Findings": _findings(evidence, independent=True, location=f"{expectation.planned_paths[0]}:1"),
            "## No-Finding Evidence": "- Inspected: assigned scope and neighboring contracts" if evidence.status == "no-findings" else "none",
            "## Routing Handoffs": "\n".join(f"- Handoff ID: {handoff_id}" for handoff_id in evidence.handoff_ids) or "none",
            "## Fingerprint Proof": _fingerprint_proof(evidence.fingerprints),
            "## Git State": "\n".join(
                (
                    f"- Source-controlled files changed: {'reported-change' if evidence.source_mutated else 'none'}",
                    f"- Git state mutated: {'yes' if evidence.git_mutated else 'no'}",
                )
            ),
            "## Review Graph Envelope": envelope,
        }
    else:
        validation_requirements = (
            "\n".join(
                f"- Requirement ID: {requirement_id}\n  - Owner: {evidence.skill_id}\n  - Disposition: required"
                for requirement_id in evidence.validation_requirement_ids
            )
            or "none"
        )
        section_bodies = {
            "## Skill Loading": "\n".join(
                (
                    f"- Skill file: {expectation.skill_path}",
                    f"- Skill digest: {expectation.skill_digest}",
                    f"- References loaded: {', '.join(path for path, _ in expectation.reference_digests) or 'none'}",
                    f"- Reference digests: {', '.join(f'{path}={digest}' for path, digest in expectation.reference_digests) or 'none'}",
                )
            ),
            "## State Verification": "\n".join(
                (
                    _state_verification(evidence),
                    f"- Changed repository paths: {', '.join(changed_paths) or 'none'}",
                    f"- HEAD, branch, or index mutated: {'yes' if evidence.git_mutated else 'no'}",
                )
            ),
            "## Scope Inspected": "- Files: assigned-scope\n- Nearby contract owners: none",
            "## Findings": _findings(evidence, independent=False),
            "## Validation": "none",
            "## Validation Requirements": validation_requirements,
            "## Predecessor Coverage": (
                "\n".join(f"- Node: predecessor-for-{evidence_id}\n  - Disposition: consumed" for evidence_id in expectation.predecessor_evidence_ids) or "none"
            ),
            "## Changes": (
                "\n".join(
                    (
                        f"- Change ID: {evidence.node_id}-change-1",
                        f"  - Finding IDs: incidental-{evidence.node_id}-1",
                        f"  - Files: {', '.join(changed_paths)}",
                        "  - What changed: corrected the authorized source contract",
                        "  - Why: this is the smallest safe correction",
                        "  - Contract preserved: unrelated behavior and Git state remain unchanged",
                    )
                )
                if evidence.source_mutated
                else "none"
            ),
            "## Handoffs": "\n".join(f"- Handoff ID: {handoff_id}" for handoff_id in evidence.handoff_ids) or "none",
            "## Limitations": "blocked inspection" if evidence.status == "blocked" else "none",
        }
    return _native_markdown(
        "# Repository Independent Review" if independent else "# Review Node Result",
        sections,
        payload,
        section_bodies,
        preamble="" if independent else _review_header(expectation, evidence),
    )


def _validation_result_payload(expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence) -> bytes:
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
    payload: dict[str, object] = {
        "after_repository_state_fingerprint": evidence.fingerprints.after[2],
        "after_scope_fingerprint": evidence.fingerprints.after[0],
        "after_worktree_fingerprint": evidence.fingerprints.after[1],
        "artifact_id": evidence.raw_result_artifact_id,
        "before_repository_state_fingerprint": evidence.fingerprints.before[2],
        "before_scope_fingerprint": evidence.fingerprints.before[0],
        "before_worktree_fingerprint": evidence.fingerprints.before[1],
        "command_identity_digest": expectation.command_identity_digest,
        "environment_digest": expectation.environment_digest,
        "evidence_id": evidence.evidence_id,
        "git_mutated": evidence.git_mutated,
        "mode": "validation",
        "node_id": evidence.node_id,
        "repository_state_fingerprint": evidence.fingerprints.expected[2],
        "requirement_ids": list(evidence.requirement_ids),
        "result_type": "validation-result",
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scope_fingerprint": evidence.fingerprints.expected[0],
        "skill_id": "review-validator",
        "source_mutated": evidence.source_mutated,
        "status": evidence.status,
        "validation_status": evidence.status,
        "worktree_fingerprint": evidence.fingerprints.expected[1],
    }
    disposition = {"passed": "passed", "failed": "failed", "blocked": "blocked", "reused": "reused", "not-applicable": "passed"}[evidence.status]
    failed_tail = "not-run" if expectation.validation_unit.dependency_policy == "stop-on-failure" else "passed"
    execution_results = {
        "passed": tuple("passed" for _ in expectation.validation_unit.commands),
        "failed": tuple("failed" if index == 0 else failed_tail for index, _ in enumerate(expectation.validation_unit.commands)),
        "blocked": (),
        "reused": (),
        "not-applicable": (),
    }[evidence.status]
    execution_records = (
        "\n".join(
            "\n".join(
                (
                    f"- Execution ID: {evidence.node_id}-exec-{index + 1}",
                    "  - Executor: parent",
                    f"  - Command: {command}",
                    f"  - Working directory: {expectation.validation_unit.working_directories[index]}",
                    f"  - Environment/configuration: {_validation_environment_identity(expectation.validation_unit)}",
                    f"  - Result: {execution_results[index]}",
                    f"  - Exit code: {'0' if execution_results[index] == 'passed' else 'none' if execution_results[index] == 'not-run' else '1'}",
                    f"  - Elapsed: {'none' if execution_results[index] == 'not-run' else '1s'}",
                    ("  - Evidence: not run after stop-on-failure" if execution_results[index] == "not-run" else "  - Evidence: fixture command evidence"),
                    "  - Log or artifact: none",
                )
            )
            for index, command in enumerate(expectation.validation_unit.commands)
        )
        if execution_results
        else "none"
    )
    requirement_counts = dict.fromkeys(("passed", "failed", "blocked", "reused"), 0)
    if evidence.requirement_ids:
        requirement_counts[disposition] = len(evidence.requirement_ids)
    execution_counts = {status: execution_results.count(status) for status in ("passed", "failed", "blocked", "not-run")}
    section_bodies = {
        "## Outcome Summary": "\n".join(
            (
                f"- Overall: {evidence.status.upper()}",
                "- Requirements: " + "; ".join(f"{status} {requirement_counts[status]}" for status in ("passed", "failed", "blocked", "reused")),
                "- Executions: " + "; ".join(f"{status} {execution_counts[status]}" for status in ("passed", "failed", "blocked", "not-run")),
                "- Review findings: not evaluated (validation-only)",
                "- Review severities: P0 not evaluated; P1 not evaluated; P2 not evaluated; P3 not evaluated",
            )
        ),
        "## Skill Loading": "\n".join(
            (
                f"- Skill file: {expectation.skill_path}",
                f"- Skill digest: {expectation.skill_digest}",
                f"- References loaded: {', '.join(path for path, _ in expectation.reference_digests) or 'none'}",
                f"- Reference digests: {', '.join(f'{path}={digest}' for path, digest in expectation.reference_digests) or 'none'}",
            )
        ),
        "## Validation Plan": _validation_plan_expected_body(expectation),
        "## State Verification": _state_verification(evidence),
        "## Requirements": _validation_requirements_expected_body(expectation, evidence),
        "## Executions": execution_records,
        "## Reused Evidence": (
            "\n".join(
                "\n".join(
                    (
                        f"- Ledger entry: {evidence_id}",
                        (
                            "  - Requirement IDs: "
                            + ", ".join(
                                requirement_id
                                for requirement_id, *_rest, mapped_evidence_id in expectation.validation_unit.requirement_plans
                                if mapped_evidence_id == evidence_id
                            )
                        ),
                        (
                            "  - Match basis: "
                            f"source={evidence.fingerprints.expected[2]}; command={expectation.command_identity_digest}; "
                            f"environment={expectation.environment_digest}; selection="
                            + ", ".join(
                                requirement_id
                                for requirement_id, *_rest, mapped_evidence_id in expectation.validation_unit.requirement_plans
                                if mapped_evidence_id == evidence_id
                            )
                        ),
                    )
                )
                for evidence_id in expectation.validation_unit.evidence_ids
            )
            if evidence.status == "reused"
            else "none"
        ),
        "## Artifacts": (
            "\n".join(
                "\n".join(
                    (
                        f"- Path: {artifact.path}",
                        f"  - Artifact ID: {artifact.artifact_id or 'none'}",
                        f"  - Artifact digest: {artifact.artifact_digest or 'none'}",
                        f"  - Kind: {artifact.kind}",
                        f"  - Repository status: {artifact.repository_status}",
                    )
                )
                for artifact in expectation.validation_unit.allowed_artifacts
            )
            or "none"
        ),
        "## Source And Git State": "\n".join(
            (
                f"- Source-controlled files changed: {'reported-change' if evidence.source_mutated else 'none'}",
                f"- Git state mutated: {'yes' if evidence.git_mutated else 'no'}",
            )
        ),
        "## Validation Ledger Export": "\n".join(f"- {label}: {value}" for label, value in _validation_ledger_expected_fields(expectation, evidence)),
        "## Limitations": "blocked execution" if evidence.status == "blocked" else "none",
    }
    return _native_markdown("# Validation Result", sections, payload, section_bodies, preamble=_validation_header(evidence))


def _result_digest(evidence_id: str) -> str:
    return "sha256:" + hashlib.sha256(evidence_id.encode()).hexdigest()


def _capacity(*, remaining: int | None = None, active: int = 1) -> dict[str, object]:
    result: dict[str, object] = {"source": "runtime-capability-metadata", "concurrent_worker_limit": 4, "active_workers": active}
    if remaining is not None:
        result["fresh_worker_creations_remaining"] = remaining
        result["lifecycle_semantics"] = "bounded-total"
    return result


def test_no_fresh_worker_capacity_blocks_before_dispatch() -> None:
    result = assess_worker_capacity(_capacity(remaining=0), required_fresh_worker_creations=1)

    assert not result.feasible
    assert result.blockers == ("no fresh-worker creation capacity remains",)


def test_unknown_total_fresh_worker_capacity_allows_incremental_dispatch() -> None:
    result = assess_worker_capacity(_capacity(), required_fresh_worker_creations=22)

    assert result.feasible
    assert result.fresh_worker_creations_remaining is None
    assert result.full_plan_creation_capacity_guaranteed is None


def test_known_insufficient_current_root_capacity_blocks_epoch_dispatch() -> None:
    result = assess_worker_capacity(_capacity(remaining=3), required_fresh_worker_creations=22)

    assert not result.feasible
    assert result.required_fresh_worker_creations == 22
    assert result.full_plan_creation_capacity_guaranteed is False
    assert result.blockers == ("known fresh-worker capacity is smaller than the bounded plan: requires 22, has 3",)


def test_no_free_concurrent_slot_blocks_before_dispatch() -> None:
    result = assess_worker_capacity(_capacity(active=4), required_fresh_worker_creations=1)

    assert not result.feasible
    assert result.blockers == ("insufficient concurrent-worker capacity: requires 1, has 0",)


def test_capacity_evidence_rejects_prior_reports_without_echoing_them() -> None:
    prior_text = "prior finding that must not enter capacity diagnosis"
    metadata = {**_capacity(remaining=3), "workers": [{"final_report": prior_text}]}

    result = assess_worker_capacity(metadata, required_fresh_worker_creations=1)

    assert not result.feasible
    assert result.blockers[0].startswith("isolation-failure:")
    assert "$.workers[0].final_report" in result.blockers[0]
    assert prior_text not in result.blockers[0]


def test_grouped_delivery_is_the_default_without_capacity_diagnosis() -> None:
    result = select_execution_profile()

    assert result.feasible
    assert result.profile == "grouped"
    assert result.blockers == ()


def test_explicit_isolation_uses_isolated_profile_when_capability_is_safe() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=24, active=1))

    assert result.feasible
    assert result.profile == "isolated"


def test_explicit_isolation_uses_grouped_profile_when_lifetime_capacity_is_unknown() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "authoritative lifetime fresh-worker capacity is unavailable" in result.blockers


def test_isolation_preference_falls_back_to_grouped_delivery() -> None:
    result = select_execution_profile(isolated_requested=True)

    assert result.feasible
    assert result.profile == "grouped"
    assert "fresh no-inherited-turn workers are unavailable" in result.blockers
    assert "safe aggregate worker-capacity metadata is unavailable" in result.blockers


def test_isolation_uses_authoritative_capacity_as_the_effective_epoch_budget() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "isolated"
    assert result.configured_worker_budget == 24
    assert result.effective_worker_budget == 2


def test_isolation_accepts_creation_capacity_beyond_the_recovery_reserve() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=24, active=1))

    assert result.feasible
    assert result.profile == "isolated"
    assert result.effective_worker_budget == 24


def test_isolation_falls_back_when_effective_budget_cannot_fit_worker_and_reserve() -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=1, active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert result.effective_worker_budget == 1
    assert "effective fresh-worker budget must exceed the recovery/finalization reserve" in result.blockers


def test_isolated_only_blocks_when_safe_capacity_is_unavailable() -> None:
    result = select_execution_profile(
        isolated_only=True, fresh_workers_supported=True, capacity_metadata={**_capacity(), "workers": [{"final_report": "must not leak"}]}
    )

    assert not result.feasible
    assert result.profile == "blocked"
    assert result.blockers[0].startswith("isolation-failure:")
    assert "must not leak" not in result.blockers[0]


@pytest.mark.parametrize("value", [1, "isolated"])
def test_malformed_isolation_preference_uses_grouped_delivery(value: object) -> None:
    result = select_execution_profile(isolated_requested=cast("bool", value), fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "isolated_requested must be a boolean" in result.blockers


@pytest.mark.parametrize("value", [1, "available"])
def test_malformed_fresh_worker_support_uses_grouped_delivery(value: object) -> None:
    result = select_execution_profile(isolated_requested=True, fresh_workers_supported=cast("bool", value), capacity_metadata=_capacity(remaining=2, active=1))

    assert result.feasible
    assert result.profile == "grouped"
    assert "fresh_workers_supported must be a boolean" in result.blockers


@pytest.mark.parametrize("value", [1, "isolated-only"])
def test_malformed_isolated_only_request_blocks(value: object) -> None:
    result = select_execution_profile(isolated_only=cast("bool", value), fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1))

    assert not result.feasible
    assert result.profile == "blocked"
    assert result.isolated_only
    assert "isolated_only must be a boolean" in result.blockers


@pytest.mark.parametrize(
    ("field", "value", "expected_blocker"),
    [
        ("total", True, "worker budget total must be a non-boolean integer"),
        ("total", "24", "worker budget total must be a non-boolean integer"),
        ("recovery_finalization_reserve", True, "worker budget recovery/finalization reserve must be a non-boolean integer"),
        ("recovery_finalization_reserve", "1", "worker budget recovery/finalization reserve must be a non-boolean integer"),
    ],
)
def test_malformed_worker_budget_uses_grouped_delivery(field: str, value: object, expected_blocker: str) -> None:
    malformed_budget = replace(WorkerBudget(), **{field: value})

    result = select_execution_profile(
        isolated_requested=True, fresh_workers_supported=True, capacity_metadata=_capacity(remaining=2, active=1), budget=malformed_budget
    )

    assert result.feasible
    assert result.profile == "grouped"
    assert expected_blocker in result.blockers


def test_packaged_python_support_tooling_requires_build_portability() -> None:
    pyproject = """
[build-system]
requires = ["setuptools"]

[project]
name = "support-tools"

[project.scripts]
alpha = "helpers:alpha"

[tool.setuptools]
package-dir = {"" = "src"}
py-modules = ["helpers"]

[tool.uv]
package = true
"""

    result = guard_packaged_python_routing(("python-support-scripts",), pyproject)

    assert result.added_python_build_portability
    assert result.selected_skills == ("python-support-scripts", "python-build-portability")
    assert {"project.scripts", "tool.setuptools.py-modules", "tool.uv.package"} <= set(result.packaging_signals)


def _closed_rust_routing_decisions() -> tuple[RoutingDecision, ...]:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    selected = {"repo.rust", "repo.independent", "repo.synthesis", "rust.invariants", "rust.tests", "rust.synthesis"}
    decisions: list[RoutingDecision] = []
    for entry in catalog:
        if entry.router_id not in {"review-graph", "rust-review-orchestrator"}:
            continue
        disposition = "selected" if entry.catalog_id in selected else "not-applicable"
        review_surface = (RUST_FIXTURE_PATH,) if disposition == "selected" and entry.target_kind in {"leaf", "independent"} else ()
        decisions.append(
            RoutingDecision(
                catalog_id=entry.catalog_id,
                requirement_id=f"requirement-{entry.catalog_id}",
                router_id=entry.router_id,
                rule_id=entry.rule_id,
                skill_id=entry.skill_id,
                skill_path=entry.skill_path,
                disposition=disposition,
                reason=(
                    "fixture decision from observed Rust state transition" if disposition == "selected" else "fixture surface does not exhibit this contract"
                ),
                applicability_evidence=(f"{RUST_FIXTURE_PATH} inspected",),
                review_surface=review_surface,
                static_references=entry.required_static_references,
                synthesis_dependency=entry.synthesis_dependency if disposition == "selected" else None,
                priority=entry.default_priority,
                owners=(entry.surface,),
            )
        )
    return tuple(decisions)


def _exhaustive_rust_document() -> dict[str, object]:
    capture = _rust_fixture_capture_manifest()
    return {
        "execution_profile": "isolated",
        "worker_budget": 5,
        "recovery_finalization_reserve": 1,
        "scope_mode": "branch",
        "concrete_change_target": True,
        "change_target": f"git diff origin/main...HEAD -- {RUST_FIXTURE_PATH}",
        "capture_mode": capture["capture_mode"],
        "base_ref": capture["base_ref"],
        "head": capture["head"],
        "merge_base": capture["merge_base"],
        "requested_paths": capture["requested_paths"],
        "scope_fingerprint": capture["scope_fingerprint"],
        "captured_worktree_fingerprint": capture["captured_worktree_fingerprint"],
        "repository_state_fingerprint": capture["repository_state_fingerprint"],
        "captured_paths": capture["captured_scope_paths"],
        "captured_path_line_bounds": capture["captured_path_line_bounds"],
        "consulted_routers": ["review-graph", "rust-review-orchestrator"],
        "routing_decisions": [json.loads(json.dumps(asdict(item))) for item in _closed_rust_routing_decisions()],
        "validation_requirements": [
            {
                "requirement_id": "baseline",
                "source_state": ["scope", "worktree", "repository"],
                "commands": ["just ci"],
                "working_directories": ["/repo"],
                "environment": "locked",
                "toolchain": "stable",
                "features": ["default"],
                "platform": "current-host",
                "artifact_owner": "repository",
                "mutation_lock": "read-only",
                "request": "run the exact repository validation gate",
                "requested_scope": "branch",
                "capture_command": f"capture_scope.py --repo {REPOSITORY_ROOT} --mode branch --path {RUST_FIXTURE_PATH}",
                "captured_paths": [RUST_FIXTURE_PATH],
                "authority": "graph dispatch",
                "selection_reason": "baseline validation for the captured Rust fixture",
                "mutation_classification": "non-mutating under validation-only",
                "expected_evidence": "the exact dispatched command exits successfully",
                "elapsed_time_budget": "300s",
                "dependency_policy": "stop-on-failure",
                "meaningful_skips": [],
                "execution_strategy": "sequential",
                "independence_basis": "none",
                "planning_blocker": None,
                "canonical_recipe": "just ci",
                "required": True,
                "baseline": True,
            }
        ],
        "synthesis_nodes": [
            {
                "node_id": "rust-synthesis",
                "skill_id": "rust-production-review",
                "skill_path": "$SKILLS_ROOT/rust-production-review/SKILL.md",
                "coverage": ["Rust synthesis"],
                "predecessors": [],
            },
            {
                "node_id": "repository-synthesis",
                "skill_id": "repository-production-review",
                "skill_path": "$SKILLS_ROOT/repository-production-review/SKILL.md",
                "coverage": ["Repository synthesis"],
                "predecessors": [],
            },
        ],
    }


def _set_instruction_path(document: dict[str, object], *, target: str, instruction_path: str) -> str:
    if target == "synthesis":
        syntheses = cast("list[dict[str, object]]", document["synthesis_nodes"])
        syntheses[0]["instruction_paths"] = [instruction_path]
        return str(syntheses[0]["node_id"])
    document["additional_nodes"] = [
        {
            "node_id": "revalidation-rust",
            "skill_id": "rust-test-quality",
            "skill_path": "$SKILLS_ROOT/rust-test-quality/SKILL.md",
            "mode": "revalidation",
            "priority": "required-validation",
            "required": True,
            "coverage": [RUST_FIXTURE_PATH],
            "predecessors": [],
            "synthesis_dependency": "rust-synthesis",
            "instruction_paths": [instruction_path],
        }
    ]
    return "revalidation-rust"


def test_real_routing_catalog_resolves_every_skill_path_and_frontmatter() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)

    assert len(catalog) == 53
    assert all(Path(entry.skill_path).is_absolute() for entry in catalog)
    assert {entry.router_id for entry in catalog} == {
        "review-graph",
        "cpp-review-orchestrator",
        "rust-review-orchestrator",
        "python-review-orchestrator",
        "docs-review-orchestrator",
    }
    by_router = {router: {entry.skill_id for entry in catalog if entry.router_id == router} for router in {entry.router_id for entry in catalog}}
    assert by_router["review-graph"] == {
        "project-tooling-review",
        "cpp-review-orchestrator",
        "rust-review-orchestrator",
        "python-review-orchestrator",
        "docs-review-orchestrator",
        "repository-independent-review",
        "repository-production-review",
    }
    assert by_router["cpp-review-orchestrator"] == {
        "cpp-lifetime-ownership-safety",
        "cpp-exception-safety-error-contracts",
        "cpp-invariant-state-transitions",
        "cpp-parse-dont-validate",
        "cpp-api-design",
        "cpp-api-docs",
        "cpp-build-portability",
        "cpp-functional-style",
        "cpp-scientific-correctness",
        "cpp-concurrency-reentrancy",
        "cpp-test-quality",
        "cpp-production-review",
    }
    assert by_router["rust-review-orchestrator"] == {
        "rust-build-portability",
        "rust-cargo-hygiene",
        "rust-api-docs",
        "rust-prelude-exports",
        "rust-fluent-api-design",
        "rust-trait-bounds",
        "rust-cli-design",
        "rust-invariant-state-transitions",
        "rust-parse-dont-validate",
        "rust-error-variants",
        "rust-borrowed-view-audit",
        "rust-scientific-correctness",
        "rust-concurrency-async",
        "rust-style-hygiene",
        "rust-iter-control-flow",
        "rust-simplification-review",
        "rust-invariant-performance",
        "rust-test-quality",
        "rust-production-review",
    }
    assert by_router["python-review-orchestrator"] == {
        "python-build-portability",
        "jupyter-notebook-review",
        "python-cli-review",
        "python-parse-dont-validate",
        "python-scientific-review",
        "python-support-scripts",
        "python-test-quality",
        "python-production-review",
    }
    assert by_router["docs-review-orchestrator"] == {
        "repository-docs-review",
        "scientific-software-docs-review",
        "scientific-crate-docs-review",
        "cpp-api-docs",
        "rust-api-docs",
        "scientific-citation-audit",
        "academic-authorship-boundary",
    }


def test_exhaustive_routing_ledger_closes_selected_repository_and_surface_router() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    result = validate_routing_ledger(catalog, _closed_rust_routing_decisions(), consulted_routers=("review-graph", "rust-review-orchestrator"))

    assert result.feasible
    assert result.catalog_closed
    assert set(result.selected_requirement_ids) == {"requirement-repo.independent", "requirement-rust.invariants", "requirement-rust.tests"}


def test_empty_routing_ledger_cannot_close_without_repository_router() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)

    result = validate_routing_ledger(catalog, (), consulted_routers=())

    assert not result.feasible
    assert not result.catalog_closed
    assert result.blockers == ("routing ledger must consult review-graph before catalog closure",)


def test_exhaustive_routing_ledger_rejects_silent_omission() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    decisions = tuple(item for item in _closed_rust_routing_decisions() if item.catalog_id != "rust.errors")

    result = validate_routing_ledger(catalog, decisions, consulted_routers=("review-graph", "rust-review-orchestrator"))

    assert not result.feasible
    assert not result.catalog_closed
    assert any("rust.errors" in blocker for blocker in result.blockers)


def test_exhaustive_routing_document_plans_every_selected_leaf_across_epochs() -> None:
    document = _exhaustive_rust_document()

    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)

    assert plan.dispatch_allowed
    assert plan.routing_catalog_closed
    assert plan.consulted_routers == ("review-graph", "rust-review-orchestrator")
    assert len(plan.actual_worker_nodes) == 6
    assert len(plan.execution_epochs) == 2
    assert {node.skill_id for node in plan.actual_worker_nodes} >= {
        "rust-invariant-state-transitions",
        "rust-test-quality",
        "repository-independent-review",
        "rust-production-review",
        "repository-production-review",
    }
    invariant_node = next(node for node in plan.actual_worker_nodes if node.skill_id == "rust-invariant-state-transitions")
    rust_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "rust-synthesis")
    repository_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "repository-synthesis")
    assert invariant_node.selection_reasons == ("fixture decision from observed Rust state transition",)
    assert invariant_node.owners == ("rust",)
    assert "rust-synthesis" in repository_synthesis.predecessors
    assert plan.actual_worker_nodes.index(rust_synthesis) < plan.actual_worker_nodes.index(repository_synthesis)


@pytest.mark.parametrize(
    ("catalog_id", "requirement_id", "skill_id", "mode"),
    [
        ("rust.tests", "requirement-rust.tests", "rust-test-quality", "audit"),
        ("repo.independent", "requirement-repo.independent", "repository-independent-review", "independent-review"),
    ],
)
def test_exact_review_reuse_is_typed_nonexecutable_evidence(catalog_id: str, requirement_id: str, skill_id: str, mode: str) -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    document = _exhaustive_rust_document()
    evidence_id = f"review:reused:{catalog_id}"
    decisions = cast("list[dict[str, object]]", document["routing_decisions"])
    for decision in decisions:
        if decision["catalog_id"] == catalog_id:
            decision["disposition"] = "exact-evidence-reused"
            decision["evidence_id"] = evidence_id

    routed_decisions = tuple(
        replace(decision, disposition="exact-evidence-reused", evidence_id=evidence_id) if decision.catalog_id == catalog_id else decision
        for decision in _closed_rust_routing_decisions()
    )
    routing_assessment = validate_routing_ledger(catalog, routed_decisions, consulted_routers=("review-graph", "rust-review-orchestrator"))

    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)
    expectation = repository_review_proof_expectation(plan, source_state=("scope", "worktree", "repository"))

    assert plan.dispatch_allowed
    assert routing_assessment.exact_reused_review_evidence == ((requirement_id, evidence_id),)
    assert plan.complete_node_count == 5
    assert all(node.skill_id != skill_id for node in plan.actual_worker_nodes)
    assert (requirement_id, evidence_id) in plan.exact_reused_review_evidence
    assert (requirement_id, evidence_id) in expectation.exact_reused_review_evidence
    assert any(
        (item.requirement_id, item.evidence_id, item.skill_id, item.mode) == (requirement_id, evidence_id, skill_id, mode)
        for item in expectation.reused_review_identities
    )
    assert requirement_id not in dict(plan.requirement_to_node)
    assert all(evidence_id not in node.predecessors for node in plan.actual_worker_nodes)


def test_repository_synthesis_derives_every_surface_synthesis_predecessor() -> None:
    requirements = (_review_requirement(1, synthesis_dependency="rust-synthesis"), _review_requirement(2, synthesis_dependency="python-synthesis"))
    syntheses = (
        _synthesis("rust-synthesis"),
        replace(_synthesis("python-synthesis"), skill_id="python-production-review", skill_path=str(SKILL_ROOT / "python-production-review" / "SKILL.md")),
        WorkerNode(
            node_id="repository-synthesis",
            skill_id="repository-production-review",
            skill_path=str(SKILL_ROOT / "repository-production-review" / "SKILL.md"),
            mode="synthesis",
            priority="required-routing-synthesis",
            required=True,
        ),
    )

    plan = plan_graph(requirements, (_validation_requirement("V-baseline", baseline=True),), syntheses)

    repository_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "repository-synthesis")
    assert {"rust-synthesis", "python-synthesis"} <= set(repository_synthesis.predecessors)
    order = tuple(node.node_id for node in plan.actual_worker_nodes)
    assert order.index("rust-synthesis") < order.index("repository-synthesis")
    assert order.index("python-synthesis") < order.index("repository-synthesis")


def test_repository_synthesis_depends_on_unowned_baseline_validation() -> None:
    plan = plan_graph(
        (_review_requirement(1, synthesis_dependency="repository-synthesis"),),
        (_validation_requirement("V-baseline", baseline=True),),
        (
            WorkerNode(
                node_id="repository-synthesis",
                skill_id="repository-production-review",
                skill_path=str(SKILL_ROOT / "repository-production-review" / "SKILL.md"),
                mode="synthesis",
                priority="required-routing-synthesis",
                required=True,
                skill_digest="sha256:surface-synthesis",
            ),
        ),
    )

    repository_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "repository-synthesis")
    assert "validation-001" in repository_synthesis.predecessors


@pytest.mark.parametrize("target", ["synthesis", "additional"])
def test_graph_document_accepts_repository_instruction_paths(target: str) -> None:
    instruction = REPOSITORY_ROOT / "AGENTS.md"
    document = _exhaustive_rust_document()
    node_id = _set_instruction_path(document, target=target, instruction_path="AGENTS.md")

    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)

    node = next(item for item in plan.actual_worker_nodes if item.node_id == node_id)
    assert node.instruction_paths == (str(instruction.resolve()),)


@pytest.mark.parametrize("target", ["synthesis", "additional"])
@pytest.mark.parametrize("path_kind", ["absolute-outside", "traversal"])
def test_graph_document_rejects_repository_instruction_paths_outside_root(tmp_path: Path, target: str, path_kind: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    instruction = outside / "AGENTS.md"
    instruction.write_text("# Outside instructions\n")
    document = _exhaustive_rust_document()
    document["repository_root"] = str(tmp_path)
    raw_path = str(instruction) if path_kind == "absolute-outside" else "../outside/AGENTS.md"
    _set_instruction_path(document, target=target, instruction_path=raw_path)

    with pytest.raises(ValueError, match="repository instruction path"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


def test_exhaustive_routing_normalizes_review_surfaces_within_captured_paths() -> None:
    document = _exhaustive_rust_document()
    decisions = cast("list[dict[str, object]]", document["routing_decisions"])
    for decision in decisions:
        if decision["catalog_id"] == "rust.tests":
            decision["review_surface"] = [RUST_FIXTURE_PATH.replace("/state.rs", "/./state.rs")]

    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)

    node = next(node for node in plan.actual_worker_nodes if node.skill_id == "rust-test-quality")
    assert node.coverage == (RUST_FIXTURE_PATH,)


@pytest.mark.parametrize("disposition", ["selected", "exact-evidence-reused"])
def test_exhaustive_routing_rejects_review_surfaces_outside_captured_paths(disposition: str) -> None:
    document = _exhaustive_rust_document()
    decisions = cast("list[dict[str, object]]", document["routing_decisions"])
    for decision in decisions:
        if decision["catalog_id"] == "rust.tests":
            decision["disposition"] = disposition
            decision["review_surface"] = ["src/outside.rs"]
            if disposition == "exact-evidence-reused":
                decision["evidence_id"] = "review:rust-tests"

    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)

    assert not plan.dispatch_allowed
    assert "rust.tests review_surface is outside captured_paths: src/outside.rs" in plan.blockers


def test_exhaustive_routing_rejects_additional_node_coverage_outside_captured_paths() -> None:
    document = _exhaustive_rust_document()
    document["additional_nodes"] = [
        {
            "node_id": "revalidation-rust",
            "skill_id": "rust-test-quality",
            "skill_path": "$SKILLS_ROOT/rust-test-quality/SKILL.md",
            "mode": "revalidation",
            "priority": "required-validation",
            "required": True,
            "coverage": ["src/outside.rs"],
            "predecessors": [],
            "synthesis_dependency": "rust-synthesis",
        }
    ]

    with pytest.raises(ValueError, match="additional node revalidation-rust coverage is outside captured_paths"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


@pytest.mark.parametrize("value", ["false", 0, 1, None])
@pytest.mark.parametrize("field", ["release_readiness", "validation.required", "validation.baseline", "additional.required"])
def test_graph_document_rejects_non_boolean_fields(field: str, value: object) -> None:
    document = _exhaustive_rust_document()
    if field == "release_readiness":
        document["release_readiness"] = value
    elif field.startswith("validation."):
        validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
        validation[field.removeprefix("validation.")] = value
    else:
        document["additional_nodes"] = [
            {
                "node_id": "revalidation-rust",
                "skill_id": "rust-test-quality",
                "skill_path": "$SKILLS_ROOT/rust-test-quality/SKILL.md",
                "mode": "revalidation",
                "priority": "required-validation",
                "required": value,
                "coverage": [RUST_FIXTURE_PATH],
                "predecessors": [],
                "synthesis_dependency": "rust-synthesis",
            }
        ]

    with pytest.raises(ValueError, match="must be a boolean"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


@pytest.mark.parametrize(
    "source_state", ["scope", ["scope", "worktree"], ["scope", "worktree", "repository", "extra"], ["scope", " ", "repository"], ["scope", 1, "repository"]]
)
def test_graph_document_rejects_malformed_validation_source_state(source_state: object) -> None:
    document = _exhaustive_rust_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation["source_state"] = source_state

    with pytest.raises(ValueError, match="source_state must be exactly three bounded non-empty strings"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


@pytest.mark.parametrize(
    "field",
    [
        "requirement_id",
        "environment",
        "toolchain",
        "platform",
        "artifact_owner",
        "mutation_lock",
        "request",
        "requested_scope",
        "capture_command",
        "authority",
        "selection_reason",
        "mutation_classification",
        "expected_evidence",
        "elapsed_time_budget",
        "dependency_policy",
        "execution_strategy",
        "independence_basis",
    ],
)
def test_graph_document_rejects_non_string_validation_configuration(field: str) -> None:
    document = _exhaustive_rust_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation[field] = True

    with pytest.raises(ValueError, match=rf"{field} must be a bounded non-empty string"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


@pytest.mark.parametrize("value", [1, [], {}, None, " "])
def test_graph_document_rejects_malformed_validation_configuration_text(value: object) -> None:
    document = _exhaustive_rust_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation["environment"] = value

    with pytest.raises(ValueError, match="environment must be a bounded non-empty string"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


def test_graph_document_preserves_optional_validation_artifact_identity() -> None:
    document = _exhaustive_rust_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    artifact_digest = "sha256:" + "a" * 64
    validation["allowed_artifacts"] = [
        {
            "path": "/external/review-validator/command.log",
            "artifact_id": "artifact://command-log",
            "artifact_digest": artifact_digest,
            "kind": "log",
            "repository_status": "outside-repository",
        }
    ]

    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)

    assert plan.coalesced_validation_units[0].allowed_artifacts == (
        ValidationArtifact(
            path="/external/review-validator/command.log",
            artifact_id="artifact://command-log",
            artifact_digest=artifact_digest,
            kind="log",
            repository_status="outside-repository",
        ),
    )


@pytest.mark.parametrize(
    "artifact",
    [
        {"path": "/external/log", "artifact_id": 1, "kind": "log", "repository_status": "outside-repository"},
        {"path": "/external/log", "artifact_digest": "sha256:invalid", "kind": "log", "repository_status": "outside-repository"},
    ],
)
def test_graph_document_rejects_malformed_validation_artifact_identity(artifact: dict[str, object]) -> None:
    document = _exhaustive_rust_document()
    validation = cast("list[dict[str, object]]", document["validation_requirements"])[0]
    validation["allowed_artifacts"] = [artifact]

    with pytest.raises(ValueError, match=r"allowed artifacts|allowed_artifacts"):
        plan_from_document(document, repository_root=REPOSITORY_ROOT)


def test_budget_deferred_routing_is_completion_blocking() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    decisions = tuple(
        replace(item, disposition="budget-deferred", reason="worker budget exhausted") if item.catalog_id == "rust.tests" else item
        for item in _closed_rust_routing_decisions()
    )

    result = validate_routing_ledger(catalog, decisions, consulted_routers=("review-graph", "rust-review-orchestrator"))

    assert not result.feasible
    assert result.completion_blocking_catalog_ids == ("rust.tests",)


def test_late_routing_handoff_blocks_synthesis_until_replanned() -> None:
    decisions = _closed_rust_routing_decisions()
    discovery = RoutingDiscovery("handoff-errors", "audit-001", "rust.errors", "new typed error contract discovered")

    blocked = assess_routing_discoveries(decisions, (discovery,))
    selected = tuple(
        replace(item, disposition="selected", review_surface=("src/error.rs",)) if item.catalog_id == "rust.errors" else item for item in decisions
    )
    closed = assess_routing_discoveries(selected, (discovery,))

    assert not blocked.feasible
    assert closed.feasible


def test_repository_classifier_routes_shared_manifests_and_workflows_to_all_owners() -> None:
    signals = classify_repository_paths(("Cargo.toml", "pyproject.toml", "src/lib.rs", "src/tool.py", ".github/workflows/ci.yml", "README.md"))

    assert set(signals) == {"tooling", "rust", "python", "documentation"}
    assert any("Cargo.toml" in item for item in signals["tooling"])
    assert any("ci.yml" in item for item in signals["rust"])
    assert any("ci.yml" in item for item in signals["python"])


def test_repository_classifier_detects_nested_language_manifests_for_shared_workflows() -> None:
    signals = classify_repository_paths(("crates/core/Cargo.toml", "packages/app/pyproject.toml", ".github/workflows/ci.yml"))

    assert any("ci.yml" in item for item in signals["rust"])
    assert any("ci.yml" in item for item in signals["python"])


def test_repository_classifier_floor_rejects_router_conflict() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    decisions = _closed_rust_routing_decisions()
    signals = classify_repository_paths(("pyproject.toml",))

    result = assess_repository_classifier_floor(catalog, decisions, signals)

    assert not result.feasible
    assert any("repo.python is not-applicable" in blocker for blocker in result.blockers)
    assert any("repo.tooling is not-applicable" in blocker for blocker in result.blockers)


def test_repository_routing_surface_migration_matrix() -> None:
    fixture = Path(__file__).with_name("fixtures") / "routing_surface_matrix.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]

    for case in cases:
        signals = classify_repository_paths(tuple(case["paths"]), release_readiness=bool(case.get("release_readiness", False)))
        assert set(signals) == set(case["expected_surfaces"]), case["id"]


def test_bounded_critical_path_over_deadline_runs_with_explicit_risk() -> None:
    nodes = tuple(PlanNode(f"A{index:02}", 300) for index in range(1, 20))

    result = assess_time_budget(nodes, TimeBudget(overall_seconds=45 * 60, coordinator_reserve_seconds=5 * 60, validation_reserve_seconds=20 * 60))

    assert result.feasible
    assert result.critical_path_seconds == 19 * 300
    assert result.policy == "run-until-deadline-account-for-unrun"
    assert result.overall_budget_seconds is not None
    assert result.required_seconds > result.overall_budget_seconds
    assert result.completion_guaranteed_with_caps is False


def test_deadline_truncates_node_timeout_and_preserves_reconciliation_reserve() -> None:
    budget = TimeBudget(overall_seconds=600, coordinator_reserve_seconds=60, validation_reserve_seconds=120)

    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=100, budget=budget) == 300
    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=350, budget=budget) == 70
    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=500, budget=budget) == 0


def test_unbounded_request_keeps_per_node_cap() -> None:
    budget = TimeBudget(overall_seconds=None, coordinator_reserve_seconds=60, validation_reserve_seconds=120)
    result = assess_time_budget((PlanNode("A01", 300),), budget)

    assert result.feasible
    assert result.overall_budget_seconds is None
    assert result.completion_guaranteed_with_caps is None
    assert result.policy == "per-node-caps-only"
    assert bounded_node_dispatch_seconds(node_cap_seconds=300, elapsed_seconds=10_000, budget=budget) == 300


def test_pre_execution_blocks_reconcile_without_claiming_skills_or_validators() -> None:
    result = reconcile_execution(
        ExecutionLedger(
            selected_nodes=("A01", "V01"),
            accepted_nodes=(),
            blocked_after_execution=(),
            blocked_before_execution=("A01", "V01"),
            invalidated_nodes=(),
            worker_attempts=(),
            workers_created=(),
            worker_creation_failures=(),
            skills_executed=(),
            planned_validators=("V01",),
            executed_validators=(),
            validators_not_run=("V01",),
        )
    )

    assert result.feasible


def test_invalidated_validator_reconciles_as_an_explicit_stale_outcome() -> None:
    result = reconcile_execution(
        ExecutionLedger(
            selected_nodes=("V01",),
            accepted_nodes=(),
            blocked_after_execution=(),
            blocked_before_execution=(),
            invalidated_nodes=("V01",),
            worker_attempts=("V01",),
            workers_created=("V01",),
            worker_creation_failures=(),
            skills_executed=("V01",),
            planned_validators=("V01",),
            executed_validators=("V01",),
            validators_not_run=(),
        )
    )

    assert result.feasible


def test_adaptive_coordinator_execution_reconciles_without_worker_creation() -> None:
    result = reconcile_execution(
        ExecutionLedger(
            selected_nodes=("A01",),
            accepted_nodes=("A01",),
            blocked_after_execution=(),
            blocked_before_execution=(),
            invalidated_nodes=(),
            worker_attempts=("A01",),
            workers_created=(),
            worker_creation_failures=("A01",),
            skills_executed=("A01",),
            planned_validators=(),
            executed_validators=(),
            validators_not_run=(),
            coordinator_executions=("A01",),
        )
    )

    assert result.feasible


def _review_requirement(
    ordinal: int, *, priority: str = "supporting-quality", required: bool = False, skill_id: str | None = None, synthesis_dependency: str = "rust-synthesis"
) -> ReviewRequirement:
    return ReviewRequirement(
        requirement_id=f"R{ordinal:02d}",
        skill_id=skill_id or f"specialist-{ordinal:02d}",
        skill_path=f"/skills/specialist-{ordinal:02d}/SKILL.md",
        router_id="rust-review-orchestrator",
        rule_id=f"fixture-rule-{ordinal:02d}",
        review_surface=(f"src/surface_{ordinal:02d}.rs",),
        reason="fixture surface owns this contract",
        priority=priority,
        synthesis_dependency=synthesis_dependency,
        required=required,
        skill_digest=f"sha256:specialist-{ordinal:02d}",
    )


def _validation_requirement(requirement_id: str, *, command: str = "just ci", evidence_id: str | None = None, baseline: bool = False) -> ValidationRequirement:
    return ValidationRequirement(
        requirement_id=requirement_id,
        source_state=("scope", "worktree", "repository"),
        commands=(command,),
        working_directories=("/repo",),
        environment="macos-arm64; locked dependencies",
        toolchain="stable",
        features=("default",),
        platform="macos-arm64",
        artifact_owner="repository-current-host",
        mutation_lock="shared-readonly-build-root",
        canonical_recipe=command,
        evidence_id=evidence_id,
        baseline=baseline,
    )


def _synthesis(node_id: str = "rust-synthesis") -> WorkerNode:
    return WorkerNode(
        node_id=node_id,
        skill_id="rust-production-review",
        skill_path=str(SKILL_ROOT / "rust-production-review" / "SKILL.md"),
        mode="synthesis",
        priority="required-routing-synthesis",
        required=True,
        coverage=("Rust synthesis",),
    )


def test_over_budget_plan_is_partitioned_without_omission() -> None:
    requirements = tuple(_review_requirement(index) for index in range(1, 9))
    plan = plan_graph(
        requirements,
        (_validation_requirement("V-baseline", baseline=True),),
        (_synthesis(),),
        budget=WorkerBudget(total=5, recovery_finalization_reserve=1),
        execution_profile="isolated",
    )

    assert plan.dispatch_allowed
    assert plan.complete_node_count == 10
    assert len(plan.actual_worker_nodes) == 10
    assert len(plan.execution_epochs) == 3
    assert all(len(epoch.node_ids) + epoch.recovery_finalization_reserve <= epoch.worker_budget for epoch in plan.execution_epochs)
    assert plan.requires_continuation


def test_concrete_independent_review_requires_trusted_captured_path_line_bounds() -> None:
    missing = _exhaustive_rust_document()
    del missing["captured_path_line_bounds"]
    with pytest.raises(ValueError, match="do not match independently recaptured source bytes"):
        plan_from_document(missing, repository_root=REPOSITORY_ROOT)

    inflated = _exhaustive_rust_document()
    inflated["captured_path_line_bounds"] = {RUST_FIXTURE_PATH: 999_999_999}
    with pytest.raises(ValueError, match="do not match independently recaptured source bytes"):
        plan_from_document(inflated, repository_root=REPOSITORY_ROOT)

    malformed = _exhaustive_rust_document()
    malformed["captured_path_line_bounds"] = {RUST_FIXTURE_PATH: True}
    with pytest.raises(ValueError, match="must be a nonnegative integer"):
        plan_from_document(malformed, repository_root=REPOSITORY_ROOT)

    outside = _exhaustive_rust_document()
    outside["captured_path_line_bounds"] = {RUST_FIXTURE_PATH: 3, "outside.rs": 10}
    with pytest.raises(ValueError, match="outside captured_paths"):
        plan_from_document(outside, repository_root=REPOSITORY_ROOT)


def test_synthesis_and_baseline_validation_retain_reserved_capacity() -> None:
    plan = plan_graph(
        tuple(_review_requirement(index, priority="optional-hygiene") for index in range(1, 7)),
        (_validation_requirement("V-baseline", baseline=True),),
        (_synthesis(),),
        budget=WorkerBudget(total=4, recovery_finalization_reserve=1),
        execution_profile="isolated",
    )

    selected = {node.node_id for node in plan.actual_worker_nodes}
    assert {"validation-001", "rust-synthesis"} <= selected
    assert len(plan.actual_worker_nodes) == 8
    assert len(plan.execution_epochs) == 3
    order = [node.node_id for node in plan.actual_worker_nodes]
    assert order.index("validation-001") < order.index("rust-synthesis")


def test_grouped_plan_over_worker_budget_has_no_execution_epochs() -> None:
    plan = plan_graph(tuple(_review_requirement(index) for index in range(1, 25)), (_validation_requirement("V-baseline", baseline=True),), (_synthesis(),))

    assert plan.execution_profile == "grouped"
    assert len(plan.actual_worker_nodes) == 26
    assert plan.execution_epochs == ()
    assert plan.current_epoch_node_ids == ()
    assert not plan.requires_continuation


def test_mixed_plan_retains_epoch_partitioning_for_its_isolated_portion() -> None:
    plan = plan_graph(
        tuple(_review_requirement(index) for index in range(1, 9)),
        (_validation_requirement("V-baseline", baseline=True),),
        (_synthesis(),),
        budget=WorkerBudget(total=5, recovery_finalization_reserve=1),
        execution_profile="mixed",
    )

    assert plan.execution_profile == "mixed"
    assert len(plan.execution_epochs) == 3
    assert plan.current_epoch_node_ids == plan.execution_epochs[0].node_ids
    assert plan.requires_continuation


@pytest.mark.parametrize("profile", [None, True, 1, [], "adaptive"])
def test_plan_graph_rejects_nonexact_execution_profile(profile: object) -> None:
    with pytest.raises(ValueError, match="execution_profile must be exactly"):
        plan_graph((_review_requirement(1),), (_validation_requirement("V-baseline", baseline=True),), (_synthesis(),), execution_profile=cast("str", profile))


@pytest.mark.parametrize("profile", [None, True, 1, [], "adaptive"])
def test_graph_document_rejects_nonexact_execution_profile(profile: object) -> None:
    with pytest.raises(ValueError, match="execution_profile must be exactly"):
        plan_from_document({"execution_profile": profile})


def test_plan_rejects_missing_baseline_validation_before_dispatch() -> None:
    with pytest.raises(ValueError, match="at least one baseline validation unit"):
        plan_graph((_review_requirement(1),), (_validation_requirement("V-focused"),), (_synthesis(),))


def test_graph_document_rejects_selected_only_legacy_routing_without_fixture_escape_hatch() -> None:
    with pytest.raises(ValueError, match="exhaustive routing_decisions"):
        plan_from_document({"review_requirements": []})


@pytest.mark.parametrize("allow_legacy_fixture", [1, "false"])
def test_graph_document_rejects_non_boolean_legacy_fixture_escape_hatch(allow_legacy_fixture: object) -> None:
    with pytest.raises(ValueError, match="allow_legacy_fixture must be a boolean"):
        plan_from_document({"allow_legacy_fixture": allow_legacy_fixture, "review_requirements": []})


@pytest.mark.parametrize(
    ("contents", "expected_message"),
    [
        ("{", "Expecting property name enclosed in double quotes"),
        ("[]", "input root must be a JSON object"),
        ("{}", "graph documents require exhaustive routing_decisions"),
    ],
)
def test_main_reports_malformed_input_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str], contents: str, expected_message: str) -> None:
    input_path = tmp_path / "invalid.json"
    input_path.write_text(contents, encoding="utf-8")

    assert main(["--input", str(input_path)]) == 2

    stderr = capsys.readouterr().err
    assert f"review_graph_plan: {expected_message}" in stderr
    assert "Traceback" not in stderr


def test_main_reports_unreadable_input_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "missing.json"

    assert main(["--input", str(input_path)]) == 2

    stderr = capsys.readouterr().err
    assert "review_graph_plan:" in stderr
    assert str(input_path) in stderr
    assert "Traceback" not in stderr


def test_main_reports_undecodable_input_without_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = tmp_path / "invalid-utf8.json"
    input_path.write_bytes(b"\xff")

    assert main(["--input", str(input_path)]) == 2

    stderr = capsys.readouterr().err
    assert "review_graph_plan:" in stderr
    assert "utf-8" in stderr
    assert "Traceback" not in stderr


def test_main_preserves_successful_plan_output(capsys: pytest.CaptureFixture[str]) -> None:
    fixture = Path(__file__).with_name("fixtures") / "representative_rust_python_docs.json"

    assert main(["--input", str(fixture)]) == 0

    assert json.loads(capsys.readouterr().out)["dispatch_allowed"] is True


def test_main_does_not_swallow_unexpected_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    input_path = tmp_path / "valid.json"
    input_path.write_text("{}", encoding="utf-8")

    def raise_unexpected(_contents: str) -> object:
        message = "unexpected programmer failure"
        raise RuntimeError(message)

    monkeypatch.setattr(json, "loads", raise_unexpected)

    with pytest.raises(RuntimeError, match="unexpected programmer failure"):
        main(["--input", str(input_path)])


def test_repeated_validation_requirements_coalesce_and_reuse_mapping_is_complete() -> None:
    requirements = (
        _validation_requirement("V-rust", evidence_id="ledger-current-host"),
        _validation_requirement("V-python", evidence_id="ledger-current-host"),
        _validation_requirement("V-docs", evidence_id="ledger-current-host"),
    )

    units, mappings = coalesce_validation_requirements(requirements)

    assert len(units) == 1
    assert units[0].requirement_ids == ("V-docs", "V-python", "V-rust")
    assert units[0].evidence_ids == ("ledger-current-host",)
    assert {item.requirement_id for item in mappings} == {item.requirement_id for item in requirements}
    assert {item.validation_unit_id for item in mappings} == {"validation-001"}
    assert {item.evidence_id for item in mappings} == {"ledger-current-host"}


def test_review_coalescing_preserves_reasons_and_does_not_merge_distinct_owners() -> None:
    first = _review_requirement(1)
    second = replace(first, requirement_id="R02", reason="second routing reason")
    distinct_owner = replace(first, requirement_id="R03", owners=("documentation",))

    nodes, mappings = coalesce_review_requirements((first, second, distinct_owner))

    assert len(nodes) == 2
    merged = next(node for node in nodes if set(node.requirement_ids) == {"R01", "R02"})
    assert merged.selection_reasons == ("fixture surface owns this contract", "second routing reason")
    assert merged.owners == ()
    assert dict(mappings).keys() == {"R01", "R02", "R03"}


def test_budget_never_reclassifies_applicable_specialists_as_skips() -> None:
    requirements = tuple(_review_requirement(index) for index in range(1, 6))
    plan = plan_graph(
        requirements,
        (_validation_requirement("V-baseline", baseline=True),),
        (_synthesis(),),
        budget=WorkerBudget(total=4, recovery_finalization_reserve=1),
        execution_profile="isolated",
    )

    selected_requirements = {requirement for node in plan.actual_worker_nodes for requirement in node.requirement_ids if requirement.startswith("R")}
    assert selected_requirements == {item.requirement_id for item in requirements}
    assert plan.requires_continuation


def test_worker_creation_failure_halts_dispatch_and_emits_resume_manifest() -> None:
    planned_nodes = tuple(
        WorkerNode(
            node_id=node_id,
            skill_id="review-validator" if node_id == "V01" else "specialist",
            skill_path=f"/skills/{'review-validator' if node_id == 'V01' else 'specialist'}/SKILL.md",
            mode="validation" if node_id == "V01" else "audit",
            priority="required-validation" if node_id == "V01" else "supporting-quality",
            required=node_id == "V01",
            requirement_ids=(f"requirement-{node_id}",),
        )
        for node_id in ("A01", "A02", "V01", "S01")
    )
    manifest = stop_after_worker_creation_failure(
        CreationFailure(
            planned_nodes=planned_nodes,
            accepted_node_ids=("A01",),
            failed_node_id="A02",
            unaccepted_node_ids=(),
            source_state=("scope", "worktree", "repository"),
            journal_location="/artifacts/review-graph/journal.json",
        )
    )

    assert manifest.dispatch_halted
    assert tuple(node.node_id for node in manifest.undispatched_nodes) == ("A02", "V01", "S01")
    assert manifest.unaccepted_nodes == manifest.undispatched_nodes
    assert manifest.fresh_root_task_may_be_required
    assert manifest.journal_location == "/artifacts/review-graph/journal.json"


def _creation_failure(
    *, accepted_node_ids: tuple[str, ...] = ("A01",), unaccepted_node_ids: tuple[str, ...] = (), failed_node_id: str = "A02"
) -> CreationFailure:
    planned_nodes = tuple(
        WorkerNode(node_id=node_id, skill_id="specialist", skill_path="/skills/specialist/SKILL.md", mode="audit", priority="supporting-quality", required=True)
        for node_id in ("A01", "A02", "A03")
    )
    return CreationFailure(
        planned_nodes=planned_nodes,
        accepted_node_ids=accepted_node_ids,
        failed_node_id=failed_node_id,
        unaccepted_node_ids=unaccepted_node_ids,
        source_state=("scope", "worktree", "repository"),
    )


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (_creation_failure(accepted_node_ids=("unknown",)), "accepted nodes do not belong to the planned graph"),
        (_creation_failure(unaccepted_node_ids=("unknown",)), "unaccepted nodes do not belong to the planned graph"),
        (_creation_failure(accepted_node_ids=("A01", "A01")), "accepted node IDs must be unique"),
        (_creation_failure(unaccepted_node_ids=("A03", "A03")), "unaccepted node IDs must be unique"),
        (_creation_failure(unaccepted_node_ids=("A01",)), "accepted and unaccepted nodes must be disjoint"),
        (_creation_failure(accepted_node_ids=("A02",)), "failed node cannot be accepted"),
    ],
)
def test_worker_creation_failure_rejects_malformed_lifecycle_sets(failure: CreationFailure, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        stop_after_worker_creation_failure(failure)


def test_worker_creation_failure_always_accounts_for_the_failed_node() -> None:
    manifest = stop_after_worker_creation_failure(_creation_failure(unaccepted_node_ids=("A03",)))

    assert "A02" in {node.node_id for node in manifest.undispatched_nodes}
    assert "A02" in {node.node_id for node in manifest.unaccepted_nodes}


def test_incomplete_graph_cannot_report_completed_outcome() -> None:
    result = assess_completion(
        replace(
            _complete_evidence(execution_profile="grouped", isolation_failures=()),
            required_requirement_ids=("R01", "R02"),
            required_documentation_ids=("R-docs",),
            completed_documentation_ids=(),
            accepted_validation_node_ids=(),
            accepted_synthesis_node_ids=(),
            unaccepted_node_ids=("A02",),
            undispatched_node_ids=("validation-001", "repository-synthesis"),
            final_report_synthesized=False,
            findings_deduplicated=False,
        )
    )

    assert not result.feasible
    assert any("caller-supplied required review coverage" in blocker for blocker in result.blockers)
    assert any("undispatched nodes remain" in blocker for blocker in result.blockers)


def test_meaningful_skip_cannot_satisfy_an_applicable_requirement() -> None:
    result = assess_completion(
        replace(_complete_evidence(execution_profile="grouped", isolation_failures=()), completed_requirement_ids=(), meaningful_skip_requirement_ids=("R01",))
    )

    assert not result.feasible
    assert any("cannot complete through meaningful skips" in blocker for blocker in result.blockers)


def test_completion_api_has_no_caller_assertable_bundle_assessment() -> None:
    assert "repository_review_bundle" not in CompletionEvidence.__dataclass_fields__


def _complete_evidence(*, execution_profile: str, isolation_failures: tuple[str, ...], include_independent: bool = False) -> CompletionEvidence:
    expectation, proof, review_records, validation_records, manifest, verifier = _completion_binding(execution_profile, include_independent=include_independent)
    return CompletionEvidence(
        required_requirement_ids=("R01",),
        completed_requirement_ids=("R01",),
        meaningful_skip_requirement_ids=(),
        required_documentation_ids=(),
        completed_documentation_ids=(),
        required_validation_node_ids=("validation-001",),
        accepted_validation_node_ids=("validation-001",),
        required_synthesis_node_ids=("repository-synthesis",),
        accepted_synthesis_node_ids=("repository-synthesis",),
        unaccepted_node_ids=(),
        undispatched_node_ids=(),
        fingerprints_matched=True,
        execution_profile=execution_profile,
        isolation_failures=isolation_failures,
        final_report_synthesized=True,
        findings_deduplicated=True,
        repository_review_expectation=expectation,
        repository_review_proof=proof,
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_artifact_verifier=verifier,
        independent_review_required=include_independent,
        independent_review_accepted=include_independent,
    )


def test_grouped_pre_evidence_fallback_can_complete_with_retained_isolation_failure() -> None:
    evidence = _complete_evidence(execution_profile="grouped", isolation_failures=("worker creation failed before accepted evidence",))

    result = assess_completion(evidence)

    assert result.feasible
    assert evidence.isolation_failures == ("worker creation failed before accepted evidence",)


def test_mixed_post_evidence_fallback_can_complete_with_retained_isolation_failure() -> None:
    evidence = _complete_evidence(execution_profile="mixed", isolation_failures=("worker creation failed after accepted isolated evidence",))

    result = assess_completion(evidence)

    assert result.feasible
    assert evidence.isolation_failures == ("worker creation failed after accepted isolated evidence",)


def test_isolated_completion_rejects_retained_isolation_failure() -> None:
    result = assess_completion(_complete_evidence(execution_profile="isolated", isolation_failures=("worker creation failed",)))

    assert not result.feasible
    assert result.blockers == ("isolation failures occurred: worker creation failed",)


@pytest.mark.parametrize("profile", ["adaptive", "", cast("str", [])])
def test_completion_rejects_nonexact_execution_profile(profile: str) -> None:
    result = assess_completion(replace(_complete_evidence(execution_profile="grouped", isolation_failures=()), execution_profile=profile))

    assert not result.feasible
    assert "final execution profile must be exactly grouped, isolated, isolated-only, or mixed" in result.blockers


def test_completion_reverifies_missing_and_tampered_artifact_inputs() -> None:
    evidence = _complete_evidence(execution_profile="grouped", isolation_failures=())
    missing_manifest_entry = replace(evidence.artifact_manifest, entries=evidence.artifact_manifest.entries[:-1])
    first_payload = evidence.trusted_artifact_verifier.artifacts[0]
    tampered_verifier = replace(
        evidence.trusted_artifact_verifier, artifacts=(replace(first_payload, content=b"tampered"), *evidence.trusted_artifact_verifier.artifacts[1:])
    )

    missing = assess_completion(replace(evidence, artifact_manifest=missing_manifest_entry))
    tampered = assess_completion(replace(evidence, trusted_artifact_verifier=tampered_verifier))

    assert not missing.feasible
    assert any("artifact manifest does not cover accepted evidence exactly" in blocker for blocker in missing.blockers)
    assert not tampered.feasible
    assert any("artifact manifest artifact digest does not verify" in blocker for blocker in tampered.blockers)


@pytest.mark.parametrize(
    ("coverage_field", "expected_blocker"),
    [
        ("required_requirement_ids", "caller-supplied required review coverage"),
        ("required_validation_node_ids", "caller-supplied required validation coverage"),
        ("required_synthesis_node_ids", "caller-supplied required synthesis coverage"),
    ],
)
def test_completion_rejects_caller_favorable_coverage_omissions(coverage_field: str, expected_blocker: str) -> None:
    evidence = _complete_evidence(execution_profile="grouped", isolation_failures=())

    result = assess_completion(replace(evidence, **{coverage_field: ()}))

    assert not result.feasible
    assert any(expected_blocker in blocker for blocker in result.blockers)


def test_completion_derives_independent_review_coverage_from_the_bound_plan() -> None:
    evidence = _complete_evidence(execution_profile="grouped", isolation_failures=(), include_independent=True)

    result = assess_completion(replace(evidence, independent_review_required=False, independent_review_accepted=False))

    assert not result.feasible
    assert "caller-supplied independent-review requirement does not match the verified repository proof" in result.blockers
    assert "caller-supplied independent-review acceptance does not match the verified repository proof" in result.blockers


def _migration_trial(
    trial_id: str, mode: str, *, forced_worker_creation_failure: bool = False, forced_worker_skill_failure: bool = False, multi_epoch: bool = False
) -> MigrationTrial:
    return MigrationTrial(
        trial_id=trial_id,
        mode=mode,
        expected_applicable_skill_ids=("rust-test-quality",),
        observed_applicable_skill_ids=("rust-test-quality",),
        unexpected_skill_ids=(),
        expected_canonical_finding_ids=("finding-1",),
        observed_canonical_finding_ids=("finding-1", "valid-extra"),
        nodes_reconciled=True,
        validation_complete=True,
        synthesis_complete=True,
        fingerprints_matched=True,
        report_complete=True,
        accepted=True,
        recovery_completed=forced_worker_creation_failure or forced_worker_skill_failure,
        multi_epoch_completed=multi_epoch,
        runtime_artifact_id=f"artifact://{trial_id}",
        runtime_artifact_verified=True,
        runtime_artifact_verifier="forward-trial-recorder",
        workers_created=1,
        grouped_fallback_completed=forced_worker_creation_failure or forced_worker_skill_failure,
        worker_creation_failure_forced=forced_worker_creation_failure,
        worker_skill_load_or_execution_failure_forced=forced_worker_skill_failure,
    )


def test_migration_gate_requires_three_consecutive_modes_recovery_and_epochs() -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_creation_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )

    result = assess_migration_trials(trials)

    assert result.feasible


@pytest.mark.parametrize("value", [1, "complete"])
def test_migration_gate_rejects_malformed_multi_epoch_evidence(value: object) -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_creation_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )
    trials = tuple(replace(trial, multi_epoch_completed=cast("bool", value)) if trial.trial_id == "baseline-release-1" else trial for trial in trials)

    result = assess_migration_trials(trials)

    assert not result.feasible
    assert "no accepted multi-epoch fresh-root continuation trial completed" in result.blockers


def test_migration_gate_rejects_missing_applicable_skill_recall() -> None:
    trials = tuple(_migration_trial(f"branch-{ordinal}", "branch-read-only") for ordinal in range(1, 4))
    trials = (*trials, replace(_migration_trial("branch-failure", "branch-read-only"), observed_applicable_skill_ids=()))

    result = assess_migration_trials(trials)

    assert not result.feasible
    assert any("branch-read-only has 0 consecutive" in blocker for blocker in result.blockers)


def test_migration_gate_rejects_trials_without_runtime_evidence() -> None:
    trial = replace(
        _migration_trial("branch-1", "branch-read-only"),
        runtime_artifact_id=None,
        runtime_artifact_verified=False,
        runtime_artifact_verifier=None,
        workers_created=0,
    )

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any("has no runtime trial artifact" in blocker for blocker in result.blockers)
    assert any("created no runtime workers" in blocker for blocker in result.blockers)


def test_migration_gate_rejects_an_unverified_runtime_artifact() -> None:
    trial = replace(_migration_trial("branch-1", "branch-read-only"), runtime_artifact_verified=False, runtime_artifact_verifier=None)

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any("runtime trial artifact was not independently verified" in blocker for blocker in result.blockers)


@pytest.mark.parametrize(
    ("changes", "expected_blocker"),
    [
        ({"runtime_artifact_id": "  "}, "has no runtime trial artifact"),
        ({"runtime_artifact_verifier": "\t"}, "runtime trial artifact was not independently verified"),
        ({"runtime_artifact_verified": 1}, "runtime trial artifact was not independently verified"),
        ({"workers_created": True}, "has an invalid runtime worker count"),
        ({"workers_created": 1.5}, "has an invalid runtime worker count"),
    ],
)
def test_migration_gate_rejects_malformed_runtime_evidence(changes: dict[str, object], expected_blocker: str) -> None:
    trial = replace(_migration_trial("branch-1", "branch-read-only"), **changes)

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any(expected_blocker in blocker for blocker in result.blockers)


@pytest.mark.parametrize("value", [1, "complete"])
@pytest.mark.parametrize(
    ("field", "expected_blocker"),
    [
        ("nodes_reconciled", "failed node lifecycle"),
        ("validation_complete", "failed validation"),
        ("synthesis_complete", "failed synthesis"),
        ("fingerprints_matched", "failed fingerprints"),
        ("report_complete", "failed report"),
        ("accepted", "failed accepted outcome"),
    ],
)
def test_migration_gate_rejects_malformed_success_evidence(field: str, expected_blocker: str, value: object) -> None:
    trial = replace(_migration_trial("branch-1", "branch-read-only"), **{field: value})

    result = assess_migration_trials((trial,))

    assert not result.feasible
    assert any(expected_blocker in blocker for blocker in result.blockers)


def test_migration_gate_requires_explicit_forced_worker_creation_failure_evidence() -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_creation_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )
    trials = (replace(trials[0], worker_creation_failure_forced=False, worker_skill_load_or_execution_failure_forced=True), *trials[1:])

    result = assess_migration_trials(trials)

    assert not result.feasible
    assert "no accepted forced worker-creation failure trial completed grouped fallback" in result.blockers


@pytest.mark.parametrize(
    ("field", "value"),
    [("recovery_completed", 1), ("recovery_completed", "complete"), ("grouped_fallback_completed", 1), ("grouped_fallback_completed", "complete")],
)
def test_migration_gate_requires_exact_true_for_recovery_evidence(field: str, value: object) -> None:
    trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_creation_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )
    malformed_trial = replace(trials[0], **{field: value})

    result = assess_migration_trials((malformed_trial, *trials[1:]))

    assert not result.feasible
    assert "no accepted forced worker-creation failure trial completed grouped fallback" in result.blockers


def test_migration_gate_allows_a_recovered_trailing_streak() -> None:
    old_failure = replace(_migration_trial("old-failure", "branch-read-only"), observed_applicable_skill_ids=())
    recovered_trials = tuple(
        _migration_trial(
            f"{mode}-{ordinal}",
            mode,
            forced_worker_creation_failure=mode == "branch-read-only" and ordinal == 1,
            multi_epoch=mode == "baseline-release" and ordinal == 1,
        )
        for mode in ("branch-read-only", "baseline-release", "review-and-fix")
        for ordinal in range(1, 4)
    )

    result = assess_migration_trials((old_failure, *recovered_trials))

    assert result.feasible


def test_node_acceptance_requires_isolation_skill_reference_and_fingerprint_proof() -> None:
    expected = ("scope", "worktree", "repository")
    accepted = assess_node_acceptance(
        NodeAcceptanceEvidence(
            node_id="A01",
            worker_created=True,
            fresh_context=True,
            expected_skill_path="/skills/rust-scientific-correctness/SKILL.md",
            loaded_skill_path="/skills/rust-scientific-correctness/SKILL.md",
            required_static_references=("/skills/rust-review-orchestrator/references/la-stack.md",),
            loaded_static_references=("/skills/rust-review-orchestrator/references/la-stack.md",),
            fingerprints=FingerprintEvidence(expected=expected, before=expected, after=expected),
            report_complete=True,
            timed_out=True,
        )
    )
    rejected = assess_node_acceptance(
        NodeAcceptanceEvidence(
            node_id="A02",
            worker_created=True,
            fresh_context=False,
            expected_skill_path="/skills/rust-test-quality/SKILL.md",
            loaded_skill_path=None,
            required_static_references=("/skills/rust-review-orchestrator/references/la-stack.md",),
            loaded_static_references=(),
            fingerprints=FingerprintEvidence(expected=expected, before=expected, after=("scope", "changed", "repository")),
            report_complete=False,
        )
    )

    assert accepted.feasible
    assert not rejected.feasible
    assert len(rejected.blockers) == 5


def _review_evidence(*, profile: str = "grouped", execution_location: str = "coordinator") -> tuple[ReviewEvidenceExpectation, ReviewEvidence]:
    state = ("scope", "worktree", "repository")
    expectation = ReviewEvidenceExpectation(
        node_id="audit-001",
        requirement_ids=("R01",),
        skill_id="python-test-quality",
        mode="audit",
        skill_path="/skills/python-test-quality/SKILL.md",
        skill_digest="sha256:skill",
        reference_digests=(("/skills/python-test-quality/references/pytest.md", "sha256:reference"),),
        source_state=state,
        execution_profile=profile,
        selection_reason="fixture review requirement owns this contract",
        authorization="review-only",
    )
    evidence = ReviewEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id="review:audit-001:repository",
        node_id="audit-001",
        requirement_ids=("R01",),
        skill_id="python-test-quality",
        mode="audit",
        skill_path="/skills/python-test-quality/SKILL.md",
        skill_digest="sha256:skill",
        reference_digests=(("/skills/python-test-quality/references/pytest.md", "sha256:reference"),),
        fingerprints=FingerprintEvidence(expected=state, before=state, after=state),
        execution_profile=profile,
        execution_location=execution_location,
        worker_created=execution_location == "worker",
        fresh_context=execution_location == "worker",
        status="completed",
        finding_ids=("python-test-quality-1",),
        validation_requirement_ids=("V01",),
        handoff_ids=(),
        raw_result_artifact_id="artifact://audit-001",
        raw_result_digest=_result_digest("review:audit-001:repository"),
        report_complete=True,
    )
    return expectation, evidence


def _independent_review_evidence(
    *, status: str = "completed", finding_ids: tuple[str, ...] = ("independent-1", "independent-2"), handoff_ids: tuple[str, ...] = ()
) -> tuple[ReviewEvidenceExpectation, ReviewEvidence]:
    expectation, evidence = _review_evidence()
    expectation = replace(
        expectation,
        node_id="independent-001",
        skill_id="repository-independent-review",
        mode="independent-review",
        skill_path="/skills/repository-independent-review/SKILL.md",
        change_target="git diff origin/main...HEAD -- src/state.rs tests/state_test.py",
        planned_paths=("src/state.rs", "tests/state_test.py"),
        planned_path_line_bounds=(("src/state.rs", 120), ("tests/state_test.py", 80)),
    )
    evidence = replace(
        evidence,
        evidence_id="review:independent-001:repository",
        node_id=expectation.node_id,
        skill_id=expectation.skill_id,
        mode=expectation.mode,
        skill_path=expectation.skill_path,
        status=status,
        finding_ids=finding_ids,
        validation_requirement_ids=(),
        handoff_ids=handoff_ids,
        raw_result_artifact_id="artifact://independent-001",
    )
    return expectation, evidence


def test_adaptive_review_accepts_the_same_proof_from_coordinator_or_worker() -> None:
    coordinator_expectation, coordinator_evidence = _review_evidence()
    worker_expectation, worker_evidence = _review_evidence(execution_location="worker")

    coordinator = assess_review_evidence(coordinator_expectation, coordinator_evidence)
    worker = assess_review_evidence(worker_expectation, worker_evidence)

    assert coordinator.feasible
    assert coordinator.satisfies_requirements
    assert worker.feasible
    assert worker.satisfies_requirements


def test_isolated_review_rejects_coordinator_evidence() -> None:
    expectation, evidence = _review_evidence(profile="isolated")

    result = assess_review_evidence(expectation, evidence)

    assert not result.feasible
    assert not result.satisfies_requirements
    assert "isolated review evidence requires a fresh worker execution" in result.blockers


def test_review_evidence_cannot_be_reused_after_source_state_changes() -> None:
    expectation, evidence = _review_evidence()
    stale = replace(evidence, fingerprints=replace(evidence.fingerprints, after=("scope", "changed", "repository")))

    result = assess_review_evidence(expectation, stale)

    assert not result.feasible
    assert "review evidence after fingerprints do not match the expected source state" in result.blockers


def test_completed_independent_review_envelope_requires_a_finding() -> None:
    expectation, evidence = _review_evidence()
    expectation = replace(
        expectation,
        skill_id="repository-independent-review",
        mode="independent-review",
        skill_path="/skills/repository-independent-review/SKILL.md",
        change_target="git diff origin/main...HEAD -- src/state.rs",
        planned_paths=("src/state.rs",),
        planned_path_line_bounds=(("src/state.rs", 120),),
    )
    evidence = replace(evidence, skill_id=expectation.skill_id, mode=expectation.mode, skill_path=expectation.skill_path, status="completed", finding_ids=())

    completed = assess_review_evidence(expectation, evidence)
    no_findings = assess_review_evidence(expectation, replace(evidence, status="no-findings"))
    blocked = assess_review_evidence(expectation, replace(evidence, status="blocked"))

    assert not completed.feasible
    assert not completed.satisfies_requirements
    assert "completed independent-review evidence must contain at least one finding ID" in completed.blockers
    assert no_findings.feasible
    assert no_findings.satisfies_requirements
    assert blocked.feasible
    assert not blocked.satisfies_requirements


def test_independent_native_result_accepts_reconciled_completed_no_findings_and_blocked_sections() -> None:
    completed_expectation, completed = _independent_review_evidence()
    no_findings_expectation, no_findings = _independent_review_evidence(status="no-findings", finding_ids=())
    blocked_expectation, blocked = _independent_review_evidence(status="blocked", finding_ids=())
    handoff_expectation, handoff = _independent_review_evidence(handoff_ids=("independent-001-handoff-1",))

    assert not _review_native_result_blockers(_review_result_payload(completed_expectation, completed), completed_expectation, completed)
    assert not _review_native_result_blockers(_review_result_payload(no_findings_expectation, no_findings), no_findings_expectation, no_findings)
    assert not _review_native_result_blockers(_review_result_payload(blocked_expectation, blocked), blocked_expectation, blocked)
    assert not _review_native_result_blockers(_review_result_payload(handoff_expectation, handoff), handoff_expectation, handoff)


def test_review_and_validation_native_headers_are_exact_and_dispatch_bound() -> None:
    review_expectation, review_evidence = _review_evidence()
    review_content = _review_result_payload(review_expectation, review_evidence)
    review_header = _review_header(review_expectation, review_evidence)
    review_variants = (
        _replace_native_preamble(review_content, "## Skill Loading", ""),
        _replace_native_preamble(review_content, "## Skill Loading", review_header.replace("- Node ID: audit-001", "", 1)),
        _replace_native_preamble(
            review_content, "## Skill Loading", review_header.replace("- Node ID: audit-001", "- Node ID: audit-001\n- Node ID: audit-001", 1)
        ),
        _replace_native_preamble(review_content, "## Skill Loading", review_header.replace("- Execution profile: grouped", "- Execution profile: isolated", 1)),
        _replace_native_preamble(review_content, "## Skill Loading", review_header.replace("- Status: completed", "- Status: blocked", 1)),
        _replace_native_preamble(review_content, "## Skill Loading", review_header.replace("- Scope fingerprint: scope", "- Scope fingerprint: wrong", 1)),
    )
    validation_expectation, validation_evidence = _validation_evidence()
    validation_content = _validation_result_payload(validation_expectation, validation_evidence)
    validation_header = _validation_header(validation_evidence)
    validation_variants = (
        _replace_native_preamble(validation_content, "## Outcome Summary", ""),
        _replace_native_preamble(validation_content, "## Outcome Summary", validation_header.replace("- Node ID: validation-001", "", 1)),
        _replace_native_preamble(
            validation_content, "## Outcome Summary", validation_header.replace("- Status: passed", "- Status: passed\n- Status: passed", 1)
        ),
        _replace_native_preamble(
            validation_content, "## Outcome Summary", validation_header.replace("- Execution location: coordinator", "- Execution location: worker", 1)
        ),
        _replace_native_preamble(validation_content, "## Outcome Summary", validation_header.replace("- Status: passed", "- Status: failed", 1)),
        _replace_native_preamble(
            validation_content,
            "## Outcome Summary",
            validation_header.replace("- Repository state fingerprint: repository", "- Repository state fingerprint: wrong", 1),
        ),
    )

    review_blockers = tuple(_review_native_result_blockers(content, review_expectation, review_evidence) for content in review_variants)
    validation_blockers = tuple(_validation_native_result_blockers(content, validation_expectation, validation_evidence) for content in validation_variants)

    assert all(any("header" in blocker for blocker in blockers) for blockers in review_blockers)
    assert all(any("header" in blocker for blocker in blockers) for blockers in validation_blockers)


def test_ordinary_review_skill_loading_binds_exact_reference_provenance() -> None:
    expectation, evidence = _review_evidence()
    content = _review_result_payload(expectation, evidence)
    reference_path, reference_digest = expectation.reference_digests[0]
    variants = (
        content.replace(f"- References loaded: {reference_path}\n".encode(), b"", 1),
        content.replace(f"- References loaded: {reference_path}".encode(), b"- References loaded: /forged/ref.md", 1),
        content.replace(f"- Reference digests: {reference_path}={reference_digest}".encode(), b"- Reference digests: /forged/ref.md=sha256:forged", 1),
        content.replace(
            f"- References loaded: {reference_path}".encode(), f"- References loaded: {reference_path}\n- References loaded: {reference_path}".encode(), 1
        ),
        content.replace(
            f"- References loaded: {reference_path}\n- Reference digests: {reference_path}={reference_digest}".encode(),
            f"- Reference digests: {reference_path}={reference_digest}\n- References loaded: {reference_path}".encode(),
            1,
        ),
    )

    blockers = tuple(_review_native_result_blockers(variant, expectation, evidence) for variant in variants)

    assert all(any("Review Skill Loading" in blocker for blocker in result) for result in blockers)


def test_completed_independent_native_findings_require_complete_bounded_records() -> None:
    expectation, evidence = _independent_review_evidence()
    content = _review_result_payload(expectation, evidence)
    id_only = _replace_native_section(content, "## Findings", "## No-Finding Evidence", "\n".join(f"- ID: {finding_id}" for finding_id in evidence.finding_ids))
    missing_fields = tuple(
        _replace_in_native_section(content, "## Findings", "## No-Finding Evidence", f"  - {label}: ", "  - Omitted: ")
        for label in ("Severity", "Location", "Summary", "Evidence", "Impact", "Owner", "Remediation")
    )
    duplicated_summary = _replace_in_native_section(
        content,
        "## Findings",
        "## No-Finding Evidence",
        "  - Summary: observed contract violation",
        "  - Summary: observed contract violation\n  - Summary: duplicate",
    )
    invalid_severity = _replace_in_native_section(content, "## Findings", "## No-Finding Evidence", "  - Severity: P1", "  - Severity: critical")
    invalid_location = _replace_in_native_section(
        content, "## Findings", "## No-Finding Evidence", "  - Location: src/state.rs:1", "  - Location: ../outside.py:0-0"
    )

    blockers = tuple(
        _review_native_result_blockers(variant, expectation, evidence)
        for variant in (id_only, *missing_fields, duplicated_summary, invalid_severity, invalid_location)
    )

    assert all(result for result in blockers)
    assert any("fields are incomplete" in blocker for blocker in blockers[0])
    assert all(any("Finding" in blocker for blocker in result) for result in blockers[1:])


def test_independent_native_finding_locations_use_trusted_line_bounds() -> None:
    expectation, evidence = _independent_review_evidence()
    content = _review_result_payload(expectation, evidence)
    path_only = content.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs", 1)
    at_bound = content.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs:120", 1)
    past_bound = content.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs:121", 1)
    impossible = content.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs:999999999", 1)
    range_past_bound = content.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs:119-121", 1)

    assert not _review_native_result_blockers(path_only, expectation, evidence)
    assert not _review_native_result_blockers(at_bound, expectation, evidence)
    for forged in (past_bound, impossible, range_past_bound):
        blockers = _review_native_result_blockers(forged, expectation, evidence)
        assert any("trusted dispatched path line bounds" in blocker for blocker in blockers)

    deleted_expectation, deleted_evidence = _independent_review_evidence(finding_ids=("independent-1",))
    deleted_expectation = replace(deleted_expectation, planned_paths=("src/state.rs",), planned_path_line_bounds=(("src/state.rs", 40),))
    deleted_content = _review_result_payload(deleted_expectation, deleted_evidence).replace(
        b"  - Location: src/state.rs:1", b"  - Location: src/state.rs:40", 1
    )
    assert not _review_native_result_blockers(deleted_content, deleted_expectation, deleted_evidence)

    repository_expectation = replace(deleted_expectation, planned_path_line_bounds=(("src/state.rs", 0),))
    repository_content = _review_result_payload(repository_expectation, deleted_evidence)
    path_only_repository = repository_content.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs", 1)
    assert not _review_native_result_blockers(path_only_repository, repository_expectation, deleted_evidence)
    assert _review_native_result_blockers(repository_content, repository_expectation, deleted_evidence)


@pytest.mark.parametrize(
    ("section", "next_section", "old", "new", "expected_blocker"),
    [
        ("## Findings", "## No-Finding Evidence", "- ID: independent-2", "- ID: wrong-finding", "finding IDs"),
        ("## Findings", "## No-Finding Evidence", "- ID: independent-1", "- ID: independent-2", "finding IDs"),
        ("## Fingerprint Proof", "## Git State", "  - Scope fingerprint: scope", "  - Scope fingerprint: wrong", "Fingerprint Proof"),
        ("## Git State", "## Review Graph Envelope", "- Git state mutated: no", "- Git state mutated: yes", "Git State"),
        ("## Review Graph Envelope", "## Machine Evidence", "- Node ID: independent-001", "- Node ID: wrong-node", "Review Graph Envelope"),
    ],
)
def test_independent_native_result_rejects_semantic_section_mismatches(section: str, next_section: str, old: str, new: str, expected_blocker: str) -> None:
    expectation, evidence = _independent_review_evidence()
    content = _review_result_payload(expectation, evidence)
    text = content.decode()
    section_start = text.index(section)
    section_end = text.index(next_section, section_start)
    changed_section = text[section_start:section_end].replace(old, new, 1)
    changed = f"{text[:section_start]}{changed_section}{text[section_end:]}".encode()

    blockers = _review_native_result_blockers(changed, expectation, evidence)

    assert any(expected_blocker in blocker for blocker in blockers)


def test_independent_native_result_rejects_target_path_result_handoff_and_limitation_contradictions() -> None:
    expectation, evidence = _independent_review_evidence()
    content = _review_result_payload(expectation, evidence)
    unrelated_target = _replace_in_native_section(
        _replace_in_native_section(content, "## Scope Inspected", "## Findings", expectation.change_target or "", "git diff -- unrelated.txt"),
        "## Review Graph Envelope",
        "## Machine Evidence",
        expectation.change_target or "",
        "git diff -- unrelated.txt",
    )
    path_variants = tuple(
        _replace_in_native_section(
            _replace_in_native_section(content, "## Scope Inspected", "## Findings", "src/state.rs, tests/state_test.py", replacement),
            "## Review Graph Envelope",
            "## Machine Evidence",
            "src/state.rs, tests/state_test.py",
            replacement,
        )
        for replacement in ("src/state.rs", "src/state.rs, tests/state_test.py, unrelated.txt", "tests/state_test.py, src/state.rs")
    )
    mismatched_results = _replace_in_native_section(content, "## Review Graph Envelope", "## Machine Evidence", "  - Result: matched", "  - Result: mismatched")
    mismatched_results = _replace_in_native_section(
        mismatched_results, "## Review Graph Envelope", "## Machine Evidence", "  - Result: matched", "  - Result: mismatched"
    )
    extra_handoff = _replace_native_section(content, "## Routing Handoffs", "## Fingerprint Proof", "- Handoff ID: independent-001-handoff-extra")
    contradictory_limitation = _replace_in_native_section(
        content, "## Review Graph Envelope", "## Machine Evidence", "- Limitations: none", "- Limitations: target was not inspected"
    )

    blockers = tuple(
        _review_native_result_blockers(variant, expectation, evidence)
        for variant in (unrelated_target, *path_variants, mismatched_results, extra_handoff, contradictory_limitation)
    )

    assert all(result for result in blockers)
    assert any("Change target" in blocker for blocker in blockers[0])
    assert all(any("Files" in blocker for blocker in result) for result in blockers[1:4])
    assert any("dispositions" in blocker for blocker in blockers[4])
    assert any("Routing Handoffs" in blocker for blocker in blockers[5])
    assert any("limitations" in blocker for blocker in blockers[6])


def test_independent_native_machine_evidence_binds_target_paths_and_handoffs() -> None:
    expectation, evidence = _independent_review_evidence(handoff_ids=("independent-001-handoff-1",))
    content = _review_result_payload(expectation, evidence)
    text = content.decode()
    start = text.index(NATIVE_EVIDENCE_BLOCK_OPEN) + len(NATIVE_EVIDENCE_BLOCK_OPEN)
    end = text.index(NATIVE_EVIDENCE_BLOCK_CLOSE, start)
    payload = json.loads(text[start:end])
    variants = []
    for field, value in (("change_target", "git diff -- unrelated.txt"), ("inspected_paths", ["unrelated.txt"]), ("handoff_ids", [])):
        changed_payload = {**payload, field: value}
        variants.append(_replace_native_block(content, json.dumps(changed_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)))

    blockers = tuple(_review_native_result_blockers(variant, expectation, evidence) for variant in variants)

    assert all(result for result in blockers)
    assert any("change_target" in blocker for blocker in blockers[0])
    assert any("inspected_paths" in blocker for blocker in blockers[1])
    assert any("handoff_ids" in blocker for blocker in blockers[2])


def test_independent_native_result_rejects_an_omitted_typed_handoff() -> None:
    expectation, evidence = _independent_review_evidence(handoff_ids=("independent-001-handoff-1",))
    content = _review_result_payload(expectation, evidence)
    omitted = _replace_native_section(content, "## Routing Handoffs", "## Fingerprint Proof", "none")

    blockers = _review_native_result_blockers(omitted, expectation, evidence)

    assert any("routing handoff IDs" in blocker for blocker in blockers)


def test_independent_native_result_rejects_all_none_and_unexpected_level_two_sections() -> None:
    expectation, evidence = _independent_review_evidence()
    content = _review_result_payload(expectation, evidence)
    sections = (
        "## Scope Inspected",
        "## Findings",
        "## No-Finding Evidence",
        "## Routing Handoffs",
        "## Fingerprint Proof",
        "## Git State",
        "## Review Graph Envelope",
        "## Machine Evidence",
    )
    all_none = _all_none_native_sections(content, sections)
    extra_section = content.replace(b"## Findings\n", b"## Unexpected\n\nprose\n\n## Findings\n", 1)

    all_none_blockers = _review_native_result_blockers(all_none, expectation, evidence)
    extra_section_blockers = _review_native_result_blockers(extra_section, expectation, evidence)

    assert any("must contain concrete evidence" in blocker for blocker in all_none_blockers)
    assert any("unexpected level-two sections" in blocker for blocker in extra_section_blockers)


def _validation_evidence(unit: ValidationUnit | None = None) -> tuple[ValidationEvidenceExpectation, ValidationEvidence]:
    state = ("scope", "worktree", "repository")
    if unit is None:
        (unit,), _ = coalesce_validation_requirements((_validation_requirement("V01"), _validation_requirement("V02")))
    expectation = validation_evidence_expectation(
        unit,
        skill_path="/skills/review-validator/SKILL.md",
        skill_digest="sha256:review-validator",
        reference_digests=(("/skills/review-validator/references/result-contract.md", "sha256:reference"),),
        execution_profile="grouped",
        execution_location="coordinator",
    )
    evidence = ValidationEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id="review-validator:validation-001:repository",
        node_id="validation-001",
        requirement_ids=unit.requirement_ids,
        skill_digest="sha256:review-validator",
        reference_digests=(("/skills/review-validator/references/result-contract.md", "sha256:reference"),),
        fingerprints=FingerprintEvidence(expected=state, before=state, after=state),
        execution_profile="grouped",
        execution_location="coordinator",
        worker_created=False,
        fresh_context=False,
        status="passed",
        command_identity_digest=validation_command_identity_digest(unit),
        environment_digest=validation_environment_digest(unit),
        raw_result_artifact_id="artifact://validation-001",
        raw_result_digest=_result_digest("review-validator:validation-001:repository"),
    )
    return expectation, evidence


def test_ordinary_review_native_result_rejects_all_none_and_state_contradictions() -> None:
    expectation, evidence = _review_evidence()
    content = _review_result_payload(expectation, evidence)
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
    all_none = _all_none_native_sections(content, sections)
    wrong_state = content.replace(b"  - Observed scope fingerprint: scope", b"  - Observed scope fingerprint: wrong", 1)

    all_none_blockers = _review_native_result_blockers(all_none, expectation, evidence)
    wrong_state_blockers = _review_native_result_blockers(wrong_state, expectation, evidence)

    assert any("Skill Loading" in blocker for blocker in all_none_blockers)
    assert any("State Verification" in blocker for blocker in wrong_state_blockers)


def test_completed_ordinary_native_findings_require_complete_records() -> None:
    expectation, evidence = _review_evidence()
    content = _review_result_payload(expectation, evidence)
    id_only = _replace_native_section(content, "## Findings", "## Validation", f"- ID: {evidence.finding_ids[0]}")
    missing_fields = tuple(
        _replace_in_native_section(content, "## Findings", "## Validation", f"  - {label}: ", "  - Omitted: ")
        for label in ("Severity", "Location", "Summary", "Evidence", "Remediation")
    )
    duplicated_summary = _replace_in_native_section(
        content, "## Findings", "## Validation", "  - Summary: observed contract violation", "  - Summary: observed contract violation\n  - Summary: duplicate"
    )
    invalid_severity = _replace_in_native_section(content, "## Findings", "## Validation", "  - Severity: P1", "  - Severity: critical")
    nonconcrete = _replace_in_native_section(content, "## Findings", "## Validation", "  - Evidence: observed contract violation", "  - Evidence: none")

    blockers = tuple(
        _review_native_result_blockers(variant, expectation, evidence)
        for variant in (id_only, *missing_fields, duplicated_summary, invalid_severity, nonconcrete)
    )

    assert all(result for result in blockers)
    assert all(any("Finding" in blocker for blocker in result) for result in blockers)


def test_fix_native_result_binds_changed_paths_and_records_to_planner_authorization() -> None:
    expectation, evidence = _review_evidence()
    after_state = ("scope-after", "worktree-after", "repository-after")
    expectation = replace(
        expectation,
        mode="fix",
        authorization="review-and-fix",
        expected_after_state=after_state,
        source_mutation_allowed=True,
        planned_paths=("src/authorized.py",),
    )
    evidence = replace(evidence, mode="fix", fingerprints=replace(evidence.fingerprints, after=after_state), source_mutated=True)
    content = _review_result_payload(expectation, evidence)
    unauthorized = content.replace(b"src/authorized.py", b"src/unrelated.py")
    mismatched_changes = _replace_in_native_section(content, "## Changes", "## Handoffs", "  - Files: src/authorized.py", "  - Files: src/other-authorized.py")

    assessment = assess_review_evidence(expectation, evidence)
    accepted_blockers = _review_native_result_blockers(content, expectation, evidence)
    unauthorized_blockers = _review_native_result_blockers(unauthorized, expectation, evidence)
    mismatched_blockers = _review_native_result_blockers(mismatched_changes, expectation, evidence)

    assert assessment.feasible
    assert assessment.satisfies_requirements
    assert not accepted_blockers
    assert any("outside planner authorization" in blocker for blocker in unauthorized_blockers)
    assert any("Changes files do not match" in blocker for blocker in mismatched_blockers)


def test_fix_evidence_requires_planner_authorized_paths() -> None:
    expectation, evidence = _review_evidence()
    expectation = replace(expectation, mode="fix", authorization="review-and-fix")
    evidence = replace(evidence, mode="fix")

    result = assess_review_evidence(expectation, evidence)

    assert not result.feasible
    assert "fix evidence expectation has no planned paths" in result.blockers


def test_validation_native_result_reconciles_outcomes_counts_and_executions() -> None:
    expectation, evidence = _validation_evidence()
    content = _validation_result_payload(expectation, evidence)
    assert not _validation_native_result_blockers(content, expectation, evidence)

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
    variants = (
        _all_none_native_sections(content, sections),
        _replace_in_native_section(content, "## Outcome Summary", "## Skill Loading", "- Requirements: passed 2", "- Requirements: passed 1"),
        _replace_in_native_section(content, "## Executions", "## Reused Evidence", "  - Result: passed", "  - Result: failed"),
        _replace_in_native_section(content, "## Executions", "## Reused Evidence", "  - Command: just ci", "  - Command: just wrong"),
    )

    blockers = tuple(_validation_native_result_blockers(variant, expectation, evidence) for variant in variants)

    assert any("Outcome Summary" in blocker for blocker in blockers[0])
    assert any("Outcome Summary Requirements" in blocker for blocker in blockers[1])
    assert any("passed status contradicts" in blocker for blocker in blockers[2])
    assert any("exact dispatched commands" in blocker for blocker in blockers[3])


def test_validation_native_plan_and_requirements_are_complete_and_dispatch_bound() -> None:
    expectation, evidence = _validation_evidence()
    content = _validation_result_payload(expectation, evidence)
    plan = _validation_plan_expected_body(expectation)
    required_plan_lines = (
        f"- Request: {expectation.validation_unit.request}",
        f"- Requested scope: {expectation.validation_unit.requested_scope}",
        f"- Capture command: {expectation.validation_unit.capture_command}",
        "- Captured paths: none",
        "- Authorities inspected: graph dispatch",
        "  - Authority: graph dispatch",
        "  - Selection reason: graph-dispatched validation requirement",
        '  - Command: ["just ci"]',
        '  - Working directory: ["/repo"]',
        f"  - Configuration: {_validation_environment_identity(expectation.validation_unit)}",
        "  - Mutation classification: non-mutating under validation-only",
        "  - Expected evidence: exact dispatched commands complete with recorded outcomes",
        "  - Budget: 300s",
        f"- Coalescing basis: {_validation_coalescing_identity(expectation.validation_unit)}",
        f"- Command identity digest: {expectation.command_identity_digest}",
        f"- Environment digest: {expectation.environment_digest}",
        "- Requirement-to-evidence mapping:",
        "  - V01: validation-001; none",
        "- Meaningful skips: none",
        "- Execution strategy: sequential",
        "- Dependency policy: stop-on-failure",
        "- Independence basis: none",
        "- Planning blocker: none",
    )
    assert all(line in plan.splitlines() for line in required_plan_lines)

    plan_variants = tuple(
        _replace_in_native_section(content, "## Validation Plan", "## State Verification", line, "- Omitted: forged") for line in required_plan_lines
    )
    missing_evidence = _replace_in_native_section(
        content, "## Requirements", "## Executions", "  - Evidence: validation-001-exec-1", "  - Omitted: validation-001-exec-1"
    )
    mismatched_evidence = _replace_in_native_section(
        content, "## Requirements", "## Executions", "  - Evidence: validation-001-exec-1", "  - Evidence: forged-execution"
    )

    blockers = tuple(_validation_native_result_blockers(variant, expectation, evidence) for variant in (*plan_variants, missing_evidence, mismatched_evidence))

    assert all(result for result in blockers)
    assert all(any("Validation Plan" in blocker for blocker in result) for result in blockers[: len(plan_variants)])
    assert all(any("Requirements" in blocker for blocker in result) for result in blockers[len(plan_variants) :])


def test_validation_native_execution_requires_complete_dispatch_bound_evidence() -> None:
    expectation, evidence = _validation_evidence()
    content = _validation_result_payload(expectation, evidence)
    minimal = _replace_native_section(
        content, "## Executions", "## Reused Evidence", "- Execution ID: validation-001-exec-1\n  - Command: just ci\n  - Result: passed"
    )
    missing_fields = tuple(
        _replace_in_native_section(content, "## Executions", "## Reused Evidence", f"  - {label}: ", "  - Omitted: ")
        for label in ("Executor", "Working directory", "Environment/configuration", "Exit code", "Elapsed", "Evidence", "Log or artifact")
    )
    duplicated_executor = _replace_in_native_section(
        content, "## Executions", "## Reused Evidence", "  - Executor: parent", "  - Executor: parent\n  - Executor: duplicate"
    )
    wrong_working_directory = _replace_in_native_section(
        content, "## Executions", "## Reused Evidence", "  - Working directory: /repo", "  - Working directory: /tmp"
    )
    expected_environment = _validation_environment_identity(expectation.validation_unit)
    wrong_environment = _replace_in_native_section(
        content, "## Executions", "## Reused Evidence", f"  - Environment/configuration: {expected_environment}", "  - Environment/configuration: forged"
    )
    nonzero_pass = _replace_in_native_section(content, "## Executions", "## Reused Evidence", "  - Exit code: 0", "  - Exit code: 1")
    empty_evidence = _replace_in_native_section(content, "## Executions", "## Reused Evidence", "  - Evidence: fixture command evidence", "  - Evidence: none")

    blockers = tuple(
        _validation_native_result_blockers(variant, expectation, evidence)
        for variant in (minimal, *missing_fields, duplicated_executor, wrong_working_directory, wrong_environment, nonzero_pass, empty_evidence)
    )

    assert all(result for result in blockers)
    assert any("fields are incomplete" in blocker for blocker in blockers[0])
    assert all(any("Execution" in blocker for blocker in result) for result in blockers[1:])


def test_validation_native_provenance_artifacts_and_ledger_are_dispatch_bound() -> None:
    expectation, evidence = _validation_evidence()
    content = _validation_result_payload(expectation, evidence)
    reference_path, reference_digest = expectation.reference_digests[0]
    forged = (
        content.replace(f"- Skill file: {expectation.skill_path}".encode(), b"- Skill file: /forged/skill.md", 1)
        .replace(f"- References loaded: {reference_path}".encode(), b"- References loaded: /forged/reference.md", 1)
        .replace(f"- Reference digests: {reference_path}={reference_digest}".encode(), b"- Reference digests: /forged/reference.md=sha256:forged", 1)
        .replace(b"## Artifacts\n\nnone", b"## Artifacts\n\n- Path: source-controlled.txt\n  - Kind: log\n  - Repository status: tracked", 1)
        .replace(b"- Consumer: review-graph", b"- Consumer: attacker", 1)
    )

    blockers = _validation_native_result_blockers(forged, expectation, evidence)

    assert any("Validation Skill Loading" in blocker for blocker in blockers)
    assert any("claims artifacts absent from its dispatch" in blocker for blocker in blockers)
    assert any("Validation Ledger Export" in blocker for blocker in blockers)

    external_unit = replace(
        expectation.validation_unit,
        artifact_owner="external",
        allowed_artifacts=(ValidationArtifact(path="/external/review-validator/command.log", kind="log", repository_status="outside-repository"),),
    )
    external_expectation = validation_evidence_expectation(
        external_unit,
        skill_path=expectation.skill_path,
        skill_digest=expectation.skill_digest,
        reference_digests=expectation.reference_digests,
        execution_profile=expectation.execution_profile,
        execution_location=expectation.execution_location,
    )
    external_evidence = replace(evidence, environment_digest=external_expectation.environment_digest)
    external_content = _validation_result_payload(external_expectation, external_evidence)
    assert b"  - Artifact digest: none" in external_content
    assert any(
        "requires a lowercase SHA-256 content digest" in blocker
        for blocker in _validation_native_result_blockers(external_content, external_expectation, external_evidence)
    )

    unapproved_external = external_content.replace(b"- Path: /external/review-validator/command.log", b"- Path: /external/review-validator/unapproved.log", 1)
    assert any(
        "artifact paths do not match its dispatch" in blocker
        for blocker in _validation_native_result_blockers(unapproved_external, external_expectation, external_evidence)
    )


def test_validation_native_artifact_references_require_matching_content_identity() -> None:
    expectation, evidence = _validation_evidence()
    artifact_digest = "sha256:" + "a" * 64
    unit = replace(
        expectation.validation_unit,
        artifact_owner="external",
        allowed_artifacts=(
            ValidationArtifact(
                path="/external/review-validator/command.log",
                artifact_id="artifact://command-log",
                artifact_digest=artifact_digest,
                kind="log",
                repository_status="outside-repository",
            ),
        ),
    )
    expectation = validation_evidence_expectation(
        unit,
        skill_path=expectation.skill_path,
        skill_digest=expectation.skill_digest,
        reference_digests=expectation.reference_digests,
        execution_profile=expectation.execution_profile,
        execution_location=expectation.execution_location,
    )
    evidence = replace(evidence, environment_digest=expectation.environment_digest)
    reference = json.dumps(
        [{"path": "/external/review-validator/command.log", "artifact_id": "artifact://command-log", "artifact_digest": artifact_digest}],
        sort_keys=True,
        separators=(",", ":"),
    )
    content = _validation_result_payload(expectation, evidence).replace(b"  - Log or artifact: none", f"  - Log or artifact: {reference}".encode(), 1)

    assert not _validation_native_result_blockers(content, expectation, evidence)

    mismatched_digest = "sha256:" + "b" * 64
    mismatched_reference_value = reference.replace(artifact_digest, mismatched_digest)
    mismatched_reference = _replace_in_native_section(
        content, "## Executions", "## Reused Evidence", f"  - Log or artifact: {reference}", f"  - Log or artifact: {mismatched_reference_value}"
    )
    mismatched_artifact = _replace_in_native_section(content, "## Artifacts", "## Source And Git State", artifact_digest, mismatched_digest)
    mismatched_artifact_id = _replace_in_native_section(
        content, "## Artifacts", "## Source And Git State", "  - Artifact ID: artifact://command-log", "  - Artifact ID: artifact://other-log"
    )
    missing_artifact_digest = _replace_in_native_section(
        content, "## Artifacts", "## Source And Git State", f"  - Artifact digest: {artifact_digest}", "  - Artifact digest: none"
    )
    unstructured_reference = _replace_in_native_section(
        content, "## Executions", "## Reused Evidence", f"  - Log or artifact: {reference}", "  - Log or artifact: /external/review-validator/command.log"
    )

    assert any("artifact reference does not match" in blocker for blocker in _validation_native_result_blockers(mismatched_reference, expectation, evidence))
    assert any("approved content digest" in blocker for blocker in _validation_native_result_blockers(mismatched_artifact, expectation, evidence))
    assert any("approved artifact ID" in blocker for blocker in _validation_native_result_blockers(mismatched_artifact_id, expectation, evidence))
    assert any("requires a lowercase SHA-256" in blocker for blocker in _validation_native_result_blockers(missing_artifact_digest, expectation, evidence))
    assert any(
        "artifact references are not valid JSON" in blocker for blocker in _validation_native_result_blockers(unstructured_reference, expectation, evidence)
    )


def test_validation_native_complete_plan_preserves_blocked_reused_and_not_applicable_modes() -> None:
    expectation, evidence = _validation_evidence()
    blocked = replace(evidence, status="blocked")
    assert not _validation_native_result_blockers(_validation_result_payload(expectation, blocked), expectation, blocked)

    reused_plans = tuple((*record[:-1], "ledger:exact") for record in expectation.validation_unit.requirement_plans)
    reused_unit = replace(expectation.validation_unit, evidence_ids=("ledger:exact",), requirement_plans=reused_plans)
    reused_expectation = validation_evidence_expectation(
        reused_unit,
        skill_path=expectation.skill_path,
        skill_digest=expectation.skill_digest,
        reference_digests=expectation.reference_digests,
        execution_profile=expectation.execution_profile,
        execution_location=expectation.execution_location,
    )
    reused = replace(
        evidence, status="reused", command_identity_digest=reused_expectation.command_identity_digest, environment_digest=reused_expectation.environment_digest
    )
    assert not _validation_native_result_blockers(_validation_result_payload(reused_expectation, reused), reused_expectation, reused)

    empty_unit = replace(
        expectation.validation_unit,
        requirement_ids=(),
        requirement_plans=(),
        commands=(),
        working_directories=(),
        evidence_ids=(),
        required=False,
        baseline=False,
    )
    empty_expectation = validation_evidence_expectation(
        empty_unit,
        skill_path=expectation.skill_path,
        skill_digest=expectation.skill_digest,
        reference_digests=expectation.reference_digests,
        execution_profile=expectation.execution_profile,
        execution_location=expectation.execution_location,
    )
    not_applicable = replace(
        evidence,
        requirement_ids=(),
        status="not-applicable",
        command_identity_digest=empty_expectation.command_identity_digest,
        environment_digest=empty_expectation.environment_digest,
    )
    assert not _validation_native_result_blockers(_validation_result_payload(empty_expectation, not_applicable), empty_expectation, not_applicable)


def test_reused_validation_ledger_binds_each_entry_to_its_mapped_requirements() -> None:
    (unit,), _ = coalesce_validation_requirements(
        (_validation_requirement("V01", evidence_id="ledger:a"), _validation_requirement("V02", evidence_id="ledger:b"))
    )
    expectation, evidence = _validation_evidence(unit)
    evidence = replace(evidence, status="reused")
    content = _validation_result_payload(expectation, evidence)
    forged = _replace_in_native_section(content, "## Reused Evidence", "## Artifacts", "  - Requirement IDs: V01", "  - Requirement IDs: V01, V02")

    assert not _validation_native_result_blockers(content, expectation, evidence)
    blockers = _validation_native_result_blockers(forged, expectation, evidence)
    assert any("ledger entry ledger:a does not match its dispatch identity" in blocker for blocker in blockers)


@pytest.mark.parametrize("dependency_policy", ["stop-on-failure", "continue-independent"])
def test_validation_execution_enforces_dependency_policy(dependency_policy: str) -> None:
    (unit,), _ = coalesce_validation_requirements((_validation_requirement("V01"),))
    unit = replace(unit, commands=("just first", "just second"), working_directories=("/repo", "/repo"), dependency_policy=dependency_policy)
    expectation, evidence = _validation_evidence(unit)
    evidence = replace(evidence, status="failed")
    content = _validation_result_payload(expectation, evidence)
    assert not _validation_native_result_blockers(content, expectation, evidence)

    if dependency_policy == "stop-on-failure":
        forged = _replace_in_native_section(content, "## Executions", "## Reused Evidence", "  - Result: not-run", "  - Result: passed")
        expected = "stop-on-failure"
    else:
        forged = _replace_in_native_section(content, "## Executions", "## Reused Evidence", "  - Result: passed", "  - Result: not-run")
        expected = "continue-independent"

    blockers = _validation_native_result_blockers(forged, expectation, evidence)
    assert any(expected in blocker for blocker in blockers)


def test_validation_evidence_is_accepted_only_for_exact_requirements_and_state() -> None:
    expectation, evidence = _validation_evidence()

    accepted = assess_validation_evidence(expectation, evidence)
    rejected = assess_validation_evidence(expectation, replace(evidence, requirement_ids=("V01",)))

    assert accepted.feasible
    assert accepted.satisfies_requirements
    assert not rejected.feasible


def test_validation_evidence_rejects_command_and_environment_digest_mismatches() -> None:
    expectation, evidence = _validation_evidence()

    wrong_command = assess_validation_evidence(expectation, replace(evidence, command_identity_digest="sha256:wrong-command"))
    wrong_environment = assess_validation_evidence(expectation, replace(evidence, environment_digest="sha256:wrong-environment"))

    assert not wrong_command.feasible
    assert "validation evidence command identity digest does not match its exact validation unit dispatch" in wrong_command.blockers
    assert not wrong_environment.feasible
    assert "validation evidence environment digest does not match its exact validation unit dispatch" in wrong_environment.blockers


def test_validation_dispatch_digests_cover_every_coalescing_identity_field() -> None:
    expectation, _ = _validation_evidence()
    unit = expectation.validation_unit

    command_variants = (
        replace(unit, commands=("just check",)),
        replace(unit, working_directories=("/different",)),
        replace(unit, canonical_recipe="just check"),
    )
    environment_variants = (
        replace(unit, environment="different"),
        replace(unit, toolchain="nightly"),
        replace(unit, features=("all",)),
        replace(unit, platform="linux-x86_64"),
        replace(unit, artifact_owner="external"),
        replace(unit, mutation_lock="exclusive"),
    )

    assert all(validation_command_identity_digest(item) != expectation.command_identity_digest for item in command_variants)
    assert all(validation_environment_digest(item) != expectation.environment_digest for item in environment_variants)


def test_validation_dispatch_digest_fixed_vectors() -> None:
    expectation, _ = _validation_evidence()
    unit = replace(
        expectation.validation_unit,
        canonical_recipe=None,
        commands=("just check", "uv run pytest tests/test_é.py"),
        working_directories=("/repo", "/repo/subdir"),
        allowed_artifacts=(
            ValidationArtifact(path="logs/é.txt", kind="log", repository_status="ignored", artifact_id="artifact://log", artifact_digest="sha256:" + "a" * 64),
        ),
        artifact_owner="validator",
        environment="PYTHONUTF8=1",
        features=("feature-a", "feature-b"),
        mutation_lock="shared-read",
        platform="darwin-arm64",
        toolchain="python-3.14",
    )

    assert validation_command_identity_digest(unit) == "sha256:0a7cf4ab06b8269b3807b1d8727bd01a82aaf85d649be501f42745136843e93d"
    assert validation_environment_digest(unit) == "sha256:b21bc5afe779633ac3609bc2bdca9df8f2e8c8296811867068636c6b280eb9cb"


def test_isolated_validation_rejects_coordinator_evidence() -> None:
    state = ("scope", "worktree", "repository")
    (unit,), _ = coalesce_validation_requirements((_validation_requirement("V01"),))
    expectation = validation_evidence_expectation(
        unit,
        skill_path="/skills/review-validator/SKILL.md",
        skill_digest="sha256:review-validator",
        reference_digests=(),
        execution_profile="isolated",
        execution_location="worker",
    )
    evidence = ValidationEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        evidence_id="review-validator:validation-001:repository",
        node_id="validation-001",
        requirement_ids=("V01",),
        skill_digest="sha256:review-validator",
        reference_digests=(),
        fingerprints=FingerprintEvidence(expected=state, before=state, after=state),
        execution_profile="isolated",
        execution_location="coordinator",
        worker_created=False,
        fresh_context=False,
        status="passed",
        command_identity_digest=validation_command_identity_digest(unit),
        environment_digest=validation_environment_digest(unit),
        raw_result_artifact_id="artifact://validation-001",
        raw_result_digest="sha256:validation-result",
    )

    result = assess_validation_evidence(expectation, evidence)

    assert not result.feasible
    assert "isolated validation evidence requires a fresh worker execution" in result.blockers


def _repository_review_expectation(
    *, review_count: int = 1, execution_profile: str = "grouped", include_independent: bool = False
) -> RepositoryReviewProofExpectation:
    requirements = tuple(_review_requirement(index, synthesis_dependency="repository-synthesis") for index in range(1, review_count + 1))
    audit_reference = "/skills/python-test-quality/references/pytest.md"
    requirements = (
        replace(
            requirements[0],
            skill_id="python-test-quality",
            skill_path="/skills/python-test-quality/SKILL.md",
            skill_digest="sha256:skill",
            static_references=(audit_reference,),
            reference_digests=((audit_reference, "sha256:reference"),),
        ),
        *requirements[1:],
    )
    plan = plan_graph(
        requirements,
        (_validation_requirement("V01", baseline=True), _validation_requirement("V02")),
        (
            WorkerNode(
                node_id="repository-synthesis",
                skill_id="repository-production-review",
                skill_path="/skills/repository-production-review/SKILL.md",
                mode="synthesis",
                priority="required-routing-synthesis",
                required=True,
                skill_digest="sha256:synthesis-skill",
            ),
        ),
        additional_nodes=(
            WorkerNode(
                node_id="independent-001",
                skill_id="repository-independent-review",
                skill_path="/skills/repository-independent-review/SKILL.md",
                mode="independent-review",
                priority="supporting-quality",
                required=True,
                coverage=("src/state.rs", "tests/state_test.py"),
                synthesis_dependency="repository-synthesis",
                change_target="git diff origin/main...HEAD -- src/state.rs tests/state_test.py",
                skill_digest="sha256:independent-skill",
            ),
        )
        if include_independent
        else (),
        execution_profile=execution_profile,
        validator_skill_path="/skills/review-validator/SKILL.md",
        validator_skill_digest="sha256:review-validator",
        validator_reference_digests=(("/skills/review-validator/references/result-contract.md", "sha256:reference"),),
        captured_path_line_bounds=(("src/state.rs", 120), ("tests/state_test.py", 80)) if include_independent else (),
    )
    return repository_review_proof_expectation(plan, source_state=("scope", "worktree", "repository"))


def _repository_review_proof(expectation: RepositoryReviewProofExpectation | None = None) -> RepositoryReviewProof:
    expectation = expectation or _repository_review_expectation()
    evidence_by_node = {
        node.node_id: (
            f"review-validator:{node.node_id}:repository"
            if node.mode == "validation"
            else "review:repository-synthesis"
            if node.node_id == "repository-synthesis"
            else f"review:{node.node_id}:repository"
        )
        for node in expectation.planned_evidence_nodes
    }
    planned_node_evidence = tuple((node.node_id, evidence_by_node[node.node_id]) for node in expectation.planned_evidence_nodes)
    return RepositoryReviewProof(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        proof_id="review-proof:repository",
        plan_digest=expectation.plan_digest,
        source_state=("scope", "worktree", "repository"),
        planned_node_evidence=planned_node_evidence,
        required_review_requirement_ids=expectation.required_review_requirement_ids,
        review_requirement_evidence=tuple(
            sorted(
                (
                    *((requirement_id, evidence_by_node[node_id]) for requirement_id, node_id in expectation.review_requirement_nodes),
                    *expectation.exact_reused_review_evidence,
                )
            )
        ),
        exact_reused_review_evidence=expectation.exact_reused_review_evidence,
        accepted_review_evidence_ids=tuple(
            dict.fromkeys(
                (
                    *(evidence_by_node[node.node_id] for node in expectation.planned_evidence_nodes if node.mode != "validation"),
                    *(evidence_id for _, evidence_id in expectation.exact_reused_review_evidence),
                )
            )
        ),
        required_validation_requirement_ids=expectation.required_validation_requirement_ids,
        validation_requirement_evidence=tuple(
            (requirement_id, evidence_by_node[node_id]) for requirement_id, node_id in expectation.validation_requirement_nodes
        ),
        accepted_validation_evidence_ids=tuple(evidence_by_node[node.node_id] for node in expectation.planned_evidence_nodes if node.mode == "validation"),
        stale_evidence_ids=(),
        unresolved_handoff_ids=(),
        final_synthesis_evidence_id=evidence_by_node["repository-synthesis"],
        artifact_manifest_id="artifact://manifest",
        artifact_manifest_digest="sha256:manifest",
        verifier_id="review-graph-plan:v1",
    )


def _completion_binding(
    execution_profile: str, *, include_independent: bool = False
) -> tuple[
    RepositoryReviewProofExpectation,
    RepositoryReviewProof,
    tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...],
    tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...],
    ArtifactManifest,
    TrustedArtifactVerifier,
]:
    expectation = _repository_review_expectation(execution_profile=execution_profile, include_independent=include_independent)
    return _verified_binding(expectation)


def _predecessor_evidence_ids(expectation: RepositoryReviewProofExpectation, proof: RepositoryReviewProof, node_id: str) -> tuple[str, ...]:
    evidence_by_node = dict(proof.planned_node_evidence)
    node = next(item for item in expectation.planned_evidence_nodes if item.node_id == node_id)
    return tuple(
        dict.fromkeys(
            (
                *(evidence_by_node[predecessor] for predecessor in node.predecessors),
                *((evidence_id for _, evidence_id in expectation.exact_reused_review_evidence) if node_id == expectation.final_synthesis_identity[0] else ()),
            )
        )
    )


def _verified_binding(
    expectation: RepositoryReviewProofExpectation,
) -> tuple[
    RepositoryReviewProofExpectation,
    RepositoryReviewProof,
    tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...],
    tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...],
    ArtifactManifest,
    TrustedArtifactVerifier,
]:
    execution_profile = expectation.plan.execution_profile
    proof = _repository_review_proof(expectation)
    evidence_by_node = dict(proof.planned_node_evidence)
    validation_units = {unit.node_id: unit for unit in expectation.plan.coalesced_validation_units}
    isolated = execution_profile in {"isolated", "isolated-only"}
    execution_location = "worker" if isolated else "coordinator"
    review_records: list[tuple[ReviewEvidenceExpectation, ReviewEvidence]] = []
    validation_records: list[tuple[ValidationEvidenceExpectation, ValidationEvidence]] = []
    for node in expectation.planned_evidence_nodes:
        evidence_id = evidence_by_node[node.node_id]
        if node.mode == "validation":
            unit = validation_units[node.node_id]
            validation_expectation = validation_evidence_expectation(
                unit,
                skill_path=node.skill_path,
                skill_digest=node.skill_digest,
                reference_digests=node.reference_digests,
                execution_profile=execution_profile,
                execution_location=execution_location,
            )
            validation_records.append(
                (
                    validation_expectation,
                    ValidationEvidence(
                        schema_version=EVIDENCE_SCHEMA_VERSION,
                        evidence_id=evidence_id,
                        node_id=node.node_id,
                        requirement_ids=unit.requirement_ids,
                        skill_digest=validation_expectation.skill_digest,
                        reference_digests=validation_expectation.reference_digests,
                        fingerprints=FingerprintEvidence(expected=expectation.source_state, before=expectation.source_state, after=expectation.source_state),
                        execution_profile=execution_profile,
                        execution_location=execution_location,
                        worker_created=isolated,
                        fresh_context=isolated,
                        status="passed",
                        command_identity_digest=validation_expectation.command_identity_digest,
                        environment_digest=validation_expectation.environment_digest,
                        raw_result_artifact_id=f"artifact://{node.node_id}",
                        raw_result_digest=_result_digest(evidence_id),
                    ),
                )
            )
            continue
        review_expectation = ReviewEvidenceExpectation(
            node_id=node.node_id,
            requirement_ids=next(item.requirement_ids for item in expectation.plan.actual_worker_nodes if item.node_id == node.node_id),
            skill_id=node.skill_id,
            mode=node.mode,
            skill_path=node.skill_path,
            skill_digest=node.skill_digest,
            reference_digests=node.reference_digests,
            source_state=expectation.source_state,
            execution_profile=execution_profile,
            selection_reason="; ".join(next(item.selection_reasons for item in expectation.plan.actual_worker_nodes if item.node_id == node.node_id))
            or f"required {node.mode} graph node",
            authorization="review-only",
            predecessor_evidence_ids=_predecessor_evidence_ids(expectation, proof, node.node_id) if node.mode == "synthesis" else (),
            change_target=node.change_target,
            planned_paths=node.planned_paths,
            planned_path_line_bounds=node.planned_path_line_bounds,
        )
        review_records.append(
            (
                review_expectation,
                ReviewEvidence(
                    schema_version=EVIDENCE_SCHEMA_VERSION,
                    evidence_id=evidence_id,
                    node_id=node.node_id,
                    requirement_ids=review_expectation.requirement_ids,
                    skill_id=node.skill_id,
                    mode=node.mode,
                    skill_path=node.skill_path,
                    skill_digest=review_expectation.skill_digest,
                    reference_digests=review_expectation.reference_digests,
                    fingerprints=FingerprintEvidence(expected=expectation.source_state, before=expectation.source_state, after=expectation.source_state),
                    execution_profile=execution_profile,
                    execution_location=execution_location,
                    worker_created=isolated,
                    fresh_context=isolated,
                    status="no-findings",
                    finding_ids=(),
                    validation_requirement_ids=(),
                    handoff_ids=(),
                    raw_result_artifact_id=f"artifact://{node.node_id}",
                    raw_result_digest=_result_digest(evidence_id),
                    report_complete=True,
                    predecessor_evidence_ids=review_expectation.predecessor_evidence_ids,
                ),
            )
        )
    for ordinal, reuse in enumerate(expectation.reused_review_identities, start=1):
        requirement_ids = tuple(requirement_id for requirement_id, evidence_id in expectation.exact_reused_review_evidence if evidence_id == reuse.evidence_id)
        reference_digests = reuse.reference_digests
        review_expectation = ReviewEvidenceExpectation(
            node_id=f"reused-ancestor-{ordinal:03d}",
            requirement_ids=requirement_ids,
            skill_id=reuse.skill_id,
            mode=reuse.mode,
            skill_path=reuse.skill_path,
            skill_digest=reuse.skill_digest,
            reference_digests=reference_digests,
            source_state=expectation.source_state,
            execution_profile=execution_profile,
            selection_reason=f"exact routed reuse for {reuse.requirement_id}",
            authorization="review-only",
            change_target=reuse.change_target,
            planned_paths=reuse.planned_paths,
            planned_path_line_bounds=reuse.planned_path_line_bounds,
        )
        review_records.append(
            (
                review_expectation,
                ReviewEvidence(
                    schema_version=EVIDENCE_SCHEMA_VERSION,
                    evidence_id=reuse.evidence_id,
                    node_id=review_expectation.node_id,
                    requirement_ids=requirement_ids,
                    skill_id=reuse.skill_id,
                    mode=reuse.mode,
                    skill_path=reuse.skill_path,
                    skill_digest=review_expectation.skill_digest,
                    reference_digests=reference_digests,
                    fingerprints=FingerprintEvidence(expected=expectation.source_state, before=expectation.source_state, after=expectation.source_state),
                    execution_profile=execution_profile,
                    execution_location=execution_location,
                    worker_created=isolated,
                    fresh_context=isolated,
                    status="no-findings",
                    finding_ids=(),
                    validation_requirement_ids=(),
                    handoff_ids=(),
                    raw_result_artifact_id=f"artifact://reused-{ordinal:03d}",
                    raw_result_digest=_result_digest(reuse.evidence_id),
                    report_complete=True,
                ),
            )
        )
    typed_review_records = tuple(review_records)
    typed_validation_records = tuple(validation_records)
    proof, manifest, verifier, typed_review_records, typed_validation_records = _artifact_verification(proof, typed_review_records, typed_validation_records)
    return expectation, proof, typed_review_records, typed_validation_records, manifest, verifier


def _artifact_verification(
    proof: RepositoryReviewProof,
    review_records: tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...],
    validation_records: tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...],
) -> tuple[
    RepositoryReviewProof,
    ArtifactManifest,
    TrustedArtifactVerifier,
    tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...],
    tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...],
]:
    finalized_review_records = tuple(
        (expectation, replace(evidence, raw_result_digest="sha256:" + hashlib.sha256(_review_result_payload(expectation, evidence)).hexdigest()))
        for expectation, evidence in review_records
    )
    finalized_validation_records = tuple(
        (expectation, replace(evidence, raw_result_digest="sha256:" + hashlib.sha256(_validation_result_payload(expectation, evidence)).hexdigest()))
        for expectation, evidence in validation_records
    )
    records = {evidence.evidence_id: (expectation, evidence) for expectation, evidence in (*finalized_review_records, *finalized_validation_records)}
    accepted_ids = (*proof.accepted_review_evidence_ids, *proof.accepted_validation_evidence_ids)
    review_ids = {evidence.evidence_id for _, evidence in finalized_review_records}
    artifacts = tuple(
        ArtifactPayload(
            artifact_id=records[evidence_id][1].raw_result_artifact_id,
            content=(
                _review_result_payload(*cast("tuple[ReviewEvidenceExpectation, ReviewEvidence]", records[evidence_id]))
                if evidence_id in review_ids
                else _validation_result_payload(*cast("tuple[ValidationEvidenceExpectation, ValidationEvidence]", records[evidence_id]))
            ),
        )
        for evidence_id in accepted_ids
    )
    manifest = create_artifact_manifest(
        manifest_id=proof.artifact_manifest_id,
        verifier_id=proof.verifier_id,
        artifacts=tuple((evidence_id, artifact.artifact_id, artifact.content) for evidence_id, artifact in zip(accepted_ids, artifacts, strict=True)),
    )
    verifier = TrustedArtifactVerifier(verifier_id=proof.verifier_id, digest_algorithm="sha256", artifacts=artifacts)
    return (replace(proof, artifact_manifest_digest=manifest.manifest_digest), manifest, verifier, finalized_review_records, finalized_validation_records)


def _replace_native_block(content: bytes, payload: str) -> bytes:
    text = content.decode()
    start = text.index(NATIVE_EVIDENCE_BLOCK_OPEN) + len(NATIVE_EVIDENCE_BLOCK_OPEN)
    end = text.index(NATIVE_EVIDENCE_BLOCK_CLOSE, start)
    return f"{text[:start]}{payload}{text[end:]}".encode()


def _replace_native_preamble(content: bytes, first_section: str, body: str) -> bytes:
    text = content.decode()
    heading_end = text.index("\n")
    section_start = text.index(f"{first_section}\n", heading_end)
    return f"{text[: heading_end + 1]}\n{body}\n\n{text[section_start:]}".encode()


def _replace_native_section(content: bytes, heading: str, next_heading: str, body: str) -> bytes:
    text = content.decode()
    start = text.index(f"{heading}\n") + len(heading) + 1
    end = text.index(f"\n{next_heading}\n", start)
    return f"{text[:start]}\n{body}\n{text[end + 1 :]}".encode()


def _replace_in_native_section(content: bytes, heading: str, next_heading: str, old: str, new: str) -> bytes:
    text = content.decode()
    start = text.index(f"{heading}\n") + len(heading) + 1
    end = text.index(f"\n{next_heading}\n", start)
    body = text[start:end].replace(old, new, 1)
    return f"{text[:start]}{body}{text[end:]}".encode()


def _all_none_native_sections(content: bytes, sections: tuple[str, ...]) -> bytes:
    changed = content
    for heading, next_heading in pairwise(sections):
        changed = _replace_native_section(changed, heading, next_heading, "none")
    return changed


def _rebase_artifact_payload(
    proof: RepositoryReviewProof, manifest: ArtifactManifest, verifier: TrustedArtifactVerifier, *, evidence_id: str, content: bytes
) -> tuple[RepositoryReviewProof, ArtifactManifest, TrustedArtifactVerifier]:
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    artifacts = tuple(replace(artifact, content=content) if artifact.artifact_id == artifact_id else artifact for artifact in verifier.artifacts)
    content_by_artifact = {artifact.artifact_id: artifact.content for artifact in artifacts}
    rebased_manifest = create_artifact_manifest(
        manifest_id=manifest.manifest_id,
        verifier_id=manifest.verifier_id,
        artifacts=tuple((entry.evidence_id, entry.artifact_id, content_by_artifact[entry.artifact_id]) for entry in manifest.entries),
    )
    return (replace(proof, artifact_manifest_digest=rebased_manifest.manifest_digest), rebased_manifest, replace(verifier, artifacts=artifacts))


def _evidence_bundle_fixture() -> tuple[
    RepositoryReviewProofExpectation,
    RepositoryReviewProof,
    tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...],
    tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...],
    ArtifactManifest,
    TrustedArtifactVerifier,
]:
    expectation = _repository_review_expectation()
    proof = _repository_review_proof(expectation)
    audit_expectation, audit_evidence = _review_evidence()
    synthesis_expectation = replace(
        audit_expectation,
        node_id="repository-synthesis",
        requirement_ids=(),
        skill_id="repository-production-review",
        mode="synthesis",
        skill_path="/skills/repository-production-review/SKILL.md",
        skill_digest="sha256:synthesis-skill",
        reference_digests=(),
        predecessor_evidence_ids=_predecessor_evidence_ids(expectation, proof, "repository-synthesis"),
    )
    synthesis_evidence = replace(
        audit_evidence,
        evidence_id="review:repository-synthesis",
        node_id="repository-synthesis",
        requirement_ids=(),
        skill_id="repository-production-review",
        mode="synthesis",
        skill_path="/skills/repository-production-review/SKILL.md",
        skill_digest="sha256:synthesis-skill",
        reference_digests=(),
        finding_ids=(),
        validation_requirement_ids=(),
        raw_result_artifact_id="artifact://repository-synthesis",
        raw_result_digest=_result_digest("review:repository-synthesis"),
        predecessor_evidence_ids=_predecessor_evidence_ids(expectation, proof, "repository-synthesis"),
    )
    validation_expectation, validation_evidence = _validation_evidence(expectation.plan.coalesced_validation_units[0])
    review_records = ((audit_expectation, audit_evidence), (synthesis_expectation, synthesis_evidence))
    validation_records = ((validation_expectation, validation_evidence),)
    proof, manifest, verifier, review_records, validation_records = _artifact_verification(proof, review_records, validation_records)
    return expectation, proof, review_records, validation_records, manifest, verifier


def _routed_reuse_binding(
    catalog_id: str,
) -> tuple[
    RepositoryReviewProofExpectation,
    RepositoryReviewProof,
    tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...],
    tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...],
    ArtifactManifest,
    TrustedArtifactVerifier,
]:
    document = _exhaustive_rust_document()
    decisions = cast("list[dict[str, object]]", document["routing_decisions"])
    for decision in decisions:
        if decision["catalog_id"] == catalog_id:
            decision["disposition"] = "exact-evidence-reused"
            decision["evidence_id"] = f"review:reused:{catalog_id}"
    plan = plan_from_document(document, repository_root=REPOSITORY_ROOT)
    expectation = repository_review_proof_expectation(plan, source_state=("scope", "worktree", "repository"))
    return _verified_binding(expectation)


@pytest.mark.parametrize("catalog_id", ["rust.tests", "repo.independent"])
def test_exact_routed_reuse_satisfies_only_its_requirement_without_execution(catalog_id: str) -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _routed_reuse_binding(catalog_id)
    planned_nodes = expectation.planned_evidence_nodes
    validation_nodes = tuple(node.node_id for node in planned_nodes if node.mode == "validation")
    synthesis_nodes = tuple(node.node_id for node in planned_nodes if node.mode == "synthesis")
    reused_requirement_ids = tuple(requirement_id for requirement_id, _ in expectation.exact_reused_review_evidence)
    independent_required = any(node.mode == "independent-review" for node in planned_nodes) or any(
        item.mode == "independent-review" for item in expectation.reused_review_identities
    )
    completion = CompletionEvidence(
        required_requirement_ids=expectation.required_review_requirement_ids,
        completed_requirement_ids=expectation.plan.selected_review_requirements,
        meaningful_skip_requirement_ids=(),
        required_documentation_ids=(),
        completed_documentation_ids=(),
        required_validation_node_ids=validation_nodes,
        accepted_validation_node_ids=validation_nodes,
        required_synthesis_node_ids=synthesis_nodes,
        accepted_synthesis_node_ids=synthesis_nodes,
        unaccepted_node_ids=(),
        undispatched_node_ids=(),
        fingerprints_matched=True,
        execution_profile=expectation.plan.execution_profile,
        isolation_failures=(),
        final_report_synthesized=True,
        findings_deduplicated=True,
        repository_review_expectation=expectation,
        repository_review_proof=proof,
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_artifact_verifier=verifier,
        exact_reused_requirement_ids=reused_requirement_ids,
        independent_review_required=independent_required,
        independent_review_accepted=independent_required,
    )

    result = assess_completion(completion)

    assert result.feasible
    assert not ({item.requirement_id for item in expectation.reused_review_identities} & set(expectation.plan.selected_review_requirements))
    if catalog_id == "repo.independent":
        (reuse,) = tuple(item for item in expectation.reused_review_identities if item.mode == "independent-review")
        assert reuse.change_target == f"git diff origin/main...HEAD -- {RUST_FIXTURE_PATH}"
        assert reuse.planned_paths == (RUST_FIXTURE_PATH,)


def test_exact_routed_reuse_rejects_substitution_missing_record_and_tampered_identity() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _routed_reuse_binding("rust.tests")
    requirement_id, evidence_id = expectation.exact_reused_review_evidence[0]
    substituted = replace(
        proof,
        exact_reused_review_evidence=((requirement_id, "review:substituted"),),
        review_requirement_evidence=tuple(
            (mapped_requirement, "review:substituted" if mapped_requirement == requirement_id else mapped_evidence)
            for mapped_requirement, mapped_evidence in proof.review_requirement_evidence
        ),
    )
    missing_records = tuple(record for record in review_records if record[1].evidence_id != evidence_id)
    tampered_records = tuple(
        (replace(record_expectation, skill_id="different-skill"), replace(envelope, skill_id="different-skill"))
        if envelope.evidence_id == evidence_id
        else (record_expectation, envelope)
        for record_expectation, envelope in review_records
    )
    reused_artifact_id = next(envelope.raw_result_artifact_id for _, envelope in review_records if envelope.evidence_id == evidence_id)
    tampered_verifier = replace(
        verifier,
        artifacts=tuple(
            replace(artifact, content=b"tampered reused artifact") if artifact.artifact_id == reused_artifact_id else artifact
            for artifact in verifier.artifacts
        ),
    )

    substitution_result = assess_evidence_bundle(
        expectation, substituted, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    missing_result = assess_evidence_bundle(
        expectation, proof, review_records=missing_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    tampered_result = assess_evidence_bundle(
        expectation, proof, review_records=tampered_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    artifact_result = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=tampered_verifier
    )

    assert not substitution_result.feasible
    assert "repository review proof exact reused review evidence do not match the planner-derived expectation" in substitution_result.blockers
    assert not missing_result.feasible
    assert f"accepted review evidence is missing from the bundle: {evidence_id}" in missing_result.blockers
    assert not tampered_result.feasible
    assert f"exactly reused review evidence expectation identity does not match routed requirement {requirement_id}" in tampered_result.blockers
    assert f"exactly reused review evidence envelope identity does not match routed requirement {requirement_id}" in tampered_result.blockers
    assert not artifact_result.feasible
    assert f"artifact manifest artifact digest does not verify: {evidence_id}" in artifact_result.blockers


def test_final_proof_expectation_rejects_fix_and_revalidation_transition_nodes() -> None:
    plan = plan_graph(
        (_review_requirement(1, synthesis_dependency="surface-synthesis"),),
        (_validation_requirement("V01", baseline=True),),
        (
            WorkerNode(
                node_id="surface-synthesis",
                skill_id="python-production-review",
                skill_path="/skills/python-production-review/SKILL.md",
                mode="synthesis",
                priority="required-routing-synthesis",
                required=True,
                skill_digest="sha256:surface-synthesis",
            ),
            WorkerNode(
                node_id="repository-synthesis",
                skill_id="repository-production-review",
                skill_path="/skills/repository-production-review/SKILL.md",
                mode="synthesis",
                priority="required-routing-synthesis",
                required=True,
                skill_digest="sha256:repository-synthesis",
            ),
        ),
        additional_nodes=tuple(
            WorkerNode(
                node_id=node_id,
                skill_id=skill_id,
                skill_path=f"/skills/{skill_id}/SKILL.md",
                mode=mode,
                priority="supporting-quality",
                required=True,
                coverage=("src/state.rs",) if mode == "independent-review" else (),
                synthesis_dependency="repository-synthesis",
                change_target="git diff origin/main...HEAD -- src/state.rs" if mode == "independent-review" else None,
                skill_digest=f"sha256:{node_id}",
            )
            for node_id, skill_id, mode in (
                ("independent-001", "repository-independent-review", "independent-review"),
                ("fix-001", "python-production-review", "fix"),
                ("revalidation-001", "python-test-quality", "revalidation"),
            )
        ),
    )
    with pytest.raises(ValueError, match="transition-only or unsupported executable node modes: fix, revalidation"):
        repository_review_proof_expectation(plan, source_state=("scope-s1", "worktree-s1", "repository-s1"))


def test_recaptured_final_plan_without_transition_nodes_verifies() -> None:
    expectation = _repository_review_expectation(include_independent=True)
    proof = _repository_review_proof(expectation)

    result = assess_repository_review_proof(expectation, proof)

    assert result.feasible
    assert {node.mode for node in expectation.planned_evidence_nodes} == {"audit", "independent-review", "synthesis", "validation"}


def test_repository_review_proof_requires_a_planned_node_evidence_bijection() -> None:
    expectation = _repository_review_expectation()
    proof = _repository_review_proof(expectation)
    omitted = replace(proof, planned_node_evidence=proof.planned_node_evidence[1:])
    duplicate_node = replace(proof, planned_node_evidence=(*proof.planned_node_evidence, proof.planned_node_evidence[0]))
    duplicate_evidence = replace(
        proof,
        planned_node_evidence=(
            proof.planned_node_evidence[0],
            (proof.planned_node_evidence[1][0], proof.planned_node_evidence[0][1]),
            *proof.planned_node_evidence[2:],
        ),
    )
    unplanned_accepted = replace(proof, accepted_review_evidence_ids=(*proof.accepted_review_evidence_ids, "review:unplanned"))

    results = tuple(assess_repository_review_proof(expectation, item) for item in (omitted, duplicate_node, duplicate_evidence, unplanned_accepted))

    assert all(not result.feasible for result in results)
    assert "repository review proof does not map every planned executable node exactly once" in results[0].blockers
    assert "repository review proof maps a planned node more than once" in results[1].blockers
    assert "repository review proof maps one evidence record to multiple planned nodes" in results[2].blockers
    assert "accepted evidence is neither mapped to a planned executable node nor exact routed reuse: review:unplanned" in results[3].blockers


def test_routed_independent_review_evidence_passes_assessment_and_bundle_verification() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG)
    (independent_node,) = independent_nodes_from_routing(
        catalog, _closed_rust_routing_decisions(), change_target=f"git diff origin/main...HEAD -- {RUST_FIXTURE_PATH}"
    )
    independent_plan = plan_graph(
        (),
        (_validation_requirement("V01", baseline=True), _validation_requirement("V02")),
        (
            WorkerNode(
                node_id="repository-synthesis",
                skill_id="repository-production-review",
                skill_path="/skills/repository-production-review/SKILL.md",
                mode="synthesis",
                priority="required-routing-synthesis",
                required=True,
                skill_digest="sha256:repository-synthesis",
            ),
        ),
        additional_nodes=(independent_node,),
        routing_assessment=RoutingLedgerAssessment(
            feasible=True,
            blockers=(),
            selected_requirement_ids=independent_node.requirement_ids,
            exact_reused_review_evidence=(),
            reused_review_identities=(),
            user_excluded_catalog_ids=(),
            completion_blocking_catalog_ids=(),
            consulted_routers=("review-graph",),
            catalog_closed=True,
        ),
        captured_path_line_bounds=((RUST_FIXTURE_PATH, 3),),
    )
    expectation = repository_review_proof_expectation(independent_plan, source_state=("scope", "worktree", "repository"))
    expectation, proof, independent_records, validation_records, manifest, verifier = _verified_binding(expectation)
    independent_expectation, independent_evidence = next(record for record in independent_records if record[0].node_id == independent_node.node_id)

    assessment = assess_review_evidence(independent_expectation, independent_evidence)
    bundle = assess_evidence_bundle(
        expectation, proof, review_records=independent_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert assessment.feasible
    assert assessment.satisfies_requirements
    assert bundle.feasible


def test_evidence_bundle_binds_independent_expectation_provenance_to_the_planned_node() -> None:
    expectation = _repository_review_expectation(include_independent=True)
    expectation, proof, review_records, validation_records, _, _ = _verified_binding(expectation)
    forged_records = tuple(
        (replace(record_expectation, change_target="git diff -- unrelated.txt", planned_paths=("unrelated.txt",)), evidence)
        if record_expectation.mode == "independent-review"
        else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, forged_records, validation_records = _artifact_verification(proof, forged_records, validation_records)

    result = assess_evidence_bundle(
        expectation, proof, review_records=forged_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert "independent-review evidence provenance does not match planned node independent-001" in result.blockers


def test_evidence_bundle_rejects_completed_independent_review_without_findings() -> None:
    expectation = _repository_review_expectation(include_independent=True)
    expectation, proof, review_records, validation_records, _, _ = _verified_binding(expectation)
    completed_records = tuple(
        (record_expectation, replace(evidence, status="completed")) if record_expectation.mode == "independent-review" else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, completed_records, validation_records = _artifact_verification(proof, completed_records, validation_records)

    result = assess_evidence_bundle(
        expectation, proof, review_records=completed_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert any("completed independent-review evidence must contain at least one finding ID" in blocker for blocker in result.blockers)


def test_synthesis_evidence_requires_accepted_mapped_predecessor_evidence() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    without_audit_mapping = replace(proof, planned_node_evidence=tuple(item for item in proof.planned_node_evidence if item[0] != "audit-001"))

    result = assess_evidence_bundle(
        expectation,
        without_audit_mapping,
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )

    assert not result.feasible
    assert "synthesis node repository-synthesis lacks accepted mapped predecessor evidence: audit-001" in result.blockers


def test_repository_review_proof_requires_complete_nonstale_mappings() -> None:
    expectation = _repository_review_expectation()
    proof = _repository_review_proof(expectation)

    accepted = assess_repository_review_proof(expectation, proof)
    stale = assess_repository_review_proof(expectation, replace(proof, stale_evidence_ids=("review:audit-001:repository",)))

    assert accepted.feasible
    assert not stale.feasible
    assert "review proof references stale evidence: review:audit-001:repository" in stale.blockers


def test_repository_review_proof_rejects_plan_identity_and_required_id_omissions() -> None:
    expectation = _repository_review_expectation()
    proof = _repository_review_proof(expectation)
    omitted = replace(proof, required_review_requirement_ids=(), review_requirement_evidence=())
    wrong_plan = replace(proof, plan_digest="sha256:different-plan")

    omitted_result = assess_repository_review_proof(expectation, omitted)
    wrong_plan_result = assess_repository_review_proof(expectation, wrong_plan)

    assert not omitted_result.feasible
    assert "repository review proof required review requirement IDs do not match the planner-derived expectation" in omitted_result.blockers
    assert not wrong_plan_result.feasible
    assert "repository review proof plan digest do not match the planner-derived expectation" in wrong_plan_result.blockers


def test_evidence_bundle_rejects_review_evidence_from_an_unplanned_node() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    audit_expectation, audit_evidence = review_records[0]
    unplanned_expectation = replace(audit_expectation, node_id="audit-unplanned")
    unplanned_evidence = replace(audit_evidence, node_id="audit-unplanned")
    records = ((unplanned_expectation, unplanned_evidence), review_records[1])
    proof, manifest, verifier, records, validation_records = _artifact_verification(proof, records, validation_records)

    result = assess_evidence_bundle(
        expectation, proof, review_records=records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert any("review proof requirement evidence does not match its planner-derived node" in blocker for blocker in result.blockers)
    assert "review evidence expectation identity does not match planned node audit-001" in result.blockers
    assert "review evidence envelope identity does not match planned node audit-001" in result.blockers


def test_evidence_bundle_reverifies_every_claimed_accepted_evidence() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()

    accepted = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    fabricated = assess_evidence_bundle(
        expectation,
        replace(proof, accepted_review_evidence_ids=(*proof.accepted_review_evidence_ids, "review:missing")),
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )

    assert accepted.feasible
    assert not fabricated.feasible
    assert "accepted review evidence is missing from the bundle: review:missing" in fabricated.blockers


def test_final_synthesis_evidence_must_have_the_repository_synthesis_identity() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()

    result = assess_evidence_bundle(
        expectation,
        replace(proof, final_synthesis_evidence_id="review:audit-001:repository"),
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )

    assert not result.feasible
    assert any("final synthesis evidence expectation identity must be" in blocker for blocker in result.blockers)


def test_artifact_manifest_rejects_missing_tampered_and_unknown_verifier_claims() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    missing = replace(manifest, entries=manifest.entries[:-1])
    tampered = replace(manifest, entries=(replace(manifest.entries[0], artifact_digest="sha256:tampered"), *manifest.entries[1:]))

    missing_result = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=missing, trusted_verifier=verifier
    )
    tampered_result = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=tampered, trusted_verifier=verifier
    )
    unknown_verifier_result = assess_evidence_bundle(
        expectation,
        replace(proof, verifier_id="unknown-verifier"),
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )

    assert not missing_result.feasible
    assert any("artifact manifest does not cover accepted evidence exactly" in blocker for blocker in missing_result.blockers)
    assert not tampered_result.feasible
    assert "artifact manifest entry digest does not verify: review:audit-001:repository" in tampered_result.blockers
    assert not unknown_verifier_result.feasible
    assert "repository review proof names an unknown verifier: unknown-verifier" in unknown_verifier_result.blockers


def test_native_artifact_gate_rejects_arbitrary_malformed_truncated_duplicate_and_incomplete_markdown() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    evidence_id = "review:audit-001:repository"
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    original = next(artifact.content for artifact in verifier.artifacts if artifact.artifact_id == artifact_id)
    header = _review_header(review_records[0][0], review_records[0][1])
    variants = (
        (b"review:audit-001:repository", "native result top heading must be exactly # Review Node Result"),
        (_replace_native_block(original, "{"), "native result evidence block is not valid JSON"),
        (original.replace(NATIVE_EVIDENCE_BLOCK_CLOSE.encode(), b"", 1), "native result evidence block is truncated"),
        (
            original + f"\n{NATIVE_EVIDENCE_BLOCK_OPEN}{{}}{NATIVE_EVIDENCE_BLOCK_CLOSE}\n".encode(),
            "native result must contain exactly one canonical evidence block",
        ),
        (original.replace(b"# Review Node Result", b"# Wrong Result", 1), "native result top heading must be exactly # Review Node Result"),
        (original.replace(b"## Findings\n\n", b"", 1), "native result must contain exactly one ## Findings section"),
        (_replace_native_preamble(original, "## Skill Loading", ""), "native result Review Node Result header"),
        (
            _replace_native_preamble(original, "## Skill Loading", header.replace("- Status: completed", "- Status: blocked", 1)),
            "native result Review Node Result header Status values do not match",
        ),
    )

    for content, expected_blocker in variants:
        rebased_proof, rebased_manifest, rebased_verifier = _rebase_artifact_payload(proof, manifest, verifier, evidence_id=evidence_id, content=content)
        result = assess_evidence_bundle(
            expectation,
            rebased_proof,
            review_records=review_records,
            validation_records=validation_records,
            artifact_manifest=rebased_manifest,
            trusted_verifier=rebased_verifier,
        )

        assert not result.feasible
        assert any(expected_blocker in blocker for blocker in result.blockers)


def test_evidence_bundle_rejects_independent_native_semantic_adversaries() -> None:
    expectation = _repository_review_expectation(include_independent=True)
    expectation, proof, review_records, validation_records, _, _ = _verified_binding(expectation)
    review_records = tuple(
        (record_expectation, replace(evidence, status="completed", finding_ids=("independent-1", "independent-2")))
        if record_expectation.mode == "independent-review"
        else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, review_records, validation_records = _artifact_verification(proof, review_records, validation_records)
    evidence_id = next(evidence.evidence_id for record_expectation, evidence in review_records if record_expectation.mode == "independent-review")
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    original = next(artifact.content for artifact in verifier.artifacts if artifact.artifact_id == artifact_id)
    independent_sections = (
        "## Scope Inspected",
        "## Findings",
        "## No-Finding Evidence",
        "## Routing Handoffs",
        "## Fingerprint Proof",
        "## Git State",
        "## Review Graph Envelope",
        "## Machine Evidence",
    )
    swapped = (
        original.replace(b"- ID: independent-1", b"- ID: temporary", 1)
        .replace(b"- ID: independent-2", b"- ID: independent-1", 1)
        .replace(b"- ID: temporary", b"- ID: independent-2", 1)
    )
    trusted_target = "git diff origin/main...HEAD -- src/state.rs tests/state_test.py"
    trusted_paths = "src/state.rs, tests/state_test.py"
    unrelated_target = _replace_in_native_section(
        _replace_in_native_section(original, "## Scope Inspected", "## Findings", trusted_target, "git diff -- unrelated.txt"),
        "## Review Graph Envelope",
        "## Machine Evidence",
        trusted_target,
        "git diff -- unrelated.txt",
    )
    path_variants = tuple(
        _replace_in_native_section(
            _replace_in_native_section(original, "## Scope Inspected", "## Findings", trusted_paths, replacement),
            "## Review Graph Envelope",
            "## Machine Evidence",
            trusted_paths,
            replacement,
        )
        for replacement in ("src/state.rs", "src/state.rs, tests/state_test.py, unrelated.txt", "tests/state_test.py, src/state.rs")
    )
    mismatched_results = _replace_in_native_section(
        original, "## Review Graph Envelope", "## Machine Evidence", "  - Result: matched", "  - Result: mismatched"
    )
    mismatched_results = _replace_in_native_section(
        mismatched_results, "## Review Graph Envelope", "## Machine Evidence", "  - Result: matched", "  - Result: mismatched"
    )
    id_only_findings = _replace_native_section(original, "## Findings", "## No-Finding Evidence", "- ID: independent-1\n- ID: independent-2")
    missing_finding_summary = _replace_in_native_section(
        original, "## Findings", "## No-Finding Evidence", "  - Summary: observed contract violation", "  - Omitted: observed contract violation"
    )
    variants = (
        _all_none_native_sections(original, independent_sections),
        original.replace(b"- ID: independent-2", b"  - Omitted ID: independent-2", 1),
        swapped,
        original.replace(b"  - Scope fingerprint: scope", b"  - Scope fingerprint: wrong", 1),
        original.replace(b"- Git state mutated: no", b"- Git state mutated: yes", 1),
        original.replace(b"- Node ID: independent-001", b"- Node ID: wrong-node", 1),
        unrelated_target,
        *path_variants,
        mismatched_results,
        _replace_native_section(original, "## Routing Handoffs", "## Fingerprint Proof", "- Handoff ID: independent-001-handoff-extra"),
        _replace_in_native_section(
            original, "## Review Graph Envelope", "## Machine Evidence", "- Limitations: none", "- Limitations: target was not inspected"
        ),
        id_only_findings,
        missing_finding_summary,
        original.replace(b"  - Location: src/state.rs:1", b"  - Location: src/state.rs:999999999", 1),
    )

    accepted = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    assert accepted.feasible
    for ordinal, content in enumerate(variants):
        rebased_proof, rebased_manifest, rebased_verifier = _rebase_artifact_payload(proof, manifest, verifier, evidence_id=evidence_id, content=content)
        result = assess_evidence_bundle(
            expectation,
            rebased_proof,
            review_records=review_records,
            validation_records=validation_records,
            artifact_manifest=rebased_manifest,
            trusted_verifier=rebased_verifier,
        )

        assert not result.feasible
        assert any("native" in blocker for blocker in result.blockers), (ordinal, result.blockers)


def test_evidence_bundle_requires_proof_to_preserve_accepted_independent_handoffs() -> None:
    expectation = _repository_review_expectation(include_independent=True)
    expectation, proof, review_records, validation_records, _, _ = _verified_binding(expectation)
    handoff_id = "independent-001-handoff-1"
    handoff_records = tuple(
        (record_expectation, replace(evidence, handoff_ids=(handoff_id,)))
        if record_expectation.mode == "independent-review"
        else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, handoff_records, validation_records = _artifact_verification(proof, handoff_records, validation_records)

    omitted = assess_evidence_bundle(
        expectation, proof, review_records=handoff_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    preserved = assess_evidence_bundle(
        expectation,
        replace(proof, unresolved_handoff_ids=(handoff_id,)),
        review_records=handoff_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )

    assert not omitted.feasible
    assert "repository review proof unresolved handoffs do not equal accepted review evidence handoffs" in omitted.blockers
    assert not preserved.feasible
    assert f"repository review proof has unresolved routing handoffs: {handoff_id}" in preserved.blockers


def test_evidence_bundle_rejects_all_none_ordinary_review_sections() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    evidence_id = "review:audit-001:repository"
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    original = next(artifact.content for artifact in verifier.artifacts if artifact.artifact_id == artifact_id)
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
    content = _all_none_native_sections(original, sections)
    rebased_proof, rebased_manifest, rebased_verifier = _rebase_artifact_payload(proof, manifest, verifier, evidence_id=evidence_id, content=content)

    result = assess_evidence_bundle(
        expectation,
        rebased_proof,
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=rebased_manifest,
        trusted_verifier=rebased_verifier,
    )

    assert not result.feasible
    assert any("native result Review Skill Loading" in blocker for blocker in result.blockers)


def test_evidence_bundle_rejects_forged_ordinary_review_references_after_rebinding() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    evidence_id = "review:audit-001:repository"
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    original = next(artifact.content for artifact in verifier.artifacts if artifact.artifact_id == artifact_id)
    review_expectation = next(record_expectation for record_expectation, evidence in review_records if evidence.evidence_id == evidence_id)
    reference_path, reference_digest = review_expectation.reference_digests[0]
    forged = original.replace(f"- References loaded: {reference_path}".encode(), b"- References loaded: /forged/ref.md", 1).replace(
        f"- Reference digests: {reference_path}={reference_digest}".encode(), b"- Reference digests: /forged/ref.md=sha256:forged", 1
    )
    rebased_proof, rebased_manifest, rebased_verifier = _rebase_artifact_payload(proof, manifest, verifier, evidence_id=evidence_id, content=forged)

    result = assess_evidence_bundle(
        expectation,
        rebased_proof,
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=rebased_manifest,
        trusted_verifier=rebased_verifier,
    )

    assert not result.feasible
    assert any("native result Review Skill Loading" in blocker for blocker in result.blockers)


def test_evidence_bundle_rejects_consistently_rebound_ordinary_review_provenance() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    rebound_records = tuple(
        (
            replace(record_expectation, skill_digest="sha256:forged-review", reference_digests=(("/forged/review.md", "sha256:forged"),)),
            replace(evidence, skill_digest="sha256:forged-review", reference_digests=(("/forged/review.md", "sha256:forged"),)),
        )
        if evidence.evidence_id == "review:audit-001:repository"
        else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, rebound_records, validation_records = _artifact_verification(proof, rebound_records, validation_records)

    result = assess_evidence_bundle(
        expectation, proof, review_records=rebound_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert "review evidence expectation identity does not match planned node audit-001" in result.blockers
    assert "review evidence envelope identity does not match planned node audit-001" in result.blockers


def test_evidence_bundle_rejects_consistently_rebound_validator_provenance() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    record_expectation, evidence = validation_records[0]
    rebound_expectation = replace(record_expectation, skill_digest="sha256:forged-validator", reference_digests=(("/forged/validator.md", "sha256:forged"),))
    rebound_evidence = replace(evidence, skill_digest=rebound_expectation.skill_digest, reference_digests=rebound_expectation.reference_digests)
    proof, manifest, verifier, review_records, validation_records = _artifact_verification(proof, review_records, ((rebound_expectation, rebound_evidence),))

    result = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert "planned validation evidence identity does not match node validation-001" in result.blockers
    assert "planned validation evidence envelope provenance does not match node validation-001" in result.blockers


def test_evidence_bundle_rejects_consistently_rebound_validator_dispatch() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    record_expectation, evidence = validation_records[0]
    forged_unit = replace(
        record_expectation.validation_unit,
        commands=("forged-validator-command",),
        working_directories=("/forged",),
        canonical_recipe="forged-validator-command",
    )
    rebound_expectation = validation_evidence_expectation(
        forged_unit,
        skill_path=record_expectation.skill_path,
        skill_digest=record_expectation.skill_digest,
        reference_digests=record_expectation.reference_digests,
        execution_profile=record_expectation.execution_profile,
        execution_location=record_expectation.execution_location,
    )
    rebound_evidence = replace(
        evidence, command_identity_digest=rebound_expectation.command_identity_digest, environment_digest=rebound_expectation.environment_digest
    )
    proof, manifest, verifier, review_records, validation_records = _artifact_verification(proof, review_records, ((rebound_expectation, rebound_evidence),))

    result = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert "planned validation evidence identity does not match node validation-001" in result.blockers


def test_evidence_bundle_rejects_validation_native_semantic_adversaries() -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    evidence_id = "review-validator:validation-001:repository"
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    original = next(artifact.content for artifact in verifier.artifacts if artifact.artifact_id == artifact_id)
    validation_expectation, _ = validation_records[0]
    reference_path, reference_digest = validation_expectation.reference_digests[0]
    forged_provenance = (
        original.replace(f"- Skill file: {validation_expectation.skill_path}".encode(), b"- Skill file: /forged/skill.md", 1)
        .replace(f"- References loaded: {reference_path}".encode(), b"- References loaded: /forged/reference.md", 1)
        .replace(f"- Reference digests: {reference_path}={reference_digest}".encode(), b"- Reference digests: /forged/reference.md=sha256:forged", 1)
        .replace(b"## Artifacts\n\nnone", b"## Artifacts\n\n- Path: source-controlled.txt\n  - Kind: log\n  - Repository status: tracked", 1)
        .replace(b"- Consumer: review-graph", b"- Consumer: attacker", 1)
    )
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
    variants = (
        _all_none_native_sections(original, sections),
        _replace_native_preamble(original, "## Outcome Summary", ""),
        _replace_in_native_section(original, "## Outcome Summary", "## Skill Loading", "- Requirements: passed 2", "- Requirements: passed 1"),
        _replace_native_section(original, "## Validation Plan", "## State Verification", "- Requirement: V01\n  - Command: just ci"),
        _replace_native_section(original, "## Requirements", "## Executions", "- Requirement: V01\n  - Disposition: passed"),
        _replace_in_native_section(original, "## Executions", "## Reused Evidence", "  - Result: passed", "  - Result: failed"),
        _replace_in_native_section(original, "## Executions", "## Reused Evidence", "  - Command: just ci", "  - Command: just wrong"),
        _replace_native_section(
            original, "## Executions", "## Reused Evidence", "- Execution ID: validation-001-exec-1\n  - Command: just ci\n  - Result: passed"
        ),
        forged_provenance,
    )

    for content in variants:
        rebased_proof, rebased_manifest, rebased_verifier = _rebase_artifact_payload(proof, manifest, verifier, evidence_id=evidence_id, content=content)
        result = assess_evidence_bundle(
            expectation,
            rebased_proof,
            review_records=review_records,
            validation_records=validation_records,
            artifact_manifest=rebased_manifest,
            trusted_verifier=rebased_verifier,
        )

        assert not result.feasible
        assert any("native validation result" in blocker or "native result" in blocker for blocker in result.blockers)


def test_native_artifact_structure_not_report_complete_boolean_proves_completeness() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    review_records = tuple(
        (record_expectation, replace(evidence, report_complete=False))
        if evidence.evidence_id == "review:audit-001:repository"
        else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, review_records, validation_records = _artifact_verification(proof, review_records, validation_records)

    result = assess_evidence_bundle(
        expectation, proof, review_records=review_records, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert result.feasible


@pytest.mark.parametrize(
    ("evidence_id", "field", "value", "expected_blocker"),
    [
        ("review:audit-001:repository", "node_id", "different-node", "native review result node_id does not match its evidence envelope"),
        (
            "review-validator:validation-001:repository",
            "validation_status",
            "failed",
            "native validation result validation_status does not match its evidence envelope",
        ),
    ],
)
def test_native_artifact_payload_must_match_review_and_validation_envelopes(evidence_id: str, field: str, value: object, expected_blocker: str) -> None:
    expectation, proof, review_records, validation_records, manifest, verifier = _evidence_bundle_fixture()
    artifact_id = next(entry.artifact_id for entry in manifest.entries if entry.evidence_id == evidence_id)
    original = next(artifact.content for artifact in verifier.artifacts if artifact.artifact_id == artifact_id)
    text = original.decode()
    start = text.index(NATIVE_EVIDENCE_BLOCK_OPEN) + len(NATIVE_EVIDENCE_BLOCK_OPEN)
    end = text.index(NATIVE_EVIDENCE_BLOCK_CLOSE, start)
    payload = json.loads(text[start:end])
    payload[field] = value
    changed = _replace_native_block(original, json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    rebased_proof, rebased_manifest, rebased_verifier = _rebase_artifact_payload(proof, manifest, verifier, evidence_id=evidence_id, content=changed)

    result = assess_evidence_bundle(
        expectation,
        rebased_proof,
        review_records=review_records,
        validation_records=validation_records,
        artifact_manifest=rebased_manifest,
        trusted_verifier=rebased_verifier,
    )

    assert not result.feasible
    assert any(expected_blocker in blocker for blocker in result.blockers)


def test_synthesis_native_payload_and_typed_evidence_require_planner_predecessor_coverage() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    missing_predecessors = tuple(
        (replace(record_expectation, predecessor_evidence_ids=()), replace(evidence, predecessor_evidence_ids=()))
        if evidence.evidence_id == proof.final_synthesis_evidence_id
        else (record_expectation, evidence)
        for record_expectation, evidence in review_records
    )
    proof, manifest, verifier, missing_predecessors, validation_records = _artifact_verification(proof, missing_predecessors, validation_records)

    result = assess_evidence_bundle(
        expectation, proof, review_records=missing_predecessors, validation_records=validation_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not result.feasible
    assert "synthesis expectation predecessor evidence does not match planner mappings: repository-synthesis" in result.blockers
    assert "synthesis evidence predecessor coverage does not match planner mappings: repository-synthesis" in result.blockers


def test_review_proof_mappings_reject_mismatched_empty_and_swapped_ownership() -> None:
    _, _, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    audit_expectation, audit_evidence = review_records[0]
    second_expectation = replace(
        audit_expectation, node_id="audit-002", requirement_ids=("R02",), skill_id="specialist-02", skill_path="/skills/specialist-02/SKILL.md"
    )
    second_evidence = replace(
        audit_evidence,
        evidence_id="review:audit-002:repository",
        node_id="audit-002",
        requirement_ids=("R02",),
        skill_id="specialist-02",
        skill_path="/skills/specialist-02/SKILL.md",
        raw_result_artifact_id="artifact://audit-002",
        raw_result_digest=_result_digest("review:audit-002:repository"),
    )
    complete_records = (review_records[0], (second_expectation, second_evidence), review_records[1])
    complete_expectation = _repository_review_expectation(review_count=2)
    complete_proof = _repository_review_proof(complete_expectation)
    complete_proof, manifest, verifier, complete_records, validation_records = _artifact_verification(complete_proof, complete_records, validation_records)
    mismatched_records = ((replace(audit_expectation, requirement_ids=()), audit_evidence), *complete_records[1:])
    empty_proof = replace(
        complete_proof,
        required_review_requirement_ids=("", "R02"),
        review_requirement_evidence=(("", "review:audit-001:repository"), ("R02", "review:audit-002:repository")),
    )
    swapped_proof = replace(complete_proof, review_requirement_evidence=(("R01", "review:audit-002:repository"), ("R02", "review:audit-001:repository")))

    mismatch = assess_evidence_bundle(
        complete_expectation,
        replace(complete_proof, plan_digest=complete_expectation.plan_digest),
        review_records=mismatched_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )
    empty = assess_evidence_bundle(
        complete_expectation,
        replace(empty_proof, plan_digest=complete_expectation.plan_digest),
        review_records=complete_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )
    swapped = assess_evidence_bundle(
        complete_expectation,
        replace(swapped_proof, plan_digest=complete_expectation.plan_digest),
        review_records=complete_records,
        validation_records=validation_records,
        artifact_manifest=manifest,
        trusted_verifier=verifier,
    )

    assert not mismatch.feasible
    assert any("review proof requirement is not owned by its evidence expectation" in blocker for blocker in mismatch.blockers)
    assert not empty.feasible
    assert "review proof mappings must contain non-empty IDs" in empty.blockers
    assert not swapped.feasible
    assert sum("review proof requirement is not owned" in blocker for blocker in swapped.blockers) == 4


def test_validation_proof_mappings_reject_mismatched_empty_and_swapped_ownership() -> None:
    expectation, proof, review_records, validation_records, _, _ = _evidence_bundle_fixture()
    first_expectation, first_evidence = validation_records[0]
    first_expectation = replace(first_expectation, requirement_ids=("V01",))
    first_evidence = replace(first_evidence, requirement_ids=("V01",))
    second_expectation = replace(first_expectation, node_id="validation-002", requirement_ids=("V02",))
    second_evidence = replace(
        first_evidence,
        evidence_id="review-validator:validation-002:repository",
        node_id="validation-002",
        requirement_ids=("V02",),
        raw_result_artifact_id="artifact://validation-002",
        raw_result_digest=_result_digest("review-validator:validation-002:repository"),
    )
    complete_records = ((first_expectation, first_evidence), (second_expectation, second_evidence))
    complete_proof = replace(
        proof,
        validation_requirement_evidence=(("V01", "review-validator:validation-001:repository"), ("V02", "review-validator:validation-002:repository")),
        accepted_validation_evidence_ids=("review-validator:validation-001:repository", "review-validator:validation-002:repository"),
    )
    complete_proof, manifest, verifier, review_records, complete_records = _artifact_verification(complete_proof, review_records, complete_records)
    mismatched_records = ((replace(first_expectation, requirement_ids=()), first_evidence), complete_records[1])
    empty_proof = replace(
        complete_proof,
        required_validation_requirement_ids=("", "V02"),
        validation_requirement_evidence=(("", "review-validator:validation-001:repository"), ("V02", "review-validator:validation-002:repository")),
    )
    swapped_proof = replace(
        complete_proof,
        validation_requirement_evidence=(("V01", "review-validator:validation-002:repository"), ("V02", "review-validator:validation-001:repository")),
    )

    mismatch = assess_evidence_bundle(
        expectation, complete_proof, review_records=review_records, validation_records=mismatched_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    empty = assess_evidence_bundle(
        expectation, empty_proof, review_records=review_records, validation_records=complete_records, artifact_manifest=manifest, trusted_verifier=verifier
    )
    swapped = assess_evidence_bundle(
        expectation, swapped_proof, review_records=review_records, validation_records=complete_records, artifact_manifest=manifest, trusted_verifier=verifier
    )

    assert not mismatch.feasible
    assert any("validation proof requirement is not owned by its evidence expectation" in blocker for blocker in mismatch.blockers)
    assert not empty.feasible
    assert "validation proof mappings must contain non-empty IDs" in empty.blockers
    assert not swapped.feasible
    assert sum("validation proof requirement is not owned" in blocker for blocker in swapped.blockers) == 4


def test_representative_rust_python_docs_fixture_stays_within_budget() -> None:
    fixture = Path(__file__).with_name("fixtures") / "representative_rust_python_docs.json"
    plan = plan_from_document(json.loads(fixture.read_text(encoding="utf-8")))

    assert plan.dispatch_allowed
    assert plan.execution_profile == "grouped"
    assert plan.execution_epochs == ()
    assert plan.current_epoch_node_ids == ()
    assert not plan.requires_continuation
    assert {"rust-synthesis", "python-synthesis", "repository-synthesis"} <= set(plan.synthesis_nodes)
    assert any(unit.baseline for unit in plan.coalesced_validation_units)
    order = [node.node_id for node in plan.actual_worker_nodes]
    assert order.index("validation-001") < order.index("rust-synthesis")
    assert order.index("validation-002") < order.index("python-synthesis")
    assert any("la-stack.md" in reference for item in json.loads(fixture.read_text())["review_requirements"] for reference in item["static_references"])
