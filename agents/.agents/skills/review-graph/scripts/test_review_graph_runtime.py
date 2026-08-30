"""Tests for compact review-graph runtime compilation."""

import json
import os
import shlex
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
from functools import partial
from pathlib import Path
from threading import Barrier
from typing import Any, cast

import pytest
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document, main as bootstrap_main
from review_graph_plan import (
    GraphPlan,
    ValidationArtifact,
    ValidationUnit,
    expand_compact_routing,
    load_routing_catalog,
    main as plan_main,
    plan_from_document,
    repository_review_proof_expectation,
    validate_routing_ledger,
)
from review_graph_runtime import (
    JournalEventRequest,
    _argument_parser,
    _git_path_status,
    _graph_plan,
    _schema_reference,
    _validation_workspace_audit,
    _workspace_content_digest,
    _write_bytes_atomically_once,
    _write_bytes_once,
    advance_after_mutation,
    append_journal_event,
    build_routing_projection_document,
    build_synthesis_bundle,
    capture_workspace_snapshot,
    compile_independent_review,
    compile_review,
    compile_validation,
    finalize_proof,
    main,
    materialize_dispatches,
    next_ready_nodes,
    read_execution_journal,
    reconcile_handoffs,
)
from review_graph_schema import SchemaValidationError, require_schema, require_schema_definition

SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_CATALOG = Path(__file__).resolve().parents[1] / "references" / "routing-catalog.json"
RUST_ERROR_SKILL = SKILL_ROOT / "rust-error-variants" / "SKILL.md"
VALIDATOR_SKILL = SKILL_ROOT / "review-validator" / "SKILL.md"
VALIDATOR_CONTRACT = SKILL_ROOT / "review-validator" / "references" / "graph-dispatch.md"
INDEPENDENT_NATIVE_EXAMPLE = SKILL_ROOT / "repository-independent-review" / "references" / "native-example.md"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references" / "schemas"
STATE_FIXTURE = "agents/.agents/skills/review-graph/scripts/fixtures/state.rs"
ORDINARY_PROMPT_WORD_BUDGET = 2400
VALIDATOR_PROMPT_WORD_BUDGET = 850
ALL_SURFACE_PROMPT_WORD_BUDGET = 4200
TRACE_PRIORITIZED_RUST_LEAF_BUDGETS = {
    "rust-api-design": 1400,
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


def _run_test_git(git: str, *arguments: str) -> None:
    subprocess.run([git, *arguments], check=True, capture_output=True)  # noqa: S603 - resolved Git test fixture.


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


def _late_handoff_replan() -> GraphPlan:
    document = _sparse_plan_document()
    document["consulted_routers"] = ["review-graph", "rust-review-orchestrator", "python-review-orchestrator"]
    document["routing_overrides"] = [
        {
            "applicability_evidence": ["accepted build audit from the unchanged source state"],
            "catalog_id": "rust.build",
            "disposition": "exact-evidence-reused",
            "evidence_id": "review:audit-001",
            "owners": ["rust"],
            "reason": "the prior Rust build audit is exact for this source state",
            "review_surface": [STATE_FIXTURE],
        },
        {
            "applicability_evidence": ["accepted audit from the unchanged source state"],
            "catalog_id": "rust.invariants",
            "disposition": "exact-evidence-reused",
            "evidence_id": "review:audit-002",
            "owners": ["rust"],
            "reason": "the prior Rust invariant audit is exact for this source state",
            "review_surface": [STATE_FIXTURE],
        },
        {
            "applicability_evidence": ["accepted handoff identified notebook ownership"],
            "catalog_id": "repo.python",
            "disposition": "selected",
            "reason": "late handoff requires the Python surface router",
        },
        {
            "applicability_evidence": ["accepted handoff identified notebook semantics"],
            "catalog_id": "python.notebook",
            "disposition": "selected",
            "owners": ["python"],
            "reason": "late handoff requires a notebook audit",
            "review_surface": [STATE_FIXTURE],
        },
    ]
    return plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))


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
                    "changes": [],
                    "command_policy_attested": True,
                    "commands_executed": [],
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


