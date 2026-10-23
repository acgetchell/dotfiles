"""Real Git handoffs preserve source evidence and require exact-commit native CI."""

import json
import shutil
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _run_git, _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_commit import _unchanged_comparison, verify_live_commit
from review_graph_integrity import digest_bytes
from review_graph_plan import plan_from_document
from review_graph_reuse import metadata_transition, source_snapshot
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compact_independent_payload,
    _complete_structural_fixture_routing,
    _publish_worker_bytes,
    _run_test_git,
)
from test_review_graph_transitions import _materialize, _payload, _synthesis_payload
from test_support_review_graph import _prepare_fixture_timing


def _save(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path, payload: dict[str, Any]) -> dict[str, str]:
    state = lifecycle.get("current_source_state", lifecycle["source_state"])
    dispatch = {**entry["dispatch"], "before_state": state, "after_state": state, "source_capture": lifecycle.get("capture", lifecycle.get("new_capture"))}
    compiler = {
        "audit": runtime.compile_review,
        "synthesis": runtime.compile_review,
        "independent-review": runtime.compile_independent_payload,
        "validation": runtime.compile_validation,
    }[dispatch["mode"]]
    content, metadata = compiler({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source: dict[str, str] = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    runtime.append_journal_event(
        journal,
        lifecycle,
        runtime.JournalEventRequest(
            entry["node_id"],
            "blocked" if payload["status"] == "blocked" else "accepted",
            source=source,
            reason="Native CI requires an authorized published commit." if payload["status"] == "blocked" else None,
        ),
    )
    return source


def _validation_payload(entry: dict[str, Any], *, blocked: bool = False) -> dict[str, Any]:
    unit = entry["dispatch"]["validation_unit"]
    return {
        "schema_version": 3,
        "status": "blocked" if blocked else "passed",
        "artifacts": [],
        "limitations": ["Native CI unavailable before authorized commit and push."] if blocked else [],
        "executions": [
            {
                "command": command,
                "working_directory": directory,
                "executor": "fixture",
                "result": "blocked" if blocked else "passed",
                "evidence": "Unavailable before commit" if blocked else "Fixture completed",
                "exit_code": None if blocked else 0,
                "elapsed": "0s",
                "artifact_paths": [],
            }
            for command, directory in zip(unit["commands"], unit["working_directories"], strict=True)
        ],
    }


def _commit_audit_payload(dispatch: dict[str, Any], *, mode: str, change_target: str) -> dict[str, Any]:
    payload = _payload(dispatch["owned_paths"], dispatch=dispatch)
    if mode == "branch":
        payload.update(
            commands_executed=[change_target],
            git_dependencies=[{"kind": "head", "command": change_target, "reason": "Compare inspected bytes against the immutable branch base."}],
        )
    return payload


def _commit_fixture(  # noqa: PLR0915 - complete real-Git execution and handoff fixture.
    tmp_path: Path, *, mode: str = "baseline", git_sensitive_review: bool = False
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "justfile").write_text("ci:\n    test -f tool.py\n")
    (repository / "review-validation-contracts.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contracts": [
                    {
                        "contract_id": "fixture-ci",
                        "commands": ["just ci"],
                        "working_directories": ["."],
                        "implementation_paths": ["justfile"],
                        "input_scope": "repository",
                        "input_prefixes": [],
                        "git_inputs": [],
                        "deterministic": True,
                        "rationale": "The fixture recipe checks file existence only.",
                    }
                ],
            }
        )
    )
    _run_test_git(git, "-C", str(repository), "add", "justfile")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "CI recipe")
    (repository / "tool.py").write_text("value = 2\n")
    (repository / "state.rs").write_text("pub fn state() { let value = 2; }\n")
    template.update(concrete_change_target=True, change_target="git diff HEAD -- tool.py state.rs")
    local = template["validation_requirements"][0]
    local.update(commands=["just ci"], canonical_recipe="just ci")
    native = deepcopy(local)
    native.update(
        requirement_id="native-ci", commands=["native-ci-pending"], canonical_recipe=None, baseline=False, environment="native Linux", platform="linux"
    )
    template["validation_requirements"].append(native)
    template["pre_review_validation_requirement_ids"] = [local["requirement_id"]]
    base_ref = _run_git(git, repository, ("rev-parse", "HEAD^")).decode().strip() if mode == "branch" else None
    capture = _scope_data(git, repository, mode, base_ref, ())
    if mode == "branch":
        template["change_target"] = f"git diff {capture['merge_base']} -- tool.py state.rs"
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, dispatch_set, dispatches = _materialize(tmp_path, capture, plan)
    lifecycle["capture"] = capture
    entries = {entry["node_id"]: entry for entry in dispatch_set["dispatches"]}
    journal = tmp_path / "original.jsonl"
    local_entry = next(entry for entry in entries.values() if entry["dispatch"].get("validation_unit", {}).get("baseline"))
    native_entry = next(entry for entry in entries.values() if entry["dispatch"]["mode"] == "validation" and entry != local_entry)
    just = shutil.which("just")
    assert just is not None
    subprocess.run([just, "ci"], cwd=repository, check=True, capture_output=True)  # noqa: S603 - fixed fixture command.
    sources = {local_entry["node_id"]: _save(local_entry, lifecycle, journal, _validation_payload(local_entry))}
    for entry in entries.values():
        dispatch = entry["dispatch"]
        if dispatch["mode"] == "audit":
            payload = _commit_audit_payload(dispatch, mode=mode, change_target=template["change_target"])
            planned = next(unit for unit in dispatch["command_policy"]["planned_validation_units"] if "native-ci" in unit["requirement_ids"])
            payload["validation_requirements"] = [
                {
                    "requirement_id": "native-ci",
                    "planned_validation_digest": planned["planned_validation_digest"],
                    "owner": dispatch["skill_id"],
                    "reason": "Native target behavior requires CI",
                    "expected_evidence": "Native CI passes",
                }
            ]
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, payload)
        elif dispatch["mode"] == "independent-review":
            payload = _compact_independent_payload(dispatch)
            if git_sensitive_review:
                payload["commands_executed"] = ["git log -1"]
                payload["git_dependencies"] = [{"kind": "history", "command": "git log -1", "reason": "Inspect the commit history."}]
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, payload)
        elif dispatch["mode"] == "validation" and entry != local_entry:
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, _validation_payload(entry, blocked=True))
    _run_test_git(git, "-C", str(repository), "switch", "-c", "fix/reviewed-commit")
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Reviewed source")
    current = _scope_data(git, repository, mode, base_ref, ())
    lifecycle.pop("capture")
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": current,
        "journal_path": str(journal),
        "dispatches_path": str(dispatches),
        "artifact_store": str(tmp_path / "handoff"),
        "authorization": {
            "operation": "branch-commit",
            "repository_root": str(repository),
            "branch": current["branch"],
            "source_state": lifecycle["source_state"],
            "user_authorization": "Commit these reviewed changes on fix/reviewed-commit and push.",
        },
        "independent_reviews": {
            entry["node_id"]: {
                "change_target": entry["dispatch"]["change_target"],
                "comparison_commit": capture["merge_base"] if mode == "branch" else capture["head"],
                "reason": "Same captured worktree compared with the same immutable HEAD.",
            }
            for entry in entries.values()
            if entry["dispatch"]["mode"] == "independent-review"
        },
        "native_ci": {native_entry["node_id"]: {"commands": [f"native-ci --commit {current['head']}"], "checks": [{"name": "CI", "target": "linux"}]}},
    }
    if git_sensitive_review:
        request["independent_reviews"] = {}
    return request, entries, sources


