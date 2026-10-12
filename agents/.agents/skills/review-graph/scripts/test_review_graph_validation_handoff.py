"""Standard typed validation handoffs preserve executions without metadata reruns."""

import json
from argparse import Namespace
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from review_graph_reuse import source_snapshot
from review_graph_validation import ValidationRecord, ValidationStatus, VerifiedValidationRecord
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _complete_structural_fixture_routing,
    _execution_payload,
    _publish_worker_bytes,
    _run_test_git,
)
from test_review_graph_transitions import _materialize


def _handoff(  # noqa: PLR0913 - orthogonal fixture execution and contract controls.
    tmp_path: Path,
    *,
    dependencies: list[dict[str, str]] | None = None,
    result: str = "passed",
    failure_kind: str | None = None,
    prefixes: list[str] | None = None,
    contract: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, Path, dict[str, Any]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    commands = template["validation_requirements"][0]["commands"]
    registry = {
        "schema_version": 1,
        "contracts": [
            {
                "contract_id": "fixture-check",
                "commands": commands,
                "working_directories": ["."],
                "implementation_paths": ["tool.py"],
                "input_scope": "repository" if prefixes is None else "prefixes",
                "input_prefixes": prefixes or [],
                "git_inputs": [],
                "deterministic": True,
                "rationale": "The fixture check depends on captured source only.",
            }
        ],
    }
    registry["contracts"].append({**registry["contracts"][0], "contract_id": "another-check", "commands": ["echo other"], "implementation_paths": ["LICENSE"]})
    if contract:
        (repository / "review-validation-contracts.json").write_text(json.dumps(registry))
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, list(source_snapshot(capture).captured_scope_paths))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    journal = tmp_path / "execution.jsonl"
    lifecycle.update(journal_path=str(journal), dispatches_path=str(dispatches))
    entry = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    payload = _execution_payload(entry, result, 1 if result == "failed" else 0, "1s")
    if failure_kind is not None:
        payload["failure_kind"] = failure_kind
    if dependencies is not None:
        payload["git_dependencies"] = dependencies
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps(capture))
    after.write_text(json.dumps(capture))
    workspace = runtime.capture_workspace_snapshot(entry["dispatch"])
    workspace_path = tmp_path / "workspace.json"
    workspace_path.write_text(json.dumps(workspace))
    runtime._compile_node_from_files(
        lifecycle,
        Namespace(
            dispatches=dispatches,
            node_id=entry["node_id"],
            before_capture=before,
            after_capture=after,
            workspace_before=workspace_path,
            workspace_after=workspace_path,
            payload=None,
            status=None,
            limitation=None,
            journal=journal,
            output=tmp_path / "compiled.json",
        ),
    )
    metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
    return lifecycle, entry, capture, git, repository, metadata


@pytest.mark.parametrize("change", ["stage", "branch", "commit"])
def test_standard_source_only_record_survives_metadata_handoff_without_rerunning(tmp_path: Path, change: str) -> None:
    lifecycle, entry, capture, git, repository, metadata = _handoff(tmp_path, dependencies=[])
    record = ValidationRecord.from_raw(metadata["normalized_record"])
    assert record.status == ValidationStatus.PASSED
    assert record.source_inputs is not None
    assert record.source_inputs.git_tree_id == capture["repository_git_tree_id"]
    saved = {key: Path(entry[key]).read_bytes() for key in ("artifact_path", "metadata_path", "worker_payload_path")}
    if change == "branch":
        _run_test_git(git, "-C", str(repository), "checkout", "-b", "fix/handoff")
    elif change == "commit":
        _run_test_git(git, "-C", str(repository), "commit", "--allow-empty", "-m", "Authorized context change")
    else:
        (repository / "tool.py").write_text("value = 2\n")
        _run_test_git(git, "-C", str(repository), "add", "tool.py")
        (repository / "tool.py").write_text("value = 1\n")
    current = _scope_data(git, repository, "baseline", None, ())
    result = runtime.resume_after_external_metadata(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": current,
            "artifact_store": str(tmp_path / "continued"),
            "git_context_authorization": "Observe the authorized commit or rebase.",
        }
    )
    assert entry["node_id"] in result["preserved_node_ids"]
    assert current["repository_git_tree_id"] == capture["repository_git_tree_id"]
    assert {key: Path(entry[key]).read_bytes() for key in saved} == saved
    verified = runtime._load_evidence_source({key: entry[key] for key in ("artifact_path", "metadata_path")}, require_normalized=True)[4]
    assert isinstance(verified, VerifiedValidationRecord)
    assert not runtime._metadata_evidence_blockers(result["lifecycle_input"], [verified])
    ready = runtime.next_ready_nodes(
        {**result["lifecycle_input"], "current_source_state": result["current_source_state"]},
        journal_events=runtime.read_execution_journal(
            Path(result["journal_path"]), plan=runtime._graph_plan(result["lifecycle_input"]["plan"]), source_state=tuple(lifecycle["source_state"])
        )[0],
        dispatch_set=json.loads(Path(result["dispatches_path"]).read_bytes()),
    )
    assert entry["node_id"] not in {item["node_id"] for item in ready["ready_dispatches"]}


