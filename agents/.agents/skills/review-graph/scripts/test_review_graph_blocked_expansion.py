"""Late validation can proceed around a sealed, unresolved source judgment."""

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compile_repair_fixture_entry,
    _late_validation_plan,
    _late_validation_requirement,
    _set_fixture_routing,
)
from test_review_graph_transitions import _materialize, _payload
from test_support_review_graph import _prepare_all_fixture_timing


def _fixture(tmp_path: Path, *, changed_observation: bool = False) -> tuple[dict[str, Any], Namespace, dict[str, Any], dict[str, Any]]:
    _git, repository, template, capture, _plan = _baseline_mutation_fixture(tmp_path)
    _set_fixture_routing(
        template,
        {
            "catalog_id": "rust.trait-bounds",
            "disposition": "selected",
            "reason": "Minimal bounds depend on the exact locked dependency source.",
            "applicability_evidence": ["state.rs"],
            "owners": ["rust"],
            "review_surface": ["state.rs"],
        },
    )
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    lifecycle, dispatches, dispatch_path = _materialize(tmp_path, capture, plan)
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture))
    args = Namespace(dispatches=dispatch_path, current_capture=capture_path, journal=tmp_path / "execution.jsonl", output=tmp_path / "control.json")
    blocked = next(entry for entry in dispatches["dispatches"] if entry["dispatch"]["skill_id"] == "rust-trait-bounds")
    discoverer = next(entry for entry in dispatches["dispatches"] if entry["dispatch"]["mode"] == "audit" and entry != blocked)
    requirements = [
        {
            **_late_validation_requirement(),
            "requirement_id": name,
            "commands": [command],
            "working_directory": str(repository),
            "environment": environment,
            "reason": reason,
            "expected_evidence": reason,
        }
        for name, command, environment, reason in (
            ("doi-metadata", "true", "offline DOI fixture", "Verify canonical software DOI metadata."),
            ("native-platform", "true", "native platform fixture", "Check the native platform contract."),
        )
    ]
    for entry in dispatches["dispatches"]:
        if entry["dispatch"]["mode"] == "synthesis":
            continue
        if entry not in (blocked, discoverer):
            _compile_repair_fixture_entry(entry, lifecycle, args.journal)
            continue
        dispatch = entry["dispatch"]
        payload = _payload(dispatch["owned_paths"], dispatch=dispatch)
        if entry == blocked:
            payload.update(
                status="blocked",
                unresolved_uncertainties=[{"kind": "dependency", "reason": "Exact locked Delaunay 0.8.3 source was not found in the searched registry."}],
            )
        else:
            payload["validation_requirements"] = requirements
        after_state = [*lifecycle["source_state"][:2], "changed"] if entry == blocked and changed_observation else lifecycle["source_state"]
        content, metadata = runtime.compile_review(
            {"dispatch": {**dispatch, "before_state": lifecycle["source_state"], "after_state": after_state}, "payload": payload}
        )
        Path(entry["artifact_path"]).write_bytes(content)
        Path(entry["metadata_path"]).write_text(json.dumps(metadata))
        runtime.append_journal_event(
            args.journal,
            lifecycle,
            runtime.JournalEventRequest(
                entry["node_id"], "blocked" if entry == blocked else "accepted", source=entry, reason="Dependency uncertainty" if entry == blocked else None
            ),
        )
    request = {
        **lifecycle,
        "artifact_store": str(tmp_path / "expanded"),
        "validation_requirements": [
            {
                **_late_validation_plan(),
                "source_state": lifecycle["source_state"],
                "requirement_id": item["requirement_id"],
                "commands": item["commands"],
                "working_directories": [item["working_directory"]],
                "environment": item["environment"],
                "expected_evidence": item["expected_evidence"],
            }
            for item in requirements
        ],
    }
    return request, args, dispatches, blocked


