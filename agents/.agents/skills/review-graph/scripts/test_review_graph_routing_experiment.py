"""Behavioral checks for shadow routing, attribution, and incomplete evidence."""

import copy
import io
import json
import sys
from email.message import Message
from http.client import BadStatusLine
from pathlib import Path
from typing import Any, Self
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
import review_graph_routing_experiment as experiment
import review_graph_runtime as runtime
from review_graph_plan import DEFAULT_ROUTING_CATALOG, load_routing_catalog
from review_graph_usage import finish_request, measure_call, measurements, parse_json, read_json, start_request, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "routing_pilot.json"
EVALUATION_FIXTURE = Path(__file__).parent / "fixtures" / "routing_evaluation.json"


@pytest.fixture
def case() -> dict[str, Any]:
    return read_json(FIXTURE)["cases"][0]


@pytest.fixture
def packet(case: dict[str, Any]) -> dict[str, Any]:
    return experiment.prepare(case)


def test_every_leaf_is_asked_and_labels_do_not_leak(case: dict[str, Any], packet: dict[str, Any]) -> None:
    expected = {e.catalog_id for e in load_routing_catalog(DEFAULT_ROUTING_CATALOG) if e.target_kind == "leaf"}
    assert set(packet["request"]["questions"]) == expected
    altered = copy.deepcopy(case)
    altered["expected"] = {key: not value for key, value in case["expected"].items()}
    altered["baseline"]["decisions"] = {}
    assert experiment.prepare(altered)["request"] == packet["request"]
    assert experiment.prepare(altered)["packet_digest"] != packet["packet_digest"]


@pytest.mark.parametrize("evaluation_case", read_json(EVALUATION_FIXTURE)["cases"], ids=lambda case: case["id"])
def test_independently_labeled_source_fixtures_prepare_offline(evaluation_case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object) -> None:
        pytest.fail("fixture preparation must not construct an HTTP client")

    monkeypatch.setattr(experiment, "build_opener", forbidden)
    packet = experiment.prepare(evaluation_case)
    assert set(packet["expected"]) == set(packet["request"]["questions"])
    report = experiment.compare(packet, {"status": "not-run", "probabilities": {}})
    assert not report["selected_catalog_ids"]
    assert len(report["uncertain"]) == len(packet["catalog"])


def test_multiple_skills_and_failure_never_change_execution(packet: dict[str, Any]) -> None:
    result = {"status": "succeeded", "probabilities": dict.fromkeys(packet["request"]["questions"], 0.95)}
    report = experiment.compare(packet, result)
    assert all(row["jev"] == "applicable" for row in report["rows"])
    assert not report["execution_routing_changed"]
    assert not report["promotion_allowed"]
    failed = experiment.compare(packet, {"probabilities": {}})
    assert len(failed["uncertain"]) == len(packet["catalog"])
    assert failed["provisional_counts"]["unresolved_required"] == 2
    assert failed["provisional_counts"]["missed_required"] == 0


@pytest.mark.parametrize(("scope_complete", "file_complete"), [(False, True), (True, False)])
def test_incomplete_context_cannot_become_a_negative(case: dict[str, Any], scope_complete: bool, file_complete: bool) -> None:
    case["scope"]["complete"] = scope_complete
    case["scope"]["files"][0]["complete"] = file_complete
    packet = experiment.prepare(case)
    report = experiment.compare(packet, {"status": "succeeded", "probabilities": dict.fromkeys(packet["request"]["questions"], 0.0)})
    assert len(report["uncertain"]) == len(packet["catalog"])


@pytest.mark.parametrize("value", [True, "0.9", -0.01, 1.01, float("nan"), float("inf")])
def test_invalid_probabilities_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="probability"):
        experiment._validate_response({"model": experiment.MODEL, "answers": {"a": {"type": "noul", "noul": value}}}, {"a"})


def test_missing_or_extra_candidate_is_rejected() -> None:
    with pytest.raises(ValueError, match="every candidate"):
        experiment._validate_response({"model": experiment.MODEL, "answers": {}}, {"a"})