@pytest.mark.parametrize("dependencies", [[{"kind": "head", "reason": "The recipe checks HEAD."}]])
def test_declared_git_input_is_compared_with_the_current_context(tmp_path: Path, dependencies: list[dict[str, str]] | None) -> None:
    lifecycle, entry, capture, git, repository, _metadata = _handoff(tmp_path, dependencies=dependencies)
    _run_test_git(git, "-C", str(repository), "commit", "--allow-empty", "-m", "New HEAD")
    current = _scope_data(git, repository, "baseline", None, ())
    result = runtime.resume_after_external_metadata(
        {
            **lifecycle,
            "previous_capture": capture,
            "new_capture": current,
            "artifact_store": str(tmp_path / "continued"),
            "git_context_authorization": "Observe the authorized commit or rebase.",
        }
    )
    assert entry["node_id"] not in result["preserved_node_ids"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "unknown"), ("command_identity_digest", "wrong"), ("observed_source_state", []), ("git_dependencies", [{}]), ("executions", [{}])],
)
def test_reader_rejects_malformed_standard_record_before_using_it(tmp_path: Path, field: str, value: object) -> None:
    _lifecycle, entry, _capture, _git, _repository, metadata = _handoff(tmp_path, dependencies=[])
    before = Path(entry["metadata_path"]).read_bytes()
    with pytest.raises((ValueError, TypeError)):
        ValidationRecord.from_raw({**metadata["normalized_record"], field: value})
    assert Path(entry["metadata_path"]).read_bytes() == before


def test_parsed_record_is_immutable_and_replacements_preserve_invariants(tmp_path: Path) -> None:
    _lifecycle, _entry, _capture, _git, _repository, metadata = _handoff(tmp_path, dependencies=[])
    record = ValidationRecord.from_raw(metadata["normalized_record"])
    field = "status"
    with pytest.raises(FrozenInstanceError):
        setattr(record, field, ValidationStatus.FAILED)
    with pytest.raises(ValueError, match="failed execution"):
        replace(record, status=ValidationStatus.FAILED)
    with pytest.raises(TypeError, match="immutable tuple"):
        replace(record, executions=list(record.executions))


@pytest.mark.parametrize("invalid", ["git-command", "unknown-dependency", "contradictory-result", "null-dependencies"])
def test_invalid_validation_is_rejected_before_payload_publication(tmp_path: Path, invalid: str) -> None:
    _git, _repository, _template, capture, plan = _baseline_mutation_fixture(tmp_path)
    _lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    payload: dict[str, Any] = {**_execution_payload(entry, "passed", 0, "1s"), "git_dependencies": []}
    if invalid == "git-command":
        payload["executions"][0]["command"] = "git diff --cached --exit-code"
    elif invalid == "unknown-dependency":
        payload["git_dependencies"] = [{"kind": "unknown", "reason": "unsupported"}]
    elif invalid == "contradictory-result":
        payload["status"] = "failed"
    else:
        payload["git_dependencies"] = None
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    with pytest.raises((ValueError, TypeError)):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert not Path(entry["worker_payload_path"]).exists()
    assert not Path(entry["metadata_path"]).exists()
    assert not Path(entry["artifact_path"]).exists()


