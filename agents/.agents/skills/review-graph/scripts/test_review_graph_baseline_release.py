"""Real baseline setup and first repair transport, with scripted audit judgments."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import main as bootstrap_main
from review_graph_integrity import digest_bytes
from review_graph_schema import require_schema
from review_graph_starter import RELEASE_EXAMPLE, STARTER_SCHEMA, main as prepare_main, starter_template
from test_review_graph_git import _accept
from test_review_graph_runtime import _baseline_mutation_fixture, _compact_audit_payload, _compile_repair_fixture_entry, _run_test_git
from test_support_review_graph import _prepare_all_fixture_timing


def _setup(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, _template, _capture, _plan = _baseline_mutation_fixture(tmp_path, instructions=True)
    for path, content in {
        "state.rs": "pub fn square(value: f64) -> f64 { value * value }\n",
        "untouched.rs": "pub fn identity(value: f64) -> f64 { value }\n",
        "tool.py": "def label(value):\n    return str(value)\n",
        "justfile": "ci:\n    true\n",
        "nested/AGENTS.md": "# Nested instructions\n\nApply only under nested/.\n",
        "nested/readme.txt": "Separate instruction scope.\n",
    }.items():
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "baseline release fixture")
    capture = _scope_data(git, repository, "baseline", None, ())
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture))
    artifact_root = tmp_path / "validation"
    artifact_root.mkdir()
    choices_path = tmp_path / "operator.json"
    assert prepare_main(["baseline-release", "--capture", str(capture_path), "--artifact-root", str(artifact_root), "--output", str(choices_path)]) == 0
    preparation = json.loads(capsys.readouterr().out)
    choices = json.loads(choices_path.read_bytes())
    discovery = json.loads(Path(preparation["discovery"]["path"]).read_bytes())
    assert discovery["instruction_paths"] == ["AGENTS.md", "nested/AGENTS.md"]
    assert choices["instruction_paths"] == ["AGENTS.md"]
    assert choices["command_policy"]["disposition"] == "blocked"
    assert preparation["model_tokens"] is preparation["provider_cost"] is None
    choices.update(
        authorization="review-and-fix",
        ignored_outputs=[],
        command_policy={"disposition": "allowed", "reason": "Scripted transport fixture; the gate is not executed."},
        execution_prerequisites={"executables": ["env"], "native_available": True, "reason": "POSIX transport fixture."},
        routing_overrides=[
            {
                "catalog_id": item["catalog_id"],
                "disposition": "selected",
                "reason": "Scripted fixture exercises every matched leaf's independent evidence contract.",
                "applicability_evidence": item["matched_paths"],
                "review_surface": item["matched_paths"],
                "owners": ["documentation" if item["catalog_id"].startswith("docs.") else item["catalog_id"].split(".")[0]],
            }
            for item in discovery["routing_projection"]["entries"]
            if item["target_kind"] == "leaf" and item["matched_paths"] and not item["catalog_id"].startswith("repo.")
        ],
    )
    choices["routing_overrides"].append(
        {
            "catalog_id": "rust.scientific",
            "disposition": "selected",
            "reason": "The fixture's independent numerical functions exercise scientific repair coverage.",
            "applicability_evidence": ["state.rs", "untouched.rs"],
            "review_surface": ["state.rs", "untouched.rs"],
            "owners": ["rust"],
        }
    )
    choices_path.write_text(json.dumps(choices))
    bootstrap = tmp_path / "bootstrap.json"
    assert bootstrap_main(["--capture", str(capture_path), "--starter-config", str(choices_path), "--output", str(bootstrap)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["preflight_status"] == "ready"
    bundle = json.loads(bootstrap.read_bytes())
    assert bundle["planning_input"]["release_readiness"]
    assert bundle["planning_input"]["scope_mode"] == "baseline"
    assert not bundle["planning_input"]["concrete_change_target"]
    dispatches_path = tmp_path / "dispatches.json"
    assert runtime.main(["materialize-dispatches", "--input", str(bootstrap), "--output", str(dispatches_path)]) == 0
    materialization = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(materialization["launch_manifest_reference"]["path"]).read_bytes())
    assert all(item["skill_path"] and item["execution_view"]["digest"] for item in manifest["nodes"])
    assert "dispatch" not in json.dumps(manifest["nodes"])
    bundle["fixture_metrics"] = {
        "preparation": preparation,
        "bootstrap": receipt["starter_metrics"],
        "launch_manifest_bytes": Path(materialization["launch_manifest_reference"]["path"]).stat().st_size,
        "materialization_bytes": dispatches_path.stat().st_size,
    }
    return git, repository, capture, bundle, json.loads(dispatches_path.read_bytes())


def _initial_audits(tmp_path: Path, bundle: dict[str, Any], dispatches: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    lifecycle = {**bundle["lifecycle_input"], "journal_path": str(tmp_path / "initial.jsonl"), "dispatches_path": str(tmp_path / "dispatches.json")}
    sources = []
    for entry in dispatches["dispatches"]:
        dispatch = entry["dispatch"]
        if dispatch["mode"] != "audit":
            continue
        protocol = [entry[key] for key in ("worker_input_path", "worker_execution_path", "worker_payload_contract_path")]
        dependencies = sorted({*dispatch["required_read_paths"], *protocol})
        scientific = dispatch["skill_id"] == "rust-scientific-correctness"
        validation = dispatch["command_policy"]["planned_validation_units"][0]
        payload = {
            **_compact_audit_payload(entry),
            "commands_executed": ["cat " + " ".join(protocol)],
            "nearby_contract_owners": [*dependencies, *(["cliff.toml"] if scientific else [])],
            "validation_requirements": [
                {
                    "requirement_id": validation["requirement_ids"][0],
                    "planned_validation_digest": validation["planned_validation_digest"],
                    "owner": "review-validator",
                    "reason": "Required release gate",
                    "expected_evidence": "Gate status and output",
                }
            ],
            "coverage_units": [
                {
                    "unit_id": f"contract-{index}",
                    "owned_paths": [path],
                    "dependency_paths": [*dependencies, *(["cliff.toml"] if scientific and path == "untouched.rs" else [])],
                    "dependency_uncertainty": "",
                    "finding_indices": [],
                }
                for index, path in enumerate(dispatch["owned_paths"])
            ],
        }
        contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
        assert runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())["status"] == "published"
        source = _accept(lifecycle, entry, payload)
        metadata = json.loads(Path(source["metadata_path"]).read_bytes())
        bindings = dict(metadata["expectation"]["audit_input_identity"]["runtime_inputs"])
        assert set(protocol) <= bindings.keys()
        assert dispatch["skill_path"] in bindings
        sources.append(source)
    assert sources
    return lifecycle, sources


def _repair(tmp_path: Path, capsys: pytest.CaptureFixture[str], *, instructions: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, capture, bundle, dispatches = _setup(tmp_path, capsys)
    lifecycle, sources = _initial_audits(tmp_path, bundle, dispatches)
    history = {path: Path(path).read_bytes() for source in sources for path in source.values()}
    changed = ["state.rs", "tool.py"]
    (repository / "state.rs").write_text("pub fn square(value: f64) -> f64 { value * value + 0.0 }\n")
    (repository / "tool.py").write_text("def label(value):\n    return str(value).strip()\n")
    if instructions:
        changed.append("AGENTS.md")
        with (repository / "AGENTS.md").open("a") as stream:
            stream.write("\n<!-- Maintainer spelling correction; no review contract changes. -->\n")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "planning_template": bundle["planning_input"],
        "authorization_before": "review-and-fix",
        "authorization_after": "review-and-fix",
        "repair_epoch": 1,
        "changed_paths": changed,
        "artifact_store": str(tmp_path / "repairs"),
        "state_verification_command": "capture_scope.py --mode baseline",
        "sources": sources,
    }
    result = runtime.advance_after_mutation(request)
    assert all(Path(path).read_bytes() == content for path, content in history.items())
    return request, result, bundle["fixture_metrics"]


@pytest.mark.parametrize("instructions", [False, True])
def test_baseline_release_first_repair_retains_bound_contracts(tmp_path: Path, capsys: pytest.CaptureFixture[str], instructions: bool) -> None:
    request, result, metrics = _repair(tmp_path, capsys, instructions=instructions)
    scientific = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "rust-scientific-correctness")
    context = scientific["dispatch"]["coverage_reuse"]
    unchanged = next(unit for unit in context["units"] if unit["owned_paths"] == ["untouched.rs"])
    assert unchanged["disposition"] == ("instruction-review" if instructions else "reused")
    assert next(unit for unit in context["units"] if unit["owned_paths"] == ["state.rs"])["disposition"] == "recheck"
    assert not result["validation_reconciliation"]["blockers"]
    assert result["new_plan"]["independent_review_after_audits"]
    assert result["new_plan"]["review_lifecycle"]["repairs_completed"] == 1
    assert context["original_validation_requirements"]
    assert all("unbound-external-source" not in json.dumps(item) for item in result["reuse_decisions"])
    if not instructions:
        assert result["audit_reuse_counts"]["retained"] > 0
    assert result["capture"]["captured_scope_paths"] == request["previous_capture"]["captured_scope_paths"]
    _finish_repair(result, tmp_path, capsys)
    print(
        json.dumps(
            {"operator_metrics": metrics, "audit_reuse_counts": result["audit_reuse_counts"], "model_tokens": None, "provider_cost": None}, sort_keys=True
        )
    )


def _finish_repair(result: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lifecycle = {**result["lifecycle_input"], "journal_path": result["journal_path"], "dispatches_path": result["dispatches_path"]}
    plan = runtime._graph_plan(lifecycle["plan"])
    dispatches = result["dispatch_set"]
    journal = Path(result["journal_path"])
    _prepare_all_fixture_timing(dispatches)
    observed_modes: set[str] = set()
    for _ in range(plan.complete_node_count + 1):
        events, _state, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = runtime.next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=dispatches)
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready["blockers"]
        for entry in ready["ready_dispatches"]:
            dispatch = entry["dispatch"]
            observed_modes.add(dispatch["mode"])
            if dispatch["mode"] != "audit":
                if dispatch["mode"] == "validation":
                    snapshot = runtime.capture_workspace_snapshot(dispatch)["records"]
                    entry = {**entry, "dispatch": {**dispatch, "workspace_before": snapshot, "workspace_after": snapshot}}
                _compile_repair_fixture_entry(entry, lifecycle, journal)
                continue
            context = dispatch.get("coverage_reuse")
            units = context["units"] if context else []
            inspected = [path for unit in units if unit["disposition"] == "recheck" for path in unit["owned_paths"]] if context else dispatch["owned_paths"]
            validation = dispatch["command_policy"]["planned_validation_units"][0]
            payload = {
                **_compact_audit_payload(entry),
                "files_inspected": inspected,
                "nearby_contract_owners": sorted(
                    {*dispatch["required_read_paths"], *(delta["path"] for unit in units for delta in unit.get("input_deltas", []))}
                ),
                "validation_requirements": [
                    {
                        "requirement_id": validation["requirement_ids"][0],
                        "planned_validation_digest": validation["planned_validation_digest"],
                        "owner": "review-validator",
                        "reason": "Retain release validation",
                        "expected_evidence": "Current gate status and output",
                    }
                ],
                "instruction_reconciliations": [
                    {
                        "unit_id": unit["unit_id"],
                        "disposition": "unchanged",
                        "assessments": [
                            {
                                "path": delta["path"],
                                "changed_sections_inspected": True,
                                **{
                                    name: {"changed": False, "reason": "Only a spelling comment changed; the fixture's review contracts are identical."}
                                    for name in ("rules", "commands", "applicability", "obligations")
                                },
                            }
                            for delta in unit["input_deltas"]
                        ],
                    }
                    for unit in units
                    if unit["disposition"] == "instruction-review"
                ],
            }
            contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
            assert runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())["status"] == "published"
            _accept(lifecycle, entry, payload)
    else:
        pytest.fail("The bounded repair fixture did not complete its graph")
    assert {"audit", "independent-review", "validation"} <= observed_modes
    report_path = tmp_path / "delivery.json"
    assert (
        runtime.main(
            [
                "report-delivery",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--current-capture",
                result["capture_path"],
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    report = json.loads(report_path.read_bytes())
    assert report["delivery_profile"] == "routine"
    assert report["graph_proof_status"] == "not-certified"
    assert not report["pending_semantic_node_ids"]
    assert not report["blockers"]
    assert all(unit["status"] == "passed" for unit in report["validation"])


def test_baseline_release_template_rejects_partial_capture_and_misplaced_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _git, _repository, capture, bundle, _dispatches = _setup(tmp_path, capsys)
    choices = json.loads(RELEASE_EXAMPLE.read_bytes())
    choices["artifact_root"] = bundle["planning_input"]["validation_requirements"][0]["isolation_root"]
    require_schema(choices, STARTER_SCHEMA)
    capture["requested_paths"] = ["state.rs"]
    with pytest.raises(ValueError, match="whole-repository capture"):
        starter_template(capture, choices)
    capture["requested_paths"] = []
    choices["ignored_outputs"] = [{"path": str(tmp_path / "external-cache"), "kind": "cache"}]
    with pytest.raises(ValueError, match=r"\$.ignored_outputs\[0\].path.*external_artifacts"):
        starter_template(capture, choices)
    choices["ignored_outputs"] = []
    choices["external_artifacts"] = [{"path": str(Path(choices["artifact_root"]) / "python-cache"), "kind": "cache"}]
    requirement = starter_template(capture, choices)["validation_requirements"][0]
    assert requirement["expected_workspace_effects"] == []
    assert requirement["allowed_artifacts"][-1]["repository_status"] == "outside-repository"
    choices["external_artifacts"][0]["path"] = str(tmp_path / "outside-artifact-root")
    with pytest.raises(ValueError, match=r"\$.external_artifacts\[0\].path"):
        starter_template(capture, choices)


def test_verification_followup_keeps_batch_and_rejects_repeated_or_expanded_work(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    request, result, _metrics = _repair(tmp_path, capsys)
    previous_path = tmp_path / "first-repair.json"
    previous_path.write_text(json.dumps(result))
    lifecycle = {**result["lifecycle_input"], "journal_path": result["journal_path"], "dispatches_path": result["dispatches_path"]}
    scientific = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "rust-scientific-correctness")
    payload = {
        **_compact_audit_payload(scientific),
        "files_inspected": ["state.rs"],
        "status": "completed",
        "validation_requirements": [
            {**item, "planned_validation_digest": scientific["dispatch"]["command_policy"]["planned_validation_units"][0]["planned_validation_digest"]}
            for item in scientific["dispatch"]["coverage_reuse"]["original_validation_requirements"]
        ],
        "findings": [
            {
                "severity": "P2",
                "location": "state.rs:1",
                "summary": "Seeded affected verification finding",
                "evidence": "Scripted transport observation",
                "remediation": "Remove the redundant term",
            }
        ],
    }
    source = _accept(lifecycle, scientific, payload)
    # Malformed legacy inline metadata must fail before recursive proof loading
    # can loop; restoring identical bytes leaves the accepted evidence usable.
    metadata_path = Path(source["metadata_path"])
    original_metadata = metadata_path.read_bytes()
    cyclic = json.loads(original_metadata)
    cyclic_context = deepcopy(runtime._coverage_proof(cyclic["expectation"]["coverage_reuse"]))
    cyclic_context["metadata_path"] = str(metadata_path)
    cyclic["expectation"]["coverage_reuse"] = cyclic_context
    metadata_path.write_text(json.dumps(cyclic))
    with pytest.raises(ValueError, match="cyclic audit evidence"):
        runtime._load_evidence_source(source, require_normalized=True)
    metadata_path.write_bytes(original_metadata)
    assert runtime._load_evidence_source(source, require_normalized=True)[4] is not None
    followup = {
        "previous_repair": {"path": str(previous_path), "digest": digest_bytes(previous_path.read_bytes())},
        "finding_evidence_id": scientific["dispatch"]["evidence_id"],
        "reason": "Fix the affected scientific expression found during verification.",
    }
    control = tmp_path / "control.json"
    control.write_text(
        json.dumps(
            {
                **result["lifecycle_input"],
                "artifact_store": str(tmp_path / "control"),
                "action": "begin-repair",
                "authorization": "review-and-fix",
                "verification_followup": followup,
            }
        )
    )
    assert (
        runtime.main(
            [
                "review-control",
                "--input",
                str(control),
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--current-capture",
                result["capture_path"],
                "--output",
                str(tmp_path / "authorized.json"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["repair_epoch"] == 1
    repository = Path(request["new_capture"]["repository_root"])
    (repository / "state.rs").write_text("pub fn square(value: f64) -> f64 { value.powi(2) }\n")
    continuation: dict[str, Any] = {
        **request,
        **lifecycle,
        "previous_capture": result["capture"],
        "new_capture": _scope_data("git", repository, "baseline", None, ()),
        "changed_paths": ["state.rs"],
        "sources": [source],
        "verification_followup": followup,
    }
    expanded = deepcopy(continuation)
    original_untouched = (repository / "untouched.rs").read_bytes()
    (repository / "untouched.rs").write_text("pub fn identity(value: f64) -> f64 { value + 0.0 }\n")
    expanded["changed_paths"].append("untouched.rs")
    expanded["new_capture"] = _scope_data("git", repository, "baseline", None, ())
    with pytest.raises(ValueError, match="already repaired paths"):
        runtime.advance_after_mutation(expanded)
    (repository / "untouched.rs").write_bytes(original_untouched)
    stale = deepcopy(continuation)
    stale["verification_followup"]["finding_evidence_id"] = json.loads(Path(request["sources"][0]["metadata_path"]).read_bytes())["evidence"]["evidence_id"]
    with pytest.raises(ValueError, match="current completed review evidence"):
        runtime.advance_after_mutation(stale)
    second = runtime.advance_after_mutation(continuation)
    assert second["new_plan"]["review_lifecycle"]["repairs_completed"] == 1
    scientific_recheck = next(item for item in second["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "rust-scientific-correctness")
    assert runtime.reused_paths(scientific_recheck["dispatch"].get("coverage_reuse")) == ("untouched.rs",)
    assert second["repair_epoch"]["verification_followup"] == followup
    assert second["journal_path"] != result["journal_path"]
    second_path = tmp_path / "followup.json"
    second_path.write_text(json.dumps(second))
    repeated = {
        **continuation,
        **second["lifecycle_input"],
        "previous_capture": second["capture"],
        "verification_followup": {**followup, "previous_repair": {"path": str(second_path), "digest": digest_bytes(second_path.read_bytes())}},
    }
    from review_graph_repair_followup import verify_followup_origin  # noqa: PLC0415 - inspect the rejected boundary without performing another mutation.

    with pytest.raises(ValueError, match="one follow-up"):
        verify_followup_origin(repeated, repeated["verification_followup"])


def test_later_repair_cannot_drop_an_inherited_repository_dependency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    request, result, _metrics = _repair(tmp_path, capsys)
    scientific = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "rust-scientific-correctness")
    lifecycle = {**result["lifecycle_input"], "journal_path": result["journal_path"], "dispatches_path": result["dispatches_path"]}
    payload = {
        **_compact_audit_payload(scientific),
        "files_inspected": ["state.rs"],
        "validation_requirements": [
            {**item, "planned_validation_digest": scientific["dispatch"]["command_policy"]["planned_validation_units"][0]["planned_validation_digest"]}
            for item in scientific["dispatch"]["coverage_reuse"]["original_validation_requirements"]
        ],
    }
    source = _accept(lifecycle, scientific, payload)
    original = Path(source["metadata_path"]).read_bytes()
    identity = json.loads(original)["expectation"]["audit_input_identity"]
    assert identity["inspected_paths"] == ["state.rs"]
    assert identity["inherited_paths"] == ["untouched.rs"]
    assert "cliff.toml" in identity["inherited_dependency_paths"]
    repository = Path(result["capture"]["repository_root"])
    (repository / "cliff.toml").write_text("Changed inherited contract dependency.\n")
    continuation = {
        **request,
        **lifecycle,
        "previous_capture": result["capture"],
        "new_capture": _scope_data("git", repository, "baseline", None, ()),
        "changed_paths": ["cliff.toml"],
        "repair_epoch": 2,
        "sources": [source],
    }
    second = runtime.advance_after_mutation(continuation)
    replacement = next(item for item in second["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "rust-scientific-correctness")
    context = replacement["dispatch"]["coverage_reuse"]
    assert runtime.reused_paths(context) == ("state.rs",)
    assert next(unit for unit in context["units"] if unit["owned_paths"] == ["untouched.rs"])["disposition"] == "recheck"
    assert Path(source["metadata_path"]).read_bytes() == original
