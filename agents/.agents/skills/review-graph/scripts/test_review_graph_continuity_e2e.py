"""Frozen bootstrap, validation observations, repair reuse and commit continuation."""

import json
import shlex
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_reuse import WORKTREE_SELECTION_ALGORITHM, source_snapshot
from test_review_graph_runtime import (
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compact_audit_payload,
    _compact_independent_payload,
    _complete_structural_fixture_routing,
    _run_test_git,
)
from test_review_graph_sessions import _cli


def _frozen_run(
    tmp_path: Path, *, early: bool, input_selection: bool = False, log_kind: str = "file"
) -> tuple[str, Path, dict[str, Any], dict[str, Any], Path, Path]:
    git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    template.update(
        authorization="review-and-fix",
        concrete_change_target=True,
        change_target=shlex.join(["git", "diff", capture["head"], "--", *capture["captured_scope_paths"]]),
    )
    requirement = template["validation_requirements"][0]
    isolation = tmp_path / "validator"
    isolation.mkdir()
    if log_kind == "aliased-directory":
        alias = tmp_path / "validator-alias"
        alias.symlink_to(isolation, target_is_directory=True)
        isolation = alias
    log = isolation / "ci.log"
    artifact = log
    if log_kind in {"directory", "aliased-directory"}:
        artifact = isolation / "logs"
        log = artifact / "nested" / "ci.log"
        log.parent.mkdir(parents=True)
        (artifact / "empty").mkdir()
        outside = tmp_path / "outside.log"
        outside.write_text("external bytes must not be archived\n")
        (artifact / "external-link").symlink_to(outside)
    elif log_kind == "symlink":
        artifact = isolation / "log-link"
        artifact.symlink_to(log.name)
    requirement.update(
        commands=["printf passed > " + shlex.quote(str(log))],
        canonical_recipe=None,
        requires_isolation=True,
        isolation_root=str(isolation),
        working_directories=[str(isolation)],
        allowed_artifacts=[{"path": str(artifact), "kind": "log", "repository_status": "outside-repository"}],
    )
    if input_selection:
        (repository / "enumerate.sh").write_text('git -C "$1" ls-files --cached --others --exclude-standard -z\n')
        requirement.update(commands=[shlex.join(["sh", str(repository / "enumerate.sh"), str(repository)]) + " > " + shlex.quote(str(log))])
        capture = _scope_data(git, repository, "baseline", None, ())
        snapshot = source_snapshot(capture)
        template["change_target"] = shlex.join(["git", "diff", snapshot.head, "--", *snapshot.captured_scope_paths])
        _complete_structural_fixture_routing(template, list(snapshot.captured_scope_paths))
    if early:
        template["pre_review_validation_requirement_ids"] = [requirement["requirement_id"]]
    capture_path, template_path, bundle_path = (tmp_path / name for name in ("initial-capture.json", "template.json", "bootstrap.json"))
    capture_path.write_text(json.dumps(capture))
    template_path.write_text(json.dumps(template))
    _cli(
        SKILL_ROOT / "review-graph/scripts/review_graph_bootstrap.py",
        "--capture",
        str(capture_path),
        "--input",
        str(template_path),
        "--output",
        str(bundle_path),
    )
    bundle = json.loads(bundle_path.read_bytes())
    assert bundle["validation_reuse_prerequisite"]["registry_present"] is False
    frozen_runtime = Path(bundle["runtime_snapshot"]["path"]).parent / "skills/review-graph/scripts/review_graph_runtime.py"
    dispatch_path = tmp_path / "dispatches.json"
    _cli(frozen_runtime, "materialize-dispatches", "--input", str(bundle_path), "--output", str(dispatch_path))
    return git, repository, bundle, json.loads(dispatch_path.read_bytes()), frozen_runtime, dispatch_path