def test_unknown_usage_stays_unknown(tmp_path: Path) -> None:
    ledger = tmp_path / "usage.jsonl"
    unfinished = start_request(ledger, stage="proof", provider="codex", model=None, scope_digest="source")
    known = start_request(ledger, stage="proof", provider="codex", model=None, scope_digest="source")
    finish_request(ledger, known, status="failed", usage={"input_tokens": 123, "cost_usd": 0.2, "cost_basis": "estimated", "measurement_source": "fixture"})
    report = summarize([ledger])
    assert unfinished != known
    assert report["totals_are_partial"]
    group = report["groups"][0]
    assert group["attempts"] == 2
    assert group["failed"] == 1
    assert group["unfinished"] == 1
    assert group["input_tokens_known"] == 123
    assert group["unknown_input_attempts"] == 1
    assert group["estimated_cost_usd"] == 0.2
    assert group["unknown_cost_attempts"] == 1


@pytest.mark.parametrize("value", [True, -1, 1.5, "123"])
def test_token_counts_must_be_actual_counts(value: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        measurements({"input_tokens": value, "measurement_source": "fixture"})


class Response:
    def __init__(self, body: object) -> None:
        """Build a bounded mock HTTP body."""
        self.body = json.dumps(body).encode()
        self.status = 200

    def __enter__(self) -> Self:
        """Open the mock response."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close the mock response."""

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


def test_live_request_counts_usage_without_leaking_secret(packet: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "fixture-only-sensitive-value"  # noqa: S105 -- deliberately fake credential
    monkeypatch.setenv("TYPESAFE_API_KEY", secret)

    class Opener:
        def open(self, request: Any, timeout: int) -> Response:
            assert request.full_url == experiment.ENDPOINT
            assert request.get_header("Authorization") == f"Bearer {secret}"
            assert timeout == 60
            body = json.loads(request.data)
            assert body == packet["request"]
            assert "expected" not in body
            return Response(
                {
                    "model": experiment.MODEL,
                    "answers": {k: {"type": "noul", "noul": 0.9} for k in body["questions"]},
                    "usage": {"input_tokens": 1000, "output_tokens": 100},
                }
            )

    monkeypatch.setattr(experiment, "build_opener", lambda *_: Opener())
    ledger = tmp_path / "usage.jsonl"
    result = experiment.call_jev(packet, ledger)
    assert result["status"] == "succeeded"
    assert result["usage"]["cost_usd"] == pytest.approx(0.000042)
    assert result["usage"]["cost_basis"] == "estimated"
    assert secret not in ledger.read_text() + json.dumps(result)


@pytest.mark.parametrize("error", [HTTPError(experiment.ENDPOINT, 401, "secret", Message(), io.BytesIO(b"secret")), URLError("secret")])
def test_service_failure_retains_attempt_without_raw_error(packet: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-key")

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> None:
            raise error

    monkeypatch.setattr(experiment, "build_opener", lambda *_: Opener())
    ledger = tmp_path / "usage.jsonl"
    result = experiment.call_jev(packet, ledger)
    assert result["status"] == "failed"
    assert "secret" not in json.dumps(result) + ledger.read_text()
    report = summarize([ledger])
    assert report["groups"][0]["failed"] == 1
    assert report["groups"][0]["unknown_cost_attempts"] == 1


def test_dry_run_needs_no_key_and_preserves_artifacts(case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    report = experiment.run_case(case, tmp_path / "run", live=False)
    assert report["status"] == "not-run"
    assert (tmp_path / "run" / "packet.json").is_file()
    with pytest.raises(FileExistsError):
        experiment.run_case(case, tmp_path / "run", live=False)


def test_catalog_and_context_changes_change_identity(case: dict[str, Any]) -> None:
    original = experiment.prepare(case)
    case["scope"]["files"][0]["content"] += "\n# a changed source state\n"
    changed = experiment.prepare(case)
    assert changed["request_digest"] != original["request_digest"]
    assert changed["packet_digest"] != original["packet_digest"]


def test_baseline_plan_preserves_unknown_exclusions() -> None:
    baseline = experiment.baseline_from_plan(
        {
            "routing_catalog_closed": True,
            "routing_decisions": [{"catalog_id": "a", "disposition": "selected"}, {"catalog_id": "b", "disposition": "user-excluded"}],
        },
        {"a", "b", "c"},
    )
    assert baseline["decisions"] == {"a": True, "b": None}


def test_oversized_or_unsafe_scope_is_rejected(case: dict[str, Any]) -> None:
    case["scope"]["files"][0]["path"] = "../private"
    with pytest.raises(ValueError, match="relative"):
        experiment.prepare(case)
    case["scope"]["files"][0]["path"] = "src.py"
    case["scope"]["files"][0]["content"] = "x" * 40_000
    with pytest.raises(ValueError, match="size limit"):
        experiment.prepare(case)


@pytest.mark.parametrize("content", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'])
def test_strict_json_rejects_duplicate_or_nonfinite_values(content: str) -> None:
    with pytest.raises(ValueError, match=r"duplicate|Out of range"):
        parse_json(content)


def test_duplicate_finishes_cannot_double_count(tmp_path: Path) -> None:
    ledger = tmp_path / "usage.jsonl"
    request_id = start_request(ledger, stage="routing", provider="test", model=None, scope_digest="source")
    for _ in range(2):
        finish_request(ledger, request_id, status="succeeded", usage={"measurement_source": "fixture"})
    with pytest.raises(ValueError, match="duplicate"):
        summarize([ledger])


def test_runtime_accounting_preserves_failure_and_separates_inference(tmp_path: Path) -> None:
    ledger = tmp_path / "usage.jsonl"
    assert measure_call(lambda: 2, ledger, stage="runtime:finalize-proof", scope_digest="source") == 2
    group = summarize([ledger])["groups"][0]
    assert group["failed"] == 1
    assert group["provider"] == "deterministic-runtime"
    assert group["measured_cost_usd"] == 0
    assert group["unknown_elapsed_attempts"] == 0


def test_dry_run_does_not_charge_an_imported_baseline_again(case: dict[str, Any], tmp_path: Path) -> None:
    case["baseline"]["usage"] = {"cost_usd": 1.0, "cost_basis": "measured", "measurement_source": "fixture"}
    summary = experiment.run_case(case, tmp_path / "run", live=False)
    assert summary["accounting"]["groups"] == []
    assert summary["baseline_measurements"]["cost_usd"] == 1.0


def test_instrumented_runtime_keeps_routing_output_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"captured_paths": ["src/lib.py"], "consulted_routers": ["review-graph", "python-review-orchestrator"]}))
    original = tmp_path / "original.json"
    measured = tmp_path / "measured.json"
    ledger = tmp_path / "usage.jsonl"
    monkeypatch.delenv("REVIEW_GRAPH_USAGE_LEDGER", raising=False)
    assert runtime.main(["routing-projection", "--input", str(source), "--output", str(original)]) == 0
    monkeypatch.setenv("REVIEW_GRAPH_USAGE_LEDGER", str(ledger))
    assert runtime.main(["routing-projection", "--input", str(source), "--output", str(measured)]) == 0
    assert original.read_bytes() == measured.read_bytes()
    group = summarize([ledger])["groups"][0]
    assert group["stage"] == "runtime:routing-projection"
    assert group["succeeded"] == 1


def test_uncertainty_is_not_hidden_from_recall(packet: dict[str, Any]) -> None:
    report = experiment.compare(packet, {"probabilities": {}})
    quality = report["quality_by_method"]["jev"]
    assert quality["recall_lower_bound_on_labeled_pairs"] == 0
    assert quality["unresolved_positive"] == 2
    assert quality["precision_on_labeled_pairs"] is None


def test_invalid_answers_retain_billable_usage(packet: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-key")

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> Response:
            return Response({"model": experiment.MODEL, "answers": {}, "usage": {"input_tokens": 1000}})

    monkeypatch.setattr(experiment, "build_opener", lambda *_: Opener())
    result = experiment.call_jev(packet, tmp_path / "usage.jsonl")
    assert result["status"] == "failed"
    assert result["usage"]["input_tokens"] == 1000
    assert result["usage"]["cost_usd"] == pytest.approx(0.000042)


def test_endpoint_redirect_is_not_followed() -> None:
    request = Request("https://api.typesafe.ai/v1/systemone", headers={"Authorization": "Bearer fixture"})
    assert experiment.NoRedirect().redirect_request(request, None, 302, "redirect", Message(), "https://other.example/") is None


def test_threshold_sweep_is_monotone_and_includes_half(packet: dict[str, Any]) -> None:
    probabilities = dict.fromkeys(packet["request"]["questions"], 0.0)
    probabilities.update({"python.scientific": 0.5, "python.parse": 0.499})
    rows = experiment.threshold_sweep(packet, {"status": "succeeded", "probabilities": probabilities})
    assert [row["selected_count"] for row in rows] == sorted([row["selected_count"] for row in rows], reverse=True)
    half = next(row for row in rows if row["include_at_or_above"] == 0.5)
    assert half["selected_count"] == 1
    assert half["quality"]["false_negative"] == 1


def test_replay_detects_modified_packet_and_makes_no_network_request(case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "run"
    experiment.run_case(case, directory, live=False)

    def forbidden(*_args: object) -> None:
        pytest.fail("replay must not construct an HTTP client")

    monkeypatch.setattr(experiment, "build_opener", forbidden)
    assert experiment.replay_case(directory)["new_api_requests"] == 0
    packet = read_json(directory / "packet.json")
    packet["request"]["state"]["complete"] = False
    (directory / "packet.json").write_text(json.dumps(packet))
    with pytest.raises(ValueError, match="digest mismatch"):
        experiment.replay_case(directory)


def test_primary_cutoff_reports_selected_ids_and_disagreements(packet: dict[str, Any]) -> None:
    probabilities = dict.fromkeys(packet["request"]["questions"], 0.0)
    probabilities.update({"python.scientific": 0.5, "python.parse": 0.499, "python.cli": 0.6})
    report = experiment.compare(packet, {"status": "succeeded", "probabilities": probabilities})
    assert set(report["selected_catalog_ids"]) == {"python.scientific", "python.cli"}
    assert set(report["disagreements"]) == {"python.parse", "python.cli"}
    row = next(row for row in report["rows"] if row["catalog_id"] == "python.scientific")
    assert row["selected"] is True
    assert row["probability_band"] == "ambiguous"
    assert report["thresholds"]["calibrated"] is False


def test_borderline_assessment_is_explicit_bound_and_advisory(packet: dict[str, Any]) -> None:
    probabilities = dict.fromkeys(packet["request"]["questions"], 0.0)
    probabilities.update({"python.scientific": 0.7, "python.parse": 0.5, "python.cli": 0.699, "repo.tooling": 0.499})
    result = {"status": "succeeded", "probabilities": probabilities, "request_digest": packet["request_digest"], "response_model": experiment.MODEL}
    result["result_digest"] = experiment.digest(result)
    original = copy.deepcopy(packet)
    pending = experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5)
    triage = pending["coordinator_assessment"]
    assert pending["selected_catalog_ids"] == ["python.scientific"]
    assert triage["borderline_catalog_ids"] == ["python.cli", "python.parse"]
    assert triage["pending_catalog_ids"] == triage["borderline_catalog_ids"]
    assert triage["quality"]["unresolved_positive"] == 1
    assert triage["quality"]["false_negative"] == 0
    assessment: dict[str, Any] = {
        **triage["binding"],
        "decisions": {"python.parse": True, "python.cli": False},
        "reasons": {"python.parse": "Input values become a validated domain value.", "python.cli": "No application CLI contract is owned."},
    }
    accepted = experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5, assessment=assessment)
    assert set(accepted["coordinator_assessment"]["selected_catalog_ids"]) == {"python.scientific", "python.parse"}
    assert accepted["coordinator_assessment"]["pending_catalog_ids"] == []
    assert not accepted["execution_routing_changed"]
    assert not accepted["promotion_allowed"]
    assert packet == original
    for key in triage["binding"]:
        stale = {**assessment, key: "wrong-binding"}
        with pytest.raises(ValueError, match="stale"):
            experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5, assessment=stale)
    assessment["decisions"] = {"python.parse": None, "python.cli": False}
    unresolved = experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5, assessment=assessment)
    assert unresolved["coordinator_assessment"]["pending_catalog_ids"] == ["python.parse"]
    assert unresolved["coordinator_assessment"]["quality"]["unresolved_positive"] == 1
    result["probabilities"]["python.parse"] = 0.6
    with pytest.raises(ValueError, match="stale"):
        experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5, assessment=assessment)


