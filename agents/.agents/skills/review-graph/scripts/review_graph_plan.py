"""Deterministic planning checks for review-graph orchestration."""

import argparse
import fnmatch
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

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
class RoutingLedgerAssessment(Assessment):
    """Syntactic and semantic closure proof for all consulted routers."""

    selected_requirement_ids: tuple[str, ...]
    reused_requirement_ids: tuple[str, ...]
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


@dataclass(frozen=True)
class WorkerBudget:
    """Configured total fresh creations and protected reserve."""

    total: int = DEFAULT_TOTAL_FRESH_WORKER_BUDGET
    recovery_finalization_reserve: int = DEFAULT_RECOVERY_FINALIZATION_RESERVE


@dataclass(frozen=True)
class GraphPlan:
    """Complete required graph partitioned into bounded execution epochs."""

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
    routing_catalog_closed: bool
    consulted_routers: tuple[str, ...]
    exact_reused_requirement_ids: tuple[str, ...]
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
class NodeAcceptanceEvidence:
    """Isolation, skill, reference, structure, and fingerprint proof."""

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
    """Evidence required for a complete graph and repo-review migration gate."""

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
    isolation_failures: tuple[str, ...]
    final_report_synthesized: bool
    findings_deduplicated: bool
    exact_reused_requirement_ids: tuple[str, ...] = ()
    completion_blocking_omission_ids: tuple[str, ...] = ()
    routing_catalog_closed: bool = True
    unresolved_handoff_ids: tuple[str, ...] = ()
    routing_revalidated_after_changes: bool = True
    independent_review_required: bool = False
    independent_review_accepted: bool = False


@dataclass(frozen=True)
class MigrationTrial:
    """One chronological forward trial for the repo-review replacement gate."""

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
    worker_failure_forced: bool = False


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
    if decision.disposition == "exact-evidence-reused" and not decision.evidence_id:
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


def validate_routing_ledger(
    catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision], *, consulted_routers: Sequence[str]
) -> RoutingLedgerAssessment:
    """Require a total disposition ledger for every consulted routing catalog."""
    consulted = tuple(dict.fromkeys(consulted_routers))
    active_entries = {entry.catalog_id: entry for entry in catalog if entry.router_id in consulted}
    decision_ids = tuple(item.catalog_id for item in decisions)
    blockers: list[str] = []
    if "repo-review" not in consulted:
        blockers.append("routing ledger must consult repo-review before catalog closure")
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
    orphan_surface_routers = sorted(set(consulted) - {"repo-review"} - selected_router_ids)
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
    reused_requirement_ids = tuple(sorted(item.requirement_id for item in decisions if item.disposition == "exact-evidence-reused"))
    user_excluded = tuple(sorted(item.catalog_id for item in decisions if item.disposition == "user-excluded"))
    catalog_closed = not blockers
    return RoutingLedgerAssessment(
        feasible=not blockers,
        blockers=tuple(blockers),
        selected_requirement_ids=selected_requirement_ids,
        reused_requirement_ids=reused_requirement_ids,
        user_excluded_catalog_ids=user_excluded,
        completion_blocking_catalog_ids=blocking_catalog_ids,
        consulted_routers=consulted,
        catalog_closed=catalog_closed,
    )


def review_requirements_from_routing(catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision]) -> tuple[ReviewRequirement, ...]:
    """Convert selected leaf dispositions into required worker commitments."""
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


def independent_nodes_from_routing(catalog: Sequence[RoutingCatalogEntry], decisions: Sequence[RoutingDecision]) -> tuple[WorkerNode, ...]:
    """Create required independent-review nodes without treating them as audits."""
    entries = {entry.catalog_id: entry for entry in catalog}
    selected = sorted(
        (
            decision
            for decision in decisions
            if decision.disposition == "selected" and entries.get(decision.catalog_id) is not None and entries[decision.catalog_id].target_kind == "independent"
        ),
        key=lambda item: item.catalog_id,
    )
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
    repository_entry_by_surface = {entry.surface: entry for entry in catalog if entry.router_id == "repo-review" and entry.layer == "repository"}
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


