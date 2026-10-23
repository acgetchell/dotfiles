"""Frozen CLI recovery, compact worker integrity and delivery without certification."""

import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_execution import capture_execution_context
from review_graph_plan import plan_from_document
from review_graph_receipts import dispatch_summary
from review_graph_session import freeze_runtime, verify_snapshot
from test_review_graph_git import _accept, _discovery_payload
from test_review_graph_reuse import _audit_request
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compact_independent_payload,
    _compile_repair_fixture_entry,
    _complete_structural_fixture_routing,
    _json_plan,
    _publish_worker_bytes,
    _run_test_git,
    _worker_input_fixture,
)
from test_review_graph_starter import _fixture as _starter_fixture
from test_review_graph_transitions import _materialize, _payload


def _cli(script: Path, *arguments: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 - fixed repository scripts with isolated fixture paths.
        [sys.executable, "-B", str(script), *arguments], input=stdin, capture_output=True, check=True
    )


def test_bootstrap_freezes_resources_and_recovers_signed_dispatch_publication(tmp_path: Path) -> None:  # noqa: PLR0915 - frozen recovery through capture, publication and final proof.
    _git, _repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    live = tmp_path / "live-skills"
    shutil.copytree(SKILL_ROOT, live, ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"))
    capture_path, input_path, output = tmp_path / "capture.json", tmp_path / "template.json", tmp_path / "bootstrap.json"
    capture_path.write_text(json.dumps(capture))
    input_path.write_text(json.dumps(template))
    bootstrap = live / "review-graph/scripts/review_graph_bootstrap.py"
    arguments = (
        "--capture",
        str(capture_path),
        "--input",
        str(input_path),
        "--output",
        str(output),
        "--skill-root",
        str(live),
        "--catalog",
        str(live / "review-graph/references/routing-catalog.json"),
    )
    _cli(bootstrap, *arguments)
    bundle = json.loads(output.read_bytes())
    reference = bundle["runtime_snapshot"]
    frozen = Path(reference["path"]).parent
    request = tmp_path / "materialize.json"
    request.write_text(json.dumps(bundle["materialization_input"]))
    dispatches = tmp_path / "dispatches.json"
    recovery = SKILL_ROOT / "review-graph/scripts/review_graph_session.py"
    reference_path = frozen / "runtime-reference.json"
    run = ("--reference", str(reference_path), "--script", "review_graph_runtime.py", "--")
    _cli(recovery, *run, "materialize-dispatches", "--input", str(request), "--output", str(dispatches))
    signed = dispatches.read_bytes()
    entries = json.loads(signed)
    audit = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit")
    observations = audit["dispatch"]["audit_observations"]
    subprocess.run(shlex.split(observations["before"]["capture_command"]), check=True, capture_output=True)  # noqa: S603 - frozen framework capture.
    # Simulate a concurrent update, including an incompatible schema/catalog.
    (live / "review-graph/scripts/review_graph_runtime.py").write_text("raise RuntimeError('changed live runtime')\n")
    (live / "review-graph/references/schemas/runtime-operation-inputs-v1.schema.json").write_text("{}")
    (live / "review-graph/references/routing-catalog.json").write_text("{}")
    (live / "python-cli-review/SKILL.md").write_text("changed live skill")
    _cli(bootstrap, *arguments)  # Recovery must use the original bundle, not replan.
    assert json.loads(output.read_bytes()) == bundle
    payload = json.dumps(_payload(audit["dispatch"]["owned_paths"], dispatch=audit["dispatch"])).encode()
    _cli(recovery, *run, "publish-worker-payload", "--input", audit["worker_payload_contract_path"], stdin=payload)
    subprocess.run(shlex.split(observations["after"]["capture_command"]), check=True, capture_output=True)  # noqa: S603 - frozen framework capture.
    lifecycle = tmp_path / "lifecycle.json"
    lifecycle.write_text(json.dumps(bundle["lifecycle_input"]))
    journal = tmp_path / "journal.jsonl"
    _cli(
        recovery,
        *run,
        "compile-node",
        "--input",
        str(lifecycle),
        "--dispatches",
        str(dispatches),
        "--journal",
        str(journal),
        "--node-id",
        audit["node_id"],
        "--before-capture",
        observations["before"]["capture_path"],
        "--after-capture",
        observations["after"]["capture_path"],
        "--output",
        str(tmp_path / "compiled.json"),
    )
    for entry in entries["dispatches"]:
        if entry["node_id"] != audit["node_id"]:
            _compile_repair_fixture_entry(entry, bundle["lifecycle_input"], journal)
    final = tmp_path / "proof.json"
    _cli(
        recovery,
        *run,
        "finalize-proof",
        "--input",
        str(lifecycle),
        "--dispatches",
        str(dispatches),
        "--journal",
        str(journal),
        "--current-capture",
        str(capture_path),
        "--output",
        str(final),
    )
    assert json.loads(final.read_bytes())["graph_proof_status"] == "complete"
    assert dispatches.read_bytes() == signed
    assert Path(audit["worker_payload_path"]).read_bytes() == payload
    assert verify_snapshot(reference).files
    damaged = frozen / "skills/review-graph/references/routing-catalog.json"
    damaged.chmod(0o644)
    damaged.write_text("{}")
    with pytest.raises(ValueError, match="resource changed"):
        verify_snapshot(reference)
    with pytest.raises(subprocess.CalledProcessError):
        _cli(recovery, *run, "materialize-dispatches", "--input", str(request), "--output", str(tmp_path / "bad.json"))


def test_runtime_rejects_repository_store_and_unpinned_interpreter(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(ValueError, match="outside"):
        freeze_runtime(SKILL_ROOT, repository / "runtime", repository=repository)
    reference = freeze_runtime(SKILL_ROOT, tmp_path / "runtime", repository=repository)
    with pytest.raises(ValueError, match="manifest digest"):
        verify_snapshot({**reference, "digest": "sha256:" + "0" * 64})


@pytest.mark.parametrize("winner", ["same", "different", "missing"])
def test_concurrent_freeze_checks_the_winning_runner_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winner: str) -> None:
    repository, skills, destination = tmp_path / "repository", tmp_path / "skills", tmp_path / "runtime"
    repository.mkdir()
    skills.mkdir()
    (skills / "SKILL.md").write_text("fixture skill\n")
    policy = {"argv": [sys.executable], "working_directory": str(repository), "environment": {}, "identity_files": []}
    requested = capture_execution_context(policy, repository)
    retained = (
        requested
        if winner == "same"
        else capture_execution_context({**policy, "environment": {"REVIEW_RUNNER": "winner"}}, repository)
        if winner == "different"
        else None
    )
    rename = Path.rename
    won = False
    winning_reference: dict[str, str] = {}

    def concurrent_rename(staged: Path, target: Path) -> Path:
        nonlocal won
        if target == destination and not won:
            won = True
            winning_reference.update(freeze_runtime(skills, destination, repository=repository, execution_context=retained))
            msg = "another bootstrap published first"
            raise FileExistsError(msg)
        return rename(staged, target)

    monkeypatch.setattr(Path, "rename", concurrent_rename)
    if winner == "same":
        assert freeze_runtime(skills, destination, repository=repository, execution_context=requested) == winning_reference
    else:
        with pytest.raises(ValueError, match="Python runner cannot change"):
            freeze_runtime(skills, destination, repository=repository, execution_context=requested)
    assert won
    assert verify_snapshot(winning_reference).files
    context = destination / "execution-context.json"
    assert json.loads(context.read_bytes()) == retained if retained is not None else not context.exists()


@pytest.mark.parametrize("portable", ["relative", "token"])
def test_absolute_reference_failure_leaves_bootstrap_retryable(tmp_path: Path, portable: str) -> None:
    _git, _repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    relative = "rust-invariant-state-transitions/references/standalone-workflow.md"
    source = SKILL_ROOT / relative
    template["routing_overrides"][0]["static_references"] = [str(source)]
    capture_path, input_path, output = (tmp_path / name for name in ("capture.json", "template.json", "bootstrap.json"))
    capture_path.write_text(json.dumps(capture))
    input_path.write_text(json.dumps(template))
    bootstrap = SKILL_ROOT / "review-graph/scripts/review_graph_bootstrap.py"
    arguments = ("--capture", str(capture_path), "--input", str(input_path), "--output", str(output))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        _cli(bootstrap, *arguments)
    assert f"use $SKILLS_ROOT/{relative} or {relative}" in failure.value.stderr.decode()
    assert not output.exists()
    assert not output.with_suffix(".runtime").exists()
    template["routing_overrides"][0]["static_references"] = [("$SKILLS_ROOT/" if portable == "token" else "") + relative]
    input_path.write_text(json.dumps(template))
    _cli(bootstrap, *arguments)
    original = output.read_bytes()
    bundle = json.loads(original)
    frozen_reference = Path(bundle["runtime_snapshot"]["path"]).parent / "skills" / relative
    assert frozen_reference.read_bytes() == source.read_bytes()
    assert any(str(frozen_reference) in node["static_references"] for node in bundle["plan"]["actual_worker_nodes"])
    _cli(bootstrap, *arguments)
    assert output.read_bytes() == original


def test_blocked_starter_resume_retains_original_runtime_and_plan(tmp_path: Path) -> None:
    capture, choices = _starter_fixture(tmp_path)
    live = tmp_path / "live-skills"
    shutil.copytree(SKILL_ROOT, live, ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"))
    capture_path, choices_path, output = tmp_path / "capture.json", tmp_path / "choices.json", tmp_path / "bootstrap.json"
    choices["features"].append("executor-permissions=require_escalated")
    capture_path.write_text(json.dumps(capture))
    choices_path.write_text(json.dumps(choices))
    bootstrap = live / "review-graph/scripts/review_graph_bootstrap.py"
    arguments = (
        "--capture",
        str(capture_path),
        "--starter-config",
        str(choices_path),
        "--skill-root=" + str(live),
        "--catalog=" + str(live / "review-graph/references/routing-catalog.json"),
    )
    with pytest.raises(subprocess.CalledProcessError) as failure:
        _cli(bootstrap, *arguments, "--output", str(output))
    assert failure.value.returncode == 2
    original = output.read_bytes()
    saved = json.loads(original)
    choices["execution_prerequisites"]["sandbox_permissions"] = "require_escalated"
    choices_path.write_text(json.dumps(choices))
    (live / "review-graph/scripts/review_graph_runtime.py").write_text("raise RuntimeError('live update')\n")
    (live / "review-graph/references/schemas/runtime-operation-inputs-v1.schema.json").write_text("{}")
    resumed_path = tmp_path / "resumed.json"
    _cli(bootstrap, *arguments, "--resume-from", str(output), "--output", str(resumed_path))
    resumed = json.loads(resumed_path.read_bytes())
    assert resumed["runtime_snapshot"] == saved["runtime_snapshot"]
    for field in ("plan", "planning_input", "materialization_input", "lifecycle_input"):
        assert resumed[field] == saved[field]
    assert output.read_bytes() == original
    assert not resumed_path.with_suffix(".runtime").exists()


@pytest.mark.parametrize("transition", ["branch", "stage"])
def test_branch_scope_preserves_source_audits_and_completed_independent_review(tmp_path: Path, transition: str) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 2\n")
    (repository / "state.rs").write_text("pub fn state() { assert!(true); }\n")
    capture = _scope_data(git, repository, "branch", "HEAD", ())
    template.update(scope_mode="branch", concrete_change_target=True, change_target="review captured branch diff")
    for override in template["routing_overrides"]:
        if override["disposition"] == "selected":
            override["review_surface"] = ["tool.py"] if override["catalog_id"].startswith("python.") else ["state.rs"]
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    journal = tmp_path / "journal.jsonl"
    lifecycle.update(journal_path=str(journal), dispatches_path=str(dispatches))
    audit = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit")
    _accept(lifecycle, audit, _discovery_payload(audit, "git diff HEAD -- tool.py"))
    independent = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "independent-review")
    state = lifecycle["source_state"]
    content, metadata = runtime.compile_independent_payload(
        {"dispatch": {**independent["dispatch"], "before_state": state, "after_state": state}, "payload": _compact_independent_payload(independent["dispatch"])}
    )
    Path(independent["artifact_path"]).write_bytes(content)
    Path(independent["metadata_path"]).write_text(json.dumps(metadata))
    source = {key: independent[key] for key in ("artifact_path", "metadata_path")}
    runtime.append_journal_event(journal, lifecycle, runtime.JournalEventRequest(independent["node_id"], "accepted", source=source))
    if transition == "branch":
        _run_test_git(git, "-C", str(repository), "checkout", "-b", "fix/fixture")
    else:
        _run_test_git(git, "-C", str(repository), "add", "tool.py")
    current = _scope_data(git, repository, "branch", "HEAD", ())
    result = runtime.resume_after_external_metadata(
        {**lifecycle, "previous_capture": capture, "new_capture": current, "artifact_store": str(tmp_path / "resumed")}
    )
    assert {audit["node_id"], independent["node_id"]} <= set(result["preserved_node_ids"])
    assert all(
        item["mode"] in {"validation", "synthesis"}
        for item in result["node_decisions"]
        if item["disposition"] == "recheck" and item["prior_status"] == "accepted"
    )
    assert result["lifecycle_input"]["plan"]["review_lifecycle"] == json.loads(json.dumps(asdict(plan.review_lifecycle)))
    assert not runtime._metadata_evidence_blockers(result["lifecycle_input"], [metadata["normalized_record"]])


def test_compact_view_publishes_semantics_and_tampering_blocks_scheduling(tmp_path: Path) -> None:
    lifecycle, entries = _worker_input_fixture(tmp_path)
    audit = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit")
    view_path = Path(dispatch_summary(audit)["worker_input"]["path"])
    view = json.loads(view_path.read_bytes())
    assert view_path.stat().st_size < Path(audit["worker_input_path"]).stat().st_size
    payload = json.dumps(_payload(view["dispatch"]["owned_paths"], dispatch=view["dispatch"])).encode()
    _publish_worker_bytes(audit, payload)
    assert Path(audit["worker_payload_path"]).read_bytes() == payload
    view_path.chmod(0o644)
    view_path.write_text("{}")
    with pytest.raises(ValueError, match="execution view"):
        runtime._dispatches_by_node(entries, plan=runtime._graph_plan(lifecycle["plan"]), source_state=tuple(lifecycle["source_state"]))


def test_routine_independent_waits_for_finished_source_without_semantic_edges(tmp_path: Path) -> None:
    git, repository, template, capture, _draft = _baseline_mutation_fixture(tmp_path)
    template.update(concrete_change_target=True, change_target="captured fixture", independent_review_after_audits=True)
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    lifecycle["current_source_state"] = lifecycle["source_state"]
    independent = next(entry for entry in entries["dispatches"] if entry["dispatch"]["mode"] == "independent-review")
    ready = runtime.next_ready_nodes(lifecycle, journal_events=(), dispatch_set=entries)
    assert independent["node_id"] not in ready["ready_node_ids"]
    assert independent["dispatch"]["predecessor_evidence_ids"] == []
    assert "shared_inspection_evidence" not in independent["dispatch"]
    journal = tmp_path / "journal.jsonl"
    for entry in entries["dispatches"]:
        if entry["dispatch"]["mode"] == "audit":
            _compile_repair_fixture_entry(entry, lifecycle, journal)
    events, _states, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))
    assert independent["node_id"] in runtime.next_ready_nodes(lifecycle, journal_events=events, dispatch_set=entries)["ready_node_ids"]
    # The coordinator repairs after initial audits, before launching independence.
    (repository / "tool.py").write_text("value = 2\n")
    advanced = runtime.advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "changed_paths": ["tool.py"],
            "artifact_store": str(tmp_path / "repair"),
            "journal_path": str(journal),
            "dispatches_path": str(dispatches),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    assert advanced["new_plan"]["independent_review_after_audits"]
    assert advanced["new_plan"]["review_lifecycle"]["repairs_completed"] == 1
    fresh = next(entry for entry in advanced["dispatch_set"]["dispatches"] if entry["dispatch"]["mode"] == "independent-review")
    assert fresh["dispatch"]["predecessor_evidence_ids"] == []
    assert not Path(independent["worker_payload_path"]).exists()
    assert not Path(fresh["worker_payload_path"]).exists()


