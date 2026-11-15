"""Real frozen operations retain their ledgers and prove bounded discovery reuse."""

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from review_graph_discovery import SourceDiscovery, bind_discovery
from review_graph_eligibility import reuse_eligibility
from review_graph_read_provenance import bind_runtime_reads
from review_graph_reuse import source_snapshot
from test_review_graph_continuity_e2e import _frozen_run
from test_review_graph_runtime import _compact_audit_payload
from test_review_graph_sessions import _cli


def _shell(command: str, repository: Path) -> bytes:
    shell = shutil.which("sh")
    assert shell is not None
    return subprocess.run([shell, "-c", command], cwd=repository, check=True, capture_output=True, timeout=60).stdout  # noqa: S603 - exact generated fixture commands.


def _instruction_commands(dispatch: dict[str, Any]) -> list[str]:
    context = dispatch["instruction_context"]
    manifest = json.loads(Path(context["manifest"]["path"]).read_bytes())
    return [
        shlex.join([*context["read_command"], "--path", record["path"], "--chunk", str(index)])
        for record in manifest["files"]
        for index in range(len(record["chunks"]))
    ]


@pytest.mark.parametrize("change", ["unrelated", "selected-path-added", "dependency"])
def test_frozen_discovery_publication_compilation_and_actual_reuse(tmp_path: Path, change: str) -> None:
    git, repository, bundle, dispatches, frozen, dispatch_path = _frozen_run(tmp_path, early=False)
    audit = next(entry for entry in dispatches["dispatches"] if entry["dispatch"].get("skill_id") == "python-cli-review")
    dispatch = audit["dispatch"]
    payload = _compact_audit_payload(audit)
    commands = ["\n".join([*_instruction_commands(dispatch), dispatch["audit_observations"]["before"]["capture_command"]])]
    _shell(commands[0], repository)
    discovery = shlex.join([*dispatch["source_discovery"]["command"], "--path", ".", "--glob", "*.py"])
    observed = json.loads(_shell(discovery, repository))
    assert observed["selected_paths"] == ["tool.py"]
    commands.append(discovery)
    reads = shlex.join(["cat", "--", *payload["files_inspected"], *payload["nearby_contract_owners"]])
    commands.append(reads + "\n" + dispatch["audit_observations"]["after"]["capture_command"])
    _shell(commands[-1], repository)
    own = shlex.join(["cat", audit["worker_payload_path"]])
    publish = shlex.join(dispatch["worker_payload_persistence"]["publish_command"]) + " < " + shlex.quote(audit["worker_payload_path"])
    payload["commands_executed"] = [*commands, own, publish]
    original_payload = json.dumps(payload).encode()
    Path(audit["worker_payload_path"]).write_bytes(original_payload)
    assert _shell(own, repository) == original_payload
    publication = json.loads(_shell(publish, repository))
    assert publication["reuse_eligibility"]["status"] == "no-known-ledger-blockers"
    journal = tmp_path / "journal.jsonl"
    compiled = tmp_path / "compiled.json"
    _cli(
        frozen,
        "compile-node",
        "--input",
        str(tmp_path / "bootstrap.json"),
        "--dispatches",
        str(dispatch_path),
        "--journal",
        str(journal),
        "--node-id",
        audit["node_id"],
        "--before-capture",
        dispatch["audit_observations"]["before"]["capture_path"],
        "--after-capture",
        dispatch["audit_observations"]["after"]["capture_path"],
        "--output",
        str(compiled),
    )
    assert json.loads(compiled.read_bytes())["journal_event"]["status"] == "accepted"
    metadata = json.loads(Path(audit["metadata_path"]).read_bytes())
    assert metadata["normalized_record"]["commands_executed"] == payload["commands_executed"]
    assert metadata["expectation"]["audit_input_identity"]["source_discoveries"] == [{"paths": ["."], "globs": ["*.py"], "selected_paths": ["tool.py"]}]
    protected = {Path(audit[key]): Path(audit[key]).read_bytes() for key in ("worker_payload_path", "artifact_path", "metadata_path")}
    changed = "new.py" if change == "selected-path-added" else "tool.py" if change == "dependency" else "state.rs"
    (repository / changed).write_text("value = 2\n" if changed.endswith(".py") else "pub fn state() { let value = 2; }\n")
    if change == "selected-path-added":
        # Give the added path its own existing owner so this tests discovery
        # invalidation, not an unrelated incomplete-routing failure.
        owner = next(item for item in bundle["planning_input"]["routing_overrides"] if item["catalog_id"] == "python.api-design")
        owner["review_surface"].append(changed)
    current = _scope_data(git, repository, "baseline", None, ())
    request = {
        **bundle["lifecycle_input"],
        "previous_capture": bundle["capture"],
        "new_capture": current,
        "planning_template": bundle["planning_input"],
        "repair_epoch": 1,
        "changed_paths": [changed],
        "authorization_before": "review-and-fix",
        "authorization_after": "review-and-fix",
        "state_verification_command": bundle["materialization_input"]["state_verification_command"],
        "journal_path": str(journal),
        "dispatches_path": str(dispatch_path),
        "artifact_store": str(tmp_path / "repair"),
    }
    request_path, output = tmp_path / "request.json", tmp_path / "resumed.json"
    request_path.write_text(json.dumps(request))
    _cli(frozen, "advance-after-mutation", "--input", str(request_path), "--output", str(output))
    result = json.loads(output.read_bytes())
    assert (dispatch["evidence_id"] in result["reused_evidence_ids"]) is (change == "unrelated")
    assert all(path.read_bytes() == content for path, content in protected.items())