def test_repair_authorization_then_late_validation_preserves_blocked_audit_and_accepted_work(tmp_path: Path) -> None:
    request, args, dispatches, blocked = _fixture(tmp_path)
    lifecycle = {key: request[key] for key in ("plan", "source_state")}
    control = runtime.review_control(
        {**lifecycle, "action": "begin-repair", "authorization": "review-and-fix", "artifact_store": str(tmp_path / "control")}, args
    )
    assert control["status"] == "repair-authorized"
    assert control["repair_epoch"] == 1
    assert len(control["validation_reconciliation"]["requirements"]) == 2
    history = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    expanded = runtime.reconcile_validation_requirements(request, args)
    assert expanded["validation_reconciliation"]["blockers"] == []
    assert {item["requirement_id"] for item in expanded["validation_reconciliation"]["requirements"]} == {"doi-metadata", "native-platform"}
    revised = expanded["lifecycle_input"]
    journal = Path(expanded["journal_path"])
    plan = runtime._graph_plan(revised["plan"])
    entries = json.loads(Path(expanded["dispatches_path"]).read_bytes())
    _prepare_all_fixture_timing(entries)
    events, state, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(revised["source_state"]))
    assert state[blocked["node_id"]] == "blocked"
    assert next(item for item in entries["dispatches"] if item["node_id"] == blocked["node_id"]) == blocked
    retained = {item["node_id"] for item in dispatches["dispatches"] if item["dispatch"]["mode"] != "synthesis"}
    assert set(expanded["retained_node_ids"]) == retained
    assert expanded["retained_blocked_node_ids"] == [blocked["node_id"]]
    assert all(state[node] == "accepted" for node in retained - {blocked["node_id"]})
    ready = runtime.next_ready_nodes({**revised, "current_source_state": revised["source_state"]}, journal_events=events, dispatch_set=entries)
    assert len(ready["ready_dispatches"]) == 2
    assert all(item["dispatch"]["mode"] == "validation" for item in ready["ready_dispatches"])
    # Merely planning the resolution work must never promote the blocked audit.
    assert not ready["complete"]
    assert not any(item["dispatch"]["mode"] == "synthesis" for item in ready["ready_dispatches"])
    for entry in ready["ready_dispatches"]:
        _compile_repair_fixture_entry(entry, revised, journal)
    events, state, _head = runtime.read_execution_journal(journal, plan=plan, source_state=tuple(revised["source_state"]))
    final_ready = runtime.next_ready_nodes({**revised, "current_source_state": revised["source_state"]}, journal_events=events, dispatch_set=entries)
    assert state[blocked["node_id"]] == "blocked"
    assert not final_ready["complete"]
    assert blocked["node_id"] not in final_ready["ready_node_ids"]
    assert "repository-synthesis" not in final_ready["ready_node_ids"]
    assert revised["source_state"] == lifecycle["source_state"]
    assert all(path.read_bytes() == content for path, content in history.items())


@pytest.mark.parametrize("transition", ["in-flight", "awaiting-replan", "uncompiled-block"])
def test_expansion_does_not_relax_active_mutation_or_missing_evidence_guards(tmp_path: Path, transition: str) -> None:
    request, args, _dispatches, blocked = _fixture(tmp_path)
    lifecycle = {key: request[key] for key in ("plan", "source_state")}
    node = blocked["node_id"]
    status = "awaiting-replan" if transition == "awaiting-replan" else "invalidated"
    runtime.append_journal_event(args.journal, lifecycle, runtime.JournalEventRequest(node, status, reason="Fixture transition"))
    if transition != "awaiting-replan":
        runtime.append_journal_event(
            args.journal,
            lifecycle,
            runtime.JournalEventRequest(
                node, "in-flight" if transition == "in-flight" else "blocked", reason="No compiled evidence" if transition == "uncompiled-block" else None
            ),
        )
    with pytest.raises(ValueError, match=r"quiescent|compiled blocked"):
        runtime.reconcile_validation_requirements(request, args)
    assert not Path(request["artifact_store"]).exists()


@pytest.mark.parametrize("damage", ["source-observation", "evidence"])
def test_blocked_audit_must_have_unchanged_observations_and_verifiable_evidence(tmp_path: Path, damage: str) -> None:
    request, args, _dispatches, blocked = _fixture(tmp_path, changed_observation=damage == "source-observation")
    if damage == "evidence":
        path = Path(blocked["artifact_path"])
        path.write_bytes(path.read_bytes() + b"tampered\n")
    with pytest.raises(ValueError, match=r"unchanged source observations|digest|artifact"):
        runtime.reconcile_validation_requirements(request, args)
    assert not Path(request["artifact_store"]).exists()
