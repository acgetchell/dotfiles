"""Large captures survive compact transport and bind compilation to saved bytes."""

import json
import shlex
import subprocess
from pathlib import Path

import capture_scope
import pytest
import review_graph_runtime as runtime
from review_graph_handoffs import audit_observations
from review_graph_session import runtime_command
from test_capture_scope import _commit_all, _init_repo


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