@pytest.mark.parametrize("floor", [-0.1, 0.7, 0.8, float("nan"), float("inf")])
def test_invalid_coordinator_band_rejects_before_network_or_artifacts(case: dict[str, Any], tmp_path: Path, floor: float) -> None:
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="policy"):
        experiment.run_case(case, output, live=True, policy={"inclusion_threshold": 0.7, "coordinator_floor": floor})
    assert not output.exists()


@pytest.mark.parametrize("kind", ["missing", "extra", "invalid-decision", "missing-reason", "empty-reason"])
def test_coordinator_cannot_silently_omit_or_expand_assessment(packet: dict[str, Any], kind: str) -> None:
    result = {
        "status": "succeeded",
        "probabilities": dict.fromkeys(packet["request"]["questions"], 0.0),
        "request_digest": packet["request_digest"],
        "response_model": experiment.MODEL,
    }
    result["probabilities"]["python.parse"] = 0.6
    result["result_digest"] = experiment.digest(result)
    binding = experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5)["coordinator_assessment"]["binding"]
    assessment: dict[str, Any] = {**binding, "decisions": {"python.parse": True}, "reasons": {"python.parse": "Boundary parser is owned."}}
    if kind == "missing":
        assessment["decisions"].clear()
    elif kind == "extra":
        assessment["decisions"]["python.cli"] = True
    elif kind == "invalid-decision":
        assessment["decisions"] = {"python.parse": "yes"}
    elif kind == "missing-reason":
        assessment["reasons"].clear()
    else:
        assessment["reasons"]["python.parse"] = " "
    with pytest.raises(ValueError, match=r"coordinator|decisions"):
        experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5, assessment=assessment)


