"""Repairs converge, pending CI does not fan out, and stopped work stays stopped."""

import json
from argparse import Namespace
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_lifecycle import ReviewLifecycle, lifecycle_from_document
from review_graph_plan import plan_from_document
from test_review_graph_commit import _commit_fixture, _save
from test_review_graph_runtime import _baseline_mutation_fixture
from test_review_graph_transitions import _materialize, _payload


def _control_args(tmp_path: Path, result: dict[str, Any]) -> Namespace:
    return Namespace(
        journal=Path(result["journal_path"]),
        dispatches=Path(result["dispatches_path"]),
        current_capture=Path(result.get("current_capture_path", result.get("capture_path"))),
        output=tmp_path / "control-result.json",
    )


def _two_repairs(tmp_path: Path) -> tuple[dict[str, Any], Namespace]:
    git, repository, template, capture, plan = _baseline_mutation_fixture(tmp_path)
    lifecycle, _entries, _dispatches = _materialize(tmp_path, capture, plan)
    result: dict[str, Any] = {}
    for ordinal in (1, 2):
        (repository / "tool.py").write_text(f"value = {ordinal + 1}\n")
        new_capture = _scope_data(git, repository, "baseline", None, ())
        result = runtime.advance_after_mutation(
            {
                **lifecycle,
                "previous_capture": capture,
                "new_capture": new_capture,
                "planning_template": template,
                "changed_paths": ["tool.py"],
                "authorization_before": "review-and-fix",
                "authorization_after": "review-and-fix",
                "repair_epoch": ordinal,
                "artifact_store": str(tmp_path / "repairs"),
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )
        lifecycle = result["lifecycle_input"]
        capture = new_capture
    return result, _control_args(tmp_path, result)


def test_optional_finding_cascade_stops_before_third_source_batch(tmp_path: Path) -> None:
    result, args = _two_repairs(tmp_path)
    lifecycle = result["lifecycle_input"]
    audit = next(entry for entry in result["dispatch_set"]["dispatches"] if entry["dispatch"]["mode"] == "audit")
    payload = _payload(audit["dispatch"]["owned_paths"])
    payload.update(
        status="completed",
        findings=[
            {
                "severity": "P3",
                "location": audit["dispatch"]["owned_paths"][0] + ":1",
                "summary": "Additional optional cleanup",
                "evidence": "Verification discovered a low-priority naming improvement",
                "remediation": "Rename the local value",
            }
        ],
    )
    source = _save(audit, lifecycle, args.journal, payload)
    original = {path: Path(path).read_bytes() for path in source.values()}
    request = {**lifecycle, "action": "begin-repair", "authorization": "review-and-fix", "artifact_store": str(tmp_path / "control")}
    stopped = runtime.review_control(request, args)
    assert stopped["status"] == "stopped"
    assert stopped["stop_reason"].startswith("repair-budget-exhausted")
    assert stopped["remaining_findings"][0]["findings"][0]["severity"] == "P3"
    assert stopped["incomplete_node_ids"]
    assert stopped["graph_proof_status"] == "partial"
    assert all(Path(path).read_bytes() == content for path, content in original.items())
    assert args.journal.with_name(args.journal.name + ".stop.json").is_file()
    with pytest.raises(ValueError, match="review stopped"):
        runtime.review_control(request, args)
    plan = runtime._graph_plan(stopped["lifecycle_input"]["plan"])
    events, _state, _head = runtime.read_execution_journal(Path(stopped["journal_path"]), plan=plan, source_state=tuple(lifecycle["source_state"]))
    ready = runtime.next_ready_nodes(
        {**stopped["lifecycle_input"], "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=stopped["dispatch_set"]
    )
    assert ready["ready_dispatches"] == []
    assert not ready["complete"]
    extended = runtime.review_control(
        {
            **stopped["lifecycle_input"],
            "action": "extend-budget",
            "additional_epochs": 1,
            "user_authorization": "Fix that deferred optional finding; one more batch.",
            "artifact_store": str(tmp_path / "extension"),
        },
        _control_args(tmp_path, stopped),
    )
    assert extended["review_lifecycle"]["repairs_completed"] == 2
    assert extended["review_lifecycle"]["repair_budget"] == 3
    authorized = runtime.review_control(
        {**extended["lifecycle_input"], "action": "begin-repair", "authorization": "review-and-fix", "artifact_store": str(tmp_path / "next-control")},
        _control_args(tmp_path, extended),
    )
    assert authorized["repair_epoch"] == 3


@pytest.mark.parametrize("ordinal", [0, 1, 4, True])
def test_epoch_number_cannot_reset_skip_or_coerce_budget(ordinal: int) -> None:
    with pytest.raises(ValueError, match="consecutive"):
        ReviewLifecycle(repairs_completed=2).next_repair(ordinal)


def test_mutation_transition_cannot_bypass_exhausted_budget(tmp_path: Path) -> None:
    result, _args = _two_repairs(tmp_path)
    request = {
        **result["lifecycle_input"],
        "previous_capture": result["capture"],
        "new_capture": {**result["capture"], "scope_fingerprint": "changed"},
        "planning_template": {},
        "authorization_before": "review-and-fix",
        "authorization_after": "review-and-fix",
        "repair_epoch": 3,
        "artifact_store": str(tmp_path / "exhausted"),
    }
    stopped = runtime.advance_after_mutation(request)
    assert stopped["status"] == "stopped"
    assert stopped["graph_proof_status"] == "partial"
    assert Path(stopped["stop_path"]).is_file()
    assert not (tmp_path / "exhausted" / "repair-epoch-003").exists()


def test_user_stop_returns_active_cancellations_and_never_restarts_workers(tmp_path: Path) -> None:
    _git, _repository, _template, capture, plan = _baseline_mutation_fixture(tmp_path)
    lifecycle, entries, dispatches = _materialize(tmp_path, capture, plan)
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture))
    args = Namespace(journal=tmp_path / "execution.jsonl", dispatches=dispatches, current_capture=capture_path, output=tmp_path / "stop.json")
    ready = runtime.next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=(), dispatch_set=entries)
    active = ready["ready_node_ids"][:2]
    for node_id in active:
        runtime.append_journal_event(args.journal, lifecycle, runtime.JournalEventRequest(node_id, "in-flight"))
    stopped = runtime.review_control({**lifecycle, "action": "stop", "reason": "Stop spending tokens now.", "artifact_store": str(tmp_path / "stop")}, args)
    assert stopped["cancel_node_ids"] == sorted(active)
    assert stopped["graph_proof_status"] == "partial"
    for current, current_args in ((lifecycle, args), (stopped["lifecycle_input"], _control_args(tmp_path, stopped))):
        with pytest.raises(ValueError, match="review stopped"):
            runtime.append_journal_event(current_args.journal, current, runtime.JournalEventRequest(ready["ready_node_ids"][-1], "in-flight"))
        with pytest.raises(ValueError, match="review stopped"):
            runtime.fallback_to_coordinator(
                {**current, "worker_created": False, "node_id": ready["ready_node_ids"][-1], "artifact_store": str(tmp_path / "fallback")}, current_args
            )
        schedule = runtime.schedule_ready(
            {
                **current,
                "artifact_store": str(tmp_path / "schedule"),
                "worker_capacity": {"active_workers": 0, "concurrent_worker_limit": 4, "source": "fixture"},
            },
            current_args,
        )
        assert schedule["ready_dispatches"] == []
        assert not schedule["complete"]
    proof = runtime.finalize_proof({**stopped["lifecycle_input"], "current_source_state": lifecycle["source_state"], "sources": []})
    assert proof["graph_proof_status"] != "complete"
    assert any("user-stop" in blocker for blocker in proof["blockers"])
    with pytest.raises(ValueError, match="user-stop"):
        runtime.review_control(
            {
                **stopped["lifecycle_input"],
                "action": "extend-budget",
                "additional_epochs": 1,
                "user_authorization": "One more repair",
                "artifact_store": str(tmp_path / "extension"),
            },
            _control_args(tmp_path, stopped),
        )