def _assert_original_comparison(request: dict[str, Any], dispatch: dict[str, Any]) -> None:
    comparison = request["previous_capture"]["merge_base"] or request["previous_capture"]["head"]
    target = f"git diff {comparison} -- tool.py state.rs"
    assert dispatch["change_target"] == target
    git = shutil.which("git")
    assert git is not None
    diff = _run_git(git, Path(request["new_capture"]["repository_root"]), ("diff", comparison, "--", "tool.py"))
    assert b"+value = 2" in diff


def test_reused_audit_native_requirement_survives_a_repair_then_commit(tmp_path: Path) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    native = deepcopy(template["validation_requirements"][0])
    native.update(
        requirement_id="native-ci", commands=["native-ci-pending"], canonical_recipe=None, baseline=False, environment="native Linux", platform="linux"
    )
    template["validation_requirements"].append(native)
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, dispatch_set, _dispatches = _materialize(tmp_path, capture, plan)
    audit = next(entry for entry in dispatch_set["dispatches"] if entry["dispatch"]["skill_id"] == "rust-invariant-state-transitions")
    payload = _payload(audit["dispatch"]["owned_paths"], dispatch=audit["dispatch"])
    planned = next(unit for unit in audit["dispatch"]["command_policy"]["planned_validation_units"] if "native-ci" in unit["requirement_ids"])
    payload["validation_requirements"] = [
        {
            "requirement_id": "native-ci",
            "planned_validation_digest": planned["planned_validation_digest"],
            "owner": audit["dispatch"]["skill_id"],
            "reason": "Native target behavior requires CI",
            "expected_evidence": "Native CI passes",
        }
    ]
    source = _save(audit, lifecycle, tmp_path / "original.jsonl", payload)
    original_bytes = {path: Path(path).read_bytes() for path in source.values()}
    (repository / "tool.py").write_text("value = 2\n")
    repaired_capture = _scope_data(git, repository, "baseline", None, ())
    advanced = runtime.advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": repaired_capture,
            "changed_paths": ["tool.py"],
            "planning_template": template,
            "sources": [source],
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    assert advanced["reused_evidence_ids"] == [audit["dispatch"]["evidence_id"]]
    native_entry = next(
        entry for entry in advanced["dispatch_set"]["dispatches"] if "native-ci" in entry["dispatch"].get("validation_unit", {}).get("requirement_ids", [])
    )
    _run_test_git(git, "-C", str(repository), "switch", "-c", "fix/repair-then-commit")
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Reviewed repair")
    committed_capture = _scope_data(git, repository, "baseline", None, ())
    result = runtime.resume_after_authorized_commit(
        {
            **advanced["lifecycle_input"],
            "previous_capture": repaired_capture,
            "new_capture": committed_capture,
            "journal_path": advanced["journal_path"],
            "dispatches_path": advanced["dispatches_path"],
            "artifact_store": str(tmp_path / "handoff"),
            "authorization": {
                "operation": "branch-commit",
                "repository_root": str(repository),
                "branch": committed_capture["branch"],
                "source_state": advanced["new_source_state"],
                "user_authorization": "Commit the reviewed repair.",
            },
            "native_ci": {
                native_entry["node_id"]: {"commands": [f"native-ci --commit {committed_capture['head']}"], "checks": [{"name": "CI", "target": "linux"}]}
            },
        }
    )
    assert result["lifecycle_input"]["plan"]["review_lifecycle"]["repairs_completed"] == 1
    assert result["lifecycle_input"]["plan"]["review_lifecycle"]["repair_budget"] == 2
    bundle = runtime.build_synthesis_bundle(result["lifecycle_input"])
    reconciliation = bundle["plan_context"]["validation_reconciliation"]
    assert reconciliation["blockers"] == []
    assert len(reconciliation["requirements"]) == 1
    requirement = reconciliation["requirements"][0]
    assert requirement["resolution"] == "planned"
    binding = requirement["commit_handoff_binding"]
    assert binding["commit"] == committed_capture["head"]
    assert binding["original_planned_validation_digest"] == planned["planned_validation_digest"]
    assert binding["reuse_binding"]["original_source_state"] == lifecycle["source_state"]
    assert binding["reuse_binding"]["replacement_source_state"] == advanced["new_source_state"]
    resumed_plan = runtime._graph_plan(result["lifecycle_input"]["plan"])
    record = json.loads(Path(source["metadata_path"]).read_bytes())["normalized_record"]
    unproved = runtime._validation_reconciliation(replace(resumed_plan, audit_reuse_transitions=()), [record])
    assert unproved["requirements"][0]["resolution"] == "identity-conflict"
    assert unproved["blockers"]
    for path, content in original_bytes.items():
        assert Path(path).read_bytes() == content


