"""Usage CLI inputs are discoverable, sanitized, and retain unknown measurements."""

import json
from pathlib import Path

import pytest
import review_graph_usage as usage


def test_report_reads_unicode_separators_inside_a_json_string(tmp_path: Path) -> None:
    ledger = tmp_path / "usage.jsonl"
    stage = "plan\u2028review"
    usage.start_request(ledger, stage=stage, provider="local", model=None, scope_digest="fixture")
    ledger.write_text(json.dumps(json.loads(ledger.read_bytes()), ensure_ascii=False) + "\n", encoding="utf-8")
    assert usage.summarize([ledger])["groups"][0]["stage"] == stage


@pytest.mark.parametrize("field", ["cost_usd", "elapsed_seconds"])
def test_report_rejects_unrepresentable_totals(tmp_path: Path, capsys: pytest.CaptureFixture[str], field: str) -> None:
    ledger = tmp_path / "usage.jsonl"
    for _ in range(2):
        request_id = usage.start_request(ledger, stage="review", provider="local", model=None, scope_digest="fixture")
        usage.finish_request(
            ledger,
            request_id,
            status="succeeded",
            usage={field: 1e308, "measurement_source": "fixture", "cost_basis": "measured" if field == "cost_usd" else "unavailable"},
        )
    assert usage.main(["report", str(ledger)]) == 2
    captured = capsys.readouterr()
    assert "total" in captured.err
    assert not captured.out


