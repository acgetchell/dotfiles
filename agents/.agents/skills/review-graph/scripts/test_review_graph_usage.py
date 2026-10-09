"""Usage CLI inputs are discoverable, sanitized, and retain unknown measurements."""

import json
from pathlib import Path

import pytest
import review_graph_usage as usage


def _finish_args(ledger: Path, usage_path: Path) -> list[str]:
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