def _native_synthesis_payload(dispatch: dict[str, Any], bundle: dict[str, Any], head: str) -> dict[str, Any]:
    reconciliation = bundle["plan_context"]["validation_reconciliation"]
    assert reconciliation["blockers"] == []
    assert reconciliation["requirements"]
    assert all(item["resolution"] == "planned" for item in reconciliation["requirements"])
    assert all(item["commit_handoff_binding"]["commit"] == head for item in reconciliation["requirements"])
    return _synthesis_payload(dispatch, bundle)


@pytest.mark.parametrize("mode", ["baseline", "worktree", "branch"])
@pytest.mark.parametrize("git_sensitive_review", [False, True])
def test_commit_handoff_preserves_evidence_and_finalizes_exact_commit(  # noqa: PLR0915 - full commit handoff and certification scenario.
    tmp_path: Path, mode: str, git_sensitive_review: bool
) -> None:
    request, entries, sources = _commit_fixture(tmp_path, mode=mode, git_sensitive_review=git_sensitive_review)
    originals = {path: Path(path).read_bytes() for source in sources.values() for path in source.values()}
    with pytest.raises(ValueError, match=r"only the index|require replanning"):
        runtime.resume_after_external_metadata(request)
    result = runtime.resume_after_authorized_commit(request)
    native_id = next(iter(request["native_ci"]))
    rechecked = {native_id} | {node_id for node_id, entry in entries.items() if git_sensitive_review and entry["dispatch"]["mode"] == "independent-review"}
    assert set(result["preserved_node_ids"]) == set(sources) - rechecked
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    sources = {key: source for key, source in sources.items() if key not in rechecked}
    journal = Path(result["journal_path"])
    plan = runtime._graph_plan(lifecycle["plan"])
    _prepare_fixture_timing(next(entry for entry in result["dispatch_set"]["dispatches"] if entry["node_id"] == native_id))
    for _ in range(plan.complete_node_count + 1):
        events, _states, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
        ready = runtime.next_ready_nodes(lifecycle, journal_events=events, dispatch_set=result["dispatch_set"])
        if ready["complete"]:
            break
        assert ready["ready_dispatches"], ready
        for entry in ready["ready_dispatches"]:
            if entry["node_id"] == native_id:
                payload = _validation_payload(entry)
                payload["native_ci"] = [
                    {"name": "CI", "target": "linux", "head_sha": request["new_capture"]["head"], "conclusion": "success", "url": "https://example.com/runs/1"}
                ]
                _publish_worker_bytes(entry, json.dumps(payload).encode())
                workspace_arguments = []
                for phase in ("before", "after"):
                    snapshot = tmp_path / f"workspace-{phase}.json"
                    assert (
                        runtime.main(
                            [
                                "snapshot-workspace",
                                "--input",
                                result["lifecycle_input_path"],
                                "--dispatches",
                                result["dispatches_path"],
                                "--node-id",
                                native_id,
                                "--current-capture",
                                result["capture_path"],
                                "--output",
                                str(snapshot),
                            ]
                        )
                        == 0
                    )
                    workspace_arguments.extend([f"--workspace-{phase}", str(snapshot)])
                assert (
                    runtime.main(
                        [
                            "compile-node",
                            "--input",
                            result["lifecycle_input_path"],
                            "--dispatches",
                            result["dispatches_path"],
                            "--journal",
                            result["journal_path"],
                            "--node-id",
                            native_id,
                            "--before-capture",
                            result["capture_path"],
                            "--after-capture",
                            result["capture_path"],
                            "--output",
                            str(tmp_path / "native-compiled.json"),
                            *workspace_arguments,
                        ]
                    )
                    == 0
                )
                sources[entry["node_id"]] = {key: entry[key] for key in ("artifact_path", "metadata_path")}
                continue
            if entry["dispatch"]["mode"] == "synthesis":
                bundle = runtime.build_synthesis_bundle({**lifecycle, "sources": list(sources.values())})
                payload = _native_synthesis_payload(entry["dispatch"], bundle, request["new_capture"]["head"])
            elif entry["dispatch"]["mode"] == "independent-review":
                _assert_original_comparison(request, entry["dispatch"])
                payload = _compact_independent_payload(entry["dispatch"])
                payload.update(before_state=result["current_source_state"], after_state=result["current_source_state"])
            else:
                pytest.fail(f"Unexpected replay: {entry['node_id']}")
            sources[entry["node_id"]] = _save(entry, lifecycle, journal, payload)
    proof = runtime.finalize_proof({**lifecycle, "sources": list(sources.values())})
    assert proof["graph_proof_status"] == "complete", proof["blockers"]
    assert proof["repository_validation_status"] == "passed"
    assert all(item["commit_handoff_binding"]["commit"] == request["new_capture"]["head"] for item in proof["validation_reconciliation"]["requirements"])
    assert proof["independent_review_metrics"]["accepted_evidence_count"] > 0
    for path, content in originals.items():
        assert Path(path).read_bytes() == content
    history = result["lifecycle_input"]["external_metadata_transitions"][-1]["commit_handoff"]
    assert any("journal_path" in item["path"] for item in history["preserved_files"])
    Path(history["preserved_files"][0]["path"]).chmod(0o644)
    Path(history["preserved_files"][0]["path"]).write_text("changed")
    with pytest.raises(ValueError, match="history missing or changed"):
        runtime.finalize_proof({**lifecycle, "sources": list(sources.values())})


