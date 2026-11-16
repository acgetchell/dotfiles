"""Keep worker publication contracts intact as scheduling relocates peer artifacts."""

import json
import shlex
from pathlib import Path
from typing import Any

import pytest
from review_graph_runtime import JournalEventRequest, append_journal_event, main
from test_review_graph_runtime import _compact_audit_payload, _compile_repair_fixture_entry, _publish_worker_bytes
from test_review_graph_scheduling import _audits, _capacity, _fixture, _run_schedule


def _compile(paths: dict[str, Path], entry: dict[str, Any], output: Path) -> int:
    return main(
        [
            "compile-node",
            *(arg for key, path in paths.items() if key != "current-capture" for arg in (f"--{key}", str(path))),
            "--node-id",
            entry["node_id"],
            "--before-capture",
            str(paths["current-capture"]),
            "--after-capture",
            str(paths["current-capture"]),
            "--output",
            str(output),
        ]
    )


def _schedule_with_worker(
    tmp_path: Path, *, profile: str = "grouped", already_dispatched: bool = False
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path], dict[str, Any], dict[str, Any]]:
    lifecycle, dispatches, paths = _fixture(tmp_path, profile=profile)
    validator = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation")
    _compile_repair_fixture_entry(validator, lifecycle, paths["journal"])
    # The scheduler assigns the first ready audit to its coordinator lane.
    worker = _audits(dispatches)[1]
    if already_dispatched:
        append_journal_event(paths["journal"], lifecycle, JournalEventRequest(worker["node_id"], "in-flight"))
    result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(int(already_dispatched))})
    updated = json.loads(Path(result["dispatches_path"]).read_bytes())
    assert next(entry for entry in updated["dispatches"] if entry["node_id"] == worker["node_id"]) == worker
    coordinator = next(entry for entry in result["ready_dispatches"] if entry["node_id"] == result["coordinator_node_id"])
    original = next(entry for entry in dispatches["dispatches"] if entry["node_id"] == coordinator["node_id"])
    assert coordinator["worker_input_path"] != original["worker_input_path"]
    paths["input"] = Path(result["lifecycle_input_path"])
    paths["dispatches"] = Path(result["dispatches_path"])
    return lifecycle, result, paths, worker, coordinator


@pytest.mark.parametrize("profile", ["grouped", "mixed"])
@pytest.mark.parametrize("already_dispatched", [False, True])
def test_worker_contract_survives_peer_relocation_and_continuation(tmp_path: Path, profile: str, already_dispatched: bool) -> None:
    _lifecycle, scheduled, paths, worker, _coordinator = _schedule_with_worker(tmp_path, profile=profile, already_dispatched=already_dispatched)
    protocol = [worker[field] for field in ("worker_input_path", "worker_execution_path", "worker_payload_contract_path")]
    originals = {path: Path(path).read_bytes() for path in protocol}
    payload = _compact_audit_payload(worker, commands=(shlex.join(["cat", *protocol]),))
    _publish_worker_bytes(worker, json.dumps(payload).encode())
    published = Path(worker["worker_payload_path"]).read_bytes()

    assert _compile(paths, worker, tmp_path / "compiled.json") == 0

    metadata = json.loads(Path(worker["metadata_path"]).read_bytes())
    assert metadata["evidence"]["execution_location"] == "worker"
    assert metadata["evidence"]["fresh_context"] is True
    assert set(protocol) <= dict(metadata["expectation"]["audit_input_identity"]["runtime_inputs"]).keys()
    assert all(Path(path).read_bytes() == content for path, content in originals.items())
    assert Path(worker["worker_payload_path"]).read_bytes() == published
    request = json.loads(Path(scheduled["schedule_input_path"]).read_bytes())
    continued = _run_schedule(tmp_path, paths, {**request, "worker_capacity": _capacity(0)}, "continued")
    assert worker["node_id"] not in continued["ready_node_ids"]
    assert worker["node_id"] not in continued["reserved_node_ids"]


@pytest.mark.parametrize("artifact", ["worker_payload_contract_path", "worker_input_path", "worker_execution_path"])
def test_relocated_peer_reads_remain_forbidden_at_compilation(tmp_path: Path, capsys: pytest.CaptureFixture[str], artifact: str) -> None:
    _lifecycle, _scheduled, paths, worker, coordinator = _schedule_with_worker(tmp_path)
    # An opaque command still truthfully names the peer artifact. Publication
    # knows only the original locations; the lifecycle must enforce the new ones.
    command = "python -c " + shlex.quote(f"from pathlib import Path; Path({coordinator[artifact]!r}).read_bytes()")
    payload = _compact_audit_payload(worker, commands=(command,))
    _publish_worker_bytes(worker, json.dumps(payload).encode())
    journal = paths["journal"].read_bytes()
    output = tmp_path / "rejected.json"
    capsys.readouterr()

    assert _compile(paths, worker, output) == 2

    error = capsys.readouterr().err
    assert "fresh-context review read another node" in error
    assert coordinator[artifact] in error
    assert paths["journal"].read_bytes() == journal
    assert not output.exists()
    assert not Path(worker["artifact_path"]).exists()
    assert not Path(worker["metadata_path"]).exists()