def test_unavailable_validation_preserves_source_partition_and_delivery_stays_uncertified(tmp_path: Path) -> None:
    request, original, _payload_before = _audit_request(tmp_path, caveat="native-unavailable")
    result = runtime.advance_after_mutation(request)
    assert result["new_plan"]["review_lifecycle"]["repairs_completed"] == 1
    assert result["new_plan"]["review_lifecycle"]["repair_budget"] == 2
    audit = next(item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == original["dispatch"]["skill_id"])
    assert {unit["disposition"] for unit in audit["dispatch"]["coverage_reuse"]["units"]} == {"reused", "recheck"}
    lifecycle = {**json.loads(Path(result["lifecycle_input_path"]).read_bytes()), "current_source_state": result["new_source_state"], "sources": []}
    report = runtime.report_delivery(lifecycle)
    assert report["graph_proof_status"] == "not-certified"
    assert "proof" not in report
    assert report["repository_readiness"] == "blocked"
    assert report["validation"][0]["status"] == "pending-or-unavailable"
    assert len(report["hosted_ci"]) == 1
    assert report["hosted_ci"][0]["requirement_ids"] == ["native-ci"]


@pytest.mark.parametrize("repair", ["tool-only", "dependencies", "python-selector"])
def test_preplanned_direct_runner_captures_manifest_repairs_without_changing_runtime(tmp_path: Path, repair: str) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    manifest = repository / "pyproject.toml"
    manifest.write_text('[project]\nname = "consumer"\nversion = "0.1.0"\nrequires-python = ">=3.15"\n[tool.ruff]\nsrc = ["src"]\n')
    (repository / "uv.lock").write_text("version = 1\n")
    (repository / ".python-version").write_text("3.15\n")
    capture = _scope_data(git, repository, "baseline", None, ())

    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    reference = freeze_runtime(SKILL_ROOT, tmp_path / "runtime", repository=repository)
    retained = Path(reference["path"]).read_bytes()
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    if repair == "python-selector":
        (repository / ".python-version").write_text("3.16\n")
        changed = [".python-version"]
        template["validation_requirements"][0]["toolchain"] = "consumer Python 3.16; verification required"
    else:
        manifest.write_text(
            manifest.read_text().replace('src = ["src"]', 'src = ["src", "scripts"]')
            if repair == "tool-only"
            else manifest.read_text().replace("[tool.ruff]", 'dependencies = ["example==2.0"]\n[tool.ruff]')
        )
        changed = ["pyproject.toml"]
        if repair == "dependencies":
            (repository / "uv.lock").write_text("version = 1\nrevision = 1\n")
            changed.append("uv.lock")
    frozen_capture = Path(reference["path"]).parent / "skills/review-graph/scripts/capture_scope.py"
    output = tmp_path / "repair.capture.json"
    result = _cli(frozen_capture, "--repo", str(repository), "--mode", "baseline", "--output", str(output))
    assert json.loads(result.stdout)["capture_digest"] == runtime.digest_bytes(output.read_bytes())

    advanced = runtime.advance_after_mutation(
        {
            "plan": _json_plan(plan),
            "source_state": [capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")],
            "previous_capture": capture,
            "new_capture": json.loads(output.read_bytes()),
            "planning_template": template,
            "changed_paths": sorted(changed),
            "authorization_before": "review-and-fix",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "artifact_store": str(tmp_path / "repair"),
            "state_verification_command": shlex.join([sys.executable, str(frozen_capture), "--repo", str(repository), "--mode", "baseline"]),
        }
    )
    assert advanced["new_plan"]["review_lifecycle"]["repairs_completed"] == 1
    assert advanced["new_plan"]["coalesced_validation_units"]
    assert Path(reference["path"]).read_bytes() == retained
    assert verify_snapshot(reference).files