def test_branch_handoff_waits_for_exact_commit_ci_without_audit_fanout(tmp_path: Path) -> None:
    request, _entries, _sources = _commit_fixture(tmp_path, mode="branch")
    result = runtime.resume_after_authorized_commit(request)
    assert request["previous_capture"]["merge_base"] != request["previous_capture"]["head"]
    lifecycle = {**result["lifecycle_input"], "current_source_state": result["current_source_state"]}
    plan = runtime._graph_plan(lifecycle["plan"])
    events, _state, _head = runtime.read_execution_journal(Path(result["journal_path"]), plan=plan, source_state=tuple(lifecycle["source_state"]))
    ready = runtime.next_ready_nodes(lifecycle, journal_events=events, dispatch_set=result["dispatch_set"])
    assert ready["ready_node_ids"] == list(request["native_ci"])
    assert all(entry["dispatch"]["mode"] == "validation" for entry in ready["ready_dispatches"])
    assert not ready["complete"]


@pytest.mark.parametrize("trigger", ["pending-ci", "incomplete-proof", "published-fixes"])
def test_bookkeeping_cannot_authorize_comprehensive_restart(tmp_path: Path, trigger: str) -> None:
    result, args = _two_repairs(tmp_path)
    request = {
        **result["lifecycle_input"],
        "action": "authorize-restart",
        "restart_trigger": {"trigger": trigger, "evidence": "No new confirmed defect", "targeted_verification_insufficient": "Finish bookkeeping"},
        "artifact_store": str(tmp_path / "restart"),
    }
    with pytest.raises(ValueError, match="schema"):
        runtime.review_control(request, args)
    assert not (tmp_path / "restart").exists()


