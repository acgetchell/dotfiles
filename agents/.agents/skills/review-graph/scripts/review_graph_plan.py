"""Deterministic planning checks for review-graph orchestration."""

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from capture_scope import _scope_data

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

_REQUIRED_CAPACITY_FIELDS = frozenset({"active_workers", "concurrent_worker_limit", "source"})
_OPTIONAL_CAPACITY_FIELDS = frozenset({"fresh_worker_creations_remaining", "lifecycle_semantics"})
_CAPACITY_FIELDS = _REQUIRED_CAPACITY_FIELDS | _OPTIONAL_CAPACITY_FIELDS
_CONTEXT_KEYS = frozenset(
    {
        "analysis",
        "content",
        "final_answer",
        "final_report",
        "finding",
        "findings",
        "message",
        "messages",
        "native_report",
        "output",
        "payload",
        "report",
        "reports",
        "result",
        "results",
    }
)

DEFAULT_TOTAL_FRESH_WORKER_BUDGET = 24
DEFAULT_RECOVERY_FINALIZATION_RESERVE = 1
EVIDENCE_SCHEMA_VERSION = 1
REPOSITORY_ROUTER_ID = "review-graph"
FINAL_SYNTHESIS_IDENTITY = ("repository-synthesis", "repository-production-review", "synthesis")
NATIVE_EVIDENCE_BLOCK_OPEN = "<!-- review-graph-evidence-v1\n"
NATIVE_EVIDENCE_BLOCK_CLOSE = "\n-->"
MAX_NATIVE_RESULT_BYTES = 1_048_576
MAX_NATIVE_EVIDENCE_BLOCK_BYTES = 65_536
MAX_NATIVE_SECTION_BYTES = 65_536
MAX_NATIVE_IDENTIFIER_LENGTH = 4_096
MAX_NATIVE_IDENTIFIER_COUNT = 1_024
_REVIEW_RESULT_SECTIONS = (
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
_INDEPENDENT_RESULT_SECTIONS = (
    "## Scope Inspected",
    "## Findings",
    "## No-Finding Evidence",
    "## Routing Handoffs",
    "## Fingerprint Proof",
    "## Git State",
    "## Review Graph Envelope",
    "## Machine Evidence",
)
_VALIDATION_RESULT_SECTIONS = (
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
_COMMON_NATIVE_EVIDENCE_KEYS = frozenset(
    {
        "after_repository_state_fingerprint",
        "after_scope_fingerprint",
        "after_worktree_fingerprint",
        "artifact_id",
        "before_repository_state_fingerprint",
        "before_scope_fingerprint",
        "before_worktree_fingerprint",
        "evidence_id",
        "git_mutated",
        "mode",
        "node_id",
        "repository_state_fingerprint",
        "requirement_ids",
        "result_type",
        "schema_version",
        "scope_fingerprint",
        "skill_id",
        "source_mutated",
        "status",
        "worktree_fingerprint",
    }
)
_REVIEW_NATIVE_EVIDENCE_KEYS = _COMMON_NATIVE_EVIDENCE_KEYS | frozenset({"finding_ids", "predecessor_evidence_ids", "validation_requirement_ids"})
_INDEPENDENT_REVIEW_NATIVE_EVIDENCE_KEYS = _REVIEW_NATIVE_EVIDENCE_KEYS | frozenset({"change_target", "handoff_ids", "inspected_paths"})
_VALIDATION_NATIVE_EVIDENCE_KEYS = _COMMON_NATIVE_EVIDENCE_KEYS | frozenset({"command_identity_digest", "environment_digest", "validation_status"})
PRIORITY_ORDER = {"required-routing-synthesis": 0, "correctness-invariants": 1, "required-validation": 2, "supporting-quality": 3, "optional-hygiene": 4}
ROUTING_DISPOSITIONS = frozenset({"selected", "not-applicable", "exact-evidence-reused", "user-excluded", "budget-deferred", "capability-blocked", "failed"})
COMPLETION_BLOCKING_DISPOSITIONS = frozenset({"budget-deferred", "capability-blocked", "failed"})
ROUTING_TARGET_KINDS = frozenset({"router", "leaf", "synthesis", "independent"})
ROUTING_LAYERS = frozenset({"repository", "surface", "finalization"})
DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"
_FRONTMATTER_NAME = re.compile(r"^name:\s*[\"']?([^\"'\s]+)[\"']?\s*$")


@dataclass(frozen=True)
class Assessment:
    """One deterministic feasibility or reconciliation result."""

    feasible: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class CapacityAssessment(Assessment):
    """Concurrent capacity and optional lifetime-capacity forecast."""

    fresh_worker_creations_remaining: int | None
    required_fresh_worker_creations: int
    free_concurrent_slots: int | None
    required_peak_workers: int
    full_plan_creation_capacity_guaranteed: bool | None


@dataclass(frozen=True)
class ExecutionProfileAssessment(Assessment):
    """Selected delivery profile before repository routing or graph planning."""

    profile: str
    reason: str
    isolated_requested: bool
    isolated_only: bool
    configured_worker_budget: int | None = None
    effective_worker_budget: int | None = None


@dataclass(frozen=True)
class PlanNode:
    """One bounded node in a sequential or dependency-driven schedule."""

    node_id: str
    elapsed_seconds: int
    predecessors: tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetAssessment(Assessment):
    """Hard-deadline readiness without treating node caps as reservations."""

    critical_path_seconds: int
    coordinator_reserve_seconds: int
    validation_reserve_seconds: int
    fix_revalidation_reserve_seconds: int
    required_seconds: int
    overall_budget_seconds: int | None
    dispatch_window_seconds: int | None
    completion_guaranteed_with_caps: bool | None
    policy: str


@dataclass(frozen=True)
class TimeBudget:
    """Graph-wide hard deadline and explicit non-worker reserves."""

    overall_seconds: int | None
    coordinator_reserve_seconds: int
    validation_reserve_seconds: int
    fix_revalidation_reserve_seconds: int = 0
    sequential: bool = True


@dataclass(frozen=True)
class RoutingGuard:
    """Result of the narrow packaged-Python routing guard."""

    selected_skills: tuple[str, ...]
    packaging_signals: tuple[str, ...]
    added_python_build_portability: bool


@dataclass(frozen=True)
class RoutingCatalogEntry:
    """One canonical candidate owned by one routing authority."""

    catalog_id: str
    router_id: str
    rule_id: str
    layer: str
    surface: str
    skill_id: str
    skill_path: str
    target_kind: str
    default_priority: str
    synthesis_dependency: str | None
    required_static_references: tuple[str, ...] = ()
    path_patterns: tuple[str, ...] = ()
    semantic_triggers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingDecision:
    """One exhaustive router disposition for one catalog candidate."""

    catalog_id: str
    requirement_id: str
    router_id: str
    rule_id: str
    skill_id: str
    skill_path: str
    disposition: str
    reason: str
    applicability_evidence: tuple[str, ...]
    review_surface: tuple[str, ...] = ()
    instruction_paths: tuple[str, ...] = ()
    static_references: tuple[str, ...] = ()
    validation_requirement_ids: tuple[str, ...] = ()
    synthesis_dependency: str | None = None
    priority: str | None = None
    owners: tuple[str, ...] = ()
    evidence_id: str | None = None


@dataclass(frozen=True)
class RoutingDiscovery:
    """One late applicability handoff emitted by an accepted worker."""

    handoff_id: str
    source_node_id: str
    catalog_id: str
    evidence: str


@dataclass(frozen=True)
class ReusedReviewEvidencePlan:
    """Planner-owned identity for one routed non-executable evidence record."""

    requirement_id: str
    evidence_id: str
    skill_id: str
    skill_path: str
    mode: str
    static_references: tuple[str, ...]
    skill_digest: str = ""
    reference_digests: tuple[tuple[str, str], ...] = ()
    change_target: str | None = None
    planned_paths: tuple[str, ...] = ()
    planned_path_line_bounds: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class RoutingLedgerAssessment(Assessment):
    """Syntactic and semantic closure proof for all consulted routers."""

    selected_requirement_ids: tuple[str, ...]
    exact_reused_review_evidence: tuple[tuple[str, str], ...]
    reused_review_identities: tuple[ReusedReviewEvidencePlan, ...]
    user_excluded_catalog_ids: tuple[str, ...]
    completion_blocking_catalog_ids: tuple[str, ...]
    consulted_routers: tuple[str, ...]
    catalog_closed: bool


@dataclass(frozen=True)
class ExecutionEpoch:
    """One per-root bounded slice of a complete required graph."""

    ordinal: int
    node_ids: tuple[str, ...]
    worker_budget: int
    recovery_finalization_reserve: int
    requires_fresh_root: bool


@dataclass(frozen=True)
class ExecutionLedger:
    """Lifecycle sets used by final graph reconciliation."""

    selected_nodes: tuple[str, ...]
    accepted_nodes: tuple[str, ...]
    blocked_after_execution: tuple[str, ...]
    blocked_before_execution: tuple[str, ...]
    invalidated_nodes: tuple[str, ...]
    worker_attempts: tuple[str, ...]
    workers_created: tuple[str, ...]
    worker_creation_failures: tuple[str, ...]
    skills_executed: tuple[str, ...]
    planned_validators: tuple[str, ...]
    executed_validators: tuple[str, ...]
    validators_not_run: tuple[str, ...]
    coordinator_executions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewRequirement:
    """One declarative router selection before worker-node coalescing."""

    requirement_id: str
    skill_id: str
    skill_path: str
    router_id: str
    rule_id: str
    review_surface: tuple[str, ...]
    reason: str
    priority: str
    synthesis_dependency: str | None
    required: bool = False
    static_references: tuple[str, ...] = ()
    instruction_paths: tuple[str, ...] = ()
    validation_requirement_ids: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    skill_digest: str = ""
    reference_digests: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ValidationRequirement:
    """One declared validation need before compatible needs are coalesced."""

    requirement_id: str
    source_state: tuple[str, str, str]
    commands: tuple[str, ...]
    working_directories: tuple[str, ...]
    environment: str
    toolchain: str
    features: tuple[str, ...]
    platform: str
    artifact_owner: str
    mutation_lock: str
    request: str = "validate graph-dispatched requirements"
    requested_scope: str = "branch"
    capture_command: str = "capture_scope.py --mode branch"
    captured_paths: tuple[str, ...] = ()
    authority: str = "graph dispatch"
    selection_reason: str = "graph-dispatched validation requirement"
    mutation_classification: str = "non-mutating under validation-only"
    expected_evidence: str = "exact dispatched commands complete with recorded outcomes"
    elapsed_time_budget: str = "300s"
    dependency_policy: str = "stop-on-failure"
    meaningful_skips: tuple[str, ...] = ()
    execution_strategy: str = "sequential"
    independence_basis: str = "none"
    planning_blocker: str | None = None
    allowed_artifacts: tuple[tuple[str, str, str], ...] = ()
    canonical_recipe: str | None = None
    evidence_id: str | None = None
    required: bool = True
    baseline: bool = False


@dataclass(frozen=True)
class ValidationUnit:
    """One fresh validator worker satisfying compatible requirements."""

    node_id: str
    requirement_ids: tuple[str, ...]
    source_state: tuple[str, str, str]
    commands: tuple[str, ...]
    working_directories: tuple[str, ...]
    environment: str
    toolchain: str
    features: tuple[str, ...]
    platform: str
    artifact_owner: str
    mutation_lock: str
    request: str
    requested_scope: str
    capture_command: str
    captured_paths: tuple[str, ...]
    requirement_plans: tuple[tuple[str, str, str, str, str, str, str | None], ...]
    dependency_policy: str
    meaningful_skips: tuple[str, ...]
    execution_strategy: str
    independence_basis: str
    planning_blocker: str | None
    allowed_artifacts: tuple[tuple[str, str, str], ...]
    canonical_recipe: str | None
    evidence_ids: tuple[str, ...]
    required: bool
    baseline: bool


@dataclass(frozen=True)
class ValidationEvidenceMapping:
    """Map one declared requirement to its verifier and reusable evidence."""

    requirement_id: str
    validation_unit_id: str
    evidence_id: str | None


@dataclass(frozen=True)
class WorkerNode:
    """One actual fresh-worker node after routing and validator coalescing."""

    node_id: str
    skill_id: str
    skill_path: str
    mode: str
    priority: str
    required: bool
    requirement_ids: tuple[str, ...] = ()
    coverage: tuple[str, ...] = ()
    predecessors: tuple[str, ...] = ()
    synthesis_dependency: str | None = None
    router_ids: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    selection_reasons: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    instruction_paths: tuple[str, ...] = ()
    static_references: tuple[str, ...] = ()
    change_target: str | None = None
    skill_digest: str = ""
    reference_digests: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class WorkerBudget:
    """Configured total fresh creations and protected reserve."""

    total: int = DEFAULT_TOTAL_FRESH_WORKER_BUDGET
    recovery_finalization_reserve: int = DEFAULT_RECOVERY_FINALIZATION_RESERVE


@dataclass(frozen=True)
class GraphPlan:
    """Complete required graph, partitioned only for isolated scheduling."""

    execution_profile: str
    worker_budget: int
    recovery_finalization_reserve: int
    selected_review_requirements: tuple[str, ...]
    complete_node_count: int
    actual_worker_nodes: tuple[WorkerNode, ...]
    execution_epochs: tuple[ExecutionEpoch, ...]
    current_epoch_node_ids: tuple[str, ...]
    requires_continuation: bool
    coalesced_validation_units: tuple[ValidationUnit, ...]
    selected_validation_units: tuple[str, ...]
    synthesis_nodes: tuple[str, ...]
    requirement_to_node: tuple[tuple[str, str], ...]
    validation_evidence_mapping: tuple[ValidationEvidenceMapping, ...]
    captured_path_line_bounds: tuple[tuple[str, int], ...]
    routing_catalog_closed: bool
    consulted_routers: tuple[str, ...]
    exact_reused_review_evidence: tuple[tuple[str, str], ...]
    reused_review_identities: tuple[ReusedReviewEvidencePlan, ...]
    user_excluded_catalog_ids: tuple[str, ...]
    routing_completion_blockers: tuple[str, ...]
    dispatch_allowed: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class FingerprintEvidence:
    """Expected and observed source identities for one worker report."""

    expected: tuple[str, str, str]
    before: tuple[str, str, str]
    after: tuple[str, str, str]


@dataclass(frozen=True)
class ReviewEvidenceExpectation:
    """Dispatch identity that one persisted review result must prove."""

    node_id: str
    requirement_ids: tuple[str, ...]
    skill_id: str
    mode: str
    skill_path: str
    skill_digest: str
    reference_digests: tuple[tuple[str, str], ...]
    source_state: tuple[str, str, str]
    execution_profile: str
    selection_reason: str
    authorization: str
    expected_after_state: tuple[str, str, str] | None = None
    source_mutation_allowed: bool = False
    predecessor_evidence_ids: tuple[str, ...] = ()
    change_target: str | None = None
    planned_paths: tuple[str, ...] = ()
    planned_path_line_bounds: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ReviewEvidence:
    """Versioned proof envelope for one review skill execution."""

    schema_version: int
    evidence_id: str
    node_id: str
    requirement_ids: tuple[str, ...]
    skill_id: str
    mode: str
    skill_path: str
    skill_digest: str
    reference_digests: tuple[tuple[str, str], ...]
    fingerprints: FingerprintEvidence
    execution_profile: str
    execution_location: str
    worker_created: bool
    fresh_context: bool
    status: str
    finding_ids: tuple[str, ...]
    validation_requirement_ids: tuple[str, ...]
    handoff_ids: tuple[str, ...]
    raw_result_artifact_id: str
    raw_result_digest: str
    report_complete: bool
    source_mutated: bool = False
    git_mutated: bool = False
    predecessor_evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlannedEvidenceNode:
    """Exact executable node identity derived from an accepted graph plan."""

    node_id: str
    skill_id: str
    skill_path: str
    skill_digest: str
    reference_digests: tuple[tuple[str, str], ...]
    mode: str
    predecessors: tuple[str, ...]
    validation_unit_digest: str | None = None
    change_target: str | None = None
    planned_paths: tuple[str, ...] = ()
    planned_path_line_bounds: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ValidationEvidenceExpectation:
    """Dispatch identity that one persisted validator result must prove."""

    node_id: str
    requirement_ids: tuple[str, ...]
    skill_path: str
    skill_digest: str
    reference_digests: tuple[tuple[str, str], ...]
    source_state: tuple[str, str, str]
    execution_profile: str
    execution_location: str
    validation_unit: ValidationUnit
    command_identity_digest: str = field(init=False)
    environment_digest: str = field(init=False)

    def __post_init__(self) -> None:
        """Derive trusted identities from the exact validator dispatch."""
        object.__setattr__(self, "command_identity_digest", validation_command_identity_digest(self.validation_unit))
        object.__setattr__(self, "environment_digest", validation_environment_digest(self.validation_unit))


@dataclass(frozen=True)
class ValidationEvidence:
    """Versioned proof envelope for one review-validator result."""

    schema_version: int
    evidence_id: str
    node_id: str
    requirement_ids: tuple[str, ...]
    skill_digest: str
    reference_digests: tuple[tuple[str, str], ...]
    fingerprints: FingerprintEvidence
    execution_profile: str
    execution_location: str
    worker_created: bool
    fresh_context: bool
    status: str
    command_identity_digest: str
    environment_digest: str
    raw_result_artifact_id: str
    raw_result_digest: str
    source_mutated: bool = False
    git_mutated: bool = False


@dataclass(frozen=True)
class EvidenceAssessment(Assessment):
    """Structural acceptance plus whether evidence completes its requirements."""

    satisfies_requirements: bool


@dataclass(frozen=True)
class RepositoryReviewProof:
    """Deterministic final mapping from applicable requirements to evidence."""

    schema_version: int
    proof_id: str
    plan_digest: str
    source_state: tuple[str, str, str]
    planned_node_evidence: tuple[tuple[str, str], ...]
    required_review_requirement_ids: tuple[str, ...]
    review_requirement_evidence: tuple[tuple[str, str], ...]
    exact_reused_review_evidence: tuple[tuple[str, str], ...]
    accepted_review_evidence_ids: tuple[str, ...]
    required_validation_requirement_ids: tuple[str, ...]
    validation_requirement_evidence: tuple[tuple[str, str], ...]
    accepted_validation_evidence_ids: tuple[str, ...]
    stale_evidence_ids: tuple[str, ...]
    unresolved_handoff_ids: tuple[str, ...]
    final_synthesis_evidence_id: str
    artifact_manifest_id: str
    artifact_manifest_digest: str
    verifier_id: str


@dataclass(frozen=True)
class RepositoryReviewProofExpectation:
    """Trusted proof identity derived from one accepted graph plan."""

    plan: GraphPlan
    source_state: tuple[str, str, str]
    plan_digest: str = field(init=False)
    required_review_requirement_ids: tuple[str, ...] = field(init=False)
    review_requirement_nodes: tuple[tuple[str, str], ...] = field(init=False)
    exact_reused_review_evidence: tuple[tuple[str, str], ...] = field(init=False)
    reused_review_identities: tuple[ReusedReviewEvidencePlan, ...] = field(init=False)
    required_validation_requirement_ids: tuple[str, ...] = field(init=False)
    validation_requirement_nodes: tuple[tuple[str, str], ...] = field(init=False)
    planned_evidence_nodes: tuple[PlannedEvidenceNode, ...] = field(init=False)
    final_synthesis_identity: tuple[str, str, str] = field(init=False)

    def __post_init__(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Derive every trusted field from the exact accepted graph plan."""
        if not isinstance(self.plan, GraphPlan) or not self.plan.dispatch_allowed:
            msg = "repository review proof expectation requires an accepted graph plan"
            raise ValueError(msg)
        if len(self.source_state) != 3 or any(not _nonempty_text(value) for value in self.source_state):
            msg = "repository review proof expectation requires three source fingerprints"
            raise ValueError(msg)
        if self.plan.complete_node_count != len(self.plan.actual_worker_nodes):
            msg = "repository review proof expectation requires the complete executable graph"
            raise ValueError(msg)
        _validate_unique_ids((node.node_id for node in self.plan.actual_worker_nodes), label="planned evidence node")
        allowed_modes = {"audit", "independent-review", "synthesis", "validation"}
        invalid_modes = sorted({node.mode for node in self.plan.actual_worker_nodes} - allowed_modes)
        if invalid_modes:
            msg = "repository review proof expectation contains transition-only or unsupported executable node modes: " + ", ".join(invalid_modes)
            raise ValueError(msg)
        invalid_validators = tuple(
            node.node_id for node in self.plan.actual_worker_nodes if (node.mode == "validation") != (node.skill_id == "review-validator")
        )
        if invalid_validators:
            msg = "repository review proof expectation has invalid validation node identities: " + ", ".join(invalid_validators)
            raise ValueError(msg)
        invalid_provenance = tuple(
            node.node_id
            for node in self.plan.actual_worker_nodes
            if not _nonempty_text(node.skill_digest)
            or tuple(path for path, _ in node.reference_digests) != node.static_references
            or any(not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in node.reference_digests)
        )
        if invalid_provenance:
            msg = "repository review proof expectation lacks planner-owned skill/reference provenance: " + ", ".join(invalid_provenance)
            raise ValueError(msg)
        validation_units = {unit.node_id: unit for unit in self.plan.coalesced_validation_units}
        planned_validator_ids = {node.node_id for node in self.plan.actual_worker_nodes if node.mode == "validation"}
        if set(validation_units) != planned_validator_ids:
            msg = "repository review proof expectation validation nodes do not match exact coalesced units"
            raise ValueError(msg)
        final_synthesis_nodes = tuple(node for node in self.plan.actual_worker_nodes if (node.node_id, node.skill_id, node.mode) == FINAL_SYNTHESIS_IDENTITY)
        if len(final_synthesis_nodes) != 1:
            msg = "repository review proof expectation requires exactly one planner-derived repository synthesis node"
            raise ValueError(msg)
        reused_mapping = self.plan.exact_reused_review_evidence
        reused_identities = self.plan.reused_review_identities
        if any(not _nonempty_text(requirement_id) or not _nonempty_text(evidence_id) for requirement_id, evidence_id in reused_mapping):
            msg = "repository review proof expectation has invalid exact-reuse mappings"
            raise ValueError(msg)
        if _duplicate_values(tuple(requirement_id for requirement_id, _ in reused_mapping)):
            msg = "repository review proof expectation maps an exactly reused requirement more than once"
            raise ValueError(msg)
        identity_mapping = tuple((item.requirement_id, item.evidence_id) for item in reused_identities)
        if identity_mapping != reused_mapping:
            msg = "repository review proof expectation exact-reuse identities do not match the routed evidence mapping"
            raise ValueError(msg)
        if any(
            not _nonempty_text(item.skill_id)
            or not _nonempty_text(item.skill_path)
            or not _nonempty_text(item.skill_digest)
            or tuple(path for path, _ in item.reference_digests) != item.static_references
            or any(not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in item.reference_digests)
            for item in reused_identities
        ):
            msg = "repository review proof expectation has invalid exact-reuse skill identities"
            raise ValueError(msg)
        invalid_reuse_modes = tuple(item.requirement_id for item in reused_identities if item.mode not in {"audit", "independent-review"})
        if invalid_reuse_modes:
            msg = "repository review proof expectation has invalid exact-reuse modes: " + ", ".join(invalid_reuse_modes)
            raise ValueError(msg)
        line_bounds = dict(self.plan.captured_path_line_bounds)
        invalid_independent_bounds = tuple(
            node.node_id
            for node in self.plan.actual_worker_nodes
            if node.mode == "independent-review" and any(path not in line_bounds for path in node.coverage)
        )
        if invalid_independent_bounds:
            msg = "repository review proof expectation lacks trusted line bounds for independent nodes: " + ", ".join(invalid_independent_bounds)
            raise ValueError(msg)
        invalid_reuse_bounds = tuple(
            item.requirement_id
            for item in reused_identities
            if item.mode == "independent-review"
            and (
                any(path not in line_bounds for path in item.planned_paths)
                or item.planned_path_line_bounds != tuple((path, line_bounds[path]) for path in item.planned_paths)
            )
        )
        if invalid_reuse_bounds:
            msg = "repository review proof expectation has invalid independent exact-reuse line bounds: " + ", ".join(invalid_reuse_bounds)
            raise ValueError(msg)
        planned_requirement_ids = {requirement_id for requirement_id, _ in self.plan.requirement_to_node}
        executable_reuse = sorted(planned_requirement_ids & {requirement_id for requirement_id, _ in reused_mapping})
        if executable_reuse:
            msg = "exactly reused review requirements cannot have executable nodes: " + ", ".join(executable_reuse)
            raise ValueError(msg)
        required_review_ids = tuple(
            sorted({*self.plan.selected_review_requirements, *(requirement_id for requirement_id, _ in self.plan.exact_reused_review_evidence)})
        )
        required_validation_ids = tuple(
            sorted(requirement_id for unit in self.plan.coalesced_validation_units if unit.required or unit.baseline for requirement_id in unit.requirement_ids)
        )
        object.__setattr__(self, "plan_digest", _sha256_json(asdict(self.plan)))
        object.__setattr__(self, "required_review_requirement_ids", required_review_ids)
        object.__setattr__(
            self,
            "review_requirement_nodes",
            tuple(sorted((requirement_id, node_id) for requirement_id, node_id in self.plan.requirement_to_node if requirement_id in required_review_ids)),
        )
        object.__setattr__(self, "exact_reused_review_evidence", self.plan.exact_reused_review_evidence)
        object.__setattr__(self, "reused_review_identities", self.plan.reused_review_identities)
        object.__setattr__(self, "required_validation_requirement_ids", required_validation_ids)
        object.__setattr__(
            self,
            "validation_requirement_nodes",
            tuple(
                sorted(
                    (mapping.requirement_id, mapping.validation_unit_id)
                    for mapping in self.plan.validation_evidence_mapping
                    if mapping.requirement_id in required_validation_ids
                )
            ),
        )
        object.__setattr__(
            self,
            "planned_evidence_nodes",
            tuple(
                PlannedEvidenceNode(
                    node_id=node.node_id,
                    skill_id=node.skill_id,
                    skill_path=node.skill_path,
                    skill_digest=node.skill_digest,
                    reference_digests=node.reference_digests,
                    mode=node.mode,
                    predecessors=node.predecessors,
                    validation_unit_digest=(_sha256_json(asdict(validation_units[node.node_id])) if node.mode == "validation" else None),
                    change_target=node.change_target,
                    planned_paths=node.coverage if node.mode in {"fix", "independent-review"} else (),
                    planned_path_line_bounds=(tuple((path, line_bounds[path]) for path in node.coverage) if node.mode == "independent-review" else ()),
                )
                for node in self.plan.actual_worker_nodes
            ),
        )
        object.__setattr__(self, "final_synthesis_identity", FINAL_SYNTHESIS_IDENTITY)


@dataclass(frozen=True)
class EvidenceBundleAssessment(Assessment):
    """Typed result of verifying one complete repository evidence bundle."""

    proof_id: str
    plan_digest: str
    source_state: tuple[str, str, str]


@dataclass(frozen=True)
class ArtifactManifestEntry:
    """One accepted evidence artifact and its canonical entry digest."""

    evidence_id: str
    artifact_id: str
    artifact_digest: str
    entry_digest: str


@dataclass(frozen=True)
class ArtifactManifest:
    """Typed, independently digestible inventory of accepted result artifacts."""

    schema_version: int
    manifest_id: str
    verifier_id: str
    entries: tuple[ArtifactManifestEntry, ...]
    manifest_digest: str


@dataclass(frozen=True)
class ArtifactPayload:
    """Raw accepted result bytes supplied to the trusted verifier boundary."""

    artifact_id: str
    content: bytes


@dataclass(frozen=True)
class TrustedArtifactVerifier:
    """Verifier identity supplied by the trusted orchestration boundary."""

    verifier_id: str
    digest_algorithm: str
    artifacts: tuple[ArtifactPayload, ...]


@dataclass(frozen=True)
class NodeAcceptanceEvidence:
    """Legacy strict-isolation fields retained for manifest compatibility."""

    node_id: str
    worker_created: bool
    fresh_context: bool
    expected_skill_path: str
    loaded_skill_path: str | None
    required_static_references: tuple[str, ...]
    loaded_static_references: tuple[str, ...]
    fingerprints: FingerprintEvidence
    report_complete: bool
    timed_out: bool = False


@dataclass(frozen=True)
class ResumeNode:
    """One detailed worker commitment preserved for resumption."""

    node_id: str
    skill_id: str
    skill_path: str
    mode: str
    requirement_ids: tuple[str, ...]
    priority: str
    predecessors: tuple[str, ...]
    coverage: tuple[str, ...]
    router_ids: tuple[str, ...]
    rule_ids: tuple[str, ...]
    selection_reasons: tuple[str, ...]
    owners: tuple[str, ...]
    instruction_paths: tuple[str, ...]
    static_references: tuple[str, ...]


@dataclass(frozen=True)
class ResumeManifest:
    """Exact remaining work after dispatch halts."""

    reason: str
    source_state: tuple[str, str, str]
    undispatched_nodes: tuple[ResumeNode, ...]
    unaccepted_nodes: tuple[ResumeNode, ...]
    outstanding_validation_mappings: tuple[ValidationEvidenceMapping, ...]
    accepted_nonexecution_catalog_ids: tuple[str, ...]
    journal_location: str | None
    dispatch_halted: bool
    fresh_root_task_may_be_required: bool
    complete_node_count: int
    execution_epochs: tuple[ExecutionEpoch, ...]
    current_epoch_ordinal: int | None
    routing_catalog_closed: bool
    unresolved_handoff_ids: tuple[str, ...]
    routing_revalidation_required: bool


@dataclass(frozen=True)
class CompletionEvidence:
    """Evidence required for a complete repository review graph."""

    required_requirement_ids: tuple[str, ...]
    completed_requirement_ids: tuple[str, ...]
    # Retain legacy skip records only so older manifests fail closed.
    meaningful_skip_requirement_ids: tuple[str, ...]
    required_documentation_ids: tuple[str, ...]
    completed_documentation_ids: tuple[str, ...]
    required_validation_node_ids: tuple[str, ...]
    accepted_validation_node_ids: tuple[str, ...]
    required_synthesis_node_ids: tuple[str, ...]
    accepted_synthesis_node_ids: tuple[str, ...]
    unaccepted_node_ids: tuple[str, ...]
    undispatched_node_ids: tuple[str, ...]
    fingerprints_matched: bool
    execution_profile: str
    isolation_failures: tuple[str, ...]
    final_report_synthesized: bool
    findings_deduplicated: bool
    repository_review_expectation: RepositoryReviewProofExpectation
    repository_review_proof: RepositoryReviewProof
    review_records: tuple[tuple[ReviewEvidenceExpectation, ReviewEvidence], ...]
    validation_records: tuple[tuple[ValidationEvidenceExpectation, ValidationEvidence], ...]
    artifact_manifest: ArtifactManifest
    trusted_artifact_verifier: TrustedArtifactVerifier
    exact_reused_requirement_ids: tuple[str, ...] = ()
    completion_blocking_omission_ids: tuple[str, ...] = ()
    routing_catalog_closed: bool = True
    unresolved_handoff_ids: tuple[str, ...] = ()
    routing_revalidated_after_changes: bool = True
    independent_review_required: bool = False
    independent_review_accepted: bool = False


@dataclass(frozen=True)
class MigrationTrial:
    """One chronological forward trial for isolated-profile promotion."""

    trial_id: str
    mode: str
    expected_applicable_skill_ids: tuple[str, ...]
    observed_applicable_skill_ids: tuple[str, ...]
    unexpected_skill_ids: tuple[str, ...]
    expected_canonical_finding_ids: tuple[str, ...]
    observed_canonical_finding_ids: tuple[str, ...]
    nodes_reconciled: bool
    validation_complete: bool
    synthesis_complete: bool
    fingerprints_matched: bool
    report_complete: bool
    accepted: bool
    recovery_completed: bool = False
    multi_epoch_completed: bool = False
    runtime_artifact_id: str | None = None
    runtime_artifact_verified: bool = False
    runtime_artifact_verifier: str | None = None
    workers_created: int = 0
    grouped_fallback_completed: bool = False
    worker_creation_failure_forced: bool = False
    worker_skill_load_or_execution_failure_forced: bool = False


@dataclass(frozen=True)
class CreationFailure:
    """Inputs needed to stop dispatch and produce a detailed resume manifest."""

    planned_nodes: tuple[WorkerNode, ...]
    accepted_node_ids: tuple[str, ...]
    failed_node_id: str
    unaccepted_node_ids: tuple[str, ...]
    source_state: tuple[str, str, str]
    validation_mappings: tuple[ValidationEvidenceMapping, ...] = ()
    accepted_nonexecution_catalog_ids: tuple[str, ...] = ()
    journal_location: str | None = None
    execution_epochs: tuple[ExecutionEpoch, ...] = ()
    current_epoch_ordinal: int | None = None
    routing_catalog_closed: bool = False
    unresolved_handoff_ids: tuple[str, ...] = ()
    routing_revalidation_required: bool = False


def _priority_rank(priority: str) -> int:
    """Return a stable priority rank and reject undeclared classes."""
    try:
        return PRIORITY_ORDER[priority]
    except KeyError as error:
        msg = f"unknown graph priority: {priority}"
        raise ValueError(msg) from error


def _validate_unique_ids(items: Iterable[str], *, label: str) -> None:
    values = tuple(items)
    if len(values) != len(set(values)):
        msg = f"{label} IDs must be unique"
        raise ValueError(msg)
    if any(not value for value in values):
        msg = f"{label} IDs must be nonempty"
        raise ValueError(msg)


def _path_is_within(path: Path, roots: Sequence[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _resolve_skill_root_path(raw_path: str, skill_roots: Sequence[Path]) -> Path:
    roots = tuple(root.resolve() for root in skill_roots)
    if not roots:
        msg = "at least one approved skill root is required"
        raise ValueError(msg)
    if raw_path.startswith("$SKILLS_ROOT/"):
        suffix = raw_path.removeprefix("$SKILLS_ROOT/")
        candidates = tuple((root / suffix).resolve() for root in roots if (root / suffix).exists())
        if len(candidates) != 1:
            msg = f"skill-root token must resolve to exactly one existing path: {raw_path}"
            raise ValueError(msg)
        resolved = candidates[0]
    else:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            candidates = tuple((root / candidate).resolve() for root in roots if (root / candidate).exists())
            if len(candidates) != 1:
                msg = f"relative skill path must resolve to exactly one existing path: {raw_path}"
                raise ValueError(msg)
            resolved = candidates[0]
    if not resolved.is_file() or not _path_is_within(resolved, roots):
        msg = f"skill path is missing or outside approved roots: {raw_path}"
        raise ValueError(msg)
    return resolved


def _frontmatter_skill_name(skill_path: Path) -> str:
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        msg = f"skill file lacks YAML frontmatter: {skill_path}"
        raise ValueError(msg)
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if match := _FRONTMATTER_NAME.match(line.strip()):
            return str(match.group(1))
    msg = f"skill file lacks a frontmatter name: {skill_path}"
    raise ValueError(msg)


def _resolve_checked_skill_path(raw_path: str, skill_id: str, skill_roots: Sequence[Path]) -> Path:
    resolved = _resolve_skill_root_path(raw_path, skill_roots)
    actual_name = _frontmatter_skill_name(resolved)
    if actual_name != skill_id:
        msg = f"skill/path mismatch: {skill_id} != {actual_name} at {resolved}"
        raise ValueError(msg)
    return resolved


def load_routing_catalog(path: Path, *, skill_roots: Sequence[Path] = (DEFAULT_SKILL_ROOT,)) -> tuple[RoutingCatalogEntry, ...]:
    """Load and validate the portable machine-readable routing catalog."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("version") != 1 or not isinstance(document.get("entries"), list):
        msg = "routing catalog must have version 1 and an entries list"
        raise ValueError(msg)
    entries: list[RoutingCatalogEntry] = []
    for raw in document["entries"]:
        if not isinstance(raw, Mapping):
            msg = "routing catalog entries must be objects"
            raise TypeError(msg)
        skill_id = str(raw["skill_id"])
        skill_path = _resolve_checked_skill_path(str(raw["skill_path"]), skill_id, skill_roots)
        entry = RoutingCatalogEntry(
            catalog_id=str(raw["catalog_id"]),
            router_id=str(raw["router_id"]),
            rule_id=str(raw["rule_id"]),
            layer=str(raw["layer"]),
            surface=str(raw["surface"]),
            skill_id=skill_id,
            skill_path=str(skill_path),
            target_kind=str(raw["target_kind"]),
            default_priority=str(raw["default_priority"]),
            synthesis_dependency=(str(raw["synthesis_dependency"]) if raw.get("synthesis_dependency") is not None else None),
            required_static_references=tuple(str(_resolve_skill_root_path(str(item), skill_roots)) for item in raw.get("required_static_references", [])),
            path_patterns=tuple(str(item) for item in raw.get("path_patterns", [])),
            semantic_triggers=tuple(str(item) for item in raw.get("semantic_triggers", [])),
        )
        if entry.layer not in ROUTING_LAYERS:
            msg = f"unknown routing layer for {entry.catalog_id}: {entry.layer}"
            raise ValueError(msg)
        if entry.target_kind not in ROUTING_TARGET_KINDS:
            msg = f"unknown routing target kind for {entry.catalog_id}: {entry.target_kind}"
            raise ValueError(msg)
        _priority_rank(entry.default_priority)
        if not entry.rule_id or not entry.semantic_triggers:
            msg = f"routing catalog entry {entry.catalog_id} needs a rule ID and semantic triggers"
            raise ValueError(msg)
        entries.append(entry)
    _validate_unique_ids((entry.catalog_id for entry in entries), label="routing catalog")
    return tuple(entries)


def _decision_matches_entry(decision: RoutingDecision, entry: RoutingCatalogEntry) -> tuple[str, ...]:  # noqa: C901, PLR0912
    blockers: list[str] = []
    for actual, expected, label in (
        (decision.router_id, entry.router_id, "router"),
        (decision.rule_id, entry.rule_id, "rule"),
        (decision.skill_id, entry.skill_id, "skill"),
        (decision.skill_path, entry.skill_path, "skill path"),
    ):
        if actual != expected:
            blockers.append(f"{decision.catalog_id} {label} mismatch: expected {expected}, got {actual}")
    if decision.disposition not in ROUTING_DISPOSITIONS:
        blockers.append(f"{decision.catalog_id} has unknown disposition {decision.disposition}")
    if not decision.reason or not decision.applicability_evidence:
        blockers.append(f"{decision.catalog_id} needs a reason and applicability evidence")
    if decision.disposition == "selected" and not decision.review_surface and entry.target_kind in {"leaf", "independent"}:
        blockers.append(f"{decision.catalog_id} selected a worker without an exact review surface")
    if decision.disposition == "selected" and entry.target_kind in {"leaf", "independent"} and not decision.owners:
        blockers.append(f"{decision.catalog_id} selected a worker without an owner")
    if decision.disposition == "exact-evidence-reused" and (not isinstance(decision.evidence_id, str) or not decision.evidence_id.strip()):
        blockers.append(f"{decision.catalog_id} claims exact evidence reuse without an evidence ID")
    if decision.disposition == "exact-evidence-reused" and entry.target_kind in {"leaf", "independent"} and not decision.review_surface:
        blockers.append(f"{decision.catalog_id} claims exact evidence reuse without an exact review surface")
    if entry.target_kind in {"router", "synthesis"} and decision.disposition == "exact-evidence-reused":
        blockers.append(f"{decision.catalog_id} cannot reuse evidence for a router or synthesis decision")
    missing_references = sorted(set(entry.required_static_references) - set(decision.static_references))
    if decision.disposition in {"selected", "exact-evidence-reused"} and missing_references:
        blockers.append(f"{decision.catalog_id} omitted required static references: {', '.join(missing_references)}")
    expected_synthesis = entry.synthesis_dependency
    if decision.disposition == "selected" and expected_synthesis is not None and decision.synthesis_dependency != expected_synthesis:
        blockers.append(f"{decision.catalog_id} must depend on synthesis {expected_synthesis}")
    if decision.priority is not None:
        _priority_rank(decision.priority)
    invalid_paths = [path for path in (*decision.instruction_paths, *decision.static_references) if not Path(path).is_absolute() or not Path(path).is_file()]
    if decision.disposition == "selected" and invalid_paths:
        blockers.append(f"{decision.catalog_id} has missing or non-absolute instruction/reference paths: {', '.join(invalid_paths)}")
    return tuple(blockers)


def validate_routing_ledger(  # noqa: C901
    catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision], *, consulted_routers: Sequence[str]
) -> RoutingLedgerAssessment:
    """Require a total disposition ledger for every consulted routing catalog."""
    consulted = tuple(dict.fromkeys(consulted_routers))
    active_entries = {entry.catalog_id: entry for entry in catalog if entry.router_id in consulted}
    decision_ids = tuple(item.catalog_id for item in decisions)
    blockers: list[str] = []
    if REPOSITORY_ROUTER_ID not in consulted:
        blockers.append(f"routing ledger must consult {REPOSITORY_ROUTER_ID} before catalog closure")
    if len(decision_ids) != len(set(decision_ids)):
        blockers.append("routing decisions must contain each catalog ID exactly once")
    unknown = sorted(set(decision_ids) - set(active_entries))
    missing = sorted(set(active_entries) - set(decision_ids))
    if unknown:
        blockers.append("routing decisions reference unconsulted or unknown catalog IDs: " + ", ".join(unknown))
    if missing:
        blockers.append("routing ledger omitted catalog IDs: " + ", ".join(missing))
    decisions_by_id = {item.catalog_id: item for item in decisions}
    for catalog_id in sorted(set(active_entries) & set(decisions_by_id)):
        blockers.extend(_decision_matches_entry(decisions_by_id[catalog_id], active_entries[catalog_id]))

    selected_router_ids = {
        entry.skill_id
        for catalog_id, entry in active_entries.items()
        if entry.target_kind == "router" and decisions_by_id.get(catalog_id) is not None and decisions_by_id[catalog_id].disposition == "selected"
    }
    missing_router_handoffs = sorted(selected_router_ids - set(consulted))
    if missing_router_handoffs:
        blockers.append("selected surface routers were not consulted: " + ", ".join(missing_router_handoffs))
    orphan_surface_routers = sorted(set(consulted) - {REPOSITORY_ROUTER_ID} - selected_router_ids)
    if orphan_surface_routers:
        blockers.append("surface routers lack a selected repository route: " + ", ".join(orphan_surface_routers))
    missing_synthesis_routes = sorted(
        entry.catalog_id
        for entry in active_entries.values()
        if entry.target_kind == "synthesis" and (decisions_by_id.get(entry.catalog_id) is None or decisions_by_id[entry.catalog_id].disposition != "selected")
    )
    if missing_synthesis_routes:
        blockers.append("required synthesis routing entries were not selected: " + ", ".join(missing_synthesis_routes))

    blocking_catalog_ids = tuple(sorted(item.catalog_id for item in decisions if item.disposition in COMPLETION_BLOCKING_DISPOSITIONS))
    if blocking_catalog_ids:
        blockers.append("completion-blocking routing dispositions remain: " + ", ".join(blocking_catalog_ids))
    selected_requirement_ids = tuple(
        sorted(
            item.requirement_id
            for item in decisions
            if item.disposition == "selected"
            and active_entries.get(item.catalog_id) is not None
            and active_entries[item.catalog_id].target_kind in {"leaf", "independent"}
        )
    )
    reused_decisions = tuple(
        sorted(
            (
                item
                for item in decisions
                if item.disposition == "exact-evidence-reused"
                and active_entries.get(item.catalog_id) is not None
                and active_entries[item.catalog_id].target_kind in {"leaf", "independent"}
            ),
            key=lambda item: item.requirement_id,
        )
    )
    exact_reused_review_evidence = tuple((item.requirement_id, item.evidence_id or "") for item in reused_decisions)
    reused_review_identities = tuple(
        ReusedReviewEvidencePlan(
            requirement_id=item.requirement_id,
            evidence_id=item.evidence_id or "",
            skill_id=item.skill_id,
            skill_path=item.skill_path,
            mode="independent-review" if active_entries[item.catalog_id].target_kind == "independent" else "audit",
            static_references=item.static_references,
            planned_paths=item.review_surface if active_entries[item.catalog_id].target_kind == "independent" else (),
        )
        for item in reused_decisions
    )
    all_review_requirement_ids = (*selected_requirement_ids, *(item.requirement_id for item in reused_decisions))
    if len(all_review_requirement_ids) != len(set(all_review_requirement_ids)):
        blockers.append("selected and exactly reused review requirements must have unique IDs")
    user_excluded = tuple(sorted(item.catalog_id for item in decisions if item.disposition == "user-excluded"))
    catalog_closed = not blockers
    return RoutingLedgerAssessment(
        feasible=not blockers,
        blockers=tuple(blockers),
        selected_requirement_ids=selected_requirement_ids,
        exact_reused_review_evidence=exact_reused_review_evidence,
        reused_review_identities=reused_review_identities,
        user_excluded_catalog_ids=user_excluded,
        completion_blocking_catalog_ids=blocking_catalog_ids,
        consulted_routers=consulted,
        catalog_closed=catalog_closed,
    )


def review_requirements_from_routing(catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision]) -> tuple[ReviewRequirement, ...]:
    """Convert only selected leaves into executable review requirements."""
    entries = {entry.catalog_id: entry for entry in catalog}
    requirements: list[ReviewRequirement] = []
    for decision in decisions:
        entry = entries.get(decision.catalog_id)
        if decision.disposition != "selected" or entry is None or entry.target_kind != "leaf":
            continue
        requirements.append(
            ReviewRequirement(
                requirement_id=decision.requirement_id,
                skill_id=decision.skill_id,
                skill_path=decision.skill_path,
                router_id=decision.router_id,
                rule_id=decision.rule_id,
                review_surface=decision.review_surface,
                reason=decision.reason,
                priority=decision.priority or entry.default_priority,
                synthesis_dependency=decision.synthesis_dependency,
                required=True,
                static_references=decision.static_references,
                instruction_paths=decision.instruction_paths,
                validation_requirement_ids=decision.validation_requirement_ids,
                owners=decision.owners or (entry.surface,),
            )
        )
    return tuple(requirements)


def independent_nodes_from_routing(
    catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision], *, change_target: str
) -> tuple[WorkerNode, ...]:
    """Create executable selected independent-review nodes without treating them as audits."""
    entries = {entry.catalog_id: entry for entry in catalog}
    selected = sorted(
        (
            decision
            for decision in decisions
            if decision.disposition == "selected" and entries.get(decision.catalog_id) is not None and entries[decision.catalog_id].target_kind == "independent"
        ),
        key=lambda item: item.catalog_id,
    )
    if selected and (not _nonempty_text(change_target) or len(change_target) > MAX_NATIVE_IDENTIFIER_LENGTH):
        msg = "selected independent review requires one bounded non-empty change target"
        raise ValueError(msg)
    return tuple(
        WorkerNode(
            node_id=f"independent-{ordinal:03d}",
            skill_id=decision.skill_id,
            skill_path=decision.skill_path,
            mode="independent-review",
            priority=decision.priority or entries[decision.catalog_id].default_priority,
            required=True,
            requirement_ids=(decision.requirement_id,),
            coverage=decision.review_surface,
            synthesis_dependency=decision.synthesis_dependency,
            router_ids=(decision.router_id,),
            rule_ids=(decision.rule_id,),
            selection_reasons=(decision.reason,),
            owners=decision.owners,
            instruction_paths=decision.instruction_paths,
            static_references=decision.static_references,
            change_target=change_target,
        )
        for ordinal, decision in enumerate(selected, start=1)
    )


