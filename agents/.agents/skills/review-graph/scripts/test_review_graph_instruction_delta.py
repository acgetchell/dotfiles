"""Fresh semantic reconciliation preserves unchanged Rust build evidence only."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from review_graph_scheduling import select_execution_lanes
from test_review_graph_reuse import _compile_args
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _complete_structural_fixture_routing,
    _run_test_git,
    _set_fixture_routing,
)
from test_review_graph_transitions import _materialize, _payload


def _fixture(tmp_path: Path, *, material: bool = False, recipe: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    files = {
        "Cargo.toml": '[package]\nname = "fixture"\nversion = "0.1.0"\nedition = "2024"\n',
        "Cargo.lock": "version = 4\n",
        "CONTRIBUTING.md": "# Contributing\n\n## Rust validation\n\nRun cargo check.\n\n## Security scans\n\nScan Cargo.lock with OSV.\n",
        "justfile": "check:\n    cargo check\n\nbench:\n    uv sync --locked\n    cargo bench\n",
    }
    for name, content in files.items():
        (repository / name).write_text(content)
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Rust build policy fixture")
    template["consulted_routers"].append("docs-review-orchestrator")
    template["instruction_paths"] = ["CONTRIBUTING.md"]
    owned = ["Cargo.toml", "Cargo.lock", "state.rs"]
    _set_fixture_routing(
        template,
        {
            "catalog_id": "rust.build",
            "disposition": "selected",
            "reason": "Rust compilation contract",
            "applicability_evidence": owned,
            "owners": ["rust"],
            "review_surface": owned,
        },
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, list(runtime._text_list(capture, "captured_scope_paths")))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    original = next(item for item in entries["dispatches"] if item["dispatch"]["skill_id"] == "rust-build-portability")
    payload = {
        **_payload(owned),
        "nearby_contract_owners": ["CONTRIBUTING.md", "justfile"],
        "coverage_units": [
            {
                "unit_id": "rust-build",
                "owned_paths": owned,
                "dependency_paths": ["CONTRIBUTING.md", "justfile"],
                "recipe_dependencies": [{"path": "justfile", "recipes": ["check"]}],
                "dependency_uncertainty": "",
                "finding_indices": [],
            }
        ],
    }
    content, metadata = runtime.compile_review(
        {"dispatch": {**original["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(original["artifact_path"]).write_bytes(content)
    Path(original["metadata_path"]).write_text(json.dumps(metadata))
    if recipe:
        changed = "justfile"
        (repository / changed).write_text(
            files[changed].replace("cargo check", "cargo check --all-features") if material else files[changed].replace("    uv sync --locked\n", "")
        )
    else:
        changed = "CONTRIBUTING.md"
        (repository / changed).write_text(
            files[changed].replace("Run cargo check.", "Run cargo check --all-features and verify the public API.")
            if material
            else files[changed].replace("Scan Cargo.lock with OSV.", "Scan Cargo.lock and uv.lock with OSV. Dependabot changes need manual review.")
        )
    current = _scope_data(git, repository, "baseline", None, ())
    result = runtime.advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": current,
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": [changed],
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "sources": [{key: original[key] for key in ("artifact_path", "metadata_path")}],
        }
    )
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "rust-build-portability")
    return result, original, entry


def _assessment(entry: dict[str, Any], *, material: bool = False) -> dict[str, Any]:
    units = entry["dispatch"]["coverage_reuse"]["units"]
    deltas = units[0]["input_deltas"]
    return {
        **_payload(entry["dispatch"]["owned_paths"] if material else []),
        "nearby_contract_owners": [item["path"] for item in deltas],
        "instruction_reconciliations": [
            {
                "unit_id": "rust-build",
                "disposition": "reinspect" if material else "unchanged",
                "assessments": [
                    {
                        "path": item["path"],
                        "changed_sections_inspected": True,
                        **{
                            name: {
                                "changed": material,
                                "reason": "Rust validation requirements changed; rechecked all owned source."
                                if material
                                else (
                                    "The changed section concerns security inventory or the unrelated benchmark recipe; "
                                    "Rust build requirements and check recipe remain identical."
                                ),
                            }
                            for name in ("rules", "commands", "applicability", "obligations")
                        },
                    }
                    for item in deltas
                ],
            }
        ],
    }


@pytest.mark.parametrize("recipe", [False, True], ids=["security-instructions", "unrelated-recipe"])
def test_unrelated_delta_keeps_rust_source_evidence_after_fresh_reconciliation(tmp_path: Path, recipe: bool) -> None:
    result, original, entry = _fixture(tmp_path, recipe=recipe)
    before = {key: Path(original[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    context = entry["dispatch"]["coverage_reuse"]
    ready = {"ready_node_ids": [entry["node_id"]], "lifecycle": {"in_flight_node_ids": []}}
    for active in (0, 1):
        selected = select_execution_lanes(
            {"worker_capacity": {"source": "fixture host", "concurrent_worker_limit": 1, "active_workers": active}},
            modes={entry["node_id"]: "audit"},
            entries={entry["node_id"]: entry},
            ready=ready,
        )
        assert selected["coordinator_node_id"] is None
        assert selected["worker_node_ids"] == ([entry["node_id"]] if active == 0 else [])
    assert context["units"][0]["disposition"] == "instruction-review"
    assert runtime.reused_paths(context) == ()
    assert all("before" not in item and "after" not in item for item in context["units"][0]["input_deltas"])
    assert runtime._coverage_proof(context)["units"][0]["input_deltas"][0]["before"]
    payload = _assessment(entry)
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    assert runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())["status"] == "published"
    assert runtime.main(_compile_args(result, entry, tmp_path / "compiled.json")) == 0
    record = runtime._load_evidence_source(entry, require_normalized=True)[4]
    assert isinstance(record, dict)
    assert record["files_inspected"] == []
    assert set(runtime.reused_paths(record["coverage_reuse"])) == set(entry["dispatch"]["owned_paths"])
    assert all(Path(original[key]).read_bytes() == value for key, value in before.items())
    assert result["repair_epoch"]["recapture_count"] == 1
    print(json.dumps({"retained_source_paths": 3, "rechecked_source_paths": 0, "focused_audit_dispatches": 1, "provider_tokens": None, "provider_cost": None}))


@pytest.mark.parametrize("recipe", [False, True], ids=["rust-policy", "rust-check-command"])
def test_material_instruction_or_recipe_change_requires_all_owned_source(tmp_path: Path, recipe: bool) -> None:
    result, _original, entry = _fixture(tmp_path, material=True, recipe=recipe)
    payload = _assessment(entry, material=True)
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    omitted = {**payload, "files_inspected": []}
    with pytest.raises(ValueError, match="require inspection"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(omitted).encode())
    false_reuse = deepcopy(payload)
    false_reuse["instruction_reconciliations"][0]["disposition"] = "unchanged"
    with pytest.raises(ValueError, match="require source reinspection"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(false_reuse).encode())
    assert runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())["status"] == "published"
    assert runtime.main(_compile_args(result, entry, tmp_path / "compiled.json")) == 0
    record = runtime._load_evidence_source(entry, require_normalized=True)[4]
    assert isinstance(record, dict)
    assert runtime.reused_paths(record["coverage_reuse"]) == ()
    assert set(record["files_inspected"]) == set(entry["dispatch"]["owned_paths"])


def test_reconciliation_cannot_be_a_coordinator_waiver_or_omit_changed_documents(tmp_path: Path) -> None:
    _result, _original, entry = _fixture(tmp_path)
    payload = _assessment(entry)
    dispatch = {**entry["dispatch"], "fresh_context": False, "worker_created": False, "execution_location": "coordinator"}
    with pytest.raises(ValueError, match="fresh audit"):
        runtime.compile_review({"dispatch": dispatch, "payload": payload})
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    payload["nearby_contract_owners"] = []
    with pytest.raises(ValueError, match="every changed document"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    uncertain = _assessment(entry)
    uncertain["instruction_reconciliations"][0]["disposition"] = "uncertain"
    with pytest.raises(ValueError, match="uncertain"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(uncertain).encode())


@pytest.mark.parametrize("dimension", ["rules", "commands", "applicability", "obligations"])
def test_each_material_dimension_independently_prevents_unchanged_reuse(tmp_path: Path, dimension: str) -> None:
    _result, _original, entry = _fixture(tmp_path, material=True)
    payload = _assessment(entry)
    judgment = payload["instruction_reconciliations"][0]["assessments"][0][dimension]
    judgment.update(changed=True, reason=f"The {dimension} contract changed and requires source reinspection.")
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    with pytest.raises(ValueError, match="require source reinspection"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert not Path(entry["worker_payload_path"]).exists()


def test_retained_delta_bytes_are_verified_against_both_captures(tmp_path: Path) -> None:
    _result, _original, entry = _fixture(tmp_path)
    proof = runtime._coverage_proof(entry["dispatch"]["coverage_reuse"])
    proof["units"][0]["input_deltas"][0]["after"] = "unrelated substituted policy"
    with pytest.raises(ValueError, match="immutable findings or verified unit decisions"):
        runtime._verify_delta_context(proof, entry["dispatch"])


@pytest.mark.parametrize(("failure_kind", "attempts"), [("unexpected", 1), ("capacity", 2)])
def test_fresh_reconciliation_creation_failure_reports_blocker_across_continuations(tmp_path: Path, failure_kind: str, attempts: int) -> None:
    result, _original, entry = _fixture(tmp_path)
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_bytes())
    failure = {"node_id": entry["node_id"], "failure_kind": failure_kind, "attempts": attempts, "reason": "observed executor failure", "worker_created": False}
    request = {**lifecycle, "artifact_store": str(tmp_path / "schedules"), "creation_failure": failure}
    dispatches = result["dispatches_path"]
    for active in (1, 0):
        request["worker_capacity"] = {"source": "fresh host observation", "concurrent_worker_limit": 1, "active_workers": active}
        request_path, output = tmp_path / f"request-{active}.json", tmp_path / f"schedule-{active}.json"
        request_path.write_text(json.dumps(request))
        assert (
            runtime.main(
                [
                    "schedule-ready",
                    "--input",
                    str(request_path),
                    "--dispatches",
                    dispatches,
                    "--journal",
                    result["journal_path"],
                    "--current-capture",
                    result["capture_path"],
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        scheduled = json.loads(output.read_bytes())
        assert scheduled["creation_failure_action"] == "fresh-worker-blocked"
        assert any("requires a fresh worker" in blocker for blocker in scheduled["blockers"])
        assert entry["node_id"] not in scheduled["ready_node_ids"]
        assert scheduled["coordinator_node_id"] != entry["node_id"]
        request = json.loads(Path(scheduled["schedule_input_path"]).read_bytes())
        assert request["creation_failure"] == failure
        dispatches = scheduled["dispatches_path"]
