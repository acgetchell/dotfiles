"""Audit reuse and coverage-proof fixtures for review-graph tests."""

import json
import shlex
from pathlib import Path
from typing import Any, cast

import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_support_review_graph import ROUTING_CATALOG, SKILL_ROOT, _complete_structural_fixture_routing, _materialize, _run_test_git, _set_fixture_routing
from test_support_review_graph_evidence import _payload
from test_support_review_graph_lifecycle import _baseline_mutation_fixture


def _audit_request(tmp_path: Path, *, large: bool = False, caveat: str = "facts") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:  # noqa: C901, PLR0915 - complete partitioned audit with explicit policy variants.
    """Capture an actual repository and preserve a fresh, partitioned audit."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    owned = ["LICENSE", "tool.py"]
    if large:
        owned = [f"scientific_model_{index:03d}_numerical_invariants_and_reproducibility.py" for index in range(23)]
        for path in owned:
            (repository / path).write_text("value = 1\n")
        for index in range(153):
            (repository / f"context_{index:03d}_captured_repository_dependency_manifest.txt").write_text("stable context\n")
        template["captured_path_dispositions"].append(
            {
                "paths": [f"context_{index:03d}_captured_repository_dependency_manifest.txt" for index in range(153)],
                "disposition": "historical",
                "reason": "Inactive context records used only to measure bounded proof transport",
                "catalog_ids": [],
            }
        )
        _run_test_git(git, "-C", str(repository), "add", ".")
        _run_test_git(git, "-C", str(repository), "commit", "-m", "whole repository fixture")
    else:
        template["captured_path_dispositions"][0]["paths"].remove("LICENSE")
    catalog = "python.scientific" if large else "python.cli"
    if caveat == "native-unavailable":
        template["validation_requirements"].append(
            {
                **template["validation_requirements"][0],
                "requirement_id": "native-ci",
                "baseline": False,
                "commands": [],
                "working_directories": [],
                "canonical_recipe": None,
                "environment": "GitHub Actions native matrix",
                "platform": "native hosted CI",
                "planning_blocker": "Required native jobs unavailable",
            }
        )
    _set_fixture_routing(
        template,
        {
            "catalog_id": catalog,
            "disposition": "selected",
            "reason": "Owned contracts",
            "applicability_evidence": owned,
            "owners": ["python"],
            "review_surface": owned,
        },
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    skill = "python-scientific-review" if large else "python-cli-review"
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["skill_id"] == skill)
    owned = entry["dispatch"]["owned_paths"]
    payload = _payload(owned, dispatch=entry["dispatch"])
    payload["coverage_units"] = [
        {
            "unit_id": path,
            "owned_paths": [path],
            "dependency_paths": ["cliff.toml", *entry["dispatch"].get("required_read_paths", [])],
            "dependency_uncertainty": "",
            "finding_indices": [],
        }
        for path in owned
    ]
    payload["nearby_contract_owners"].append("cliff.toml")
    if caveat == "facts":
        payload["execution_facts"] = ["validators-not-executed", "source-captures-match", "git-not-mutated"]
        payload["commands_executed"] = [f"nl -ba {owned[0]}", shlex.join(entry["dispatch"]["worker_payload_persistence"]["publish_command"])]
    elif caveat == "unclassified":
        payload["limitations"] = ["No validators ran; a free-text caveat is not typed evidence."]
    elif caveat == "scope":
        payload.update(status="completed", files_inspected=owned[1:], scope_limitations=[{"path": owned[0], "reason": "Source unavailable"}])
    elif caveat == "uncertainty":
        payload["unresolved_uncertainties"] = [{"kind": "semantic", "reason": "The input contract is unresolved"}]
    elif caveat == "dependency":
        payload["coverage_units"][0]["dependency_uncertainty"] = "Unknown dynamic dependency"
    elif caveat in {"delegated", "unavailable", "failed", "native-unavailable"}:
        planned = entry["dispatch"]["command_policy"]["planned_validation_units"][-1 if caveat == "native-unavailable" else 0]
        requirement = planned["requirement_ids"][0]
        payload["validation_requirements"] = [
            {
                "requirement_id": requirement,
                "planned_validation_digest": planned["planned_validation_digest"],
                "owner": "review-validator",
                "reason": "Platform evidence",
                "expected_evidence": "Required checks pass",
            }
        ]
        payload["validation_limits"] = [
            {
                "requirement_id": requirement,
                "environment": "current host",
                "status": "unavailable" if caveat == "native-unavailable" else caveat,
                "reason": "Execution belongs to the validator",
            }
        ]
    if caveat == "no-partition":
        del payload["coverage_units"]
    dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
    content, metadata = runtime.compile_review({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    changed = owned[-1]
    (repository / changed).write_text("value = 2\n")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "planning_template": template,
        "authorization_before": "review-only",
        "authorization_after": "review-and-fix",
        "repair_epoch": 1,
        "changed_paths": [changed],
        "artifact_store": str(tmp_path / "repair"),
        "state_verification_command": "capture_scope.py --mode baseline",
        "sources": [{key: entry[key] for key in ("artifact_path", "metadata_path")}],
    }
    return request, entry, payload


def _compile_args(result: dict[str, Any], entry: dict[str, Any], output: Path) -> list[str]:
    """Build a compile-node invocation that uses the same source capture on both sides."""
    return [
        "compile-node",
        "--input",
        result["lifecycle_input_path"],
        "--dispatches",
        result["dispatches_path"],
        "--journal",
        result["journal_path"],
        "--node-id",
        entry["node_id"],
        "--before-capture",
        result["capture_path"],
        "--after-capture",
        result["capture_path"],
        "--output",
        str(output),
    ]


def _proof_fixture(  # noqa: PLR0915 - complete partitioned audit and repair fixture.
    tmp_path: Path, *, validation_change: str | None = None, stage_after_repair: bool = False, unrelated_paths: int = 1
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Use fresh real proof files; expand the inventory only for the size contract."""
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    owned = ["pyproject.toml", "tests/tooling/test_adoption.py"]
    (repository / "tests/tooling").mkdir(parents=True)
    (repository / owned[0]).write_text('[project]\nname = "fixture"\nversion = "0.1.0"\n')
    (repository / owned[1]).write_text("def test_adoption():\n    assert True\n")
    (repository / "AGENTS.md").write_text("# Instructions\n\nInspect test contracts.\n")
    for index in range(unrelated_paths):
        (repository / f"unrelated_{index:03d}.txt").write_text("Unrelated captured input.\n")
    template["captured_path_dispositions"].append(
        {
            "paths": [f"unrelated_{index:03d}.txt" for index in range(unrelated_paths)],
            "disposition": "historical",
            "reason": "Inactive inventory records used only to measure proof transport",
            "catalog_ids": [],
        }
    )
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "fixed coverage fixture")
    template["consulted_routers"].append("docs-review-orchestrator")
    _set_fixture_routing(
        template,
        {
            "catalog_id": "python.tests",
            "disposition": "selected",
            "reason": "Test and configuration contracts",
            "applicability_evidence": owned,
            "owners": ["python"],
            "review_surface": owned,
        },
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    if validation_change is not None and validation_change.startswith("commandless"):
        template["validation_requirements"][0].update(
            commands=[], working_directories=[], canonical_recipe="just ci", planning_blocker="External CI has no retained log"
        )
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    fresh = next(entry for entry in entries["dispatches"] if entry["dispatch"]["skill_id"] == "python-test-quality")
    validation = fresh["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload = {
        **_payload(owned, dispatch=fresh["dispatch"]),
        "status": "completed",
        "nearby_contract_owners": ["cliff.toml", *fresh["dispatch"]["required_read_paths"]],
        "coverage_units": [
            {
                "unit_id": "configuration",
                "owned_paths": [owned[0]],
                "dependency_paths": ["cliff.toml", *fresh["dispatch"]["required_read_paths"]],
                "dependency_uncertainty": "",
                "finding_indices": [1],
            },
            {"unit_id": "adoption-tests", "owned_paths": [owned[1]], "dependency_paths": [owned[0]], "dependency_uncertainty": "", "finding_indices": [2]},
        ],
        "findings": [
            {
                "severity": "P2",
                "location": f"{path}:1",
                "summary": summary,
                "evidence": "Seeded fixture observation.",
                "remediation": "Add the missing test contract.",
            }
            for path, summary in zip(owned, ("Configuration omits test discovery", "Test omits failure assertion"), strict=True)
        ],
        "validation_requirements": [
            {
                "requirement_id": validation["requirement_ids"][0],
                "planned_validation_digest": validation["planned_validation_digest"],
                "owner": "review-validator",
                "reason": "Run the fixture's required validation",
                "expected_evidence": "Checks pass",
            }
        ],
        "handoffs": [{"catalog_id": "python.build", "observed_trigger": "Test configuration", "reason": "Check installation", "scope": owned}],
    }
    if stage_after_repair:
        payload["git_dependencies"] = [{"kind": "index", "reason": "The judgment depends on staging."}]
    if validation_change is not None and validation_change.startswith("commandless"):
        payload["validation_limits"] = [
            {"requirement_id": validation["requirement_ids"][0], "environment": "fixture", "status": "unavailable", "reason": "External CI has no retained log"}
        ]
    content, metadata = runtime.compile_review(
        {"dispatch": {**fresh["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(fresh["artifact_path"]).write_bytes(content)
    Path(fresh["metadata_path"]).write_text(json.dumps(metadata))
    if validation_change == "renamed-requirement":
        template["validation_requirements"][0]["requirement_id"] += "-replacement"
    elif validation_change == "environment":
        template["validation_requirements"][0]["environment"] += "; changed executor"
    elif validation_change is not None and validation_change.startswith("commandless"):
        template["validation_requirements"][0].update(commands=["just ci"], working_directories=[str(repository)], planning_blocker=None)
        if validation_change != "commandless":
            field = validation_change.removeprefix("commandless-")
            template["validation_requirements"][0][field] = ["just other"] if field == "commands" else "different"
    (repository / owned[1]).write_text("def test_adoption():\n    assert 1 == 1\n")
    repaired_capture = _scope_data(git, repository, "baseline", None, ())
    metadata_transition = {}
    if stage_after_repair:
        _run_test_git(git, "-C", str(repository), "add", owned[1])
        metadata_transition["post_repair_capture"] = _scope_data(git, repository, "baseline", None, ())
    original = {key: Path(fresh[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    result = runtime.advance_after_mutation(
        {
            **lifecycle,
            **metadata_transition,
            "previous_capture": capture,
            "new_capture": repaired_capture,
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": [owned[1]],
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "sources": [{key: fresh[key] for key in ("artifact_path", "metadata_path")}],
        }
    )
    assert {key: Path(fresh[key]).read_bytes() for key in original} == original
    partial = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["skill_id"] == "python-test-quality")
    validation = partial["dispatch"]["command_policy"]["planned_validation_units"][0]
    updated = {
        **_payload([owned[1]], dispatch=partial["dispatch"]),
        "status": "completed",
        "findings": payload["findings"][1:],
        "nearby_contract_owners": [owned[0], *partial["dispatch"]["required_read_paths"]],
        "validation_requirements": [{**payload["validation_requirements"][0], "planned_validation_digest": validation["planned_validation_digest"]}],
        "handoffs": payload["handoffs"],
    }
    return fresh, partial, result, updated


def _compile(entry: dict[str, Any], result: dict[str, Any], payload: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Compile fixture evidence with both observations bound to the new source state."""
    state = result["new_source_state"]
    return runtime.compile_review({"dispatch": {**entry["dispatch"], "before_state": state, "after_state": state}, "payload": payload})
