"""Applicable coverage survives truthful partial publication and archive classification."""

import json
from argparse import Namespace
from pathlib import Path
from typing import Any, cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_plan import plan_from_document
from test_review_graph_compact import _publish
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _compile_repair_fixture_entry,
    _complete_structural_fixture_routing,
    _set_fixture_routing,
)
from test_review_graph_transitions import _materialize, _payload

ACTIVE = ["docs/current.md", "docs/remaining.md"]
ARCHIVES = ["docs/archive/history.md", "docs/archive/CHANGELOG.md"]


@pytest.mark.parametrize("mode", ["baseline", "worktree"])
def test_rust_style_coverage_is_per_skill_and_focused_scope_stays_focused(tmp_path: Path, mode: str) -> None:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    paths = ["src/lib.rs", "tests/smoke.rs", "benches/common/helpers.rs", "examples/demo.rs"]
    for path in paths:
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pub fn demo() {}\n")
    capture = _scope_data(git, repository, mode, None, ())
    if mode == "worktree":
        template["routing_overrides"] = []
        template["consulted_routers"] = ["review-graph", "rust-review-orchestrator"]
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    document = bootstrap_document(capture, template)
    plan = plan_from_document(document, repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    style_id = dict(plan.requirement_to_node)["rust.style"]
    style = next(node for node in plan.actual_worker_nodes if node.node_id == style_id)
    assert set(style.coverage) == set(paths)
    _lifecycle, dispatches, _path = _materialize(tmp_path, capture, plan)
    assert set(next(item for item in dispatches["dispatches"] if item["node_id"] == style_id)["dispatch"]["owned_paths"]) == set(paths)
    # Other reviewers still own the missing paths; union coverage cannot discharge style.
    assert set(paths[2:]) <= {path for node in plan.actual_worker_nodes if node.node_id != style_id and node.mode == "audit" for path in node.coverage}
    override = next(item for item in document["routing_overrides"] if item["catalog_id"] == "rust.style")
    override["review_surface"] = paths[:2]
    narrowed = plan_from_document(document, repository_root=repository)
    if mode == "baseline":
        assert not narrowed.dispatch_allowed
        assert any("rust.style whole-repository coverage" in blocker and paths[2] in blocker and paths[3] in blocker for blocker in narrowed.blockers)
    else:
        assert narrowed.dispatch_allowed, narrowed.blockers
        assert next(node for node in narrowed.actual_worker_nodes if "rust.style" in node.requirement_ids).coverage == tuple(paths[:2])


def _fixture(
    tmp_path: Path, *, exclude_before: bool = False, citation_only_archives: bool = False
) -> tuple[dict[str, Any], Namespace, dict[str, Any], dict[str, Any], dict[str, Any]]:
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path, instructions=True)
    (repository / "AGENTS.md").write_text("Historical archives and generated changelog archives are excluded from citation maintenance.\n")
    for path in [*ACTIVE, *ARCHIVES]:
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Historical archive; retained for provenance\n" if path in ARCHIVES else "# Current scientific references\n")
    capture = _scope_data(git, repository, "baseline", None, ())
    _set_fixture_routing(
        template,
        {
            "catalog_id": "docs.citations",
            "disposition": "selected",
            "reason": "Audit active scientific references.",
            "applicability_evidence": ACTIVE,
            "review_surface": [*ACTIVE, *ARCHIVES],
            "owners": ["documentation"],
            "instruction_paths": ["AGENTS.md"],
        },
    )
    exclusions = [
        {
            "catalog_id": "docs.citations",
            "path": path,
            "reason": "Header designates historical content excluded by the citation policy.",
            "policy_source": "AGENTS.md",
        }
        for path in ARCHIVES
    ]
    if exclude_before:
        template["review_scope_exclusions"] = exclusions
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    if citation_only_archives:
        _set_fixture_routing(
            template,
            {
                "catalog_id": "repo.tooling",
                "disposition": "selected",
                "reason": "Inspect the active repository validation policy.",
                "applicability_evidence": ["AGENTS.md"],
                "review_surface": ["AGENTS.md"],
                "owners": ["tooling"],
            },
        )
        for override in template["routing_overrides"]:
            if override["catalog_id"] != "docs.citations":
                override["review_surface"] = [path for path in override.get("review_surface", []) if path not in ARCHIVES]
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    if citation_only_archives:
        assert [item.catalog_id for item in plan.routing_decisions if set(item.review_surface) & set(ARCHIVES)] == ["docs.citations"]
    lifecycle, dispatches, dispatch_path = _materialize(tmp_path, capture, plan)
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture))
    args = Namespace(dispatches=dispatch_path, current_capture=capture_path, journal=tmp_path / "execution.jsonl", output=tmp_path / "result.json")
    entry = next(item for item in dispatches["dispatches"] if "docs.citations" in item["dispatch"]["requirement_ids"])
    request = {
        **lifecycle,
        "artifact_store": str(tmp_path / "continued"),
        "node_id": entry["node_id"],
        "reason": "Finish applicable citation inspection without changing source.",
        "review_scope_exclusions": [{**item, "policy_source": str(repository / "AGENTS.md")} for item in exclusions],
    }
    return request, args, entry, dispatches, template


