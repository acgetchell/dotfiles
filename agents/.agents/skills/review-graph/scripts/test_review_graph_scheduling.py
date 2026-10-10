"""Lifecycle regressions for adaptive coordinator and worker lanes."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from review_graph_plan import plan_from_document
from review_graph_runtime import JournalEventRequest, _graph_plan, append_journal_event, main, materialize_dispatches, next_ready_nodes
from review_graph_scheduling import select_execution_lanes
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _compact_audit_payload,
    _compile_repair_fixture_entry,
    _complete_structural_fixture_routing,
    _json_plan,
    _publish_worker_bytes,
    _sparse_plan_document,
    _typed_synthesis_payload,
)


def _fixture(tmp_path: Path, *, profile: str = "grouped", mixed_surfaces: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
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
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,))
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
    paths["dispatches"].write_text(json.dumps(dispatches))
    paths["current-capture"].write_text(
        json.dumps({"scope_fingerprint": "scope", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"})
    )
    return lifecycle, dispatches, paths


def _run_schedule(tmp_path: Path, paths: dict[str, Path], request: dict[str, Any], name: str = "schedule") -> dict[str, Any]:
    paths["input"] = tmp_path / f"{name}.input.json"
    paths["input"].write_text(json.dumps({"artifact_store": str(tmp_path / "schedules"), **request}))
    output = tmp_path / f"{name}.json"
    assert main(["schedule-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]) == 0
    return json.loads(output.read_text())


def _capacity(active: int) -> dict[str, Any]:
    return {"source": "authoritative aggregate host slots (coordinator excluded)", "concurrent_worker_limit": 3, "active_workers": active}


def _audits(dispatches: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in dispatches["dispatches"] if entry["dispatch"].get("mode") == "audit"]


def test_known_full_capacity_schedules_coordinator_without_creation_and_preserves_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    validation = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation")
    source = _compile_repair_fixture_entry(validation, lifecycle, paths["journal"])
    old_files = {path: path.read_bytes() for path in (paths["dispatches"], paths["journal"], *(Path(path) for path in source.values()))}
    for entry in _audits(dispatches)[:3]:
        append_journal_event(paths["journal"], lifecycle, JournalEventRequest(entry["node_id"], "in-flight"))
    old_files[paths["journal"]] = paths["journal"].read_bytes()
    result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(3)})
    receipt = json.loads(capsys.readouterr().out)

    assert result["capacity_state"] == "known-exhausted"
    assert result["worker_node_ids"] == []
    assert result["creation_failure"] is None
    assert result["retry_after_seconds"] == 0
    assert len(result["ready_dispatches"]) == 1
    entry = result["ready_dispatches"][0]
    assert entry["dispatch"]["execution_location"] == "coordinator"
    assert entry["dispatch"]["worker_created"] is False
    assert entry["dispatch"]["fresh_context"] is False
    assert result["lineage"]["previous_dispatch_set_digest"] == dispatches["dispatch_set_digest"]
    updated = json.loads(Path(result["dispatches_path"]).read_text())
    for old, new in zip(dispatches["dispatches"], updated["dispatches"], strict=True):
        if old["node_id"] != entry["node_id"]:
            assert old == new
        else:
            assert old["dispatch"]["command_policy"] == new["dispatch"]["command_policy"]
            assert old["dispatch"]["owned_paths"] == new["dispatch"]["owned_paths"]
    assert all(path.read_bytes() == content for path, content in old_files.items())
    assert receipt["continuation"]["path"] == result["continuation_path"]
    assert receipt["ready_dispatches"][0]["worker_input"]["digest"] == "sha256:" + hashlib.sha256(Path(entry["worker_input_path"]).read_bytes()).hexdigest()
    assert "dispatch" not in receipt["ready_dispatches"][0]
    # Publication preflight must use the new coordinator input rather than the
    # ancestral worker input. Compile through the ordinary lifecycle gate.
    _publish_worker_bytes(entry, json.dumps(_compact_audit_payload(entry)).encode())
    paths["dispatches"] = Path(result["dispatches_path"])
    paths["input"] = Path(result["lifecycle_input_path"])
    compile_output = tmp_path / "compiled.json"
    compile_args = [arg for key, path in paths.items() if key != "current-capture" for arg in (f"--{key}", str(path))]
    assert (
        main(
            [
                "compile-node",
                *compile_args,
                "--before-capture",
                str(paths["current-capture"]),
                "--after-capture",
                str(paths["current-capture"]),
                "--node-id",
                entry["node_id"],
                "--output",
                str(compile_output),
            ]
        )
        == 0
    )
    evidence = json.loads(Path(entry["metadata_path"]).read_text())["evidence"]
    assert evidence["execution_location"] == "coordinator"
    assert evidence["worker_created"] is False
    assert evidence["fresh_context"] is False


@pytest.mark.parametrize("profile", ["grouped", "mixed"])
def test_three_worker_lanes_plus_one_coordinator_and_unstarted_reservations(tmp_path: Path, profile: str) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path, profile=profile)
    result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(0)})
    assert len(result["worker_node_ids"]) == 3
    assert result["coordinator_node_id"] is not None
    assert len(result["reserved_node_ids"]) == 4
    assert not paths["journal"].exists()
    assert all(entry["dispatch"].get("mode") == "audit" for entry in result["ready_dispatches"])
    paths["dispatches"] = Path(result["dispatches_path"])
    next_request = json.loads(Path(result["schedule_input_path"]).read_text())
    assert "worker_capacity" not in next_request
    repeated = _run_schedule(tmp_path, paths, {**next_request, "worker_capacity": _capacity(0)}, "reserved")
    assert repeated["ready_node_ids"] == []
    assert repeated["reserved_node_ids"] == result["reserved_node_ids"]
    assert len(dispatches["dispatches"]) == len(json.loads(Path(repeated["dispatches_path"]).read_text())["dispatches"])


def test_completed_worker_retains_slot_until_authoritative_release(tmp_path: Path) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    accepted = _audits(dispatches)[0]
    source = _compile_repair_fixture_entry(accepted, lifecycle, paths["journal"])
    evidence_bytes = {path: Path(path).read_bytes() for path in source.values()}
    full = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(3)}, "occupied")
    assert full["worker_node_ids"] == []
    paths["dispatches"] = Path(full["dispatches_path"])
    released = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(2), "reserved_node_ids": full["reserved_node_ids"]}, "released")
    assert len(released["worker_node_ids"]) == 1
    assert released["coordinator_node_id"] is None
    assert accepted["node_id"] not in released["ready_node_ids"]
    assert all(Path(path).read_bytes() == content for path, content in evidence_bytes.items())


def test_known_full_capacity_completes_all_nodes_without_worker_failures_or_replay(tmp_path: Path) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    accepted: list[str] = []
    for ordinal in range(len(dispatches["dispatches"]) + 1):
        result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(3)}, f"step-{ordinal}")
        assert result["worker_node_ids"] == []
        assert result["creation_failure"] is None
        paths["input"] = Path(result["lifecycle_input_path"])
        paths["dispatches"] = Path(result["dispatches_path"])
        if result["complete"]:
            break
        assert len(result["ready_dispatches"]) == 1
        entry = result["ready_dispatches"][0]
        assert entry["node_id"] not in accepted
        assert entry["dispatch"]["execution_location"] == "coordinator"
        _compile_repair_fixture_entry(entry, lifecycle, paths["journal"])
        accepted.append(entry["node_id"])
    assert set(accepted) == {entry["node_id"] for entry in dispatches["dispatches"]}
    output = tmp_path / "final.json"
    assert main(["finalize-proof", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["status"] == "complete"


def _publish_compile_synthesis(entry: dict[str, Any], lifecycle: dict[str, Any], paths: dict[str, Path], tmp_path: Path) -> None:
    # Public compile-node binds the actual accepted predecessor bundle.
    payload = _typed_synthesis_payload(entry["dispatch"], _compact_audit_payload(entry), _graph_plan(lifecycle["plan"]))
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    assert (
        main(
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
                str(tmp_path / f"{entry['node_id']}.compiled.json"),
            ]
        )
        == 0
    )


@pytest.mark.parametrize("profile", ["grouped", "mixed"])
def test_surface_syntheses_share_slots_and_repository_waits_for_both(tmp_path: Path, profile: str) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path, profile=profile, mixed_surfaces=True)
    for entry in dispatches["dispatches"]:
        if entry["dispatch"].get("mode") != "synthesis":
            _compile_repair_fixture_entry(entry, lifecycle, paths["journal"])
    result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(0)})
    surface_ids = {"rust-synthesis", "python-synthesis"}
    assert set(result["worker_node_ids"]) == surface_ids
    assert set(result["reserved_node_ids"]) == surface_ids
    assert result["coordinator_node_id"] is None
    assert result["deferred_node_ids"] == []
    waiting = next(item for item in result["waiting"] if item["node_id"] == "repository-synthesis")
    assert set(waiting["missing_predecessors"]) == surface_ids
    paths["dispatches"] = Path(result["dispatches_path"])
    paths["input"] = Path(result["lifecycle_input_path"])
    for node_id in surface_ids:
        append_journal_event(paths["journal"], lifecycle, JournalEventRequest(node_id, "in-flight"))
    first, second = result["ready_dispatches"]
    _publish_compile_synthesis(first, lifecycle, paths, tmp_path)
    partial = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(1)}, "partial")
    assert partial["ready_node_ids"] == []
    waiting = next(item for item in partial["waiting"] if item["node_id"] == "repository-synthesis")
    assert waiting["missing_predecessors"] == [second["node_id"]]
    paths["input"] = Path(partial["lifecycle_input_path"])
    paths["dispatches"] = Path(partial["dispatches_path"])
    _publish_compile_synthesis(second, lifecycle, paths, tmp_path)
    final = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(0)}, "final")
    assert final["worker_node_ids"] == ["repository-synthesis"]
    paths["dispatches"] = Path(final["dispatches_path"])
    paths["input"] = Path(final["lifecycle_input_path"])
    _publish_compile_synthesis(final["ready_dispatches"][0], lifecycle, paths, tmp_path)
    output = tmp_path / "proof.json"
    assert main(["finalize-proof", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["status"] == "complete"


def test_synthesis_reservations_and_in_flight_work_respect_capacity(tmp_path: Path) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path, mixed_surfaces=True)
    for entry in dispatches["dispatches"]:
        if entry["dispatch"].get("mode") != "synthesis":
            _compile_repair_fixture_entry(entry, lifecycle, paths["journal"])
    result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(2)})
    assert len(result["worker_node_ids"]) == 1
    first = result["worker_node_ids"][0]
    request = json.loads(Path(result["schedule_input_path"]).read_text())
    reserved = _run_schedule(tmp_path, paths, {**request, "worker_capacity": _capacity(2)}, "reserved-synthesis")
    assert reserved["ready_node_ids"] == []
    assert reserved["reserved_node_ids"] == [first]
    append_journal_event(paths["journal"], lifecycle, JournalEventRequest(first, "in-flight"))
    running = _run_schedule(tmp_path, paths, {**request, "worker_capacity": _capacity(1)}, "running-synthesis")
    assert len(running["worker_node_ids"]) == 1
    assert set(running["worker_node_ids"]) | {first} == {"rust-synthesis", "python-synthesis"}


def test_preflight_hold_persists_without_reserving_capacity_or_blocking_audits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    validator = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation")
    holds = [{"node_id": validator["node_id"], "reason": "Command policy blocks execution pending permission."}]
    result = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(0), "preflight_blocked_nodes": holds})
    assert json.loads(capsys.readouterr().out)["preflight_blocked_nodes"] == holds
    assert len(result["worker_node_ids"]) == 3
    assert result["coordinator_node_id"] is not None
    assert validator["node_id"] not in result["reserved_node_ids"]
    assert validator["node_id"] in result["deferred_node_ids"]
    continuation = json.loads(Path(result["schedule_input_path"]).read_text())
    assert continuation["preflight_blocked_nodes"] == holds
    paths["dispatches"] = Path(result["dispatches_path"])
    updated = json.loads(paths["dispatches"].read_text())
    for entry in _audits(updated):
        _compile_repair_fixture_entry(entry, lifecycle, paths["journal"])
    held = _run_schedule(tmp_path, paths, {**continuation, "worker_capacity": _capacity(0)}, "held")
    assert held["ready_node_ids"] == []
    assert held["complete"] is False
    assert held["waiting"]
    continuation = json.loads(Path(held["schedule_input_path"]).read_text())
    continuation["preflight_blocked_nodes"] = []
    resumed = _run_schedule(tmp_path, paths, {**continuation, "worker_capacity": _capacity(0)}, "resumed")
    assert resumed["worker_node_ids"] == [validator["node_id"]]


@pytest.mark.parametrize("damage", ["unknown", "audit", "duplicate", "blank", "reserved", "in-flight", "accepted"])
def test_preflight_hold_rejects_invalid_or_started_nodes(tmp_path: Path, damage: str) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    validator = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation")
    node_id = validator["node_id"]
    holds = [{"node_id": node_id, "reason": "Policy blocks execution."}]
    request = {**lifecycle, "worker_capacity": _capacity(1), "preflight_blocked_nodes": holds}
    if damage == "unknown":
        holds[0]["node_id"] = "not-planned"
    elif damage == "audit":
        holds[0]["node_id"] = _audits(dispatches)[0]["node_id"]
    elif damage == "duplicate":
        holds.append(holds[0])
    elif damage == "blank":
        holds[0]["reason"] = " "
    elif damage == "reserved":
        request["reserved_node_ids"] = [node_id]
    elif damage == "in-flight":
        append_journal_event(paths["journal"], lifecycle, JournalEventRequest(node_id, "in-flight"))
    else:
        _compile_repair_fixture_entry(validator, lifecycle, paths["journal"])
    paths["input"].write_text(json.dumps({**request, "artifact_store": str(tmp_path / "schedules")}))
    assert main(["schedule-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(tmp_path / "rejected.json")]) == 2
    assert not (tmp_path / "schedules").exists()


@pytest.mark.parametrize(
    ("failure_kind", "attempts", "active", "action"),
    [
        ("capacity", 1, None, "bounded-retry"),
        ("capacity", 1, 2, "bounded-retry"),
        ("capacity", 1, 3, "coordinator-fallback"),
        ("capacity", 2, None, "coordinator-fallback"),
        ("unexpected", 1, None, "coordinator-fallback"),
    ],
)
def test_creation_failures_preserve_diagnostics_and_only_retry_uncertain_capacity(
    tmp_path: Path, failure_kind: str, attempts: int, active: int | None, action: str
) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    failed = _audits(dispatches)[0]
    failure = {
        "node_id": failed["node_id"],
        "failure_kind": failure_kind,
        "attempts": attempts,
        "reason": "observed creation diagnostic",
        "worker_created": False,
    }
    request = {**lifecycle, "creation_failure": failure, "reserved_node_ids": [failed["node_id"]]}
    if active is not None:
        request["worker_capacity"] = _capacity(active)
    result = _run_schedule(tmp_path, paths, request)
    assert result["creation_failure"] == failure
    assert result["creation_failure_action"] == action
    if action == "bounded-retry":
        assert result["retry_after_seconds"] == 30
        retried = next(entry for entry in result["ready_dispatches"] if entry["node_id"] == failed["node_id"])
        assert retried == failed
        assert result["coordinator_node_id"] != failed["node_id"]
    else:
        assert result["retry_after_seconds"] == 0
        assert result["coordinator_node_id"] == failed["node_id"]
        assert failed["node_id"] not in result["worker_node_ids"]
    assert not paths["journal"].exists()


def test_creation_failure_waits_for_busy_coordinator_without_losing_reservation_history(tmp_path: Path) -> None:
    lifecycle, _dispatches, paths = _fixture(tmp_path)
    initial = _run_schedule(tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(0)}, "initial")
    failed_id = initial["worker_node_ids"][0]
    coordinator_id = initial["coordinator_node_id"]
    paths["dispatches"] = Path(initial["dispatches_path"])
    append_journal_event(paths["journal"], lifecycle, JournalEventRequest(coordinator_id, "in-flight"))
    failure = {"node_id": failed_id, "failure_kind": "unexpected", "attempts": 1, "reason": "unexpected host error", "worker_created": False}
    waiting = _run_schedule(
        tmp_path, paths, {**lifecycle, "worker_capacity": _capacity(3), "reserved_node_ids": initial["reserved_node_ids"], "creation_failure": failure}, "busy"
    )
    assert waiting["ready_node_ids"] == []
    assert waiting["retry_after_seconds"] == 0
    continuation_input = json.loads(Path(waiting["schedule_input_path"]).read_text())
    assert continuation_input["creation_failure"] == failure
    coordinator = next(entry for entry in initial["ready_dispatches"] if entry["node_id"] == coordinator_id)
    _compile_repair_fixture_entry(coordinator, lifecycle, paths["journal"])
    paths["dispatches"] = Path(waiting["dispatches_path"])
    resumed = _run_schedule(tmp_path, paths, {**continuation_input, "worker_capacity": _capacity(3)}, "resumed")
    assert resumed["coordinator_node_id"] == failed_id
    assert coordinator_id not in resumed["reserved_node_ids"]
    assert "creation_failure" not in json.loads(Path(resumed["schedule_input_path"]).read_text())


def test_schedule_replay_is_idempotent_and_output_conflict_leaves_store_retryable(tmp_path: Path) -> None:
    lifecycle, _dispatches, paths = _fixture(tmp_path)
    request = {**lifecycle, "worker_capacity": _capacity(3)}
    paths["input"].write_text(json.dumps({**request, "artifact_store": str(tmp_path / "schedules")}))
    output = tmp_path / "result.json"
    output.write_text("immutable prior output")
    args = ["schedule-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]
    assert main(args) == 2
    assert output.read_text() == "immutable prior output"
    assert not (tmp_path / "schedules").exists()
    output.unlink()
    assert main(args) == 0
    first = output.read_bytes()
    assert main(args) == 0
    assert output.read_bytes() == first


@pytest.mark.parametrize("profile", ["isolated", "isolated-only"])
def test_isolated_profiles_reject_scheduling_and_explicit_coordinator_materialization(tmp_path: Path, profile: str) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path, profile=profile)
    request = {**lifecycle, "artifact_store": str(tmp_path / "schedules"), "worker_capacity": _capacity(3)}
    paths["input"].write_text(json.dumps(request))
    output = tmp_path / "schedule.json"
    assert main(["schedule-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]) == 2
    assert not output.exists()
    assert not (tmp_path / "schedules").exists()
    with pytest.raises(ValueError, match="isolated dispatches require worker"):
        materialize_dispatches(
            {
                **lifecycle,
                "artifact_store": str(tmp_path / "invalid"),
                "authorization": "review-only",
                "repository_root": str(SKILL_ROOT.parents[2]),
                "state_verification_command": "capture_scope.py",
                "execution_locations": {dispatches["dispatches"][0]["node_id"]: "coordinator"},
            }
        )


@pytest.mark.parametrize("case", ["stale", "output", "dangling-output", "bad-capacity", "unknown-reservation", "created", "started-failure"])
def test_invalid_schedule_publishes_no_continuation(tmp_path: Path, case: str) -> None:
    lifecycle, dispatches, paths = _fixture(tmp_path)
    request = {**lifecycle, "artifact_store": str(tmp_path / "schedules"), "worker_capacity": _capacity(3)}
    audit = _audits(dispatches)[0]
    if case == "stale":
        paths["current-capture"].write_text(
            json.dumps({"scope_fingerprint": "changed", "captured_worktree_fingerprint": "worktree", "repository_state_fingerprint": "repository"})
        )
    elif case == "output":
        Path(audit["worker_payload_path"]).write_text("uncompiled output")
    elif case == "dangling-output":
        Path(audit["worker_payload_path"]).symlink_to(tmp_path / "absent-output")
    elif case == "bad-capacity":
        request["worker_capacity"] = _capacity(4)
    elif case == "unknown-reservation":
        request["reserved_node_ids"] = ["not-planned"]
    else:
        request["creation_failure"] = {
            "node_id": audit["node_id"],
            "failure_kind": "unexpected",
            "attempts": 1,
            "reason": "creation error",
            "worker_created": case == "created",
        }
        if case == "started-failure":
            append_journal_event(paths["journal"], lifecycle, JournalEventRequest(audit["node_id"], "in-flight"))
    paths["input"].write_text(json.dumps(request))
    output = tmp_path / "invalid.json"
    assert main(["schedule-ready", *(arg for key, path in paths.items() for arg in (f"--{key}", str(path))), "--output", str(output)]) == 2
    assert not output.exists()
    assert not (tmp_path / "schedules").exists()
    if case == "dangling-output":
        assert Path(audit["worker_payload_path"]).is_symlink()
        assert not (tmp_path / "absent-output").exists()


def test_independent_review_and_serial_work_do_not_use_parallel_coordinator_lane(tmp_path: Path) -> None:
    lifecycle, dispatches, _paths = _fixture(tmp_path)
    ready = next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=(), dispatch_set=dispatches)
    entries = {entry["node_id"]: entry for entry in dispatches["dispatches"]}
    modes = {node["node_id"]: node["mode"] for node in lifecycle["plan"]["actual_worker_nodes"]}
    independent = _audits(dispatches)[0]["node_id"]
    modes[independent] = "independent-review"
    only_independent = deepcopy(ready)
    only_independent["ready_node_ids"] = [independent]
    selected = select_execution_lanes({"worker_capacity": _capacity(3)}, modes=modes, entries=entries, ready=only_independent)
    assert selected["coordinator_node_id"] is None
    assert selected["worker_node_ids"] == []
    validation = next(node_id for node_id, mode in modes.items() if mode == "validation")
    ready["lifecycle"]["in_flight_node_ids"] = [validation]
    ready["ready_node_ids"].remove(validation)
    selected = select_execution_lanes({"worker_capacity": _capacity(1)}, modes=modes, entries=entries, ready=ready)
    assert selected["coordinator_node_id"] is None
    assert selected["worker_node_ids"] == []


@pytest.mark.parametrize("serial_mode", ["validation", "fix"])
@pytest.mark.parametrize("occupied_mode", ["serial", "synthesis"])
@pytest.mark.parametrize("occupancy", ["in-flight", "reserved"])
def test_serial_work_and_synthesis_exclude_each_other(tmp_path: Path, serial_mode: str, occupied_mode: str, occupancy: str) -> None:
    lifecycle, dispatches, _paths = _fixture(tmp_path)
    entries = {entry["node_id"]: entry for entry in dispatches["dispatches"]}
    modes = {node["node_id"]: node["mode"] for node in lifecycle["plan"]["actual_worker_nodes"]}
    serial = next(node_id for node_id, mode in modes.items() if mode == "validation")
    modes[serial] = serial_mode
    synthesis = "rust-synthesis"
    occupied, candidate = (serial, synthesis) if occupied_mode == "serial" else (synthesis, serial)
    request = {"worker_capacity": _capacity(1 if occupancy == "in-flight" else 0)}
    ready = {"ready_node_ids": [candidate], "lifecycle": {"in_flight_node_ids": []}}
    if occupancy == "reserved":
        request["reserved_node_ids"] = [occupied]
        ready["ready_node_ids"].append(occupied)
    else:
        ready["lifecycle"]["in_flight_node_ids"] = [occupied]
    selected = select_execution_lanes(request, modes=modes, entries=entries, ready=ready)
    assert selected["coordinator_node_id"] is None
    assert selected["worker_node_ids"] == []
