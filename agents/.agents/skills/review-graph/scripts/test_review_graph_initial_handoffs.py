"""Executable bootstrap, runner, timing and fresh-worker handoff regressions."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_execution import capture_execution_context, command_prefix
from review_graph_isolation import IsolationPublicationError
from review_graph_plan import plan_from_document
from review_graph_schema import require_schema_definition
from review_graph_session import _check_portable_references, freeze_runtime, verify_snapshot
from review_graph_timing import timing_blocker
from test_review_graph_runtime import SKILL_ROOT, _compact_audit_payload, _json_plan, _sparse_plan_document, _worker_input_fixture
from test_review_graph_starter import RUNTIME_SCHEMA, _fixture, _invoke


@pytest.mark.parametrize("form", ["token", "relative", "absolute", "outside", "symlink"])
def test_static_reference_diagnostics_precede_freezing(tmp_path: Path, form: str) -> None:
    root = tmp_path / "skills"
    reference = root / "tool/references/policy.md"
    reference.parent.mkdir(parents=True)
    reference.write_text("policy\n")
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n")
    link = root / "tool/references/link.md"
    link.symlink_to(reference)
    choices = {
        "token": "$SKILLS_ROOT/tool/references/policy.md",
        "relative": "tool/references/policy.md",
        "absolute": str(reference),
        "outside": str(outside),
        "symlink": str(link),
    }
    path = tmp_path / "template.json"
    path.write_text(json.dumps({"routing_overrides": [{"static_references": [choices[form]]}]}))
    if form in {"token", "relative"}:
        _check_portable_references(path, root)
    else:
        expected = {"absolute": r"use \$SKILLS_ROOT/tool/references/policy.md or tool/references/policy.md", "outside": "outside", "symlink": "symlink"}
        with pytest.raises(ValueError, match=expected[form]):
            _check_portable_references(path, root)
    assert sorted(item.name for item in tmp_path.iterdir()) == ["outside.md", "skills", "template.json"]


def test_starter_to_grouped_schedule_and_continuation_without_plan_transcription(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture, choices = _fixture(tmp_path)
    status, bundle_path = _invoke(tmp_path, capture, choices)
    assert status == 0
    bootstrap = json.loads(capsys.readouterr().out)
    assert runtime.main(bootstrap["next_command"][2:]) == 0
    materialized = json.loads(capsys.readouterr().out)
    capacity = Path(materialized["scheduler_prerequisite"]["path"])
    capacity.write_text(json.dumps({"source": "fixture aggregate", "concurrent_worker_limit": 3, "active_workers": 0}))
    assert runtime.main(materialized["next_command"][2:]) == 0
    first = json.loads(capsys.readouterr().out)
    result = json.loads(Path(first["output"]["path"]).read_bytes())
    schedule = json.loads(Path(result["schedule_input_path"]).read_bytes())
    require_schema_definition(schedule, RUNTIME_SCHEMA, "schedule-ready")
    assert schedule["plan"] == json.loads(bundle_path.read_bytes())["plan"]
    assert "worker_capacity" not in schedule
    assert result["reserved_node_ids"]
    assert (
        runtime.main(
            [
                "schedule-ready",
                "--input",
                result["schedule_input_path"],
                "--dispatches",
                result["dispatches_path"],
                "--journal",
                result["journal_path"],
                "--current-capture",
                result["current_capture_path"],
                "--worker-capacity",
                str(capacity),
                "--output",
                str(tmp_path / "next.json"),
            ]
        )
        == 0
    )
    second = json.loads((tmp_path / "next.json").read_bytes())
    assert not set(second["ready_node_ids"]) & set(result["reserved_node_ids"])
    assert set(result["reserved_node_ids"]) <= set(second["reserved_node_ids"])
    capsys.readouterr()
    print(
        json.dumps(
            {
                "initial_cli_invocations_after_capture": 3,
                "initial_protocol_operations_after_capture": 4,
                "model_facing_receipt_bytes": sum(len(json.dumps(value).encode()) for value in (bootstrap, materialized, first)),
                "operator_capacity_bytes": capacity.stat().st_size,
                "source_review_executions": 0,
                "validator_executions": 0,
                "model_tokens": None,
                "provider_cost": None,
            }
        )
    )


def _prepare_timing(entry: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    policy = tmp_path / "shell.json"
    policy.write_text(json.dumps({"shell_argv": ["/bin/sh", "-c"]}))
    assert runtime.main(["prepare-validation-timing", "--input", entry["worker_payload_contract_path"], "--shell-policy", str(policy)]) == 0
    return json.loads(Path(entry["dispatch"]["timing_prerequisite"]["manifest_path"]).read_bytes())


def test_starter_validator_is_held_until_exact_timing_launch_exists(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture, choices = _fixture(tmp_path)
    status, bundle_path = _invoke(tmp_path, capture, choices)
    assert status == 0
    bootstrap = json.loads(capsys.readouterr().out)
    assert runtime.main(bootstrap["next_command"][2:]) == 0
    receipt = json.loads(capsys.readouterr().out)
    dispatch_set = json.loads(Path(receipt["output"]["path"]).read_bytes())
    entry = next(item for item in dispatch_set["dispatches"] if item["dispatch"]["mode"] == "validation")
    bundle = json.loads(bundle_path.read_bytes())
    lifecycle = {**bundle["lifecycle_input"], "current_source_state": bundle["lifecycle_input"]["source_state"]}
    initial = runtime.next_ready_nodes(lifecycle, journal_events=(), dispatch_set=dispatch_set)
    assert entry["node_id"] not in initial["ready_node_ids"]
    assert next(item for item in initial["waiting"] if item["node_id"] == entry["node_id"])["timing_prerequisite"]["prepare_command"]
    manifest = _prepare_timing(entry, tmp_path)
    assert timing_blocker(entry["dispatch"]) is None
    launch = manifest["launches"][0]
    raw = json.loads(Path(launch["launch"]["path"]).read_bytes())
    assert raw["argv"] == ["/bin/sh", "-c", entry["dispatch"]["validation_unit"]["commands"][0]]
    ready = runtime.next_ready_nodes(lifecycle, journal_events=(), dispatch_set=dispatch_set)
    assert entry["node_id"] in ready["ready_node_ids"]
    result = subprocess.run(  # noqa: S603 - explicit shell launches the isolated stand-in only.
        launch["execute_command"], env={**os.environ, "PATH": str(tmp_path / "host") + os.pathsep + os.defpath}, check=False
    )
    assert result.returncode == 7
    finished = json.loads(Path(launch["receipt_path"]).read_text().splitlines()[-1])
    assert finished["elapsed_seconds"] >= 0
    assert finished["exit_code"] == 7
    blocker = timing_blocker(entry["dispatch"])
    assert blocker is not None
    assert "already exists" in blocker["reason"]
    assert entry["node_id"] not in runtime.next_ready_nodes(lifecycle, journal_events=(), dispatch_set=dispatch_set)["ready_node_ids"]


@pytest.mark.parametrize("ledger", ["commands_executed", "files_inspected", "nearby_contract_owners"])
def test_fresh_audit_rejection_retains_attempt_and_only_replaces_failed_node(tmp_path: Path, ledger: str) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "audit")
    other = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "validation")
    view = json.loads(Path(audit["worker_execution_path"]).read_bytes())
    assert "validator/CI evidence" in view["instructions"]
    assert "Fresh audit isolation" in audit["worker_prompt"]
    originals = {entry["worker_input_path"]: Path(entry["worker_input_path"]).read_bytes() for entry in entries["dispatches"]}
    contract = json.loads(Path(audit["worker_payload_contract_path"]).read_bytes())
    payload = _compact_audit_payload(audit)
    payload[ledger] = [*payload[ledger], f"cat {other['metadata_path']}" if ledger == "commands_executed" else other["metadata_path"]]
    content = json.dumps(payload).encode()
    for _retry in range(2):
        with pytest.raises(IsolationPublicationError) as failure:
            runtime.publish_worker_payload_bytes(contract, content)
        receipt = failure.value.receipt
        assert receipt["replacement_allowed"]
        assert receipt["node_id"] == audit["node_id"]
        assert Path(receipt["rejected_payload"]["path"]).read_bytes() == content
        assert not Path(audit["worker_payload_path"]).exists()
    clean = json.dumps(_compact_audit_payload(audit)).encode()
    assert runtime.publish_worker_payload_bytes(contract, clean)["status"] == "published"
    assert all(Path(path).read_bytes() == content for path, content in originals.items())
    assert not Path(other["worker_payload_path"]).exists()


def test_second_isolation_failure_exhausts_only_this_node(tmp_path: Path) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "audit")
    other = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "validation")
    contract = json.loads(Path(audit["worker_payload_contract_path"]).read_bytes())
    clean = json.dumps(_compact_audit_payload(audit)).encode()
    approval = runtime.review_worker_payload_write(contract, clean)["approval_identity"]
    for index, field in enumerate(("metadata_path", "worker_execution_path")):
        with pytest.raises(IsolationPublicationError) as failure:
            runtime.publish_worker_payload_bytes(contract, json.dumps(_compact_audit_payload(audit, commands=(f"cat {other[field]}",))).encode())
        assert failure.value.receipt["replacement_allowed"] is (index == 0)
    with pytest.raises(ValueError, match="replacement exhausted"):
        runtime.publish_worker_payload_bytes(contract, clean)
    with pytest.raises(ValueError, match="replacement exhausted"):
        runtime.persist_worker_payload_bytes(contract, clean, approval_identity=approval)
    # Replaying the first rejected bytes is idempotent and does not restore budget.
    with pytest.raises(IsolationPublicationError) as failure:
        runtime.publish_worker_payload_bytes(contract, json.dumps(_compact_audit_payload(audit, commands=(f"cat {other['metadata_path']}",))).encode())
    assert not failure.value.receipt["replacement_allowed"]
    assert len(failure.value.receipt["rejected_attempts"]) == 2


@pytest.mark.parametrize("selector", ["absolute-glob", "relative-glob", "directory", "sealed-payload", "timing-receipt", "coverage-proof"])
def test_isolation_rejects_selectors_that_read_other_workers(tmp_path: Path, selector: str) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "audit")
    directory = Path(audit["worker_input_path"]).parent
    other = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "validation")
    selected = {
        "absolute-glob": f"{directory}/*.execution.json",
        "relative-glob": "./*.execution.json",
        "directory": str(directory),
        "sealed-payload": f"{directory}/{other['node_id']}.worker-payload.digest.sealed.json",
        "timing-receipt": f"{directory}/{other['node_id']}.timing-0.receipt.jsonl",
        "coverage-proof": f"{directory}/{other['node_id']}.coverage-proof.json",
    }[selector]
    command = f"cat {selected}" if selector != "directory" else f"rg -n . {selected}"
    payload = _compact_audit_payload(audit, commands=(command,))
    contract = json.loads(Path(audit["worker_payload_contract_path"]).read_bytes())
    with pytest.raises(IsolationPublicationError, match="another node"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    state = audit["dispatch"]["source_state"]
    with pytest.raises(ValueError, match="another node"):
        runtime.compile_review({"dispatch": {**audit["dispatch"], "before_state": state, "after_state": state}, "payload": payload})


def test_frozen_uv_runner_supplies_writable_cache_for_capture_and_publication(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    project = tmp_path / "project"
    project.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(SKILL_ROOT.parents[2] / name, project / name)
    (project / "AGENTS.md").write_text("Use uv run --locked for all Python commands.\n")
    (project / ".venv").symlink_to(SKILL_ROOT.parents[2] / ".venv", target_is_directory=True)
    cache = tmp_path / "approved-cache"
    cache.mkdir()
    context = capture_execution_context(
        {
            "argv": [uv, "run", "--locked", "--no-sync", "python"],
            "working_directory": str(project),
            "environment": {"UV_CACHE_DIR": str(cache)},
            "identity_files": [str(project / "pyproject.toml"), str(project / "uv.lock")],
        },
        project,
    )
    reference = freeze_runtime(SKILL_ROOT, tmp_path / "runtime", repository=project, execution_context=context)
    frozen = Path(reference["path"]).parent / "skills/review-graph/scripts"
    # The inherited default is unusable; the retained argv must override it.
    unavailable_cache = tmp_path / "not-a-cache"
    unavailable_cache.write_text("not a writable cache directory")
    environment = {**os.environ, "UV_CACHE_DIR": str(unavailable_cache), "UV_OFFLINE": "1"}
    document, _entries = _worker_input_fixture(tmp_path)
    plan = plan_from_document(_sparse_plan_document(), repository_root=project)
    document.update(artifact_store=str(tmp_path / "frozen-proof"), repository_root=str(project), plan=_json_plan(plan))
    request, output = tmp_path / "request.json", tmp_path / "dispatches.json"
    request.write_text(json.dumps(document))
    subprocess.run(  # noqa: S603 - pinned runtime and explicit fixture runner.
        [*command_prefix(context), str(frozen / "review_graph_runtime.py"), "materialize-dispatches", "--input", str(request), "--output", str(output)],
        cwd=project,
        env=environment,
        check=True,
        capture_output=True,
    )
    audit = next(entry for entry in json.loads(output.read_bytes())["dispatches"] if entry["dispatch"]["mode"] == "audit")
    command = audit["dispatch"]["worker_payload_persistence"]["publish_command"]
    assert command[: len(command_prefix(context))] == command_prefix(context)
    assert audit["dispatch"]["execution_context"] == context
    result = subprocess.run(command, cwd=project, env=environment, input=json.dumps(_compact_audit_payload(audit)).encode(), capture_output=True, check=True)  # noqa: S603
    assert json.loads(result.stdout)["status"] == "published"
    # Exercise the exact capture helper through the same wrapper; source is read only.
    subprocess.run(  # noqa: S603 - capture reads the real repository without changing source or Git.
        [*command_prefix(context), str(frozen / "capture_scope.py"), "--repo", str(SKILL_ROOT.parents[2]), "--mode", "worktree", "--path", "README.md"],
        cwd=project,
        env=environment,
        check=True,
        capture_output=True,
    )
    validator = next(entry for entry in json.loads(output.read_bytes())["dispatches"] if entry["dispatch"]["mode"] == "validation")
    policy = Path(validator["dispatch"]["timing_prerequisite"]["prepare_command"][-1])
    policy.write_text(json.dumps({"shell_argv": ["/bin/sh", "-c"]}))
    prepared = subprocess.run(  # noqa: S603 - generated preparation command never executes validator commands.
        validator["dispatch"]["timing_prerequisite"]["prepare_command"], cwd=project, env=environment, check=True, capture_output=True
    )
    launch = json.loads(prepared.stdout)["launches"][0]
    assert "review_graph_session.py" in shlex.join(launch["execute_command"])
    (project / "uv.lock").write_text("changed lock identity\n")
    with pytest.raises(ValueError, match="prerequisite identity changed"):
        verify_snapshot(reference)
    attempted = subprocess.run(launch["execute_command"], cwd=project, env=environment, check=False, capture_output=True)  # noqa: S603
    assert attempted.returncode == 2
    assert b"prerequisite identity changed" in attempted.stderr
    assert not Path(launch["receipt_path"]).exists()


def test_runner_rejects_interpreter_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout='{"path":"different"}'))
    with pytest.raises(ValueError, match="different interpreter"):
        capture_execution_context({"argv": [sys.executable], "working_directory": str(tmp_path), "environment": {}, "identity_files": []}, tmp_path)
