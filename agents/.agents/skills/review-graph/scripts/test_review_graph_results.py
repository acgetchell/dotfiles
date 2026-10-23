"""Malformed or incomplete review output cannot become successful evidence."""

import io
import json
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_continuation import NextReadyAction
from review_graph_integrity import digest_json
from review_graph_lifecycle import lifecycle_from_document
from review_graph_plan import graph_plan_digest, graph_plan_digest_matches
from review_graph_results import EvaluationBoundaryError, EvaluationRejection, RecoveryKind, RejectionKind, parse_json_object
from review_graph_schema import SchemaValidationError
from test_review_graph_runtime import _compact_audit_payload, _compile_cli_paths, _sparse_plan, _worker_input_fixture


@pytest.mark.parametrize(
    "content",
    [
        '{"status":"passed","status":"blocked"}',
        '{"nested":{"x":1,"x":2}}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":1e999}',
        '{"x":[[1e999]]}',
        "[]",
        "null",
        '{"x":',
        b'{"x":"\xff"}',
    ],
)
def test_json_rejects_ambiguous_or_nonfinite_input(content: str | bytes) -> None:
    with pytest.raises(EvaluationBoundaryError) as failure:
        parse_json_object(content)
    decision = EvaluationRejection.from_exception(failure.value)
    assert decision.kind is RejectionKind.MALFORMED_INPUT
    assert decision.as_dict()["recovery"]["kind"] is RecoveryKind.CORRECT_INPUT
    assert decision.as_dict()["recovery"]["automatic_retry"] is False


def test_json_preserves_valid_deeply_nested_input() -> None:
    # The supported Python decoder accepts this valid JSON iteratively; nesting
    # alone is not malformed transport or a reason to discard its evidence.
    nested = parse_json_object('{"x":' + "[" * 2000 + "0" + "]" * 2000 + "}")["x"]
    for _ in range(2000):
        assert isinstance(nested, list)
        assert len(nested) == 1
        nested = nested[0]
    assert nested == 0


def test_nonfinite_diagnostic_identifies_its_field() -> None:
    with pytest.raises(EvaluationBoundaryError, match="elapsed"):
        parse_json_object('{"executions":[{"elapsed":NaN}]}')


@pytest.mark.parametrize(
    ("mode", "contract"),
    [("audit", "compact-review"), ("synthesis", "compact-review"), ("independent-review", "compact-independent-review"), ("validation", "compact-validation")],
)
def test_every_worker_mode_rejects_missing_evidence_fields_before_semantic_use(mode: str, contract: str) -> None:
    with pytest.raises(SchemaValidationError) as failure:
        runtime._validate_worker_payload_bytes({"mode": mode, "result_contract": contract}, b"{}")
    decision = EvaluationRejection.from_exception(failure.value)
    assert decision.kind is RejectionKind.MISSING_INPUT
    assert decision.as_dict()["recovery"]["kind"] is RecoveryKind.SUPPLY_INPUT
    assert decision.as_dict()["accepted"] is False


@pytest.mark.parametrize("kind", list(RejectionKind))
def test_rejection_transport_round_trip_preserves_typed_policy(kind: RejectionKind) -> None:
    rejection = EvaluationRejection(kind)
    transported = parse_json_object(json.dumps(rejection.as_dict()))
    assert EvaluationRejection.from_document(transported) == rejection
    assert transported["recovery"]["automatic_retry"] is False


@pytest.mark.parametrize("change", ["missing", "unknown-kind", "success", "wrong-action", "automatic-retry", "extra"])
def test_rejection_parser_refuses_incomplete_or_contradictory_outcomes(change: str) -> None:
    raw: dict[str, Any] = json.loads(json.dumps(EvaluationRejection(RejectionKind.MISSING_INPUT).as_dict()))
    if change == "missing":
        del raw["recovery"]
    elif change == "unknown-kind":
        raw["kind"] = "probably-fine"
    elif change == "success":
        raw["accepted"] = True
    elif change == "wrong-action":
        raw["recovery"]["kind"] = "recapture-source"
    elif change == "automatic-retry":
        raw["recovery"]["automatic_retry"] = True
    else:
        raw["evidence_id"] = "invented-success"
    with pytest.raises(SchemaValidationError):
        EvaluationRejection.from_document(raw)


def test_unknown_failure_is_not_classified_from_message_text() -> None:
    decision = EvaluationRejection.from_exception(ValueError("missing evidence; retry now"))
    assert decision.kind is RejectionKind.UNCLASSIFIED
    assert decision.as_dict()["recovery"]["kind"] is RecoveryKind.INSPECT


def test_next_action_parser_detaches_command_from_raw_transport() -> None:
    original = NextReadyAction(("python", "runtime.py", "next-ready"))
    raw = json.loads(json.dumps(asdict(original)))
    parsed = NextReadyAction.from_document(raw)
    raw["command"].append("--invented")
    assert parsed == original
    del raw["operation"]
    with pytest.raises(SchemaValidationError):
        NextReadyAction.from_document(raw)