def test_cli_replays_bound_coordinator_assessment_without_network(packet: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved = tmp_path / "saved"
    saved.mkdir()
    experiment.write_json(saved / "packet.json", packet)
    probabilities = dict.fromkeys(packet["request"]["questions"], 0.0)
    probabilities.update({"python.scientific": 0.7, "python.parse": 0.56})
    result = {"status": "succeeded", "probabilities": probabilities, "request_digest": packet["request_digest"], "response_model": experiment.MODEL}
    result["result_digest"] = experiment.digest(result)
    experiment.write_json(saved / "result.json", result)
    assessment_path = tmp_path / "assessment.json"
    experiment.write_json(
        assessment_path,
        {
            "packet_digest": packet["packet_digest"],
            "result_digest": result["result_digest"],
            "inclusion_threshold": 0.7,
            "coordinator_floor": 0.5,
            "decisions": {"python.parse": True},
            "reasons": {"python.parse": "The owned input parser needs a boundary review."},
        },
    )

    def forbidden(*_args: object) -> None:
        pytest.fail("replaying an assessment must not construct an HTTP client")

    monkeypatch.setattr(experiment, "build_opener", forbidden)
    output = tmp_path / "replayed"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "routing-experiment",
            "--replay-case",
            str(saved),
            "--output-dir",
            str(output),
            "--inclusion-threshold",
            "0.7",
            "--coordinator-floor",
            "0.5",
            "--coordinator-assessment",
            str(assessment_path),
        ],
    )
    assert experiment.main() == 0
    report = read_json(output / "comparison.json")
    assert report["new_api_requests"] == 0
    assert report["selected_catalog_ids"] == ["python.scientific"]
    assert set(report["coordinator_assessment"]["selected_catalog_ids"]) == {"python.scientific", "python.parse"}
    assert report["coordinator_assessment"]["pending_catalog_ids"] == []
    assert not (output / "usage.jsonl").exists()