def test_review_payload_schema_reports_all_field_diagnostics() -> None:
    with pytest.raises(SchemaValidationError) as captured:
        require_schema({"status": "unknown", "unexpected": True}, SCHEMA_ROOT / "review-payload-v1.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    paths = {item["path"] for item in diagnostics}
    assert {"$.changes", "$.command_policy_attested", "$.commands_executed", "$.status", "$.unexpected"} <= paths
    status = next(item for item in diagnostics if item["path"] == "$.status")
    assert status["accepted_values"] == ["completed", "no-findings", "blocked"]


def test_planning_schema_aggregates_enum_and_required_field_diagnostics() -> None:
    with pytest.raises(SchemaValidationError) as captured:
        require_schema({"validation_requirements": [{"execution_strategy": "distributed"}]}, SCHEMA_ROOT / "planning-input-v1.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    paths = {item["path"] for item in diagnostics}
    strategy_path = "$.validation_requirements[0].execution_strategy"
    assert {"$.captured_paths", "$.scope_fingerprint", strategy_path} <= paths
    strategy = next(item for item in diagnostics if item["path"] == strategy_path)
    assert strategy["accepted_values"] == ["sequential", "parallel-independent"]


def test_runtime_operations_publish_schema_valid_examples_and_help_links(capsys: pytest.CaptureFixture[str]) -> None:
    examples_path = SCHEMA_ROOT.parent / "runtime-operation-examples-v1.json"
    schema_path = SCHEMA_ROOT / "runtime-operation-inputs-v1.schema.json"
    examples = json.loads(examples_path.read_text(encoding="utf-8"))

    for operation, example in examples.items():
        require_schema_definition(example, schema_path, operation)
        with pytest.raises(SystemExit) as exit_status:
            _argument_parser().parse_args([operation, "--help"])
        assert exit_status.value.code == 0
        help_text = capsys.readouterr().out
        assert f"#/$defs/{operation}" in help_text
        assert f"runtime-operation-examples-v1.json#/{operation}" in help_text


@pytest.mark.parametrize("value", [1, 1.0])
def test_review_payload_schema_rejects_numeric_true_constants(value: float) -> None:
    with pytest.raises(SchemaValidationError) as captured:
        require_schema({"command_policy_attested": value}, SCHEMA_ROOT / "review-payload-v1.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    assert any(item["path"] == "$.command_policy_attested" and item["code"] == "const" for item in diagnostics)


@pytest.mark.parametrize("value", [True, False])
def test_planning_schema_rejects_boolean_schema_versions(value: bool) -> None:
    with pytest.raises(SchemaValidationError) as captured:
        require_schema({"schema_version": value}, SCHEMA_ROOT / "planning-input-v1.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    assert any(item["path"] == "$.schema_version" for item in diagnostics)


@pytest.mark.parametrize("exit_code", ["signal", "1.0", "+ 1", "+12", ""])
def test_validation_payload_schema_rejects_nonnumeric_exit_code_strings(exit_code: str) -> None:
    payload = {
        "artifacts": [],
        "executions": [
            {
                "artifact_paths": [],
                "command": "true",
                "elapsed": "0s",
                "evidence": "command completed",
                "executor": "validation-001",
                "exit_code": exit_code,
                "result": "passed",
                "working_directory": "/repo",
            }
        ],
        "limitations": [],
        "status": "passed",
    }

    with pytest.raises(SchemaValidationError) as captured:
        require_schema(payload, SCHEMA_ROOT / "validation-payload-v2.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    assert any(item["path"] == "$.executions[0].exit_code" and item["code"] == "pattern" for item in diagnostics)


@pytest.mark.parametrize("exit_code", [-9, None, "-9", "0", "none"])
def test_validation_payload_schema_accepts_supported_exit_codes(exit_code: int | str | None) -> None:
    require_schema(
        {
            "artifacts": [],
            "executions": [
                {
                    "artifact_paths": [],
                    "command": "true",
                    "elapsed": "0s",
                    "evidence": "command completed",
                    "executor": "validation-001",
                    "exit_code": exit_code,
                    "result": "passed",
                    "working_directory": "/repo",
                }
            ],
            "limitations": [],
            "status": "passed",
        },
        SCHEMA_ROOT / "validation-payload-v2.schema.json",
    )


def test_validation_payload_v1_remains_legacy_compatible_while_v2_requires_stronger_fields() -> None:
    legacy_artifact_payload = {
        "artifacts": [
            {"artifact_digest": "sha256:" + "a" * 64, "artifact_id": None, "kind": "log", "path": "legacy.log", "repository_status": "outside-repository"}
        ],
        "executions": [],
        "limitations": [],
        "status": "not-applicable",
    }
    legacy_execution_payload = {
        "artifacts": [],
        "executions": [
            {
                "artifact_paths": [],
                "command": "true",
                "evidence": "legacy execution",
                "executor": "validation-legacy",
                "result": "passed",
                "working_directory": "/repo",
            }
        ],
        "limitations": [],
        "status": "passed",
    }

    require_schema(legacy_artifact_payload, SCHEMA_ROOT / "validation-payload-v1.schema.json")
    require_schema(legacy_execution_payload, SCHEMA_ROOT / "validation-payload-v1.schema.json")
    with pytest.raises(SchemaValidationError) as artifact_error:
        require_schema(legacy_artifact_payload, SCHEMA_ROOT / "validation-payload-v2.schema.json")
    with pytest.raises(SchemaValidationError) as execution_error:
        require_schema(legacy_execution_payload, SCHEMA_ROOT / "validation-payload-v2.schema.json")

    artifact_diagnostics = cast("list[dict[str, Any]]", artifact_error.value.as_dict()["diagnostics"])
    execution_diagnostics = cast("list[dict[str, Any]]", execution_error.value.as_dict()["diagnostics"])
    assert any(item["path"] == "$.artifacts[0].artifact_digest_mode" and item["code"] == "required" for item in artifact_diagnostics)
    assert {item["path"] for item in execution_diagnostics if item["code"] == "required"} >= {"$.executions[0].elapsed", "$.executions[0].exit_code"}


def test_schema_reference_reports_canonical_version_and_rejects_filename_mismatch(tmp_path: Path) -> None:
    review = _schema_reference(SCHEMA_ROOT / "review-payload-v1.schema.json")
    validation = _schema_reference(SCHEMA_ROOT / "validation-payload-v2.schema.json")
    mismatched = tmp_path / "validation-payload-v1.schema.json"
    mismatched.write_text(
        json.dumps({"$id": "https://openai.com/codex/review-graph/validation-payload-v2.schema.json", "required": [], "type": "object"}), encoding="utf-8"
    )

    assert review["version"] == 1
    assert validation["version"] == 2
    with pytest.raises(ValueError, match="filename does not match"):
        _schema_reference(mismatched)


def test_planning_schema_reports_routing_decision_item_diagnostics() -> None:
    with pytest.raises(SchemaValidationError) as captured:
        require_schema({"routing_decisions": [{"catalog_id": "rust.errors", "unexpected": True}]}, SCHEMA_ROOT / "planning-input-v1.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    paths = {item["path"] for item in diagnostics}
    assert "$.routing_decisions[0].router_id" in paths
    assert "$.routing_decisions[0].unexpected" in paths


def test_planning_schema_reports_review_requirement_item_diagnostics() -> None:
    with pytest.raises(SchemaValidationError) as captured:
        require_schema({"review_requirements": [{"requirement_id": "rust.errors", "unexpected": True}]}, SCHEMA_ROOT / "planning-input-v1.schema.json")

    diagnostics = cast("list[dict[str, Any]]", captured.value.as_dict()["diagnostics"])
    paths = {item["path"] for item in diagnostics}
    assert "$.review_requirements[0].skill_id" in paths
    assert "$.review_requirements[0].unexpected" in paths


@pytest.mark.parametrize(("attempt", "retry_allowed"), [(1, True), (2, False)])
def test_compile_cli_allows_at_most_one_schema_retry(tmp_path: Path, capsys: pytest.CaptureFixture[str], attempt: int, retry_allowed: bool) -> None:
    request = tmp_path / f"request-{attempt}.json"
    request.write_text(json.dumps({"dispatch": {}, "handoff_attempt": attempt, "payload": {"status": "unknown", "unexpected": True}}), encoding="utf-8")

    result = main(
        [
            "compile-review",
            "--input",
            str(request),
            "--artifact",
            str(tmp_path / f"artifact-{attempt}.md"),
            "--metadata",
            str(tmp_path / f"metadata-{attempt}.json"),
        ]
    )

    diagnostic = json.loads(capsys.readouterr().err)
    assert result == 2
    assert diagnostic["handoff_attempt"] == attempt
    assert diagnostic["maximum_handoff_attempts"] == 2
    assert diagnostic["retry_allowed"] is retry_allowed
    assert len(diagnostic["diagnostics"]) > 2


def test_bootstrap_binds_capture_and_validation_fingerprints_without_field_renaming(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture = {
        "base_ref": None,
        "branch": "main",
        "capture_mode": "baseline",
        "captured_path_line_bounds": {STATE_FIXTURE: 3},
        "captured_scope_paths": [STATE_FIXTURE],
        "captured_worktree_fingerprint": "captured-worktree",
        "head": "head",
        "merge_base": None,
        "repository_root": str(SKILL_ROOT.parents[2]),
        "repository_state_fingerprint": "captured-repository",
        "requested_paths": [],
        "scope_fingerprint": "captured-scope",
        "status": [],
        "untracked_paths": [],
    }

    document = bootstrap_document(capture, _sparse_plan_document())
    require_schema(document, SCHEMA_ROOT / "planning-input-v1.schema.json")

    validation = document["validation_requirements"][0]
    assert validation["source_state"] == ["captured-scope", "captured-worktree", "captured-repository"]
    assert validation["captured_paths"] == [STATE_FIXTURE]
    assert document["captured_paths"] == [STATE_FIXTURE]

    capture_path = tmp_path / "capture.json"
    template_path = tmp_path / "template.json"
    bundle_path = tmp_path / "bootstrap.json"
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    template_path.write_text(json.dumps(_sparse_plan_document()), encoding="utf-8")
    assert bootstrap_main(["--capture", str(capture_path), "--input", str(template_path), "--output", str(bundle_path)]) == 0

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    command = shlex.split(bundle["materialization_input"]["state_verification_command"])
    assert Path(command[0]).is_absolute()
    assert Path(command[1]).is_absolute()
    assert Path(command[1]).stat().st_mode & 0o111
    assert subprocess.run(command, check=False, capture_output=True).returncode == 0  # noqa: S603 - bootstrap-owned absolute command.

    assert plan_main(["--input", str(bundle_path)]) == 0
    assert json.loads(capsys.readouterr().out) == bundle["plan"]


def test_advance_after_mutation_emits_one_recaptured_repair_epoch(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_test_git(git, "init", str(repository))
    _run_test_git(git, "-C", str(repository), "config", "user.email", "review@example.com")
    _run_test_git(git, "-C", str(repository), "config", "user.name", "Review Test")
    state_path = repository / "state.rs"
    state_path.write_text("pub fn state() {}\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "initial")
    state_path.write_text("pub fn state() { assert!(true); }\n", encoding="utf-8")
    new_capture = _scope_data(git, repository, "baseline", None, ())
    template = _sparse_plan_document()
    template["captured_paths"] = ["state.rs"]
    template["routing_overrides"][0]["review_surface"] = ["state.rs"]

    result = advance_after_mutation(
        {
            "artifact_store": str(tmp_path / "proof-store"),
            "authorization_after": "review-and-fix",
            "authorization_before": "review-only",
            "changed_paths": ["state.rs"],
            "new_capture": new_capture,
            "plan": _json_plan(_sparse_plan()),
            "planning_template": template,
            "repair_epoch": 1,
            "source_state": ["old-scope", "old-worktree", "old-repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )

    assert result["status"] == "advanced"
    assert result["repair_epoch"]["recapture_count"] == 1
    assert result["repair_epoch"]["fix_nodes"] == [{"mode": "fix", "node_id": "fix-epoch-001", "serialized": True}]
    assert {item["state"] for item in result["invalidated_nodes"]} == {"awaiting-replan"}
    assert result["newly_touched_paths"] == ["state.rs"]
    assert result["dispatch_set"]["source_state"] == result["new_source_state"]
    new_node_ids = {node["node_id"] for node in result["new_plan"]["actual_worker_nodes"]}
    new_evidence_ids = {entry["dispatch"]["evidence_id"] for entry in result["dispatch_set"]["dispatches"]}
    assert all(node_id.startswith("repair-epoch-001-") for node_id in new_node_ids)
    assert set(result["stale_evidence_ids"]).isdisjoint(new_evidence_ids)
    expectation = repository_review_proof_expectation(_graph_plan(json.loads(json.dumps(result["new_plan"]))), source_state=tuple(result["new_source_state"]))
    assert expectation.final_synthesis_identity == ("repair-epoch-001-repository-synthesis", "repository-production-review", "synthesis")


def test_compile_review_enforces_validator_owned_command_policy() -> None:
    dispatch = _dispatch()
    dispatch["command_policy"] = {
        "authorized_duplicate_commands": [],
        "prohibited_commands": ["just check-fast"],
        "validator_owned_commands": ["just check-fast"],
    }
    with pytest.raises(ValueError, match="owned by planned validators"):
        compile_review(
            {
                "dispatch": dispatch,
                "payload": {
                    "command_policy_attested": True,
                    "commands_executed": ["just check-fast"],
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


def test_compile_review_rejects_numeric_command_policy_attestation_without_policy() -> None:
    with pytest.raises(ValueError, match="must attest to the dispatched command policy"):
        compile_review(
            {
                "dispatch": _dispatch(),
                "payload": {
                    "changes": [],
                    "command_policy_attested": 1,
                    "commands_executed": [],
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


def test_compile_review_records_explicitly_authorized_duplicate_validation() -> None:
    dispatch = _dispatch()
    dispatch["command_policy"] = {
        "authorized_duplicate_commands": ["just check-fast"],
        "prohibited_commands": [],
        "validator_owned_commands": ["just check-fast"],
    }
    content, metadata = compile_review(
        {
            "dispatch": dispatch,
            "payload": {
                "changes": [],
                "command_policy_attested": True,
                "commands_executed": ["just check-fast"],
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

    assert content.startswith(b"# Review Node Result")
    assert metadata["normalized_record"]["commands_executed"] == ["just check-fast"]


def test_compile_review_rejects_non_catalog_handoff_identity() -> None:
    dispatch = _dispatch()
    dispatch["handoff_catalog_ids"] = ["rust.errors"]
    with pytest.raises(ValueError, match="unknown handoff catalog IDs"):
        compile_review(
            {
                "dispatch": dispatch,
                "payload": {
                    "changes": [],
                    "command_policy_attested": True,
                    "commands_executed": [],
                    "files_inspected": ["src/error.rs"],
                    "findings": [],
                    "handoffs": [
                        {
                            "catalog_id": "rust-error-variants",
                            "observed_trigger": "skill ID was supplied instead of a catalog ID",
                            "reason": "exercise the catalog boundary",
                            "scope": ["src/error.rs"],
                        }
                    ],
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
                    "changes": [],
                    "command_policy_attested": True,
                    "commands_executed": [],
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


def test_validation_workspace_audit_rejects_successful_run_with_unexpected_outputs() -> None:
    unit = ValidationUnit(
        node_id="validation-package",
        requirement_ids=("python-package",),
        source_state=("scope", "worktree", "repository"),
        commands=("uv build",),
        working_directories=(str(SKILL_ROOT.parents[2]),),
        environment="locked",
        toolchain="Python",
        features=("wheel",),
        platform="current",
        artifact_owner="python-dist",
        mutation_lock="isolated-output",
        request="build package",
        requested_scope="branch",
        capture_command="capture_scope.py --mode branch",
        captured_paths=("pyproject.toml",),
        requirement_plans=(("python-package", "graph", "package changed", "isolated", "wheel built", "30s", None),),
        dependency_policy="stop-on-failure",
        meaningful_skips=(),
        execution_strategy="sequential",
        independence_basis="none",
        planning_blocker=None,
        allowed_artifacts=(
            ValidationArtifact(path="dist", kind="build", repository_status="ignored", status_source="repository-rule", status_rule=".gitignore:dist/"),
        ),
        canonical_recipe="uv build",
        evidence_ids=(),
        required=True,
        baseline=False,
        expected_workspace_effects=("dist",),
    )
    digest = "sha256:" + "a" * 64
    dispatch = {
        "repository_root": str(SKILL_ROOT.parents[2]),
        "workspace_after": [
            {"digest": digest, "path": "dist/package.whl", "snapshot_mode": "content-sha256-v1", "status": "ignored"},
            {"digest": digest, "path": "src/generated.c", "snapshot_mode": "content-sha256-v1", "status": "tracked"},
        ],
        "workspace_before": [],
    }

    with pytest.raises(ValueError, match="unexpected workspace paths"):
        _validation_workspace_audit(dispatch, unit)

    dispatch["workspace_after"] = [{"digest": digest, "path": "dist/package.whl", "snapshot_mode": "content-sha256-v1", "status": "ignored"}]
    assert _validation_workspace_audit(dispatch, unit)["changed_paths"] == ["dist/package.whl"]

    dispatch["workspace_after"] = [{"digest": digest, "exists": False, "path": "dist/package.whl", "snapshot_mode": "content-sha256-v1", "status": "ignored"}]
    with pytest.raises(ValueError, match="inconsistent existence and snapshot identity"):
        _validation_workspace_audit(dispatch, unit)


def test_git_path_status_accepts_only_tracked_gitignore_rules(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_test_git(git, "init", str(repository))
    (repository / ".gitignore").write_text("generated/\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", ".gitignore")
    (repository / ".git" / "info" / "exclude").write_text("local-output/\n", encoding="utf-8")
    global_excludes = tmp_path / "global-excludes"
    global_excludes.write_text("global-output/\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "config", "core.excludesFile", str(global_excludes))

    assert _git_path_status(repository, repository / "generated" / "result.json") == "ignored"
    assert _git_path_status(repository, repository / "local-output" / "result.json") == "untracked"
    assert _git_path_status(repository, repository / "global-output" / "result.json") == "untracked"
    assert _git_path_status(repository, repository / "ordinary-output" / "result.json") == "untracked"


def test_runtime_snapshots_preserve_validation_artifact_digest_mode(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    isolation_root = tmp_path / "isolation"
    artifact_path = isolation_root / "target"
    nested_artifact_path = artifact_path / "debug" / "deps" / "result.json"
    repository_root.mkdir()
    unit = ValidationUnit(
        node_id="validation-runtime-artifact",
        requirement_ids=("runtime-artifact",),
        source_state=("scope", "worktree", "repository"),
        commands=("build",),
        working_directories=(str(isolation_root / "work"),),
        environment="locked",
        toolchain="test",
        features=(),
        platform="current",
        artifact_owner="validator",
        mutation_lock="isolated-output",
        request="produce one result",
        requested_scope="branch",
        capture_command="capture_scope.py --mode branch",
        captured_paths=("src/lib.rs",),
        requirement_plans=(("runtime-artifact", "graph", "build changed", "isolated", "result exists", "30s", None),),
        dependency_policy="stop-on-failure",
        meaningful_skips=(),
        execution_strategy="sequential",
        independence_basis="none",
        planning_blocker=None,
        allowed_artifacts=(
            ValidationArtifact(path=str(artifact_path), kind="report", repository_status="outside-repository", status_source="isolated-output-directory"),
        ),
        canonical_recipe="build",
        evidence_ids=(),
        required=True,
        baseline=False,
        expected_workspace_effects=(str(artifact_path),),
        requires_isolation=True,
        isolation_root=str(isolation_root),
    )
    dispatch = {
        "after_state": ["scope", "worktree", "repository"],
        "artifact_id": "artifact://validation-runtime-artifact",
        "before_state": ["scope", "worktree", "repository"],
        "evidence_id": "validation:runtime-artifact",
        "execution_location": "worker",
        "execution_profile": "grouped",
        "fresh_context": True,
        "reference_paths": [str(VALIDATOR_CONTRACT)],
        "repository_root": str(repository_root),
        "skill_path": str(VALIDATOR_SKILL),
        "state_verification_command": "capture_scope.py --mode branch",
        "validation_unit": json.loads(json.dumps(asdict(unit))),
        "worker_created": True,
    }
    before = capture_workspace_snapshot(dispatch)
    nested_artifact_path.parent.mkdir(parents=True)
    nested_artifact_path.write_text('{"passed":true}\n', encoding="utf-8")
    after = capture_workspace_snapshot(dispatch)
    dispatch["workspace_before"] = before["records"]
    dispatch["workspace_after"] = after["records"]
    payload = {
        "executions": [
            {
                "artifact_paths": [str(artifact_path)],
                "command": "build",
                "elapsed": "1s",
                "evidence": "result created",
                "executor": "worker validation-runtime-artifact",
                "exit_code": 0,
                "result": "passed",
                "working_directory": str(isolation_root / "work"),
            }
        ],
        "limitations": [],
        "status": "passed",
    }

    _content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})

    assert before["records"][0]["exists"] is False
    assert after["records"][0]["exists"] is True
    assert metadata["normalized_record"]["artifacts"][0]["artifact_digest"] == after["records"][0]["digest"]
    assert metadata["normalized_record"]["artifacts"][0]["artifact_digest_mode"] == "bounded-directory-metadata-v3"
    assert metadata["workspace_audit"]["snapshot_modes"] == {str(artifact_path): "bounded-directory-metadata-v3"}


def test_runtime_snapshot_bounds_known_build_trees_without_reading_file_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository_root = tmp_path / "repository"
    build_root = tmp_path / "isolated" / "target"
    payload_path = build_root / "debug" / "deps" / "large-artifact"
    repository_root.mkdir()
    payload_path.parent.mkdir(parents=True)
    payload_path.write_bytes(b"artifact bytes must not be read")
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(), expected_workspace_effects=(str(build_root),))
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == payload_path:
            msg = "bounded workspace snapshots must not hash cache/build file contents"
            raise AssertionError(msg)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    snapshot = capture_workspace_snapshot({"repository_root": str(repository_root), "validation_unit": json.loads(json.dumps(asdict(unit)))})

    assert snapshot["records"] == [
        {
            "digest": snapshot["records"][0]["digest"],
            "exists": True,
            "path": str(build_root),
            "snapshot_mode": "bounded-directory-metadata-v3",
            "status": "outside-repository",
        }
    ]


def test_bounded_workspace_snapshot_selects_entries_deterministically_before_truncation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository_root = tmp_path / "repository"
    build_root = tmp_path / "target"
    repository_root.mkdir()
    build_root.mkdir()
    for ordinal in range(300):
        (build_root / f"artifact-{ordinal:03d}").write_text(str(ordinal), encoding="utf-8")
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(), expected_workspace_effects=(str(build_root),))
    dispatch = {"repository_root": str(repository_root), "validation_unit": json.loads(json.dumps(asdict(unit)))}
    real_scandir = os.scandir
    with real_scandir(build_root) as stream:
        entries = list(stream)

    class OrderedScandir:
        def __init__(self, ordered_entries: list[os.DirEntry[str]]) -> None:
            self.ordered_entries = ordered_entries

        def __enter__(self) -> object:
            return iter(self.ordered_entries)

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(os, "scandir", lambda _path: OrderedScandir(entries))
    forward = capture_workspace_snapshot(dispatch)
    monkeypatch.setattr(os, "scandir", lambda _path: OrderedScandir(list(reversed(entries))))
    reverse = capture_workspace_snapshot(dispatch)

    assert forward["records"][0]["digest"] == reverse["records"][0]["digest"]


def test_bounded_workspace_snapshot_hashes_names_outside_metadata_sample(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    build_root = tmp_path / "target"
    repository_root.mkdir()
    build_root.mkdir()
    for ordinal in range(300):
        (build_root / f"artifact-{ordinal:03d}").write_text(str(ordinal), encoding="utf-8")
    fixed_timestamp_ns = 1_700_000_000_000_000_000
    os.utime(build_root, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(), expected_workspace_effects=(str(build_root),))
    dispatch = {"repository_root": str(repository_root), "validation_unit": json.loads(json.dumps(asdict(unit)))}
    before = capture_workspace_snapshot(dispatch)

    (build_root / "artifact-299").rename(build_root / "artifact-399")
    os.utime(build_root, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    after = capture_workspace_snapshot(dispatch)

    assert before["records"][0]["digest"] != after["records"][0]["digest"]


def test_bounded_workspace_snapshot_hashes_metadata_outside_diagnostic_sample(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    build_root = tmp_path / "target"
    repository_root.mkdir()
    build_root.mkdir()
    for ordinal in range(300):
        (build_root / f"artifact-{ordinal:03d}").write_text(str(ordinal), encoding="utf-8")
    fixed_timestamp_ns = 1_700_000_000_000_000_000
    os.utime(build_root, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(), expected_workspace_effects=(str(build_root),))
    dispatch = {"repository_root": str(repository_root), "validation_unit": json.loads(json.dumps(asdict(unit)))}
    before = capture_workspace_snapshot(dispatch)

    (build_root / "artifact-299").write_text("changed outside the diagnostic sample", encoding="utf-8")
    os.utime(build_root, ns=(fixed_timestamp_ns, fixed_timestamp_ns))
    after = capture_workspace_snapshot(dispatch)

    assert before["records"][0]["digest"] != after["records"][0]["digest"]


def test_recursive_workspace_snapshot_bounds_nested_build_trees_without_reading_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository_root = tmp_path / "repository"
    workspace_root = tmp_path / "artifacts"
    bounded_root = workspace_root / "target"
    bounded_payload = bounded_root / "large-artifact"
    ordinary_payload = workspace_root / "ordinary.txt"
    repository_root.mkdir()
    bounded_root.mkdir(parents=True)
    bounded_payload.write_bytes(b"bounded bytes must not be read")
    ordinary_payload.write_bytes(b"ordinary bytes remain content hashed")
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], allowed_artifacts=(), expected_workspace_effects=(str(workspace_root),))
    dispatch = {"repository_root": str(repository_root), "validation_unit": json.loads(json.dumps(asdict(unit)))}
    original_read_bytes = Path.read_bytes
    read_paths: list[Path] = []

    def guarded_read_bytes(path: Path) -> bytes:
        read_paths.append(path)
        if path.is_relative_to(bounded_root):
            msg = "recursive workspace snapshots must not hash nested cache/build file contents"
            raise AssertionError(msg)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    before = capture_workspace_snapshot(dispatch)
    bounded_payload.write_bytes(b"changed bounded metadata")
    after_bounded_change = capture_workspace_snapshot(dispatch)
    ordinary_payload.write_bytes(b"changed ordinary content")
    after_ordinary_change = capture_workspace_snapshot(dispatch)

    assert before["records"][0]["snapshot_mode"] == "recursive-content-sha256-v2"
    assert ordinary_payload in read_paths
    assert bounded_payload not in read_paths
    assert before["records"][0]["digest"] != after_bounded_change["records"][0]["digest"]
    assert after_bounded_change["records"][0]["digest"] != after_ordinary_change["records"][0]["digest"]


@pytest.mark.parametrize(("entry_kind", "content_change_detected"), [("file", True), ("directory-symlink", False)])
def test_recursive_workspace_digest_preserves_non_directory_bounded_names(tmp_path: Path, entry_kind: str, content_change_detected: bool) -> None:
    workspace_root = tmp_path / "artifacts"
    workspace_root.mkdir()
    entry = workspace_root / "target"
    if entry_kind == "file":
        entry.write_bytes(b"initial")
        changed_path = entry
    else:
        external_root = tmp_path / "external"
        external_root.mkdir()
        changed_path = external_root / "payload"
        changed_path.write_bytes(b"initial")
        entry.symlink_to(external_root, target_is_directory=True)
    exists, before, before_mode = _workspace_content_digest(workspace_root)

    changed_path.write_bytes(b"changed")
    _exists, after, after_mode = _workspace_content_digest(workspace_root)

    assert exists
    assert before_mode == after_mode == "recursive-content-sha256-v2"
    assert (before != after) is content_change_detected


def test_isolated_validation_workspace_audit_binds_artifacts_and_changes_to_root(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    isolation_root = tmp_path / "isolation"
    unrelated_root = tmp_path / "unrelated"
    artifact_root = isolation_root / "artifacts"
    digest = "sha256:" + "a" * 64
    unit = ValidationUnit(
        node_id="validation-isolated",
        requirement_ids=("isolated",),
        source_state=("scope", "worktree", "repository"),
        commands=("build",),
        working_directories=(str(isolation_root / "work"),),
        environment="locked",
        toolchain="Python",
        features=(),
        platform="current",
        artifact_owner="isolated",
        mutation_lock="isolated-output",
        request="build outside the repository",
        requested_scope="branch",
        capture_command="capture_scope.py --mode branch",
        captured_paths=("pyproject.toml",),
        requirement_plans=(("isolated", "graph", "package changed", "isolated", "artifact built", "30s", None),),
        dependency_policy="stop-on-failure",
        meaningful_skips=(),
        execution_strategy="sequential",
        independence_basis="none",
        planning_blocker=None,
        allowed_artifacts=(
            ValidationArtifact(path=str(artifact_root), kind="build", repository_status="outside-repository", status_source="isolated-output-directory"),
        ),
        canonical_recipe="build",
        evidence_ids=(),
        required=True,
        baseline=False,
        requires_isolation=True,
        isolation_root=str(isolation_root),
    )
    artifact_path = artifact_root / "package.whl"
    dispatch = {
        "repository_root": str(repository_root),
        "workspace_after": [{"digest": digest, "path": str(artifact_path), "snapshot_mode": "content-sha256-v1", "status": "outside-repository"}],
        "workspace_before": [],
    }

    assert _validation_workspace_audit(dispatch, unit)["changed_paths"] == [str(artifact_path)]

    unrelated_artifact = replace(unit.allowed_artifacts[0], path=str(unrelated_root / "artifacts"))
    with pytest.raises(ValueError, match="artifacts must be under the dispatched isolation root"):
        _validation_workspace_audit({**dispatch, "workspace_after": []}, replace(unit, allowed_artifacts=(unrelated_artifact,)))

    unrelated_path = unrelated_root / "package.whl"
    with pytest.raises(ValueError, match="changed workspace paths must be under the dispatched isolation root"):
        _validation_workspace_audit(
            {
                **dispatch,
                "workspace_after": [{"digest": digest, "path": str(unrelated_path), "snapshot_mode": "content-sha256-v1", "status": "outside-repository"}],
            },
            replace(unit, allowed_artifacts=(), expected_workspace_effects=(str(unrelated_path),)),
        )


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
    assert by_id["rust.concurrency"].disposition == "selected"
    assert by_id["rust.concurrency"].review_surface == ("src/lib.rs",)
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


def test_routing_regression_fixtures_enforce_guarded_docs_and_scripts_test_paths() -> None:
    fixture = Path(__file__).with_name("fixtures") / "routing_regressions.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]

    for case in cases:
        projection = build_routing_projection_document(
            {"captured_paths": case["paths"], "consulted_routers": case["consulted_routers"]}, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,)
        )
        projected = {entry["catalog_id"]: entry for entry in projection["entries"]}
        for catalog_id, expected_matches in case["expected_matches"].items():
            assert projected[catalog_id]["matched_paths"] == expected_matches, case["id"]


def test_sparse_mixed_lockfile_fixture_selects_every_projection_match_and_coalesces_aliases() -> None:
    fixture = Path(__file__).with_name("fixtures") / "sparse_mixed_lockfiles.json"
    document = json.loads(fixture.read_text(encoding="utf-8"))
    plan = plan_from_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    projection = build_routing_projection_document(document, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))

    matched_leaf_ids = {entry["catalog_id"] for entry in projection["entries"] if entry["target_kind"] == "leaf" and entry["matched_paths"]}
    selected_ids = {decision.catalog_id for decision in plan.routing_decisions if decision.disposition == "selected"}
    assert matched_leaf_ids <= selected_ids
    assert {"rust.cargo", "python.build", "docs.repository", "docs.rust-api", "rust.api-docs"} <= selected_ids
    requirement_nodes = dict(plan.requirement_to_node)
    assert requirement_nodes["rust.api-docs"] == requirement_nodes["docs.rust-api"]
    alias_node = requirement_nodes["rust.api-docs"]
    assert alias_node in next(node for node in plan.actual_worker_nodes if node.node_id == "rust-synthesis").predecessors
    assert alias_node in next(node for node in plan.actual_worker_nodes if node.node_id == "repository-synthesis").predecessors


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
    assert {entry["compiler_operation"] for entry in result["dispatches"]} == {"compile-review", "compile-validation"}
    assert {entry["journal_operation"] for entry in result["dispatches"]} == {"journal-append"}
    audit_dispatch = next(entry["dispatch"] for entry in result["dispatches"] if entry["result_contract"] == "compact-review")
    validation_dispatch = next(entry["dispatch"] for entry in result["dispatches"] if entry["result_contract"] == "compact-validation")
    assert audit_dispatch["payload_schema"]["id"].endswith("review-payload-v1.schema.json")
    assert validation_dispatch["payload_schema"]["id"].endswith("validation-payload-v2.schema.json")
    assert audit_dispatch["payload_schema"]["version"] == 1
    assert validation_dispatch["payload_schema"]["version"] == 2
    assert "command_policy_attested" in audit_dispatch["payload_schema"]["required_fields"]
    assert audit_dispatch["command_policy"]["validator_owned_commands"] == ["true"]
    assert str(SKILL_ROOT.parents[2] / "AGENTS.md") in audit_dispatch["instruction_paths"]
    assert all(entry["worker_prompt"] for entry in result["dispatches"])
    assert all("persist-worker-payload" in entry["worker_prompt"] for entry in result["dispatches"])
    assert all(Path(entry["worker_payload_contract_path"]).is_file() for entry in result["dispatches"])

    lifecycle_document = {
        "current_source_state": ["scope", "worktree", "repository"],
        "plan": _json_plan(plan),
        "source_state": ["scope", "worktree", "repository"],
    }
    initial = next_ready_nodes(lifecycle_document, journal_events=(), dispatch_set=result)
    assert set(initial["ready_node_ids"]) == {node.node_id for node in plan.actual_worker_nodes if not node.predecessors}
    assert {entry["node_id"] for entry in initial["ready_dispatches"]} == set(initial["ready_node_ids"])
    stale = dict(lifecycle_document)
    stale["current_source_state"] = ["scope", "worktree", "changed-repository"]
    with pytest.raises(ValueError, match="current recapture differs"):
        next_ready_nodes(stale, journal_events=(), dispatch_set=result)

    journal = tmp_path / "execution.jsonl"
    started = initial["ready_node_ids"][0]
    append_journal_event(journal, lifecycle_document, JournalEventRequest(started, "in-flight"))
    events, _state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    after_start = next_ready_nodes(lifecycle_document, journal_events=events, dispatch_set=result)
    assert started not in after_start["ready_node_ids"]
    assert after_start["lifecycle"]["in_flight_node_ids"] == [started]


def test_validator_prompt_exposes_nested_required_shape_and_minimal_response_compiles(tmp_path: Path) -> None:
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
    entry = next(item for item in materialized["dispatches"] if item["result_contract"] == "compact-validation")
    dispatch = deepcopy(entry["dispatch"])
    execution_shape = dispatch["payload_schema"]["required_shape"]["executions"][0]
    unit = dispatch["validation_unit"]
    payload = {
        "executions": [
            {
                "artifact_paths": [],
                "command": command,
                "elapsed": "0s",
                "evidence": "command completed",
                "executor": f"worker {dispatch['node_id']}",
                "exit_code": 0,
                "result": "passed",
                "working_directory": working_directory,
            }
            for command, working_directory in zip(unit["commands"], unit["working_directories"], strict=True)
        ],
        "limitations": [],
        "status": "passed",
    }
    dispatch.update({"after_state": ["scope", "worktree", "repository"], "before_state": ["scope", "worktree", "repository"]})

    assert set(execution_shape) == {"artifact_paths", "command", "elapsed", "evidence", "executor", "exit_code", "result", "working_directory"}
    assert '"artifact_paths":["string"]' in entry["worker_prompt"]
    require_schema(payload, SCHEMA_ROOT / "validation-payload-v2.schema.json")
    content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
    assert content.startswith(b"# Validation Result\n")
    assert metadata["evidence"]["status"] == "passed"


def test_late_handoff_replan_reserves_reused_ids_and_binds_surface_readiness(tmp_path: Path) -> None:
    plan = _late_handoff_replan()
    audit = next(node for node in plan.actual_worker_nodes if node.mode == "audit")
    validation = next(node for node in plan.actual_worker_nodes if node.mode == "validation")
    rust_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "rust-synthesis")
    python_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "python-synthesis")
    repository_synthesis = next(node for node in plan.actual_worker_nodes if node.node_id == "repository-synthesis")

    assert audit.node_id == "audit-003"
    assert validation.node_id in rust_synthesis.predecessors
    assert {audit.node_id, validation.node_id} <= set(python_synthesis.predecessors)
    assert {rust_synthesis.node_id, python_synthesis.node_id, validation.node_id} <= set(repository_synthesis.predecessors)

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
    dispatches = {entry["node_id"]: entry["dispatch"] for entry in materialized["dispatches"]}
    assert {"review:audit-001", "review:audit-002"} <= set(dispatches["rust-synthesis"]["predecessor_evidence_ids"])
    assert {"review:audit-001", "review:audit-002"} <= set(dispatches["repository-synthesis"]["predecessor_evidence_ids"])
    assert f"review:{audit.node_id}" in dispatches["python-synthesis"]["predecessor_evidence_ids"]
    assert f"validation:{validation.node_id}" in dispatches["python-synthesis"]["predecessor_evidence_ids"]


def test_next_ready_creates_runtime_managed_output_directory(tmp_path: Path) -> None:
    plan = _sparse_plan()
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(tmp_path / "artifacts"),
            "authorization": "review-only",
            "plan": lifecycle["plan"],
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": lifecycle["source_state"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    capture = {"captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository", "scope_fingerprint": "scope"}
    input_path = tmp_path / "lifecycle.json"
    dispatch_path = tmp_path / "dispatches.json"
    capture_path = tmp_path / "capture.json"
    input_path.write_text(json.dumps(lifecycle), encoding="utf-8")
    dispatch_path.write_text(json.dumps(dispatch_set), encoding="utf-8")
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    output_directory = tmp_path / "missing" / "ready"

    result = main(
        [
            "next-ready",
            "--input",
            str(input_path),
            "--journal",
            str(tmp_path / "execution.jsonl"),
            "--dispatches",
            str(dispatch_path),
            "--current-capture",
            str(capture_path),
            "--output-dir",
            str(output_directory),
        ]
    )

    assert result == 0
    assert (output_directory / "next-ready.000000.json").is_file()


def test_dispatch_materialization_reports_validation_node_without_unit(tmp_path: Path) -> None:
    plan = _sparse_plan()
    malformed = replace(plan, coalesced_validation_units=())

    with pytest.raises(ValueError, match="validation node has no coalesced unit"):
        materialize_dispatches(
            {
                "artifact_store": str(tmp_path),
                "authorization": "review-only",
                "plan": _json_plan(malformed),
                "repository_root": str(SKILL_ROOT.parents[2]),
                "source_state": ["scope", "worktree", "repository"],
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )


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
    assert entry["compiler_operation"] == "compile-independent-review"
    assert entry["dispatch"]["planned_path_line_bounds"] == [[STATE_FIXTURE, 3]]
    _assert_compact_dispatches(result["dispatches"])


def test_exact_overlap_leaves_share_only_trusted_read_only_observations(tmp_path: Path) -> None:
    plan = _sparse_plan()
    audit = next(node for node in plan.actual_worker_nodes if node.mode == "audit")
    observer = replace(audit, node_id="audit-shared-observer", requirement_ids=("shared-observer",))
    shared_plan = replace(plan, actual_worker_nodes=(*plan.actual_worker_nodes, observer), complete_node_count=plan.complete_node_count + 1)
    result = materialize_dispatches(
        {
            "artifact_store": str(tmp_path),
            "authorization": "review-only",
            "plan": _json_plan(shared_plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    by_id = {entry["node_id"]: entry["dispatch"] for entry in result["dispatches"]}
    producer = by_id[audit.node_id]["shared_inspection_evidence"]
    consumer = by_id[observer.node_id]["shared_inspection_evidence"]

    assert producer == consumer
    assert producer["observation_digest"].startswith("sha256:")
    assert producer["observations"] == [
        {
            "byte_count": (SKILL_ROOT.parents[2] / STATE_FIXTURE).stat().st_size,
            "content_digest": producer["observations"][0]["content_digest"],
            "line_count": 3,
            "path": STATE_FIXTURE,
        }
    ]
    assert producer["observations"][0]["content_digest"].startswith("sha256:")
    assert Path(producer["artifact_path"]).is_file()

    independent = materialize_dispatches(
        {
            "artifact_store": str(tmp_path / "independent"),
            "authorization": "review-only",
            "inspection_profile": "independent-source",
            "plan": _json_plan(shared_plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    assert all("shared_inspection_evidence" not in entry["dispatch"] for entry in independent["dispatches"])


def test_compile_independent_review_wraps_native_result_and_reloads_evidence(tmp_path: Path) -> None:
    skill_path = SKILL_ROOT / "repository-independent-review" / "SKILL.md"
    change_target = f"git diff -- {STATE_FIXTURE}"
    dispatch = {
        "adversarial_checks": ["fallback absence and failure", "platform seams", "parser suffixes and error branches", "unexpected exception types"],
        "after_state": ["scope", "worktree", "repository"],
        "artifact_id": "artifact://independent",
        "authorization": "review-only",
        "before_state": ["scope", "worktree", "repository"],
        "change_target": change_target,
        "evidence_id": "review:independent",
        "execution_location": "worker",
        "execution_profile": "grouped",
        "fresh_context": True,
        "handoff_catalog_ids": ["rust.invariants"],
        "mode": "independent-review",
        "node_id": "independent",
        "planned_path_line_bounds": [[STATE_FIXTURE, 3]],
        "planned_paths": [STATE_FIXTURE],
        "reference_paths": [],
        "requirement_ids": ["repo.independent"],
        "selection_reason": "concrete change target",
        "skill_id": "repository-independent-review",
        "skill_path": str(skill_path),
        "source_state": ["scope", "worktree", "repository"],
        "worker_created": True,
    }
    checks = "\n".join(f"- Inspected: {check}" for check in dispatch["adversarial_checks"])
    native = f"""# Repository Independent Review

## Scope Inspected

- Change target: {change_target}
- Files: {STATE_FIXTURE}
- Branches: captured change target
- Boundary cases: dispatched adversarial checks
- Tests: planned validator evidence

## Findings

No findings.

## No-Finding Evidence

{checks}

## Routing Handoffs

none

## Fingerprint Proof

- Expected:
  - Scope fingerprint: scope
  - Worktree fingerprint: worktree
  - Repository state fingerprint: repository
- Before:
  - Scope fingerprint: scope
  - Worktree fingerprint: worktree
  - Repository state fingerprint: repository
- After:
  - Scope fingerprint: scope
  - Worktree fingerprint: worktree
  - Repository state fingerprint: repository

## Git State

- Source-controlled files changed: none
- Git state mutated: no
""".encode()

    content, metadata = compile_independent_review({"dispatch": dispatch, "limitations": [], "status": "no-findings"}, native)
    mutated_native = native.replace(b"- Git state mutated: no", b"- Git state mutated: yes", 1)
    with pytest.raises(ValueError, match="native state proof failed validation"):
        compile_independent_review({"dispatch": dispatch, "limitations": [], "status": "no-findings"}, mutated_native)

    stale_dispatch = deepcopy(dispatch)
    stale_dispatch["before_state"] = ["stale-scope", "worktree", "repository"]
    stale_native = native.replace(b"- Before:\n  - Scope fingerprint: scope", b"- Before:\n  - Scope fingerprint: stale-scope", 1)
    with pytest.raises(ValueError, match="observed fingerprints differ"):
        compile_independent_review({"dispatch": stale_dispatch, "limitations": [], "status": "no-findings"}, stale_native)

    artifact_path = tmp_path / "independent.md"
    metadata_path = tmp_path / "independent.json"
    artifact_path.write_bytes(content)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    bundle = build_synthesis_bundle(
        {"source_state": ["scope", "worktree", "repository"], "sources": [{"artifact_path": str(artifact_path), "metadata_path": str(metadata_path)}]}
    )

    assert b"## Review Graph Envelope" in content
    assert b"## Machine Evidence" in content
    assert metadata["native_input_digest"].startswith("sha256:")
    assert bundle["records"][0]["mode"] == "independent-review"

    blocked_content, blocked_metadata = compile_independent_review(
        {"dispatch": dispatch, "limitations": ["target; unavailable", "retry exhausted"], "status": "blocked"}, native
    )
    blocked_artifact_path = tmp_path / "blocked-independent.md"
    blocked_metadata_path = tmp_path / "blocked-independent.json"
    blocked_artifact_path.write_bytes(blocked_content)
    blocked_metadata_path.write_text(json.dumps(blocked_metadata), encoding="utf-8")
    blocked_bundle = build_synthesis_bundle(
        {
            "source_state": ["scope", "worktree", "repository"],
            "sources": [{"artifact_path": str(blocked_artifact_path), "metadata_path": str(blocked_metadata_path)}],
        }
    )
    assert blocked_metadata["normalized_record"]["limitations"] == ["target; unavailable; retry exhausted"]
    assert blocked_bundle["records"][0]["limitations"] == ["target; unavailable; retry exhausted"]


def test_independent_native_example_compiles_verbatim_and_aggregates_contract_errors() -> None:
    dispatch = {
        "adversarial_checks": ["fallback absence and failure", "platform seams", "parser suffixes and error branches", "unexpected exception types"],
        "after_state": ["scope", "worktree", "repository"],
        "artifact_id": "artifact://independent-example",
        "authorization": "review-only",
        "before_state": ["scope", "worktree", "repository"],
        "change_target": f"git diff -- {STATE_FIXTURE}",
        "evidence_id": "review:independent-example",
        "execution_location": "worker",
        "execution_profile": "grouped",
        "fresh_context": True,
        "handoff_catalog_ids": ["rust.invariants"],
        "mode": "independent-review",
        "node_id": "independent-example",
        "planned_path_line_bounds": [[STATE_FIXTURE, 3]],
        "planned_paths": [STATE_FIXTURE],
        "reference_paths": [],
        "requirement_ids": ["repo.independent"],
        "selection_reason": "concrete change target",
        "skill_id": "repository-independent-review",
        "skill_path": str(SKILL_ROOT / "repository-independent-review" / "SKILL.md"),
        "source_state": ["scope", "worktree", "repository"],
        "worker_created": True,
    }
    native = INDEPENDENT_NATIVE_EXAMPLE.read_bytes()

    content, metadata = compile_independent_review({"dispatch": dispatch, "limitations": [], "status": "no-findings"}, native)

    assert metadata["native_input_digest"].startswith("sha256:")
    assert content.startswith(native.rstrip() + b"\n\n")

    malformed = (
        native.replace(f"`{STATE_FIXTURE}`".encode(), b"`wrong.rs`")
        .replace(b"- Inspected: platform seams\n", b"")
        .replace(b"## Routing Handoffs\n\nnone", b"## Routing Handoffs\n\nmalformed")
        .replace(b"- Git state mutated: no", b"- Git state mutated: yes")
    )
    with pytest.raises(ValueError, match="contract validation") as raised:
        compile_independent_review({"dispatch": dispatch, "limitations": [], "status": "no-findings"}, malformed)
    diagnostic = str(raised.value)
    assert "files do not equal" in diagnostic
    assert "platform seams" in diagnostic
    assert "must contain Catalog ID records" in diagnostic
    assert "native state proof failed validation" in diagnostic


@pytest.mark.parametrize("writer", ["direct", "atomic"])
def test_create_once_writers_reject_preexisting_symlinks_without_touching_target(tmp_path: Path, writer: str) -> None:
    content = b"accepted payload"
    target = tmp_path / "target"
    target.write_bytes(content)
    target.chmod(0o600)
    destination = tmp_path / f"{writer}.artifact"
    destination.symlink_to(target)
    write = partial(_write_bytes_atomically_once, mode=0o444) if writer == "atomic" else _write_bytes_once

    with pytest.raises(ValueError, match="regular non-symlink file"):
        write(destination, content)

    assert destination.is_symlink()
    assert target.read_bytes() == content
    assert target.stat().st_mode & 0o777 == 0o600
    assert not tuple(tmp_path.glob(f".{destination.name}.*.tmp"))


@pytest.mark.parametrize("writer", ["direct", "atomic"])
def test_create_once_writers_reject_nonregular_targets(tmp_path: Path, writer: str) -> None:
    destination = tmp_path / f"{writer}.artifact"
    destination.mkdir()
    write = partial(_write_bytes_atomically_once, mode=0o444) if writer == "atomic" else _write_bytes_once

    with pytest.raises(ValueError, match="regular non-symlink file"):
        write(destination, b"accepted payload")

    assert destination.is_dir()
    assert not tuple(tmp_path.glob(f".{destination.name}.*.tmp"))


def test_compile_node_survives_context_compaction_by_reading_bound_worker_payload(tmp_path: Path) -> None:
    plan = _sparse_plan()
    source_state = ["scope", "worktree", "repository"]
    artifact_store = tmp_path / "nested" / "artifacts"
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(artifact_store),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": source_state,
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    entry = next(
        candidate
        for candidate in dispatch_set["dispatches"]
        if candidate["result_contract"] == "compact-review" and not candidate["dispatch"]["predecessor_evidence_ids"]
    )
    payload = {
        "changes": [],
        "command_policy_attested": True,
        "commands_executed": [],
        "files_inspected": entry["dispatch"]["owned_paths"],
        "findings": [],
        "handoffs": [],
        "limitations": [],
        "nearby_contract_owners": [],
        "status": "no-findings",
        "validation_requirements": [],
    }
    payload_bytes = (json.dumps(payload, indent=2) + "\n").encode()
    lifecycle = {"plan": _json_plan(plan), "source_state": source_state}
    capture = {"captured_worktree_fingerprint": source_state[1], "repository_state_fingerprint": source_state[2], "scope_fingerprint": source_state[0]}
    lifecycle_path = tmp_path / "lifecycle.json"
    dispatch_path = tmp_path / "dispatches.json"
    capture_path = tmp_path / "capture.json"
    payload_path = Path(entry["worker_payload_path"])
    payload_candidate_path = Path(entry["worker_payload_candidate_path"])
    output_path = tmp_path / "compile.json"
    journal_path = tmp_path / "journal" / "execution.jsonl"
    lifecycle_path.write_text(json.dumps(lifecycle), encoding="utf-8")
    dispatch_path.write_text(json.dumps(dispatch_set), encoding="utf-8")
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    payload_candidate_path.write_bytes(payload_bytes)
    assert main(["persist-worker-payload", "--input", entry["worker_payload_contract_path"], "--payload", str(payload_candidate_path)]) == 0

    result = main(
        [
            "compile-node",
            "--input",
            str(lifecycle_path),
            "--dispatches",
            str(dispatch_path),
            "--node-id",
            entry["node_id"],
            "--before-capture",
            str(capture_path),
            "--after-capture",
            str(capture_path),
            "--journal",
            str(journal_path),
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    output = json.loads(output_path.read_text(encoding="utf-8"))
    sealed_payload_path = Path(output["worker_payload_path"])
    assert sealed_payload_path != payload_path
    assert sealed_payload_path.read_bytes() == payload_bytes
    assert sealed_payload_path.stat().st_mode & 0o222 == 0
    metadata = json.loads(Path(output["metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["worker_payload_byte_count"] == len(payload_bytes)
    assert metadata["worker_payload_path"] == str(sealed_payload_path)
    assert metadata["worker_payload_staging_path"] == str(payload_path)
    events, lifecycle_state, _head = read_execution_journal(journal_path, plan=plan, source_state=cast("tuple[str, str, str]", tuple(source_state)))
    assert len(events) == 1
    assert lifecycle_state[entry["node_id"]] == "accepted"
    source = {"artifact_path": output["artifact_path"], "metadata_path": output["metadata_path"]}
    build_synthesis_bundle({"source_state": source_state, "sources": [source]})

    replacement_bytes = (json.dumps({**payload, "limitations": ["late replacement"]}, indent=2) + "\n").encode()
    payload_candidate_path.write_bytes(replacement_bytes)
    assert main(["persist-worker-payload", "--input", entry["worker_payload_contract_path"], "--payload", str(payload_candidate_path)]) == 0
    assert payload_path.read_bytes() == replacement_bytes
    assert sealed_payload_path.read_bytes() == payload_bytes
    build_synthesis_bundle({"source_state": source_state, "sources": [source]})


def test_persist_worker_payload_preserves_valid_target_when_validation_or_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _sparse_plan()
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(tmp_path / "artifacts"),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(SKILL_ROOT.parents[2]),
            "source_state": ["scope", "worktree", "repository"],
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    entry = next(candidate for candidate in dispatch_set["dispatches"] if candidate["result_contract"] == "compact-review")
    target = Path(entry["worker_payload_path"])
    candidate = Path(entry["worker_payload_candidate_path"])
    valid_payload = {
        "changes": [],
        "command_policy_attested": True,
        "commands_executed": [],
        "files_inspected": entry["dispatch"]["owned_paths"],
        "findings": [],
        "handoffs": [],
        "limitations": [],
        "nearby_contract_owners": [],
        "status": "no-findings",
        "validation_requirements": [],
    }
    valid_bytes = (json.dumps(valid_payload, indent=2) + "\n").encode()
    candidate.write_bytes(valid_bytes)
    command = ["persist-worker-payload", "--input", entry["worker_payload_contract_path"], "--payload", str(candidate)]
    assert main(command) == 0
    capsys.readouterr()

    candidate.write_bytes(b"{}\n")
    assert main(command) == 2
    assert target.read_bytes() == valid_bytes
    assert candidate.read_bytes() == b"{}\n"
    capsys.readouterr()

    replacement = {**valid_payload, "limitations": ["replacement"]}
    candidate.write_bytes((json.dumps(replacement, indent=2) + "\n").encode())

    def fail_replace(_source: Path, _target: Path) -> Path:
        msg = "simulated publication failure"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    assert main(command) == 2
    assert target.read_bytes() == valid_bytes
    assert candidate.is_file()


def test_compact_branch_runs_from_bootstrap_through_journal_and_final_proof(tmp_path: Path) -> None:  # noqa: PLR0915
    git = shutil.which("git")
    assert git is not None
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_test_git(git, "init", str(repository))
    _run_test_git(git, "-C", str(repository), "config", "user.email", "review@example.com")
    _run_test_git(git, "-C", str(repository), "config", "user.name", "Review Test")
    state_path = repository / "state.rs"
    state_path.write_text("pub fn state() {}\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "initial")
    state_path.write_text("pub fn state() { assert!(true); }\n", encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "change state")
    capture = _scope_data(git, repository, "branch", "HEAD~1", ())
    template = _sparse_plan_document()
    template.update({"change_target": "git diff HEAD~1...HEAD -- state.rs", "concrete_change_target": True, "scope_mode": "branch"})
    template["captured_paths"] = ["state.rs"]
    template["routing_overrides"][0]["review_surface"] = ["state.rs"]
    validation_template = template["validation_requirements"][0]
    validation_template["capture_command"] = "capture_scope.py --mode branch --base HEAD~1"
    validation_template["captured_paths"] = ["state.rs"]
    validation_template["working_directories"] = [str(repository)]
    planning = bootstrap_document(capture, template)
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    source_state = cast(
        "tuple[str, str, str]", (capture["scope_fingerprint"], capture["captured_worktree_fingerprint"], capture["repository_state_fingerprint"])
    )
    proof_store = tmp_path / "proof-store"
    proof_store.mkdir()
    dispatch_set = materialize_dispatches(
        {
            "artifact_store": str(proof_store),
            "authorization": "review-only",
            "plan": _json_plan(plan),
            "repository_root": str(repository),
            "source_state": list(source_state),
            "state_verification_command": "capture_scope.py --mode branch --base HEAD~1",
        }
    )
    sources_by_node: dict[str, dict[str, str]] = {}
    for entry in dispatch_set["dispatches"]:
        dispatch = deepcopy(entry["dispatch"])
        dispatch.update({"after_state": list(source_state), "before_state": list(source_state)})
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
            require_schema(payload, SCHEMA_ROOT / "validation-payload-v2.schema.json")
            content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
            kind = "validation"
        elif entry["result_contract"] == "native-independent-review":
            checks = "\n".join(f"- Inspected: {check}" for check in dispatch["adversarial_checks"])
            native = f"""# Repository Independent Review

## Scope Inspected

- Change target: {dispatch["change_target"]}
- Files: state.rs
- Branches: HEAD~1...HEAD
- Boundary cases: changed state transition
- Tests: baseline validation command

## Findings

No findings.

## No-Finding Evidence

{checks}

## Routing Handoffs

none

## Fingerprint Proof

- Expected:
  - Scope fingerprint: {source_state[0]}
  - Worktree fingerprint: {source_state[1]}
  - Repository state fingerprint: {source_state[2]}
- Before:
  - Scope fingerprint: {source_state[0]}
  - Worktree fingerprint: {source_state[1]}
  - Repository state fingerprint: {source_state[2]}
- After:
  - Scope fingerprint: {source_state[0]}
  - Worktree fingerprint: {source_state[1]}
  - Repository state fingerprint: {source_state[2]}

## Git State

- Source-controlled files changed: none
- Git state mutated: no
""".encode()
            content, metadata = compile_independent_review({"dispatch": dispatch, "limitations": [], "status": "no-findings"}, native)
            kind = "review"
        else:
            payload = {
                "changes": [],
                "command_policy_attested": True,
                "commands_executed": [],
                "files_inspected": list(dispatch["owned_paths"]) or ["state.rs"],
                "findings": [],
                "handoffs": [],
                "limitations": [],
                "nearby_contract_owners": [],
                "status": "no-findings",
                "validation_requirements": [],
            }
            require_schema(payload, SCHEMA_ROOT / "review-payload-v1.schema.json")
            content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
            kind = "review"
        artifact_path = Path(entry["artifact_path"])
        metadata_path = Path(entry["metadata_path"])
        artifact_path.write_bytes(content)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        sources_by_node[entry["node_id"]] = {"artifact_path": str(artifact_path), "kind": kind, "metadata_path": str(metadata_path)}

    lifecycle = {"plan": _json_plan(plan), "source_state": list(source_state)}
    journal = proof_store / "execution.jsonl"
    for node in plan.actual_worker_nodes:
        append_journal_event(journal, lifecycle, JournalEventRequest(node.node_id, "accepted", source=sources_by_node[node.node_id]))
    events, _state, _head = read_execution_journal(journal, plan=plan, source_state=source_state)
    ready = next_ready_nodes({**lifecycle, "current_source_state": list(source_state)}, journal_events=events, dispatch_set=dispatch_set)
    sources = list(sources_by_node.values())
    bundle = build_synthesis_bundle({"source_state": list(source_state), "sources": sources})
    final = finalize_proof({**lifecycle, "current_source_state": list(source_state), "sources": sources})
    lifecycle_path = proof_store / "lifecycle.json"
    dispatch_path = proof_store / "dispatches.json"
    capture_path = proof_store / "capture.json"
    final_path = proof_store / "final-from-journal.json"
    lifecycle_path.write_text(json.dumps(lifecycle), encoding="utf-8")
    dispatch_path.write_text(json.dumps(dispatch_set), encoding="utf-8")
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    finalize_result = main(
        [
            "finalize-proof",
            "--input",
            str(lifecycle_path),
            "--dispatches",
            str(dispatch_path),
            "--journal",
            str(journal),
            "--current-capture",
            str(capture_path),
            "--output",
            str(final_path),
        ]
    )

    assert any(record["mode"] == "independent-review" for record in bundle["records"])
    assert ready["complete"] is True
    assert final["repository_validation_status"] == "passed"
    assert final["graph_proof_status"] == "complete"
    assert finalize_result == 0
    assert json.loads(final_path.read_text(encoding="utf-8"))["graph_proof_status"] == "complete"


def test_journal_and_next_ready_cli_use_persisted_artifacts(tmp_path: Path) -> None:
    plan = _sparse_plan()
    lifecycle_document = {
        "current_source_state": ["scope", "worktree", "repository"],
        "plan": _json_plan(plan),
        "source_state": ["scope", "worktree", "repository"],
    }
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
    capture_path = tmp_path / "capture.json"
    lifecycle_path.write_text(json.dumps(lifecycle_document), encoding="utf-8")
    dispatch_path.write_text(json.dumps(dispatch_set), encoding="utf-8")
    capture_path.write_text(
        json.dumps({"captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository", "scope_fingerprint": "scope"}), encoding="utf-8"
    )
    started = next(node.node_id for node in plan.actual_worker_nodes if not node.predecessors)

    assert main(["journal-append", "--input", str(lifecycle_path), "--journal", str(journal_path), "--node-id", started, "--status", "in-flight"]) == 0
    assert (
        main(
            [
                "next-ready",
                "--input",
                str(lifecycle_path),
                "--journal",
                str(journal_path),
                "--dispatches",
                str(dispatch_path),
                "--current-capture",
                str(capture_path),
                "--output",
                str(ready_path),
            ]
        )
        == 0
    )
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    assert started not in ready["ready_node_ids"]
    assert ready["journal"]["event_count"] == 1
    assert (
        main(
            [
                "next-ready",
                "--input",
                str(lifecycle_path),
                "--journal",
                str(journal_path),
                "--dispatches",
                str(dispatch_path),
                "--current-capture",
                str(capture_path),
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    generated = json.loads((tmp_path / "next-ready.000001.json").read_text(encoding="utf-8"))
    assert generated["output_generation"] == 1


def _compile_materialized_evidence(
    tmp_path: Path, *, handoff_catalog_id: str | None = None, resolved_handoff: bool = False, plan: GraphPlan | None = None, skip_node_ids: tuple[str, ...] = ()
) -> tuple[GraphPlan, list[dict[str, str]]]:
    plan = plan or _sparse_plan()
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
        if entry["node_id"] in skip_node_ids:
            continue
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
            if handoff_catalog_id is not None and dispatch["skill_id"] == "rust-invariant-state-transitions":
                handoffs = [
                    {
                        "catalog_id": handoff_catalog_id,
                        "observed_trigger": "the accepted audit discovered a newly applicable review surface",
                        "reason": "late routing must add the catalog owner before synthesis",
                        "scope": [STATE_FIXTURE],
                    }
                ]
            elif resolved_handoff and dispatch["mode"] == "audit":
                handoffs = [
                    {
                        "catalog_id": "rust.invariants",
                        "observed_trigger": "state transition ownership confirmed",
                        "reason": "the current plan already selected the owning catalog entry",
                        "scope": [STATE_FIXTURE],
                    }
                ]
            else:
                handoffs = []
            payload = {
                "command_policy_attested": True,
                "commands_executed": [],
                "files_inspected": [STATE_FIXTURE],
                "findings": [],
                "handoffs": handoffs,
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


def _source_by_node(sources: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {json.loads(Path(source["metadata_path"]).read_text(encoding="utf-8"))["evidence"]["node_id"]: source for source in sources}


def test_late_handoff_exact_reuse_replan_finalizes_complete_proof(tmp_path: Path) -> None:
    initial_plan, initial_sources = _compile_materialized_evidence(tmp_path / "initial", handoff_catalog_id="python.notebook")
    initial_by_node = _source_by_node(initial_sources)
    reconciled = reconcile_handoffs({"plan": _json_plan(initial_plan), "source_state": ["scope", "worktree", "repository"], "sources": initial_sources})
    assert reconciled["status"] == "requires-expansion"
    assert {trigger["catalog_id"] for trigger in reconciled["new_routing_triggers"]} == {"python.notebook"}

    replanned = _late_handoff_replan()
    validation_node_id = next(node.node_id for node in replanned.actual_worker_nodes if node.mode == "validation")
    _replanned, fresh_sources = _compile_materialized_evidence(tmp_path / "replan", plan=replanned, skip_node_ids=(validation_node_id,))
    reused_sources = [initial_by_node["audit-001"], initial_by_node["audit-002"], initial_by_node["validation-001"]]
    final = finalize_proof(
        {
            "current_source_state": ["scope", "worktree", "repository"],
            "plan": _json_plan(replanned),
            "source_state": ["scope", "worktree", "repository"],
            "sources": [*reused_sources, *fresh_sources],
        }
    )

    assert final["status"] == "complete", final["blockers"]
    assert final["proof"]["exact_reused_review_evidence"] == (("rust.build", "review:audit-001"), ("rust.invariants", "review:audit-002"))
    assert final["proof"]["validation_requirement_evidence"] == (("baseline-validation", "validation:validation-001"),)
    assert final["proof"]["resolved_handoff_ids"]


def test_artifact_derived_synthesis_and_final_proof_are_verified(tmp_path: Path) -> None:
    plan, sources = _compile_materialized_evidence(tmp_path)
    bundle = build_synthesis_bundle({"source_state": ["scope", "worktree", "repository"], "sources": sources})
    final = finalize_proof(
        {
            "current_source_state": ["scope", "worktree", "repository"],
            "plan": _json_plan(plan),
            "source_state": ["scope", "worktree", "repository"],
            "sources": sources,
        }
    )

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

    with pytest.raises(ValueError, match="current recapture differs"):
        finalize_proof(
            {
                "current_source_state": ["scope", "worktree", "changed-repository"],
                "plan": _json_plan(plan),
                "source_state": ["scope", "worktree", "repository"],
                "sources": sources,
            }
        )


def test_finalizer_reconciles_handoff_already_covered_by_current_plan(tmp_path: Path) -> None:
    plan, sources = _compile_materialized_evidence(tmp_path, resolved_handoff=True)

    reconciled = reconcile_handoffs({"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"], "sources": sources})
    final = finalize_proof(
        {
            "current_source_state": ["scope", "worktree", "repository"],
            "plan": _json_plan(plan),
            "source_state": ["scope", "worktree", "repository"],
            "sources": sources,
        }
    )

    assert reconciled["status"] == "resolved"
    assert reconciled["new_routing_triggers"] == []
    assert final["status"] == "complete"
    assert final["proof"]["resolved_handoff_ids"]
    assert final["proof"]["unresolved_handoff_ids"] == ()


def test_append_only_journal_drives_scheduling_and_cascade_invalidation(tmp_path: Path) -> None:
    plan, sources = _compile_materialized_evidence(tmp_path)
    lifecycle_document = {
        "current_source_state": ["scope", "worktree", "repository"],
        "plan": _json_plan(plan),
        "source_state": ["scope", "worktree", "repository"],
    }
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


def test_concurrent_journal_appends_serialize_sequence_and_hash_chain(tmp_path: Path) -> None:
    plan = _sparse_plan()
    lifecycle_document = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    ready_nodes = [node.node_id for node in plan.actual_worker_nodes if not node.predecessors][:2]
    assert len(ready_nodes) == 2
    barrier = Barrier(len(ready_nodes))
    journal = tmp_path / "execution.jsonl"

    def append(node_id: str) -> dict[str, Any]:
        barrier.wait()
        return append_journal_event(journal, lifecycle_document, JournalEventRequest(node_id, "in-flight"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        events = list(executor.map(append, ready_nodes))

    persisted, state, head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))
    assert sorted(event["sequence"] for event in events) == [1, 2]
    assert [event["sequence"] for event in persisted] == [1, 2]
    assert persisted[1]["previous_event_digest"] == persisted[0]["event_digest"]
    assert head == persisted[1]["event_digest"]
    assert state == dict.fromkeys(ready_nodes, "in-flight")


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


def test_awaiting_replan_is_terminal_for_stale_dispatch_set(tmp_path: Path) -> None:
    plan, sources = _compile_materialized_evidence(tmp_path)
    lifecycle = {"current_source_state": ["scope", "worktree", "repository"], "plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
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
    root = next(node for node in plan.actual_worker_nodes if not node.predecessors)
    journal = tmp_path / "awaiting-replan.jsonl"
    append_journal_event(journal, lifecycle, JournalEventRequest(root.node_id, "accepted", source=source_by_node[root.node_id]))
    append_journal_event(journal, lifecycle, JournalEventRequest(root.node_id, "awaiting-replan", reason="repair epoch changed source state"))
    events, _state, _head = read_execution_journal(journal, plan=plan, source_state=("scope", "worktree", "repository"))

    ready = next_ready_nodes(lifecycle, journal_events=events, dispatch_set=dispatch_set)

    assert root.node_id not in ready["ready_node_ids"]
    assert root.node_id in ready["lifecycle"]["awaiting_replan_node_ids"]
    assert any("fresh plan" in blocker for blocker in ready["blockers"])


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
