"""Live repository regressions for partial coverage, external staging, and readiness."""

import json
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    _graph_plan,
    advance_after_mutation,
    append_journal_event,
    build_synthesis_bundle,
    compile_independent_review,
    compile_review,
    compile_validation,
    finalize_proof,
    main,
    materialize_dispatches,
    next_ready_nodes,
    read_execution_journal,
    resume_after_external_metadata,
)
from review_graph_schema import SchemaValidationError, require_schema_definition
from review_graph_synthesis import validate_synthesis
from test_review_graph_runtime import (
    INDEPENDENT_NATIVE_EXAMPLE,
    ROUTING_CATALOG,
    SCHEMA_ROOT,
    SKILL_ROOT,
    STATE_FIXTURE,
    _baseline_mutation_fixture,
    _json_plan,
    _publish_worker_bytes,
    _run_test_git,
    _sparse_plan_document,
)


def _payload(paths: list[str]) -> dict[str, Any]:
    return {
        "status": "no-findings",
        "files_inspected": paths,
        "findings": [],
        "changes": [],
        "handoffs": [],
        "limitations": [],
        "scope_limitations": [],
        "nearby_contract_owners": [],
        "validation_requirements": [],
        "commands_executed": [],
        "command_policy_attested": True,
    }


def _synthesis_payload(dispatch: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    records = [record for record in bundle["records"] if record["evidence_id"] in dispatch["predecessor_evidence_ids"]]
    findings = [
        {
            **{key: finding[key] for key in ("severity", "location", "summary", "evidence", "remediation")},
            "owner": record["skill_id"],
            "disposition": "remaining",
            "source_findings": [{"evidence_id": record["evidence_id"], "finding_id": finding["finding_id"]}],
        }
        for record in records
        for finding in record.get("findings", [])
    ]
    return {
        **_payload([]),
        "status": "completed" if findings else "no-findings",
        "findings": findings,
        "readiness_verdict": "not-ready" if findings else "ready",
        "verdict_reasons": ["Findings remain." if findings else "Required evidence reconciles."],
        "predecessor_coverage": [
            {"evidence_id": record["evidence_id"], "requirement_ids": record["requirement_ids"], "disposition": "reused" if record.get("reuse") else "accepted"}
            for record in records
        ],
        "routing_closure": {"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
        "validation_reconciliation": [
            {
                "evidence_id": record["evidence_id"],
                "requirement_ids": record["requirement_ids"],
                "result": record["status"],
                "platform": bundle["plan_context"]["validation_environments"][record["node_id"]]["platform"],
                "execution_mode": "native",
            }
            for record in records
            if record["record_type"] == "validation"
        ],
        "cross_surface_risks": [],
    }


def _materialize(tmp_path: Path, capture: dict[str, Any], plan: Any) -> tuple[dict[str, Any], dict[str, Any], Path]:
    state = [capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")]
    lifecycle = {"plan": _json_plan(plan), "source_state": state}
    entries = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "old"),
            "repository_root": capture["repository_root"],
            "authorization": "review-only",
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    dispatches = tmp_path / "dispatches.json"
    dispatches.write_text(json.dumps(entries))
    return lifecycle, entries, dispatches


@pytest.mark.parametrize("dependency", ["independent", "manifest", "uncertain"])
def test_manifest_delta_reuses_implementation_and_preserves_findings(tmp_path: Path, dependency: str) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "pyproject.toml").write_text('[project]\nname = "example"\nversion = "0.1.0"\ndependencies = []\n')
    _run_test_git(git, "-C", str(repository), "add", "pyproject.toml")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "manifest")
    template["routing_overrides"].append(
        {
            "catalog_id": "python.cli",
            "disposition": "selected",
            "reason": "CLI and installation contracts",
            "applicability_evidence": ["tool.py"],
            "owners": ["python"],
            "review_surface": ["tool.py", "pyproject.toml"],
        }
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["skill_id"] == "python-cli-review")
    payload = _payload(entry["dispatch"]["owned_paths"])
    payload.update(
        {
            "status": "completed",
            "findings": [
                {
                    "severity": "P2",
                    "location": "tool.py:1",
                    "summary": "Exit status contract is missing",
                    "evidence": "The tool does not implement its documented exit contract.",
                    "remediation": "Return the documented exit status.",
                }
            ],
            "coverage_units": [
                {"unit_id": "implementation", "owned_paths": ["tool.py"], "dependency_paths": [], "dependency_uncertainty": "", "finding_indices": [1]},
                {"unit_id": "installation", "owned_paths": ["pyproject.toml"], "dependency_paths": [], "dependency_uncertainty": "", "finding_indices": []},
            ],
        }
    )
    if dependency == "manifest":
        payload["coverage_units"][0]["dependency_paths"] = ["pyproject.toml"]
    elif dependency == "uncertain":
        payload["coverage_units"][0]["dependency_uncertainty"] = "Installation may affect command discovery."
    content, metadata = compile_review(
        {"dispatch": {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    original = Path(entry["artifact_path"]).read_bytes()
    (repository / "pyproject.toml").write_text('[project]\nname = "example"\nversion = "0.1.0"\ndependencies = ["rust-just==1.58.0"]\n')
    result = advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": ["pyproject.toml"],
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "sources": [{"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}],
        }
    )
    delta = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "python-cli-review")
    if dependency != "independent":
        assert "coverage_reuse" not in delta["dispatch"]
        decisions = next(item["units"] for item in result["coverage_reuse_decisions"] if item["node_id"] == delta["node_id"])
        assert all(unit["disposition"] == "recheck" and unit["reason"] for unit in decisions)
        assert set(delta["dispatch"]["owned_paths"]) == {"tool.py", "pyproject.toml"}
        return
    assert {unit["unit_id"]: unit["disposition"] for unit in delta["dispatch"]["coverage_reuse"]["units"]} == {
        "implementation": "reused",
        "installation": "recheck",
    }
    updated = {**_payload(["pyproject.toml"]), "status": "completed"}
    contract = json.loads(Path(delta["worker_payload_contract_path"]).read_text())
    require_schema_definition(contract, SCHEMA_ROOT / "runtime-operation-inputs-v1.schema.json", "stdinWorkerPayloadContract")
    _publish_worker_bytes(delta, json.dumps(updated).encode())
    state = result["new_source_state"]
    compiled, metadata = compile_review({"dispatch": {**delta["dispatch"], "before_state": state, "after_state": state}, "payload": updated})
    assert metadata["normalized_record"]["files_inspected"] == ["pyproject.toml"]
    assert metadata["normalized_record"]["findings"][0]["source_findings"][0]["evidence_id"] == entry["dispatch"]["evidence_id"]
    assert b"Exit status contract is missing" in compiled
    assert Path(entry["artifact_path"]).read_bytes() == original
    assert (
        main(
            [
                "compile-node",
                "--input",
                result["lifecycle_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--node-id",
                delta["node_id"],
                "--before-capture",
                result["capture_path"],
                "--after-capture",
                result["capture_path"],
                "--output",
                str(tmp_path / "delta-result.json"),
            ]
        )
        == 0
    )
    with pytest.raises(ValueError, match="structured scope limitation"):
        compile_review({"dispatch": {**delta["dispatch"], "before_state": state, "after_state": state}, "payload": {**_payload([]), "status": "completed"}})
    tampered = json.loads(json.dumps(delta["dispatch"]))
    tampered["coverage_reuse"]["units"][1]["disposition"] = "reused"
    with pytest.raises(ValueError, match="verified unit decisions"):
        compile_review({"dispatch": {**tampered, "before_state": state, "after_state": state}, "payload": updated})


def _staging_fixture(tmp_path: Path) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 2\n")
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    journal = tmp_path / "old.jsonl"
    audit = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    _publish_worker_bytes(audit, json.dumps(_payload(audit["dispatch"]["owned_paths"])).encode())
    append_journal_event(journal, lifecycle, JournalEventRequest(audit["node_id"], "in-flight"))
    _run_test_git(git, "-C", str(repository), "add", "tool.py")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "dispatches_path": str(dispatches),
        "journal_path": str(journal),
        "artifact_store": str(tmp_path / "resumed"),
    }
    return git, repository, request, audit, entries


@pytest.mark.parametrize("remaining_findings", [False, True])
def test_external_staging_between_dispatch_and_compile_completes_without_rollback(tmp_path: Path, remaining_findings: bool) -> None:  # noqa: PLR0915
    git, repository, request, audit, _entries = _staging_fixture(tmp_path)
    if remaining_findings:
        payload = _payload(audit["dispatch"]["owned_paths"])
        payload.update(
            {
                "status": "completed",
                "findings": [
                    {
                        "severity": "P2",
                        "location": "tool.py:1",
                        "summary": "Exit contract",
                        "evidence": "Failure exits zero.",
                        "remediation": "Set an error exit status.",
                    }
                ],
            }
        )
        _publish_worker_bytes(audit, json.dumps(payload).encode())
    result = resume_after_external_metadata(request)
    assert result["original_source_state"] != result["current_source_state"]
    assert audit["node_id"] in result["preserved_node_ids"]
    before = tmp_path / "before.json"
    before.write_text(json.dumps(request["previous_capture"]))
    argv = [
        "compile-node",
        "--input",
        result["lifecycle_input_path"],
        "--dispatches",
        result["dispatches_path"],
        "--journal",
        result["journal_path"],
        "--node-id",
        audit["node_id"],
        "--before-capture",
        str(before),
        "--after-capture",
        result["capture_path"],
        "--output",
        str(tmp_path / "first-result.json"),
    ]
    assert main(argv) == 0
    metadata = json.loads(Path(audit["metadata_path"]).read_text())
    assert metadata["evidence"]["fingerprints"]["before"] == result["original_source_state"]
    assert metadata["evidence"]["fingerprints"]["after"] == result["current_source_state"]
    assert metadata["evidence"]["git_mutated"] is False
    lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_text())
    plan = _graph_plan(lifecycle["plan"])
    sources = [{"artifact_path": audit["artifact_path"], "metadata_path": audit["metadata_path"]}]
    for _ in range(plan.complete_node_count):
        events, _states, _head = read_execution_journal(Path(result["journal_path"]), plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = next_ready_nodes(
            {**lifecycle, "current_source_state": result["current_source_state"]}, journal_events=events, dispatch_set=result["dispatch_set"]
        )
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready
        for entry in ready["ready_dispatches"]:
            dispatch = entry["dispatch"]
            workspace_args = []
            if entry["result_contract"] == "compact-validation":
                unit = dispatch["validation_unit"]
                payload = {
                    "status": "passed",
                    "limitations": [],
                    "executions": [
                        {
                            "command": command,
                            "working_directory": directory,
                            "executor": "fixture",
                            "result": "passed",
                            "exit_code": 0,
                            "elapsed": "0s",
                            "evidence": "true completed",
                            "artifact_paths": [],
                        }
                        for command, directory in zip(unit["commands"], unit["working_directories"], strict=True)
                    ],
                }
                for phase in ("before", "after"):
                    snapshot = tmp_path / f"{entry['node_id']}-{phase}.json"
                    assert (
                        main(
                            [
                                "snapshot-workspace",
                                "--input",
                                result["lifecycle_input_path"],
                                "--dispatches",
                                result["dispatches_path"],
                                "--node-id",
                                entry["node_id"],
                                "--current-capture",
                                result["capture_path"],
                                "--output",
                                str(snapshot),
                            ]
                        )
                        == 0
                    )
                    workspace_args.extend([f"--workspace-{phase}", str(snapshot)])
            elif dispatch["mode"] == "synthesis":
                payload = _synthesis_payload(dispatch, build_synthesis_bundle({**lifecycle, "sources": sources}))
            else:
                payload = _payload(dispatch["owned_paths"])
            _publish_worker_bytes(entry, json.dumps(payload).encode())
            assert (
                main(
                    [
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
                        str(tmp_path / f"{entry['node_id']}-result.json"),
                        *workspace_args,
                    ]
                )
                == 0
            )
            sources.append({"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]})
    proof = finalize_proof({**lifecycle, "current_source_state": result["current_source_state"], "sources": sources})
    assert proof["status"] == "complete", proof["blockers"]
    assert proof["repository_validation_status"] == "passed"
    assert proof["repository_readiness"] == ("not-ready" if remaining_findings else "ready")
    assert _scope_data(git, repository, "baseline", None, ())["index_fingerprint"] == request["new_capture"]["index_fingerprint"]
    template = _sparse_plan_document()
    template["consulted_routers"] = ["review-graph", "rust-review-orchestrator", "python-review-orchestrator"]
    template["routing_overrides"][0]["review_surface"] = ["state.rs"]
    template["validation_requirements"][0]["working_directories"] = [str(repository)]
    (repository / "tool.py").write_text("value = 3\n")
    advanced = advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": request["new_capture"],
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "changed_paths": ["tool.py"],
            "planning_template": template,
            "sources": sources,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "artifact_store": str(tmp_path / "after-staging-repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    assert advanced["status"] == "advanced"
    assert advanced["reused_evidence_ids"]


def test_independent_review_can_revalidate_on_resumed_metadata(tmp_path: Path) -> None:
    _git, _repository, request, _audit, _entries = _staging_fixture(tmp_path)
    resumed = resume_after_external_metadata(request)
    original, current = request["source_state"], resumed["current_source_state"]
    native = INDEPENDENT_NATIVE_EXAMPLE.read_text().replace(STATE_FIXTURE, "state.rs")
    native = native.replace("Scope fingerprint: scope", f"Scope fingerprint: {original[0]}")
    native = native.replace("Worktree fingerprint: worktree", f"Worktree fingerprint: {original[1]}")
    native = native.replace("Repository state fingerprint: repository", f"Repository state fingerprint: {original[2]}", 1)
    native = native.replace("Repository state fingerprint: repository", f"Repository state fingerprint: {current[2]}")
    dispatch = {
        "adversarial_checks": ["fallback absence and failure", "platform seams", "parser suffixes and error branches", "unexpected exception types"],
        "artifact_id": "artifact://independent-staging",
        "authorization": "review-only",
        "change_target": "git diff -- state.rs",
        "evidence_id": "review:independent-staging",
        "execution_location": "worker",
        "execution_profile": "grouped",
        "fresh_context": True,
        "handoff_catalog_ids": [],
        "mode": "independent-review",
        "node_id": "independent-staging",
        "planned_path_line_bounds": [["state.rs", 1]],
        "planned_paths": ["state.rs"],
        "reference_paths": [],
        "requirement_ids": ["repo.independent"],
        "selection_reason": "concrete worktree change",
        "skill_id": "repository-independent-review",
        "skill_path": str(SKILL_ROOT / "repository-independent-review" / "SKILL.md"),
        "source_state": original,
        "before_state": current,
        "after_state": current,
        "worker_created": True,
        "external_metadata_transitions": resumed["lifecycle_input"]["external_metadata_transitions"],
    }
    content, metadata = compile_independent_review({"dispatch": dispatch, "limitations": [], "status": "no-findings"}, native.encode())
    assert metadata["normalized_record"]["observed_source_state"] == current
    assert b"External metadata transitions:" in content


def test_compound_git_command_is_rechecked_after_staging(tmp_path: Path) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    payload = _payload(audit["dispatch"]["owned_paths"])
    payload["commands_executed"] = ["rg value tool.py && git diff --cached --stat"]
    content, metadata = compile_review(
        {"dispatch": {**audit["dispatch"], "before_state": request["source_state"], "after_state": request["source_state"]}, "payload": payload}
    )
    Path(audit["artifact_path"]).write_bytes(content)
    Path(audit["metadata_path"]).write_text(json.dumps(metadata))
    append_journal_event(
        Path(request["journal_path"]),
        request,
        JournalEventRequest(audit["node_id"], "accepted", source={"artifact_path": audit["artifact_path"], "metadata_path": audit["metadata_path"]}),
    )
    resumed = resume_after_external_metadata(request)
    assert audit["node_id"] in resumed["recheck_node_ids"]
    assert audit["node_id"] not in resumed["preserved_node_ids"]


@pytest.mark.parametrize("mode", ["staged", "branch"])
def test_external_metadata_resume_rejects_git_sensitive_scope(tmp_path: Path, mode: str) -> None:
    git, repository, request, _audit, _entries = _staging_fixture(tmp_path)
    base = "HEAD" if mode == "branch" else None
    request["previous_capture"] = _scope_data(git, repository, mode, base, ())
    request["new_capture"] = request["previous_capture"]
    with pytest.raises(ValueError, match="staged and branch targets"):
        resume_after_external_metadata(request)


def test_external_metadata_resume_rejects_content_changes(tmp_path: Path) -> None:
    git, repository, request, _audit, _entries = _staging_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 3\n")
    request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
    with pytest.raises(ValueError, match="only the index"):
        resume_after_external_metadata(request)


def test_synthesis_cannot_use_generic_payload_or_ready_with_remaining_findings(tmp_path: Path) -> None:
    _git, _repository, _template, capture, plan = _baseline_mutation_fixture(tmp_path)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "synthesis")
    dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
    assert dispatch["payload_schema"]["id"].endswith("synthesis-payload-v1.schema.json")
    with pytest.raises(SchemaValidationError, match="readiness_verdict"):
        compile_review({"dispatch": dispatch, "payload": _payload([])})
    payload = {
        **_payload([]),
        "status": "completed",
        "readiness_verdict": "not-ready",
        "verdict_reasons": ["Exit contract remains broken."],
        "predecessor_coverage": [{"evidence_id": key, "requirement_ids": [], "disposition": "accepted"} for key in dispatch["predecessor_evidence_ids"]],
        "routing_closure": {"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
        "validation_reconciliation": [],
        "cross_surface_risks": [],
        "findings": [
            {
                "severity": "P2",
                "location": "tool.py:1",
                "summary": "Exit contract",
                "evidence": "Failure exits zero.",
                "remediation": "Set an error exit status.",
                "owner": "python-cli-review",
                "disposition": "remaining",
                "source_findings": [],
            }
        ],
    }
    _content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
    assert metadata["evidence"]["status"] == "completed"
    assert metadata["normalized_record"]["readiness_verdict"] == "not-ready"
    with pytest.raises(ValueError, match="ready synthesis contradicts"):
        compile_review({"dispatch": dispatch, "payload": {**payload, "readiness_verdict": "ready"}})


@pytest.mark.parametrize("transition", [{}, {"before": {}}, {"before": None, "after": {}}])
def test_malformed_metadata_transition_is_a_cli_error_without_publication(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], transition: dict[str, Any]
) -> None:
    git, repository, request, _audit, _entries = _staging_fixture(tmp_path)
    request["external_metadata_transitions"] = [transition]
    request_path = tmp_path / "malformed.json"
    request_path.write_text(json.dumps(request))
    output = tmp_path / "result.json"
    assert main(["resume-after-external-metadata", "--input", str(request_path), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "before and after snapshot objects" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()
    assert not Path(request["artifact_store"]).exists()
    assert _scope_data(git, repository, "baseline", None, ())["index_fingerprint"] == request["new_capture"]["index_fingerprint"]


@pytest.mark.parametrize("staged_before_repairs", [False, True])
def test_partitioned_audit_retains_original_capture_across_multiple_repairs(tmp_path: Path, staged_before_repairs: bool) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "pyproject.toml").write_text('[project]\nname="example"\nversion="0.1.0"\n')
    _run_test_git(git, "-C", str(repository), "add", "pyproject.toml")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "manifest")
    (repository / "tool.py").write_text("value = 2\n")
    template["routing_overrides"].append(
        {
            "catalog_id": "python.cli",
            "disposition": "selected",
            "reason": "CLI and manifest contracts",
            "applicability_evidence": ["tool.py"],
            "owners": ["python"],
            "review_surface": ["tool.py", "pyproject.toml"],
        }
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["skill_id"] == "python-cli-review")
    payload = _payload(entry["dispatch"]["owned_paths"])
    payload["coverage_units"] = [
        {"unit_id": path, "owned_paths": [path], "dependency_paths": [], "dependency_uncertainty": "", "finding_indices": []}
        for path in ("tool.py", "pyproject.toml")
    ]
    content, metadata = compile_review(
        {"dispatch": {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    sources = [{"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}]
    origin = capture
    if staged_before_repairs:
        _run_test_git(git, "-C", str(repository), "add", "tool.py")
        capture = _scope_data(git, repository, "baseline", None, ())
        lifecycle["external_metadata_transitions"] = [{"before": origin, "after": capture}]
    repairs: list[dict[str, Any]] = []
    for epoch, (path, replacement) in enumerate(
        [("state.rs", "pub fn changed() {}\n"), ("pyproject.toml", '[project]\nname="example"\nversion="0.2.0"\n')], start=1
    ):
        (repository / path).write_text(replacement)
        after = _scope_data(git, repository, "baseline", None, ())
        result = advance_after_mutation(
            {
                **lifecycle,
                "previous_capture": capture,
                "new_capture": after,
                "planning_template": template,
                "authorization_before": "review-and-fix",
                "authorization_after": "review-and-fix",
                "repair_epoch": epoch,
                "changed_paths": [path],
                "artifact_store": str(tmp_path / f"repair-{epoch}"),
                "state_verification_command": "capture_scope.py --mode baseline",
                "sources": sources,
            }
        )
        assert result["status"] == "advanced"
        repairs.append(result)
        if epoch == 1:
            assert result["reused_evidence_ids"] == [entry["dispatch"]["evidence_id"]]
        lifecycle = json.loads(Path(result["lifecycle_input_path"]).read_text())
        capture = after
    result = repairs[-1]
    delta = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "python-cli-review")
    context = delta["dispatch"]["coverage_reuse"]
    assert context["origin"]["repository_state_fingerprint"] == origin["repository_state_fingerprint"]
    assert {unit["unit_id"]: unit["disposition"] for unit in context["units"]} == {"tool.py": "reused", "pyproject.toml": "recheck"}
    state = result["new_source_state"]
    _content, updated = compile_review(
        {"dispatch": {**delta["dispatch"], "before_state": state, "after_state": state}, "payload": _payload(["pyproject.toml"])}
    )
    assert updated["normalized_record"]["files_inspected"] == ["pyproject.toml"]
    assert Path(entry["artifact_path"]).read_bytes() == content
    assert _scope_data(git, repository, "baseline", None, ())["index_fingerprint"] == capture["index_fingerprint"]


def test_synthesis_uses_bound_validator_platform_and_exposes_execution_configuration(tmp_path: Path) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    template["validation_requirements"][0].update(
        {"platform": "macos-arm64", "environment": "Linux boundary emulation on macOS", "features": ["mode=emulated"]}
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    unit = entry["dispatch"]["validation_unit"]
    executions = [
        {
            "command": command,
            "working_directory": directory,
            "executor": "macOS fixture",
            "result": "passed",
            "exit_code": 0,
            "elapsed": "0s",
            "evidence": "Modeled Linux boundary passed on macOS.",
            "artifact_paths": [],
        }
        for command, directory in zip(unit["commands"], unit["working_directories"], strict=True)
    ]
    content, metadata = compile_validation(
        {
            "dispatch": {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]},
            "payload": {"status": "passed", "limitations": ["Linux boundary emulation only."], "executions": executions},
        }
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    bundle = build_synthesis_bundle({**lifecycle, "sources": [{"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"]}]})
    configuration = bundle["plan_context"]["validation_environments"][entry["node_id"]]
    assert configuration["platform"] == "macos-arm64"
    assert configuration["environment"] == "Linux boundary emulation on macOS"
    assert configuration["features"] == ["mode=emulated"]
    predecessor = entry["dispatch"]["evidence_id"]
    payload = _synthesis_payload({"predecessor_evidence_ids": [predecessor]}, bundle)
    payload["validation_reconciliation"][0]["execution_mode"] = "emulated"
    validate_synthesis(payload, (predecessor,), bundle)
    payload["validation_reconciliation"][0]["platform"] = "linux-native"
    with pytest.raises(ValueError, match="bound executor environment"):
        validate_synthesis(payload, (predecessor,), bundle)
