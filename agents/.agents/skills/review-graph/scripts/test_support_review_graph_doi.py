"""Citation captures and DOI verification fixtures for review-graph tests."""

import base64
import json
from copy import deepcopy
from hashlib import sha256
from typing import Any
lazy from pathlib import Path

from review_graph_doi import captured_software_inputs
from review_graph_reuse import SNAPSHOT_FORMAT, regular_file_fingerprint, source_snapshot
from test_support_review_graph import _sparse_plan_document

CFF_CONTENT = b"title: 'Project: Scientific software'\n"


def _source_capture(root: Path) -> dict[str, Any]:
    """Build a source capture whose stored fingerprint matches its fixture contents."""
    capture = {
        "repository_state_format": SNAPSHOT_FORMAT,
        "repository_root": str(root),
        "capture_mode": "baseline",
        "head": "fixture",
        "branch": "main",
        "base_ref": None,
        "merge_base": None,
        "requested_paths": [],
        "captured_scope_paths": ["CITATION.cff"],
        "scope_fingerprint": "a" * 64,
        "captured_worktree_fingerprint": "b" * 64,
        "repository_state_fingerprint": "pending",
        "index_fingerprint": "c" * 64,
        "repository_path_fingerprints": {"CITATION.cff": regular_file_fingerprint("CITATION.cff", CFF_CONTENT)},
        "repository_symlink_paths": [],
    }
    capture["repository_state_fingerprint"] = source_snapshot(capture).computed_fingerprint()
    return capture


def _save_report(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Write the DOI report and return an artifact declaration bound to its exact bytes."""
    content = json.dumps(rows).encode()
    path.write_bytes(content)
    return {
        "path": str(path),
        "kind": "report",
        "repository_status": "outside-repository",
        "artifact_digest_mode": "content-sha256-v1",
        "artifact_digest": "sha256:" + sha256(content).hexdigest(),
    }


def _fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Create the original and verification records plus the resolution that links their reports."""
    source = {"path": str(tmp_path / "README.md"), "digest": "sha256:" + "a" * 64}
    row = {
        "doi": "10.5281/zenodo.123",
        "line": 3,
        "status": "INSUFFICIENT_CONTEXT",
        "resolved_title": "Project: Scientific software",
        "resolved_year": "2026",
        "resolved_authors": ["Getchell"],
        "resolved_container": None,
        "source": source,
    }
    canonical = {
        "path": str(tmp_path / "CITATION.cff"),
        "digest": "sha256:" + sha256(CFF_CONTENT).hexdigest(),
        "content_base64": base64.b64encode(CFF_CONTENT).decode("ascii"),
        "doi": row["doi"],
        "title": row["resolved_title"],
        "authors": row["resolved_authors"],
        "year": row["resolved_year"],
    }
    records: list[dict[str, Any]] = []
    for name, status, report_row in (
        ("original", "failed", row),
        ("verified", "passed", {**row, "status": "OK", "local_status": "INSUFFICIENT_CONTEXT", "canonical_software": canonical}),
    ):
        artifact = _save_report(tmp_path / f"{name}.json", [report_row])
        command = "uv run validate_reference_dois.py README.md --json"
        if name == "verified":
            command += " --citation-cff CITATION.cff"
        records.append(
            {
                "record_type": "validation",
                "evidence_id": f"validation:{name}",
                "node_id": name,
                "status": status,
                "requirement_ids": [name],
                "observed_source_state": list(source_snapshot(_source_capture(tmp_path)).source_state),
                "artifacts": [artifact],
                "executions": [
                    {
                        "command": command,
                        "working_directory": str(tmp_path),
                        "result": status,
                        "exit_code": 1 if name == "original" else 0,
                        "elapsed": "0.1s",
                        "executor": "fixture",
                        "evidence": "DOI metadata report",
                        "artifact_paths": [artifact["path"]],
                    }
                ],
            }
        )
    records[1]["captured_software_inputs"] = captured_software_inputs(records[1], _source_capture(tmp_path))
    resolution = {
        "reason": "Canonical software identity independently checked on the same source.",
        "checks": [
            {
                "execution_index": 0,
                "original_report": str(tmp_path / "original.json"),
                "verification_evidence_id": records[1]["evidence_id"],
                "verification_execution_index": 0,
                "verification_report": str(tmp_path / "verified.json"),
            }
        ],
    }
    return records[0], records[1], resolution


def _requirement(record: dict[str, Any], *, baseline: bool) -> dict[str, Any]:
    """Translate a DOI execution record into a validation requirement with declared report paths."""
    requirement = deepcopy(_sparse_plan_document()["validation_requirements"][0])
    requirement.update(
        {
            "baseline": baseline,
            "canonical_recipe": None,
            "requirement_id": record["requirement_ids"][0],
            "source_state": record["observed_source_state"],
            "commands": [record["executions"][0]["command"]],
            "working_directories": [record["executions"][0]["working_directory"]],
            "requires_isolation": True,
            "isolation_root": record["executions"][0]["working_directory"],
            "expected_workspace_effects": [],
            "allowed_artifacts": [
                {"path": artifact["path"], "kind": artifact["kind"], "repository_status": "outside-repository"} for artifact in record["artifacts"]
            ],
        }
    )
    return requirement