def _compile(entry: dict[str, Any], payload: dict[str, Any], lifecycle: dict[str, Any], args: Namespace) -> dict[str, Any]:
    _publish(entry, payload)
    runtime._compile_node_from_files(
        lifecycle,
        Namespace(
            dispatches=args.dispatches,
            journal=args.journal,
            node_id=entry["node_id"],
            before_capture=args.current_capture,
            after_capture=args.current_capture,
            payload=None,
            workspace_before=None,
            workspace_after=None,
            output=args.journal.parent / (entry["node_id"] + ".compiled.json"),
            status=None,
            limitation=["Partial inspection remains."] if payload["status"] == "blocked" else None,
        ),
    )
    return json.loads(Path(entry["metadata_path"]).read_bytes())["normalized_record"]


def _partial(entry: dict[str, Any], *, finding: bool = False) -> dict[str, Any]:
    payload = _payload([ACTIVE[0]], dispatch=entry["dispatch"])
    payload.update(
        status="blocked",
        scope_limitations=[{"path": path, "reason": "Not yet substantively inspected."} for path in entry["dispatch"]["owned_paths"] if path != ACTIVE[0]],
    )
    planned = entry["dispatch"]["command_policy"]["planned_validation_units"][0]
    payload["validation_requirements"] = [
        {
            "requirement_id": planned["requirement_ids"][0],
            "planned_validation_digest": planned["planned_validation_digest"],
            "owner": "review-validator",
            "reason": "Required repository gate.",
            "expected_evidence": "Checks pass.",
        }
    ]
    if finding:
        payload["findings"] = [
            {
                "severity": "P2",
                "location": ACTIVE[0] + ":1",
                "summary": "Missing primary citation",
                "evidence": "The active claim has no primary reference.",
                "remediation": "Add its primary source.",
            }
        ]
    return payload


def test_archive_exclusions_apply_before_dispatch_and_active_omissions_still_reject(tmp_path: Path) -> None:
    request, args, entry, dispatches, _template = _fixture(tmp_path, exclude_before=True)
    assert entry["dispatch"]["owned_paths"] == ACTIVE
    assert entry["dispatch"]["review_scope_exclusions"] == request["review_scope_exclusions"]
    assert any(set(ARCHIVES) <= set(item["dispatch"]["owned_paths"]) for item in dispatches["dispatches"] if item != entry)
    with pytest.raises(ValueError, match="inspection of every owned path"):
        _publish(entry, _payload([ACTIVE[0]], dispatch=entry["dispatch"]))
    record = _compile(entry, _payload(ACTIVE, dispatch=entry["dispatch"]), request, args)
    assert record["status"] == "no-findings"
    assert record["files_inspected"] == ACTIVE