def test_another_reviewers_requirement_binds_to_the_existing_exact_execution(tmp_path: Path) -> None:
    lifecycle, entry, _capture, _git, _repository, metadata = _handoff(tmp_path, dependencies=[])
    plan = runtime._graph_plan(lifecycle["plan"])
    unit = next(item for item in plan.coalesced_validation_units if item.node_id == entry["node_id"])
    requirement = {
        "requirement_id": "second-reviewer-same-check",
        "planned_validation_digest": runtime._planned_validation_digest(unit),
        "owner": "review-validator",
        "reason": "Verify the same dispatched execution contract.",
        "expected_evidence": "Existing standard validation evidence passes.",
    }
    audit = {"status": "no-findings", "evidence_id": "review:second", "validation_requirements": [requirement]}
    report = runtime._validation_reconciliation(plan, [audit, metadata["normalized_record"]])
    assert report["blockers"] == []
    assert report["requirements"][0]["validation_unit_id"] == unit.node_id
    assert report["requirements"][0]["resolution"] == "planned"
    requirement["planned_validation_digest"] = runtime._planned_validation_digest(replace(unit, environment="another toolchain"))
    assert runtime._validation_reconciliation(plan, [audit])["requirements"][0]["resolution"] == "requires-expansion"


def _verified(entry: dict[str, Any]) -> VerifiedValidationRecord:
    return runtime.load_validation_record(metadata_path=Path(entry["metadata_path"]), artifact_path=Path(entry["artifact_path"]))


def _applicability(record: VerifiedValidationRecord, capture: dict[str, Any], **unit_changes: Any) -> list[dict[str, str]]:
    return record.applicability_reasons(
        source_snapshot(capture),
        current_unit=replace(record.expectation.validation_unit, **unit_changes),
        observe_artifact=lambda artifact: (artifact.digest, artifact.digest_mode),
    )


@pytest.mark.parametrize("prefixes", [None, ["tool.py", "fixtures"]])
def test_default_tree_and_explicit_input_selection_handle_irrelevant_edits_and_new_files(tmp_path: Path, prefixes: list[str] | None) -> None:
    _lifecycle, entry, _capture, git, repository, _metadata = _handoff(tmp_path, prefixes=prefixes)
    record = _verified(entry)
    (repository / "LICENSE").write_text("unrelated document edit")
    target = _scope_data(git, repository, "baseline", None, ())
    assert bool(_applicability(record, target)) == (prefixes is None)
    (repository / "unrelated-link").symlink_to("LICENSE")
    assert bool(_applicability(record, _scope_data(git, repository, "baseline", None, ()))) == (prefixes is None)
    (repository / "fixtures").mkdir()
    (repository / "fixtures" / "new.txt").write_text("new selected input")
    assert _applicability(record, _scope_data(git, repository, "baseline", None, ()))[0]["reason_code"] == "validation-inputs-changed"
    (repository / "fixtures" / "new.txt").unlink()
    (repository / "tool.py").unlink()
    assert _applicability(record, _scope_data(git, repository, "baseline", None, ()))


@pytest.mark.parametrize("kind", ["source", "infrastructure", "timeout", "inconclusive"])
def test_failed_results_retain_negative_status_and_only_source_failures_survive_handoff(tmp_path: Path, kind: str) -> None:
    lifecycle, entry, capture, git, repository, _metadata = _handoff(tmp_path, result="failed", failure_kind=kind)
    record = _verified(entry)
    original = Path(entry["metadata_path"]).read_bytes()
    _run_test_git(git, "-C", str(repository), "switch", "-c", "fix/failed-evidence")
    current = _scope_data(git, repository, "baseline", None, ())
    continued = runtime.resume_after_external_metadata(
        {**lifecycle, "previous_capture": capture, "new_capture": current, "artifact_store": str(tmp_path / "continued")}
    )
    assert (entry["node_id"] in continued["preserved_node_ids"]) == (kind == "source")
    assert Path(entry["metadata_path"]).read_bytes() == original
    assert record.record.status == ValidationStatus.FAILED
    if kind == "source":
        report = runtime.report_delivery(
            {
                **continued["lifecycle_input"],
                "current_source_state": continued["current_source_state"],
                "sources": [{key: entry[key] for key in ("artifact_path", "metadata_path")}],
            }
        )
        assert report["repository_readiness"] == "blocked"
        assert report["validation"][0]["status"] == "failed"


@pytest.mark.parametrize("change", ["contract", "recipe", "environment", "command"])
def test_contract_recipe_or_execution_changes_invalidate_a_narrow_binding(tmp_path: Path, change: str) -> None:
    _lifecycle, entry, _capture, git, repository, _metadata = _handoff(tmp_path, prefixes=["fixtures"])
    record = _verified(entry)
    changes = {}
    if change == "contract":
        path = repository / "review-validation-contracts.json"
        data = json.loads(path.read_text())
        data["contracts"][0]["rationale"] = "A changed contract"
        path.write_text(json.dumps(data))
    elif change == "recipe":
        (repository / "tool.py").write_text("new implementation")
    elif change == "environment":
        changes["environment"] = "a different toolchain"
    else:
        changes["commands"] = ("another command",)
    assert _applicability(record, _scope_data(git, repository, "baseline", None, ()), **changes)
    # A new incoming agent can still verify immutable historical evidence.
    assert _verified(entry).record == record.record