def _validation_nodes(units: Sequence[ValidationUnit], *, skill_path: str) -> tuple[WorkerNode, ...]:
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
        )
        for unit in units
    )


def _synthesis_nodes(
    declared_nodes: Sequence[WorkerNode],
    audit_nodes: Sequence[WorkerNode],
    review_requirements: Sequence[ReviewRequirement],
    evidence_mapping: Sequence[ValidationEvidenceMapping],
    additional_nodes: Sequence[WorkerNode],
) -> tuple[WorkerNode, ...]:
    review_by_id = {item.requirement_id: item for item in review_requirements}
    validation_node_by_requirement = {item.requirement_id: item.validation_unit_id for item in evidence_mapping}
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
        result.append(
            replace(
                node,
                required=True,
                priority="required-routing-synthesis",
                predecessors=tuple(dict.fromkeys((*node.predecessors, *routed_audits, *routed_validators, *routed_additional))),
            )
        )
    return tuple(result)


def _additional_nodes(nodes: Sequence[WorkerNode]) -> tuple[WorkerNode, ...]:
    for node in nodes:
        if node.mode in {"audit", "validation", "synthesis"}:
            msg = f"additional node {node.node_id} must use independent-review, fix, or revalidation mode"
            raise ValueError(msg)
        _priority_rank(node.priority)
    return tuple(nodes)


def _validate_plan_edges(nodes: Sequence[WorkerNode]) -> None:
    _validate_unique_ids((node.node_id for node in nodes), label="worker node")
    node_ids = {node.node_id for node in nodes}
    missing = sorted({predecessor for node in nodes for predecessor in node.predecessors if predecessor not in node_ids})
    if missing:
        msg = "worker nodes reference missing predecessors: " + ", ".join(missing)
        raise ValueError(msg)


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


def plan_graph(  # noqa: PLR0913
    review_requirements: Sequence[ReviewRequirement],
    validation_requirements: Sequence[ValidationRequirement],
    synthesis_nodes: Sequence[WorkerNode],
    *,
    additional_nodes: Sequence[WorkerNode] = (),
    budget: WorkerBudget | None = None,
    routing_assessment: RoutingLedgerAssessment | None = None,
    validator_skill_path: str | None = None,
) -> GraphPlan:
    """Build the complete required graph and partition it into bounded epochs."""
    budget = budget or WorkerBudget()
    if budget.total < 1 or budget.recovery_finalization_reserve < 0:
        msg = "worker budget must be positive and recovery/finalization reserve nonnegative"
        raise ValueError(msg)
    if budget.recovery_finalization_reserve >= budget.total:
        msg = "recovery/finalization reserve must leave capacity for at least one worker"
        raise ValueError(msg)

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
    all_nodes = (
        *audit_nodes,
        *_validation_nodes(validation_units, skill_path=validator_skill_path or str((DEFAULT_SKILL_ROOT / "review-validator" / "SKILL.md").resolve())),
        *_additional_nodes(additional_nodes),
        *_synthesis_nodes(synthesis_nodes, audit_nodes, review_requirements, evidence_mapping, additional_nodes),
    )
    _validate_plan_edges(all_nodes)
    scheduled = _schedule_nodes(all_nodes)
    epochs = _partition_execution_epochs(scheduled, budget)
    current_epoch_ids = epochs[0].node_ids if epochs else ()
    selected_node_ids = {node.node_id for node in scheduled}
    selected_units = tuple(unit.node_id for unit in validation_units if unit.node_id in selected_node_ids)
    selected_synthesis = tuple(node.node_id for node in scheduled if node.mode == "synthesis")
    return GraphPlan(
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
        requirement_to_node=requirement_to_node,
        validation_evidence_mapping=evidence_mapping,
        routing_catalog_closed=routing_assessment.catalog_closed if routing_assessment is not None else False,
        consulted_routers=routing_assessment.consulted_routers if routing_assessment is not None else (),
        exact_reused_requirement_ids=routing_assessment.reused_requirement_ids if routing_assessment is not None else (),
        user_excluded_catalog_ids=routing_assessment.user_excluded_catalog_ids if routing_assessment is not None else (),
        routing_completion_blockers=routing_assessment.completion_blocking_catalog_ids if routing_assessment is not None else (),
        dispatch_allowed=routing_assessment.feasible if routing_assessment is not None else True,
        blockers=routing_assessment.blockers if routing_assessment is not None else (),
    )