@pytest.mark.parametrize("finding", [False, True])
@pytest.mark.parametrize("exclude_archives", [False, True])
def test_continuation_preserves_evidence_and_requires_remaining_inspection(tmp_path: Path, finding: bool, exclude_archives: bool) -> None:
    request, args, old, dispatches, _template = _fixture(tmp_path)
    if not exclude_archives:
        request["review_scope_exclusions"] = []
    payload = _partial(old, finding=finding)
    original = _compile(old, payload, request, args)
    validator = next(item for item in dispatches["dispatches"] if item["dispatch"]["mode"] == "validation")
    _compile_repair_fixture_entry(validator, request, args.journal)
    history = {
        path: path.read_bytes()
        for path in (args.journal, args.dispatches, *(Path(old[key]) for key in ("artifact_path", "metadata_path", "worker_payload_path")))
    }
    result = runtime.continue_partial_audit(request, args)
    assert runtime.continue_partial_audit(request, args) == result
    lifecycle = result["lifecycle_input"]
    for field in ("review_lifecycle", "worker_budget", "recovery_finalization_reserve", "coalesced_validation_units"):
        assert lifecycle["plan"][field] == request["plan"][field]
    assert result["retained_node_ids"] == [validator["node_id"]]
    entries = json.loads(Path(result["dispatches_path"]).read_bytes())
    new_id = result["audit_continuation"]["replacement_node_ids"][old["node_id"]]
    new = next(item for item in entries["dispatches"] if item["node_id"] == new_id)
    assert next(item for item in entries["dispatches"] if item["node_id"] == validator["node_id"]) == validator
    assert set(new["dispatch"]["owned_paths"]) == set(ACTIVE if exclude_archives else [*ACTIVE, *ARCHIVES])
    context = new["dispatch"]["coverage_reuse"]
    assert runtime.reused_paths(context) == (ACTIVE[0],)
    assert context["original_findings"] == original["findings"]
    assert context["original_validation_requirements"] == original["validation_requirements"]
    remaining = [path for unit in context["units"] if unit["disposition"] == "recheck" for path in unit["owned_paths"]]
    successor = _payload(remaining, dispatch=new["dispatch"])
    successor["validation_requirements"] = payload["validation_requirements"]
    successor["status"] = "completed" if finding else "no-findings"
    for invalid in ([ACTIVE[0], *remaining], remaining[1:]):
        with pytest.raises(ValueError, match=r"recheck|every owned path|scope limitation"):
            _publish(new, {**successor, "files_inspected": invalid})
    with pytest.raises(ValueError, match="validation requirements"):
        _publish(new, {**successor, "validation_requirements": []})
    record = _compile(
        new,
        successor,
        lifecycle,
        Namespace(dispatches=Path(result["dispatches_path"]), journal=Path(result["journal_path"]), current_capture=args.current_capture),
    )
    assert record["status"] == ("completed" if finding else "no-findings")
    assert record["files_inspected"] == remaining
    assert len(record["findings"]) == int(finding)
    if finding:
        assert record["findings"][0]["source_findings"] == [{"evidence_id": original["evidence_id"], "finding_id": original["findings"][0]["finding_id"]}]
    assert all(path.read_bytes() == content for path, content in history.items())
    with pytest.raises(ValueError, match="superseded"):
        runtime.append_journal_event(args.journal, request, runtime.JournalEventRequest(old["node_id"], "in-flight"))


@pytest.mark.parametrize("damage", ["source", "overlap", "missing-reason", "wrong-policy", "uncertainty", "in-flight", "stopped"])
def test_continuation_rejects_unsafe_or_incomplete_inputs(tmp_path: Path, damage: str) -> None:
    request, args, old, dispatches, _template = _fixture(tmp_path)
    payload = _partial(old)
    if damage == "uncertainty":
        payload["unresolved_uncertainties"] = [{"kind": "semantic", "reason": "Active source semantics remain uncertain."}]
    _compile(old, payload, request, args)
    if damage == "source":
        capture = json.loads(args.current_capture.read_bytes())
        capture["captured_worktree_fingerprint"] = "changed"
        args.current_capture.write_text(json.dumps(capture))
    elif damage == "overlap":
        request["review_scope_exclusions"][0]["path"] = ACTIVE[0]
    elif damage == "missing-reason":
        request["review_scope_exclusions"][0]["reason"] = ""
    elif damage == "wrong-policy":
        request["review_scope_exclusions"][0]["policy_source"] = "unbound.md"
    elif damage == "in-flight":
        other = next(item for item in dispatches["dispatches"] if item != old and item["dispatch"]["mode"] == "audit")
        runtime.append_journal_event(args.journal, request, runtime.JournalEventRequest(other["node_id"], "in-flight"))
    elif damage == "stopped":
        runtime.review_control(
            {
                "plan": request["plan"],
                "source_state": request["source_state"],
                "artifact_store": str(tmp_path / "stop"),
                "action": "stop",
                "reason": "User stopped this run.",
            },
            args,
        )
    with pytest.raises(ValueError, match=r"unchanged|omitted paths|scope exclusions|bound skill|uncertainties|quiescent|stopped"):
        runtime.continue_partial_audit(request, args)
    assert not Path(request["artifact_store"]).exists()


