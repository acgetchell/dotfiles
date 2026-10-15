"""Explicit reader grammars and truthful external instruction provenance."""

import json
import shlex
from pathlib import Path

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_git import refresh_comparison_scope
from review_graph_plan import plan_from_document
from review_graph_read_provenance import MissingReadProvenanceError, file_identity, verify_runtime_inputs
from review_graph_reads import source_read_operands
from review_graph_session import runtime_command
from test_review_graph_git import _accept, _discovery_payload
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compact_audit_payload,
    _mutation_with_audit_source,
    _publish_worker_bytes,
    _run_test_git,
    _worker_input_fixture,
)
from test_review_graph_transitions import _materialize, _staging_fixture


@pytest.mark.parametrize("paths", [["tool.py", "added.txt"], ["tool.py"]])
def test_repair_refreshes_added_and_removed_paths_without_changing_fixed_base(paths: list[str]) -> None:
    base = "a" * 40
    previous = {"head": base, "merge_base": None, "captured_scope_paths": ["tool.py", "old.txt"]}
    command = f"git diff {base} -- tool.py old.txt"
    updated = refresh_comparison_scope(command, previous, {"captured_scope_paths": paths})
    assert shlex.split(updated) == ["git", "diff", base, "--", *paths]
    assert previous["captured_scope_paths"] == ["tool.py", "old.txt"]


def test_unsupported_repair_comparison_requests_correction_before_dispatch() -> None:
    with pytest.raises(ValueError, match="plain git diff against the captured immutable base"):
        refresh_comparison_scope("custom comparison script", {"captured_scope_paths": ["old.py"]}, {"captured_scope_paths": ["old.py", "new.py"]})


@pytest.mark.parametrize("damage", ["changed", "missing", "symlink", "repository"])
def test_bound_external_reads_require_unchanged_external_regular_files(tmp_path: Path, damage: str) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    path = (repository if damage == "repository" else tmp_path) / "instruction.md"
    path.write_text("Required instructions\n")
    inputs = ((str(path), file_identity(str(path))),)
    if damage == "changed":
        path.write_text("Different instructions\n")
    elif damage == "missing":
        path.unlink()
    elif damage == "symlink":
        target = tmp_path / "target.md"
        path.rename(target)
        path.symlink_to(target)
    with pytest.raises(ValueError, match="runtime read"):
        verify_runtime_inputs(inputs, str(repository))


def test_arbitrary_external_declaration_cannot_be_relabelled_for_repair_reuse(tmp_path: Path) -> None:
    external = tmp_path / "external.md"
    external.write_text("Unbound context\n")
    request, entry, _source = _mutation_with_audit_source(tmp_path, nearby_contract_owners=(str(external),))
    result = runtime.advance_after_mutation(request)
    assert entry["dispatch"]["evidence_id"] not in result["reused_evidence_ids"]
    assert any(item["reason_code"] == "input-proof-failed" for item in result["reuse_decisions"])


@pytest.mark.parametrize("flags", ["-n -A2 -B1", "-C3", "--after-context=2 --before-context=1", "--context 3", "--color never -n"])
def test_rg_context_options_resolve_only_actual_file_operands(flags: str) -> None:
    assert source_read_operands(f"rg {flags} 'two words' AGENTS.md pyproject.toml") == ("AGENTS.md", "pyproject.toml")


@pytest.mark.parametrize("program", ["1p", "1,600p", "-e '12,35p'"])
def test_numeric_sed_selection_is_a_bounded_reader(program: str) -> None:
    assert source_read_operands(f"sed -n {program} 'source file.py'") == ("source file.py",)