@pytest.mark.parametrize("damage", ["authorization", "content", "mode", "new-path", "live-drift", "execution", "comparison", "native-sha"])
def test_handoff_rejects_unproved_transition(tmp_path: Path, damage: str) -> None:
    request, _entries, _sources = _commit_fixture(tmp_path)
    repository = Path(request["new_capture"]["repository_root"])
    git = shutil.which("git")
    assert git is not None
    if damage == "authorization":
        request["authorization"]["branch"] = "unauthorized-branch"
    elif damage in {"content", "mode", "new-path"}:
        if damage == "mode":
            (repository / "tool.py").chmod(0o755)
        else:
            (repository / ("tool.py" if damage == "content" else "new.txt")).write_text("unreviewed\n")
        _run_test_git(git, "-C", str(repository), "add", ".")
        _run_test_git(git, "-C", str(repository), "commit", "--amend", "--no-edit")
        request["new_capture"] = _scope_data(git, repository, "baseline", None, ())
        next(iter(request["native_ci"].values()))["commands"] = [f"native-ci --commit {request['new_capture']['head']}"]
    elif damage == "live-drift":
        (repository / "tool.py").write_text("uncommitted drift\n")
    elif damage == "execution":
        request["local_validation"] = {}
    elif damage == "comparison":
        next(iter(request["independent_reviews"].values()))["comparison_commit"] = request["new_capture"]["head"]
    else:
        next(iter(request["native_ci"].values()))["commands"] = [f"native-ci --commit {request['previous_capture']['head']}"]
    with pytest.raises(ValueError, match=r"handoff|reuse|replacement|local_validation"):
        runtime.resume_after_authorized_commit(request)
    assert not Path(request["artifact_store"]).exists()