@pytest.mark.parametrize("progress", [False, True])
def test_repeated_partial_continuation_requires_progress_and_preserves_findings(tmp_path: Path, progress: bool) -> None:
    request, args, old, _dispatches, _template = _fixture(tmp_path)
    exclusions = request.pop("review_scope_exclusions")
    initial = _partial(old, finding=True)
    _compile(old, initial, request, args)
    first = runtime.continue_partial_audit(request, args)
    lifecycle = first["lifecycle_input"]
    entries = json.loads(Path(first["dispatches_path"]).read_bytes())
    new_id = first["audit_continuation"]["replacement_node_ids"][old["node_id"]]
    new = next(item for item in entries["dispatches"] if item["node_id"] == new_id)
    next_args = Namespace(dispatches=Path(first["dispatches_path"]), journal=Path(first["journal_path"]), current_capture=args.current_capture)
    payload = _payload([ACTIVE[1]] if progress else [], dispatch=new["dispatch"])
    payload.update(
        status="blocked",
        validation_requirements=initial["validation_requirements"],
        scope_limitations=[{"path": path, "reason": "Inspection remains outstanding."} for path in (ARCHIVES if progress else [*ARCHIVES, ACTIVE[1]])],
    )
    _compile(new, payload, lifecycle, next_args)
    next_request = {**lifecycle, "node_id": new_id, "artifact_store": str(tmp_path / "second"), "reason": "Finish the remaining scope."}
    if not progress:
        with pytest.raises(ValueError, match="requires progress"):
            runtime.continue_partial_audit(next_request, next_args)
        return
    second = runtime.continue_partial_audit({**next_request, "review_scope_exclusions": exclusions}, next_args)
    final_id = second["audit_continuation"]["replacement_node_ids"][new_id]
    final_entry = next(item for item in json.loads(Path(second["dispatches_path"]).read_bytes())["dispatches"] if item["node_id"] == final_id)
    assert runtime.reused_paths(final_entry["dispatch"]["coverage_reuse"]) == tuple(ACTIVE)
    assert all(unit["disposition"] == "reused" for unit in final_entry["dispatch"]["coverage_reuse"]["units"])
    final_payload = _payload([], dispatch=final_entry["dispatch"])
    final_payload.update(status="completed", validation_requirements=initial["validation_requirements"])
    record = _compile(
        final_entry,
        final_payload,
        second["lifecycle_input"],
        Namespace(dispatches=Path(second["dispatches_path"]), journal=Path(second["journal_path"]), current_capture=args.current_capture),
    )
    assert record["files_inspected"] == []
    assert [finding["location"] for finding in record["findings"]] == [ACTIVE[0] + ":1"]
    assert len(second["lifecycle_input"]["plan"]["audit_continuations"]) == 2


def test_late_exclusions_reconcile_global_inventory_without_false_owned_coverage(tmp_path: Path) -> None:
    request, args, old, _dispatches, _template = _fixture(tmp_path, citation_only_archives=True)
    _compile(old, _partial(old), request, args)
    with pytest.raises(ValueError, match="captured_path_dispositions"):
        runtime.continue_partial_audit(request, args)
    request["captured_path_dispositions"] = [
        {
            "paths": ARCHIVES,
            "disposition": "archive",
            "reason": "Only historical citation artifacts; no remaining active maintenance contract.",
            "catalog_ids": [],
        }
    ]
    result = runtime.continue_partial_audit(request, args)
    inventory = result["lifecycle_input"]["plan"]["captured_path_inventory"]
    assert inventory["unassessed_captured_paths"] == []
    assert set(ARCHIVES) <= set(inventory["unassigned_captured_paths"])
    assert any(set(item["paths"]) == set(ARCHIVES) and item["disposition"] == "archive" for item in inventory["dispositions"])