@pytest.mark.parametrize(
    "command",
    [
        "rg --pre processor pattern tool.py",
        "rg -Ainvalid pattern tool.py",
        "rg --unknown pattern tool.py",
        "rg -f patterns tool.py",
        "rg pattern",
        "cat tool.py; touch changed",
        "cat tool.py#suffix; git log --oneline",
        "cat tool.py # comment; git log --oneline",
        "cat 'tool.py#suffix'; git log --oneline",
        "cat $(pwd)/tool.py",
        "sed -i '1p' tool.py",
        "sed -n '1,10w /tmp/output' tool.py",
        "sed -n '1e id' tool.py",
        "sed -n '1,10p;10q' tool.py",
        "sed -n /pattern/p tool.py",
        "sed -n '1,$p' tool.py",
    ],
)
def test_ambiguous_readers_remain_unclassified(command: str) -> None:
    assert source_read_operands(command) is None


@pytest.mark.parametrize("operand", ["tool.py#suffix", "'tool.py#suffix'", '"tool.py#suffix"'])
def test_hash_bearing_reader_operands_keep_their_actual_identity(operand: str) -> None:
    assert source_read_operands(f"cat {operand}") == ("tool.py#suffix",)


@pytest.mark.parametrize("content", [None, "", "{", "[]", "null", "{}"])
def test_failed_capture_does_not_prevent_truthful_blocked_publication(tmp_path: Path, content: str | None) -> None:
    document, _entries = _worker_input_fixture(tmp_path)
    command = shlex.join([*runtime_command(Path(runtime.__file__).with_name("capture_scope.py")), "--mode", "baseline"])
    document["artifact_store"] = str(tmp_path / "failed-capture-proof")
    document["state_verification_command"] = command
    entries = runtime.materialize_dispatches(document)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit")
    output = tmp_path / "failed-capture.json"
    if content is not None:
        output.write_text(content)
    ledger = [command + " > " + shlex.quote(str(output))]
    payload = {**_compact_audit_payload(entry, commands=tuple(ledger)), "status": "blocked", "limitations": ["Source capture failed before verification."]}
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert json.loads(Path(entry["worker_payload_path"]).read_bytes()) == payload
    _native, metadata = runtime.compile_review(
        {"dispatch": {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}, "payload": payload}
    )
    inputs = metadata["expectation"]["audit_input_identity"]
    assert str(output) not in dict(inputs.get("runtime_inputs", []))
    assert ledger[0] not in inputs.get("protocol_commands", [])
    assert metadata["normalized_record"]["commands_executed"] == ledger


@pytest.mark.parametrize("reader", ["rg -n -A2 -B1 value tool.py", "sed -n '1,600p' tool.py"])
def test_live_staging_span_keeps_actual_reader_ledger(tmp_path: Path, reader: str) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    payload = _discovery_payload(audit)
    payload["commands_executed"] = [reader]
    payload["git_dependencies"] = []
    source = _accept(request, audit, payload)
    original = Path(source["artifact_path"]).read_bytes()
    result = runtime.resume_after_external_metadata(request)
    assert audit["node_id"] in result["preserved_node_ids"]
    assert Path(source["artifact_path"]).read_bytes() == original
    record = runtime._load_evidence_source(source, require_normalized=True)[4]
    assert isinstance(record, dict)
    assert record["commands_executed"] == [reader]


