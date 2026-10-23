"""Large captures survive compact transport and bind compilation to saved bytes."""

import json
import shlex
import subprocess
from pathlib import Path

import capture_scope
import pytest
import review_graph_runtime as runtime
from review_graph_bootstrap import bootstrap_document
from review_graph_handoffs import audit_observations
from review_graph_plan import plan_from_document
from review_graph_session import runtime_command
from test_capture_scope import _commit_all, _init_repo
from test_review_graph_runtime import ROUTING_CATALOG, SKILL_ROOT, _baseline_mutation_fixture, _json_plan, _worker_input_fixture


def test_large_audit_captures_persist_before_compact_receipts(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _init_repo(repository)
    # Cross the serialized-size boundary without hundreds of extra Git traversals.
    sources = [repository / f"source-{index:04}-{'capture-' * 9}.py" for index in range(160)]
    for index, source in enumerate(sources):
        source.write_text(f"value = {index}\n")
    _commit_all(repository)
    command = runtime_command(Path(capture_scope.__file__), "--repo", str(repository), "--mode", "baseline")
    dispatch = {"node_id": "audit-001", "repository_root": str(repository), "state_verification_command": shlex.join(command)}
    observations = audit_observations(dispatch, tmp_path / "contract.json")
    dispatch["audit_observations"] = observations
    for observation in observations.values():
        result = subprocess.run(shlex.split(observation["capture_command"]), capture_output=True, check=True, timeout=30)  # noqa: S603 - emitted framework command.
        receipt = json.loads(result.stdout)
        path = Path(observation["capture_path"])
        capture = json.loads(path.read_bytes())
        assert path.stat().st_size > 65000
        assert len(result.stdout) < 1500
        assert receipt["capture_digest"] == runtime.digest_bytes(path.read_bytes())
        for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint"):
            assert receipt[key] == capture[key]
        assert json.loads(Path(observation["receipt_path"]).read_bytes()) == receipt
    before, after = (Path(observations[phase]["capture_path"]) for phase in ("before", "after"))
    runtime._verify_audit_captures(dispatch, before, after)
    with pytest.raises(ValueError, match="dispatched artifact path"):
        runtime._verify_audit_captures(dispatch, after, before)
    receipt_path = Path(observations["before"]["receipt_path"])
    receipt_path.unlink()
    with pytest.raises(ValueError, match="regular non-symlink file"):
        runtime._verify_audit_captures(dispatch, before, after)
    retained_bytes = before.read_bytes()
    sources[0].write_text("value = 'changed'\n")
    result = subprocess.run(shlex.split(observations["before"]["capture_command"]), capture_output=True, check=False, timeout=30)  # noqa: S603
    assert result.returncode == 2
    assert b"refusing to overwrite" in result.stderr
    assert before.read_bytes() == retained_bytes


@pytest.mark.parametrize("option", ["separate", "equals"])
def test_validator_rebinds_existing_capture_outputs_and_snapshots_full_json(tmp_path: Path, option: str) -> None:

    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    old = tmp_path / "old.capture.json"
    base = runtime_command(Path(capture_scope.__file__), "--repo", str(repository), "--mode", "baseline")
    subprocess.run([*base, "--output", str(old)], check=True, capture_output=True)  # noqa: S603 - framework capture in a fixture.
    original = old.read_bytes()
    (repository / "state.rs").write_text("pub fn state() { assert!(true); }\n")
    capture = capture_scope._scope_data(git, repository, "baseline", None, ())
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    output = ["--output", str(old)] if option == "separate" else [f"--output={old}"]
    entries = runtime.materialize_dispatches(
        {
            "plan": _json_plan(plan),
            "source_state": [capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")],
            "artifact_store": str(tmp_path / "dispatch"),
            "repository_root": str(repository),
            "authorization": "review-only",
            "state_verification_command": shlex.join([*base, *output]),
        }
    )
    validator = next(entry for entry in entries["dispatches"] if entry["result_contract"] == "compact-validation")
    for observation in validator["dispatch"]["validation_observations"].values():
        result = subprocess.run(shlex.split(observation["capture_command"]), check=True, capture_output=True)  # noqa: S603
        receipt = json.loads(result.stdout)
        full = json.loads(Path(observation["capture_path"]).read_bytes())
        assert "repository_path_fingerprints" in full
        assert "repository_path_fingerprints" not in receipt
        assert full == capture
        subprocess.run(observation["workspace_command"], check=True, capture_output=True)  # noqa: S603
        assert json.loads(Path(observation["workspace_path"]).read_bytes())["observed_source_state"] == validator["dispatch"]["source_state"]
    assert old.read_bytes() == original


def test_invalid_custom_observation_can_be_corrected_before_materialization(tmp_path: Path) -> None:

    document, _entries = _worker_input_fixture(tmp_path / "prior")
    store = tmp_path / "new-dispatch"
    request = {**document, "artifact_store": str(store), "state_verification_command": "custom-capture --output old.json"}
    with pytest.raises(ValueError, match="custom capture command must emit full capture JSON"):
        runtime.materialize_dispatches(request)
    assert not store.exists()
    request["state_verification_command"] = "custom-capture"
    result = runtime.materialize_dispatches(request)
    assert result["source_state"] == document["source_state"]