@pytest.fixture
def discovered_audit(tmp_path: Path) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    """Prepare exact captures and bound commands without claiming an accepted audit."""
    _git, repository, _bundle, dispatches, _frozen, _path = _frozen_run(tmp_path, early=False)
    entry = next(item for item in dispatches["dispatches"] if item["dispatch"].get("skill_id") == "python-cli-review")
    dispatch = entry["dispatch"]
    _shell(dispatch["audit_observations"]["before"]["capture_command"], repository)
    command = shlex.join([*dispatch["source_discovery"]["command"], "--path", ".", "--glob", "*.py"])
    payload = _compact_audit_payload(entry)
    return repository, dispatch, payload, command


@pytest.mark.parametrize(
    "suffix", [" --unknown yes", " --path", " && true", "; true", " | cat", "\npython -c 'pass'", " --glob '*.rs' --hidden", " --glob *.py"]
)
def test_unknown_or_compound_operations_remain_in_original_ledger(discovered_audit: tuple[Path, dict[str, Any], dict[str, Any], str], suffix: str) -> None:
    repository, dispatch, payload, command = discovered_audit
    command += suffix
    payload["commands_executed"] = [command]
    bound = bind_runtime_reads(dispatch, payload)
    assert bound.commands == ()
    diagnostic = reuse_eligibility({**payload, "runtime_inputs": bound.inputs, "protocol_commands": bound.commands}, str(repository))
    assert diagnostic["reason_counts"] == {"unclassified-command": 1}
    assert diagnostic["blockers"][0]["command"] == command


def test_mixed_protocol_reads_preserve_hidden_external_dependencies(discovered_audit: tuple[Path, dict[str, Any], dict[str, Any], str], tmp_path: Path) -> None:
    repository, dispatch, payload, command = discovered_audit
    outside = tmp_path / "unbound.txt"
    outside.write_text("external evidence\n")
    payload["commands_executed"] = [command + "\n" + shlex.join(["cat", str(outside)])]
    bound = bind_runtime_reads(dispatch, payload)
    diagnostic = reuse_eligibility({**payload, "runtime_inputs": bound.inputs, "protocol_commands": bound.commands}, str(repository))
    assert diagnostic["reason_counts"] == {"unbound-external-read": 1}
    assert diagnostic["blockers"][0]["path"] == str(outside)


def test_changed_bound_arguments_remain_unclassified(discovered_audit: tuple[Path, dict[str, Any], dict[str, Any], str]) -> None:
    _repository, dispatch, payload, command = discovered_audit
    other = "/unbound/protocol.json"
    payload["commands_executed"] = [
        command.replace(dispatch["source_discovery"]["capture_path"], other),
        command.replace(",".join(dispatch["source_state"]), "changed-state"),
        dispatch["audit_observations"]["before"]["capture_command"].replace(dispatch["audit_observations"]["before"]["capture_path"], other),
        shlex.join([*dispatch["worker_payload_persistence"]["publish_command"][:-1], other]),
        shlex.join([*dispatch["instruction_context"]["read_command"], "--path", other, "--chunk", "0"]),
    ]
    assert bind_runtime_reads(dispatch, payload).commands == ()


@pytest.mark.parametrize("artifact", ["capture", "receipt", "contract", "execution", "payload"])
def test_changed_protocol_artifacts_fail_binding(discovered_audit: tuple[Path, dict[str, Any], dict[str, Any], str], artifact: str) -> None:
    _repository, dispatch, payload, command = discovered_audit
    observation = dispatch["audit_observations"]["before"]
    paths = {
        "capture": observation["capture_path"],
        "receipt": observation["receipt_path"],
        "contract": dispatch["worker_payload_persistence"]["input_path"],
        "execution": dispatch["protocol_input_paths"][1],
        "payload": dispatch["worker_payload_path"],
    }
    path = Path(paths[artifact])
    if artifact == "payload":
        path.write_text('{"status":"changed"}')
        payload["commands_executed"] = [shlex.join(dispatch["worker_payload_persistence"]["publish_command"]) + " < " + shlex.quote(str(path))]
    else:
        path.chmod(0o644)
        value = json.loads(path.read_bytes())
        value["capture_digest" if artifact == "receipt" else "repository_state_fingerprint" if artifact == "capture" else "tampered"] = "changed"
        path.write_text(json.dumps(value))
        payload["commands_executed"] = [observation["capture_command"] if artifact == "receipt" else command]
    with pytest.raises(ValueError, match=r"source snapshot|protocol.*differs"):
        bind_runtime_reads(dispatch, payload)


def test_discovery_empty_selection_and_literal_roots(discovered_audit: tuple[Path, dict[str, Any], dict[str, Any], str]) -> None:
    _repository, dispatch, _payload, _command = discovered_audit
    base = dispatch["source_discovery"]["command"]
    command = shlex.join([*base, "--path", "missing directory", "--glob", "*.py"])
    result = bind_discovery(command, dispatch)
    assert result is not None
    query, _binding = result
    assert query.selected_paths == ()
    capture = source_snapshot(json.loads(Path(dispatch["source_discovery"]["capture_path"]).read_bytes()))
    assert SourceDiscovery(("tool.py",), (), ()).select(capture) == ("tool.py",)
    for invalid in ("../outside", "/outside", "tests/../src", "tests//src", "*.py"):
        with pytest.raises(ValueError, match="canonical repository-relative"):
            SourceDiscovery((invalid,), (), ()).select(capture)