@pytest.mark.parametrize("operation", ["schedule-ready", "fallback-to-coordinator"])
def test_relocated_coordinator_reads_remain_bound_across_staging(tmp_path: Path, operation: str) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    (repository / "tool.py").write_text("value = 2\n")
    capture = _scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    audit = next(entry for entry in entries["dispatches"] if entry["dispatch"].get("mode") == "audit")
    request = {**lifecycle, "artifact_store": str(tmp_path / "coordinator")}
    if operation == "schedule-ready":
        request["worker_capacity"] = {"source": "fixture", "concurrent_worker_limit": 3, "active_workers": 3}
    else:
        request.update(node_id=audit["node_id"], worker_created=False, reason="fixture capacity exhaustion")
    request_path, capture_path, journal = (tmp_path / name for name in ("request.json", "capture.json", "journal.jsonl"))
    request_path.write_text(json.dumps(request))
    capture_path.write_text(json.dumps(capture))
    output = tmp_path / "relocated.json"
    arguments = {"input": request_path, "dispatches": dispatches, "current-capture": capture_path, "journal": journal, "output": output}
    assert runtime.main([operation, *(arg for key, path in arguments.items() for arg in (f"--{key}", str(path)))]) == 0
    relocated = json.loads(output.read_text())
    updated = json.loads(Path(relocated["dispatches_path"]).read_text())
    entry = next(item for item in updated["dispatches"] if item["dispatch"]["execution_location"] == "coordinator")
    protocol_paths = [entry[field] for field in ("worker_input_path", "worker_execution_path", "worker_payload_contract_path")]
    payload = _compact_audit_payload(entry, commands=(shlex.join(["cat", *protocol_paths]),))
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    current = {**lifecycle, "journal_path": str(journal)}
    source = _accept(current, entry, payload)
    originals = {path: Path(path).read_bytes() for path in source.values()}
    _run_test_git(git, "-C", str(repository), "add", "tool.py")
    resumed = runtime.resume_after_external_metadata(
        {
            **current,
            "dispatches_path": relocated["dispatches_path"],
            "previous_capture": capture,
            "new_capture": _scope_data(git, repository, "baseline", None, ()),
            "artifact_store": str(tmp_path / "resumed"),
        }
    )
    assert entry["node_id"] in resumed["preserved_node_ids"]
    metadata = json.loads(Path(entry["metadata_path"]).read_text())
    assert set(protocol_paths) <= dict(metadata["expectation"]["audit_input_identity"]["runtime_inputs"]).keys()
    assert metadata["normalized_record"]["commands_executed"] == payload["commands_executed"]
    assert all(Path(path).read_bytes() == content for path, content in originals.items())


def test_undeclared_reader_operand_cannot_hide_external_dependency(tmp_path: Path) -> None:
    _git, _repository, request, audit, _entries = _staging_fixture(tmp_path)
    payload = _discovery_payload(audit)
    payload["commands_executed"] = ["sed -n '1,600p' /unbound/external.py"]
    payload["git_dependencies"] = []
    _accept(request, audit, payload)
    result = runtime.resume_after_external_metadata(request)
    assert audit["node_id"] in result["recheck_node_ids"]
    decision = next(item for item in result["node_decisions"] if item["node_id"] == audit["node_id"])
    assert any(reason.get("path") == "/unbound/external.py" for reason in decision["reasons"])


def test_required_instruction_declaration_has_one_preserved_correction(tmp_path: Path) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit")
    payload = _compact_audit_payload(entry)
    missing = payload["nearby_contract_owners"].pop()
    payload["commands_executed"] = [shlex.join(["cat", missing])]
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    rejected = json.dumps(payload).encode()
    with pytest.raises(MissingReadProvenanceError, match="required instruction-read provenance") as failure:
        runtime.publish_worker_payload_bytes(contract, rejected)
    assert missing in str(failure.value)
    assert not Path(entry["worker_payload_path"]).exists()
    attempts = runtime._provenance_attempts(contract)
    assert len(attempts) == 1
    assert json.loads(attempts[0].read_bytes())["payload"] == payload
    payload["nearby_contract_owners"].append(missing)
    corrected = json.dumps(payload).encode()
    runtime.publish_worker_payload_bytes(contract, corrected)
    assert Path(entry["worker_payload_path"]).read_bytes() == corrected
    assert runtime._provenance_attempts(contract) == attempts


def test_second_incomplete_provenance_attempt_exhausts_the_single_correction(tmp_path: Path) -> None:
    _lifecycle, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "audit")
    payload = _compact_audit_payload(entry)
    required = payload["nearby_contract_owners"]
    payload["nearby_contract_owners"] = []
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    for commands in ([], ["cat tool.py"]):
        payload["commands_executed"] = commands
        with pytest.raises(MissingReadProvenanceError):
            runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    payload["nearby_contract_owners"] = required
    with pytest.raises(ValueError, match="provenance correction exhausted"):
        runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    assert len(runtime._provenance_attempts(contract)) == 2
    assert not Path(entry["worker_payload_path"]).exists()