def assess_node_acceptance(evidence: NodeAcceptanceEvidence) -> Assessment:
    """Require isolated execution proof even for a timed-out returned report."""
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


def stop_after_worker_creation_failure(failure: CreationFailure) -> ResumeManifest:
    """Halt dispatch and account for all work requiring a fresh worker."""
    _validate_unique_ids((node.node_id for node in failure.planned_nodes), label="planned node")
    by_id = {node.node_id: node for node in failure.planned_nodes}
    if failure.failed_node_id not in by_id:
        msg = "failed node must belong to the planned graph"
        raise ValueError(msg)
    accepted = set(failure.accepted_node_ids)
    unknown_unaccepted = sorted(set(failure.unaccepted_node_ids) - set(by_id))
    if unknown_unaccepted:
        msg = "unaccepted nodes do not belong to the planned graph: " + ", ".join(unknown_unaccepted)
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
    unaccepted_ids = set(failure.unaccepted_node_ids) | {node.node_id for node in remaining}
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


def assess_completion(evidence: CompletionEvidence) -> Assessment:
    """Enforce the graph-completion and repo-review migration gate."""
    covered_requirements = (*evidence.completed_requirement_ids, *evidence.exact_reused_requirement_ids)
    coverage_checks = (
        (evidence.required_requirement_ids, covered_requirements, "required review requirements are incomplete"),
        (evidence.required_documentation_ids, evidence.completed_documentation_ids, "required documentation or citation coverage is incomplete"),
        (evidence.required_validation_node_ids, evidence.accepted_validation_node_ids, "baseline or required validation is incomplete"),
        (evidence.required_synthesis_node_ids, evidence.accepted_synthesis_node_ids, "required production synthesis is incomplete"),
    )
    blockers = [blocker for required, satisfied, label in coverage_checks if (blocker := _missing_completion_evidence(required, satisfied, label)) is not None]
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
            (evidence.independent_review_required and not evidence.independent_review_accepted, "required independent repository review is incomplete"),
            (not evidence.fingerprints_matched, "source-state fingerprints did not remain matched"),
            (bool(evidence.isolation_failures), "isolation failures occurred: " + ", ".join(evidence.isolation_failures)),
            (not evidence.final_report_synthesized, "final report was not synthesized"),
            (not evidence.findings_deduplicated, "final findings were not deduplicated"),
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
        and trial.worker_failure_forced is True
        and trial.recovery_completed is True
        and trial.grouped_fallback_completed is True
        for trial in trials
    ):
        blockers.append("no accepted forced worker-failure trial completed grouped fallback")
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
    )


