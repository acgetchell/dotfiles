"""Large frozen reviews resume without altering their original evidence."""

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_reuse import source_snapshot
from test_review_graph_continuity_e2e import _compile, _frozen_run
from test_review_graph_runtime import _compact_audit_payload
from test_review_graph_sessions import _cli


def test_updated_runtime_advances_large_frozen_baseline_without_reauditing_unchanged_source(tmp_path: Path) -> None:
    git, repository, bundle, dispatches, frozen, dispatch_path = _frozen_run(tmp_path, early=False, large_scope=True)
    audit = next(entry for entry in dispatches["dispatches"] if entry["dispatch"].get("skill_id") == "python-cli-review")
    _cli(frozen, "publish-worker-payload", "--input", audit["worker_payload_contract_path"], stdin=json.dumps(_compact_audit_payload(audit)).encode())
    _compile(
        frozen,
        tmp_path / "bootstrap.json",
        dispatch_path,
        tmp_path / "execution.jsonl",
        audit,
        bundle["capture_path"],
        bundle["capture_path"],
        tmp_path / "audited.json",
    )
    originals = {Path(audit[key]): Path(audit[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    (repository / "extra.txt").write_text("new untracked source obligation\n")
    bundle["planning_input"]["routing_overrides"].append(
        {
            "catalog_id": "repo.tooling",
            "disposition": "selected",
            "reason": "The scripted repair introduces a repository input contract outside the unchanged Python CLI",
            "applicability_evidence": ["extra.txt is a new untracked repository input"],
            "review_surface": ["extra.txt"],
            "owners": ["tooling"],
        }
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    captured_paths = source_snapshot(capture).captured_scope_paths
    assert len(shlex.join(captured_paths)) > 4096
    request_path, output_path = tmp_path / "advance.json", tmp_path / "advanced.json"
    request_path.write_text(
        json.dumps(
            {
                **bundle["lifecycle_input"],
                "previous_capture": bundle["capture"],
                "new_capture": capture,
                "planning_template": bundle["planning_input"],
                "repair_epoch": 1,
                "changed_paths": ["extra.txt"],
                "authorization_before": "review-and-fix",
                "authorization_after": "review-and-fix",
                "artifact_store": str(tmp_path / "recovery"),
                "state_verification_command": "capture_scope.py --mode baseline",
                "routing_catalog_path": str(frozen.parent.parent / "references/routing-catalog.json"),
                "sources": [{key: audit[key] for key in ("artifact_path", "metadata_path")}],
            }
        )
    )
    updated_root = tmp_path / "updated-runtime" / "skills" / "review-graph"
    shutil.copytree(Path(runtime.__file__).parent.parent, updated_root, ignore=shutil.ignore_patterns("test_*.py", "__pycache__", "*.pyc"))
    # Only the frozen root has the specialist skills and their static references.
    updated_runtime = updated_root / "scripts" / "review_graph_runtime.py"
    subprocess.run(  # noqa: S603 - fixed current runtime and isolated fixture paths.
        [sys.executable, "-B", str(updated_runtime), "advance-after-mutation", "--input", str(request_path), "--output", str(output_path)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    result = json.loads(output_path.read_bytes())
    independent = next(entry["dispatch"] for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["mode"] == "independent-review")
    assert len(independent["change_target"]) <= 4096
    assert shlex.split(independent["change_target"]) == ["git", "diff", bundle["capture"]["head"], "--", "."]
    comparison = subprocess.run(shlex.split(independent["change_target"]), cwd=repository, capture_output=True, check=True)  # noqa: S603 - runtime-built diff.
    assert comparison.stdout == b""  # Git omits the new file; direct source obligations must retain it.
    assert independent["owned_paths"] == ["extra.txt"]
    assert set(result["capture"]["captured_scope_paths"]) == set(captured_paths)
    assert audit["dispatch"]["evidence_id"] in result["reused_evidence_ids"]
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert result["new_plan"]["review_lifecycle"]["repairs_completed"] == 1
    assert result["new_plan"]["review_lifecycle"]["run_control"] == bundle["lifecycle_input"]["plan"]["review_lifecycle"]["run_control"]
    assert len(result["new_plan"]["coalesced_validation_units"]) == len(bundle["lifecycle_input"]["plan"]["coalesced_validation_units"])