@pytest.mark.parametrize("failure", ["failed", "cancelled", "not-run", "partial", "stale", "model"])
def test_unusable_evidence_never_supplies_selections_or_sweep_negatives(packet: dict[str, Any], failure: str) -> None:
    result = {"status": "succeeded", "probabilities": dict.fromkeys(packet["request"]["questions"], 0.99)}
    if failure == "partial":
        result["probabilities"].pop(next(iter(result["probabilities"])))
    elif failure == "stale":
        result["request_digest"] = "changed-source-request"
    elif failure == "model":
        result["response_model"] = "jev-0.0.0"
    else:
        result["status"] = failure
    original = copy.deepcopy(packet)
    report = experiment.compare(packet, result, inclusion_threshold=0.7, coordinator_floor=0.5)
    assert packet == original
    assert not report["selected_catalog_ids"]
    assert not report["disagreements"]
    assert len(report["uncertain"]) == len(packet["catalog"])
    assert all(row["unknown_count"] == len(packet["catalog"]) for row in report["inclusion_threshold_sweep"])
    assert len(report["coordinator_assessment"]["unknown_catalog_ids"]) == len(packet["catalog"])
    assert report["coordinator_assessment"]["selected_catalog_ids"] == []


def test_no_match_and_unresolved_ownership_labels_remain_distinct(packet: dict[str, Any]) -> None:
    packet["expected"] = {"python.parse": None, "python.cli": False}
    report = experiment.compare(packet, {"status": "succeeded", "probabilities": dict.fromkeys(packet["request"]["questions"], 0.0)})
    assert report["selected_catalog_ids"] == []
    assert report["quality_by_method"]["jev"]["unresolved_labels"] == 1
    assert report["quality_by_method"]["jev"]["true_negative"] == 1


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TimeoutError("secret-response"), "timeout"),
        (URLError(TimeoutError("secret-response")), "timeout"),
        (BadStatusLine("secret-response"), "protocol-error"),
        (HTTPError(experiment.ENDPOINT, 429, "secret-response", Message(), io.BytesIO(b"secret-response")), "rate-limited"),
    ],
)
def test_explicit_failure_reasons_remain_redacted(
    packet: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-key")

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> None:
            raise error

    monkeypatch.setattr(experiment, "build_opener", lambda *_: Opener())
    result = experiment.call_jev(packet, tmp_path / "usage.jsonl")
    assert result["error"] == reason
    assert not experiment.compare(packet, result)["selected_catalog_ids"]
    assert "secret-response" not in json.dumps(result) + (tmp_path / "usage.jsonl").read_text()


@pytest.mark.parametrize(
    "limit", [{"max_requests": 1}, {"max_input_tokens": 127_999}, {"max_cost_usd": 0.005}, {"max_retries": -1}, {"max_cost_usd": float("nan")}]
)
def test_budget_reserves_all_attempts_including_unknown_failures(limit: dict[str, Any]) -> None:
    policy: dict[str, Any] = {"cases": 2, "max_requests": 2, "max_retries": 0, "max_input_tokens": 128_000, "max_cost_usd": 1.0}
    with pytest.raises(ValueError, match=r"budget|limit|retr"):
        experiment.budget_manifest(**(policy | limit))
    budget = experiment.budget_manifest(**policy)
    assert budget["reserved_requests"] == 2
    assert budget["reserved_cost_usd"] == pytest.approx(0.005376)


def test_retry_is_bounded_and_each_attempt_is_retained(case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-key")
    calls = []

    class Opener:
        def open(self, *_args: object, **_kwargs: object) -> None:
            calls.append(1)
            raise TimeoutError

    monkeypatch.setattr(experiment, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(experiment.time, "sleep", lambda _: None)
    output = tmp_path / "retry"
    experiment.run_case(case, output, live=True, policy={"max_retries": 1})
    assert len(calls) == 2
    assert len(list(output.glob("attempt-*.json"))) == 2
    assert summarize([output / "usage.jsonl"])["groups"][0]["unknown_cost_attempts"] == 2
    assert read_json(output / "result.json")["retries"] == 1


def test_cli_budget_rejection_precedes_all_network_and_output_creation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object) -> None:
        pytest.fail("budget rejection must precede network access")

    monkeypatch.setattr(experiment, "build_opener", forbidden)
    output = tmp_path / "uncreated"
    monkeypatch.setattr(experiment.sys, "argv", ["experiment", "--live", "--max-requests", "0", "--output-dir", str(output)])
    assert experiment.main() == 2
    assert not output.exists()


def test_retry_success_does_not_hide_unknown_earlier_cost(case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-key")
    case["baseline"]["usage"] = {"cost_usd": 0.1, "cost_basis": "measured", "measurement_source": "fixture"}
    calls = []

    class Opener:
        def open(self, request: Any, **_kwargs: object) -> Response:
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError
            body = json.loads(request.data)
            return Response(
                {"model": experiment.MODEL, "answers": {k: {"type": "noul", "noul": 0.9} for k in body["questions"]}, "usage": {"input_tokens": 1000}}
            )

    monkeypatch.setattr(experiment, "build_opener", lambda *_: Opener())
    monkeypatch.setattr(experiment.time, "sleep", lambda _: None)
    output = tmp_path / "retry-success"
    experiment.run_case(case, output, live=True, policy={"max_retries": 1})
    report = read_json(output / "comparison.json")
    assert report["accounting"]["groups"][0]["unknown_cost_attempts"] == 1
    assert not report["cost_comparison_complete"]


def test_failed_shadow_run_preserves_the_normal_plan_and_required_coverage(case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = {
        "routing_catalog_closed": True,
        "routing_decisions": [{"catalog_id": "python.scientific", "disposition": "selected"}],
        "required_node_ids": ["scientific", "independent", "validation", "synthesis"],
        "routing_overrides": [],
    }
    original = copy.deepcopy(plan)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    summary = experiment.run_case(case, tmp_path / "failure", live=True, plan=plan)
    assert summary["status"] == "failed"
    assert plan == original
    report = read_json(tmp_path / "failure" / "comparison.json")
    assert report["baseline_selected_catalog_ids"] == ["python.scientific"]
    assert not report["execution_routing_changed"]
    assert not report["promotion_allowed"]
