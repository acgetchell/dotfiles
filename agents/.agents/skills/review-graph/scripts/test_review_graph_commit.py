"""Real Git handoffs preserve source evidence and require exact-commit native CI."""

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _run_git, _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_commit import _unchanged_comparison, verify_live_commit
from review_graph_plan import plan_from_document
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


def _save(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path, payload: dict[str, Any]) -> dict[str, str]:
    state = lifecycle.get("current_source_state", lifecycle["source_state"])
    dispatch = {**entry["dispatch"], "before_state": state, "after_state": state}
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


def _commit_fixture(
    tmp_path: Path, *, mode: str = "baseline", git_sensitive_review: bool = False
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "justfile").write_text("ci:\n    test -f tool.py\n")
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
    capture = _scope_data(git, repository, mode, None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, dispatch_set, dispatches = _materialize(tmp_path, capture, plan)
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
            payload = _payload(dispatch["owned_paths"])
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
    current = _scope_data(git, repository, mode, None, ())
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
        "local_validation": {
            local_entry["node_id"]: {
                "execution_identity": local_entry["dispatch"]["validation_unit"],
                "git_dependencies": [],
                "environment_unchanged": True,
                "reason": "The fixture CI checks only file existence; no Git inputs.",
            }
        },
        "independent_reviews": {
            entry["node_id"]: {
                "change_target": entry["dispatch"]["change_target"],
                "comparison_commit": capture["head"],
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
    target = f"git diff {request['previous_capture']['head']} -- tool.py state.rs"
    assert dispatch["change_target"] == target
    git = shutil.which("git")
    assert git is not None
    diff = _run_git(git, Path(request["new_capture"]["repository_root"]), ("diff", request["previous_capture"]["head"], "--", "tool.py"))
    assert b"+value = 2" in diff


@pytest.mark.parametrize("mode", ["baseline", "worktree"])
@pytest.mark.parametrize("git_sensitive_review", [False, True])
def test_commit_handoff_preserves_evidence_and_finalizes_exact_commit(tmp_path: Path, mode: str, git_sensitive_review: bool) -> None:
    request, entries, sources = _commit_fixture(tmp_path, mode=mode, git_sensitive_review=git_sensitive_review)
    originals = {path: Path(path).read_bytes() for source in sources.values() for path in source.values()}
    with pytest.raises(ValueError, match="only the index"):
        runtime.resume_after_external_metadata(request)
    result = runtime.resume_after_authorized_commit(request)
    native_id = next(iter(request["native_ci"]))
    rechecked = {native_id} | {node_id for node_id, entry in entries.items() if git_sensitive_review and entry["dispatch"]["mode"] == "independent-review"}
    assert set(result["preserved_node_ids"]) == set(sources) - rechecked
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    sources = {key: source for key, source in sources.items() if key not in rechecked}
    journal = Path(result["journal_path"])
    plan = runtime._graph_plan(lifecycle["plan"])
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
                payload = _synthesis_payload(entry["dispatch"], runtime.build_synthesis_bundle({**lifecycle, "sources": list(sources.values())}))
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
        next(iter(request["local_validation"].values()))["execution_identity"]["environment"] = "different environment"
    elif damage == "comparison":
        next(iter(request["independent_reviews"].values()))["comparison_commit"] = request["new_capture"]["head"]
    else:
        next(iter(request["native_ci"].values()))["commands"] = [f"native-ci --commit {request['previous_capture']['head']}"]
    with pytest.raises(ValueError, match=r"handoff|reuse|replacement"):
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


@pytest.mark.parametrize("target", ["git diff -- tool.py", "git diff --cached HEAD -- tool.py", "git diff origin/main -- tool.py"])
def test_independent_comparison_cannot_infer_head_from_an_index_or_moving_ref(target: str) -> None:
    assert not _unchanged_comparison(target, "a" * 40)