@pytest.mark.parametrize(("field", "value"), [("id", 1), ("stage", False), ("provider", 1), ("model", 0)])
def test_report_rejects_mistyped_restored_identity(tmp_path: Path, capsys: pytest.CaptureFixture[str], field: str, value: object) -> None:
    ledger = tmp_path / "usage.jsonl"
    usage.start_request(ledger, stage="review", provider="local", model=None, scope_digest="fixture")
    event = json.loads(ledger.read_bytes())
    event[field] = value
    ledger.write_text(json.dumps(event) + "\n", encoding="utf-8")
    assert usage.main(["report", str(ledger)]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "invalid" in captured.err


def _finish_args(ledger: Path, usage_path: Path) -> list[str]:
    """Construct the command that records a successful fixture attempt with usage from a file."""
    return ["finish", "--ledger", str(ledger), "--id", "fixture-attempt", "--status", "succeeded", "--usage", str(usage_path)]


def test_help_example_can_be_used_without_reading_the_implementation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        usage.main(["finish", "--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--usage JSON_FILE" in help_text
    example_start = help_text.index("\n{\n") + 1
    example = json.loads(help_text[example_start : help_text.index("\n}", example_start) + 2])
    ledger = tmp_path / "usage.jsonl"
    request_id = usage.start_request(ledger, stage="specialist:fixture", provider="fixture", model=None, scope_digest="fixture")
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(json.dumps(example))
    args = _finish_args(ledger, usage_path)
    args[args.index("--id") + 1] = request_id
    assert usage.main(args) == 0
    event = json.loads(ledger.read_text().splitlines()[-1])
    assert all(event[field] is None for field in ("input_tokens", "output_tokens", "cached_input_tokens", "elapsed_seconds", "cost_usd"))
    group = usage.summarize([ledger])["groups"][0]
    assert group["unknown_input_attempts"] == group["unknown_output_attempts"] == group["unknown_cost_attempts"] == group["unknown_elapsed_attempts"] == 1


@pytest.mark.parametrize(
    ("content", "diagnostic"),
    [
        ('{"private-value":', "invalid JSON at line"),
        ('{"private-value": 1, "private-value": 2}', "duplicate JSON field"),
        ('{"private-value": NaN}', "non-finite numbers"),
        ('{"private-value": 1e999}', "non-finite numbers"),
        ('["private-value"]', "JSON input must be an object"),
        (json.dumps({"input_tokens": "private-value"}), "input_tokens must be a nonnegative integer or null"),
        (json.dumps({"output_tokens": True}), "output_tokens must be a nonnegative integer or null"),
        (json.dumps({"cached_input_tokens": -1}), "cached_input_tokens must be a nonnegative integer or null"),
        (json.dumps({"elapsed_seconds": -1}), "elapsed_seconds must be a nonnegative finite number or null"),
        (json.dumps({"cost_usd": "private-value"}), "cost_usd must be a nonnegative finite number or null"),
        (json.dumps({"cost_usd": 10**400}), "cost_usd must be a nonnegative finite number or null"),
        (json.dumps({"cost_basis": "private-value"}), "cost_basis must be measured, estimated, or unavailable"),
        (json.dumps({"cost_basis": []}), "cost_basis must be measured, estimated, or unavailable"),
        (json.dumps({"cost_usd": 1}), "cost_basis must be measured or estimated when cost_usd is supplied"),
        (json.dumps({"cost_basis": "measured"}), "cost_basis must be unavailable when cost_usd is null"),
        ("{}", "measurement_source is required and must be a nonempty string"),
        (json.dumps({"measurement_source": " "}), "measurement_source is required and must be a nonempty string"),
        (json.dumps({"measurement_source": ["private-value"]}), "measurement_source is required and must be a nonempty string"),
    ],
)
def test_invalid_usage_identifies_failure_without_echoing_values(tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str, diagnostic: str) -> None:
    ledger = tmp_path / "usage.jsonl"
    ledger.write_text("existing event\n")
    usage_path = tmp_path / "private-filename.json"
    usage_path.write_text(content)
    assert usage.main(_finish_args(ledger, usage_path)) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "--usage:" in output.err
    assert diagnostic in output.err
    assert "private-value" not in output.err
    assert "private-filename" not in output.err
    assert ledger.read_text() == "existing event\n"


@pytest.fixture
def deeply_nested_usage(tmp_path: Path) -> Path:
    # Decoder stack limits vary by Python build; keep the input below the four MiB cap.
    """Write a deeply nested JSON value directly to disk for testing the ledger's input limits."""
    depth = 1_000_000
    path = tmp_path / "private-filename.json"
    path.write_text('{"private-value":' + "[" * depth + '"private-value"' + "]" * depth + "}", encoding="utf-8")
    return path


def test_deep_ledger_returns_a_private_diagnostic(deeply_nested_usage: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert usage.main(["report", str(deeply_nested_usage)]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "review_graph_usage:" in captured.err
    assert "private-" not in captured.err


def test_deep_usage_json_reports_safe_diagnostic_without_traceback(tmp_path: Path, deeply_nested_usage: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "usage.jsonl"
    ledger.write_text("existing event\n", encoding="utf-8")
    assert usage.main(_finish_args(ledger, deeply_nested_usage)) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "--usage: invalid JSON: nesting exceeds parser limit" in output.err
    assert all(value not in output.err for value in ("Traceback", "private-value", "private-filename"))
    assert ledger.read_text(encoding="utf-8") == "existing event\n"


@pytest.mark.parametrize("kind", ["missing", "directory", "inline", "encoding", "oversized"])
def test_usage_file_failures_are_distinct_and_do_not_create_a_ledger(tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str) -> None:
    ledger = tmp_path / "usage.jsonl"
    path = tmp_path / "private-filename.json"
    if kind == "directory":
        path.mkdir()
    elif kind == "inline":
        path = Path('{"measurement_source":"private-value"}')
    elif kind == "encoding":
        path.write_bytes(b"\xff")
    elif kind == "oversized":
        path.write_bytes(b" " * 4_194_305)
    assert usage.main(_finish_args(ledger, path)) == 2
    diagnostic = capsys.readouterr().err
    expected = "UTF-8 encoding" if kind == "encoding" else "exceeds four MiB" if kind == "oversized" else "cannot read JSON file"
    assert expected in diagnostic
    assert "private-value" not in diagnostic
    assert "private-filename" not in diagnostic
    assert not ledger.exists()


@pytest.mark.parametrize("basis", ["measured", "estimated"])
def test_supplied_cost_does_not_infer_missing_tokens(tmp_path: Path, basis: str) -> None:
    path = tmp_path / "usage.json"
    path.write_text(json.dumps({"cost_usd": 0.2, "cost_basis": basis, "measurement_source": "fixture rate source"}))
    ledger = tmp_path / "usage.jsonl"
    assert usage.main(_finish_args(ledger, path)) == 0
    event = json.loads(ledger.read_text())
    assert event["cost_usd"] == 0.2
    assert event["cost_basis"] == basis
    assert event["input_tokens"] is None
    assert event["output_tokens"] is None


def test_finish_retry_preserves_the_first_completion(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = tmp_path / "usage.jsonl"
    request_id = usage.start_request(ledger, stage="review", provider="local", model=None, scope_digest="fixture")
    measurements = tmp_path / "measurements.json"
    measurements.write_text('{"measurement_source": "fixture", "input_tokens": 4}', encoding="utf-8")
    argv = _finish_args(ledger, measurements)
    argv[argv.index("--id") + 1] = request_id
    assert usage.main(argv) == 0
    original = ledger.read_bytes()

    assert usage.main(argv) == 0
    assert ledger.read_bytes() == original

    measurements.write_text('{"measurement_source": "fixture", "input_tokens": 5}', encoding="utf-8")
    assert usage.main(argv) == 2
    assert "conflicts with the recorded completion" in capsys.readouterr().err
    assert ledger.read_bytes() == original
    group = usage.summarize([ledger])["groups"][0]
    assert group["succeeded"] == 1
    assert group["input_tokens_known"] == 4


def test_finish_retry_resynchronizes_the_first_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "usage.jsonl"
    request_id = usage.start_request(ledger, stage="review", provider="local", model=None, scope_digest="fixture")
    measurements = {"measurement_source": "fixture", "input_tokens": 4}

    def unavailable_fsync(_fd: int) -> None:
        msg = "simulated ledger synchronization failure"
        raise OSError(msg)

    with monkeypatch.context() as failed_disk:
        failed_disk.setattr(usage.os, "fsync", unavailable_fsync)
        with pytest.raises(OSError, match="simulated ledger synchronization failure"):
            usage.finish_request(ledger, request_id, status="succeeded", usage=measurements)
        original = ledger.read_bytes()
        assert json.loads(original.splitlines()[-1])["event"] == "finished"
        with pytest.raises(OSError, match="simulated ledger synchronization failure"):
            usage.finish_request(ledger, request_id, status="succeeded", usage=measurements)

    usage.finish_request(ledger, request_id, status="succeeded", usage=measurements)
    assert ledger.read_bytes() == original
    assert usage.summarize([ledger])["groups"][0]["succeeded"] == 1


@pytest.mark.parametrize("status", ["attempts", "measured_cost_usd", "unfinished", None, []])
def test_report_rejects_invalid_restored_completion(tmp_path: Path, capsys: pytest.CaptureFixture[str], status: object) -> None:
    ledger = tmp_path / "usage.jsonl"
    request_id = usage.start_request(ledger, stage="review", provider="local", model=None, scope_digest="fixture")
    usage.finish_request(ledger, request_id, status="succeeded", usage={"cost_basis": "measured", "cost_usd": 0, "measurement_source": "fixture"})
    start, end = map(json.loads, ledger.read_text(encoding="utf-8").splitlines())
    end["status"] = status
    ledger.write_text(f"{json.dumps(start)}\n{json.dumps(end)}\n", encoding="utf-8")
    assert usage.main(["report", str(ledger)]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "invalid request status" in output.err