def _compile(  # noqa: PLR0913, PLR0917 - mirror the explicit compiler CLI boundaries.
    frozen: Path, lifecycle: Path, dispatches: Path, journal: Path, entry: dict[str, Any], before: str, after: str, output: Path, *workspace: str
) -> None:
    _cli(
        frozen,
        "compile-node",
        "--input",
        str(lifecycle),
        "--dispatches",
        str(dispatches),
        "--journal",
        str(journal),
        "--node-id",
        entry["node_id"],
        "--before-capture",
        before,
        "--after-capture",
        after,
        "--output",
        str(output),
        *workspace,
    )


def _observe(entry: dict[str, Any], phase: str) -> dict[str, Any]:
    observation = entry["dispatch"]["validation_observations"][phase]
    subprocess.run(["/bin/sh", "-c", observation["capture_command"]], check=True)  # noqa: S603 - runtime-generated fixture capture only.
    subprocess.run(observation["workspace_command"], check=True, capture_output=True)  # noqa: S603 - runtime-owned fixture snapshot.
    return observation


@pytest.mark.parametrize(
    ("dependency_kind", "log_kind"),
    [
        ("none", "file"),
        ("none", "symlink"),
        ("input-selection", "file"),
        ("index", "file"),
        ("index", "directory"),
        ("index", "aliased-directory"),
        ("index", "symlink"),
    ],
)
def test_frozen_validator_handoffs_release_source_review_without_metadata_ci_replay(tmp_path: Path, dependency_kind: str, log_kind: str) -> None:  # noqa: PLR0915 - frozen execution through metadata continuation.
    git, repository, bundle, dispatches, frozen, dispatch_path = _frozen_run(
        tmp_path, early=True, input_selection=dependency_kind == "input-selection", log_kind=log_kind
    )
    validator = next(entry for entry in dispatches["dispatches"] if entry["dispatch"]["mode"] == "validation")
    view = json.loads(Path(validator["worker_execution_path"]).read_bytes())
    assert view["dispatch"]["validation_observations"] == validator["dispatch"]["validation_observations"]
    assert "Before execution, run validation_observations.before.capture_command then its workspace_command" in view["instructions"]
    assert "After execution, run validation_observations.after.capture_command then its workspace_command before publishing" in view["instructions"]
    policy = tmp_path / "shell.json"
    policy.write_text(json.dumps({"shell_argv": ["/bin/sh", "-c"]}))
    _cli(frozen, "prepare-validation-timing", "--input", validator["worker_payload_contract_path"], "--shell-policy", str(policy))
    launch = json.loads(Path(validator["dispatch"]["timing_prerequisite"]["manifest_path"]).read_bytes())["launches"][0]
    before = _observe(validator, "before")
    subprocess.run(launch["execute_command"], check=True, capture_output=True)  # noqa: S603 - explicit runtime-owned fixture launch.
    after = _observe(validator, "after")
    receipt_path = Path(launch["receipt_path"])
    receipt_bytes = receipt_path.read_bytes()
    timing = json.loads(receipt_bytes.splitlines()[-1])
    payload = {
        "schema_version": 3,
        "status": "passed",
        "limitations": [],
        "git_dependencies": [],
        "executions": [
            {
                "command": launch["command"],
                "working_directory": launch["working_directory"],
                "executor": validator["node_id"],
                "result": "passed",
                "exit_code": 0,
                "elapsed": f"{timing['elapsed_seconds']}s",
                "evidence": "Observed timed fixture pass",
                "artifact_paths": [validator["dispatch"]["validation_unit"]["allowed_artifacts"][0]["path"]],
            }
        ],
    }
    if dependency_kind != "none":
        payload["git_dependencies"] = [
            {
                "kind": dependency_kind,
                "command": launch["command"],
                "reason": "Fixture Git dependency",
                **({"selection_algorithm": WORKTREE_SELECTION_ALGORITHM} if dependency_kind == "input-selection" else {}),
            }
        ]
    _cli(frozen, "publish-worker-payload", "--input", validator["worker_payload_contract_path"], stdin=json.dumps(payload).encode())
    journal = tmp_path / "execution.jsonl"
    _compile(
        frozen,
        tmp_path / "bootstrap.json",
        dispatch_path,
        journal,
        validator,
        before["capture_path"],
        after["capture_path"],
        tmp_path / "validated.json",
        "--workspace-before",
        before["workspace_path"],
        "--workspace-after",
        after["workspace_path"],
    )
    # Stage different index bytes while leaving exactly the captured worktree.
    (repository / "tool.py").write_text("value = 2\n")
    _run_test_git(git, "-C", str(repository), "add", "tool.py")
    (repository / "tool.py").write_text("value = 1\n")
    request = {
        **bundle["lifecycle_input"],
        "previous_capture": bundle["capture"],
        "new_capture": _scope_data(git, repository, "baseline", None, ()),
        "journal_path": str(journal),
        "dispatches_path": str(dispatch_path),
        "artifact_store": str(tmp_path / "continued"),
    }
    request_path, output = tmp_path / "resume.json", tmp_path / "resumed.json"
    request_path.write_text(json.dumps(request))
    _cli(frozen, "resume-after-external-metadata", "--input", str(request_path), "--output", str(output))
    result = json.loads(output.read_bytes())
    decision = next(item for item in result["node_decisions"] if item["node_id"] == validator["node_id"])
    if dependency_kind == "index":
        assert decision["disposition"] == "recheck"
        archive = result["validation_log_archives"][0]
        assert archive["evidence_id"] == validator["dispatch"]["evidence_id"]
        if log_kind in {"directory", "aliased-directory"}:
            assert archive["original_digest_mode"] == "recursive-content-sha256-v2"
            archived_bytes = Path(archive["path"]).read_bytes()
            with tarfile.open(archive["path"]) as retained:
                output = retained.extractfile("nested/ci.log")
                assert output is not None
                assert output.read() == b"passed"
                assert retained.getmember("empty").isdir()
                assert retained.getmember("external-link").issym()
                assert retained.getmember("external-link").linkname == str(tmp_path / "outside.log")
            assert b"external bytes must not be archived" not in archived_bytes
            (Path(archive["original_path"]) / "nested/ci.log").write_text("subsequent validation output\n")
            assert Path(archive["path"]).read_bytes() == archived_bytes
        elif log_kind == "symlink":
            assert archive["original_digest_mode"] == "symlink-target-v1"
            assert Path(archive["path"]).read_bytes() == b"ci.log"
            original = Path(archive["original_path"])
            original.unlink()
            original.symlink_to("replacement.log")
            assert Path(archive["path"]).read_bytes() == b"ci.log"
        else:
            assert Path(archive["path"]).read_bytes() == b"passed"
            Path(archive["original_path"]).write_text("subsequent validation output\n")
            assert Path(archive["path"]).read_bytes() == b"passed"
        assert Path(archive["path"]).stat().st_mode & 0o222 == 0
        assert receipt_path.read_bytes() == receipt_bytes
        return
    assert decision["scheduling_gate"] == "historical-source-pass"
    assert decision["formal_reuse"] == "unproven"
    lifecycle = result["lifecycle_input"]
    for entry in result["dispatch_set"]["dispatches"]:
        if entry["dispatch"]["mode"] not in {"audit", "independent-review"}:
            continue
        payload = _compact_audit_payload(entry) if entry["dispatch"]["mode"] == "audit" else _compact_independent_payload(entry["dispatch"])
        if entry["dispatch"]["mode"] == "independent-review":
            payload.update(before_state=result["current_source_state"], after_state=result["current_source_state"])
        _cli(frozen, "publish-worker-payload", "--input", entry["worker_payload_contract_path"], stdin=json.dumps(payload).encode())
        _compile(
            frozen,
            Path(result["lifecycle_input_path"]),
            Path(result["dispatches_path"]),
            Path(result["journal_path"]),
            entry,
            result["capture_path"],
            result["capture_path"],
            tmp_path / (entry["node_id"] + ".compiled.json"),
        )
    assert receipt_path.read_bytes() == receipt_bytes
    report = tmp_path / "delivery.json"
    _cli(
        frozen,
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
        str(report),
    )
    delivery = json.loads(report.read_bytes())
    assert delivery["pending_semantic_node_ids"] == []
    assert delivery["repository_readiness"] == "blocked"
    assert any("validation-contract-unavailable" in blocker for blocker in delivery["blockers"])