@pytest.mark.parametrize("remove_archive", [False, True])
@pytest.mark.parametrize("template_exclusions", [False, True])
@pytest.mark.parametrize("changed_path", [ACTIVE[0], "state.rs"])
def test_mutation_after_partial_continuation_retains_applicable_exclusions(
    tmp_path: Path, *, remove_archive: bool, template_exclusions: bool, changed_path: str
) -> None:
    request, args, old, _dispatches, template = _fixture(tmp_path)
    payload = _partial(old)
    _compile(old, payload, request, args)
    continued = runtime.continue_partial_audit(request, args)
    lifecycle = continued["lifecycle_input"]
    entries = json.loads(Path(continued["dispatches_path"]).read_bytes())
    new = next(item for item in entries["dispatches"] if "docs.citations" in item["dispatch"]["requirement_ids"])
    successor = _payload([ACTIVE[1]], dispatch=new["dispatch"])
    successor["validation_requirements"] = payload["validation_requirements"]
    _compile(
        new,
        successor,
        lifecycle,
        Namespace(dispatches=Path(continued["dispatches_path"]), journal=Path(continued["journal_path"]), current_capture=args.current_capture),
    )
    previous_capture = json.loads(args.current_capture.read_bytes())
    repository = Path(previous_capture["repository_root"])
    (repository / changed_path).write_text("# Updated current scientific references\n" if changed_path in ACTIVE else "pub fn state() { assert!(true); }\n")
    if remove_archive:
        (repository / ARCHIVES[1]).unlink()
        for override in template["routing_overrides"]:
            override["review_surface"] = [path for path in override.get("review_surface", []) if path != ARCHIVES[1]]
    expected = [dict(item) for item in request["review_scope_exclusions"] if not remove_archive or item["path"] != ARCHIVES[1]]
    if template_exclusions:
        expected[0]["reason"] = "The current planning policy still excludes this historical citation archive."
        tooling = next(item for item in lifecycle["plan"]["routing_decisions"] if item["catalog_id"] == "repo.tooling")
        expected.append({**expected[0], "catalog_id": "repo.tooling", "policy_source": tooling["skill_path"]})
        template["review_scope_exclusions"] = [dict(expected[0]), dict(expected[-1])]
    original_template = json.dumps(template, sort_keys=True)
    original_plan = json.dumps(lifecycle["plan"], sort_keys=True)
    advanced = runtime.advance_after_mutation(
        {
            **lifecycle,
            "previous_capture": previous_capture,
            "new_capture": _scope_data("git", repository, "baseline", None, ()),
            "changed_paths": [changed_path, *([ARCHIVES[1]] if remove_archive else [])],
            "planning_template": template,
            "authorization_before": "review-only",
            "authorization_after": "review-and-fix",
            "repair_epoch": 1,
            "artifact_store": str(tmp_path / "after-continuation-repair"),
            "state_verification_command": "capture_scope.py --mode baseline",
            "journal_path": continued["journal_path"],
            "dispatches_path": continued["dispatches_path"],
        }
    )
    assert advanced["lifecycle_input"]["plan"]["review_scope_exclusions"] == expected
    if changed_path in ACTIVE:
        citations = next(item["dispatch"] for item in advanced["dispatch_set"]["dispatches"] if "docs.citations" in item["dispatch"]["requirement_ids"])
        assert citations["owned_paths"] == ACTIVE
        assert citations["review_scope_exclusions"] == [item for item in expected if item["catalog_id"] == "docs.citations"]
    else:
        assert new["dispatch"]["evidence_id"] in advanced["reused_evidence_ids"]
        reused = next(item for item in advanced["lifecycle_input"]["plan"]["reused_review_identities"] if item["requirement_id"] == "docs.citations")
        assert reused["planned_paths"] == ACTIVE
    tooling_dispatch = next(item["dispatch"] for item in advanced["dispatch_set"]["dispatches"] if "repo.tooling" in item["dispatch"]["requirement_ids"])
    assert (ARCHIVES[0] in tooling_dispatch["owned_paths"]) is not template_exclusions
    if remove_archive:
        assert all(ARCHIVES[1] not in item["dispatch"]["owned_paths"] for item in advanced["dispatch_set"]["dispatches"])
    assert advanced["lifecycle_input"]["plan"]["audit_continuations"] == lifecycle["plan"]["audit_continuations"]
    assert json.dumps(template, sort_keys=True) == original_template
    assert json.dumps(lifecycle["plan"], sort_keys=True) == original_plan
