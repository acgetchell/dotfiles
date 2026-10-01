"""Behavioral checks for shadow routing, attribution, and incomplete evidence."""

import copy
import io
import json
from email.message import Message
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


def test_multiple_skills_and_failure_never_change_execution(packet: dict[str, Any]) -> None:
    result = {"probabilities": dict.fromkeys(packet["request"]["questions"], 0.95)}
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
    report = experiment.compare(packet, {"probabilities": dict.fromkeys(packet["request"]["questions"], 0.0)})
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
    rows = experiment.threshold_sweep(packet, {"probabilities": probabilities})
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
