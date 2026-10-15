"""Explicit reader grammars and truthful external instruction provenance."""

import json
import shlex
from pathlib import Path

import pytest
import review_graph_runtime as runtime
from review_graph_git import refresh_comparison_scope
from review_graph_read_provenance import MissingReadProvenanceError, file_identity, verify_runtime_inputs
from review_graph_reads import source_read_operands
from test_review_graph_git import _accept, _discovery_payload
from test_review_graph_runtime import _compact_audit_payload, _mutation_with_audit_source, _worker_input_fixture
from test_review_graph_transitions import _staging_fixture


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
