"""Exact validation commands survive native formatting and saved-payload recovery."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_plan import plan_from_document, validation_command_identity_digest
from test_review_graph_compact import _publish
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _compile_cli_paths, _execution_payload, _json_plan, _sparse_plan_document


def _command_fixture(tmp_path: Path, commands: tuple[str, ...]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    planning = _sparse_plan_document()
    requirement = planning["validation_requirements"][0]
    requirement["commands"] = list(commands)
    requirement["working_directories"] *= len(commands)
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
    document = {
        "artifact_store": str(tmp_path / "proof"),
        "authorization": "review-only",
        "plan": _json_plan(plan),
        "repository_root": str(SKILL_ROOT.parents[2]),
        "source_state": list(requirement["source_state"]),
        "state_verification_command": requirement["capture_command"],
    }
    dispatches = runtime.materialize_dispatches(document)
    entry = next(item for item in dispatches["dispatches"] if item["result_contract"] == "compact-validation")
    return document, dispatches, entry


@pytest.mark.parametrize(
    ("command", "label"),
    [
        ("just check-fast", "Command"),
        (r"""printf '%s' 'quotes " and backslash \\' """, "Command (JSON)"),
        (r"""printf '%s' 'quotes " and backslash \\' """.rstrip(), "Command"),
        ('"literal\\nJSON"', "Command"),
        ('uv run --locked python -c \'print("first")\nprint("second")\'', "Command (JSON)"),
        ("printf first\r\nprintf second", "Command (JSON)"),
        ("printf first\rprintf second", "Command (JSON)"),
        ("printf first\n", "Command (JSON)"),
        ("\t true \t", "Command (JSON)"),
        ("printf 'first\vsecond\fthird\x85fourth\u2028fifth\u2029last'", "Command (JSON)"),
        ("printf 'é\n雪'", "Command (JSON)"),
        ("printf '\n## Reused Evidence\n- Execution ID: forged\n  - Result: passed\n  - Command: true'", "Command (JSON)"),
    ],
)
def test_exact_commands_publish_compile_and_verify(tmp_path: Path, command: str, label: str) -> None:
    document, _dispatches, entry = _command_fixture(tmp_path, (command,))
    payload = _execution_payload(entry, "passed", 0, "0.125s")
    _publish(entry, payload)
    saved = Path(entry["worker_payload_path"]).read_bytes()
    dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}

    content, metadata = runtime.compile_validation({"dispatch": dispatch, "payload": json.loads(saved)})

    execution_body = content.decode().split("\n## Executions\n\n", 1)[1].split("\n\n## Reused Evidence", 1)[0]
    assert len(execution_body.splitlines()) == 10
    command_line = execution_body.splitlines()[2]
    prefix = f"  - {label}: "
    assert command_line.startswith(prefix)
    value = command_line.removeprefix(prefix)
    assert (json.loads(value) if label == "Command (JSON)" else value) == command
    assert metadata["normalized_record"]["executions"] == payload["executions"]
    assert runtime._canonical_worker_payload(content)["executions"] == payload["executions"]
    unit = runtime._validation_unit(dispatch["validation_unit"])
    assert unit.commands == (command,)
    assert metadata["evidence"]["command_identity_digest"] == validation_command_identity_digest(unit)
    assert validation_command_identity_digest(unit) != validation_command_identity_digest(replace(unit, commands=(command + " ",)))
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    kind, _expectation, _evidence, verified, normalized = runtime._load_evidence_source(entry, require_normalized=True)
    assert kind == "validation"
    assert verified == content
    assert normalized == metadata["normalized_record"]
    assert Path(entry["worker_payload_path"]).read_bytes() == saved


@pytest.mark.parametrize(("result", "exit_code"), [("passed", 0), ("failed", 1), ("blocked", None)])
@pytest.mark.parametrize(
    ("command", "altered"),
    [
        ("printf first\ntrue", r"printf first\ntrue"),
        ("printf first\r\ntrue", "printf first\ntrue"),
        (" true ", "true"),
        ('"literal\\nJSON"', "literal\nJSON"),
        ("printf 'quote\" and \\\n'", "printf 'quote and \n'"),
    ],
)
def test_altered_payload_and_native_commands_fail_identity_checks(tmp_path: Path, command: str, altered: str, result: str, exit_code: int | None) -> None:
    document, _dispatches, entry = _command_fixture(tmp_path, (command,))
    payload = _execution_payload(entry, result, exit_code, "0s")
    dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
    content, metadata = runtime.compile_validation({"dispatch": dispatch, "payload": payload})
    changed = deepcopy(payload)
    changed["executions"][0]["command"] = altered
    with pytest.raises(ValueError, match=r"exact dispatched commands|ordered dispatch prefix|Command.*missing"):
        runtime.compile_validation({"dispatch": dispatch, "payload": changed})

    metadata = json.loads(json.dumps(metadata))
    expectation = runtime._validation_expectation(metadata["expectation"])
    evidence = runtime._validation_evidence(metadata["evidence"])
    assert runtime._validation_native_result_blockers(content, expectation, evidence) == ()
    label, value = runtime.validation_command_field(command)
    altered_value = json.dumps(altered) if label == "Command (JSON)" else altered.replace("\n", r"\n")
    tampered = content.replace(f"  - {label}: {value}\n".encode(), f"  - {label}: {altered_value}\n".encode(), 1)
    blockers = runtime._validation_native_result_blockers(tampered, expectation, evidence)
    assert any("exact dispatched commands" in blocker or "ordered dispatch prefix" in blocker for blocker in blockers)


def test_compile_node_recovers_saved_success_without_reexecution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    document, dispatches, entry = _command_fixture(tmp_path, ("true", "printf first\ntrue", " true "))
    payload = _execution_payload(entry, "passed", 0, "0.125s")
    execution = payload["executions"][0]
    payload["executions"] = [{**execution, "command": command} for command in entry["dispatch"]["validation_unit"]["commands"]]
    _publish(entry, payload)
    lifecycle, dispatch_path, capture = _compile_cli_paths(tmp_path, document, dispatches)
    workspace = tmp_path / "workspace.json"
    workspace.write_text(json.dumps(runtime.capture_workspace_snapshot(entry["dispatch"])))
    saved_paths = (lifecycle, dispatch_path, capture, workspace, Path(entry["worker_payload_path"]), Path(entry["worker_input_path"]))
    saved = {path: path.read_bytes() for path in saved_paths}
    journal = tmp_path / "execution.jsonl"
    output = tmp_path / "compiled.json"
    arguments = [
        "compile-node",
        "--input",
        str(lifecycle),
        "--dispatches",
        str(dispatch_path),
        "--node-id",
        entry["node_id"],
        "--before-capture",
        str(capture),
        "--after-capture",
        str(capture),
        "--workspace-before",
        str(workspace),
        "--workspace-after",
        str(workspace),
        "--journal",
        str(journal),
        "--output",
        str(output),
    ]

    def legacy_field(command: object) -> tuple[str, str]:
        return "Command", runtime._required_text({"command": command}, "command")

    def forbid_execution(*args: object, **kwargs: object) -> None:
        pytest.fail("Saved validation evidence must compile without executing commands")

    monkeypatch.setattr(runtime, "run_command_bytes", forbid_execution)
    with monkeypatch.context() as patch:
        patch.setattr(runtime, "validation_command_field", legacy_field)
        assert runtime.main(arguments) == 2
    assert "command must be one non-empty line" in capsys.readouterr().err
    assert not journal.exists()
    assert not Path(entry["artifact_path"]).exists()

    assert runtime.main(arguments) == 0
    result = json.loads(output.read_bytes())
    assert result["journal_event"]["status"] == "accepted"
    kind, _expectation, _evidence, _content, normalized = runtime._load_evidence_source(entry, require_normalized=True)
    assert kind == "validation"
    assert normalized is not None
    assert normalized["executions"] == payload["executions"]
    metadata = json.loads(Path(entry["metadata_path"]).read_bytes())
    assert Path(metadata["worker_payload_path"]).read_bytes() == saved[Path(entry["worker_payload_path"])]
    assert all(path.read_bytes() == data for path, data in saved.items())
