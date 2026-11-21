"""Dispatch scheduling and preflight capacity fixtures for review-graph tests."""

import json
import sys
from dataclasses import replace
from typing import Any
lazy from pathlib import Path

from review_graph_plan import plan_from_document
from review_graph_runtime import main, materialize_dispatches
from test_support_review_graph import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _complete_structural_fixture_routing,
    _json_plan,
    _prepare_fixture_timing,
    _sparse_plan,
    _sparse_plan_document,
)


def _preflight_request(tmp_path: Path) -> dict[str, Any]:
    """Build a read-only preflight request using an executable available on the test host."""
    plan = _sparse_plan()
    unit = replace(plan.coalesced_validation_units[0], working_directories=(str(tmp_path),))
    return {
        "plan": _json_plan(replace(plan, coalesced_validation_units=(unit,))),
        "repository_root": str(tmp_path),
        "cache_paths": [],
        "command_policy": [{"command": "true", "disposition": "allowed", "reason": "read-only fixture"}],
        "execution_prerequisites": [{"node_id": unit.node_id, "executables": [sys.executable], "native_available": True, "reason": "current host"}],
    }


def _fixture(tmp_path: Path, *, profile: str = "grouped", mixed_surfaces: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    """Prepare the saved lifecycle, dispatches, and capture for the selected scheduling profile."""
    planning = _sparse_plan_document()
    planning["execution_profile"] = profile
    if mixed_surfaces:
        path = "scripts/skill_validate.py"
        planning["captured_paths"].append(path)
        planning["consulted_routers"].append("python-review-orchestrator")
        planning["routing_overrides"].append(
            {
                "applicability_evidence": ["Python support script boundary"],
                "catalog_id": "python.support-scripts",
                "disposition": "selected",
                "owners": ["python"],
                "reason": "inspect support script behavior",
                "review_surface": [path],
            }
        )
    for catalog_id in ("rust.errors", "rust.api-design", "rust.trait-bounds", "rust.tests", "rust.style"):
        planning["routing_overrides"].append({**planning["routing_overrides"][0], "catalog_id": catalog_id})
    _complete_structural_fixture_routing(planning, planning["captured_paths"])
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
    lifecycle = {"plan": _json_plan(plan), "source_state": ["scope", "worktree", "repository"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
            "artifact_store": str(tmp_path / "proof"),
        }
    )
    paths = {key: tmp_path / f"{key}.json" for key in ("input", "dispatches", "journal", "current-capture")}
    for entry in dispatches["dispatches"]:
        if entry["dispatch"]["mode"] == "validation":
            # Scheduling fixtures explicitly approve their stand-in shell policy.
            _prepare_fixture_timing(entry)
    paths["dispatches"].write_text(json.dumps(dispatches))
    paths["current-capture"].write_text(
        json.dumps({"scope_fingerprint": "scope", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"})
    )
    return lifecycle, dispatches, paths


def _run_schedule(tmp_path: Path, paths: dict[str, Path], request: dict[str, Any], name: str = "schedule") -> dict[str, Any]:
    """Write the scheduler request, invoke the CLI, and load its result from disk."""
    paths["input"] = tmp_path / f"{name}.input.json"
    paths["input"].write_text(json.dumps({"artifact_store": str(tmp_path / "schedules"), **request}))
    output = tmp_path / f"{name}.json"
    assert main(["schedule-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]) == 0
    return json.loads(output.read_text())


def _capacity(active: int) -> dict[str, Any]:
    """Describe a three-slot worker pool with the given number of active workers."""
    return {"source": "authoritative aggregate host slots (coordinator excluded)", "concurrent_worker_limit": 3, "active_workers": active}


def _audits(dispatches: dict[str, Any]) -> list[dict[str, Any]]:
    """Select audit workers from the materialized dispatch set."""
    return [entry for entry in dispatches["dispatches"] if entry["dispatch"].get("mode") == "audit"]