def assess_routing_discoveries(decisions: Sequence[RoutingDecision], discoveries: Sequence[RoutingDiscovery]) -> Assessment:
    """Block synthesis until every late handoff resolves to selected or reused work."""
    _validate_unique_ids((item.handoff_id for item in discoveries), label="routing handoff")
    dispositions = {item.catalog_id: item.disposition for item in decisions}
    unresolved = [item.handoff_id for item in discoveries if dispositions.get(item.catalog_id) not in {"selected", "exact-evidence-reused", "user-excluded"}]
    unknown = [item.handoff_id for item in discoveries if item.catalog_id not in dispositions]
    blockers: list[str] = []
    if unknown:
        blockers.append("late handoffs reference unknown routing candidates: " + ", ".join(sorted(unknown)))
    if unresolved:
        blockers.append("late applicability handoffs remain unresolved: " + ", ".join(sorted(unresolved)))
    return Assessment(not blockers, tuple(blockers))


def classify_repository_paths(paths: Sequence[str], *, release_readiness: bool = False) -> dict[str, tuple[str, ...]]:  # noqa: C901
    """Return conservative repository-surface signals, including shared owners."""
    normalized = tuple(str(PurePosixPath(path)) for path in paths)
    signals: dict[str, set[str]] = {surface: set() for surface in ("tooling", "cpp", "rust", "python", "documentation")}

    def add(surface: str, path: str, reason: str) -> None:
        signals[surface].add(f"{path}: {reason}")

    has_cpp = any(fnmatch.fnmatch(path, pattern) for path in normalized for pattern in ("*.cc", "*.cpp", "*.cxx", "*.hh", "*.hpp", "*.hxx", "*.ixx", "*.cppm"))
    has_rust = any(path.endswith(".rs") or PurePosixPath(path).name in {"Cargo.toml", "Cargo.lock"} for path in normalized)
    has_python = any(path.endswith((".py", ".ipynb")) or PurePosixPath(path).name in {"pyproject.toml", "uv.lock"} for path in normalized)
    for path in normalized:
        basename = PurePosixPath(path).name
        if path.endswith((".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".ixx", ".cppm")):
            add("cpp", path, "C++ source or contract")
        if path.endswith(".rs") or basename in {"Cargo.toml", "Cargo.lock", "rust-toolchain", "rust-toolchain.toml", "clippy.toml", "rustfmt.toml"}:
            add("rust", path, "Rust source, package, or toolchain surface")
        if path.endswith((".py", ".ipynb")) or basename in {"pyproject.toml", "uv.lock"}:
            add("python", path, "Python source, notebook, package, or lock surface")
        if basename in {"CMakeLists.txt", "CMakePresets.json", "vcpkg.json", "vcpkg-configuration.json"} or path.startswith("cmake/"):
            add("cpp", path, "C++ build semantics")
            add("tooling", path, "shared build configuration")
        if basename in {"Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock"}:
            add("tooling", path, "shared dependency or command configuration")
        if basename in {"justfile", "Makefile", "Brewfile"} or path.startswith(".github/workflows/"):
            add("tooling", path, "repository command or CI surface")
            if has_cpp:
                add("cpp", path, "shared workflow/recipe may alter C++ validation")
            if has_rust:
                add("rust", path, "shared workflow/recipe may alter Rust validation")
            if has_python:
                add("python", path, "shared workflow/recipe may alter Python validation")
        if basename in {"README.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md", "CITATION.cff"} or path.startswith("docs/"):
            add("documentation", path, "active repository documentation")
            add("tooling", path, "documentation may describe commands or maintainer workflow")
    if release_readiness:
        add("documentation", "<active-doc-inventory>", "release readiness requires the full active documentation suite")
    return {surface: tuple(sorted(values)) for surface, values in signals.items() if values}


def assess_repository_classifier_floor(
    catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision], signals: Mapping[str, Sequence[str]]
) -> Assessment:
    """Prevent repository routing from silently contradicting deterministic signals."""
    repository_entry_by_surface = {entry.surface: entry for entry in catalog if entry.router_id == REPOSITORY_ROUTER_ID and entry.layer == "repository"}
    decision_by_id = {item.catalog_id: item for item in decisions}
    blockers: list[str] = []
    for surface, evidence in signals.items():
        entry = repository_entry_by_surface.get(surface)
        if entry is None:
            blockers.append(f"repository classifier signaled uncataloged surface {surface}")
            continue
        decision = decision_by_id.get(entry.catalog_id)
        if decision is None:
            blockers.append(f"repository classifier signal lacks a decision for {entry.catalog_id}")
            continue
        if decision.disposition not in {"selected", "exact-evidence-reused", "user-excluded"}:
            blockers.append(f"repository classifier signaled {surface} but {entry.catalog_id} is {decision.disposition}: " + "; ".join(evidence))
    return Assessment(not blockers, tuple(blockers))


def coalesce_review_requirements(requirements: Sequence[ReviewRequirement]) -> tuple[tuple[WorkerNode, ...], tuple[tuple[str, str], ...]]:
    """Coalesce identical leaf dispatches without merging distinct scopes."""
    _validate_unique_ids((item.requirement_id for item in requirements), label="review requirement")
    groups: dict[tuple[object, ...], list[ReviewRequirement]] = {}
    for item in requirements:
        _priority_rank(item.priority)
        if not all((item.skill_id, item.skill_path, item.router_id, item.rule_id, item.reason)) or not item.review_surface:
            msg = f"review requirement {item.requirement_id} lacks routing, skill-path, reason, or surface evidence"
            raise ValueError(msg)
        key = (
            item.skill_id,
            item.skill_path,
            item.skill_digest,
            item.reference_digests,
            tuple(sorted(item.review_surface)),
            tuple(sorted(item.instruction_paths)),
            tuple(sorted(item.static_references)),
            item.synthesis_dependency,
            tuple(sorted(item.owners)),
        )
        groups.setdefault(key, []).append(item)

    nodes: list[WorkerNode] = []
    mappings: list[tuple[str, str]] = []
    for ordinal, key in enumerate(sorted(groups, key=repr), start=1):
        members = sorted(groups[key], key=lambda item: item.requirement_id)
        node_id = f"audit-{ordinal:03d}"
        priority = min((item.priority for item in members), key=_priority_rank)
        requirement_ids = tuple(item.requirement_id for item in members)
        coverage = tuple(sorted({path for item in members for path in item.review_surface}))
        nodes.append(
            WorkerNode(
                node_id=node_id,
                skill_id=members[0].skill_id,
                skill_path=members[0].skill_path,
                mode="audit",
                priority=priority,
                required=True,
                requirement_ids=requirement_ids,
                coverage=coverage,
                synthesis_dependency=members[0].synthesis_dependency,
                router_ids=tuple(sorted({item.router_id for item in members})),
                rule_ids=tuple(sorted({item.rule_id for item in members})),
                selection_reasons=tuple(sorted({item.reason for item in members})),
                owners=tuple(sorted({owner for item in members for owner in item.owners})),
                instruction_paths=tuple(sorted({path for item in members for path in item.instruction_paths})),
                static_references=tuple(sorted({path for item in members for path in item.static_references})),
                skill_digest=members[0].skill_digest,
                reference_digests=members[0].reference_digests,
            )
        )
        mappings.extend((item.requirement_id, node_id) for item in members)
    return tuple(nodes), tuple(sorted(mappings))


def _validation_group_key(item: ValidationRequirement) -> tuple[object, ...]:
    command_identity: object = item.canonical_recipe or item.commands
    return (
        item.source_state,
        command_identity,
        item.commands,
        item.working_directories,
        item.environment,
        item.toolchain,
        tuple(sorted(item.features)),
        item.platform,
        item.artifact_owner,
        item.mutation_lock,
        item.request,
        item.requested_scope,
        item.capture_command,
        item.captured_paths,
        item.dependency_policy,
        item.meaningful_skips,
        item.execution_strategy,
        item.independence_basis,
        item.planning_blocker,
        item.allowed_artifacts,
    )


def coalesce_validation_requirements(requirements: Sequence[ValidationRequirement]) -> tuple[tuple[ValidationUnit, ...], tuple[ValidationEvidenceMapping, ...]]:
    """Group exactly compatible validator needs and retain complete reuse maps."""
    _validate_unique_ids((item.requirement_id for item in requirements), label="validation requirement")
    groups: dict[tuple[object, ...], list[ValidationRequirement]] = {}
    for item in requirements:
        if len(item.source_state) != 3:
            msg = f"validation requirement {item.requirement_id} must name three source fingerprints"
            raise ValueError(msg)
        if len(item.commands) != len(item.working_directories):
            msg = f"validation requirement {item.requirement_id} must map every command to a working directory"
            raise ValueError(msg)
        required_plan_values = (
            item.request,
            item.capture_command,
            item.authority,
            item.selection_reason,
            item.mutation_classification,
            item.expected_evidence,
            item.elapsed_time_budget,
            item.independence_basis,
        )
        if (
            any(not _nonempty_text(value) or len(value) > MAX_NATIVE_IDENTIFIER_LENGTH for value in required_plan_values)
            or item.requested_scope not in {"branch", "staged", "worktree", "baseline", "release"}
            or item.dependency_policy not in {"stop-on-failure", "continue-independent"}
            or item.execution_strategy not in {"sequential", "parallel-independent"}
            or (item.planning_blocker is not None and not _nonempty_text(item.planning_blocker))
        ):
            msg = f"validation requirement {item.requirement_id} has invalid plan provenance"
            raise ValueError(msg)
        normalized_captured_paths = _normalized_repository_paths(item.captured_paths, label=f"validation requirement {item.requirement_id} captured_paths")
        if normalized_captured_paths != item.captured_paths:
            msg = f"validation requirement {item.requirement_id} captured_paths must be normalized"
            raise ValueError(msg)
        if _duplicate_values(tuple(path for path, _, _ in item.allowed_artifacts)) or any(
            not _nonempty_text(path)
            or len(path) > MAX_NATIVE_IDENTIFIER_LENGTH
            or kind not in {"build", "cache", "coverage", "log", "other"}
            or repository_status not in {"ignored", "outside-repository"}
            for path, kind, repository_status in item.allowed_artifacts
        ):
            msg = f"validation requirement {item.requirement_id} has invalid allowed artifacts"
            raise ValueError(msg)
        groups.setdefault(_validation_group_key(item), []).append(item)

    units: list[ValidationUnit] = []
    mappings: list[ValidationEvidenceMapping] = []
    for ordinal, key in enumerate(sorted(groups, key=repr), start=1):
        members = sorted(groups[key], key=lambda item: item.requirement_id)
        first = members[0]
        node_id = f"validation-{ordinal:03d}"
        unit = ValidationUnit(
            node_id=node_id,
            requirement_ids=tuple(item.requirement_id for item in members),
            source_state=first.source_state,
            commands=first.commands,
            working_directories=first.working_directories,
            environment=first.environment,
            toolchain=first.toolchain,
            features=tuple(sorted(first.features)),
            platform=first.platform,
            artifact_owner=first.artifact_owner,
            mutation_lock=first.mutation_lock,
            request=first.request,
            requested_scope=first.requested_scope,
            capture_command=first.capture_command,
            captured_paths=first.captured_paths,
            requirement_plans=tuple(
                (
                    item.requirement_id,
                    item.authority,
                    item.selection_reason,
                    item.mutation_classification,
                    item.expected_evidence,
                    item.elapsed_time_budget,
                    item.evidence_id,
                )
                for item in members
            ),
            dependency_policy=first.dependency_policy,
            meaningful_skips=first.meaningful_skips,
            execution_strategy=first.execution_strategy,
            independence_basis=first.independence_basis,
            planning_blocker=first.planning_blocker,
            allowed_artifacts=first.allowed_artifacts,
            canonical_recipe=first.canonical_recipe,
            evidence_ids=tuple(sorted({item.evidence_id for item in members if item.evidence_id is not None})),
            required=any(item.required or item.baseline for item in members),
            baseline=any(item.baseline for item in members),
        )
        units.append(unit)
        mappings.extend(ValidationEvidenceMapping(item.requirement_id, node_id, item.evidence_id) for item in members)
    return tuple(units), tuple(sorted(mappings, key=lambda item: item.requirement_id))


def _schedule_nodes(nodes: Sequence[WorkerNode]) -> tuple[WorkerNode, ...]:
    """Topologically order selected nodes with deterministic priority tie-breaking."""
    by_id = {node.node_id: node for node in nodes}
    if len(by_id) != len(nodes):
        msg = "worker node IDs must be unique"
        raise ValueError(msg)
    selected = set(by_id)
    normalized = {node_id: replace(node, predecessors=tuple(item for item in node.predecessors if item in selected)) for node_id, node in by_id.items()}
    pending = set(normalized)
    complete: set[str] = set()
    result: list[WorkerNode] = []
    while pending:
        ready = [normalized[node_id] for node_id in pending if set(normalized[node_id].predecessors) <= complete]
        if not ready:
            msg = "selected worker graph contains a dependency cycle"
            raise ValueError(msg)
        next_node = min(ready, key=lambda node: (_priority_rank(node.priority), node.node_id))
        result.append(next_node)
        pending.remove(next_node.node_id)
        complete.add(next_node.node_id)
    return tuple(result)


def _validation_nodes(
    units: Sequence[ValidationUnit], *, skill_path: str, skill_digest: str, reference_digests: tuple[tuple[str, str], ...]
) -> tuple[WorkerNode, ...]:
    return tuple(
        WorkerNode(
            node_id=unit.node_id,
            skill_id="review-validator",
            skill_path=skill_path,
            mode="validation",
            priority="required-validation" if unit.required else "supporting-quality",
            required=unit.required,
            requirement_ids=unit.requirement_ids,
            coverage=(unit.canonical_recipe or " + ".join(unit.commands),),
            static_references=tuple(path for path, _ in reference_digests),
            skill_digest=skill_digest,
            reference_digests=reference_digests,
        )
        for unit in units
    )


def _synthesis_nodes(
    declared_nodes: Sequence[WorkerNode],
    audit_nodes: Sequence[WorkerNode],
    review_requirements: Sequence[ReviewRequirement],
    validation_units: Sequence[ValidationUnit],
    additional_nodes: Sequence[WorkerNode],
) -> tuple[WorkerNode, ...]:
    review_by_id = {item.requirement_id: item for item in review_requirements}
    validation_node_by_requirement = {requirement_id: unit.node_id for unit in validation_units for requirement_id in unit.requirement_ids}
    result: list[WorkerNode] = []
    for node in declared_nodes:
        if node.mode != "synthesis":
            msg = f"declared synthesis node {node.node_id} has mode {node.mode}"
            raise ValueError(msg)
        routed_audits = tuple(audit.node_id for audit in audit_nodes if audit.synthesis_dependency == node.node_id)
        routed_validators = tuple(
            dict.fromkeys(
                validation_node_by_requirement[validation_requirement_id]
                for audit in audit_nodes
                if audit.synthesis_dependency == node.node_id
                for review_requirement_id in audit.requirement_ids
                for validation_requirement_id in review_by_id[review_requirement_id].validation_requirement_ids
            )
        )
        routed_additional = tuple(item.node_id for item in additional_nodes if item.synthesis_dependency == node.node_id)
        routed_syntheses = (
            tuple(item.node_id for item in declared_nodes if item.node_id != node.node_id)
            if (node.node_id, node.skill_id, node.mode) == FINAL_SYNTHESIS_IDENTITY
            else ()
        )
        required_validators = (
            tuple(unit.node_id for unit in validation_units if unit.required or unit.baseline)
            if (node.node_id, node.skill_id, node.mode) == FINAL_SYNTHESIS_IDENTITY
            else ()
        )
        result.append(
            replace(
                node,
                required=True,
                priority="required-routing-synthesis",
                predecessors=tuple(
                    dict.fromkeys((*node.predecessors, *routed_audits, *routed_validators, *required_validators, *routed_additional, *routed_syntheses))
                ),
            )
        )
    return tuple(result)


def _additional_nodes(nodes: Sequence[WorkerNode]) -> tuple[WorkerNode, ...]:
    for node in nodes:
        if node.mode not in {"independent-review", "fix", "revalidation"}:
            msg = f"additional node {node.node_id} must use independent-review, fix, or revalidation mode"
            raise ValueError(msg)
        _priority_rank(node.priority)
        if node.mode == "independent-review" and (not _nonempty_text(node.change_target) or not node.coverage):
            msg = f"independent-review node {node.node_id} requires an exact change target and planned coverage"
            raise ValueError(msg)
        if node.mode != "independent-review" and node.change_target is not None:
            msg = f"non-independent additional node {node.node_id} cannot declare a change target"
            raise ValueError(msg)
    return tuple(nodes)


def _validate_plan_edges(nodes: Sequence[WorkerNode]) -> None:
    _validate_unique_ids((node.node_id for node in nodes), label="worker node")
    node_ids = {node.node_id for node in nodes}
    missing = sorted({predecessor for node in nodes for predecessor in node.predecessors if predecessor not in node_ids})
    if missing:
        msg = "worker nodes reference missing predecessors: " + ", ".join(missing)
        raise ValueError(msg)


def _file_identity_digest(path: str) -> str:
    """Hash one planner-resolved skill or reference file."""
    try:
        content = Path(path).read_bytes()
    except OSError as error:
        msg = f"could not hash planner-owned provenance file {path}: {error}"
        raise ValueError(msg) from error
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _resolved_provenance(
    *, skill_path: str, static_references: Sequence[str], skill_digest: str = "", reference_digests: Sequence[tuple[str, str]] = ()
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Derive provenance from resolved files, retaining typed fixture identities only when files are absent."""
    skill_file = Path(skill_path)
    resolved_skill_digest = _file_identity_digest(skill_path) if skill_file.is_file() else skill_digest
    reference_paths = tuple(static_references)
    if all(Path(path).is_file() for path in reference_paths):
        resolved_reference_digests = tuple((path, _file_identity_digest(path)) for path in reference_paths)
    else:
        resolved_reference_digests = tuple(reference_digests)
    if not _nonempty_text(resolved_skill_digest):
        msg = f"planned node skill provenance is unavailable: {skill_path}"
        raise ValueError(msg)
    if tuple(path for path, _ in resolved_reference_digests) != reference_paths or any(
        not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in resolved_reference_digests
    ):
        msg = f"planned node reference provenance does not match its static references: {skill_path}"
        raise ValueError(msg)
    return resolved_skill_digest, resolved_reference_digests


def _bind_worker_node_provenance(node: WorkerNode) -> WorkerNode:
    skill_digest, reference_digests = _resolved_provenance(
        skill_path=node.skill_path, static_references=node.static_references, skill_digest=node.skill_digest, reference_digests=node.reference_digests
    )
    return replace(node, skill_digest=skill_digest, reference_digests=reference_digests)


def _bind_reused_review_provenance(identity: ReusedReviewEvidencePlan) -> ReusedReviewEvidencePlan:
    skill_digest, reference_digests = _resolved_provenance(
        skill_path=identity.skill_path,
        static_references=identity.static_references,
        skill_digest=identity.skill_digest,
        reference_digests=identity.reference_digests,
    )
    return replace(identity, skill_digest=skill_digest, reference_digests=reference_digests)


def _validator_static_references(skill_path: str) -> tuple[str, ...]:
    """Return the required graph-dispatched validator contract paths."""
    skill_dir = Path(skill_path).parent
    return (str(skill_dir / "references" / "result-contract.md"), str(skill_dir.parent / "review-graph" / "references" / "evidence-contract.md"))


def _partition_execution_epochs(nodes: Sequence[WorkerNode], budget: WorkerBudget) -> tuple[ExecutionEpoch, ...]:
    """Partition a complete schedule without dropping any applicable node."""
    usable_capacity = budget.total - budget.recovery_finalization_reserve
    if usable_capacity < 1:
        msg = "worker budget and reserve must leave capacity for one graph node"
        raise ValueError(msg)
    return tuple(
        ExecutionEpoch(
            ordinal=ordinal,
            node_ids=tuple(node.node_id for node in nodes[offset : offset + usable_capacity]),
            worker_budget=budget.total,
            recovery_finalization_reserve=budget.recovery_finalization_reserve,
            requires_fresh_root=ordinal > 1,
        )
        for ordinal, offset in enumerate(range(0, len(nodes), usable_capacity), start=1)
    )


def plan_graph(  # noqa: C901, PLR0913, PLR0915
    review_requirements: Sequence[ReviewRequirement],
    validation_requirements: Sequence[ValidationRequirement],
    synthesis_nodes: Sequence[WorkerNode],
    *,
    additional_nodes: Sequence[WorkerNode] = (),
    budget: WorkerBudget | None = None,
    routing_assessment: RoutingLedgerAssessment | None = None,
    validator_skill_path: str | None = None,
    validator_skill_digest: str = "",
    validator_reference_digests: tuple[tuple[str, str], ...] = (),
    execution_profile: str = "grouped",
    captured_path_line_bounds: tuple[tuple[str, int], ...] = (),
) -> GraphPlan:
    """Build the complete required graph for one exact execution profile."""
    if not isinstance(execution_profile, str) or execution_profile not in {"grouped", "isolated", "isolated-only", "mixed"}:
        msg = "execution_profile must be exactly grouped, isolated, isolated-only, or mixed"
        raise ValueError(msg)
    budget = budget or WorkerBudget()
    if budget.total < 1 or budget.recovery_finalization_reserve < 0:
        msg = "worker budget must be positive and recovery/finalization reserve nonnegative"
        raise ValueError(msg)
    if budget.recovery_finalization_reserve >= budget.total:
        msg = "recovery/finalization reserve must leave capacity for at least one worker"
        raise ValueError(msg)
    normalized_line_bounds: dict[str, int] = {}
    for path, bound in captured_path_line_bounds:
        normalized_path = _normalize_repository_path(path, label="captured_path_line_bounds")
        if normalized_path in normalized_line_bounds:
            msg = "captured_path_line_bounds must not contain duplicate normalized paths"
            raise ValueError(msg)
        if not isinstance(bound, int) or isinstance(bound, bool) or bound < 0:
            msg = f"captured_path_line_bounds value for {normalized_path} must be a nonnegative integer"
            raise ValueError(msg)
        normalized_line_bounds[normalized_path] = bound
    captured_path_line_bounds = tuple(sorted(normalized_line_bounds.items()))

    audit_nodes, requirement_to_node = coalesce_review_requirements(review_requirements)
    validation_units, evidence_mapping = coalesce_validation_requirements(validation_requirements)
    if not any(unit.baseline for unit in validation_units):
        msg = "bounded review graphs require at least one baseline validation unit"
        raise ValueError(msg)
    declared_validation_ids = {item.requirement_id for item in validation_requirements}
    missing_validation_ids = sorted(
        {requirement_id for item in review_requirements for requirement_id in item.validation_requirement_ids if requirement_id not in declared_validation_ids}
    )
    if missing_validation_ids:
        msg = "review requirements reference undeclared validation requirements: " + ", ".join(missing_validation_ids)
        raise ValueError(msg)
    declared_synthesis_ids = {node.node_id for node in synthesis_nodes}
    missing_synthesis_ids = sorted(
        {
            item.synthesis_dependency
            for item in review_requirements
            if item.synthesis_dependency is not None and item.synthesis_dependency not in declared_synthesis_ids
        }
    )
    if missing_synthesis_ids:
        msg = "review requirements reference undeclared synthesis nodes: " + ", ".join(missing_synthesis_ids)
        raise ValueError(msg)
    routed_synthesis_ids = {item.synthesis_dependency for item in review_requirements if item.synthesis_dependency is not None}
    if len(routed_synthesis_ids) > 1 and not any(node.skill_id == "repository-production-review" for node in synthesis_nodes):
        msg = "multi-surface review graphs require a fresh repository-production-review synthesis node"
        raise ValueError(msg)
    normalized_additional_nodes = _additional_nodes(additional_nodes)
    resolved_validator_skill_path = validator_skill_path or str((DEFAULT_SKILL_ROOT / "review-validator" / "SKILL.md").resolve())
    validator_static_references = (
        tuple(path for path, _ in validator_reference_digests) if validator_reference_digests else _validator_static_references(resolved_validator_skill_path)
    )
    resolved_validator_skill_digest, resolved_validator_reference_digests = _resolved_provenance(
        skill_path=resolved_validator_skill_path,
        static_references=validator_static_references,
        skill_digest=validator_skill_digest,
        reference_digests=validator_reference_digests,
    )
    all_nodes = tuple(
        _bind_worker_node_provenance(node)
        for node in (
            *audit_nodes,
            *_validation_nodes(
                validation_units,
                skill_path=resolved_validator_skill_path,
                skill_digest=resolved_validator_skill_digest,
                reference_digests=resolved_validator_reference_digests,
            ),
            *normalized_additional_nodes,
            *_synthesis_nodes(synthesis_nodes, audit_nodes, review_requirements, validation_units, normalized_additional_nodes),
        )
    )
    _validate_plan_edges(all_nodes)
    scheduled = _schedule_nodes(all_nodes)
    epochs = _partition_execution_epochs(scheduled, budget) if execution_profile in {"isolated", "isolated-only", "mixed"} else ()
    current_epoch_ids = epochs[0].node_ids if epochs else ()
    selected_node_ids = {node.node_id for node in scheduled}
    selected_units = tuple(unit.node_id for unit in validation_units if unit.node_id in selected_node_ids)
    selected_synthesis = tuple(node.node_id for node in scheduled if node.mode == "synthesis")
    return GraphPlan(
        execution_profile=execution_profile,
        worker_budget=budget.total,
        recovery_finalization_reserve=budget.recovery_finalization_reserve,
        selected_review_requirements=(
            routing_assessment.selected_requirement_ids
            if routing_assessment is not None
            else tuple(sorted(item.requirement_id for item in review_requirements))
        ),
        complete_node_count=len(all_nodes),
        actual_worker_nodes=scheduled,
        execution_epochs=epochs,
        current_epoch_node_ids=current_epoch_ids,
        requires_continuation=len(epochs) > 1,
        coalesced_validation_units=validation_units,
        selected_validation_units=selected_units,
        synthesis_nodes=selected_synthesis,
        requirement_to_node=tuple(
            sorted((*requirement_to_node, *((requirement_id, node.node_id) for node in normalized_additional_nodes for requirement_id in node.requirement_ids)))
        ),
        validation_evidence_mapping=evidence_mapping,
        captured_path_line_bounds=captured_path_line_bounds,
        routing_catalog_closed=routing_assessment.catalog_closed if routing_assessment is not None else False,
        consulted_routers=routing_assessment.consulted_routers if routing_assessment is not None else (),
        exact_reused_review_evidence=routing_assessment.exact_reused_review_evidence if routing_assessment is not None else (),
        reused_review_identities=routing_assessment.reused_review_identities if routing_assessment is not None else (),
        user_excluded_catalog_ids=routing_assessment.user_excluded_catalog_ids if routing_assessment is not None else (),
        routing_completion_blockers=routing_assessment.completion_blocking_catalog_ids if routing_assessment is not None else (),
        dispatch_allowed=routing_assessment.feasible if routing_assessment is not None else True,
        blockers=routing_assessment.blockers if routing_assessment is not None else (),
    )


def assess_node_acceptance(evidence: NodeAcceptanceEvidence) -> Assessment:
    """Require legacy isolated execution proof for persisted manifests."""
    blockers: list[str] = []
    if not evidence.worker_created:
        blockers.append("worker was not created")
    if not evidence.fresh_context:
        blockers.append("fresh no-inherited-turn context was not proved")
    if evidence.loaded_skill_path != evidence.expected_skill_path:
        blockers.append("dispatched skill loading was not proved")
    missing_refs = sorted(set(evidence.required_static_references) - set(evidence.loaded_static_references))
    if missing_refs:
        blockers.append("required static references were not loaded: " + ", ".join(missing_refs))
    if not evidence.report_complete:
        blockers.append("worker report is structurally incomplete")
    if evidence.fingerprints.before != evidence.fingerprints.expected:
        blockers.append("before fingerprints do not match the captured source state")
    if evidence.fingerprints.after != evidence.fingerprints.expected:
        blockers.append("after fingerprints do not match the captured source state")
    return Assessment(not blockers, tuple(blockers))


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _duplicate_values(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return tuple(sorted(duplicates))


def _identifier_tuple_blockers(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    blockers: list[str] = []
    if any(not _nonempty_text(value) for value in values):
        blockers.append(f"{label} must be non-empty strings")
    if _duplicate_values(values):
        blockers.append(f"{label} must be unique")
    return tuple(blockers)


def _sha256_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _native_heading_blockers(text: str, *, expected_heading: str, required_sections: Sequence[str]) -> tuple[str, ...]:
    blockers: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0] != expected_heading:
        blockers.append(f"native result top heading must be exactly {expected_heading}")
    unexpected_sections = tuple(line for line in lines if line.startswith("## ") and line not in required_sections)
    if unexpected_sections:
        blockers.append("native result contains unexpected level-two sections: " + ", ".join(sorted(set(unexpected_sections))))
    prior_position = -1
    for heading in required_sections:
        positions = tuple(index for index, line in enumerate(lines) if line == heading)
        if len(positions) != 1:
            blockers.append(f"native result must contain exactly one {heading} section")
            continue
        if positions[0] <= prior_position:
            blockers.append(f"native result section is out of order: {heading}")
        prior_position = positions[0]
    return tuple(blockers)


def _native_section_bodies(text: str, required_sections: Sequence[str]) -> tuple[Mapping[str, str] | None, tuple[str, ...]]:
    """Extract the exact bounded bodies of an already validated section sequence."""
    lines = text.splitlines()
    positions = tuple(tuple(index for index, line in enumerate(lines) if line == heading) for heading in required_sections)
    if any(len(matches) != 1 for matches in positions):
        return None, ()
    section_bodies: dict[str, str] = {}
    blockers: list[str] = []
    for index, heading in enumerate(required_sections[:-1]):
        start = positions[index][0] + 1
        end = positions[index + 1][0]
        body = "\n".join(lines[start:end]).strip()
        if len(body.encode("utf-8")) > MAX_NATIVE_SECTION_BYTES:
            blockers.append(f"native result {heading} section exceeds the maximum size")
        section_bodies[heading] = body
    return section_bodies, tuple(blockers)


def _native_preamble(text: str, first_section: str) -> tuple[str | None, tuple[str, ...]]:
    """Extract the bounded body between the exact H1 and first required H2."""
    lines = text.splitlines()
    positions = tuple(index for index, line in enumerate(lines) if line == first_section)
    if len(positions) != 1:
        return None, ()
    body = "\n".join(lines[1 : positions[0]]).strip()
    if len(body.encode("utf-8")) > MAX_NATIVE_SECTION_BYTES:
        return None, ("native result header exceeds the maximum size",)
    return body, ()


def _native_json_block(text: str) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    blockers: list[str] = []
    if text.count(NATIVE_EVIDENCE_BLOCK_OPEN) != 1:
        return None, ("native result must contain exactly one canonical evidence block",)
    marker_start = text.find(NATIVE_EVIDENCE_BLOCK_OPEN)
    if marker_start < text.rfind("## Machine Evidence"):
        blockers.append("native result evidence block must appear under the Machine Evidence section")
    block_start = marker_start + len(NATIVE_EVIDENCE_BLOCK_OPEN)
    block_end = text.find(NATIVE_EVIDENCE_BLOCK_CLOSE, block_start)
    if block_end < 0:
        return None, (*blockers, "native result evidence block is truncated")
    if text[block_end + len(NATIVE_EVIDENCE_BLOCK_CLOSE) :].strip():
        blockers.append("native result evidence block must end the artifact")
    raw_block = text[block_start:block_end]
    if len(raw_block.encode("utf-8")) > MAX_NATIVE_EVIDENCE_BLOCK_BYTES:
        return None, (*blockers, "native result evidence block exceeds the maximum size")
    try:
        parsed = json.loads(raw_block)
    except json.JSONDecodeError, RecursionError:
        return None, (*blockers, "native result evidence block is not valid JSON")
    if not isinstance(parsed, Mapping):
        return None, (*blockers, "native result evidence block must be a JSON object")
    try:
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except RecursionError:
        canonical = None
        blockers.append("native result evidence block exceeds the nesting limit")
    if canonical is not None and raw_block != canonical:
        blockers.append("native result evidence block is not canonical JSON")
    return parsed, tuple(blockers)


def _parse_native_result(
    content: bytes, *, expected_heading: str, required_sections: Sequence[str]
) -> tuple[Mapping[str, Any] | None, str | None, Mapping[str, str] | None, tuple[str, ...]]:
    """Parse one bounded canonical evidence block from a native Markdown result."""
    if len(content) > MAX_NATIVE_RESULT_BYTES:
        return None, None, None, ("native result exceeds the maximum artifact size",)
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None, None, None, ("native result is not valid UTF-8",)
    heading_blockers = _native_heading_blockers(text, expected_heading=expected_heading, required_sections=required_sections)
    preamble, preamble_blockers = _native_preamble(text, required_sections[0])
    section_bodies, section_blockers = _native_section_bodies(text, required_sections)
    payload, block_blockers = _native_json_block(text)
    return payload, preamble, section_bodies, (*heading_blockers, *preamble_blockers, *section_blockers, *block_blockers)


def _native_identifier_list_blockers(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        return (f"native result evidence {field_name} must be an array",)
    if len(value) > MAX_NATIVE_IDENTIFIER_COUNT:
        return (f"native result evidence {field_name} exceeds the item limit",)
    if any(not isinstance(item, str) or not item.strip() or len(item) > MAX_NATIVE_IDENTIFIER_LENGTH for item in value):
        return (f"native result evidence {field_name} must contain bounded non-empty strings",)
    if _duplicate_values(tuple(value)):
        return (f"native result evidence {field_name} must contain unique strings",)
    return ()


def _native_payload_shape_blockers(payload: Mapping[str, Any], *, expected_keys: frozenset[str]) -> tuple[str, ...]:
    blockers: list[str] = []
    observed_keys = frozenset(payload)
    if observed_keys != expected_keys:
        missing = sorted(expected_keys - observed_keys)
        extra = sorted(observed_keys - expected_keys)
        detail: list[str] = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        blockers.append("native result evidence fields do not match schema: " + "; ".join(detail))
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version != EVIDENCE_SCHEMA_VERSION:
        blockers.append(f"native result evidence schema must be exactly {EVIDENCE_SCHEMA_VERSION}")
    bool_fields = ("source_mutated", "git_mutated")
    blockers.extend(f"native result evidence {field_name} must be a boolean" for field_name in bool_fields if not isinstance(payload.get(field_name), bool))
    list_fields = ("requirement_ids", "finding_ids", "validation_requirement_ids", "predecessor_evidence_ids", "handoff_ids", "inspected_paths")
    for field_name in list_fields:
        if field_name in expected_keys:
            blockers.extend(_native_identifier_list_blockers(payload.get(field_name), field_name=field_name))
    scalar_fields = expected_keys - {"schema_version", *bool_fields, *list_fields}
    for field_name in scalar_fields:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_NATIVE_IDENTIFIER_LENGTH:
            blockers.append(f"native result evidence {field_name} must be a bounded non-empty string")
    return tuple(blockers)


def _native_field_values(body: str, label: str, *, indent: str = "") -> tuple[str, ...]:
    prefix = f"{indent}- {label}: "
    return tuple(line[len(prefix) :].strip() for line in body.splitlines() if line.startswith(prefix))


def _native_values_blockers(body: str, *, section: str, label: str, expected: Sequence[str], indent: str = "") -> tuple[str, ...]:
    observed = _native_field_values(body, label, indent=indent)
    if observed != tuple(expected):
        return (f"native result {section} {label} values do not match its evidence envelope",)
    return ()


def _native_header_blockers(body: str, *, result_kind: str, expected_fields: Sequence[tuple[str, str]]) -> tuple[str, ...]:
    """Require one exact ordered native result header without accepting prose aliases."""
    blockers: list[str] = []
    for label, expected in expected_fields:
        blockers.extend(_native_values_blockers(body, section=f"{result_kind} header", label=label, expected=(expected,)))
    expected_lines = tuple(f"- {label}: {expected}" for label, expected in expected_fields)
    if tuple(body.splitlines()) != expected_lines:
        blockers.append(f"native result {result_kind} header fields are incomplete, duplicated, unexpected, or out of order")
    return tuple(blockers)


def _native_record_fields(body: str, *, section: str, labels: Sequence[str], indent: str = "  ") -> tuple[Mapping[str, str], tuple[str, ...]]:
    """Parse one strict ordered bullet record with exactly one value per label."""
    blockers: list[str] = []
    fields: dict[str, str] = {}
    for label in labels:
        values = _native_field_values(body, label, indent=indent)
        if len(values) != 1 or not values[0]:
            blockers.append(f"native result {section} {label} is missing, duplicated, or empty")
        else:
            fields[label] = values[0]
    expected_prefixes = tuple(f"{indent}- {label}: " for label in labels)
    lines = tuple(body.splitlines())
    if len(lines) != len(expected_prefixes) or any(not line.startswith(prefix) for line, prefix in zip(lines, expected_prefixes, strict=False)):
        blockers.append(f"native result {section} fields are incomplete, duplicated, unexpected, or out of order")
    return fields, tuple(blockers)


def _native_nonempty_section_blockers(body: str, *, section: str) -> tuple[str, ...]:
    if not body or body == "none":
        return (f"native result {section} section must contain concrete evidence",)
    return ()


def _native_records(body: str, label: str) -> tuple[tuple[str, str], ...]:
    lines = body.splitlines()
    prefix = f"- {label}: "
    positions = tuple(index for index, line in enumerate(lines) if line.startswith(prefix))
    records: list[tuple[str, str]] = []
    for ordinal, position in enumerate(positions):
        end = positions[ordinal + 1] if ordinal + 1 < len(positions) else len(lines)
        records.append((lines[position][len(prefix) :].strip(), "\n".join(lines[position + 1 : end])))
    return tuple(records)


def _native_mutation_blockers(  # noqa: PLR0913
    body: str, *, section: str, source_label: str, git_label: str, source_mutated: bool, git_mutated: bool
) -> tuple[str, ...]:
    blockers: list[str] = []
    source_values = _native_field_values(body, source_label)
    source_matches = len(source_values) == 1 and bool(source_values[0]) and ((source_values[0] != "none") if source_mutated else (source_values[0] == "none"))
    if not source_matches:
        blockers.append(f"native result {section} source mutation does not match its evidence envelope")
    blockers.extend(_native_values_blockers(body, section=section, label=git_label, expected=("yes" if git_mutated else "no",)))
    return tuple(blockers)


def _native_fingerprint_proof_blockers(body: str, fingerprints: FingerprintEvidence) -> tuple[str, ...]:
    blockers: list[str] = []
    lines = body.splitlines()
    group_positions = tuple(tuple(index for index, line in enumerate(lines) if line == heading) for heading in ("- Expected:", "- Before:", "- After:"))
    if any(len(matches) != 1 for matches in group_positions) or tuple(matches[0] for matches in group_positions) != tuple(
        sorted(matches[0] for matches in group_positions)
    ):
        blockers.append("native independent result Fingerprint Proof groups are incomplete or out of order")
    for ordinal, label in enumerate(("Scope fingerprint", "Worktree fingerprint", "Repository state fingerprint")):
        blockers.extend(
            _native_values_blockers(
                body,
                section="Fingerprint Proof",
                label=label,
                expected=(fingerprints.expected[ordinal], fingerprints.before[ordinal], fingerprints.after[ordinal]),
                indent="  ",
            )
        )
    return tuple(blockers)


def _independent_finding_location_matches_dispatch(location: str, planned_paths: Sequence[str], planned_path_line_bounds: Sequence[tuple[str, int]]) -> bool:
    if len(location) > MAX_NATIVE_IDENTIFIER_LENGTH:
        return False
    line_bounds = dict(planned_path_line_bounds)
    if location in planned_paths:
        return location in line_bounds
    path, separator, line_range = location.rpartition(":")
    if separator != ":" or path not in planned_paths or path not in line_bounds:
        return False
    match = re.fullmatch(r"([1-9]\d*)(?:-([1-9]\d*))?", line_range)
    if match is None:
        return False
    start = int(match.group(1))
    end = match.group(2)
    final = int(end) if end is not None else start
    return start <= final <= line_bounds[path]


def _independent_finding_blockers(body: str, expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> tuple[str, ...]:
    records = _native_records(body, "ID")
    if tuple(finding_id for finding_id, _ in records) != evidence.finding_ids:
        return ("native independent result finding IDs do not match its evidence envelope",)
    blockers: list[str] = []
    labels = ("Severity", "Location", "Summary", "Evidence", "Impact", "Owner", "Remediation")
    for finding_id, record_body in records:
        fields, field_blockers = _native_record_fields(record_body, section=f"independent Finding {finding_id}", labels=labels)
        blockers.extend(field_blockers)
        severity = fields.get("Severity")
        if severity is not None and severity not in {"P0", "P1", "P2", "P3"}:
            blockers.append(f"native independent result Finding {finding_id} has an invalid severity")
        location = fields.get("Location")
        if location is not None and not _independent_finding_location_matches_dispatch(
            location, expectation.planned_paths, expectation.planned_path_line_bounds
        ):
            blockers.append(f"native independent result Finding {finding_id} location is outside its trusted dispatched path line bounds")
        for label in ("Summary", "Evidence", "Impact", "Owner", "Remediation"):
            value = fields.get(label)
            if value is not None and value == "none":
                blockers.append(f"native independent result Finding {finding_id} {label} must contain concrete evidence")
    return tuple(blockers)


def _ordinary_finding_blockers(body: str, evidence: ReviewEvidence) -> tuple[str, ...]:
    records = _native_records(body, "ID")
    if tuple(finding_id for finding_id, _ in records) != evidence.finding_ids:
        return ("native review result finding IDs do not match its evidence envelope",)
    blockers: list[str] = []
    labels = ("Severity", "Location", "Summary", "Evidence", "Remediation")
    for finding_id, record_body in records:
        fields, field_blockers = _native_record_fields(record_body, section=f"Finding {finding_id}", labels=labels)
        blockers.extend(field_blockers)
        severity = fields.get("Severity")
        if severity is not None and severity not in {"P0", "P1", "P2", "P3"}:
            blockers.append(f"native review result Finding {finding_id} has an invalid severity")
        for label in ("Location", "Summary", "Evidence", "Remediation"):
            value = fields.get(label)
            if value is not None and (value == "none" or len(value) > MAX_NATIVE_IDENTIFIER_LENGTH):
                blockers.append(f"native review result Finding {finding_id} {label} must contain bounded concrete evidence")
    return tuple(blockers)


def _native_repository_path_list(value: str, *, label: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if value == "none":
        return (), ()
    raw_paths = tuple(value.split(", "))
    try:
        paths = _normalized_repository_paths(raw_paths, label=label)
    except ValueError:
        return (), (f"native result {label} must contain unique portable repository-relative paths",)
    return paths, ()


def _fix_change_record_blockers(change_id: str, record_body: str, *, expected_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    blockers: list[str] = []
    if change_id != expected_id:
        blockers.append("native fix result Change IDs do not match the ordered node identity")
    labels = ("Finding IDs", "Files", "What changed", "Why", "Contract preserved")
    fields, field_blockers = _native_record_fields(record_body, section=f"Change {change_id}", labels=labels)
    blockers.extend(field_blockers)
    files = fields.get("Files")
    paths: tuple[str, ...] = ()
    if files is not None:
        paths, file_blockers = _native_repository_path_list(files, label=f"Change {change_id} Files")
        blockers.extend(file_blockers)
    if fields.get("Finding IDs") == "none":
        blockers.append(f"native fix result Change {change_id} must identify a finding or incidental change")
    blockers.extend(
        f"native fix result Change {change_id} {label} must contain concrete evidence"
        for label in ("What changed", "Why", "Contract preserved")
        if fields.get(label) == "none"
    )
    return paths, tuple(blockers)


def _fix_change_blockers(state_verification: str, changes: str, expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> tuple[str, ...]:
    if expectation.mode != "fix":
        return ()
    blockers: list[str] = []
    changed_values = _native_field_values(state_verification, "Changed repository paths")
    if len(changed_values) != 1:
        return ("native fix result must report changed repository paths exactly once",)
    changed_paths, path_blockers = _native_repository_path_list(changed_values[0], label="Changed repository paths")
    blockers.extend(path_blockers)
    if evidence.source_mutated is not bool(changed_paths):
        blockers.append("native fix result changed paths contradict its source-mutation evidence")
    unauthorized = tuple(path for path in changed_paths if path not in expectation.planned_paths)
    if unauthorized:
        blockers.append("native fix result changed paths are outside planner authorization: " + ", ".join(unauthorized))
    if not evidence.source_mutated:
        return tuple(blockers)

    records = _native_records(changes, "Change ID")
    if not records:
        blockers.append("native fix result Changes section omits structured change records")
        return tuple(blockers)
    reported_paths: list[str] = []
    for ordinal, (change_id, record_body) in enumerate(records, start=1):
        paths, record_blockers = _fix_change_record_blockers(change_id, record_body, expected_id=f"{evidence.node_id}-change-{ordinal}")
        reported_paths.extend(paths)
        blockers.extend(record_blockers)
    if tuple(dict.fromkeys(reported_paths)) != changed_paths:
        blockers.append("native fix result Changes files do not match its changed repository paths")
    return tuple(blockers)


def _native_state_verification_blockers(body: str, fingerprints: FingerprintEvidence, *, status: str, changed_as_reported: bool = False) -> tuple[str, ...]:
    blockers: list[str] = []
    for ordinal, label in enumerate(("Observed scope fingerprint", "Observed worktree fingerprint", "Observed repository state fingerprint")):
        blockers.extend(
            _native_values_blockers(
                body, section="State Verification", label=label, expected=(fingerprints.before[ordinal], fingerprints.after[ordinal]), indent="  "
            )
        )
    results = _native_field_values(body, "Result", indent="  ")
    if status != "blocked":
        expected_results = ("matched", "changed-as-reported" if changed_as_reported else "matched")
        if results != expected_results:
            blockers.append("native result State Verification results do not match its evidence envelope")
    elif len(results) != 2 or any(result not in {"matched", "mismatched", "blocked", "changed-as-reported"} for result in results):
        blockers.append("native blocked result State Verification results are incomplete")
    return tuple(blockers)


def _ordinary_review_native_blockers(  # noqa: C901, PLR0912
    sections: Mapping[str, str], expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence
) -> tuple[str, ...]:
    blockers: list[str] = []
    skill_loading = sections["## Skill Loading"]
    references_loaded = ", ".join(path for path, _ in expectation.reference_digests) or "none"
    reference_digests = ", ".join(f"{path}={digest}" for path, digest in expectation.reference_digests) or "none"
    blockers.extend(
        _native_header_blockers(
            skill_loading,
            result_kind="Review Skill Loading",
            expected_fields=(
                ("Skill file", expectation.skill_path),
                ("Skill digest", expectation.skill_digest),
                ("References loaded", references_loaded),
                ("Reference digests", reference_digests),
            ),
        )
    )
    state_verification = sections["## State Verification"]
    blockers.extend(
        _native_state_verification_blockers(state_verification, evidence.fingerprints, status=evidence.status, changed_as_reported=evidence.source_mutated)
    )
    blockers.extend(
        _native_mutation_blockers(
            state_verification,
            section="State Verification",
            source_label="Changed repository paths",
            git_label="HEAD, branch, or index mutated",
            source_mutated=evidence.source_mutated,
            git_mutated=evidence.git_mutated,
        )
    )
    scope = sections["## Scope Inspected"]
    if evidence.status != "blocked":
        blockers.extend(_native_nonempty_section_blockers(scope, section="Scope Inspected"))
        files = _native_field_values(scope, "Files")
        if len(files) != 1 or not files[0] or files[0] == "none":
            blockers.append("native review result Scope Inspected does not identify concrete files")
    findings = sections["## Findings"]
    if evidence.status == "no-findings":
        if findings != "none":
            blockers.append("native review result no-findings status requires an exact none Findings section")
    elif evidence.finding_ids:
        blockers.extend(_ordinary_finding_blockers(findings, evidence))
    elif not evidence.finding_ids and evidence.status == "completed" and findings != "none":
        blockers.append("native review result Findings section claims entries absent from its evidence envelope")
    validation_requirements = _native_field_values(sections["## Validation Requirements"], "Requirement ID")
    if evidence.validation_requirement_ids:
        if validation_requirements != evidence.validation_requirement_ids:
            blockers.append("native review result validation requirement IDs do not match its evidence envelope")
    elif sections["## Validation Requirements"] != "none":
        blockers.append("native review result Validation Requirements claims entries absent from its evidence envelope")
    if _native_field_values(sections["## Handoffs"], "Handoff ID") != evidence.handoff_ids:
        blockers.append("native review result handoff IDs do not match its evidence envelope")
    if expectation.mode == "synthesis" and expectation.predecessor_evidence_ids:
        blockers.extend(_native_nonempty_section_blockers(sections["## Predecessor Coverage"], section="Predecessor Coverage"))
    changes = sections["## Changes"]
    if evidence.source_mutated and (not changes or changes == "none"):
        blockers.append("native review result Changes section omits reported source mutation")
    if not evidence.source_mutated and changes != "none":
        blockers.append("native review result Changes section contradicts its evidence envelope")
    blockers.extend(_fix_change_blockers(state_verification, changes, expectation, evidence))
    if evidence.status == "blocked":
        blockers.extend(_native_nonempty_section_blockers(sections["## Limitations"], section="Limitations"))
    return tuple(blockers)


def _independent_review_native_blockers(  # noqa: C901, PLR0912, PLR0915
    sections: Mapping[str, str], expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence
) -> tuple[str, ...]:
    blockers: list[str] = []
    scope = sections["## Scope Inspected"]
    blockers.extend(_native_nonempty_section_blockers(scope, section="Scope Inspected"))
    planned_paths = ", ".join(expectation.planned_paths)
    blockers.extend(_native_values_blockers(scope, section="Scope Inspected", label="Change target", expected=(expectation.change_target or "",)))
    blockers.extend(_native_values_blockers(scope, section="Scope Inspected", label="Files", expected=(planned_paths,)))
    findings = sections["## Findings"]
    if evidence.status == "completed":
        blockers.extend(_independent_finding_blockers(findings, expectation, evidence))
    elif evidence.status == "no-findings":
        if findings != "No findings.":
            blockers.append("native independent result no-findings status requires the exact No findings. assertion")
        inspected = _native_field_values(sections["## No-Finding Evidence"], "Inspected")
        if not inspected or any(not value or value == "none" for value in inspected):
            blockers.append("native independent result no-findings status requires concrete No-Finding Evidence")
    elif evidence.finding_ids and _native_field_values(findings, "ID") != evidence.finding_ids:
        blockers.append("native independent result finding IDs do not match its evidence envelope")
    routing_handoffs = sections["## Routing Handoffs"]
    if evidence.handoff_ids:
        if _native_field_values(routing_handoffs, "Handoff ID") != evidence.handoff_ids:
            blockers.append("native independent result routing handoff IDs do not match its evidence envelope")
    elif routing_handoffs != "none":
        blockers.append("native independent result Routing Handoffs claims entries absent from its evidence envelope")
    fingerprint_proof = sections["## Fingerprint Proof"]
    blockers.extend(_native_nonempty_section_blockers(fingerprint_proof, section="Fingerprint Proof"))
    blockers.extend(_native_fingerprint_proof_blockers(fingerprint_proof, evidence.fingerprints))
    git_state = sections["## Git State"]
    blockers.extend(_native_nonempty_section_blockers(git_state, section="Git State"))
    blockers.extend(
        _native_mutation_blockers(
            git_state,
            section="Git State",
            source_label="Source-controlled files changed",
            git_label="Git state mutated",
            source_mutated=evidence.source_mutated,
            git_mutated=evidence.git_mutated,
        )
    )
    envelope = sections["## Review Graph Envelope"]
    blockers.extend(_native_nonempty_section_blockers(envelope, section="Review Graph Envelope"))
    for label, expected in (
        ("Node ID", evidence.node_id),
        ("Skill", evidence.skill_id),
        ("Mode", evidence.mode),
        ("Status", evidence.status),
        ("Scope fingerprint", evidence.fingerprints.expected[0]),
        ("Worktree fingerprint", evidence.fingerprints.expected[1]),
        ("Repository state fingerprint", evidence.fingerprints.expected[2]),
        ("Skill file", expectation.skill_path),
        ("Change target", expectation.change_target or ""),
        ("Files inspected", planned_paths),
    ):
        blockers.extend(_native_values_blockers(envelope, section="Review Graph Envelope", label=label, expected=(expected,)))
    for ordinal, label in enumerate(("Observed scope fingerprint", "Observed worktree fingerprint", "Observed repository state fingerprint")):
        blockers.extend(
            _native_values_blockers(
                envelope,
                section="Review Graph Envelope",
                label=label,
                expected=(evidence.fingerprints.before[ordinal], evidence.fingerprints.after[ordinal]),
                indent="  ",
            )
        )
    results = _native_field_values(envelope, "Result", indent="  ")
    if evidence.status in {"completed", "no-findings"} and results != ("matched", "matched"):
        blockers.append("native independent result state-verification dispositions contradict accepted status")
    elif evidence.status == "blocked":
        allowed_results = {"matched", "mismatched", "blocked"}
        if len(results) != 2 or any(result not in allowed_results for result in results):
            blockers.append("native blocked independent result state-verification dispositions are incomplete")
        else:
            for observed, result in zip((evidence.fingerprints.before, evidence.fingerprints.after), results, strict=True):
                if result == "matched" and observed != evidence.fingerprints.expected:
                    blockers.append("native blocked independent result reports matched for a mismatched source identity")
                if result == "mismatched" and observed == evidence.fingerprints.expected:
                    blockers.append("native blocked independent result reports mismatched for a matching source identity")
    blockers.extend(
        _native_mutation_blockers(
            envelope,
            section="Review Graph Envelope",
            source_label="Source-controlled files changed",
            git_label="Git state mutated",
            source_mutated=evidence.source_mutated,
            git_mutated=evidence.git_mutated,
        )
    )
    limitations = _native_field_values(envelope, "Limitations")
    if evidence.status in {"completed", "no-findings"} and limitations != ("none",):
        blockers.append("native accepted independent result must report exact none limitations")
    elif evidence.status == "blocked" and (len(limitations) != 1 or not limitations[0] or limitations[0] == "none"):
        blockers.append("native blocked independent result must report one concrete limitation")
    return tuple(blockers)


def _validation_environment_identity(unit: ValidationUnit) -> str:
    return json.dumps(
        {
            "artifact_owner": unit.artifact_owner,
            "allowed_artifacts": unit.allowed_artifacts,
            "environment": unit.environment,
            "features": list(unit.features),
            "mutation_lock": unit.mutation_lock,
            "platform": unit.platform,
            "toolchain": unit.toolchain,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _validation_reused_evidence_blockers(body: str, expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence) -> tuple[str, ...]:
    if evidence.status != "reused":
        return () if body == "none" else ("native validation result Reused Evidence must be exact none when validation was executed",)
    records = _native_records(body, "Ledger entry")
    expected_ids = expectation.validation_unit.evidence_ids
    blockers: list[str] = []
    if tuple(evidence_id for evidence_id, _ in records) != expected_ids or not expected_ids:
        blockers.append("native reused validation result ledger entries do not match its dispatch")
    requirements_by_evidence = {
        evidence_id: tuple(
            requirement_id for requirement_id, *_rest, mapped_evidence_id in expectation.validation_unit.requirement_plans if mapped_evidence_id == evidence_id
        )
        for evidence_id in expected_ids
    }
    for evidence_id, record_body in records:
        fields, field_blockers = _native_record_fields(record_body, section=f"Reused Evidence {evidence_id}", labels=("Requirement IDs", "Match basis"))
        blockers.extend(field_blockers)
        expected_requirements = ", ".join(requirements_by_evidence.get(evidence_id, ()))
        expected_basis = (
            f"source={evidence.fingerprints.expected[2]}; command={expectation.command_identity_digest}; "
            f"environment={expectation.environment_digest}; selection={expected_requirements}"
        )
        if fields.get("Requirement IDs") != expected_requirements or fields.get("Match basis") != expected_basis:
            blockers.append(f"native reused validation result ledger entry {evidence_id} does not match its dispatch identity")
    return tuple(blockers)


def _validation_artifact_blockers(body: str, expectation: ValidationEvidenceExpectation) -> tuple[str, ...]:
    expected = expectation.validation_unit.allowed_artifacts
    if not expected:
        return () if body == "none" else ("native validation result claims artifacts absent from its dispatch",)
    records = _native_records(body, "Path")
    blockers: list[str] = []
    if tuple(path for path, _ in records) != tuple(path for path, _, _ in expected):
        blockers.append("native validation result artifact paths do not match its dispatch")
    for (path, record_body), (_, expected_kind, expected_status) in zip(records, expected, strict=False):
        fields, field_blockers = _native_record_fields(record_body, section=f"Artifact {path}", labels=("Kind", "Repository status"))
        blockers.extend(field_blockers)
        if fields.get("Kind") != expected_kind or fields.get("Repository status") != expected_status:
            blockers.append(f"native validation result artifact {path} does not match its approved kind and repository status")
    return tuple(blockers)


def _validation_ledger_expected_fields(expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence) -> tuple[tuple[str, str], ...]:
    mutated = evidence.source_mutated or evidence.git_mutated
    disposition = "ineligible" if mutated else "candidate-for-reuse" if evidence.status in {"passed", "reused"} else "evidence-only"
    if evidence.status in {"passed", "failed"}:
        commands_and_selections = ", ".join(f"{evidence.node_id}-exec-{ordinal}" for ordinal in range(1, len(expectation.validation_unit.commands) + 1))
    elif evidence.status == "reused":
        commands_and_selections = ", ".join(expectation.validation_unit.evidence_ids) or "none"
    else:
        commands_and_selections = "none"
    return (
        ("Evidence ID", evidence.evidence_id),
        ("Consumer", "review-graph"),
        ("Disposition", disposition),
        ("Requirement IDs", ", ".join(evidence.requirement_ids) if evidence.requirement_ids else "none"),
        ("Commands and selections", commands_and_selections),
        ("Scope fingerprint", evidence.fingerprints.expected[0]),
        ("Worktree fingerprint", evidence.fingerprints.expected[1]),
        ("Repository state fingerprint", evidence.fingerprints.expected[2]),
        ("Environment/configuration", _validation_environment_identity(expectation.validation_unit)),
        ("Command identity digest", expectation.command_identity_digest),
        ("Environment digest", expectation.environment_digest),
        ("Source and Git state", "changed" if mutated else "unchanged"),
        ("Provenance", f"{evidence.node_id}; graph-dispatched; {evidence.status}; {evidence.raw_result_artifact_id}"),
        ("Handoff", "returned directly to review-graph"),
    )


def _validation_coalescing_identity(unit: ValidationUnit) -> str:
    return json.dumps(
        {
            "allowed_artifacts": unit.allowed_artifacts,
            "artifact_owner": unit.artifact_owner,
            "canonical_recipe": unit.canonical_recipe,
            "commands": unit.commands,
            "environment": unit.environment,
            "features": unit.features,
            "mutation_lock": unit.mutation_lock,
            "platform": unit.platform,
            "source_state": unit.source_state,
            "toolchain": unit.toolchain,
            "working_directories": unit.working_directories,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _validation_plan_expected_body(expectation: ValidationEvidenceExpectation) -> str:
    unit = expectation.validation_unit
    authorities = tuple(dict.fromkeys(authority for _, authority, *_ in unit.requirement_plans))
    lines = [
        f"- Request: {unit.request}",
        f"- Requested scope: {unit.requested_scope}",
        f"- Capture command: {unit.capture_command}",
        f"- Captured paths: {', '.join(unit.captured_paths) or 'none'}",
        f"- Authorities inspected: {', '.join(authorities) or 'graph dispatch'}",
    ]
    commands = json.dumps(unit.commands, separators=(",", ":"), ensure_ascii=True) if unit.commands else "none"
    working_directories = json.dumps(unit.working_directories, separators=(",", ":"), ensure_ascii=True) if unit.working_directories else "none"
    configuration = _validation_environment_identity(unit)
    for requirement_id, authority, reason, mutation, expected_evidence, budget, _evidence_id in unit.requirement_plans:
        lines.extend(
            (
                f"- Requirement: {requirement_id}",
                f"  - Authority: {authority}",
                f"  - Selection reason: {reason}",
                f"  - Command: {commands}",
                f"  - Working directory: {working_directories}",
                f"  - Configuration: {configuration}",
                f"  - Mutation classification: {mutation}",
                f"  - Expected evidence: {expected_evidence}",
                f"  - Budget: {budget}",
            )
        )
    lines.extend(
        (
            f"- Coalescing basis: {_validation_coalescing_identity(unit)}",
            f"- Command identity digest: {expectation.command_identity_digest}",
            f"- Environment digest: {expectation.environment_digest}",
            "- Requirement-to-evidence mapping:",
            *(f"  - {requirement_id}: {unit.node_id}; {evidence_id or 'none'}" for requirement_id, *_rest, evidence_id in unit.requirement_plans),
            f"- Meaningful skips: {'; '.join(unit.meaningful_skips) or 'none'}",
            f"- Execution strategy: {unit.execution_strategy}",
            f"- Dependency policy: {unit.dependency_policy}",
            f"- Independence basis: {unit.independence_basis}",
            f"- Planning blocker: {unit.planning_blocker or 'none'}",
        )
    )
    return "\n".join(lines)


def _validation_requirements_expected_body(expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence) -> str:
    if not evidence.requirement_ids:
        return "none"
    disposition = evidence.status if evidence.status in {"passed", "failed", "blocked", "reused"} else "blocked"
    execution_ids = ", ".join(f"{evidence.node_id}-exec-{ordinal}" for ordinal in range(1, len(expectation.validation_unit.commands) + 1))
    reuse_mapping = {requirement_id: evidence_id for requirement_id, *_rest, evidence_id in expectation.validation_unit.requirement_plans}
    records: list[str] = []
    for requirement_id in evidence.requirement_ids:
        if disposition == "reused":
            requirement_evidence = reuse_mapping.get(requirement_id) or "none"
        elif disposition == "blocked":
            requirement_evidence = "blocked execution"
        else:
            requirement_evidence = execution_ids or "none"
        records.append("\n".join((f"- Requirement: {requirement_id}", f"  - Disposition: {disposition}", f"  - Evidence: {requirement_evidence}")))
    return "\n".join(records)


def _validation_native_sections_blockers(  # noqa: C901, PLR0912, PLR0915
    sections: Mapping[str, str], expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence
) -> tuple[str, ...]:
    blockers: list[str] = []
    skill_loading = sections["## Skill Loading"]
    references_loaded = ", ".join(path for path, _ in expectation.reference_digests) or "none"
    reference_digests = ", ".join(f"{path}={digest}" for path, digest in expectation.reference_digests) or "none"
    blockers.extend(
        _native_header_blockers(
            skill_loading,
            result_kind="Validation Skill Loading",
            expected_fields=(
                ("Skill file", expectation.skill_path),
                ("Skill digest", expectation.skill_digest),
                ("References loaded", references_loaded),
                ("Reference digests", reference_digests),
            ),
        )
    )
    validation_plan = sections["## Validation Plan"]
    if validation_plan != _validation_plan_expected_body(expectation):
        blockers.append("native validation result Validation Plan does not match its complete typed dispatch")
    state_verification = sections["## State Verification"]
    blockers.extend(_native_state_verification_blockers(state_verification, evidence.fingerprints, status=evidence.status))

    requirements_body = sections["## Requirements"]
    if requirements_body != _validation_requirements_expected_body(expectation, evidence):
        blockers.append("native validation result Requirements do not match exact dispositions and evidence")
    requirement_records = () if requirements_body == "none" else _native_records(requirements_body, "Requirement")
    requirement_ids = tuple(requirement_id for requirement_id, _ in requirement_records)
    if requirement_ids != evidence.requirement_ids:
        blockers.append("native validation result Requirements IDs do not match its evidence envelope")
    requirement_dispositions: list[str] = []
    for _, record_body in requirement_records:
        dispositions = _native_field_values(record_body, "Disposition", indent="  ")
        if len(dispositions) != 1 or dispositions[0] not in {"passed", "failed", "blocked", "reused"}:
            blockers.append("native validation result Requirement disposition is missing or invalid")
            continue
        requirement_dispositions.append(dispositions[0])

    executions_body = sections["## Executions"]
    execution_records = () if executions_body == "none" else _native_records(executions_body, "Execution ID")
    execution_ids = tuple(execution_id for execution_id, _ in execution_records)
    if any(not execution_id for execution_id in execution_ids) or _duplicate_values(execution_ids):
        blockers.append("native validation result Execution IDs must be unique non-empty values")
    execution_commands: list[str] = []
    execution_results: list[str] = []
    execution_labels = (
        "Executor",
        "Command",
        "Working directory",
        "Environment/configuration",
        "Result",
        "Exit code",
        "Elapsed",
        "Evidence",
        "Log or artifact",
    )
    expected_environment = _validation_environment_identity(expectation.validation_unit)
    for ordinal, (execution_id, record_body) in enumerate(execution_records, start=1):
        fields, field_blockers = _native_record_fields(record_body, section=f"Execution {execution_id}", labels=execution_labels)
        blockers.extend(field_blockers)
        if execution_id != f"{evidence.node_id}-exec-{ordinal}":
            blockers.append("native validation result Execution IDs do not match the ordered validator identity")
        executor = fields.get("Executor")
        if executor is not None and executor == "none":
            blockers.append(f"native validation result Execution {execution_id} has no concrete executor")
        command = fields.get("Command")
        if command is not None:
            execution_commands.append(command)
        working_directory = fields.get("Working directory")
        if (
            ordinal <= len(expectation.validation_unit.working_directories)
            and working_directory is not None
            and working_directory != expectation.validation_unit.working_directories[ordinal - 1]
        ):
            blockers.append(f"native validation result Execution {execution_id} working directory does not match its dispatch")
        environment = fields.get("Environment/configuration")
        if environment is not None and environment != expected_environment:
            blockers.append(f"native validation result Execution {execution_id} environment does not match its dispatch")
        result = fields.get("Result")
        if result is None or result not in {"passed", "failed", "blocked", "not-run"}:
            blockers.append("native validation result Execution result is missing or invalid")
        else:
            execution_results.append(result)
            exit_code = fields.get("Exit code")
            elapsed = fields.get("Elapsed")
            execution_evidence = fields.get("Evidence")
            if result == "passed" and exit_code != "0":
                blockers.append(f"native validation result passed Execution {execution_id} requires exit code 0")
            if result == "failed" and (exit_code is None or re.fullmatch(r"-?\d+", exit_code) is None or int(exit_code) == 0):
                blockers.append(f"native validation result failed Execution {execution_id} requires a nonzero exit code")
            if result == "blocked" and exit_code is not None and exit_code != "none" and (re.fullmatch(r"-?\d+", exit_code) is None or int(exit_code) == 0):
                blockers.append(f"native validation result blocked Execution {execution_id} has an invalid exit code")
            if result == "not-run" and exit_code != "none":
                blockers.append(f"native validation result not-run Execution {execution_id} requires exit code none")
            if result in {"passed", "failed"} and (elapsed is None or elapsed == "none"):
                blockers.append(f"native validation result executed command {execution_id} requires concrete elapsed time")
            if result == "not-run" and elapsed != "none":
                blockers.append(f"native validation result not-run Execution {execution_id} requires elapsed none")
            if execution_evidence is None or execution_evidence == "none":
                blockers.append(f"native validation result Execution {execution_id} requires concrete evidence")

    expected_commands = expectation.validation_unit.commands
    if evidence.status in {"passed", "failed"} and tuple(execution_commands) != expected_commands:
        blockers.append("native validation result Executions do not match the exact dispatched commands")
    if evidence.status == "blocked" and tuple(execution_commands) != expected_commands[: len(execution_commands)]:
        blockers.append("native blocked validation result Executions are not an ordered dispatch prefix")
    if evidence.status in {"reused", "not-applicable"} and execution_records:
        blockers.append("native validation result status forbids execution records")
    if expectation.validation_unit.dependency_policy == "stop-on-failure":
        stopping_index = next((index for index, result in enumerate(execution_results) if result in {"failed", "blocked"}), None)
        if stopping_index is not None and any(result != "not-run" for result in execution_results[stopping_index + 1 :]):
            blockers.append("native validation result violates its stop-on-failure dependency policy")
    elif expectation.validation_unit.dependency_policy == "continue-independent" and "not-run" in execution_results:
        blockers.append("native validation result violates its continue-independent dependency policy")
    blockers.extend(_validation_reused_evidence_blockers(sections["## Reused Evidence"], expectation, evidence))
    blockers.extend(_validation_artifact_blockers(sections["## Artifacts"], expectation))

    dispositions = tuple(requirement_dispositions)
    results = tuple(execution_results)
    if evidence.status == "passed" and (
        not results or any(result != "passed" for result in results) or any(item not in {"passed", "reused"} for item in dispositions)
    ):
        blockers.append("native validation result passed status contradicts Requirements or Executions")
    if evidence.status == "failed" and ("failed" not in results or "failed" not in dispositions or "blocked" in dispositions):
        blockers.append("native validation result failed status contradicts Requirements or Executions")
    if evidence.status == "blocked" and "blocked" not in dispositions:
        blockers.append("native validation result blocked status requires a blocked Requirement")
    if evidence.status == "reused" and (not dispositions or any(item != "reused" for item in dispositions)):
        blockers.append("native validation result reused status requires every Requirement to be reused")
    if evidence.status == "not-applicable" and (requirement_records or execution_records):
        blockers.append("native validation result not-applicable status requires zero Requirements and Executions")

    requirement_counts = {status: dispositions.count(status) for status in ("passed", "failed", "blocked", "reused")}
    execution_counts = {status: results.count(status) for status in ("passed", "failed", "blocked", "not-run")}
    outcome = sections["## Outcome Summary"]
    expected_overall = {"passed": "PASSED", "failed": "FAILED", "blocked": "BLOCKED", "reused": "REUSED", "not-applicable": "NOT-APPLICABLE"}.get(
        evidence.status
    )
    expected_requirement_counts = "; ".join(f"{status} {requirement_counts[status]}" for status in ("passed", "failed", "blocked", "reused"))
    expected_execution_counts = "; ".join(f"{status} {execution_counts[status]}" for status in ("passed", "failed", "blocked", "not-run"))
    if expected_overall is None:
        blockers.append("native validation result has an unsupported status")
    else:
        for label, expected in (
            ("Overall", expected_overall),
            ("Requirements", expected_requirement_counts),
            ("Executions", expected_execution_counts),
            ("Review findings", "not evaluated (validation-only)"),
            ("Review severities", "P0 not evaluated; P1 not evaluated; P2 not evaluated; P3 not evaluated"),
        ):
            blockers.extend(_native_values_blockers(outcome, section="Outcome Summary", label=label, expected=(expected,)))

    source_and_git = sections["## Source And Git State"]
    blockers.extend(
        _native_mutation_blockers(
            source_and_git,
            section="Source And Git State",
            source_label="Source-controlled files changed",
            git_label="Git state mutated",
            source_mutated=evidence.source_mutated,
            git_mutated=evidence.git_mutated,
        )
    )
    ledger = sections["## Validation Ledger Export"]
    blockers.extend(_native_nonempty_section_blockers(ledger, section="Validation Ledger Export"))
    blockers.extend(
        _native_header_blockers(ledger, result_kind="Validation Ledger Export", expected_fields=_validation_ledger_expected_fields(expectation, evidence))
    )
    if evidence.status == "blocked":
        blockers.extend(_native_nonempty_section_blockers(sections["## Limitations"], section="Limitations"))
    return tuple(blockers)


def _review_native_header_blockers(body: str, expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> tuple[str, ...]:
    return _native_header_blockers(
        body,
        result_kind="Review Node Result",
        expected_fields=(
            ("Node ID", evidence.node_id),
            ("Skill", evidence.skill_id),
            ("Mode", evidence.mode),
            ("Evidence schema version", str(EVIDENCE_SCHEMA_VERSION)),
            ("Execution profile", evidence.execution_profile),
            ("Execution location", evidence.execution_location),
            ("Status", evidence.status),
            ("Selection reason", expectation.selection_reason),
            ("Scope fingerprint", evidence.fingerprints.expected[0]),
            ("Worktree fingerprint", evidence.fingerprints.expected[1]),
            ("Repository state fingerprint", evidence.fingerprints.expected[2]),
            ("Authorization", expectation.authorization),
        ),
    )


def _validation_native_header_blockers(body: str, evidence: ValidationEvidence) -> tuple[str, ...]:
    return _native_header_blockers(
        body,
        result_kind="Validation Result",
        expected_fields=(
            ("Node ID", evidence.node_id),
            ("Skill", "review-validator"),
            ("Invocation", "graph-dispatched"),
            ("Evidence schema version", str(EVIDENCE_SCHEMA_VERSION)),
            ("Execution profile", evidence.execution_profile),
            ("Execution location", evidence.execution_location),
            ("Status", evidence.status),
            ("Scope fingerprint", evidence.fingerprints.expected[0]),
            ("Worktree fingerprint", evidence.fingerprints.expected[1]),
            ("Repository state fingerprint", evidence.fingerprints.expected[2]),
        ),
    )


def _review_native_result_blockers(content: bytes, expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> tuple[str, ...]:
    independent = evidence.mode == "independent-review"
    payload, preamble, sections, parse_blockers = _parse_native_result(
        content,
        expected_heading="# Repository Independent Review" if independent else "# Review Node Result",
        required_sections=_INDEPENDENT_RESULT_SECTIONS if independent else _REVIEW_RESULT_SECTIONS,
    )
    blockers = list(parse_blockers)
    if payload is None or preamble is None or sections is None:
        return tuple(blockers)
    if independent:
        if preamble:
            blockers.append("native independent result must not contain an untyped result header")
    else:
        blockers.extend(_review_native_header_blockers(preamble, expectation, evidence))
    blockers.extend(
        _native_payload_shape_blockers(payload, expected_keys=_INDEPENDENT_REVIEW_NATIVE_EVIDENCE_KEYS if independent else _REVIEW_NATIVE_EVIDENCE_KEYS)
    )
    expected_payload: dict[str, Any] = {
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
        "predecessor_evidence_ids": list(evidence.predecessor_evidence_ids),
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
        expected_payload.update(
            {"change_target": expectation.change_target, "handoff_ids": list(evidence.handoff_ids), "inspected_paths": list(expectation.planned_paths)}
        )
    for field_name, expected_value in expected_payload.items():
        if payload.get(field_name) != expected_value:
            blockers.append(f"native review result {field_name} does not match its evidence envelope")
    if tuple(evidence.predecessor_evidence_ids) != tuple(expectation.predecessor_evidence_ids):
        blockers.append("native review result predecessor evidence does not match its dispatch")
    blockers.extend(
        _independent_review_native_blockers(sections, expectation, evidence)
        if independent
        else _ordinary_review_native_blockers(sections, expectation, evidence)
    )
    return tuple(blockers)


def _validation_native_result_blockers(content: bytes, expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence) -> tuple[str, ...]:
    payload, preamble, sections, parse_blockers = _parse_native_result(
        content, expected_heading="# Validation Result", required_sections=_VALIDATION_RESULT_SECTIONS
    )
    blockers = list(parse_blockers)
    if payload is None or preamble is None or sections is None:
        return tuple(blockers)
    blockers.extend(_validation_native_header_blockers(preamble, evidence))
    blockers.extend(_native_payload_shape_blockers(payload, expected_keys=_VALIDATION_NATIVE_EVIDENCE_KEYS))
    expected_payload: dict[str, Any] = {
        "after_repository_state_fingerprint": evidence.fingerprints.after[2],
        "after_scope_fingerprint": evidence.fingerprints.after[0],
        "after_worktree_fingerprint": evidence.fingerprints.after[1],
        "artifact_id": evidence.raw_result_artifact_id,
        "before_repository_state_fingerprint": evidence.fingerprints.before[2],
        "before_scope_fingerprint": evidence.fingerprints.before[0],
        "before_worktree_fingerprint": evidence.fingerprints.before[1],
        "command_identity_digest": evidence.command_identity_digest,
        "environment_digest": evidence.environment_digest,
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
    for field_name, expected_value in expected_payload.items():
        if payload.get(field_name) != expected_value:
            blockers.append(f"native validation result {field_name} does not match its evidence envelope")
    if expectation.requirement_ids != tuple(evidence.requirement_ids):
        blockers.append("native validation result requirements do not match its dispatch")
    blockers.extend(_validation_native_sections_blockers(sections, expectation, evidence))
    return tuple(blockers)


def repository_review_proof_expectation(plan: GraphPlan, *, source_state: tuple[str, str, str]) -> RepositoryReviewProofExpectation:
    """Derive the only proof identity accepted for one graph plan."""
    return RepositoryReviewProofExpectation(plan=plan, source_state=source_state)


def validation_command_identity_digest(unit: ValidationUnit) -> str:
    """Hash the exact command-selection portion of a validator dispatch."""
    return _sha256_json({"canonical_recipe": unit.canonical_recipe, "commands": unit.commands, "working_directories": unit.working_directories})


def validation_environment_digest(unit: ValidationUnit) -> str:
    """Hash the exact environment and shared-resource validator identity."""
    return _sha256_json(
        {
            "artifact_owner": unit.artifact_owner,
            "allowed_artifacts": unit.allowed_artifacts,
            "environment": unit.environment,
            "features": unit.features,
            "mutation_lock": unit.mutation_lock,
            "platform": unit.platform,
            "toolchain": unit.toolchain,
        }
    )


def validation_evidence_expectation(  # noqa: PLR0913
    unit: ValidationUnit, *, skill_path: str, skill_digest: str, reference_digests: tuple[tuple[str, str], ...], execution_profile: str, execution_location: str
) -> ValidationEvidenceExpectation:
    """Construct a validator expectation from one exact coalesced dispatch."""
    return ValidationEvidenceExpectation(
        node_id=unit.node_id,
        requirement_ids=unit.requirement_ids,
        skill_path=skill_path,
        skill_digest=skill_digest,
        reference_digests=reference_digests,
        source_state=unit.source_state,
        execution_profile=execution_profile,
        execution_location=execution_location,
        validation_unit=unit,
    )


def _manifest_entry_digest(*, evidence_id: str, artifact_id: str, artifact_digest: str) -> str:
    return _sha256_json({"artifact_digest": artifact_digest, "artifact_id": artifact_id, "evidence_id": evidence_id})


def _manifest_digest(manifest: ArtifactManifest) -> str:
    entries = sorted(
        (
            {"artifact_digest": entry.artifact_digest, "artifact_id": entry.artifact_id, "entry_digest": entry.entry_digest, "evidence_id": entry.evidence_id}
            for entry in manifest.entries
        ),
        key=lambda item: (item["evidence_id"], item["artifact_id"]),
    )
    return _sha256_json(
        {"entries": entries, "manifest_id": manifest.manifest_id, "schema_version": manifest.schema_version, "verifier_id": manifest.verifier_id}
    )


def create_artifact_manifest(*, manifest_id: str, verifier_id: str, artifacts: Sequence[tuple[str, str, bytes]]) -> ArtifactManifest:
    """Create canonical manifest metadata; acceptance still recomputes every digest."""
    entries = tuple(
        ArtifactManifestEntry(
            evidence_id=evidence_id,
            artifact_id=artifact_id,
            artifact_digest=_sha256_bytes(content),
            entry_digest=_manifest_entry_digest(evidence_id=evidence_id, artifact_id=artifact_id, artifact_digest=_sha256_bytes(content)),
        )
        for evidence_id, artifact_id, content in artifacts
    )
    manifest = ArtifactManifest(
        schema_version=EVIDENCE_SCHEMA_VERSION, manifest_id=manifest_id, verifier_id=verifier_id, entries=entries, manifest_digest="pending"
    )
    return replace(manifest, manifest_digest=_manifest_digest(manifest))


def assess_review_evidence(expectation: ReviewEvidenceExpectation, evidence: ReviewEvidence) -> EvidenceAssessment:  # noqa: C901, PLR0912, PLR0915
    """Accept the same persisted proof envelope for worker or coordinator review."""
    blockers: list[str] = []
    if not isinstance(evidence.schema_version, int) or isinstance(evidence.schema_version, bool) or evidence.schema_version != EVIDENCE_SCHEMA_VERSION:
        blockers.append(f"review evidence schema must be exactly {EVIDENCE_SCHEMA_VERSION}")
    for value, label in (
        (evidence.evidence_id, "evidence ID"),
        (evidence.skill_digest, "skill digest"),
        (evidence.raw_result_artifact_id, "raw result artifact ID"),
        (evidence.raw_result_digest, "raw result digest"),
    ):
        if not _nonempty_text(value):
            blockers.append(f"review evidence has no {label}")
    for actual, expected, label in (
        (evidence.node_id, expectation.node_id, "node ID"),
        (evidence.skill_id, expectation.skill_id, "skill ID"),
        (evidence.mode, expectation.mode, "mode"),
        (evidence.skill_path, expectation.skill_path, "skill path"),
        (evidence.skill_digest, expectation.skill_digest, "skill digest"),
        (evidence.fingerprints.expected, expectation.source_state, "captured source fingerprints"),
        (evidence.execution_profile, expectation.execution_profile, "execution profile"),
    ):
        if actual != expected:
            blockers.append(f"review evidence {label} does not match its dispatch")
    if set(evidence.requirement_ids) != set(expectation.requirement_ids) or _duplicate_values(evidence.requirement_ids):
        blockers.append("review evidence requirement IDs do not match the dispatch exactly")
    blockers.extend(_identifier_tuple_blockers(evidence.requirement_ids, label="review evidence requirement IDs"))
    blockers.extend(_identifier_tuple_blockers(evidence.finding_ids, label="review evidence finding IDs"))
    blockers.extend(_identifier_tuple_blockers(evidence.validation_requirement_ids, label="review evidence validation requirement IDs"))
    blockers.extend(_identifier_tuple_blockers(evidence.handoff_ids, label="review evidence handoff IDs"))
    blockers.extend(_identifier_tuple_blockers(evidence.predecessor_evidence_ids, label="review evidence predecessor evidence IDs"))
    if evidence.predecessor_evidence_ids != expectation.predecessor_evidence_ids:
        blockers.append("review evidence predecessor evidence IDs do not match the dispatch exactly")
    if expectation.mode != "synthesis" and (expectation.predecessor_evidence_ids or evidence.predecessor_evidence_ids):
        blockers.append("non-synthesis review evidence cannot claim predecessor evidence")
    if dict(evidence.reference_digests) != dict(expectation.reference_digests) or _duplicate_values(tuple(path for path, _ in evidence.reference_digests)):
        blockers.append("review evidence reference digests do not match the dispatch exactly")
    if _duplicate_values(tuple(path for path, _ in expectation.reference_digests)) or any(
        not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in expectation.reference_digests
    ):
        blockers.append("review evidence expectation has invalid reference digests")
    if any(not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in evidence.reference_digests):
        blockers.append("review evidence reference paths and digests must be non-empty")
    if (
        not _nonempty_text(expectation.selection_reason)
        or "\n" in expectation.selection_reason
        or len(expectation.selection_reason) > MAX_NATIVE_IDENTIFIER_LENGTH
    ):
        blockers.append("review evidence expectation has no bounded single-line selection reason")
    if expectation.authorization not in {"review-only", "review-and-fix"}:
        blockers.append("review evidence expectation has an invalid authorization")
    if expectation.mode == "fix" and expectation.authorization != "review-and-fix":
        blockers.append("fix evidence expectation requires review-and-fix authorization")
    if expectation.execution_profile not in {"grouped", "isolated", "isolated-only", "mixed"}:
        blockers.append("review evidence expectation has an invalid execution profile")
    if expectation.mode not in {"audit", "synthesis", "fix", "revalidation", "independent-review"}:
        blockers.append("review evidence expectation has an invalid mode")
    if expectation.mode in {"fix", "independent-review"}:
        blockers.extend(_identifier_tuple_blockers(expectation.planned_paths, label=f"{expectation.mode} planned paths"))
        try:
            normalized_planned_paths = _normalized_repository_paths(expectation.planned_paths, label=f"{expectation.mode} planned paths")
        except ValueError:
            normalized_planned_paths = ()
            blockers.append(f"{expectation.mode} evidence expectation has invalid planned paths")
        if not expectation.planned_paths:
            blockers.append(f"{expectation.mode} evidence expectation has no planned paths")
        elif normalized_planned_paths != expectation.planned_paths:
            blockers.append(f"{expectation.mode} evidence expectation planned paths are not normalized")
    if expectation.mode == "independent-review":
        if (
            not isinstance(expectation.change_target, str)
            or not expectation.change_target.strip()
            or len(expectation.change_target) > MAX_NATIVE_IDENTIFIER_LENGTH
        ):
            blockers.append("independent-review evidence expectation has no bounded change target")
        if tuple(path for path, _ in expectation.planned_path_line_bounds) != expectation.planned_paths or any(
            not isinstance(bound, int) or isinstance(bound, bool) or bound < 0 for _, bound in expectation.planned_path_line_bounds
        ):
            blockers.append("independent-review evidence expectation line bounds do not match its planned paths")
    elif expectation.mode == "fix":
        if expectation.change_target is not None or expectation.planned_path_line_bounds:
            blockers.append("fix review evidence expectation cannot claim independent target provenance")
    elif expectation.change_target is not None or expectation.planned_paths or expectation.planned_path_line_bounds:
        blockers.append("non-independent review evidence expectation cannot claim independent target provenance")
    if evidence.execution_location not in {"worker", "coordinator"}:
        blockers.append("review evidence execution location is invalid")
    elif evidence.execution_location == "worker" and evidence.worker_created is not True:
        blockers.append("worker execution lacks exact worker-creation evidence")
    elif evidence.execution_location == "coordinator" and evidence.worker_created is not False:
        blockers.append("coordinator execution cannot claim worker creation")
    if expectation.execution_profile in {"isolated", "isolated-only"} and (
        evidence.execution_location != "worker" or evidence.worker_created is not True or evidence.fresh_context is not True
    ):
        blockers.append("isolated review evidence requires a fresh worker execution")
    if not isinstance(evidence.fresh_context, bool):
        blockers.append("fresh-context evidence must be a boolean")
    if not isinstance(evidence.source_mutated, bool) or not isinstance(evidence.git_mutated, bool):
        blockers.append("review evidence mutation fields must be booleans")
    if evidence.status not in {"completed", "no-findings", "blocked"}:
        blockers.append("review evidence status is invalid")
    if not isinstance(evidence.report_complete, bool):
        blockers.append("review evidence report-complete compatibility field must be a boolean")
    if evidence.status == "no-findings" and evidence.finding_ids:
        blockers.append("no-findings review evidence cannot contain finding IDs")
    if expectation.mode == "independent-review" and evidence.status == "completed" and not evidence.finding_ids:
        blockers.append("completed independent-review evidence must contain at least one finding ID")

    satisfies = evidence.status in {"completed", "no-findings"}
    if satisfies:
        expected_after = expectation.expected_after_state or expectation.source_state
        if evidence.fingerprints.before != expectation.source_state:
            blockers.append("review evidence before fingerprints do not match the captured source state")
        if evidence.fingerprints.after != expected_after:
            blockers.append("review evidence after fingerprints do not match the expected source state")
        if evidence.git_mutated is not False:
            blockers.append("accepted review evidence mutated Git state")
        if evidence.source_mutated is not expectation.source_mutation_allowed:
            blockers.append("review evidence source-mutation status does not match its dispatch")
    return EvidenceAssessment(not blockers, tuple(blockers), satisfies and not blockers)


def assess_validation_evidence(  # noqa: C901, PLR0912, PLR0915
    expectation: ValidationEvidenceExpectation, evidence: ValidationEvidence
) -> EvidenceAssessment:
    """Accept a persisted review-validator result without transferring trust blindly."""
    blockers: list[str] = []
    if not isinstance(evidence.schema_version, int) or isinstance(evidence.schema_version, bool) or evidence.schema_version != EVIDENCE_SCHEMA_VERSION:
        blockers.append(f"validation evidence schema must be exactly {EVIDENCE_SCHEMA_VERSION}")
    for value, label in (
        (evidence.evidence_id, "evidence ID"),
        (evidence.skill_digest, "skill digest"),
        (evidence.command_identity_digest, "command identity digest"),
        (evidence.environment_digest, "environment digest"),
        (evidence.raw_result_artifact_id, "raw result artifact ID"),
        (evidence.raw_result_digest, "raw result digest"),
    ):
        if not _nonempty_text(value):
            blockers.append(f"validation evidence has no {label}")
    if evidence.node_id != expectation.node_id:
        blockers.append("validation evidence node ID does not match its dispatch")
    if not _nonempty_text(expectation.skill_path) or len(expectation.skill_path) > MAX_NATIVE_IDENTIFIER_LENGTH:
        blockers.append("validation evidence expectation has no bounded skill path")
    if expectation.node_id != expectation.validation_unit.node_id:
        blockers.append("validation evidence expectation node ID does not match its exact validation unit dispatch")
    if set(evidence.requirement_ids) != set(expectation.requirement_ids) or _duplicate_values(evidence.requirement_ids):
        blockers.append("validation evidence requirement IDs do not match the dispatch exactly")
    if set(expectation.requirement_ids) != set(expectation.validation_unit.requirement_ids) or _duplicate_values(expectation.requirement_ids):
        blockers.append("validation evidence expectation requirement IDs do not match its exact validation unit dispatch")
    blockers.extend(_identifier_tuple_blockers(evidence.requirement_ids, label="validation evidence requirement IDs"))
    if evidence.skill_digest != expectation.skill_digest:
        blockers.append("validation evidence skill digest does not match its dispatch")
    if dict(evidence.reference_digests) != dict(expectation.reference_digests) or _duplicate_values(tuple(path for path, _ in evidence.reference_digests)):
        blockers.append("validation evidence reference digests do not match the dispatch exactly")
    if _duplicate_values(tuple(path for path, _ in expectation.reference_digests)) or any(
        not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in expectation.reference_digests
    ):
        blockers.append("validation evidence expectation has invalid reference digests")
    if any(not _nonempty_text(path) or not _nonempty_text(digest) for path, digest in evidence.reference_digests):
        blockers.append("validation evidence reference paths and digests must be non-empty")
    if evidence.fingerprints.expected != expectation.source_state:
        blockers.append("validation evidence captured fingerprints do not match its dispatch")
    if expectation.source_state != expectation.validation_unit.source_state:
        blockers.append("validation evidence expectation source state does not match its exact validation unit dispatch")
    if evidence.command_identity_digest != expectation.command_identity_digest:
        blockers.append("validation evidence command identity digest does not match its exact validation unit dispatch")
    if evidence.environment_digest != expectation.environment_digest:
        blockers.append("validation evidence environment digest does not match its exact validation unit dispatch")
    if evidence.execution_profile != expectation.execution_profile:
        blockers.append("validation evidence execution profile does not match its dispatch")
    if expectation.execution_profile not in {"grouped", "isolated", "isolated-only", "mixed"}:
        blockers.append("validation evidence expectation has an invalid execution profile")
    if evidence.execution_location != expectation.execution_location or evidence.execution_location not in {"worker", "coordinator"}:
        blockers.append("validation evidence execution location does not match its dispatch")
    elif evidence.execution_location == "worker" and evidence.worker_created is not True:
        blockers.append("validation worker execution lacks exact worker-creation evidence")
    elif evidence.execution_location == "coordinator" and evidence.worker_created is not False:
        blockers.append("validation coordinator execution cannot claim worker creation")
    if expectation.execution_profile in {"isolated", "isolated-only"} and (
        evidence.execution_location != "worker" or evidence.worker_created is not True or evidence.fresh_context is not True
    ):
        blockers.append("isolated validation evidence requires a fresh worker execution")
    if not isinstance(evidence.fresh_context, bool):
        blockers.append("validation fresh-context evidence must be a boolean")
    if not isinstance(evidence.source_mutated, bool) or not isinstance(evidence.git_mutated, bool):
        blockers.append("validation evidence mutation fields must be booleans")
    if evidence.status not in {"passed", "failed", "blocked", "reused", "not-applicable"}:
        blockers.append("validation evidence status is invalid")
    if evidence.status == "not-applicable" and evidence.requirement_ids:
        blockers.append("not-applicable validation evidence cannot satisfy requirements")

    state_checked_status = evidence.status in {"passed", "failed", "reused", "not-applicable"}
    if state_checked_status:
        if evidence.fingerprints.before != expectation.source_state or evidence.fingerprints.after != expectation.source_state:
            blockers.append("validation evidence did not preserve the captured source state")
        if evidence.source_mutated is not False or evidence.git_mutated is not False:
            blockers.append("validation evidence mutated source or Git state")
    satisfies = evidence.status in {"passed", "reused"} or (evidence.status == "not-applicable" and not evidence.requirement_ids)
    return EvidenceAssessment(not blockers, tuple(blockers), satisfies and not blockers)


def _proof_mapping_blockers(
    *, label: str, required_ids: Sequence[str], mapping: Sequence[tuple[str, str]], accepted_evidence_ids: Sequence[str], stale_evidence_ids: Sequence[str]
) -> tuple[str, ...]:
    blockers: list[str] = []
    required = set(required_ids)
    mapped_ids = tuple(requirement_id for requirement_id, _ in mapping)
    blockers.extend(_identifier_tuple_blockers(tuple(required_ids), label=f"{label} requirement IDs"))
    blockers.extend(_identifier_tuple_blockers(tuple(accepted_evidence_ids), label=f"accepted {label} evidence IDs"))
    if _duplicate_values(tuple(required_ids)):
        blockers.append(f"{label} requirements contain duplicate IDs")
    if _duplicate_values(mapped_ids):
        blockers.append(f"{label} proof maps a requirement more than once")
    if set(mapped_ids) != required:
        blockers.append(f"{label} proof does not map every required requirement exactly once")
    accepted = set(accepted_evidence_ids)
    stale = set(stale_evidence_ids)
    unaccepted = sorted({evidence_id for _, evidence_id in mapping} - accepted)
    if any(not _nonempty_text(requirement_id) or not _nonempty_text(evidence_id) for requirement_id, evidence_id in mapping):
        blockers.append(f"{label} proof mappings must contain non-empty IDs")
    if unaccepted:
        blockers.append(f"{label} proof references unaccepted evidence: {', '.join(unaccepted)}")
    stale_mappings = sorted({evidence_id for _, evidence_id in mapping} & stale)
    if stale_mappings:
        blockers.append(f"{label} proof references stale evidence: {', '.join(stale_mappings)}")
    return tuple(blockers)


def _planned_node_mapping_blockers(  # noqa: C901, PLR0912
    expectation: RepositoryReviewProofExpectation, proof: RepositoryReviewProof
) -> tuple[str, ...]:
    """Require one unique accepted evidence record for every executable node."""
    blockers: list[str] = []
    expected_nodes = {node.node_id: node for node in expectation.planned_evidence_nodes}
    mapped_node_ids = tuple(node_id for node_id, _ in proof.planned_node_evidence)
    mapped_evidence_ids = tuple(evidence_id for _, evidence_id in proof.planned_node_evidence)
    blockers.extend(_identifier_tuple_blockers(mapped_node_ids, label="planned-node proof node IDs"))
    blockers.extend(_identifier_tuple_blockers(mapped_evidence_ids, label="planned-node proof evidence IDs"))
    if _duplicate_values(mapped_node_ids):
        blockers.append("repository review proof maps a planned node more than once")
    if _duplicate_values(mapped_evidence_ids):
        blockers.append("repository review proof maps one evidence record to multiple planned nodes")
    if set(mapped_node_ids) != set(expected_nodes):
        blockers.append("repository review proof does not map every planned executable node exactly once")
    accepted_review = set(proof.accepted_review_evidence_ids)
    accepted_validation = set(proof.accepted_validation_evidence_ids)
    overlapping = sorted(accepted_review & accepted_validation)
    if overlapping:
        blockers.append("review and validation accepted evidence IDs overlap: " + ", ".join(overlapping))
    reused_review = {evidence_id for _, evidence_id in expectation.exact_reused_review_evidence}
    if reused_review & accepted_validation:
        blockers.append("exactly reused review evidence cannot be accepted as validation evidence")
    accepted = accepted_review | accepted_validation
    mapped = set(mapped_evidence_ids)
    expected_accepted = mapped | reused_review
    if accepted != expected_accepted:
        missing = sorted(mapped - accepted)
        missing_reuse = sorted(reused_review - accepted_review)
        unplanned = sorted(accepted - expected_accepted)
        if missing:
            blockers.append("planned nodes reference unaccepted evidence: " + ", ".join(missing))
        if missing_reuse:
            blockers.append("routed exact-reuse evidence is not accepted review evidence: " + ", ".join(missing_reuse))
        if unplanned:
            blockers.append("accepted evidence is neither mapped to a planned executable node nor exact routed reuse: " + ", ".join(unplanned))
    reuse_node_overlap = sorted(mapped & reused_review)
    if reuse_node_overlap:
        blockers.append("exactly reused evidence cannot also satisfy an executable node: " + ", ".join(reuse_node_overlap))
    stale = sorted(expected_accepted & set(proof.stale_evidence_ids))
    if stale:
        blockers.append("planned nodes reference stale evidence: " + ", ".join(stale))
    mapped_by_node = dict(proof.planned_node_evidence)
    final_evidence_id = mapped_by_node.get(expectation.final_synthesis_identity[0])
    if final_evidence_id != proof.final_synthesis_evidence_id:
        blockers.append("final synthesis evidence does not match the planned repository synthesis node")
    for node_id, evidence_id in proof.planned_node_evidence:
        node = expected_nodes.get(node_id)
        if node is None:
            continue
        expected_set = accepted_validation if node.mode == "validation" else accepted_review
        if evidence_id not in expected_set:
            blockers.append(f"planned {node.mode} node maps to the wrong evidence kind: {node_id} -> {evidence_id}")
    return tuple(blockers)


def assess_repository_review_proof(  # noqa: C901
    expectation: RepositoryReviewProofExpectation, proof: RepositoryReviewProof
) -> Assessment:
    """Require complete, reusable evidence mappings before final synthesis is trusted."""
    blockers: list[str] = []
    if not isinstance(expectation, RepositoryReviewProofExpectation):
        return Assessment(feasible=False, blockers=("repository review proof requires a typed planner-derived expectation",))
    if not isinstance(proof.schema_version, int) or isinstance(proof.schema_version, bool) or proof.schema_version != EVIDENCE_SCHEMA_VERSION:
        blockers.append(f"repository review proof schema must be exactly {EVIDENCE_SCHEMA_VERSION}")
    for value, label in (
        (proof.proof_id, "proof ID"),
        (proof.plan_digest, "plan digest"),
        (proof.final_synthesis_evidence_id, "final synthesis evidence ID"),
        (proof.artifact_manifest_id, "artifact manifest ID"),
        (proof.artifact_manifest_digest, "artifact manifest digest"),
        (proof.verifier_id, "verifier ID"),
    ):
        if not _nonempty_text(value):
            blockers.append(f"repository review proof has no {label}")
    if len(proof.source_state) != 3 or any(not _nonempty_text(value) for value in proof.source_state):
        blockers.append("repository review proof must name three source fingerprints")
    for actual, expected, label in (
        (proof.plan_digest, expectation.plan_digest, "plan digest"),
        (proof.source_state, expectation.source_state, "source state"),
        (proof.required_review_requirement_ids, expectation.required_review_requirement_ids, "required review requirement IDs"),
        (proof.exact_reused_review_evidence, expectation.exact_reused_review_evidence, "exact reused review evidence"),
        (proof.required_validation_requirement_ids, expectation.required_validation_requirement_ids, "required validation requirement IDs"),
    ):
        if actual != expected:
            blockers.append(f"repository review proof {label} do not match the planner-derived expectation")
    blockers.extend(_identifier_tuple_blockers(proof.stale_evidence_ids, label="stale evidence IDs"))
    blockers.extend(_identifier_tuple_blockers(proof.unresolved_handoff_ids, label="unresolved handoff IDs"))
    blockers.extend(_planned_node_mapping_blockers(expectation, proof))
    reused_requirement_ids = {requirement_id for requirement_id, _ in expectation.exact_reused_review_evidence}
    proof_reuse_mapping = tuple(
        sorted((requirement_id, evidence_id) for requirement_id, evidence_id in proof.review_requirement_evidence if requirement_id in reused_requirement_ids)
    )
    if proof_reuse_mapping != expectation.exact_reused_review_evidence:
        blockers.append("repository review proof substitutes routed exact-reuse evidence IDs")
    blockers.extend(
        _proof_mapping_blockers(
            label="review",
            required_ids=proof.required_review_requirement_ids,
            mapping=proof.review_requirement_evidence,
            accepted_evidence_ids=proof.accepted_review_evidence_ids,
            stale_evidence_ids=proof.stale_evidence_ids,
        )
    )
    blockers.extend(
        _proof_mapping_blockers(
            label="validation",
            required_ids=proof.required_validation_requirement_ids,
            mapping=proof.validation_requirement_evidence,
            accepted_evidence_ids=proof.accepted_validation_evidence_ids,
            stale_evidence_ids=proof.stale_evidence_ids,
        )
    )
    if proof.final_synthesis_evidence_id not in set(proof.accepted_review_evidence_ids):
        blockers.append("final synthesis evidence is not accepted review evidence")
    if proof.final_synthesis_evidence_id in set(proof.stale_evidence_ids):
        blockers.append("final synthesis evidence is stale")
    if proof.unresolved_handoff_ids:
        blockers.append("repository review proof has unresolved routing handoffs: " + ", ".join(proof.unresolved_handoff_ids))
    return Assessment(not blockers, tuple(blockers))


def _review_bundle_blockers(  # noqa: C901, PLR0912
    proof_expectation: RepositoryReviewProofExpectation, proof: RepositoryReviewProof, records: Sequence[tuple[ReviewEvidenceExpectation, ReviewEvidence]]
) -> tuple[tuple[str, ...], dict[str, tuple[ReviewEvidenceExpectation, ReviewEvidence]]]:
    blockers = list(_identifier_tuple_blockers(tuple(evidence.evidence_id for _, evidence in records), label="review bundle evidence IDs"))
    by_id = {evidence.evidence_id: (expectation, evidence) for expectation, evidence in records}
    accepted_handoff_ids = tuple(
        handoff_id for evidence_id in proof.accepted_review_evidence_ids if evidence_id in by_id for handoff_id in by_id[evidence_id][1].handoff_ids
    )
    if _duplicate_values(accepted_handoff_ids):
        blockers.append("accepted review evidence handoff IDs must be globally unique")
    if proof.unresolved_handoff_ids != accepted_handoff_ids:
        blockers.append("repository review proof unresolved handoffs do not equal accepted review evidence handoffs")
    extra_ids = sorted(set(by_id) - set(proof.accepted_review_evidence_ids))
    if extra_ids:
        blockers.append("review bundle contains evidence not accepted by the proof: " + ", ".join(extra_ids))
    for evidence_id in proof.accepted_review_evidence_ids:
        record = by_id.get(evidence_id)
        if record is None:
            blockers.append(f"accepted review evidence is missing from the bundle: {evidence_id}")
            continue
        expectation, evidence = record
        assessment = assess_review_evidence(expectation, evidence)
        blockers.extend(f"{evidence_id}: {blocker}" for blocker in assessment.blockers)
        if not assessment.satisfies_requirements:
            blockers.append(f"accepted review evidence does not satisfy its requirements: {evidence_id}")
        if expectation.source_state != proof.source_state:
            blockers.append(f"accepted review evidence has a different source state: {evidence_id}")
    synthesis_record = by_id.get(proof.final_synthesis_evidence_id)
    if synthesis_record is not None:
        expectation, evidence = synthesis_record
        for owner, identity in (("expectation", expectation), ("envelope", evidence)):
            observed = (identity.node_id, identity.skill_id, identity.mode)
            if observed != proof_expectation.final_synthesis_identity:
                blockers.append(f"final synthesis evidence {owner} identity must be node/skill/mode {'/'.join(proof_expectation.final_synthesis_identity)}")
    for reuse in proof_expectation.reused_review_identities:
        record = by_id.get(reuse.evidence_id)
        if record is None:
            continue
        record_expectation, envelope = record
        expected_identity = (reuse.skill_id, reuse.skill_path, reuse.skill_digest, reuse.reference_digests, reuse.mode)
        for owner, identity in (("expectation", record_expectation), ("envelope", envelope)):
            observed = (identity.skill_id, identity.skill_path, identity.skill_digest, identity.reference_digests, identity.mode)
            if observed != expected_identity:
                blockers.append(f"exactly reused review evidence {owner} identity does not match routed requirement {reuse.requirement_id}")
        if reuse.mode == "independent-review" and (
            record_expectation.change_target != reuse.change_target
            or record_expectation.planned_paths != reuse.planned_paths
            or record_expectation.planned_path_line_bounds != reuse.planned_path_line_bounds
        ):
            blockers.append(f"exactly reused independent-review evidence expectation provenance does not match routed requirement {reuse.requirement_id}")
    return tuple(blockers), by_id


def _validation_bundle_blockers(
    proof: RepositoryReviewProof, records: Sequence[tuple[ValidationEvidenceExpectation, ValidationEvidence]]
) -> tuple[tuple[str, ...], dict[str, tuple[ValidationEvidenceExpectation, ValidationEvidence]]]:
    blockers = list(_identifier_tuple_blockers(tuple(evidence.evidence_id for _, evidence in records), label="validation bundle evidence IDs"))
    by_id = {evidence.evidence_id: (expectation, evidence) for expectation, evidence in records}
    extra_ids = sorted(set(by_id) - set(proof.accepted_validation_evidence_ids))
    if extra_ids:
        blockers.append("validation bundle contains evidence not accepted by the proof: " + ", ".join(extra_ids))
    for evidence_id in proof.accepted_validation_evidence_ids:
        record = by_id.get(evidence_id)
        if record is None:
            blockers.append(f"accepted validation evidence is missing from the bundle: {evidence_id}")
            continue
        expectation, evidence = record
        assessment = assess_validation_evidence(expectation, evidence)
        blockers.extend(f"{evidence_id}: {blocker}" for blocker in assessment.blockers)
        if not assessment.satisfies_requirements:
            blockers.append(f"accepted validation evidence does not satisfy its requirements: {evidence_id}")
        if expectation.source_state != proof.source_state:
            blockers.append(f"accepted validation evidence has a different source state: {evidence_id}")
    return tuple(blockers), by_id


def _mapping_ownership_blockers(*, label: str, mapping: Sequence[tuple[str, str]], records: Mapping[str, tuple[Any, Any]]) -> tuple[str, ...]:
    blockers: list[str] = []
    for requirement_id, evidence_id in mapping:
        record = records.get(evidence_id)
        if record is None:
            continue
        expectation, evidence = record
        if requirement_id not in expectation.requirement_ids:
            blockers.append(f"{label} proof requirement is not owned by its evidence expectation: {requirement_id} -> {evidence_id}")
        if requirement_id not in evidence.requirement_ids:
            blockers.append(f"{label} proof requirement is not owned by its evidence envelope: {requirement_id} -> {evidence_id}")
    return tuple(blockers)


def _planned_mapping_blockers(
    *,
    label: str,
    proof_mapping: Sequence[tuple[str, str]],
    planned_mapping: Sequence[tuple[str, str]],
    planned_node_evidence: Sequence[tuple[str, str]],
    records: Mapping[str, tuple[Any, Any]],
) -> tuple[str, ...]:
    blockers: list[str] = []
    planned_nodes = dict(planned_mapping)
    evidence_by_node = dict(planned_node_evidence)
    for requirement_id, evidence_id in proof_mapping:
        expected_node_id = planned_nodes.get(requirement_id)
        record = records.get(evidence_id)
        if expected_node_id is not None and evidence_by_node.get(expected_node_id) != evidence_id:
            blockers.append(
                f"{label} proof requirement evidence does not match its planned-node evidence mapping: "
                f"{requirement_id} -> {evidence_id}, expected {evidence_by_node.get(expected_node_id)}"
            )
        if expected_node_id is not None and record is not None and record[0].node_id != expected_node_id:
            blockers.append(
                f"{label} proof requirement evidence does not match its planner-derived node: "
                f"{requirement_id} -> {record[0].node_id}, expected {expected_node_id}"
            )
    return tuple(blockers)


def _planned_node_bundle_blockers(  # noqa: C901, PLR0912, PLR0915
    expectation: RepositoryReviewProofExpectation,
    proof: RepositoryReviewProof,
    review_records: Mapping[str, tuple[ReviewEvidenceExpectation, ReviewEvidence]],
    validation_records: Mapping[str, tuple[ValidationEvidenceExpectation, ValidationEvidence]],
) -> tuple[str, ...]:
    """Bind every mapped artifact envelope to its exact planned node identity."""
    blockers: list[str] = []
    planned = {node.node_id: node for node in expectation.planned_evidence_nodes}
    evidence_by_node = dict(proof.planned_node_evidence)
    accepted = set(proof.accepted_review_evidence_ids) | set(proof.accepted_validation_evidence_ids)
    for node_id, evidence_id in proof.planned_node_evidence:
        node = planned.get(node_id)
        if node is None:
            continue
        if node.mode == "validation":
            record = validation_records.get(evidence_id)
            if record is None:
                blockers.append(f"planned validation node has no validation evidence record: {node_id}")
                continue
            record_expectation, envelope = record
            expectation_identity = (
                record_expectation.node_id,
                record_expectation.skill_path,
                record_expectation.skill_digest,
                record_expectation.reference_digests,
                _sha256_json(asdict(record_expectation.validation_unit)),
            )
            planned_identity = (node.node_id, node.skill_path, node.skill_digest, node.reference_digests, node.validation_unit_digest)
            envelope_identity = (envelope.node_id, envelope.skill_digest, envelope.reference_digests)
            planned_envelope_identity = (node.node_id, node.skill_digest, node.reference_digests)
            if expectation_identity != planned_identity:
                blockers.append(f"planned validation evidence identity does not match node {node_id}")
            if envelope_identity != planned_envelope_identity:
                blockers.append(f"planned validation evidence envelope provenance does not match node {node_id}")
        else:
            record = review_records.get(evidence_id)
            if record is None:
                blockers.append(f"planned {node.mode} node has no review evidence record: {node_id}")
                continue
            record_expectation, envelope = record
            planned_identity = (node.node_id, node.skill_id, node.skill_path, node.skill_digest, node.reference_digests, node.mode)
            expectation_identity = (
                record_expectation.node_id,
                record_expectation.skill_id,
                record_expectation.skill_path,
                record_expectation.skill_digest,
                record_expectation.reference_digests,
                record_expectation.mode,
            )
            envelope_identity = (envelope.node_id, envelope.skill_id, envelope.skill_path, envelope.skill_digest, envelope.reference_digests, envelope.mode)
            if expectation_identity != planned_identity:
                blockers.append(f"review evidence expectation identity does not match planned node {node_id}")
            if envelope_identity != planned_identity:
                blockers.append(f"review evidence envelope identity does not match planned node {node_id}")
            if node.mode in {"fix", "independent-review"} and (
                record_expectation.change_target != node.change_target
                or record_expectation.planned_paths != node.planned_paths
                or record_expectation.planned_path_line_bounds != node.planned_path_line_bounds
            ):
                blockers.append(f"{node.mode} evidence provenance does not match planned node {node_id}")
    for node in expectation.planned_evidence_nodes:
        if node.mode != "synthesis":
            continue
        synthesis_evidence_id = evidence_by_node.get(node.node_id)
        if synthesis_evidence_id not in accepted:
            continue
        missing_predecessors = tuple(predecessor for predecessor in node.predecessors if evidence_by_node.get(predecessor) not in accepted)
        if missing_predecessors:
            blockers.append(f"synthesis node {node.node_id} lacks accepted mapped predecessor evidence: " + ", ".join(missing_predecessors))
        record = review_records.get(synthesis_evidence_id)
        if record is None:
            continue
        expected_predecessor_evidence = tuple(
            dict.fromkeys(
                (
                    *(evidence_by_node[predecessor] for predecessor in node.predecessors if predecessor in evidence_by_node),
                    *(
                        (evidence_id for _, evidence_id in expectation.exact_reused_review_evidence)
                        if node.node_id == expectation.final_synthesis_identity[0]
                        else ()
                    ),
                )
            )
        )
        record_expectation, envelope = record
        if record_expectation.predecessor_evidence_ids != expected_predecessor_evidence:
            blockers.append(f"synthesis expectation predecessor evidence does not match planner mappings: {node.node_id}")
        if envelope.predecessor_evidence_ids != expected_predecessor_evidence:
            blockers.append(f"synthesis evidence predecessor coverage does not match planner mappings: {node.node_id}")
    return tuple(blockers)


def _artifact_manifest_blockers(  # noqa: C901, PLR0912, PLR0915
    proof: RepositoryReviewProof,
    manifest: ArtifactManifest | None,
    trusted_verifier: TrustedArtifactVerifier | None,
    review_records: Mapping[str, tuple[ReviewEvidenceExpectation, ReviewEvidence]],
    validation_records: Mapping[str, tuple[ValidationEvidenceExpectation, ValidationEvidence]],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not isinstance(trusted_verifier, TrustedArtifactVerifier):
        blockers.append("artifact verification requires a typed trusted verifier")
        return tuple(blockers)
    if trusted_verifier.digest_algorithm != "sha256":
        blockers.append(f"artifact verifier uses an unsupported digest algorithm: {trusted_verifier.digest_algorithm}")
    if proof.verifier_id != trusted_verifier.verifier_id:
        blockers.append(f"repository review proof names an unknown verifier: {proof.verifier_id}")
    if any(not isinstance(artifact, ArtifactPayload) for artifact in trusted_verifier.artifacts):
        blockers.append("artifact verifier contains an untyped payload")
        return tuple(blockers)
    verifier_artifact_ids = tuple(artifact.artifact_id for artifact in trusted_verifier.artifacts)
    blockers.extend(_identifier_tuple_blockers(verifier_artifact_ids, label="artifact verifier artifact IDs"))
    if any(not isinstance(artifact.content, bytes) for artifact in trusted_verifier.artifacts):
        blockers.append("artifact verifier payload content must be bytes")
        return tuple(blockers)
    verifier_artifacts = {artifact.artifact_id: artifact.content for artifact in trusted_verifier.artifacts}
    if not isinstance(manifest, ArtifactManifest):
        blockers.append("artifact verification requires a typed manifest")
        return tuple(blockers)
    if not isinstance(manifest.schema_version, int) or isinstance(manifest.schema_version, bool) or manifest.schema_version != EVIDENCE_SCHEMA_VERSION:
        blockers.append(f"artifact manifest schema must be exactly {EVIDENCE_SCHEMA_VERSION}")
    if manifest.manifest_id != proof.artifact_manifest_id:
        blockers.append("artifact manifest ID does not match the repository review proof")
    if manifest.verifier_id != trusted_verifier.verifier_id:
        blockers.append("artifact manifest verifier does not match the trusted verifier")
    if any(not _nonempty_text(value) for value in (manifest.manifest_id, manifest.verifier_id, manifest.manifest_digest)):
        blockers.append("artifact manifest identity and digest must be non-empty strings")
    if any(not isinstance(entry, ArtifactManifestEntry) for entry in manifest.entries):
        blockers.append("artifact manifest contains an untyped entry")
        return tuple(blockers)

    evidence_ids = tuple(entry.evidence_id for entry in manifest.entries)
    artifact_ids = tuple(entry.artifact_id for entry in manifest.entries)
    blockers.extend(_identifier_tuple_blockers(evidence_ids, label="artifact manifest evidence IDs"))
    blockers.extend(_identifier_tuple_blockers(artifact_ids, label="artifact manifest artifact IDs"))
    accepted_ids = set(proof.accepted_review_evidence_ids) | set(proof.accepted_validation_evidence_ids)
    if set(evidence_ids) != accepted_ids:
        missing = sorted(accepted_ids - set(evidence_ids))
        extra = sorted(set(evidence_ids) - accepted_ids)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        blockers.append("artifact manifest does not cover accepted evidence exactly: " + "; ".join(detail))
    if set(artifact_ids) != set(verifier_artifacts):
        blockers.append("artifact manifest does not cover trusted verifier artifacts exactly")

    for entry in manifest.entries:
        if any(not _nonempty_text(value) for value in (entry.evidence_id, entry.artifact_id, entry.artifact_digest, entry.entry_digest)):
            blockers.append(f"artifact manifest entry fields must be non-empty strings: {entry.evidence_id!r}")
            continue
        expected_entry_digest = _manifest_entry_digest(evidence_id=entry.evidence_id, artifact_id=entry.artifact_id, artifact_digest=entry.artifact_digest)
        if entry.entry_digest != expected_entry_digest:
            blockers.append(f"artifact manifest entry digest does not verify: {entry.evidence_id}")
        content = verifier_artifacts.get(entry.artifact_id)
        if content is not None and entry.artifact_digest != _sha256_bytes(content):
            blockers.append(f"artifact manifest artifact digest does not verify: {entry.evidence_id}")
        review_record = review_records.get(entry.evidence_id)
        validation_record = validation_records.get(entry.evidence_id)
        record = review_record or validation_record
        if record is not None:
            evidence = record[1]
            if (entry.artifact_id, entry.artifact_digest) != (evidence.raw_result_artifact_id, evidence.raw_result_digest):
                blockers.append(f"artifact manifest entry does not match its evidence envelope: {entry.evidence_id}")
        if content is not None and review_record is not None:
            expectation, evidence = review_record
            blockers.extend(f"{entry.evidence_id}: {blocker}" for blocker in _review_native_result_blockers(content, expectation, evidence))
        if content is not None and validation_record is not None:
            expectation, evidence = validation_record
            blockers.extend(f"{entry.evidence_id}: {blocker}" for blocker in _validation_native_result_blockers(content, expectation, evidence))

    recomputed_manifest_digest = _manifest_digest(manifest)
    if manifest.manifest_digest != recomputed_manifest_digest:
        blockers.append("artifact manifest digest does not verify")
    if proof.artifact_manifest_digest != recomputed_manifest_digest:
        blockers.append("repository review proof artifact manifest digest does not verify")
    return tuple(blockers)


def assess_evidence_bundle(  # noqa: PLR0913
    expectation: RepositoryReviewProofExpectation,
    proof: RepositoryReviewProof,
    *,
    review_records: Sequence[tuple[ReviewEvidenceExpectation, ReviewEvidence]],
    validation_records: Sequence[tuple[ValidationEvidenceExpectation, ValidationEvidence]],
    artifact_manifest: ArtifactManifest | None = None,
    trusted_verifier: TrustedArtifactVerifier | None = None,
) -> EvidenceBundleAssessment:
    """Verify every evidence object trusted by one repository review proof."""
    blockers = list(assess_repository_review_proof(expectation, proof).blockers)
    review_blockers, review_ids = _review_bundle_blockers(expectation, proof, review_records)
    validation_blockers, validation_ids = _validation_bundle_blockers(proof, validation_records)
    blockers.extend(review_blockers)
    blockers.extend(validation_blockers)
    blockers.extend(_mapping_ownership_blockers(label="review", mapping=proof.review_requirement_evidence, records=review_ids))
    blockers.extend(_mapping_ownership_blockers(label="validation", mapping=proof.validation_requirement_evidence, records=validation_ids))
    blockers.extend(
        _planned_mapping_blockers(
            label="review",
            proof_mapping=proof.review_requirement_evidence,
            planned_mapping=expectation.review_requirement_nodes,
            planned_node_evidence=proof.planned_node_evidence,
            records=review_ids,
        )
    )
    blockers.extend(
        _planned_mapping_blockers(
            label="validation",
            proof_mapping=proof.validation_requirement_evidence,
            planned_mapping=expectation.validation_requirement_nodes,
            planned_node_evidence=proof.planned_node_evidence,
            records=validation_ids,
        )
    )
    blockers.extend(_planned_node_bundle_blockers(expectation, proof, review_ids, validation_ids))
    blockers.extend(_artifact_manifest_blockers(proof, artifact_manifest, trusted_verifier, review_ids, validation_ids))
    overlapping_ids = sorted(set(review_ids) & set(validation_ids))
    if overlapping_ids:
        blockers.append("review and validation evidence IDs overlap: " + ", ".join(overlapping_ids))
    return EvidenceBundleAssessment(
        feasible=not blockers, blockers=tuple(blockers), proof_id=proof.proof_id, plan_digest=expectation.plan_digest, source_state=expectation.source_state
    )


def stop_after_worker_creation_failure(failure: CreationFailure) -> ResumeManifest:
    """Halt dispatch and account for all work requiring a fresh worker."""
    _validate_unique_ids((node.node_id for node in failure.planned_nodes), label="planned node")
    _validate_unique_ids(failure.accepted_node_ids, label="accepted node")
    _validate_unique_ids(failure.unaccepted_node_ids, label="unaccepted node")
    by_id = {node.node_id: node for node in failure.planned_nodes}
    if failure.failed_node_id not in by_id:
        msg = "failed node must belong to the planned graph"
        raise ValueError(msg)
    accepted = set(failure.accepted_node_ids)
    unknown_accepted = sorted(accepted - set(by_id))
    if unknown_accepted:
        msg = "accepted nodes do not belong to the planned graph: " + ", ".join(unknown_accepted)
        raise ValueError(msg)
    unknown_unaccepted = sorted(set(failure.unaccepted_node_ids) - set(by_id))
    if unknown_unaccepted:
        msg = "unaccepted nodes do not belong to the planned graph: " + ", ".join(unknown_unaccepted)
        raise ValueError(msg)
    overlap = sorted(accepted & set(failure.unaccepted_node_ids))
    if overlap:
        msg = "accepted and unaccepted nodes must be disjoint: " + ", ".join(overlap)
        raise ValueError(msg)
    if failure.failed_node_id in accepted:
        msg = "failed node cannot be accepted"
        raise ValueError(msg)

    def resume_node(node: WorkerNode) -> ResumeNode:
        return ResumeNode(
            node_id=node.node_id,
            skill_id=node.skill_id,
            skill_path=node.skill_path,
            mode=node.mode,
            requirement_ids=node.requirement_ids,
            priority=node.priority,
            predecessors=node.predecessors,
            coverage=node.coverage,
            router_ids=node.router_ids,
            rule_ids=node.rule_ids,
            selection_reasons=node.selection_reasons,
            owners=node.owners,
            instruction_paths=node.instruction_paths,
            static_references=node.static_references,
        )

    remaining = tuple(resume_node(node) for node in failure.planned_nodes if node.node_id not in accepted)
    unaccepted_ids = set(failure.unaccepted_node_ids) | {failure.failed_node_id} | {node.node_id for node in remaining}
    return ResumeManifest(
        reason=f"worker creation failed for {failure.failed_node_id}; no later node was dispatched",
        source_state=failure.source_state,
        undispatched_nodes=remaining,
        unaccepted_nodes=tuple(resume_node(node) for node in failure.planned_nodes if node.node_id in unaccepted_ids),
        outstanding_validation_mappings=tuple(item for item in failure.validation_mappings if item.validation_unit_id in unaccepted_ids),
        accepted_nonexecution_catalog_ids=failure.accepted_nonexecution_catalog_ids,
        journal_location=failure.journal_location,
        dispatch_halted=True,
        fresh_root_task_may_be_required=True,
        complete_node_count=len(failure.planned_nodes),
        execution_epochs=failure.execution_epochs,
        current_epoch_ordinal=failure.current_epoch_ordinal,
        routing_catalog_closed=failure.routing_catalog_closed,
        unresolved_handoff_ids=failure.unresolved_handoff_ids,
        routing_revalidation_required=failure.routing_revalidation_required,
    )


def _missing_completion_evidence(required: Sequence[str], satisfied: Sequence[str], label: str) -> str | None:
    missing = sorted(set(required) - set(satisfied))
    return f"{label}: {', '.join(missing)}" if missing else None


def assess_completion(evidence: CompletionEvidence) -> Assessment:  # noqa: C901
    """Enforce the graph-completion gate."""
    blockers: list[str] = []
    expectation = evidence.repository_review_expectation
    proof = evidence.repository_review_proof
    bound = isinstance(expectation, RepositoryReviewProofExpectation) and isinstance(proof, RepositoryReviewProof)
    records_typed = (
        isinstance(evidence.review_records, tuple)
        and all(
            isinstance(record, tuple) and len(record) == 2 and isinstance(record[0], ReviewEvidenceExpectation) and isinstance(record[1], ReviewEvidence)
            for record in evidence.review_records
        )
        and isinstance(evidence.validation_records, tuple)
        and all(
            isinstance(record, tuple)
            and len(record) == 2
            and isinstance(record[0], ValidationEvidenceExpectation)
            and isinstance(record[1], ValidationEvidence)
            for record in evidence.validation_records
        )
    )
    bundle_verified = False
    if not bound:
        blockers.append("completion requires the exact typed repository proof expectation and proof")
    elif not records_typed:
        blockers.append("completion requires complete typed review and validation evidence records")
    else:
        verified_bundle = assess_evidence_bundle(
            expectation,
            proof,
            review_records=evidence.review_records,
            validation_records=evidence.validation_records,
            artifact_manifest=evidence.artifact_manifest,
            trusted_verifier=evidence.trusted_artifact_verifier,
        )
        blockers.extend(f"repository review evidence bundle: {blocker}" for blocker in verified_bundle.blockers)
        bundle_verified = verified_bundle.feasible and not verified_bundle.blockers

    if bound and bundle_verified:
        planned_nodes = expectation.planned_evidence_nodes
        evidence_by_node = dict(proof.planned_node_evidence)
        accepted_review = set(proof.accepted_review_evidence_ids)
        accepted_validation = set(proof.accepted_validation_evidence_ids)
        expected_required_reviews = expectation.required_review_requirement_ids
        mapped_review_requirements = {requirement_id for requirement_id, evidence_id in proof.review_requirement_evidence if evidence_id in accepted_review}
        expected_completed_reviews = tuple(sorted(set(expectation.plan.selected_review_requirements) & mapped_review_requirements))
        expected_reused_reviews = tuple(
            sorted(requirement_id for requirement_id, evidence_id in expectation.exact_reused_review_evidence if evidence_id in accepted_review)
        )
        required_node_ids = {node.node_id for node in expectation.plan.actual_worker_nodes if node.required}
        expected_validation_nodes = tuple(node.node_id for node in planned_nodes if node.mode == "validation" and node.node_id in required_node_ids)
        expected_accepted_validation = tuple(node_id for node_id in expected_validation_nodes if evidence_by_node.get(node_id) in accepted_validation)
        expected_synthesis_nodes = tuple(node.node_id for node in planned_nodes if node.mode == "synthesis")
        expected_accepted_synthesis = tuple(node_id for node_id in expected_synthesis_nodes if evidence_by_node.get(node_id) in accepted_review)
        independent_nodes = tuple(node.node_id for node in planned_nodes if node.mode == "independent-review")
        independent_reuse = tuple(item for item in expectation.reused_review_identities if item.mode == "independent-review")
        expected_independent_required = bool(independent_nodes or independent_reuse)
        expected_independent_accepted = (
            expected_independent_required
            and all(evidence_by_node.get(node_id) in accepted_review for node_id in independent_nodes)
            and all(item.evidence_id in accepted_review for item in independent_reuse)
        )
        expected_final_synthesized = evidence_by_node.get(expectation.final_synthesis_identity[0]) in accepted_review
        for actual, expected, label in (
            (evidence.required_requirement_ids, expected_required_reviews, "required review coverage"),
            (evidence.completed_requirement_ids, expected_completed_reviews, "completed review coverage"),
            (evidence.exact_reused_requirement_ids, expected_reused_reviews, "exact-reuse review coverage"),
            (evidence.required_validation_node_ids, expected_validation_nodes, "required validation coverage"),
            (evidence.accepted_validation_node_ids, expected_accepted_validation, "accepted validation coverage"),
            (evidence.required_synthesis_node_ids, expected_synthesis_nodes, "required synthesis coverage"),
            (evidence.accepted_synthesis_node_ids, expected_accepted_synthesis, "accepted synthesis coverage"),
            (evidence.independent_review_required, expected_independent_required, "independent-review requirement"),
            (evidence.independent_review_accepted, expected_independent_accepted, "independent-review acceptance"),
            (evidence.final_report_synthesized, expected_final_synthesized, "final synthesis status"),
        ):
            if actual != expected:
                blockers.append(f"caller-supplied {label} does not match the verified repository proof")

        completed_review_requirements = tuple(sorted(mapped_review_requirements))
        completed_validation_requirements = tuple(
            sorted(requirement_id for requirement_id, evidence_id in proof.validation_requirement_evidence if evidence_id in accepted_validation)
        )
        for required, satisfied, label in (
            (expected_required_reviews, completed_review_requirements, "required review requirements are incomplete"),
            (expectation.required_validation_requirement_ids, completed_validation_requirements, "required validation requirements are incomplete"),
            (expected_validation_nodes, expected_accepted_validation, "baseline or required validation is incomplete"),
            (expected_synthesis_nodes, expected_accepted_synthesis, "required production synthesis is incomplete"),
            (
                (*independent_nodes, *(item.requirement_id for item in independent_reuse)),
                (*independent_nodes, *(item.requirement_id for item in independent_reuse)) if expected_independent_accepted else (),
                "required independent repository review is incomplete",
            ),
        ):
            if (blocker := _missing_completion_evidence(required, satisfied, label)) is not None:
                blockers.append(blocker)

    documentation_blocker = _missing_completion_evidence(
        evidence.required_documentation_ids, evidence.completed_documentation_ids, "required documentation or citation coverage is incomplete"
    )
    if documentation_blocker is not None:
        blockers.append(documentation_blocker)
    valid_execution_profile = isinstance(evidence.execution_profile, str) and evidence.execution_profile in {"grouped", "isolated", "isolated-only", "mixed"}
    if not valid_execution_profile:
        blockers.append("final execution profile must be exactly grouped, isolated, isolated-only, or mixed")
    elif bound and evidence.execution_profile != expectation.plan.execution_profile:
        blockers.append("final execution profile does not match the bound graph plan")
    isolated_execution_profile = valid_execution_profile and evidence.execution_profile in {"isolated", "isolated-only"}
    blockers.extend(
        message
        for condition, message in (
            (bool(evidence.unaccepted_node_ids), "unaccepted nodes remain: " + ", ".join(evidence.unaccepted_node_ids)),
            (bool(evidence.undispatched_node_ids), "undispatched nodes remain: " + ", ".join(evidence.undispatched_node_ids)),
            (
                bool(evidence.meaningful_skip_requirement_ids),
                "applicable requirements cannot complete through meaningful skips: " + ", ".join(evidence.meaningful_skip_requirement_ids),
            ),
            (
                bool(evidence.completion_blocking_omission_ids),
                "completion-blocking routing dispositions remain: " + ", ".join(evidence.completion_blocking_omission_ids),
            ),
            (not evidence.routing_catalog_closed, "routing catalog is not exhaustively closed"),
            (bool(evidence.unresolved_handoff_ids), "late applicability handoffs remain unresolved: " + ", ".join(evidence.unresolved_handoff_ids)),
            (not evidence.routing_revalidated_after_changes, "routing was not revalidated after source-surface changes"),
            (not evidence.fingerprints_matched, "source-state fingerprints did not remain matched"),
            (isolated_execution_profile and bool(evidence.isolation_failures), "isolation failures occurred: " + ", ".join(evidence.isolation_failures)),
            (not evidence.final_report_synthesized, "final report was not synthesized"),
            (not evidence.findings_deduplicated, "final findings were not deduplicated"),
            (not bundle_verified, "repository review evidence bundle was not verified"),
        )
        if condition
    )
    return Assessment(not blockers, tuple(blockers))


def _migration_trial_blockers(trial: MigrationTrial) -> tuple[str, ...]:
    expected_skills = set(trial.expected_applicable_skill_ids)
    observed_skills = set(trial.observed_applicable_skill_ids)
    expected_findings = set(trial.expected_canonical_finding_ids)
    observed_findings = set(trial.observed_canonical_finding_ids)
    blockers: list[str] = []
    missing_skills = sorted(expected_skills - observed_skills)
    if missing_skills:
        blockers.append(f"{trial.trial_id} missed applicable skills: {', '.join(missing_skills)}")
    if trial.unexpected_skill_ids:
        blockers.append(f"{trial.trial_id} has unexplained extra skills: {', '.join(trial.unexpected_skill_ids)}")
    if not isinstance(trial.runtime_artifact_id, str) or not trial.runtime_artifact_id.strip():
        blockers.append(f"{trial.trial_id} has no runtime trial artifact")
    elif trial.runtime_artifact_verified is not True or not isinstance(trial.runtime_artifact_verifier, str) or not trial.runtime_artifact_verifier.strip():
        blockers.append(f"{trial.trial_id} runtime trial artifact was not independently verified")
    if not isinstance(trial.workers_created, int) or isinstance(trial.workers_created, bool):
        blockers.append(f"{trial.trial_id} has an invalid runtime worker count")
    elif trial.workers_created < 1:
        blockers.append(f"{trial.trial_id} created no runtime workers")
    missing_findings = sorted(expected_findings - observed_findings)
    if missing_findings:
        blockers.append(f"{trial.trial_id} missed canonical findings: {', '.join(missing_findings)}")
    for condition, label in (
        (trial.nodes_reconciled, "node lifecycle"),
        (trial.validation_complete, "validation"),
        (trial.synthesis_complete, "synthesis"),
        (trial.fingerprints_matched, "fingerprints"),
        (trial.report_complete, "report"),
        (trial.accepted, "accepted outcome"),
    ):
        if condition is not True:
            blockers.append(f"{trial.trial_id} failed {label}")
    return tuple(blockers)


def assess_migration_trials(trials: Sequence[MigrationTrial], *, required_consecutive: int = 3) -> Assessment:
    """Require verified forward parity before promoting isolated review."""
    if required_consecutive < 1:
        msg = "required consecutive migration trials must be positive"
        raise ValueError(msg)
    _validate_unique_ids((trial.trial_id for trial in trials), label="migration trial")
    required_modes = ("branch-read-only", "baseline-release", "review-and-fix")
    streaks = dict.fromkeys(required_modes, 0)
    active_failure_blockers: dict[str, tuple[str, ...]] = dict.fromkeys(required_modes, ())
    blockers: list[str] = []
    for trial in trials:
        trial_blockers = _migration_trial_blockers(trial)
        if trial.mode not in streaks:
            blockers.extend(trial_blockers)
            blockers.append(f"unknown migration trial mode: {trial.mode}")
            continue
        if trial_blockers:
            streaks[trial.mode] = 0
            active_failure_blockers[trial.mode] = trial_blockers
            continue
        streaks[trial.mode] += 1
        if streaks[trial.mode] >= required_consecutive:
            active_failure_blockers[trial.mode] = ()
    for mode, streak in streaks.items():
        if streak < required_consecutive:
            blockers.extend(active_failure_blockers[mode])
            blockers.append(f"{mode} has {streak} consecutive accepted trials; requires {required_consecutive}")
    if not any(
        not _migration_trial_blockers(trial)
        and trial.worker_creation_failure_forced is True
        and trial.recovery_completed is True
        and trial.grouped_fallback_completed is True
        for trial in trials
    ):
        blockers.append("no accepted forced worker-creation failure trial completed grouped fallback")
    if not any(not _migration_trial_blockers(trial) and trial.multi_epoch_completed is True for trial in trials):
        blockers.append("no accepted multi-epoch fresh-root continuation trial completed")
    return Assessment(not blockers, tuple(blockers))


def _context_paths(value: object, path: str = "$") -> tuple[str, ...]:
    """Return sensitive key paths without retaining or rendering their values."""
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.casefold().replace("-", "_") in _CONTEXT_KEYS:
                matches.append(child_path)
                continue
            matches.extend(_context_paths(item, child_path))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            matches.extend(_context_paths(item, f"{path}[{index}]"))
    return tuple(matches)


def _required_capacity_metadata_blocker(metadata: Mapping[str, Any]) -> str | None:
    """Validate the aggregate fields required to start one worker."""
    source = metadata.get("source")
    concurrent_limit = metadata.get("concurrent_worker_limit")
    active_workers = metadata.get("active_workers")
    if not isinstance(source, str) or not source.strip():
        return "capacity evidence source is unknown or invalid"
    if not isinstance(concurrent_limit, int) or isinstance(concurrent_limit, bool) or concurrent_limit < 1:
        return "concurrent-worker capacity is unknown or invalid"
    if not isinstance(active_workers, int) or isinstance(active_workers, bool) or active_workers < 0:
        return "active-worker count is unknown or invalid"
    if active_workers > concurrent_limit:
        return "active-worker count exceeds the concurrent-worker limit"
    return None


def _optional_lifetime_metadata_blocker(metadata: Mapping[str, Any]) -> str | None:
    """Validate lifetime metadata only when the runtime supplies it."""
    lifetime_fields = {"fresh_worker_creations_remaining", "lifecycle_semantics"}
    present = lifetime_fields & set(metadata)
    if present and present != lifetime_fields:
        return "optional lifetime-capacity evidence is incomplete"
    if not present:
        return None
    remaining = metadata["fresh_worker_creations_remaining"]
    lifecycle = metadata["lifecycle_semantics"]
    if not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 0:
        return "fresh total-worker creation capacity is invalid"
    if lifecycle not in {"bounded-total", "release-on-completion"}:
        return "worker lifecycle semantics are invalid"
    return None


def _capacity_metadata_blocker(metadata: Mapping[str, Any]) -> str | None:
    """Validate safe concurrency metadata and optional lifetime metadata."""
    exposed_context = _context_paths(metadata)
    if exposed_context:
        return "isolation-failure: capacity evidence exposed task context at " + ", ".join(exposed_context)
    unexpected = sorted(set(metadata) - _CAPACITY_FIELDS)
    if unexpected:
        return "capacity evidence contains unsupported fields: " + ", ".join(unexpected)
    missing = sorted(_REQUIRED_CAPACITY_FIELDS - set(metadata))
    if missing:
        return "capacity evidence is missing required fields: " + ", ".join(missing)
    return _required_capacity_metadata_blocker(metadata) or _optional_lifetime_metadata_blocker(metadata)


def _blocked_capacity(reason: str, *, required_fresh_worker_creations: int, required_peak_workers: int) -> CapacityAssessment:
    """Create one capacity blocker without leaking rejected metadata values."""
    return CapacityAssessment(
        feasible=False,
        blockers=(reason,),
        fresh_worker_creations_remaining=None,
        required_fresh_worker_creations=required_fresh_worker_creations,
        free_concurrent_slots=None,
        required_peak_workers=required_peak_workers,
        full_plan_creation_capacity_guaranteed=None,
    )


def assess_worker_capacity(metadata: Mapping[str, Any], *, required_fresh_worker_creations: int, required_peak_workers: int = 1) -> CapacityAssessment:
    """Require known lifetime capacity to cover the already-bounded plan."""
    if required_fresh_worker_creations < 0 or required_peak_workers < 1:
        msg = "worker requirements must be nonnegative with a positive peak"
        raise ValueError(msg)

    blocker = _capacity_metadata_blocker(metadata)
    if blocker is not None:
        return _blocked_capacity(blocker, required_fresh_worker_creations=required_fresh_worker_creations, required_peak_workers=required_peak_workers)

    raw_remaining = metadata.get("fresh_worker_creations_remaining")
    remaining = int(raw_remaining) if raw_remaining is not None else None
    concurrent_limit = int(metadata["concurrent_worker_limit"])
    active_workers = int(metadata["active_workers"])

    free_slots = max(0, concurrent_limit - active_workers)
    blockers: list[str] = []
    if required_fresh_worker_creations > 0 and remaining == 0:
        blockers.append("no fresh-worker creation capacity remains")
    elif remaining is not None and remaining < required_fresh_worker_creations:
        blockers.append(f"known fresh-worker capacity is smaller than the bounded plan: requires {required_fresh_worker_creations}, has {remaining}")
    if free_slots < required_peak_workers:
        blockers.append(f"insufficient concurrent-worker capacity: requires {required_peak_workers}, has {free_slots}")
    full_plan_guaranteed = None if remaining is None else remaining >= required_fresh_worker_creations
    return CapacityAssessment(
        not blockers, tuple(blockers), remaining, required_fresh_worker_creations, free_slots, required_peak_workers, full_plan_guaranteed
    )


def _malformed_execution_profile_assessment(
    *, isolated_requested: object, isolated_only: object, fresh_workers_supported: object, budget: WorkerBudget
) -> ExecutionProfileAssessment | None:
    """Return the fail-closed profile for malformed boundary values."""
    input_blockers = [
        f"{field} must be a boolean"
        for field, value in (("isolated_requested", isolated_requested), ("isolated_only", isolated_only), ("fresh_workers_supported", fresh_workers_supported))
        if not isinstance(value, bool)
    ]
    input_blockers.extend(
        f"{field} must be a non-boolean integer"
        for field, value in (("worker budget total", budget.total), ("worker budget recovery/finalization reserve", budget.recovery_finalization_reserve))
        if not isinstance(value, int) or isinstance(value, bool)
    )
    if not input_blockers:
        return None

    strict_isolated_only = isolated_only is True or not isinstance(isolated_only, bool)
    return ExecutionProfileAssessment(
        feasible=not strict_isolated_only,
        blockers=tuple(input_blockers),
        profile="blocked" if strict_isolated_only else "grouped",
        reason=(
            "malformed isolated-only execution inputs cannot be used safely"
            if strict_isolated_only
            else "malformed isolation preference inputs require grouped delivery"
        ),
        isolated_requested=isolated_requested is True or strict_isolated_only,
        isolated_only=strict_isolated_only,
        configured_worker_budget=(budget.total if isinstance(budget.total, int) and not isinstance(budget.total, bool) else None),
    )


def select_execution_profile(  # noqa: C901, PLR0912
    *,
    isolated_requested: bool = False,
    isolated_only: bool = False,
    fresh_workers_supported: bool = False,
    capacity_metadata: Mapping[str, Any] | None = None,
    budget: WorkerBudget | None = None,
) -> ExecutionProfileAssessment:
    """Choose useful grouped delivery unless strict isolation is both requested and feasible."""
    selected_budget = budget if budget is not None else WorkerBudget()
    malformed = _malformed_execution_profile_assessment(
        isolated_requested=isolated_requested, isolated_only=isolated_only, fresh_workers_supported=fresh_workers_supported, budget=selected_budget
    )
    if malformed is not None:
        return malformed

    if isolated_only:
        isolated_requested = True

    if not isolated_requested:
        return ExecutionProfileAssessment(
            feasible=True,
            blockers=(),
            profile="grouped",
            reason="adaptive grouped delivery is the default profile",
            isolated_requested=False,
            isolated_only=False,
            configured_worker_budget=selected_budget.total,
        )

    blockers: list[str] = []
    effective_budget: int | None = None
    if not fresh_workers_supported:
        blockers.append("fresh no-inherited-turn workers are unavailable")
    if selected_budget.total <= selected_budget.recovery_finalization_reserve or selected_budget.recovery_finalization_reserve < 1:
        blockers.append("configured fresh-worker budget must exceed a positive recovery/finalization reserve")
    if capacity_metadata is None:
        blockers.append("safe aggregate worker-capacity metadata is unavailable")
    else:
        metadata_blocker = _capacity_metadata_blocker(capacity_metadata)
        if metadata_blocker is not None:
            blockers.append(metadata_blocker)
        else:
            remaining = capacity_metadata.get("fresh_worker_creations_remaining")
            if remaining is None:
                blockers.append("authoritative lifetime fresh-worker capacity is unavailable")
            else:
                effective_budget = min(selected_budget.total, int(remaining))
                capacity = assess_worker_capacity(capacity_metadata, required_fresh_worker_creations=max(1, effective_budget))
                blockers.extend(capacity.blockers)
                if effective_budget <= selected_budget.recovery_finalization_reserve:
                    blockers.append("effective fresh-worker budget must exceed the recovery/finalization reserve")

    if not blockers:
        return ExecutionProfileAssessment(
            feasible=True,
            blockers=(),
            profile="isolated",
            reason="explicit isolation request passed the worker-capability gate",
            isolated_requested=True,
            isolated_only=isolated_only,
            configured_worker_budget=selected_budget.total,
            effective_worker_budget=effective_budget,
        )

    if isolated_only:
        return ExecutionProfileAssessment(
            feasible=False,
            blockers=tuple(blockers),
            profile="blocked",
            reason="isolated-only execution cannot start safely",
            isolated_requested=True,
            isolated_only=True,
            configured_worker_budget=selected_budget.total,
            effective_worker_budget=effective_budget,
        )

    return ExecutionProfileAssessment(
        feasible=True,
        blockers=tuple(blockers),
        profile="grouped",
        reason="isolated execution was requested but unavailable; using grouped delivery",
        isolated_requested=True,
        isolated_only=False,
        configured_worker_budget=selected_budget.total,
        effective_worker_budget=effective_budget,
    )


def _validate_nodes(nodes: Sequence[PlanNode]) -> dict[str, PlanNode]:
    by_id = {node.node_id: node for node in nodes}
    if len(by_id) != len(nodes):
        msg = "node IDs must be unique"
        raise ValueError(msg)
    for node in nodes:
        if node.elapsed_seconds < 0:
            msg = f"node {node.node_id} has a negative elapsed budget"
            raise ValueError(msg)
        missing = sorted(set(node.predecessors) - set(by_id))
        if missing:
            msg = f"node {node.node_id} has missing predecessors: {', '.join(missing)}"
            raise ValueError(msg)
    return by_id


def critical_path_seconds(nodes: Sequence[PlanNode], *, sequential: bool) -> int:
    """Return the bounded schedule length, rejecting dependency cycles."""
    by_id = _validate_nodes(nodes)
    if sequential:
        return sum(node.elapsed_seconds for node in nodes)

    visiting: set[str] = set()
    complete: dict[str, int] = {}

    def visit(node_id: str) -> int:
        if node_id in complete:
            return complete[node_id]
        if node_id in visiting:
            msg = f"dependency cycle includes {node_id}"
            raise ValueError(msg)
        visiting.add(node_id)
        node = by_id[node_id]
        predecessor_cost = max((visit(item) for item in node.predecessors), default=0)
        visiting.remove(node_id)
        complete[node_id] = predecessor_cost + node.elapsed_seconds
        return complete[node_id]

    return max((visit(node.node_id) for node in nodes), default=0)


def assess_time_budget(nodes: Sequence[PlanNode], budget: TimeBudget) -> BudgetAssessment:
    """Report worst-case deadline risk while allowing incremental dispatch."""
    values = (budget.coordinator_reserve_seconds, budget.validation_reserve_seconds, budget.fix_revalidation_reserve_seconds)
    if min(values) < 0 or (budget.overall_seconds is not None and budget.overall_seconds < 0):
        msg = "time budgets and reserves must be nonnegative"
        raise ValueError(msg)
    critical_path = critical_path_seconds(nodes, sequential=budget.sequential)
    reserves = sum(values)
    required = critical_path + reserves
    if budget.overall_seconds is None:
        dispatch_window = None
        completion_guaranteed = None
        blockers: tuple[str, ...] = ()
        policy = "per-node-caps-only"
    else:
        dispatch_window = max(0, budget.overall_seconds - reserves)
        completion_guaranteed = required <= budget.overall_seconds
        blockers = ("global deadline leaves no time for worker dispatch after required reserves",) if nodes and dispatch_window == 0 else ()
        policy = "run-until-deadline-account-for-unrun"
    return BudgetAssessment(
        not blockers,
        blockers,
        critical_path,
        budget.coordinator_reserve_seconds,
        budget.validation_reserve_seconds,
        budget.fix_revalidation_reserve_seconds,
        required,
        budget.overall_seconds,
        dispatch_window,
        completion_guaranteed,
        policy,
    )


def bounded_node_dispatch_seconds(*, node_cap_seconds: int, elapsed_seconds: int, budget: TimeBudget) -> int:
    """Return the node timeout allowed by the remaining hard deadline."""
    if node_cap_seconds < 0 or elapsed_seconds < 0:
        msg = "node cap and elapsed time must be nonnegative"
        raise ValueError(msg)
    if budget.overall_seconds is None:
        return node_cap_seconds
    reserves = budget.coordinator_reserve_seconds + budget.validation_reserve_seconds + budget.fix_revalidation_reserve_seconds
    remaining = max(0, budget.overall_seconds - elapsed_seconds - reserves)
    return min(node_cap_seconds, remaining)


def python_packaging_signals(pyproject_text: str) -> tuple[str, ...]:
    """Detect only the packaging signals needed by the graph-side routing guard."""
    document = tomllib.loads(pyproject_text)
    project = document.get("project", {})
    tool = document.get("tool", {})
    setuptools = tool.get("setuptools", {})
    uv = tool.get("uv", {})
    signals: list[str] = []
    if document.get("build-system"):
        signals.append("build-system")
    if project.get("scripts"):
        signals.append("project.scripts")
    if project.get("gui-scripts"):
        signals.append("project.gui-scripts")
    if project.get("entry-points"):
        signals.append("project.entry-points")
    if setuptools.get("package-dir"):
        signals.append("tool.setuptools.package-dir")
    if setuptools.get("py-modules"):
        signals.append("tool.setuptools.py-modules")
    if setuptools.get("packages"):
        signals.append("tool.setuptools.packages")
    if uv.get("package") is True:
        signals.append("tool.uv.package")
    return tuple(signals)


def guard_packaged_python_routing(selected_skills: Iterable[str], pyproject_text: str) -> RoutingGuard:
    """Require build-portability without duplicating the Python routing matrix."""
    selected = list(dict.fromkeys(selected_skills))
    signals = python_packaging_signals(pyproject_text)
    required = bool(signals) and "python-build-portability" not in selected
    if required:
        selected.append("python-build-portability")
    return RoutingGuard(tuple(selected), signals, required)


def reconcile_execution(ledger: ExecutionLedger) -> Assessment:
    """Reconcile node, executor, skill, and validator lifecycle sets."""
    selected = set(ledger.selected_nodes)
    accepted = set(ledger.accepted_nodes)
    blocked_after = set(ledger.blocked_after_execution)
    blocked_before = set(ledger.blocked_before_execution)
    invalidated = set(ledger.invalidated_nodes)
    attempts = set(ledger.worker_attempts)
    created = set(ledger.workers_created)
    creation_failures = set(ledger.worker_creation_failures)
    coordinator_executions = set(ledger.coordinator_executions)
    executors = created | coordinator_executions
    executed_skills = set(ledger.skills_executed)
    validator_plan = set(ledger.planned_validators)
    validator_runs = set(ledger.executed_validators)
    validator_skips = set(ledger.validators_not_run)
    outcomes = accepted | blocked_after | blocked_before | invalidated
    outcome_sets = (accepted, blocked_after, blocked_before, invalidated)
    checks = (
        (selected != outcomes, "selected nodes do not reconcile with accepted, blocked, and invalidated lifecycle outcomes"),
        (any(left & right for index, left in enumerate(outcome_sets) for right in outcome_sets[index + 1 :]), "node lifecycle outcome sets overlap"),
        (bool(attempts != created | creation_failures or created & creation_failures), "worker creation attempts do not reconcile"),
        (not created <= attempts, "created-worker records lack a worker attempt"),
        (not coordinator_executions <= selected, "coordinator execution records are not selected graph nodes"),
        (not executed_skills <= executors, "executed-skill records lack a worker or coordinator execution"),
        (not (accepted | blocked_after | invalidated) <= executors, "executed node outcomes lack a worker or coordinator execution"),
        (
            not (accepted | invalidated) <= executed_skills or not executed_skills <= accepted | blocked_after | invalidated,
            "accepted, invalidated, and executed-skill records do not reconcile",
        ),
        (bool(blocked_before & executors), "pre-execution blocked nodes incorrectly claim an executor"),
        (bool(validator_plan != validator_runs | validator_skips or validator_runs & validator_skips), "planned validators do not reconcile"),
        (not validator_plan <= selected, "planned validators are not selected graph nodes"),
        (not validator_runs <= accepted | invalidated, "executed validators lack an accepted or invalidated node result"),
    )
    blockers = [message for failed, message in checks if failed]
    return Assessment(not blockers, tuple(blockers))


def _tuple_field(item: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = item.get(name, [])
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        msg = f"{name} must be a list of strings"
        raise ValueError(msg)
    return tuple(entry for entry in value if isinstance(entry, str))


def _bounded_text_field(item: Mapping[str, Any], name: str) -> str:
    value = item.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_NATIVE_IDENTIFIER_LENGTH:
        msg = f"{name} must be a bounded non-empty string"
        raise ValueError(msg)
    return value


def _optional_bounded_text_field(item: Mapping[str, Any], name: str) -> str | None:
    return None if item.get(name) is None else _bounded_text_field(item, name)


def _source_state_field(item: Mapping[str, Any]) -> tuple[str, str, str]:
    value = item.get("source_state")
    if not isinstance(value, list) or len(value) != 3:
        msg = "source_state must be exactly three bounded non-empty strings"
        raise ValueError(msg)
    scope, worktree, repository = value
    if not isinstance(scope, str) or not isinstance(worktree, str) or not isinstance(repository, str):
        msg = "source_state must be exactly three bounded non-empty strings"
        raise ValueError(msg)  # noqa: TRY004 - JSON schema violations use one public ValueError contract.
    if any(not entry.strip() or len(entry) > MAX_NATIVE_IDENTIFIER_LENGTH for entry in (scope, worktree, repository)):
        msg = "source_state must be exactly three bounded non-empty strings"
        raise ValueError(msg)
    return scope, worktree, repository


def _allowed_artifacts_field(item: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    value = item.get("allowed_artifacts", [])
    expected_keys = {"kind", "path", "repository_status"}
    if not isinstance(value, list) or any(not isinstance(entry, Mapping) or set(entry) != expected_keys for entry in value):
        msg = "allowed_artifacts must be a list of exact path/kind/repository_status objects"
        raise ValueError(msg)
    result: list[tuple[str, str, str]] = []
    for entry in value:
        path, kind, repository_status = entry["path"], entry["kind"], entry["repository_status"]
        if not all(isinstance(field, str) for field in (path, kind, repository_status)):
            msg = "allowed_artifacts fields must be strings"
            raise ValueError(msg)
        result.append((path, kind, repository_status))
    return tuple(result)


def _boolean_field(item: Mapping[str, Any], name: str, *, default: bool, label: str | None = None) -> bool:
    if name not in item:
        return default
    value = item[name]
    if not isinstance(value, bool):
        msg = f"{label or name} must be a boolean"
        raise ValueError(msg)  # noqa: TRY004 - JSON schema violations use one public ValueError contract.
    return value


def _normalize_repository_path(value: str, *, label: str) -> str:
    if not value.strip() or "\\" in value:
        msg = f"{label} must contain portable repository-relative paths"
        raise ValueError(msg)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        msg = f"{label} must contain portable repository-relative paths"
        raise ValueError(msg)
    normalized = str(path)
    if normalized in {"", "."}:
        msg = f"{label} must contain concrete repository paths"
        raise ValueError(msg)
    return normalized


def _normalized_repository_paths(values: Sequence[str], *, label: str) -> tuple[str, ...]:
    normalized = tuple(_normalize_repository_path(value, label=label) for value in values)
    if len(normalized) != len(set(normalized)):
        msg = f"{label} must not contain duplicate normalized paths"
        raise ValueError(msg)
    return normalized


def _captured_path_line_bounds_from_document(document: Mapping[str, Any], captured_paths: Sequence[str] | None) -> tuple[tuple[str, int], ...]:
    """Parse declared maximum addressable lines before independent verification."""
    raw_bounds = document.get("captured_path_line_bounds")
    if raw_bounds is None:
        return ()
    if captured_paths is None or not isinstance(raw_bounds, Mapping):
        msg = "captured_path_line_bounds requires captured_paths and a JSON object"
        raise ValueError(msg)
    normalized: dict[str, int] = {}
    for raw_path, raw_bound in raw_bounds.items():
        if not isinstance(raw_path, str):
            msg = "captured_path_line_bounds keys must be repository-relative path strings"
            raise ValueError(msg)  # noqa: TRY004 - JSON schema violations use one public ValueError contract.
        path = _normalize_repository_path(raw_path, label="captured_path_line_bounds")
        if path in normalized:
            msg = "captured_path_line_bounds must not contain duplicate normalized paths"
            raise ValueError(msg)
        if not isinstance(raw_bound, int) or isinstance(raw_bound, bool) or raw_bound < 0:
            msg = f"captured_path_line_bounds value for {path} must be a nonnegative integer"
            raise ValueError(msg)
        normalized[path] = raw_bound
    outside = tuple(sorted(set(normalized) - set(captured_paths)))
    if outside:
        msg = "captured_path_line_bounds contains paths outside captured_paths: " + ", ".join(outside)
        raise ValueError(msg)
    return tuple(sorted(normalized.items()))


def _capture_pathspecs_from_document(document: Mapping[str, Any]) -> tuple[str, ...]:
    raw_pathspecs = _tuple_field(document, "requested_paths")
    normalized = tuple("." if path == "." else _normalize_repository_path(path, label="requested_paths") for path in raw_pathspecs)
    if len(normalized) != len(set(normalized)):
        msg = "requested_paths must not contain duplicate normalized paths"
        raise ValueError(msg)
    return normalized


def _verified_captured_path_line_bounds(
    document: Mapping[str, Any], captured_paths: Sequence[str], repository_root: Path | None, declared_bounds: Sequence[tuple[str, int]]
) -> tuple[tuple[str, int], ...]:
    """Recapture exact source state and reject caller-authored line-bound claims."""
    if repository_root is None:
        msg = "independent-review line bounds require a trusted repository_root"
        raise ValueError(msg)
    git = shutil.which("git")
    if git is None:
        msg = "independent-review line-bound verification requires Git"
        raise ValueError(msg)
    capture_mode = document.get("capture_mode")
    if capture_mode not in {"branch", "staged", "worktree", "baseline"}:
        msg = "independent-review line-bound verification requires an exact capture_mode"
        raise ValueError(msg)
    base_ref = document.get("base_ref")
    if base_ref is not None and not isinstance(base_ref, str):
        msg = "base_ref must be a string or null"
        raise ValueError(msg)
    requested_paths = _capture_pathspecs_from_document(document)
    try:
        manifest = _scope_data(git, repository_root, capture_mode, base_ref, requested_paths)
    except RuntimeError as error:
        msg = f"could not independently verify captured source line bounds: {error}"
        raise ValueError(msg) from error
    expected_manifest = {
        "base_ref": base_ref,
        "capture_mode": capture_mode,
        "captured_scope_paths": list(captured_paths),
        "captured_worktree_fingerprint": document.get("captured_worktree_fingerprint"),
        "head": document.get("head"),
        "merge_base": document.get("merge_base"),
        "repository_root": str(repository_root),
        "repository_state_fingerprint": document.get("repository_state_fingerprint"),
        "requested_paths": list(requested_paths),
        "scope_fingerprint": document.get("scope_fingerprint"),
    }
    mismatches = tuple(field for field, expected in expected_manifest.items() if manifest.get(field) != expected)
    if mismatches:
        msg = "captured source manifest does not match independent recapture: " + ", ".join(mismatches)
        raise ValueError(msg)
    raw_derived = manifest.get("captured_path_line_bounds")
    if not isinstance(raw_derived, Mapping) or any(not isinstance(path, str) or not isinstance(bound, int) for path, bound in raw_derived.items()):
        msg = "trusted capture did not produce typed captured_path_line_bounds"
        raise ValueError(msg)
    derived = tuple(sorted((path, bound) for path, bound in raw_derived.items() if isinstance(path, str) and isinstance(bound, int)))
    if tuple(declared_bounds) != derived:
        msg = "captured_path_line_bounds do not match independently recaptured source bytes"
        raise ValueError(msg)
    return derived


def _constrain_routing_surfaces(
    catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision], *, captured_paths: Sequence[str]
) -> tuple[tuple[RoutingDecision, ...], tuple[str, ...]]:
    catalog_by_id = {entry.catalog_id: entry for entry in catalog}
    captured = set(captured_paths)
    normalized: list[RoutingDecision] = []
    blockers: list[str] = []
    for decision in decisions:
        entry = catalog_by_id.get(decision.catalog_id)
        review_surface = _normalized_repository_paths(decision.review_surface, label=f"{decision.catalog_id} review_surface")
        if entry is not None and entry.target_kind in {"leaf", "independent"} and decision.disposition in {"selected", "exact-evidence-reused"}:
            outside = tuple(sorted(set(review_surface) - captured))
            if outside:
                blockers.append(f"{decision.catalog_id} review_surface is outside captured_paths: {', '.join(outside)}")
        normalized.append(replace(decision, review_surface=review_surface))
    return tuple(normalized), tuple(blockers)


def _resolved_reference_tuple(item: Mapping[str, Any], name: str, skill_roots: Sequence[Path]) -> tuple[str, ...]:
    return tuple(str(_resolve_skill_root_path(path, skill_roots)) for path in _tuple_field(item, name))


def _validated_repository_root(repository_root: Path | None) -> Path | None:
    if repository_root is None:
        return None
    if not repository_root.is_absolute():
        msg = "repository_root must be an absolute path"
        raise ValueError(msg)
    resolved = repository_root.resolve()
    if not resolved.is_dir():
        msg = f"repository_root is missing or not a directory: {repository_root}"
        raise ValueError(msg)
    return resolved


def _resolve_repository_instruction_path(raw_path: str, repository_root: Path | None, skill_roots: Sequence[Path]) -> Path:
    roots = tuple(root.resolve() for root in skill_roots)
    if raw_path.startswith("$SKILLS_ROOT/"):
        return _resolve_skill_root_path(raw_path, roots)
    if not raw_path.strip() or "\\" in raw_path or ".." in PurePosixPath(raw_path).parts:
        msg = f"repository instruction path must not be empty or traverse directories: {raw_path}"
        raise ValueError(msg)
    if raw_path.startswith("$REPOSITORY_ROOT/"):
        if repository_root is None:
            msg = "repository instruction paths require repository_root"
            raise ValueError(msg)
        candidate = repository_root / raw_path.removeprefix("$REPOSITORY_ROOT/")
    else:
        path = Path(raw_path)
        if path.is_absolute():
            candidate = path
        elif repository_root is not None:
            candidate = repository_root / path
        else:
            return _resolve_skill_root_path(raw_path, roots)
    resolved = candidate.resolve()
    approved_roots = (*roots, repository_root) if repository_root is not None else roots
    if not resolved.is_file() or not _path_is_within(resolved, approved_roots):
        msg = f"repository instruction path is missing or outside repository and approved roots: {raw_path}"
        raise ValueError(msg)
    return resolved


def _resolved_instruction_tuple(item: Mapping[str, Any], name: str, repository_root: Path | None, skill_roots: Sequence[Path]) -> tuple[str, ...]:
    return tuple(str(_resolve_repository_instruction_path(path, repository_root, skill_roots)) for path in _tuple_field(item, name))


def _routing_decisions_from_document(document: Mapping[str, Any], repository_root: Path | None, skill_roots: Sequence[Path]) -> tuple[RoutingDecision, ...]:
    return tuple(
        RoutingDecision(
            catalog_id=str(item["catalog_id"]),
            requirement_id=str(item.get("requirement_id", item["catalog_id"])),
            router_id=str(item["router_id"]),
            rule_id=str(item["rule_id"]),
            skill_id=str(item["skill_id"]),
            skill_path=str(_resolve_checked_skill_path(str(item["skill_path"]), str(item["skill_id"]), skill_roots)),
            disposition=str(item["disposition"]),
            reason=str(item["reason"]),
            applicability_evidence=_tuple_field(item, "applicability_evidence"),
            review_surface=_tuple_field(item, "review_surface"),
            instruction_paths=_resolved_instruction_tuple(item, "instruction_paths", repository_root, skill_roots),
            static_references=_resolved_reference_tuple(item, "static_references", skill_roots),
            validation_requirement_ids=_tuple_field(item, "validation_requirement_ids"),
            synthesis_dependency=(str(item["synthesis_dependency"]) if item.get("synthesis_dependency") is not None else None),
            priority=(str(item["priority"]) if item.get("priority") is not None else None),
            owners=_tuple_field(item, "owners"),
            evidence_id=(str(item["evidence_id"]) if item.get("evidence_id") is not None else None),
        )
        for item in document.get("routing_decisions", [])
    )


def _routing_discoveries_from_document(document: Mapping[str, Any]) -> tuple[RoutingDiscovery, ...]:
    return tuple(
        RoutingDiscovery(
            handoff_id=str(item["handoff_id"]), source_node_id=str(item["source_node_id"]), catalog_id=str(item["catalog_id"]), evidence=str(item["evidence"])
        )
        for item in document.get("routing_discoveries", [])
    )


def plan_from_document(  # noqa: C901, PLR0912, PLR0915
    document: Mapping[str, Any],
    *,
    catalog_path: Path = DEFAULT_ROUTING_CATALOG,
    skill_roots: Sequence[Path] = (DEFAULT_SKILL_ROOT,),
    repository_root: Path | None = None,
) -> GraphPlan:
    """Build a graph plan from the exhaustive fixture/CLI JSON schema."""
    execution_profile = document.get("execution_profile", "grouped")
    if not isinstance(execution_profile, str) or execution_profile not in {"grouped", "isolated", "isolated-only", "mixed"}:
        msg = "execution_profile must be exactly grouped, isolated, isolated-only, or mixed"
        raise ValueError(msg)
    release_readiness = _boolean_field(document, "release_readiness", default=False)
    repository_root = _validated_repository_root(repository_root)
    exhaustive_routing = document.get("routing_decisions") is not None
    change_target: str | None = None
    captured_paths = (
        _normalized_repository_paths(_tuple_field(document, "captured_paths"), label="captured_paths") if document.get("captured_paths") is not None else None
    )
    captured_path_line_bounds = _captured_path_line_bounds_from_document(document, captured_paths)
    routing_assessment: RoutingLedgerAssessment | None = None
    routing_catalog: tuple[RoutingCatalogEntry, ...] = ()
    routing_decisions: tuple[RoutingDecision, ...] = ()
    if exhaustive_routing:
        routing_catalog = load_routing_catalog(catalog_path, skill_roots=skill_roots)
        routing_decisions = _routing_decisions_from_document(document, repository_root, skill_roots)
        if captured_paths is not None:
            routing_decisions, routing_surface_blockers = _constrain_routing_surfaces(routing_catalog, routing_decisions, captured_paths=captured_paths)
        else:
            routing_surface_blockers = ()
        consulted_routers = _tuple_field(document, "consulted_routers")
        routing_assessment = validate_routing_ledger(routing_catalog, routing_decisions, consulted_routers=consulted_routers)
        routing_metadata_blockers: list[str] = list(routing_surface_blockers)
        scope_mode = document.get("scope_mode")
        if scope_mode not in {"branch", "staged-only", "changed-file-only", "baseline", "release-readiness"}:
            routing_metadata_blockers.append("exhaustive routing requires a known scope_mode")
        concrete_change_target = document.get("concrete_change_target")
        if not isinstance(concrete_change_target, bool):
            routing_metadata_blockers.append("exhaustive routing requires concrete_change_target=true or false")
        raw_change_target = document.get("change_target")
        if concrete_change_target is True:
            if not isinstance(raw_change_target, str) or not raw_change_target.strip() or len(raw_change_target) > MAX_NATIVE_IDENTIFIER_LENGTH:
                msg = "a concrete independent review requires one bounded non-empty change_target"
                raise ValueError(msg)
            change_target = raw_change_target
        elif raw_change_target is not None:
            msg = "change_target is permitted only when concrete_change_target is true"
            raise ValueError(msg)
        independent_decision = next((item for item in routing_decisions if item.catalog_id == "repo.independent"), None)
        if independent_decision is not None and independent_decision.disposition in {"selected", "exact-evidence-reused"}:
            if captured_paths is None:
                msg = "independent-review line-bound verification requires captured_paths"
                raise ValueError(msg)
            captured_path_line_bounds = _verified_captured_path_line_bounds(document, captured_paths, repository_root, captured_path_line_bounds)
        if change_target is not None:
            line_bounds = dict(captured_path_line_bounds)
            routing_assessment = replace(
                routing_assessment,
                reused_review_identities=tuple(
                    replace(
                        item,
                        change_target=change_target,
                        planned_path_line_bounds=tuple((path, line_bounds[path]) for path in item.planned_paths if path in line_bounds),
                    )
                    if item.mode == "independent-review"
                    else item
                    for item in routing_assessment.reused_review_identities
                ),
            )
        routing_assessment = replace(
            routing_assessment, reused_review_identities=tuple(_bind_reused_review_provenance(item) for item in routing_assessment.reused_review_identities)
        )
        if concrete_change_target is True and (independent_decision is None or independent_decision.disposition not in {"selected", "exact-evidence-reused"}):
            routing_metadata_blockers.append("a concrete change target requires selected or exactly reused repository-independent-review")
        if concrete_change_target is False and independent_decision is not None and independent_decision.disposition in {"selected", "exact-evidence-reused"}:
            routing_metadata_blockers.append("a pure baseline without a concrete change must not select or reuse repository-independent-review")
        if independent_decision is not None and independent_decision.disposition in {"selected", "exact-evidence-reused"}:
            missing_line_bounds = tuple(sorted(set(independent_decision.review_surface) - set(dict(captured_path_line_bounds))))
            if missing_line_bounds:
                routing_metadata_blockers.append(
                    "repository-independent-review paths lack trusted captured_path_line_bounds: " + ", ".join(missing_line_bounds)
                )
        if captured_paths is not None:
            classifier = assess_repository_classifier_floor(
                routing_catalog, routing_decisions, classify_repository_paths(captured_paths, release_readiness=release_readiness)
            )
            if not classifier.feasible:
                routing_metadata_blockers.extend(classifier.blockers)
        else:
            routing_metadata_blockers.append("exhaustive routing requires captured_paths for classifier comparison")
        if routing_metadata_blockers:
            routing_assessment = replace(routing_assessment, feasible=False, blockers=(*routing_assessment.blockers, *routing_metadata_blockers))
        discovery_assessment = assess_routing_discoveries(routing_decisions, _routing_discoveries_from_document(document))
        if not discovery_assessment.feasible:
            routing_assessment = replace(routing_assessment, feasible=False, blockers=(*routing_assessment.blockers, *discovery_assessment.blockers))
        review_requirements = review_requirements_from_routing(routing_catalog, routing_decisions)
        routed_additional_nodes = independent_nodes_from_routing(routing_catalog, routing_decisions, change_target=change_target or "")
    else:
        allow_legacy_fixture = document.get("allow_legacy_fixture", False)
        if not isinstance(allow_legacy_fixture, bool):
            msg = "allow_legacy_fixture must be a boolean"
            raise ValueError(msg)
        if allow_legacy_fixture is not True:
            msg = "graph documents require exhaustive routing_decisions; legacy review_requirements are test-fixture-only"
            raise ValueError(msg)
        routed_additional_nodes = ()
        review_requirements = tuple(
            ReviewRequirement(
                requirement_id=str(item["requirement_id"]),
                skill_id=str(item["skill_id"]),
                skill_path=str(_resolve_checked_skill_path(str(item["skill_path"]), str(item["skill_id"]), skill_roots)),
                router_id=str(item.get("router_id", "legacy-fixture")),
                rule_id=str(item.get("rule_id", item["requirement_id"])),
                review_surface=_tuple_field(item, "review_surface"),
                reason=str(item["reason"]),
                priority=str(item["priority"]),
                synthesis_dependency=(str(item["synthesis_dependency"]) if item.get("synthesis_dependency") is not None else None),
                required=True,
                static_references=_resolved_reference_tuple(item, "static_references", skill_roots),
                instruction_paths=_resolved_instruction_tuple(item, "instruction_paths", repository_root, skill_roots),
                validation_requirement_ids=_tuple_field(item, "validation_requirement_ids"),
                owners=_tuple_field(item, "owners"),
            )
            for item in document.get("review_requirements", [])
        )
    validation_requirements = tuple(
        ValidationRequirement(
            requirement_id=_bounded_text_field(item, "requirement_id"),
            source_state=_source_state_field(item),
            commands=_tuple_field(item, "commands"),
            working_directories=_tuple_field(item, "working_directories"),
            environment=_bounded_text_field(item, "environment"),
            toolchain=_bounded_text_field(item, "toolchain"),
            features=_tuple_field(item, "features"),
            platform=_bounded_text_field(item, "platform"),
            artifact_owner=_bounded_text_field(item, "artifact_owner"),
            mutation_lock=_bounded_text_field(item, "mutation_lock"),
            request=_bounded_text_field(item, "request"),
            requested_scope=_bounded_text_field(item, "requested_scope"),
            capture_command=_bounded_text_field(item, "capture_command"),
            captured_paths=_tuple_field(item, "captured_paths"),
            authority=_bounded_text_field(item, "authority"),
            selection_reason=_bounded_text_field(item, "selection_reason"),
            mutation_classification=_bounded_text_field(item, "mutation_classification"),
            expected_evidence=_bounded_text_field(item, "expected_evidence"),
            elapsed_time_budget=_bounded_text_field(item, "elapsed_time_budget"),
            dependency_policy=_bounded_text_field(item, "dependency_policy"),
            meaningful_skips=_tuple_field(item, "meaningful_skips"),
            execution_strategy=_bounded_text_field(item, "execution_strategy"),
            independence_basis=_bounded_text_field(item, "independence_basis"),
            planning_blocker=_optional_bounded_text_field(item, "planning_blocker"),
            allowed_artifacts=_allowed_artifacts_field(item),
            canonical_recipe=_optional_bounded_text_field(item, "canonical_recipe"),
            evidence_id=_optional_bounded_text_field(item, "evidence_id"),
            required=_boolean_field(item, "required", default=True, label=f"validation requirement {item.get('requirement_id', '<unknown>')} required"),
            baseline=_boolean_field(item, "baseline", default=False, label=f"validation requirement {item.get('requirement_id', '<unknown>')} baseline"),
        )
        for item in document.get("validation_requirements", [])
    )
    synthesis_nodes = tuple(
        WorkerNode(
            node_id=str(item["node_id"]),
            skill_id=str(item["skill_id"]),
            skill_path=str(_resolve_checked_skill_path(str(item["skill_path"]), str(item["skill_id"]), skill_roots)),
            mode="synthesis",
            priority="required-routing-synthesis",
            required=True,
            requirement_ids=_tuple_field(item, "requirement_ids"),
            coverage=_tuple_field(item, "coverage"),
            predecessors=_tuple_field(item, "predecessors"),
            instruction_paths=_resolved_instruction_tuple(item, "instruction_paths", repository_root, skill_roots),
            static_references=_resolved_reference_tuple(item, "static_references", skill_roots),
        )
        for item in document.get("synthesis_nodes", [])
    )
    if routing_decisions:
        catalog_by_id = {entry.catalog_id: entry for entry in routing_catalog}
        selected_synthesis_skills = {
            decision.skill_id
            for decision in routing_decisions
            if decision.disposition == "selected" and catalog_by_id[decision.catalog_id].target_kind == "synthesis"
        }
        declared_synthesis_skills = {node.skill_id for node in synthesis_nodes}
        if selected_synthesis_skills != declared_synthesis_skills:
            missing = sorted(selected_synthesis_skills - declared_synthesis_skills)
            extra = sorted(declared_synthesis_skills - selected_synthesis_skills)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("unrouted " + ", ".join(extra))
            msg = "declared synthesis nodes do not match exhaustive routing: " + "; ".join(details)
            raise ValueError(msg)
    declared_additional_nodes: list[WorkerNode] = []
    for item in document.get("additional_nodes", []):
        node_id = str(item["node_id"])
        mode = str(item["mode"])
        coverage = _tuple_field(item, "coverage")
        if exhaustive_routing:
            if captured_paths is None:
                msg = f"additional node {node_id} coverage requires captured_paths"
                raise ValueError(msg)
            coverage = _normalized_repository_paths(coverage, label=f"additional node {node_id} coverage")
            outside = tuple(sorted(set(coverage) - set(captured_paths)))
            if outside:
                msg = f"additional node {node_id} coverage is outside captured_paths: {', '.join(outside)}"
                raise ValueError(msg)
        declared_additional_nodes.append(
            WorkerNode(
                node_id=node_id,
                skill_id=str(item["skill_id"]),
                skill_path=str(_resolve_checked_skill_path(str(item["skill_path"]), str(item["skill_id"]), skill_roots)),
                mode=mode,
                priority=str(item["priority"]),
                required=_boolean_field(item, "required", default=False, label=f"additional node {node_id} required"),
                requirement_ids=_tuple_field(item, "requirement_ids"),
                coverage=coverage,
                predecessors=_tuple_field(item, "predecessors"),
                synthesis_dependency=(str(item["synthesis_dependency"]) if item.get("synthesis_dependency") is not None else None),
                instruction_paths=_resolved_instruction_tuple(item, "instruction_paths", repository_root, skill_roots),
                static_references=_resolved_reference_tuple(item, "static_references", skill_roots),
                change_target=(str(item["change_target"]) if item.get("change_target") is not None else None),
            )
        )
    return plan_graph(
        review_requirements,
        validation_requirements,
        synthesis_nodes,
        additional_nodes=(*routed_additional_nodes, *declared_additional_nodes),
        routing_assessment=routing_assessment,
        execution_profile=execution_profile,
        budget=WorkerBudget(
            total=int(document.get("worker_budget", DEFAULT_TOTAL_FRESH_WORKER_BUDGET)),
            recovery_finalization_reserve=int(document.get("recovery_finalization_reserve", DEFAULT_RECOVERY_FINALIZATION_RESERVE)),
        ),
        validator_skill_path=str(_resolve_checked_skill_path("$SKILLS_ROOT/review-validator/SKILL.md", "review-validator", skill_roots)),
        captured_path_line_bounds=captured_path_line_bounds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one deterministic, read-only fixture-based planning dry run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON graph-planning fixture")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_ROUTING_CATALOG, help="machine-readable routing catalog")
    parser.add_argument("--skill-root", action="append", type=Path, help="approved skill root; repeat for multiple roots")
    parser.add_argument("--repository-root", type=Path, help="trusted repository root used to recapture independent-review source")
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            msg = "input root must be a JSON object"
            raise TypeError(msg)
        plan = plan_from_document(
            document, catalog_path=args.catalog, skill_roots=tuple(args.skill_root or (DEFAULT_SKILL_ROOT,)), repository_root=args.repository_root
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(f"review_graph_plan: {error}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    return 0 if plan.dispatch_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