@pytest.mark.parametrize("damage", ["old-sha", "wrong-target", "skipped", "missing", "duplicate"])
def test_native_ci_requires_every_target_on_exact_commit(tmp_path: Path, damage: str) -> None:
    request, _entries, _sources = _commit_fixture(tmp_path)
    result = runtime.resume_after_authorized_commit(request)
    native_id = next(iter(request["native_ci"]))
    entry = next(item for item in result["dispatch_set"]["dispatches"] if item["node_id"] == native_id)
    payload = _validation_payload(entry)
    check = {"name": "CI", "target": "linux", "head_sha": request["new_capture"]["head"], "conclusion": "success", "url": "https://example.com/runs/1"}
    if damage == "old-sha":
        check["head_sha"] = request["previous_capture"]["head"]
    elif damage == "wrong-target":
        check["target"] = "emulated-linux"
    elif damage == "skipped":
        check["conclusion"] = "skipped"
    payload["native_ci"] = [] if damage == "missing" else [check, check] if damage == "duplicate" else [check]
    dispatch = {**entry["dispatch"], "before_state": result["current_source_state"], "after_state": result["current_source_state"]}
    with pytest.raises(ValueError, match="exact-commit"):
        runtime.compile_validation({"dispatch": dispatch, "payload": payload})


def test_history_symlink_cannot_write_into_reviewed_source(tmp_path: Path) -> None:
    request, _entries, _sources = _commit_fixture(tmp_path)
    root = Path(request["artifact_store"])
    root.mkdir()
    repository = Path(request["new_capture"]["repository_root"])
    (root / "commit-history").symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="must not traverse symlinks"):
        runtime.resume_after_authorized_commit(request)
    git = shutil.which("git")
    assert git is not None
    assert _scope_data(git, repository, "baseline", None, ()) == request["new_capture"]


@pytest.mark.parametrize("damage", ["empty", "array", "authorization", "policy", "native", "file", "missing-history"])
def test_malformed_handoff_has_a_boundary_error_and_preserves_cli_output(tmp_path: Path, capsys: pytest.CaptureFixture[str], damage: str) -> None:
    request, _entries, _sources = _commit_fixture(tmp_path)
    result = runtime.resume_after_authorized_commit(request)
    lifecycle = deepcopy(result["lifecycle_input"])
    transition = lifecycle["plan"]["commit_handoffs"][-1]
    proof = transition["commit_handoff"]
    if damage == "empty":
        transition["commit_handoff"] = {}
    elif damage == "array":
        transition["commit_handoff"] = []
    elif damage == "authorization":
        proof["authorization"] = []
    elif damage == "policy":
        next(iter(proof["preserved_evidence"].values()))["policy"] = []
    elif damage == "native":
        proof["native_ci"] = {"invalid": []}
    elif damage == "file":
        proof["preserved_files"] = [{}]
    else:
        proof["preserved_files"] = [item for item in proof["preserved_files"] if not item["path"].endswith("reconciliation.json")]
    with pytest.raises(ValueError, match="commit"):
        metadata_transition(transition)
    input_path, output_path = tmp_path / "malformed.json", tmp_path / "existing.json"
    input_path.write_text(json.dumps(lifecycle))
    output_path.write_text("Keep the previous proof.\n")
    assert runtime.main(["finalize-proof", "--input", str(input_path), "--current-capture", result["capture_path"], "--output", str(output_path)]) == 2
    diagnostic = capsys.readouterr().err
    assert diagnostic.strip()
    assert "Traceback" not in diagnostic
    assert "commit" in diagnostic
    assert output_path.read_text() == "Keep the previous proof.\n"