def test_explicit_restart_and_extension_preserve_run_wide_limits(tmp_path: Path) -> None:
    result, args = _two_repairs(tmp_path)
    request = {
        **result["lifecycle_input"],
        "action": "authorize-restart",
        "restart_trigger": {
            "trigger": "explicit-user-request",
            "evidence": "Run another full review of this source.",
            "targeted_verification_insufficient": "User requests exhaustive reinspection.",
        },
        "artifact_store": str(tmp_path / "restart"),
    }
    authorized = runtime.review_control(request, args)
    assert authorized["review_lifecycle"]["repairs_completed"] == 2
    assert authorized["review_lifecycle"]["repair_budget"] == 2
    assert len(authorized["review_lifecycle"]["comprehensive_restarts"]) == 1
    assert "ready_dispatches" not in authorized
    damaged = deepcopy(authorized["review_lifecycle"])
    damaged["repair_budget"] = 20
    with pytest.raises(ValueError, match="extension history"):
        lifecycle_from_document(damaged)
    assert lifecycle_from_document(asdict(ReviewLifecycle())).repair_budget == 2


def test_planner_cannot_restart_an_existing_run_without_a_trigger() -> None:
    lifecycle = asdict(ReviewLifecycle(repairs_completed=1))
    with pytest.raises(ValueError, match="existing review lifecycle"):
        plan_from_document({"review_lifecycle": lifecycle})
    with pytest.raises(ValueError, match="recorded concrete trigger"):
        plan_from_document({"review_lifecycle": lifecycle, "planning_purpose": "comprehensive-restart"})
    lifecycle["stop_reason"] = "user-stop: enough"
    with pytest.raises(ValueError, match="review stopped"):
        plan_from_document({"review_lifecycle": lifecycle, "planning_purpose": "repair-verification"})


def test_review_control_cli_publishes_cancellation_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result, args = _two_repairs(tmp_path)
    request = {**result["lifecycle_input"], "action": "stop", "reason": "Stop now", "artifact_store": str(tmp_path / "control")}
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request))
    assert (
        runtime.main(
            [
                "review-control",
                "--input",
                str(input_path),
                "--journal",
                str(args.journal),
                "--dispatches",
                str(args.dispatches),
                "--current-capture",
                str(args.current_capture),
                "--output",
                str(args.output),
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "stopped"
    assert receipt["graph_proof_status"] == "partial"
    assert receipt["stop_reason"] == "user-stop: Stop now"
    assert receipt["incomplete_node_ids"]
    assert Path(receipt["continuation"]["path"]).is_file()
