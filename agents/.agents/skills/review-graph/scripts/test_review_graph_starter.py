"""Runnable bootstrap preset, read-only preflight, and protocol accounting."""

import json
import os
import shutil
import subprocess
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from capture_scope import _scope_data
from research_repo_tools.process import run_command_bytes
from review_graph_bootstrap import PLANNING_SCHEMA, RUNTIME_SCHEMA, bootstrap_document, main
from review_graph_plan import DEFAULT_ROUTING_CATALOG, DEFAULT_SKILL_ROOT, plan_from_document
from review_graph_runtime import main as runtime_main
from review_graph_schema import SchemaValidationError, require_schema, require_schema_definition
from review_graph_starter import STARTER_EXAMPLE, STARTER_SCHEMA, starter_template
from test_review_graph_runtime import STATE_FIXTURE


@cache
def _branch_capture() -> dict[str, Any]:
    """Capture one committed fixture from existing history without changing Git."""
    repository = DEFAULT_SKILL_ROOT.parents[2]
    git = shutil.which("git")
    assert git is not None
    base = run_command_bytes(git, ("-C", str(repository), "rev-list", "--max-parents=0", "HEAD")).stdout.decode().splitlines()[0]
    return _scope_data(git, repository, "branch", base, (STATE_FIXTURE,))


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Use tracked ignore rules and source read-only; create no Git repository/state."""
    capture = deepcopy(_branch_capture())
    choices = json.loads(STARTER_EXAMPLE.read_text())
    root = tmp_path / "proof ' space $(no-shell-expansion)"
    root.mkdir()
    choices.update(
        artifact_root=str(root),
        consulted_routers=["review-graph", "rust-review-orchestrator"],
        ignored_outputs=[{"path": ".pytest_cache", "kind": "cache"}],
        command_policy={"disposition": "allowed", "reason": "Deterministic stand-in emits text and exits; no Git or source mutation."},
    )
    host = tmp_path / "host"
    host.mkdir()
    just = host / "just"
    just.write_text('#!/bin/sh\nprintf "%s\\n" "$UV_CACHE_DIR"\nexit 7\n')
    just.chmod(0o755)
    choices["execution_prerequisites"] = {
        "executables": [str(just)],
        "native_available": True,
        "reason": "POSIX stand-in inspected for this deterministic fixture; no recipe is run by bootstrap.",
    }
    return capture, choices


def _invoke(tmp_path: Path, capture: dict[str, Any], choices: dict[str, Any]) -> tuple[int, Path]:
    capture_path, choices_path, output = (tmp_path / name for name in ("capture.json", "choices.json", "bootstrap.json"))
    capture_path.write_text(json.dumps(capture, indent=2) + "\n")
    choices_path.write_text(json.dumps(choices, indent=2) + "\n")
    return main(["--capture", str(capture_path), "--starter-config", str(choices_path), "--output", str(output)]), output


def test_starter_bootstrap_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture, choices = _fixture(tmp_path)
    original_choices = deepcopy(choices)
    status, output = _invoke(tmp_path, capture, choices)
    captured = capsys.readouterr()
    assert status == 0, captured.err
    receipt = json.loads(captured.out)
    assert receipt["dispatch_allowed"]
    assert receipt["preflight_status"] == "ready"
    assert receipt["next_command"][2] == "materialize-dispatches"
    bundle = json.loads(output.read_text())
    document = bundle["planning_input"]
    require_schema(choices, STARTER_SCHEMA)
    require_schema(document, PLANNING_SCHEMA)
    require_schema_definition(bundle["preflight_input"], RUNTIME_SCHEMA, "preflight-validation")
    require_schema_definition(bundle["materialization_input"], RUNTIME_SCHEMA, "materialize-dispatches")
    for operation in ("compile-node", "finalize-proof", "journal-append", "next-ready", "snapshot-workspace"):
        require_schema_definition(bundle["lifecycle_input"], RUNTIME_SCHEMA, operation)
    assert document["scope_mode"] == "branch"
    requirement = document["validation_requirements"][0]
    assert requirement["baseline"]
    assert requirement["requested_scope"] == "branch"
    assert requirement["source_state"] == [capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")]
    assert requirement["captured_paths"] == capture["captured_scope_paths"]
    assert requirement["working_directories"] == [capture["repository_root"]]
    assert not requirement["requires_isolation"]
    assert requirement["isolation_root"] == choices["artifact_root"]
    unit = bundle["plan"]["coalesced_validation_units"][0]
    assert unit["allowed_artifacts"][-1]["status_source"] == "repository-rule"
    assert bundle["preflight_input"]["execution_prerequisites"][0]["node_id"] == unit["node_id"]
    assert bundle["preflight_input"]["command_policy"][0]["command"] == unit["commands"][0]
    assert any(node["mode"] == "independent-review" for node in bundle["plan"]["actual_worker_nodes"])
    assert choices == original_choices
    assert not list(Path(choices["artifact_root"]).iterdir())

    # Deterministic retry preserves immutable output, including the actual plan.
    original_bytes = output.read_bytes()
    assert _invoke(tmp_path, capture, choices)[0] == 0
    assert output.read_bytes() == original_bytes
    capsys.readouterr()
    # The saved bundle can rerun public preflight without hand-built plan/node IDs.
    preflight_path = tmp_path / "preflight.json"
    assert runtime_main(["preflight-validation", "--input", str(output), "--output", str(preflight_path)]) == 0
    assert json.loads(preflight_path.read_text()) == bundle["preflight_report"]
    capsys.readouterr()

    metrics = receipt["starter_metrics"]
    assert metrics["protocol_operations"] == ["bootstrap", "preflight-validation"]
    assert metrics["protocol_operation_count"] == 2
    assert metrics["cli_invocations"] == 1
    assert metrics["operator_input_bytes"] == (tmp_path / "choices.json").stat().st_size
    assert metrics["capture_input_bytes"] == (tmp_path / "capture.json").stat().st_size
    assert metrics["planning_input_bytes"] == len(json.dumps(document, sort_keys=True, separators=(",", ":")).encode())
    assert metrics["preflight_input_bytes"] == len(json.dumps(bundle["preflight_input"], sort_keys=True, separators=(",", ":")).encode())
    assert metrics["model_tokens"] is metrics["provider_cost"] is None
    print(json.dumps(metrics, sort_keys=True))


def test_generated_command_quotes_paths_and_preserves_ci_failure(tmp_path: Path) -> None:
    capture, choices = _fixture(tmp_path)
    document = bootstrap_document(capture, starter_template(capture, choices))
    command = document["validation_requirements"][0]["commands"][0]
    result = subprocess.run(  # noqa: S603 - generated command executes only the isolated stand-in.
        ["/bin/sh", "-c", command], cwd=tmp_path, env={**os.environ, "PATH": str(tmp_path / "host") + os.pathsep + os.defpath}, check=False
    )
    assert result.returncode == 7
    assert (Path(choices["artifact_root"]) / "ci.log").read_text().strip() == str(Path(choices["artifact_root"]) / "uv-cache")
    assert not (tmp_path / "no-shell-expansion").exists()


@pytest.mark.parametrize("field", ["authorization", "environment", "artifact_root", "ignored_outputs", "command_policy", "execution_prerequisites"])
def test_starter_requires_operator_choices(tmp_path: Path, field: str) -> None:
    capture, choices = _fixture(tmp_path)
    del choices[field]
    with pytest.raises(SchemaValidationError, match=rf"\$.{field}"):
        starter_template(capture, choices)


@pytest.mark.parametrize("field", ["source_state", "captured_paths", "capture_command", "node_id"])
def test_starter_does_not_accept_transcribed_runtime_identities(tmp_path: Path, field: str) -> None:
    capture, choices = _fixture(tmp_path)
    choices[field] = "operator-invented"
    with pytest.raises(SchemaValidationError, match="unknown field"):
        starter_template(capture, choices)


@pytest.mark.parametrize("mode", ["baseline", "worktree", "staged"])
def test_other_scopes_require_general_bootstrap(tmp_path: Path, mode: str) -> None:
    capture, choices = _fixture(tmp_path)
    capture["capture_mode"] = mode
    with pytest.raises(ValueError, match="nonempty branch capture"):
        starter_template(capture, choices)


@pytest.mark.parametrize("defect", ["policy", "native", "executable"])
def test_starter_preflight_blocks_before_dispatch(tmp_path: Path, capsys: pytest.CaptureFixture[str], defect: str) -> None:
    capture, choices = _fixture(tmp_path)
    if defect == "policy":
        choices["command_policy"]["disposition"] = "blocked"
    elif defect == "native":
        choices["execution_prerequisites"]["native_available"] = False
    else:
        choices["execution_prerequisites"]["executables"] = [str(tmp_path / "missing")]
    status, output = _invoke(tmp_path, capture, choices)
    receipt = json.loads(capsys.readouterr().out)
    assert status == 2
    assert receipt["next_command"] is None
    assert not receipt["dispatch_allowed"]
    assert receipt["blockers"]
    bundle = json.loads(output.read_text())
    assert bundle["preflight_report"]["status"] == "blocked"
    assert not list(Path(choices["artifact_root"]).iterdir())


def test_public_example_is_schema_valid_and_requires_policy_inspection() -> None:
    choices = json.loads(STARTER_EXAMPLE.read_text())
    require_schema(choices, STARTER_SCHEMA)
    assert choices["command_policy"]["disposition"] == "blocked"
    assert not choices["execution_prerequisites"]["native_available"]


@pytest.mark.parametrize("defect", ["missing-root", "execution-isolation", "unignored-output", "overlap", "symlink-overlap"])
def test_output_combinations_fail_before_any_dispatch(tmp_path: Path, defect: str) -> None:
    capture, choices = _fixture(tmp_path)
    repository = Path(capture["repository_root"])
    if defect in {"overlap", "symlink-overlap"}:
        root = repository
        if defect == "symlink-overlap":
            root = tmp_path / "repository-link"
            root.symlink_to(repository, target_is_directory=True)
        choices["artifact_root"] = str(root)
        with pytest.raises(ValueError, match="overlap"):
            starter_template(capture, choices)
        return
    template = starter_template(capture, choices)
    requirement = template["validation_requirements"][0]
    if defect == "missing-root":
        requirement["isolation_root"] = None
        diagnostic = "outside-repository artifact requires a dispatched isolation root"
    elif defect == "execution-isolation":
        requirement["requires_isolation"] = True
        diagnostic = "isolated working directories"
    else:
        requirement["allowed_artifacts"].append({"path": "AGENTS.md", "kind": "report", "repository_status": "ignored"})
        diagnostic = "not ignored"
    with pytest.raises(ValueError, match=diagnostic):
        plan_from_document(
            bootstrap_document(capture, template), catalog_path=DEFAULT_ROUTING_CATALOG, skill_roots=(DEFAULT_SKILL_ROOT,), repository_root=repository
        )


def test_starter_does_not_replace_existing_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capture, choices = _fixture(tmp_path)
    assert _invoke(tmp_path, capture, choices)[0] == 0
    capsys.readouterr()
    output = tmp_path / "bootstrap.json"
    original = output.read_bytes()
    choices["environment"] = "different executor"
    assert _invoke(tmp_path, capture, choices)[0] == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert output.read_bytes() == original
