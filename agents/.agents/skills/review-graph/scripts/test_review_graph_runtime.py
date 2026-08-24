"""Tests for compact review-graph runtime compilation."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast

import pytest
from review_graph_plan import GraphPlan, expand_compact_routing, load_routing_catalog, plan_from_document, validate_routing_ledger
from review_graph_runtime import (
    JournalEventRequest,
    append_journal_event,
    build_routing_projection_document,
    build_synthesis_bundle,
    compile_review,
    compile_validation,
    finalize_proof,
    main,
    materialize_dispatches,
    next_ready_nodes,
    read_execution_journal,
)

SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"
RUST_ERROR_SKILL = SKILL_ROOT / "rust-error-variants" / "SKILL.md"
VALIDATOR_SKILL = SKILL_ROOT / "review-validator" / "SKILL.md"
VALIDATOR_CONTRACT = SKILL_ROOT / "review-validator" / "references" / "graph-dispatch.md"
STATE_FIXTURE = "agents/.agents/skills/review-graph/scripts/fixtures/state.rs"
ORDINARY_PROMPT_WORD_BUDGET = 2400
VALIDATOR_PROMPT_WORD_BUDGET = 850
ALL_SURFACE_PROMPT_WORD_BUDGET = 4200
TRACE_PRIORITIZED_RUST_LEAF_BUDGETS = {
    "rust-api-docs": 950,
    "rust-cargo-hygiene": 900,
    "rust-error-variants": 1400,
    "rust-invariant-performance": 1350,
    "rust-prelude-exports": 950,
    "rust-production-review": 950,
    "rust-scientific-correctness": 1500,
    "rust-test-quality": 950,
}
TRACE_PRIORITIZED_DOCUMENTATION_SKILL_BUDGETS = {
    "academic-authorship-boundary": 700,
    "cpp-api-docs": 950,
    "docs-review-orchestrator": 400,
    "repository-docs-review": 800,
    "scientific-citation-audit": 500,
    "scientific-crate-docs-review": 750,
    "scientific-software-docs-review": 900,
}
TRACE_PRIORITIZED_PYTHON_SKILL_BUDGETS = {
    "jupyter-notebook-review": 900,
    "python-build-portability": 1050,
    "python-cli-review": 800,
    "python-parse-dont-validate": 850,
    "python-production-review": 1100,
    "python-review-orchestrator": 400,
    "python-scientific-review": 750,
    "python-support-scripts": 800,
    "python-test-quality": 800,
}
TRACE_PRIORITIZED_SHARED_SKILL_BUDGETS = {"project-tooling-review": 850}
ALL_SURFACE_PATHS = (
    "src/lib.cpp",
    "include/lib.hpp",
    "src/lib.rs",
    "src/main.py",
    "docs/README.md",
    "justfile",
    "pyproject.toml",
    "Cargo.toml",
    "CMakeLists.txt",
)
ALL_ROUTER_IDS = ("review-graph", "cpp-review-orchestrator", "rust-review-orchestrator", "python-review-orchestrator", "docs-review-orchestrator")
FORBIDDEN_DISPATCH_KEYS = frozenset(
    {
        "accepted_node_ids",
        "artifact_manifest",
        "blocked_node_ids",
        "complete_lifecycle_ledger",
        "complete_routing_ledger",
        "evidence_contract",
        "execution_journal",
        "in_flight_node_ids",
        "invalidated_node_ids",
        "journal",
        "journal_events",
        "lifecycle",
        "lifecycle_ledger",
        "maintainer_specifications",
        "native_artifacts",
        "node_contract",
        "planning_contract",
        "predecessor_artifacts",
        "predecessor_reports",
        "prior_conclusions",
        "prior_reports",
        "proof",
        "report_contract",
        "repository_review_proof",
        "routing_decisions",
        "routing_ledger",
        "validation_ledger",
    }
)
FORBIDDEN_MAINTAINER_REFERENCES = frozenset(
    {
        "evidence-contract.md",
        "execution-feasibility.md",
        "migration-acceptance.md",
        "node-contract.md",
        "planning-contract.md",
        "report-contract.md",
        "routing-catalog.json",
        "routing-handoff.md",
        "runtime-contract.md",
    }
)


def _word_count(paths: tuple[Path, ...]) -> int:
    return sum(len(path.read_text(encoding="utf-8").split()) for path in paths)


def _assert_compact_dispatches(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        serialized = json.dumps(entry["dispatch"], sort_keys=True)
        present_keys = sorted(key for key in FORBIDDEN_DISPATCH_KEYS if f'"{key}":' in serialized)
        present_references = sorted(reference for reference in FORBIDDEN_MAINTAINER_REFERENCES if reference in serialized)
        assert not present_keys, f"dispatch {entry['node_id']} contains coordinator-only fields: {present_keys}"
        assert not present_references, f"dispatch {entry['node_id']} contains maintainer specifications: {present_references}"


def _sparse_plan_document() -> dict[str, Any]:
    return {
        "captured_paths": [STATE_FIXTURE],
        "concrete_change_target": False,
        "consulted_routers": ["review-graph", "rust-review-orchestrator"],
        "execution_profile": "grouped",
        "release_readiness": False,
        "routing_overrides": [
            {
                "applicability_evidence": ["state.rs changes Rust state behavior"],
                "catalog_id": "rust.invariants",
                "disposition": "selected",
                "owners": ["rust"],
                "reason": "state transition behavior changed",
                "review_surface": [STATE_FIXTURE],
            }
        ],
        "scope_mode": "baseline",
        "validation_requirements": [
            {
                "allowed_artifacts": [],
                "artifact_owner": "repository",
                "authority": "repository baseline",
                "baseline": True,
                "canonical_recipe": "true",
                "capture_command": "capture_scope.py --mode baseline",
                "captured_paths": [STATE_FIXTURE],
                "commands": ["true"],
                "dependency_policy": "stop-on-failure",
                "elapsed_time_budget": "30s",
                "environment": "current host",
                "evidence_id": None,
                "execution_strategy": "sequential",
                "expected_evidence": "baseline command completes",
                "features": [],
                "independence_basis": "none",
                "meaningful_skips": [],
                "mutation_classification": "non-mutating under validation-only",
                "mutation_lock": "repository read-only",
                "planning_blocker": None,
                "platform": "current host",
                "request": "validate compact routing fixture",
                "requested_scope": "baseline",
                "required": True,
                "requirement_id": "baseline-validation",
                "selection_reason": "bounded graphs require baseline validation",
                "source_state": ["scope", "worktree", "repository"],
                "toolchain": "system",
                "working_directories": [str(SKILL_ROOT.parents[2])],
            }
        ],
    }


def _sparse_plan() -> GraphPlan:
    return plan_from_document(_sparse_plan_document(), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))


def _json_plan(plan: GraphPlan) -> dict[str, object]:
    value = json.loads(json.dumps(asdict(plan)))
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _dispatch(*, mode: str = "audit") -> dict[str, object]:
    return {
        "artifact_id": "artifact://audit-errors",
        "authorization": "review-and-fix" if mode == "fix" else "review-only",
        "after_state": ["scope", "worktree", "repository"],
        "before_state": ["scope", "worktree", "repository"],
        "evidence_id": "review:audit-errors",
        "execution_location": "worker" if mode != "fix" else "coordinator",
        "execution_profile": "grouped",
        "fresh_context": mode != "fix",
        "mode": mode,
        "node_id": "audit-errors" if mode != "fix" else "fix-errors",
        "predecessor_evidence_ids": [],
        "reference_paths": [],
        "requirement_ids": ["rust.errors"],
        "selection_reason": "typed error behavior changed",
        "skill_id": "rust-error-variants",
        "skill_path": str(RUST_ERROR_SKILL),
        "source_state": ["scope", "worktree", "repository"],
        "state_verification_command": "capture_scope.py --mode branch",
        "worker_created": mode != "fix",
    }


def test_compile_review_builds_verified_artifact_from_compact_payload() -> None:
    content, metadata = compile_review(
        {
            "dispatch": _dispatch(),
            "payload": {
                "files_inspected": ["src/error.rs"],
                "findings": [
                    {
                        "evidence": "the public error path discards its typed source",
                        "location": "src/error.rs:12",
                        "remediation": "preserve the source in the existing variant",
                        "severity": "P2",
                        "summary": "typed error evidence is discarded",
                    }
                ],
                "handoffs": [],
                "limitations": [],
                "nearby_contract_owners": ["src/lib.rs"],
                "status": "completed",
                "validation_requirements": [],
            },
        }
    )

    assert content.startswith(b"# Review Node Result\n")
    assert b"Canonical worker payload" in content
    assert metadata["evidence"]["fresh_context"] is True
    assert metadata["evidence"]["finding_ids"] == ("audit-errors-finding-1",)
    assert metadata["artifact_digest"].startswith("sha256:")


def test_compile_fix_binds_changed_paths_and_transition_state() -> None:
    dispatch = _dispatch(mode="fix")
    dispatch.update(
        {
            "after_state": ["scope-after", "worktree-after", "repository-after"],
            "changed_paths": ["src/error.rs"],
            "expected_after_state": ["scope-after", "worktree-after", "repository-after"],
            "planned_paths": ["src/error.rs"],
            "source_mutated": True,
        }
    )
    content, metadata = compile_review(
        {
            "dispatch": dispatch,
            "payload": {
                "changes": [
                    {
                        "contract_preserved": "public compatibility and unrelated error behavior",
                        "files": ["src/error.rs"],
                        "finding_ids": ["incidental-fix-errors-1"],
                        "what_changed": "used the existing typed error variant",
                        "why": "preserves structured caller evidence",
                    }
                ],
                "files_inspected": ["src/error.rs"],
                "findings": [],
                "handoffs": [],
                "limitations": [],
                "nearby_contract_owners": ["src/lib.rs"],
                "status": "completed",
                "validation_requirements": [],
            },
        }
    )

    assert b"changed-as-reported" in content
    assert metadata["evidence"]["source_mutated"] is True


def test_compile_review_rejects_inherited_worker_context() -> None:
    dispatch = _dispatch()
    dispatch["fresh_context"] = False
    with pytest.raises(ValueError, match="fresh_context=true"):
        compile_review(
            {
                "dispatch": dispatch,
                "payload": {
                    "files_inspected": ["src/error.rs"],
                    "findings": [],
                    "handoffs": [],
                    "limitations": [],
                    "nearby_contract_owners": [],
                    "status": "no-findings",
                    "validation_requirements": [],
                },
            }
        )


def test_runtime_cli_writes_verified_review_artifacts(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    artifact = tmp_path / "review.md"
    metadata = tmp_path / "review.json"
    request.write_text(
        json.dumps(
            {
                "dispatch": _dispatch(),
                "payload": {
                    "files_inspected": ["src/error.rs"],
                    "findings": [],
                    "handoffs": [],
                    "limitations": [],
                    "nearby_contract_owners": [],
                    "status": "no-findings",
                    "validation_requirements": [],
                },
            }
        ),
        encoding="utf-8",
    )

    result = main(["compile-review", "--input", str(request), "--artifact", str(artifact), "--metadata", str(metadata)])

    assert result == 0
    assert artifact.read_bytes().startswith(b"# Review Node Result\n")
    assert json.loads(metadata.read_text(encoding="utf-8"))["evidence"]["evidence_id"] == "review:audit-errors"
    assert main(["compile-review", "--input", str(request), "--artifact", str(artifact), "--metadata", str(metadata)]) == 0

    artifact.write_text("tampered\n", encoding="utf-8")
    assert main(["compile-review", "--input", str(request), "--artifact", str(artifact), "--metadata", str(metadata)]) == 2


def test_compile_validation_builds_verified_artifact_from_execution_payload() -> None:
    unit = {
        "allowed_artifacts": [],
        "artifact_owner": "rust",
        "baseline": True,
        "canonical_recipe": "just check-fast",
        "capture_command": "capture_scope.py --mode branch",
        "captured_paths": ["src/error.rs"],
        "commands": ["just check-fast"],
        "dependency_policy": "stop-on-failure",
        "environment": "clean repository environment",
        "evidence_ids": [],
        "execution_strategy": "sequential",
        "features": [],
        "independence_basis": "none",
        "meaningful_skips": [],
        "mutation_lock": "repository read-only",
        "node_id": "validation-rust",
        "planning_blocker": None,
        "platform": "current host",
        "request": "validate typed error changes",
        "requested_scope": "branch",
        "required": True,
        "requirement_ids": ["rust-tests"],
        "requirement_plans": [
            [
                "rust-tests",
                "justfile check-fast",
                "typed error behavior requires focused tests",
                "non-mutating under validation-only",
                "focused tests pass",
                "300s",
                None,
            ]
        ],
        "source_state": ["scope", "worktree", "repository"],
        "toolchain": "repository toolchain",
        "working_directories": [str(SKILL_ROOT.parents[2])],
    }
    content, metadata = compile_validation(
        {
            "dispatch": {
                "after_state": ["scope", "worktree", "repository"],
                "artifact_id": "artifact://validation-rust",
                "before_state": ["scope", "worktree", "repository"],
                "evidence_id": "validation:rust",
                "execution_location": "worker",
                "execution_profile": "grouped",
                "fresh_context": True,
                "reference_paths": [str(VALIDATOR_CONTRACT)],
                "skill_path": str(VALIDATOR_SKILL),
                "state_verification_command": "capture_scope.py --mode branch",
                "validation_unit": unit,
                "worker_created": True,
            },
            "payload": {
                "artifacts": [],
                "executions": [
                    {
                        "artifact_paths": [],
                        "command": "just check-fast",
                        "elapsed": "3s",
                        "evidence": "command exited successfully",
                        "executor": "worker validation-rust",
                        "exit_code": 0,
                        "result": "passed",
                        "working_directory": str(SKILL_ROOT.parents[2]),
                    }
                ],
                "limitations": [],
                "status": "passed",
            },
        }
    )

    assert content.startswith(b"# Validation Result\n")
    assert b"Canonical worker payload" in content
    assert metadata["evidence"]["status"] == "passed"


def test_sparse_routing_expands_to_exhaustive_catalog_records() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    decisions = expand_compact_routing(
        catalog,
        consulted_routers=("review-graph", "rust-review-orchestrator"),
        captured_paths=("src/lib.rs",),
        overrides=(
            {
                "applicability_evidence": ["src/lib.rs changes typed error propagation"],
                "catalog_id": "rust.errors",
                "disposition": "selected",
                "owners": ["rust"],
                "reason": "typed error behavior changed",
                "review_surface": ["src/lib.rs"],
            },
        ),
        change_target="git diff origin/main...HEAD",
    )

    assessment = validate_routing_ledger(catalog, decisions, consulted_routers=("review-graph", "rust-review-orchestrator"))
    by_id = {decision.catalog_id: decision for decision in decisions}
    assert assessment.feasible
    assert len(decisions) == sum(entry.router_id in {"review-graph", "rust-review-orchestrator"} for entry in catalog)
    assert by_id["repo.rust"].disposition == "selected"
    assert by_id["rust.errors"].skill_id == "rust-error-variants"
    assert by_id["rust.errors"].disposition == "selected"
    assert by_id["rust.concurrency"].disposition == "not-applicable"
    assert by_id["rust.synthesis"].disposition == "selected"


def test_sparse_routing_rejects_catalog_owned_identity_fields() -> None:
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    with pytest.raises(ValueError, match="catalog-owned fields"):
        expand_compact_routing(
            catalog,
            consulted_routers=("review-graph", "rust-review-orchestrator"),
            captured_paths=("src/lib.rs",),
            overrides=(
                {
                    "applicability_evidence": ["typed errors changed"],
                    "catalog_id": "rust.errors",
                    "disposition": "selected",
                    "reason": "typed errors changed",
                    "review_surface": ["src/lib.rs"],
                    "skill_id": "substituted-skill",
                },
            ),
        )


def test_plan_from_document_accepts_sparse_routing_and_derives_synthesis() -> None:
    plan = _sparse_plan()

    assert plan.routing_catalog_closed
    assert "rust.invariants" in plan.selected_review_requirements
    assert {"rust-synthesis", "repository-synthesis"} <= set(plan.synthesis_nodes)
    decisions = {decision.catalog_id: decision for decision in plan.routing_decisions}
    assert decisions["rust.invariants"].disposition == "selected"
    assert decisions["rust.errors"].disposition == "not-applicable"
    validator = next(node for node in plan.actual_worker_nodes if node.skill_id == "review-validator")
    assert tuple(path for path, _digest in validator.reference_digests) == (str(VALIDATOR_CONTRACT),)


def test_synthesis_bundle_is_order_independent_and_hashed(tmp_path: Path) -> None:
    _plan, sources = _compile_materialized_evidence(tmp_path)
    first = build_synthesis_bundle({"source_state": ["scope", "worktree", "repository"], "sources": sources})
    second = build_synthesis_bundle({"source_state": ["scope", "worktree", "repository"], "sources": list(reversed(sources))})

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["bundle_digest"].startswith("sha256:")
    expected_ids = sorted(json.loads(Path(source["metadata_path"]).read_text(encoding="utf-8"))["evidence"]["evidence_id"] for source in sources)
    assert [record["evidence_id"] for record in first["records"]] == expected_ids


def test_synthesis_bundle_rejects_caller_authored_records() -> None:
    with pytest.raises(ValueError, match="requires compiler evidence sources"):
        build_synthesis_bundle({"records": [{"evidence_id": "review:untrusted"}], "source_state": ["scope", "worktree", "repository"]})


def test_routing_projection_is_complete_compact_and_hashed() -> None:
    captured_path = "src/lib.rs"
    projection = build_routing_projection_document(
        {"captured_paths": [captured_path], "consulted_routers": ["review-graph", "rust-review-orchestrator"]},
        catalog_path=ROUTING_CATALOG,
        skill_roots=(SKILL_ROOT,),
    )

    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    expected_ids = {entry.catalog_id for entry in catalog if entry.router_id in {"review-graph", "rust-review-orchestrator"}}
    projected = {entry["catalog_id"]: entry for entry in projection["entries"]}
    assert set(projected) == expected_ids
    assert projected["rust.errors"]["matched_paths"] == [captured_path]
    assert projected["rust.concurrency"]["matched_paths"] == [captured_path]
    assert projection["projection_digest"].startswith("sha256:")


def test_validation_coalescing_ignores_narrative_differences_without_losing_provenance() -> None:
    document = _sparse_plan_document()
    requirements = cast("list[dict[str, Any]]", document["validation_requirements"])
    second = deepcopy(requirements[0])
    second.update(
        {
            "meaningful_skips": ["network-only integration check"],
            "request": "validate the same command for a second routed requirement",
            "requirement_id": "routed-validation",
            "selection_reason": "routed specialist requires the repository baseline",
        }
    )
    requirements.append(second)

    plan = plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))

    assert len(plan.coalesced_validation_units) == 1
    unit = plan.coalesced_validation_units[0]
    assert unit.requirement_ids == ("baseline-validation", "routed-validation")
    assert unit.meaningful_skips == ("network-only integration check",)
    assert unit.requirement_requests == (
        ("baseline-validation", "validate compact routing fixture"),
        ("routed-validation", "validate the same command for a second routed requirement"),
    )


def test_dispatch_materialization_and_ready_nodes_are_plan_derived(tmp_path: Path) -> None:
    plan = _sparse_plan()
    result = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )

    assert len(result["dispatches"]) == plan.complete_node_count
    by_id = {entry["node_id"]: entry for entry in result["dispatches"]}
    synthesis = by_id["repository-synthesis"]["dispatch"]
    expected_predecessors = [
        ("validation:" if predecessor.startswith("validation-") else "review:") + predecessor
        for predecessor in next(node for node in plan.actual_worker_nodes if node.node_id == "repository-synthesis").predecessors
    ]
    assert synthesis["predecessor_evidence_ids"] == expected_predecessors
    _assert_compact_dispatches(result["dispatches"])
    assert by_id[next(node.node_id for node in plan.actual_worker_nodes if node.mode == "validation")]["result_contract"] == "compact-validation"

    lifecycle_document = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    initial = next_ready_nodes(lifecycle_document, journal_events=(), dispatch_set=result)
    assert set(initial["ready_node_ids"]) == {node.node_id for node in plan.actual_worker_nodes if not node.predecessors}
    assert {entry["node_id"] for entry in initial["ready_dispatches"]} == set(initial["ready_node_ids"])

    journal = tmp_path / "execution.jsonl"
    started = initial["ready_node_ids"][0]
    append_journal_event(journal, lifecycle_document, JournalEventRequest(started, "in-flight"))
    events, _state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    after_start = next_ready_nodes(lifecycle_document, journal_events=events, dispatch_set=result)
    assert started not in after_start["ready_node_ids"]
    assert after_start["lifecycle"]["in_flight_node_ids"] == [started]


def test_independent_review_dispatch_excludes_coordinator_context(tmp_path: Path) -> None:
    plan = _sparse_plan()
    audit = next(node for node in plan.actual_worker_nodes if node.mode == "audit")
    independent = replace(
        audit,
        change_target=f"git diff -- {STATE_FIXTURE}",
        mode="independent-review",
        skill_id="repository-independent-review",
        skill_path=str(SKILL_ROOT / "repository-independent-review" / "SKILL.md"),
    )
    independent_plan = replace(
        plan,
        actual_worker_nodes=tuple(independent if node.node_id == audit.node_id else node for node in plan.actual_worker_nodes),
        captured_path_line_bounds=((STATE_FIXTURE, 3),),
    )
    result = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(independent_plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode branch",
        }
    )
    entry = next(item for item in result["dispatches"] if item["node_id"] == independent.node_id)

    assert entry["result_contract"] == "native-independent-review"
    assert entry["dispatch"]["planned_path_line_bounds"] == [[STATE_FIXTURE, 3]]
    _assert_compact_dispatches(result["dispatches"])


def test_journal_and_next_ready_cli_use_persisted_artifacts(tmp_path: Path) -> None:
    plan = _sparse_plan()
    lifecycle_document = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    lifecycle_path = tmp_path / "lifecycle.json"
    dispatch_path = tmp_path / "dispatches.json"
    journal_path = tmp_path / "execution.jsonl"
    ready_path = tmp_path / "ready.json"
    lifecycle_path.write_text(json.dumps(lifecycle_document), encoding="utf-8")
    dispatch_path.write_text(json.dumps(dispatch_set), encoding="utf-8")
    started = next(node.node_id for node in plan.actual_worker_nodes if not node.predecessors)

    assert main(["journal-append", "--input", str(lifecycle_path), "--journal", str(journal_path), "--node-id", started, "--status", "in-flight"]) == 0
    assert (
        main(["next-ready", "--input", str(lifecycle_path), "--journal", str(journal_path), "--dispatches", str(dispatch_path), "--output", str(ready_path)])
        == 0
    )
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    assert started not in ready["ready_node_ids"]
    assert ready["journal"]["event_count"] == 1


def _compile_materialized_evidence(tmp_path: Path) -> tuple[GraphPlan, list[dict[str, str]]]:
    plan = _sparse_plan()
    materialized = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    sources: list[dict[str, str]] = []
    for entry in materialized["dispatches"]:
        dispatch = entry["dispatch"]
        dispatch.update({"after_state": ["scope", "worktree", "repository"], "before_state": ["scope", "worktree", "repository"]})
        if entry["result_contract"] == "compact-validation":
            unit = dispatch["validation_unit"]
            payload = {
                "artifacts": [],
                "executions": [
                    {
                        "artifact_paths": [],
                        "command": command,
                        "elapsed": "0s",
                        "evidence": "command exited successfully",
                        "executor": dispatch["node_id"],
                        "exit_code": 0,
                        "result": "passed",
                        "working_directory": working_directory,
                    }
                    for command, working_directory in zip(unit["commands"], unit["working_directories"], strict=True)
                ],
                "limitations": [],
                "status": "passed",
            }
            content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
            kind = "validation"
        else:
            payload = {
                "files_inspected": [STATE_FIXTURE],
                "findings": [],
                "handoffs": [],
                "limitations": [],
                "nearby_contract_owners": [],
                "status": "no-findings",
                "validation_requirements": [],
            }
            content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
            kind = "review"
        artifact_path = Path(entry["artifact_path"])
        metadata_path = Path(entry["metadata_path"])
        artifact_path.write_bytes(content)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        sources.append({"artifact_path": str(artifact_path), "kind": kind, "metadata_path": str(metadata_path)})
    return plan, sources


def test_artifact_derived_synthesis_and_final_proof_are_verified(tmp_path: Path) -> None:
    plan, sources = _compile_materialized_evidence(tmp_path)
    bundle = build_synthesis_bundle({"source_state": ["scope", "worktree", "repository"], "sources": sources})
    final = finalize_proof({"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"], "sources": sources})

    assert len(bundle["records"]) == plan.complete_node_count
    assert final["status"] == "complete"
    assert final["blockers"] == []
    assert len(final["artifact_manifest"]["entries"]) == plan.complete_node_count

    metadata_path = Path(sources[0]["metadata_path"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["normalized_record"]["status"] = "completed"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="normalized record does not match"):
        build_synthesis_bundle({"source_state": ["scope", "worktree", "repository"], "sources": sources})


def test_append_only_journal_drives_scheduling_and_cascade_invalidation(tmp_path: Path) -> None:
    plan, sources = _compile_materialized_evidence(tmp_path)
    lifecycle_document = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    source_by_node = {json.loads(Path(source["metadata_path"]).read_text(encoding="utf-8"))["evidence"]["node_id"]: source for source in sources}
    journal = tmp_path / "execution.jsonl"

    while True:
        events, _state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
        ready = next_ready_nodes(lifecycle_document, journal_events=events, dispatch_set=dispatch_set)
        non_final = [node_id for node_id in ready["ready_node_ids"] if node_id != "repository-synthesis"]
        if not non_final:
            break
        for node_id in non_final:
            append_journal_event(journal, lifecycle_document, JournalEventRequest(node_id, "accepted", source=source_by_node[node_id]))

    events, _state, head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    before_synthesis = next_ready_nodes(lifecycle_document, journal_events=events, dispatch_set=dispatch_set)
    assert before_synthesis["ready_node_ids"] == ["repository-synthesis"]
    assert before_synthesis["journal"]["head_digest"] == head
    assert before_synthesis["ready_dispatches"][0]["node_id"] == "repository-synthesis"

    append_journal_event(journal, lifecycle_document, JournalEventRequest("repository-synthesis", "accepted", source=source_by_node["repository-synthesis"]))
    with pytest.raises(ValueError, match="cannot transition repository-synthesis from accepted to accepted"):
        append_journal_event(
            journal, lifecycle_document, JournalEventRequest("repository-synthesis", "accepted", source=source_by_node["repository-synthesis"])
        )

    root = next(node for node in plan.actual_worker_nodes if not node.predecessors and node.mode != "validation")
    invalidated = append_journal_event(
        journal, lifecycle_document, JournalEventRequest(root.node_id, "invalidated", reason="repair epoch changed accepted review evidence")
    )
    assert root.node_id in invalidated["affected_node_ids"]
    assert "repository-synthesis" in invalidated["affected_node_ids"]

    events, _state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    repair = next_ready_nodes(lifecycle_document, journal_events=events, dispatch_set=dispatch_set)
    assert root.node_id in repair["ready_node_ids"]
    assert "repository-synthesis" in repair["lifecycle"]["invalidated_node_ids"]
    assert "repository-synthesis" not in repair["ready_node_ids"]
    _assert_compact_dispatches(repair["ready_dispatches"])

    tampered = tmp_path / "tampered.jsonl"
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    records[0]["event_digest"] = "sha256:" + "0" * 64
    tampered.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        read_execution_journal(tampered, plan=plan, source_state=("scope", "worktree", "repository"))


def test_journal_rejects_unverified_acceptance_and_out_of_order_nodes(tmp_path: Path) -> None:
    plan = _sparse_plan()
    lifecycle_document = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    journal = tmp_path / "execution.jsonl"
    with pytest.raises(ValueError, match="requires verified evidence"):
        append_journal_event(
            journal, lifecycle_document, JournalEventRequest(next(node.node_id for node in plan.actual_worker_nodes if not node.predecessors), "accepted")
        )
    dependent = next(node for node in plan.actual_worker_nodes if node.predecessors)
    with pytest.raises(ValueError, match="missing accepted predecessors"):
        append_journal_event(journal, lifecycle_document, JournalEventRequest(dependent.node_id, "in-flight"))
    assert not journal.exists()

    root = next(node for node in plan.actual_worker_nodes if not node.predecessors)
    blocked = append_journal_event(journal, lifecycle_document, JournalEventRequest(root.node_id, "blocked", reason="worker creation failed"))
    assert blocked["evidence"] is None
    with pytest.raises(ValueError, match=f"cannot transition {root.node_id} from blocked to in-flight"):
        append_journal_event(journal, lifecycle_document, JournalEventRequest(root.node_id, "in-flight"))
    append_journal_event(journal, lifecycle_document, JournalEventRequest(root.node_id, "invalidated", reason="worker capacity became available"))
    append_journal_event(journal, lifecycle_document, JournalEventRequest(root.node_id, "in-flight"))
    _events, state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    assert state[root.node_id] == "in-flight"


def test_ordinary_validator_and_all_surface_prompt_budgets() -> None:
    review_prompt = (
        SKILL_ROOT / "repo-review" / "SKILL.md",
        SKILL_ROOT / "review-graph" / "SKILL.md",
        SKILL_ROOT / "review-graph" / "references" / "runtime-contract.md",
    )
    validator_prompt = (VALIDATOR_SKILL, VALIDATOR_CONTRACT)
    projection = build_routing_projection_document(
        {"captured_paths": list(ALL_SURFACE_PATHS), "consulted_routers": list(ALL_ROUTER_IDS)}, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)
    )
    catalog = load_routing_catalog(ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    ordinary_words = _word_count(review_prompt)
    validator_words = _word_count(validator_prompt)
    projection_words = len(json.dumps(projection, indent=2, sort_keys=True).split())
    all_surface_words = ordinary_words + projection_words

    assert len(projection["entries"]) == len(catalog)
    assert set(projection["classifier_signals"]) == {"cpp", "documentation", "python", "rust", "tooling"}
    assert ordinary_words <= ORDINARY_PROMPT_WORD_BUDGET, f"ordinary coordinator prompt proxy is {ordinary_words} words"
    assert validator_words <= VALIDATOR_PROMPT_WORD_BUDGET, f"validator prompt proxy is {validator_words} words"
    assert all_surface_words <= ALL_SURFACE_PROMPT_WORD_BUDGET, f"all-surface prompt proxy is {all_surface_words} words"


def test_trace_prioritized_rust_leaf_prompt_budgets() -> None:
    for skill_id, budget in TRACE_PRIORITIZED_RUST_LEAF_BUDGETS.items():
        entrypoint = SKILL_ROOT / skill_id / "SKILL.md"
        words = _word_count((entrypoint,))

        assert words <= budget, f"{skill_id} graph/orchestrator entrypoint is {words} words"


def test_trace_prioritized_documentation_prompt_budgets() -> None:
    for skill_id, budget in TRACE_PRIORITIZED_DOCUMENTATION_SKILL_BUDGETS.items():
        entrypoint = SKILL_ROOT / skill_id / "SKILL.md"
        words = _word_count((entrypoint,))

        assert words <= budget, f"{skill_id} graph/orchestrator entrypoint is {words} words"


def test_trace_prioritized_python_prompt_budgets() -> None:
    for skill_id, budget in TRACE_PRIORITIZED_PYTHON_SKILL_BUDGETS.items():
        entrypoint = SKILL_ROOT / skill_id / "SKILL.md"
        words = _word_count((entrypoint,))

        assert words <= budget, f"{skill_id} graph/orchestrator entrypoint is {words} words"


def test_trace_prioritized_shared_prompt_budgets() -> None:
    for skill_id, budget in TRACE_PRIORITIZED_SHARED_SKILL_BUDGETS.items():
        entrypoint = SKILL_ROOT / skill_id / "SKILL.md"
        words = _word_count((entrypoint,))

        assert words <= budget, f"{skill_id} graph/orchestrator entrypoint is {words} words"