def test_interleaved_history_is_detached_and_missing_legacy_field_preserves_plan_identity() -> None:
    original = _sparse_plan()
    plan = replace(original, review_lifecycle=replace(original.review_lifecycle, repairs_completed=1))
    legacy = asdict(plan)
    for key in (
        "independent_review_after_audits",
        "commit_handoffs",
        "pre_review_validation_nodes",
        "validation_recoveries",
        "audit_replacements",
        "audit_delta_reviews",
        "validation_exclusions",
        "validation_requirement_bindings",
        "audit_reuse_transitions",
        "reuse_source_snapshots",
    ):
        legacy.pop(key)
    legacy["review_lifecycle"].pop("interleaved_repair_epochs")
    assert graph_plan_digest(plan) == digest_json(legacy)
    assert graph_plan_digest_matches(plan, digest_json(legacy))
    raw = {**legacy["review_lifecycle"], "interleaved_repair_epochs": [1]}
    parsed = lifecycle_from_document(raw)
    raw["interleaved_repair_epochs"].clear()
    assert parsed.interleaved_repair_epochs == (1,)
    limited = replace(plan, review_lifecycle=parsed)
    assert graph_plan_digest(limited) != graph_plan_digest(plan)
    assert not graph_plan_digest_matches(limited, digest_json(legacy))


@pytest.mark.parametrize("epochs", [[True], [0], [2], [1, 1], "1", ["1"]])
def test_interleaved_history_rejects_uncompleted_or_invalid_epochs(epochs: Any) -> None:
    raw = {**asdict(_sparse_plan().review_lifecycle), "repairs_completed": 1, "interleaved_repair_epochs": epochs}
    with pytest.raises(ValueError, match="interleaved repair"):
        lifecycle_from_document(raw)


def test_publication_rejection_preserves_previous_payload_and_reports_typed_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _document, entries = _worker_input_fixture(tmp_path)
    entry = next(item for item in entries["dispatches"] if item["dispatch"].get("mode") == "audit")
    target = Path(entry["worker_payload_path"])
    payload = _compact_audit_payload(entry)
    content = json.dumps(payload).encode()
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, content)
    invalid = deepcopy(payload)
    del invalid["files_inspected"]
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(invalid).encode()), encoding="utf-8"))
    assert runtime.main(["publish-worker-payload", "--input", entry["worker_payload_contract_path"]]) == 2
    diagnostic = capsys.readouterr()
    assert diagnostic.out == ""
    rejection = EvaluationRejection.from_document(json.loads(diagnostic.err)["rejection"])
    assert rejection.kind is RejectionKind.MISSING_INPUT
    assert target.read_bytes() == content


def test_cli_rejects_duplicate_request_fields_without_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    request, output = tmp_path / "request.json", tmp_path / "output.json"
    request.write_text('{"plan":{},"plan":{"pretend":"valid"}}')
    assert runtime.main(["advance-after-mutation", "--input", str(request), "--output", str(output)]) == 2
    diagnostic = capsys.readouterr()
    assert diagnostic.out == ""
    rejection = EvaluationRejection.from_document(json.loads(diagnostic.err)["rejection"])
    assert rejection.kind is RejectionKind.MALFORMED_INPUT
    assert not output.exists()


@pytest.mark.parametrize("invalid", ["duplicate-status", "nonfinite", "missing-field"])
def test_compiler_rejects_invalid_saved_payload_before_sealing_or_acceptance(tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid: str) -> None:
    document, dispatches = _worker_input_fixture(tmp_path)
    entry = next(item for item in dispatches["dispatches"] if item["result_contract"] == "compact-review")
    payload = _compact_audit_payload(entry)
    if invalid == "missing-field":
        del payload["files_inspected"]
    content = json.dumps(payload)
    if invalid == "duplicate-status":
        content = '{"status":"blocked",' + content[1:]
    elif invalid == "nonfinite":
        content = '{"unknown":1e999,' + content[1:]
    Path(entry["worker_payload_path"]).write_text(content)
    lifecycle, dispatch, capture = _compile_cli_paths(tmp_path, document, dispatches)
    journal = tmp_path / "execution.jsonl"
    assert (
        runtime.main(
            [
                "compile-node",
                "--input",
                str(lifecycle),
                "--dispatches",
                str(dispatch),
                "--node-id",
                entry["node_id"],
                "--before-capture",
                str(capture),
                "--after-capture",
                str(capture),
                "--journal",
                str(journal),
                "--output",
                str(tmp_path / "compiled.json"),
            ]
        )
        == 2
    )
    rejection = EvaluationRejection.from_document(json.loads(capsys.readouterr().err)["rejection"])
    assert rejection.kind is (RejectionKind.MISSING_INPUT if invalid == "missing-field" else RejectionKind.MALFORMED_INPUT)
    assert not Path(entry["artifact_path"]).exists()
    assert not Path(entry["metadata_path"]).exists()
    assert not journal.exists()
    assert not tuple(Path(entry["worker_payload_path"]).parent.glob("*.sealed.json"))