@pytest.mark.parametrize("external_read", [False, True])
def test_frozen_audit_repair_reuse_and_range_read_commit_continuation(tmp_path: Path, external_read: bool) -> None:  # noqa: PLR0915 - complete frozen workflow.
    git, repository, bundle, dispatches, frozen, dispatch_path = _frozen_run(tmp_path, early=False)
    audit = next(entry for entry in dispatches["dispatches"] if entry["dispatch"].get("skill_id") == "python-cli-review")
    payload = _compact_audit_payload(audit)
    external = tmp_path / "registry-dependency.rs"
    if external_read:
        external.write_text("pub fn dependency() {}\n")
        payload["nearby_contract_owners"].append(str(external))
    payload["commands_executed"] = [shlex.join(["cat", path]) for path in payload["nearby_contract_owners"]]
    for command in payload["commands_executed"]:
        subprocess.run(shlex.split(command), check=True, capture_output=True)  # noqa: S603 - exact fixture instruction reads.
    _cli(frozen, "publish-worker-payload", "--input", audit["worker_payload_contract_path"], stdin=json.dumps(payload).encode())
    journal = tmp_path / "execution.jsonl"
    _compile(frozen, tmp_path / "bootstrap.json", dispatch_path, journal, audit, bundle["capture_path"], bundle["capture_path"], tmp_path / "audited.json")
    original = Path(audit["artifact_path"]).read_bytes()
    (repository / "state.rs").write_text("pub fn state() { let value = 2; }\n")
    (repository / "extra.txt").write_text("repair-added boundary fixture\n")
    current = _scope_data(git, repository, "baseline", None, ())
    request = {
        **bundle["lifecycle_input"],
        "previous_capture": bundle["capture"],
        "new_capture": current,
        "planning_template": bundle["planning_input"],
        "repair_epoch": 1,
        "changed_paths": ["state.rs", "extra.txt"],
        "authorization_before": "review-and-fix",
        "authorization_after": "review-and-fix",
        "state_verification_command": bundle["materialization_input"]["state_verification_command"],
        "journal_path": str(journal),
        "dispatches_path": str(dispatch_path),
        "artifact_store": str(tmp_path / "repair"),
    }
    request_path, output = tmp_path / "repair.json", tmp_path / "repaired.json"
    request_path.write_text(json.dumps(request))
    _cli(frozen, "advance-after-mutation", "--input", str(request_path), "--output", str(output))
    result = json.loads(output.read_bytes())
    if external_read:
        assert audit["dispatch"]["evidence_id"] not in result["reused_evidence_ids"]
        decision = next(item for item in result["reuse_decisions"] if item["node_id"] == audit["node_id"])
        assert decision["rejected_inputs"] == [{"path": str(external), "classification": "unbound-external-source"}]
        assert Path(audit["artifact_path"]).read_bytes() == original
        return
    assert audit["dispatch"]["evidence_id"] in result["reused_evidence_ids"]
    assert Path(audit["artifact_path"]).read_bytes() == original
    independent = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["mode"] == "independent-review")
    dispatch = independent["dispatch"]
    comparison = shlex.split(dispatch["change_target"])
    assert comparison[2] == bundle["capture"]["head"]
    assert comparison[comparison.index("--") + 1 :] == current["captured_scope_paths"]
    # The original immutable plan/dispatch continues to advertise only its old scope.
    assert "extra.txt" not in bundle["planning_input"]["change_target"]
    # Complete the remaining source audits, then publish the independent reviewer once.
    for entry in result["dispatch_set"]["dispatches"]:
        if entry["dispatch"]["mode"] != "audit":
            continue
        _cli(frozen, "publish-worker-payload", "--input", entry["worker_payload_contract_path"], stdin=json.dumps(_compact_audit_payload(entry)).encode())
        _compile(
            frozen,
            Path(result["lifecycle_input_path"]),
            Path(result["dispatches_path"]),
            Path(result["journal_path"]),
            entry,
            result["capture_path"],
            result["capture_path"],
            tmp_path / (entry["node_id"] + ".compiled.json"),
        )
    payload = _compact_independent_payload(dispatch)
    payload["nearby_contract_owners"].extend([independent["worker_input_path"], dispatch["payload_schema"]["path"]])
    commands = [shlex.join(["sed", "-n", "1,600p", path]) for path in dispatch["owned_paths"]]
    commands += [shlex.join(["cat", path]) for path in payload["nearby_contract_owners"]]
    for command in commands:
        subprocess.run(shlex.split(command), cwd=repository, check=True, capture_output=True)  # noqa: S603 - bounded fixture reads.
    captures = []
    for phase in ("before", "after"):
        capture = tmp_path / f"independent-{phase}.json"
        command = dispatch["state_verification_command"] + " > " + shlex.quote(str(capture))
        subprocess.run(["/bin/sh", "-c", command], check=True)  # noqa: S603 - exact generated fixture capture.
        captures.append(str(capture))
        commands.append(command)
    commands.append(shlex.join(dispatch["worker_payload_persistence"]["publish_command"]))
    payload["commands_executed"] = commands
    _cli(frozen, "publish-worker-payload", "--input", independent["worker_payload_contract_path"], stdin=json.dumps(payload).encode())
    _compile(
        frozen,
        Path(result["lifecycle_input_path"]),
        Path(result["dispatches_path"]),
        Path(result["journal_path"]),
        independent,
        captures[0],
        captures[1],
        tmp_path / "independent.compiled.json",
    )
    sealed = Path(independent["artifact_path"]).read_bytes()
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "Authorized reviewed fixture")
    committed = _scope_data(git, repository, "baseline", None, ())
    handoff = {
        **result["lifecycle_input"],
        "previous_capture": current,
        "new_capture": committed,
        "journal_path": result["journal_path"],
        "dispatches_path": result["dispatches_path"],
        "artifact_store": str(tmp_path / "committed"),
        "authorization": {
            "operation": "branch-commit",
            "repository_root": str(repository),
            "branch": committed["branch"],
            "source_state": result["new_source_state"],
            "user_authorization": "Commit the reviewed fixture.",
        },
        "independent_reviews": {
            independent["node_id"]: {
                "change_target": dispatch["change_target"],
                "comparison_commit": current["head"],
                "reason": "Same complete source and fixed comparison after the authorized fixture commit.",
            }
        },
        "native_ci": {
            entry["node_id"]: {"commands": [f"native-ci --commit {committed['head']}"], "checks": [{"name": "CI", "target": "fixture"}]}
            for entry in result["dispatch_set"]["dispatches"]
            if entry["dispatch"]["mode"] == "validation"
        },
    }
    handoff_path, committed_path = tmp_path / "handoff.json", tmp_path / "committed.json"
    handoff_path.write_text(json.dumps(handoff))
    _cli(frozen, "resume-after-authorized-commit", "--input", str(handoff_path), "--output", str(committed_path))
    continuation = json.loads(committed_path.read_bytes())
    assert independent["node_id"] in continuation["preserved_node_ids"]
    assert Path(independent["artifact_path"]).read_bytes() == sealed
    metadata = json.loads(Path(independent["metadata_path"]).read_bytes())
    assert metadata["normalized_record"]["commands_executed"] == commands
    assert metadata["normalized_record"]["runtime_inputs"]