def select_execution_profile(
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
            feasible=True, blockers=(), profile="grouped", reason="grouped delivery is the default profile", isolated_requested=False, isolated_only=False
        )

    blockers: list[str] = []
    if not fresh_workers_supported:
        blockers.append("fresh no-inherited-turn workers are unavailable")
    if selected_budget.total <= selected_budget.recovery_finalization_reserve or selected_budget.recovery_finalization_reserve < 1:
        blockers.append("configured fresh-worker budget must exceed a positive recovery/finalization reserve")
    if capacity_metadata is None:
        blockers.append("safe aggregate worker-capacity metadata is unavailable")
    else:
        capacity = assess_worker_capacity(capacity_metadata, required_fresh_worker_creations=max(1, selected_budget.recovery_finalization_reserve + 1))
        blockers.extend(capacity.blockers)
        if capacity.feasible and capacity.full_plan_creation_capacity_guaranteed is not True:
            blockers.append("full bounded-plan fresh-worker creation capacity is not guaranteed")

    if not blockers:
        return ExecutionProfileAssessment(
            feasible=True,
            blockers=(),
            profile="isolated",
            reason="explicit isolation request passed the worker-capability gate",
            isolated_requested=True,
            isolated_only=isolated_only,
        )

    if isolated_only:
        return ExecutionProfileAssessment(
            feasible=False,
            blockers=tuple(blockers),
            profile="blocked",
            reason="isolated-only execution cannot start safely",
            isolated_requested=True,
            isolated_only=True,
        )

    return ExecutionProfileAssessment(
        feasible=True,
        blockers=tuple(blockers),
        profile="grouped",
        reason="isolated execution was requested but unavailable; using grouped delivery",
        isolated_requested=True,
        isolated_only=False,
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
    """Reconcile node, worker, skill, and validator lifecycle sets."""
    selected = set(ledger.selected_nodes)
    accepted = set(ledger.accepted_nodes)
    blocked_after = set(ledger.blocked_after_execution)
    blocked_before = set(ledger.blocked_before_execution)
    invalidated = set(ledger.invalidated_nodes)
    attempts = set(ledger.worker_attempts)
    created = set(ledger.workers_created)
    creation_failures = set(ledger.worker_creation_failures)
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
        (not created <= attempts or not executed_skills <= created, "created-worker or executed-skill records lack a worker attempt"),
        (not (accepted | blocked_after | invalidated) <= created, "executed node outcomes lack a created worker"),
        (
            not (accepted | invalidated) <= executed_skills or not executed_skills <= accepted | blocked_after | invalidated,
            "accepted, invalidated, and executed-skill records do not reconcile",
        ),
        (bool(blocked_before & created), "pre-execution blocked nodes incorrectly claim a created worker"),
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


def _resolved_reference_tuple(item: Mapping[str, Any], name: str, skill_roots: Sequence[Path]) -> tuple[str, ...]:
    return tuple(str(_resolve_skill_root_path(path, skill_roots)) for path in _tuple_field(item, name))


def _routing_decisions_from_document(document: Mapping[str, Any], skill_roots: Sequence[Path]) -> tuple[RoutingDecision, ...]:
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
            instruction_paths=_tuple_field(item, "instruction_paths"),
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
    document: Mapping[str, Any], *, catalog_path: Path = DEFAULT_ROUTING_CATALOG, skill_roots: Sequence[Path] = (DEFAULT_SKILL_ROOT,)
) -> GraphPlan:
    """Build a graph plan from the exhaustive fixture/CLI JSON schema."""
    routing_assessment: RoutingLedgerAssessment | None = None
    routing_catalog: tuple[RoutingCatalogEntry, ...] = ()
    routing_decisions: tuple[RoutingDecision, ...] = ()
    if document.get("routing_decisions") is not None:
        routing_catalog = load_routing_catalog(catalog_path, skill_roots=skill_roots)
        routing_decisions = _routing_decisions_from_document(document, skill_roots)
        consulted_routers = _tuple_field(document, "consulted_routers")
        routing_assessment = validate_routing_ledger(routing_catalog, routing_decisions, consulted_routers=consulted_routers)
        routing_metadata_blockers: list[str] = []
        scope_mode = document.get("scope_mode")
        if scope_mode not in {"branch", "staged-only", "changed-file-only", "baseline", "release-readiness"}:
            routing_metadata_blockers.append("exhaustive routing requires a known scope_mode")
        concrete_change_target = document.get("concrete_change_target")
        if not isinstance(concrete_change_target, bool):
            routing_metadata_blockers.append("exhaustive routing requires concrete_change_target=true or false")
        independent_decision = next((item for item in routing_decisions if item.catalog_id == "repo.independent"), None)
        if concrete_change_target is True and (independent_decision is None or independent_decision.disposition != "selected"):
            routing_metadata_blockers.append("a concrete change target requires selected repository-independent-review")
        if concrete_change_target is False and independent_decision is not None and independent_decision.disposition == "selected":
            routing_metadata_blockers.append("a pure baseline without a concrete change must not select repository-independent-review")
        if document.get("captured_paths") is not None:
            classifier = assess_repository_classifier_floor(
                routing_catalog,
                routing_decisions,
                classify_repository_paths(_tuple_field(document, "captured_paths"), release_readiness=bool(document.get("release_readiness", False))),
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
        routed_additional_nodes = independent_nodes_from_routing(routing_catalog, routing_decisions)
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
                instruction_paths=_resolved_reference_tuple(item, "instruction_paths", skill_roots),
                validation_requirement_ids=_tuple_field(item, "validation_requirement_ids"),
                owners=_tuple_field(item, "owners"),
            )
            for item in document.get("review_requirements", [])
        )
    validation_requirements = tuple(
        ValidationRequirement(
            requirement_id=str(item["requirement_id"]),
            source_state=tuple(item["source_state"]),
            commands=_tuple_field(item, "commands"),
            working_directories=_tuple_field(item, "working_directories"),
            environment=str(item["environment"]),
            toolchain=str(item["toolchain"]),
            features=_tuple_field(item, "features"),
            platform=str(item["platform"]),
            artifact_owner=str(item["artifact_owner"]),
            mutation_lock=str(item["mutation_lock"]),
            canonical_recipe=(str(item["canonical_recipe"]) if item.get("canonical_recipe") is not None else None),
            evidence_id=(str(item["evidence_id"]) if item.get("evidence_id") is not None else None),
            required=bool(item.get("required", True)),
            baseline=bool(item.get("baseline", False)),
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
            instruction_paths=_resolved_reference_tuple(item, "instruction_paths", skill_roots),
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
    declared_additional_nodes = tuple(
        WorkerNode(
            node_id=str(item["node_id"]),
            skill_id=str(item["skill_id"]),
            skill_path=str(_resolve_checked_skill_path(str(item["skill_path"]), str(item["skill_id"]), skill_roots)),
            mode=str(item["mode"]),
            priority=str(item["priority"]),
            required=bool(item.get("required", False)),
            requirement_ids=_tuple_field(item, "requirement_ids"),
            coverage=_tuple_field(item, "coverage"),
            predecessors=_tuple_field(item, "predecessors"),
            synthesis_dependency=(str(item["synthesis_dependency"]) if item.get("synthesis_dependency") is not None else None),
            instruction_paths=_resolved_reference_tuple(item, "instruction_paths", skill_roots),
            static_references=_resolved_reference_tuple(item, "static_references", skill_roots),
        )
        for item in document.get("additional_nodes", [])
    )
    return plan_graph(
        review_requirements,
        validation_requirements,
        synthesis_nodes,
        additional_nodes=(*routed_additional_nodes, *declared_additional_nodes),
        routing_assessment=routing_assessment,
        budget=WorkerBudget(
            total=int(document.get("worker_budget", DEFAULT_TOTAL_FRESH_WORKER_BUDGET)),
            recovery_finalization_reserve=int(document.get("recovery_finalization_reserve", DEFAULT_RECOVERY_FINALIZATION_RESERVE)),
        ),
        validator_skill_path=str(_resolve_checked_skill_path("$SKILLS_ROOT/review-validator/SKILL.md", "review-validator", skill_roots)),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one deterministic, read-only fixture-based planning dry run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON graph-planning fixture")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_ROUTING_CATALOG, help="machine-readable routing catalog")
    parser.add_argument("--skill-root", action="append", type=Path, help="approved skill root; repeat for multiple roots")
    args = parser.parse_args(argv)
    document = json.loads(args.input.read_text(encoding="utf-8"))
    plan = plan_from_document(document, catalog_path=args.catalog, skill_roots=tuple(args.skill_root or (DEFAULT_SKILL_ROOT,)))
    print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    return 0 if plan.dispatch_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
