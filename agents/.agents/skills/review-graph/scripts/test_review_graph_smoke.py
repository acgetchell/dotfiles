"""Verify the environment smoke retains real timing and rejects corrupted evidence."""

import contextlib
import json
import os
import shlex
import signal
import sys
from pathlib import Path

import pytest
import review_graph_smoke
from review_graph_runtime import finalize_proof
from review_graph_smoke import run_smoke


def test_smoke_runs_native_validation_and_reloads_published_evidence(tmp_path: Path) -> None:
    output = tmp_path / "smoke"
    final = run_smoke(output)
    assert final["graph_proof_status"] == "complete"
    assert final["repository_validation_status"] == "passed"
    assert json.loads((output / "smoke.json").read_text())["model_review"] is False
    finished = json.loads((output / "validation-timing.jsonl").read_text().splitlines()[-1])
    assert finished["command_started"] is True
    assert finished["exit_code"] == 0
    assert finished["elapsed_seconds"] > 0
    request = json.loads((output / "final-request.json").read_text())
    assert finalize_proof(request)["graph_proof_status"] == "complete"
    Path(request["sources"][0]["artifact_path"]).write_text("corrupted")
    with pytest.raises(ValueError, match="artifact digest does not match evidence metadata"):
        finalize_proof(request)


def test_smoke_does_not_replace_prior_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "private.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        run_smoke(output)
    assert marker.read_text() == "preserve"


@pytest.mark.parametrize("exit_code", [0, 74])
def test_main_rejects_empty_timing_receipts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], exit_code: int) -> None:
    def run(argv: list[str]) -> int:
        Path(argv[argv.index("--receipt") + 1]).write_bytes(b"")
        return exit_code

    monkeypatch.setattr(review_graph_smoke, "run_validation", run)
    output = tmp_path / "smoke"
    assert review_graph_smoke.main(["--output", str(output)]) == 2
    assert "timing receipt is empty" in capsys.readouterr().err
    assert (output / "validation-timing.jsonl").read_bytes() == b""
    assert not (output / "final-proof.json").exists()
    assert not (output / "smoke.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="Linux/macOS smoke uses POSIX process groups")
def test_validation_timeout_stops_the_child_and_retains_interruption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(review_graph_smoke, "VALIDATION_TIMEOUT_SECONDS", 2)
    pid_file = tmp_path / "child.pid"
    marker = tmp_path / "child-completed.txt"
    command = (
        "import os, signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGINT, signal.SIG_IGN); "
        f"Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(20); Path({str(marker)!r}).write_text('completed')"
    )
    entry = {
        "node_id": "validator",
        "dispatch": {"validation_unit": {"commands": [shlex.join([sys.executable, "-c", command])], "working_directories": [str(tmp_path)]}},
    }
    try:
        with pytest.raises(ValueError, match="exceeded"):
            review_graph_smoke.validation_payload(entry, tmp_path)
        pid = int(pid_file.read_text())
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not marker.exists()
        finished = json.loads((tmp_path / "validation-timing.jsonl").read_text().splitlines()[-1])
        assert finished["status"] == "interrupted"
        assert finished["command_started"] is True
        assert finished["exit_code"] != 0
        assert json.loads((tmp_path / "validation-timeout.json").read_text())["status"] == "timed-out"
    finally:
        if pid_file.exists():
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