def test_worker_empty_dependencies_do_not_authorize_reuse_of_an_unknown_command(tmp_path: Path) -> None:
    _lifecycle, entry, capture, _git, _repository, _metadata = _handoff(tmp_path, dependencies=[], contract=False)
    assert _applicability(_verified(entry), capture)[0]["reason_code"] == "validation-contract-unavailable"


@pytest.mark.parametrize("invalid", ["command", "directory", "executor", "version", "reported-root", "reused"])
def test_dispatch_mismatch_or_retired_format_never_writes_a_payload(tmp_path: Path, invalid: str) -> None:
    _git, _repository, _template, capture, plan = _baseline_mutation_fixture(tmp_path)
    _lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["result_contract"] == "compact-validation")
    payload = _execution_payload(entry, "passed", 0, "1s")
    if invalid == "reused":
        payload.update(status="reused", executions=[])
    elif invalid == "reported-root":
        payload["artifacts"] = [
            {
                "path": "unknown-root",
                "kind": "log",
                "repository_status": "outside-repository",
                "artifact_digest": "sha256:" + "0" * 64,
                "artifact_digest_mode": "content-sha256-v1",
            }
        ]
    elif invalid == "version":
        payload["schema_version"] = 2
    else:
        field = {"command": "command", "directory": "working_directory", "executor": "executor"}[invalid]
        payload["executions"][0][field] = "none" if invalid == "executor" else "incorrect"
    before = {path: path.read_bytes() for path in Path(entry["worker_payload_path"]).parent.iterdir() if path.is_file()}
    with pytest.raises((ValueError, TypeError)):
        runtime.publish_worker_payload_bytes(json.loads(Path(entry["worker_payload_contract_path"]).read_bytes()), json.dumps(payload).encode())
    assert {path: path.read_bytes() for path in before} == before
    assert not Path(entry["worker_payload_path"]).exists()


def test_accepted_journal_collection_loads_each_incoming_record_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lifecycle, entry, _capture, _git, _repository, _metadata = _handoff(tmp_path)
    plan = runtime._graph_plan(lifecycle["plan"])
    state = tuple(lifecycle["source_state"])
    dispatches = runtime._dispatches_by_node(json.loads(Path(lifecycle["dispatches_path"]).read_bytes()), plan=plan, source_state=state)
    events = runtime.read_execution_journal(Path(lifecycle["journal_path"]), plan=plan, source_state=state)[0]
    original = runtime._load_evidence_source
    reads = []

    def counted(*args: Any, **kwargs: Any) -> Any:
        reads.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime, "_load_evidence_source", counted)
    sources, records = runtime._accepted_journal_sources(plan, state, events, dispatches)
    assert set(sources) == {entry["node_id"]}
    assert len(reads) == 1
    assert isinstance(records[0], VerifiedValidationRecord)


def test_loader_binds_semantics_to_sealed_worker_bytes_even_if_their_digest_is_relabelled(tmp_path: Path) -> None:
    _lifecycle, entry, _capture, _git, _repository, metadata = _handoff(tmp_path)
    native = Path(entry["artifact_path"]).read_bytes()
    sealed = Path(metadata["worker_payload_path"])
    payload = json.loads(sealed.read_bytes())
    payload["executions"][0]["evidence"] = "changed worker observations"
    content = json.dumps(payload).encode()
    sealed.chmod(0o600)
    sealed.write_bytes(content)
    metadata["worker_payload_digest"] = runtime.digest_bytes(content)
    metadata["worker_payload_byte_count"] = len(content)
    Path(entry["metadata_path"]).chmod(0o600)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="differs from sealed worker bytes"):
        _verified(entry)
    assert Path(entry["artifact_path"]).read_bytes() == native


def test_loader_rejects_a_valid_registry_contract_for_a_different_execution(tmp_path: Path) -> None:
    _lifecycle, entry, _capture, _git, _repository, metadata = _handoff(tmp_path)
    binding = metadata["normalized_record"]["contract_binding"]
    registry = json.loads(binding["registry_content"])
    binding["contract"] = registry["contracts"][1]
    path = Path(entry["metadata_path"])
    path.chmod(0o600)
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="does not match its dispatched execution"):
        _verified(entry)