@pytest.mark.parametrize("damage", ["root", "policies", "record", "plan", "duplicate"])
def test_malformed_retained_handoff_history_is_rejected(tmp_path: Path, damage: str) -> None:
    request, _entries, _sources = _commit_fixture(tmp_path)
    result = runtime.resume_after_authorized_commit(request)
    transition = result["lifecycle_input"]["plan"]["commit_handoffs"][-1]
    proof = transition["commit_handoff"]
    if damage == "duplicate":
        proof["preserved_files"].append(proof["preserved_files"][0])
    else:
        policy = next(iter(proof["preserved_evidence"].values()))
        name = "plan.json" if damage == "plan" else policy["node_id"] + ".metadata_path" if damage == "record" else "reconciliation.json"
        item = next(item for item in proof["preserved_files"] if Path(item["path"]).name == name)
        path = Path(item["path"])
        content = json.loads(path.read_bytes())
        if damage == "root":
            content = []
        elif damage == "policies":
            content[policy["kind"]] = []
        elif damage == "record":
            content["normalized_record"] = []
        else:
            content["coalesced_validation_units"] = [[]]
        path.chmod(0o644)
        path.write_text(json.dumps(content))
        item["digest"] = digest_bytes(path.read_bytes())
    with pytest.raises((TypeError, ValueError), match="commit handoff history"):
        metadata_transition(transition)


def test_committed_symlink_identity_and_executable_mode(tmp_path: Path) -> None:
    git, repository, _template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "link").symlink_to("tool.py")
    (repository / "tool.py").chmod(0o755)
    before = _scope_data(git, repository, "baseline", None, ())
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Reviewed modes and link")
    after = _scope_data(git, repository, "baseline", None, ())
    assert verify_live_commit(before, after) == before["head"]
    assert before["repository_path_fingerprints"] == after["repository_path_fingerprints"]


def test_committed_branch_deletion_preserves_absent_path_identity(tmp_path: Path) -> None:
    git, repository, _template, initial, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").unlink()
    before = _scope_data(git, repository, "branch", initial["head"], ())
    _run_test_git(git, "-C", str(repository), "add", "-u")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Reviewed deletion")
    after = _scope_data(git, repository, "branch", initial["head"], ())

    assert dict(source_snapshot(before).repository_path_fingerprints)["tool.py"] == "absent"
    assert after["repository_path_fingerprints"] == before["repository_path_fingerprints"]
    assert verify_live_commit(before, after) == before["head"]


def test_missing_tracked_path_is_not_a_committed_deletion(tmp_path: Path) -> None:
    git, repository, _template, initial, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "state.rs").write_text("pub fn changed() {}\n")
    before = _scope_data(git, repository, "branch", initial["head"], ())
    _run_test_git(git, "-C", str(repository), "add", "state.rs")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Reviewed state change")
    _run_test_git(git, "-C", str(repository), "update-index", "--skip-worktree", "tool.py")
    (repository / "tool.py").unlink()
    after = _scope_data(git, repository, "branch", initial["head"], ())

    assert dict(source_snapshot(after).repository_path_fingerprints)["tool.py"] == "absent"
    assert not _run_git(git, repository, ("status", "--porcelain"))
    with pytest.raises(ValueError, match="committed tree bytes or modes differ"):
        verify_live_commit(before, after)


@pytest.mark.parametrize("target", ["git diff -- tool.py", "git diff --cached HEAD -- tool.py", "git diff origin/main -- tool.py"])
def test_independent_comparison_cannot_infer_head_from_an_index_or_moving_ref(target: str) -> None:
    assert not _unchanged_comparison(target, "a" * 40)
