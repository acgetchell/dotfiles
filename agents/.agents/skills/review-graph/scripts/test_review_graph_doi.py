"""DOI reconciliation preserves failed executions while allowing verified readiness."""

import base64
import json
import shlex
from argparse import Namespace
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from review_graph_doi import captured_software_inputs, validate_software_doi_resolution
from review_graph_doi_gate import SoftwareDoiRecheck
from review_graph_integrity import canonical_json, digest_bytes, digest_json
from review_graph_phases import pending_validation_barrier
from review_graph_plan import GraphPlan, plan_from_document
from review_graph_reuse import source_snapshot
from review_graph_runtime import (
    JournalEventRequest,
    _graph_plan,
    _journal_evidence,
    _software_doi_recheck_ids,
    append_journal_event,
    build_synthesis_bundle,
    capture_workspace_snapshot,
    compile_review,
    compile_validation,
    main,
    materialize_dispatches,
    next_ready_nodes,
    read_execution_journal,
    reconcile_validation_requirements,
    recover_validation_execution,
    recover_validation_launch,
)
from review_graph_schema import SchemaValidationError, require_schema, require_schema_definition
from review_graph_synthesis import validate_synthesis
from test_support_review_graph import ROUTING_CATALOG, SCHEMA_ROOT, SKILL_ROOT, _json_plan, _prepare_all_fixture_timing, _sparse_plan_document
from test_support_review_graph_capture import _capture, _commit_all, _init_repo
from test_support_review_graph_doi import CFF_CONTENT, _fixture, _requirement, _save_report, _source_capture
from test_support_review_graph_evidence import _synthesis_payload
from test_support_review_graph_lifecycle import _compile_repair_fixture_entry
from test_support_review_graph_recovery import _block_validator


@pytest.mark.parametrize("legacy", [False, True])
def test_synthesis_reconciles_canonical_software_without_rewriting_failure(tmp_path: Path, legacy: bool) -> None:
    original, verified, resolution = _fixture(tmp_path)
    if legacy:
        path = Path(original["artifacts"][0]["path"])
        rows = json.loads(path.read_bytes())
        rows[0]["status"] = "MISMATCH"
        del rows[0]["source"]
        original["artifacts"] = [_save_report(path, rows)]
    records = [original, verified]
    bundle = {"records": records, "plan_context": {"routing_catalog_closed": True}}
    payload = {
        "status": "no-findings",
        "findings": [],
        "readiness_verdict": "ready",
        "predecessor_coverage": [
            {"evidence_id": record["evidence_id"], "requirement_ids": record["requirement_ids"], "disposition": "accepted"} for record in records
        ],
        "routing_closure": {"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
        "validation_reconciliation": [
            {"evidence_id": record["evidence_id"], "requirement_ids": record["requirement_ids"], "result": record["status"], "execution_mode": "native"}
            for record in records
        ],
    }
    predecessors = tuple(record["evidence_id"] for record in records)
    with pytest.raises(ValueError, match="ready synthesis"):
        validate_synthesis(payload, predecessors, bundle)
    payload["validation_reconciliation"][0]["software_doi_resolution"] = resolution
    before = deepcopy(records)
    with pytest.raises(ValueError, match="ready synthesis"):
        validate_synthesis(payload, predecessors)
    validate_synthesis(payload, predecessors, bundle)
    assert records == before
    assert payload["validation_reconciliation"][0]["result"] == "failed"
    assert original["executions"][0]["exit_code"] == 1


@pytest.mark.parametrize("mixed_digests", [False, True])
def test_resolution_requires_one_captured_cff_digest_across_rows(tmp_path: Path, mixed_digests: bool) -> None:
    original, verified, resolution = _fixture(tmp_path)
    for record in (original, verified):
        path = Path(record["artifacts"][0]["path"])
        rows = json.loads(path.read_bytes())
        rows.append({**deepcopy(rows[0]), "line": 5})
        if record is verified and mixed_digests:
            rows[1]["canonical_software"]["digest"] = "sha256:" + "c" * 64
        record["artifacts"] = [_save_report(path, rows)]
    # Readiness uses the captured reports, not current on-disk CFF bytes.
    (tmp_path / "CITATION.cff").write_text("changed since the captured validation")
    records = {verified["evidence_id"]: verified}
    if mixed_digests:
        with pytest.raises(ValueError, match="canonical metadata digest"):
            validate_software_doi_resolution(resolution, original, records)
    else:
        validate_software_doi_resolution(resolution, original, records)


def _validate_recheck_path(path: str) -> None:
    """Check a proposed original-report path against the reconciliation input schema."""
    require_schema_definition(
        {
            "plan": {},
            "source_state": ["scope", "worktree", "repository"],
            "software_doi_rechecks": [{"requirement_id": "canonical", "evidence_id": "validation:old", "execution_index": 0, "original_report": path}],
        },
        SCHEMA_ROOT / "runtime-operation-inputs-v1.schema.json",
        "reconcile-validation-requirements",
    )


@pytest.mark.parametrize("path", ["/proof/report.json", "C:/proof/report.json", r"C:\proof\report.json", r"\\server\share\report.json"])
def test_recheck_schema_accepts_absolute_report_paths(path: str) -> None:
    _validate_recheck_path(path)


@pytest.mark.parametrize("path", ["", "report.json", "./report.json", "../report.json", "~/report.json", "C:report.json", r"\report.json", r"\\server"])
def test_recheck_schema_rejects_relative_report_paths(path: str) -> None:
    with pytest.raises(SchemaValidationError, match="original_report"):
        _validate_recheck_path(path)


@pytest.mark.parametrize("defect", ["absent", "wrong-bytes", "missing-bytes", "invalid-base64", "stale-capture"])
def test_cff_binding_rejects_missing_or_unproven_captured_bytes(tmp_path: Path, defect: str) -> None:
    _original, verified, _resolution = _fixture(tmp_path)
    capture = _source_capture(tmp_path)
    path = Path(verified["artifacts"][0]["path"])
    rows = json.loads(path.read_bytes())
    if defect == "absent":
        capture["repository_path_fingerprints"] = {}
    elif defect == "stale-capture":
        capture["scope_fingerprint"] = "d" * 64
    elif defect == "missing-bytes":
        del rows[0]["canonical_software"]["content_base64"]
    else:
        rows[0]["canonical_software"]["content_base64"] = "!" if defect == "invalid-base64" else base64.b64encode(b"different bytes").decode("ascii")
    capture["repository_state_fingerprint"] = source_snapshot(capture).computed_fingerprint()
    if defect != "stale-capture":
        verified["observed_source_state"] = list(source_snapshot(capture).source_state)
    verified["artifacts"] = [_save_report(path, rows)]
    if defect == "stale-capture":
        with pytest.raises(ValueError, match="software DOI reconciliation"):
            captured_software_inputs(verified, capture)
    else:
        assert captured_software_inputs(verified, capture) == {}


@pytest.mark.parametrize("unproven_first", [False, True])
def test_one_proven_row_cannot_override_an_unproven_cff_row(tmp_path: Path, unproven_first: bool) -> None:
    original, verified, resolution = _fixture(tmp_path)
    for record in (original, verified):
        path = Path(record["artifacts"][0]["path"])
        rows = json.loads(path.read_bytes())
        rows.append({**deepcopy(rows[0]), "line": 5})
        if record is verified:
            del rows[0 if unproven_first else 1]["canonical_software"]["content_base64"]
        record["artifacts"] = [_save_report(path, rows)]
    verified["captured_software_inputs"] = captured_software_inputs(verified, _source_capture(tmp_path))
    assert verified["captured_software_inputs"] == {}
    with pytest.raises(ValueError, match="captured CFF bytes"):
        validate_software_doi_resolution(resolution, original, {verified["evidence_id"]: verified})


@pytest.mark.parametrize("defect", ["missing-binding", "wrong-digest"])
def test_resolution_requires_the_digest_of_captured_cff_bytes(tmp_path: Path, defect: str) -> None:
    original, verified, resolution = _fixture(tmp_path)
    if defect == "missing-binding":
        del verified["captured_software_inputs"]
    else:
        path = Path(verified["artifacts"][0]["path"])
        rows = json.loads(path.read_bytes())
        rows[0]["canonical_software"]["digest"] = "sha256:" + "f" * 64
        verified["artifacts"] = [_save_report(path, rows)]
    with pytest.raises(ValueError, match="captured"):
        validate_software_doi_resolution(resolution, original, {verified["evidence_id"]: verified})


def test_cff_binding_uses_actual_capture_after_current_file_is_removed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "CITATION.cff").write_bytes(CFF_CONTENT)
    _commit_all(repo)
    capture = _capture(repo, "baseline")
    _original, verified, _resolution = _fixture(repo)
    verified["observed_source_state"] = list(source_snapshot(capture).source_state)
    (repo / "CITATION.cff").unlink()
    assert captured_software_inputs(verified, capture) == {str(repo / "CITATION.cff"): "sha256:" + sha256(CFF_CONTENT).hexdigest()}


@pytest.mark.parametrize("redirect", [">", "1>", None, "unbound"])
def test_canonical_compilation_preserves_results_with_unrelated_reports(tmp_path: Path, redirect: str | None) -> None:
    _original, verified, _resolution = _fixture(tmp_path)
    report = Path(verified["artifacts"][0]["path"])
    canonical = _save_report(tmp_path / "canonical report.json", json.loads(report.read_bytes()))
    unrelated = _save_report(tmp_path / "summary.json", [{"summary": "check completed"}])
    verified["artifacts"] = [canonical] if redirect == "unbound" else [unrelated, canonical]
    execution = verified["executions"][0]
    execution["artifact_paths"] = [artifact["path"] for artifact in verified["artifacts"]]
    if redirect is not None:
        target = "missing.json" if redirect == "unbound" else canonical["path"] if redirect == "1>" else "canonical report.json"
        execution["command"] += f" {'>' if redirect == 'unbound' else redirect} {shlex.quote(target)}"
    planning = _sparse_plan_document()
    planning["validation_requirements"] = [_requirement(verified, baseline=True)]
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
    lifecycle = {"plan": _json_plan(plan), "source_state": verified["observed_source_state"]}
    materialized = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "artifacts"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    entry = next(item for item in materialized["dispatches"] if item["result_contract"] == "compact-validation")
    source = _compile_validator(entry, lifecycle, tmp_path / "journal.json", verified)
    record = json.loads(Path(source["metadata_path"]).read_bytes())["normalized_record"]
    assert record["status"] == "passed"
    assert record["executions"] == verified["executions"]
    if redirect in {">", "1>"}:
        assert record["captured_software_inputs"] == {str(tmp_path / "CITATION.cff"): "sha256:" + sha256(CFF_CONTENT).hexdigest()}
    else:
        assert "captured_software_inputs" not in record


def test_identified_canonical_report_still_requires_unchanged_bytes(tmp_path: Path) -> None:
    _original, verified, _resolution = _fixture(tmp_path)
    verified["executions"][0]["command"] += " > verified.json"
    Path(verified["artifacts"][0]["path"]).write_text("changed report")
    with pytest.raises(ValueError, match="report bytes changed"):
        captured_software_inputs(verified, _source_capture(tmp_path))


@pytest.mark.parametrize("content", [b"invalid json", b"\xff", b"[]", b"[{}]"])
@pytest.mark.parametrize("valid_report", [False, True])
def test_unusable_canonical_report_does_not_discard_other_execution_evidence(tmp_path: Path, content: bytes, valid_report: bool) -> None:
    _original, verified, _resolution = _fixture(tmp_path)
    path = tmp_path / "unusable.json"
    path.write_bytes(content)
    artifact = {**verified["artifacts"][0], "path": str(path), "artifact_digest": "sha256:" + sha256(content).hexdigest()}
    execution = {**verified["executions"][0], "artifact_paths": [str(path)]}
    verified["artifacts"] = [artifact, *verified["artifacts"]] if valid_report else [artifact]
    verified["executions"] = [execution, *verified["executions"]] if valid_report else [execution]
    before = deepcopy(verified)
    expected = {str(tmp_path / "CITATION.cff"): "sha256:" + sha256(CFF_CONTENT).hexdigest()} if valid_report else {}
    assert captured_software_inputs(verified, _source_capture(tmp_path)) == expected
    assert verified == before


@pytest.mark.parametrize(
    "defect",
    [
        "stale-source",
        "failed-verification",
        "unknown-verification",
        "missing-report",
        "changed-report",
        "non-doi-command",
        "other-markdown",
        "no-cff",
        "missing-command",
        "duplicate-command",
        "extra-failure",
        "unexecuted",
        "wrong-exit",
        "compound-command",
    ],
)
def test_resolution_rejects_invalid_execution_provenance(tmp_path: Path, defect: str) -> None:  # noqa: C901, PLR0912
    original, verified, resolution = _fixture(tmp_path)
    check = resolution["checks"][0]
    if defect == "stale-source":
        verified["observed_source_state"][1] = "changed"
    elif defect == "failed-verification":
        verified["status"] = "failed"
    elif defect == "unknown-verification":
        check["verification_evidence_id"] = "missing"
    elif defect == "missing-report":
        Path(check["original_report"]).unlink()
    elif defect == "changed-report":
        Path(check["verification_report"]).write_text("[]")
    elif defect == "non-doi-command":
        original["executions"][0]["command"] = "false"
    elif defect == "other-markdown":
        verified["executions"][0]["command"] = verified["executions"][0]["command"].replace("README.md", "OTHER.md")
    elif defect == "no-cff":
        verified["executions"][0]["command"] = original["executions"][0]["command"]
    elif defect == "missing-command":
        resolution["checks"] = []
    elif defect == "duplicate-command":
        resolution["checks"].append(deepcopy(check))
    elif defect == "extra-failure":
        original["executions"].append(deepcopy(original["executions"][0]))
    elif defect == "unexecuted":
        original["executions"].append({"result": "not-run"})
    elif defect == "compound-command":
        original["executions"][0]["command"] = "false && " + original["executions"][0]["command"]
    else:
        original["executions"][0]["exit_code"] = 2
    with pytest.raises(ValueError, match="software DOI reconciliation"):
        validate_software_doi_resolution(resolution, original, {verified["evidence_id"]: verified})


@pytest.mark.parametrize(
    "defect",
    [
        "contradiction",
        "wrong-doi",
        "wrong-title",
        "wrong-year",
        "wrong-author",
        "missing-author",
        "missing-occurrence",
        "extra-occurrence",
        "different-resolved-identity",
        "changed-source",
        "missing-canonical",
        "failed-row",
        "resolver-failure",
        "malformed-source",
        "punctuation-doi",
    ],
)
def test_resolution_rejects_unverified_or_contradictory_metadata(tmp_path: Path, defect: str) -> None:  # noqa: C901, PLR0912
    original, verified, resolution = _fixture(tmp_path)
    path = Path(verified["artifacts"][0]["path"])
    rows = json.loads(path.read_bytes())
    row = rows[0]
    if defect == "contradiction":
        row["local_status"] = "MISMATCH"
    elif defect in {"wrong-doi", "wrong-title", "wrong-year"}:
        row["canonical_software"][defect.removeprefix("wrong-")] = "wrong"
    elif defect == "wrong-author":
        row["canonical_software"]["authors"] = ["Someone"]
    elif defect == "missing-author":
        row["canonical_software"]["authors"] = []
    elif defect == "missing-occurrence":
        rows = []
    elif defect == "extra-occurrence":
        rows.append({**row, "line": 4})
    elif defect == "different-resolved-identity":
        row["resolved_title"] = "Other title"
    elif defect == "changed-source":
        row["source"]["digest"] = "sha256:" + "c" * 64
    elif defect == "missing-canonical":
        del row["canonical_software"]
    elif defect == "failed-row":
        row["status"] = "MISMATCH"
    elif defect == "malformed-source":
        row["source"] = []
    elif defect == "punctuation-doi":
        row["canonical_software"]["doi"] = row["doi"].replace(".", "-")
    else:
        old_path = Path(original["artifacts"][0]["path"])
        old_rows = json.loads(old_path.read_bytes())
        old_rows[0]["status"] = "FAIL"
        original["artifacts"] = [_save_report(old_path, old_rows)]
    verified["artifacts"] = [_save_report(path, rows)]
    with pytest.raises(ValueError, match="software DOI reconciliation"):
        validate_software_doi_resolution(resolution, original, {verified["evidence_id"]: verified})


def _bound_doi_fixture(tmp_path: Path, *, failed_followup: bool = False) -> tuple[GraphPlan, SoftwareDoiRecheck, dict[str, Any], dict[str, Any]]:
    """Bind real compiled original evidence, retaining independent canonical report data."""
    original, verified, _resolution = _fixture(tmp_path)
    if failed_followup:
        log = tmp_path / "denied.log"
        log.write_bytes(b"PermissionError: [Errno 1] Operation not permitted\n")
        verified.update(status="failed")
        verified["executions"][0].update(result="failed", exit_code=1, evidence=log.read_text().strip())
        verified["executions"][0]["artifact_paths"].append(str(log))
        verified["artifacts"].append(
            {
                "path": str(log),
                "kind": "log",
                "repository_status": "outside-repository",
                "artifact_digest_mode": "content-sha256-v1",
                "artifact_digest": digest_bytes(log.read_bytes()),
            }
        )
    planning = _sparse_plan_document()
    planning["validation_requirements"] = [_requirement(original, baseline=True), _requirement(verified, baseline=False)]
    planning["pre_review_validation_requirement_ids"] = ["original"]
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
    nodes = {mapping.requirement_id: mapping.validation_unit_id for mapping in plan.validation_evidence_mapping}
    original["node_id"], verified["node_id"] = nodes["original"], nodes["verified"]
    lifecycle = {"plan": _json_plan(plan), "source_state": original["observed_source_state"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "initial"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    entry = next(entry for entry in dispatches["dispatches"] if entry["node_id"] == nodes["original"])
    original["evidence_id"] = entry["dispatch"]["evidence_id"]
    source = _compile_validator(entry, lifecycle, tmp_path / "journal.jsonl", original)
    original = json.loads(Path(source["metadata_path"]).read_bytes())["normalized_record"]
    binding = SoftwareDoiRecheck(nodes["verified"], "verified", 0, original["artifacts"][0]["path"], canonical_json(original))
    return replace(plan, software_doi_rechecks=(binding,)), binding, original, verified


@pytest.mark.parametrize(
    "defect", ["none", "redirected-report", "wrong-source", "wrong-cff", "wrong-report", "contradiction", "failed", "unrelated", "altered-original"]
)
def test_early_doi_gate_requires_complete_canonical_evidence(tmp_path: Path, defect: str) -> None:
    plan, binding, original, verified = _bound_doi_fixture(tmp_path)
    nodes = {mapping.requirement_id: mapping.validation_unit_id for mapping in plan.validation_evidence_mapping}
    state = {nodes["original"]: "accepted"}
    latest = {
        nodes["original"]: {
            "evidence": {"evidence_id": original["evidence_id"], "evidence_status": "failed", "normalized_record_digest": digest_json(original)}
        }
    }
    assert pending_validation_barrier(plan, state, latest, nodes["verified"]) == ()
    assert pending_validation_barrier(plan, state, latest, "semantic-work") == (nodes["original"],)
    if defect == "redirected-report":
        verified["executions"][0]["command"] += " > " + shlex.quote(verified["artifacts"][0]["path"])
        extra = _save_report(tmp_path / "summary.json", [])
        verified["artifacts"].append(extra)
        verified["executions"][0]["artifact_paths"].append(extra["path"])
    elif defect == "wrong-source":
        verified["observed_source_state"][0] = "different"
    elif defect == "failed":
        verified["status"] = "failed"
        verified["executions"][0].update(result="failed", exit_code=1)
    elif defect == "wrong-report":
        verified["executions"][0]["artifact_paths"] = []
    elif defect in {"wrong-cff", "contradiction"}:
        report = Path(verified["artifacts"][0]["path"])
        rows = json.loads(report.read_bytes())
        if defect == "wrong-cff":
            rows[0]["canonical_software"]["digest"] = "sha256:" + "0" * 64
        else:
            rows[0]["local_status"] = "MISMATCH"
        verified["artifacts"] = [_save_report(report, rows)]
    elif defect == "unrelated":
        plan = replace(plan, pre_review_validation_nodes=(*plan.pre_review_validation_nodes, "unrelated"))
        state["unrelated"] = "accepted"
        latest["unrelated"] = {"evidence": {"evidence_status": "failed"}}
        assert pending_validation_barrier(plan, state, latest, nodes["verified"]) == ("unrelated",)
    elif defect == "altered-original":
        latest[nodes["original"]]["evidence"]["normalized_record_digest"] = "sha256:" + "0" * 64
        assert pending_validation_barrier(plan, state, latest, nodes["verified"]) == (nodes["original"],)
    artifact, metadata = tmp_path / "compiled.md", tmp_path / "compiled.metadata.json"
    artifact.write_bytes(b"canonical fixture evidence")
    metadata.write_text(json.dumps({"normalized_record": verified}))
    state[nodes["verified"]] = "accepted"
    latest[nodes["verified"]] = {
        "evidence": {
            "evidence_id": verified["evidence_id"],
            "evidence_status": verified["status"],
            "normalized_record_digest": digest_json(verified),
            "artifact_digest": digest_bytes(artifact.read_bytes()),
            "canonical_doi_source": {"artifact_path": str(artifact), "metadata_path": str(metadata)},
        }
    }
    pending = pending_validation_barrier(plan, state, latest, "semantic-work")
    assert pending == (() if defect in {"none", "redirected-report"} else ("unrelated",) if defect == "unrelated" else (nodes["original"],))
    assert binding.original.status.value == "failed"


@pytest.mark.parametrize("defect", ["missing", "extra", "boolean-index", "negative-index", "unknown-report", "malformed-record", "passed-record"])
def test_doi_binding_rejects_invalid_construction_and_detaches_exports(tmp_path: Path, defect: str) -> None:
    _plan, binding, original, _verified = _bound_doi_fixture(tmp_path)
    raw = asdict(binding)
    assert SoftwareDoiRecheck.parse(raw) == binding
    detached = binding.original_document()
    detached["executions"][0]["result"] = "passed"
    assert binding.original.executions[0].result.value == "failed"
    if defect == "missing":
        del raw["original_report"]
    elif defect == "extra":
        raw["unbound_policy"] = True
    elif defect == "boolean-index":
        raw["execution_index"] = True
    elif defect == "negative-index":
        raw["execution_index"] = -1
    elif defect == "unknown-report":
        raw["original_report"] = str(tmp_path / "other.json")
    elif defect == "malformed-record":
        raw["original_record_json"] = "{}"
    else:
        original.update(status="passed")
        original["executions"][0].update(result="passed", exit_code=0)
        raw["original_record_json"] = canonical_json(original)
    with pytest.raises((ValueError, TypeError)):
        SoftwareDoiRecheck.parse(raw)
    if defect not in {"missing", "extra"}:
        with pytest.raises((ValueError, TypeError)):
            SoftwareDoiRecheck(**raw)
        with pytest.raises((ValueError, TypeError)):
            replace(binding, **raw)


def _compile_validator(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path, record: dict[str, Any]) -> dict[str, str]:
    """Compile the validator's result and register its evidence as accepted in the journal."""
    dispatch = {
        **entry["dispatch"],
        "before_state": lifecycle["source_state"],
        "after_state": lifecycle["source_state"],
        "source_capture": _source_capture(Path(record["executions"][0]["working_directory"])),
        "workspace_before": [],
        "workspace_after": [
            {"path": artifact["path"], "digest": artifact["artifact_digest"], "snapshot_mode": "content-sha256-v1", "status": "outside-repository"}
            for artifact in record["artifacts"]
        ],
    }
    content, metadata = compile_validation(
        {"dispatch": dispatch, "payload": {key: record[key] for key in ("status", "executions", "artifacts")} | {"schema_version": 3, "limitations": []}}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source: dict[str, str] = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
    return source


def _doi_recovery_fixture(tmp_path: Path, *, checks_started: bool = True) -> tuple[dict[str, Any], Namespace, dict[str, Any], dict[str, Any]]:
    """Prepare a failed DOI follow-up for recovery with its verification record."""
    plan, binding, original, verified = _bound_doi_fixture(tmp_path, failed_followup=True)
    # Early validators keep their superseded events in the migrated journal.
    plan = replace(plan, pre_review_validation_nodes=(*plan.pre_review_validation_nodes, binding.node_id))
    lifecycle = {"plan": _json_plan(plan), "source_state": original["observed_source_state"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "bound"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    entries = {entry["node_id"]: entry for entry in dispatches["dispatches"]}
    args = Namespace(journal=tmp_path / "bound.jsonl", dispatches=tmp_path / "dispatches.json", current_capture=tmp_path / "capture.json")
    args.dispatches.write_text(json.dumps(dispatches))
    args.current_capture.write_text(json.dumps(_source_capture(tmp_path)))
    _compile_validator(entries[binding.original.node_id], lifecycle, args.journal, original)
    entry = entries[binding.node_id]
    verified["evidence_id"] = entry["dispatch"]["evidence_id"]
    after = capture_workspace_snapshot(entry["dispatch"])
    if checks_started:
        _compile_validator(entry, lifecycle, args.journal, verified)
    else:
        blocked = {**entry, "dispatch": {**entry["dispatch"], "workspace_before": after["records"], "workspace_after": after["records"]}}
        _block_validator(blocked, lifecycle, args.journal)
    for phase, snapshot in (("before", {**after, "records": []}), ("after", after)):
        (tmp_path / f"{phase}.json").write_text(json.dumps(snapshot))
    request = {
        **lifecycle,
        "artifact_store": str(tmp_path / "recovery"),
        "node_id": entry["node_id"],
        "failure_kind": "executor-permission",
        "checks_started": True,
        "reason": "The canonical follow-up encountered a captured executor permission denial.",
        "remedy": "Use the permitted executor.",
        "environment": "permitted native executor",
        "permission_change": "restricted to permitted executor",
        "executor_permissions": "require_escalated",
        "failure_evidence": {
            "log_path": str(tmp_path / "denied.log"),
            "diagnostic": "PermissionError: [Errno 1] Operation not permitted",
            "before_capture": str(args.current_capture),
            "after_capture": str(args.current_capture),
            "workspace_before": str(tmp_path / "before.json"),
            "workspace_after": str(tmp_path / "after.json"),
        },
    }
    if not checks_started:
        request.update(checks_started=False, failure_kind="cache-access", permission_change="none", environment="accessible uv cache")
        del request["failure_evidence"], request["executor_permissions"]
    return request, args, entry, verified


@pytest.mark.parametrize("checks_started", [False, True])
def test_doi_recovery_verifies_superseded_sources_against_retained_attempt(tmp_path: Path, checks_started: bool) -> None:
    request, args, entry, verified = _doi_recovery_fixture(tmp_path, checks_started=checks_started)
    preserved = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    original_events = read_execution_journal(args.journal, plan=_graph_plan(request["plan"]), source_state=tuple(request["source_state"]))[0]
    historical = original_events[-1]["evidence"]
    recover = recover_validation_execution if checks_started else recover_validation_launch
    recovered = recover(request, args)
    lifecycle = recovered["lifecycle_input"]
    plan = _graph_plan(lifecycle["plan"])
    journal = Path(recovered["journal_path"])
    node = next(node for node in plan.actual_worker_nodes if node.node_id == entry["node_id"])
    status = "accepted" if checks_started else "blocked"
    checked = _journal_evidence(historical, plan=plan, node=node, status=status, superseded=True)
    assert checked is not None
    assert checked["evidence_id"] == verified["evidence_id"]
    diagnostic = "evidence ID differs" if checks_started else "validation evidence differs"
    with pytest.raises(ValueError, match=diagnostic):
        _journal_evidence(historical, plan=plan, node=node, status=status)
    altered = deepcopy(historical)
    unbound = tmp_path / "unbound.json"
    unbound.write_bytes(Path(historical["canonical_doi_source"]["metadata_path"]).read_bytes())
    altered["canonical_doi_source"]["metadata_path"] = str(unbound)
    with pytest.raises(ValueError, match=diagnostic):
        _journal_evidence(altered, plan=plan, node=node, status=status, superseded=True)
    entries = json.loads(Path(recovered["dispatches_path"]).read_bytes())
    _prepare_all_fixture_timing(entries)
    events = read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))[0]
    ready = next_ready_nodes({**lifecycle, "current_source_state": lifecycle["source_state"]}, journal_events=events, dispatch_set=entries)
    assert ready["ready_node_ids"] == [entry["node_id"]]
    retry = ready["ready_dispatches"][0]
    if checks_started:
        assert retry["dispatch"]["evidence_id"] != verified["evidence_id"]
    else:
        assert retry["dispatch"]["evidence_id"] == verified["evidence_id"]
    verified.update(status="passed", evidence_id=retry["dispatch"]["evidence_id"])
    verified["executions"][0].update(result="passed", exit_code=0, evidence="Canonical report completed on the permitted executor")
    _compile_validator(retry, lifecycle, journal, verified)
    events = read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))[0]
    assert events[-1]["evidence"]["evidence_id"] == verified["evidence_id"]
    assert any(event["evidence"] == historical for event in events)
    assert all(path.read_bytes() == content for path, content in preserved.items())
    old_artifact = Path(historical["canonical_doi_source"]["artifact_path"])
    old_artifact.chmod(0o644)
    old_artifact.write_bytes(old_artifact.read_bytes() + b"\nchanged historical result\n")
    with pytest.raises(ValueError, match=r"digest|identity|result"):
        read_execution_journal(journal, plan=plan, source_state=tuple(lifecycle["source_state"]))


def test_historical_doi_evidence_is_not_shadowed_by_another_launch_recovery(tmp_path: Path) -> None:
    older = tmp_path / "older"
    older.mkdir()
    launch_request, launch_args, _entry, _verified = _doi_recovery_fixture(older, checks_started=False)
    launch = recover_validation_launch(launch_request, launch_args)
    current = tmp_path / "current"
    current.mkdir()
    request, args, entry, _verified = _doi_recovery_fixture(current)
    original = read_execution_journal(args.journal, plan=_graph_plan(request["plan"]), source_state=tuple(request["source_state"]))[0][-1]["evidence"]
    recovered = recover_validation_execution(request, args)
    plan = _graph_plan(recovered["lifecycle_input"]["plan"])
    older_recoveries = _graph_plan(launch["lifecycle_input"]["plan"]).validation_recoveries
    plan = replace(plan, validation_recoveries=(*older_recoveries, *plan.validation_recoveries))
    node = next(node for node in plan.actual_worker_nodes if node.node_id == entry["node_id"])
    assert _journal_evidence(original, plan=plan, node=node, status="accepted", superseded=True) is not None


@pytest.mark.parametrize("fields", [{}, {"evidence_id": None}, {"evidence_id": ""}, {"evidence_id": False}])
def test_doi_recheck_request_rejects_missing_or_invalid_evidence_id(fields: dict[str, Any]) -> None:
    request = {"software_doi_rechecks": [{"requirement_id": "canonical", **fields}]}
    with pytest.raises(ValueError, match="evidence_id"):
        _software_doi_recheck_ids(request, [{"evidence_id": "accepted-original"}], ())


def _followup_planning(original: dict[str, Any], verified: dict[str, Any], *, early: bool, later_check: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a plan containing the original DOI check and a later validation requirement."""
    planning = _sparse_plan_document()
    planning["validation_requirements"] = [_requirement(original, baseline=True)]
    if early:
        planning["pre_review_validation_requirement_ids"] = ["original"]
    later = deepcopy(verified)
    later.update(requirement_ids=["later"], artifacts=[])
    later["executions"][0].update(command="true", artifact_paths=[])
    if later_check:
        planning["validation_requirements"].append(_requirement(later, baseline=False))
        planning["pre_review_validation_requirement_ids"].append("later")
    return planning, later


@pytest.mark.parametrize(("early", "later_check"), [(False, False), (True, False), (True, True)])
def test_canonical_followup_expands_only_validation_and_finalizes_with_failed_history(  # noqa: C901, PLR0915 - complete preserved-history continuation.
    tmp_path: Path, capsys: pytest.CaptureFixture[str], early: bool, later_check: bool
) -> None:
    """Bind a later DOI check to its original failed report and verify that both records survive finalization."""
    original, verified, resolution = _fixture(tmp_path)
    planning, later = _followup_planning(original, verified, early=early, later_check=later_check)
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
    lifecycle = {"plan": _json_plan(plan), "source_state": original["observed_source_state"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "initial"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    paths = {name: tmp_path / f"{name}.json" for name in ("journal", "dispatches", "capture")}
    paths["dispatches"].write_text(json.dumps(dispatches))
    paths["capture"].write_text(json.dumps(_source_capture(tmp_path)))
    sources = []
    for entry in dispatches["dispatches"]:
        if entry["result_contract"] == "compact-validation" and "original" in entry["dispatch"]["requirement_ids"]:
            original["evidence_id"] = entry["dispatch"]["evidence_id"]
            sources.append(_compile_validator(entry, lifecycle, paths["journal"], original))
        elif entry["dispatch"]["mode"] == "audit" and not early:
            sources.append(_compile_repair_fixture_entry(entry, lifecycle, paths["journal"]))
    preserved = {Path(path): Path(path).read_bytes() for source in sources for path in source.values()}
    preserved[paths["journal"]] = paths["journal"].read_bytes()
    request: dict[str, Any] = {
        **lifecycle,
        "artifact_store": str(tmp_path / "followup"),
        "validation_requirements": [_requirement(verified, baseline=False)],
        "software_doi_rechecks": [
            {"requirement_id": "verified", "evidence_id": original["evidence_id"], "execution_index": 0, "original_report": original["artifacts"][0]["path"]}
        ],
    }
    args = Namespace(journal=paths["journal"], dispatches=paths["dispatches"], current_capture=paths["capture"])
    for field, value in (("commands", ["false"]), ("source_state", ["scope", "changed", "repository"])):
        invalid = deepcopy(request)
        invalid["validation_requirements"][0][field] = value
        with pytest.raises(ValueError, match=r"software DOI|source-matching"):
            reconcile_validation_requirements(invalid, args)
        assert all(path.read_bytes() == content for path, content in preserved.items())
    for directories in ([], [str(tmp_path), str(tmp_path)]):
        invalid = deepcopy(request)
        invalid["validation_requirements"][0]["working_directories"] = directories
        input_path = tmp_path / "invalid-recheck.json"
        input_path.write_text(json.dumps(invalid))
        assert (
            main(
                [
                    "reconcile-validation-requirements",
                    "--input",
                    str(input_path),
                    "--journal",
                    str(paths["journal"]),
                    "--dispatches",
                    str(paths["dispatches"]),
                    "--current-capture",
                    str(paths["capture"]),
                    "--output",
                    str(tmp_path / "invalid-output.json"),
                ]
            )
            == 2
        )
        assert "software DOI recheck requires" in capsys.readouterr().err
        assert all(path.read_bytes() == content for path, content in preserved.items())
    expanded = reconcile_validation_requirements(request, args)
    lifecycle = expanded["lifecycle_input"]
    journal = Path(expanded["journal_path"])
    entries = json.loads(Path(expanded["dispatches_path"]).read_bytes())["dispatches"]
    expanded_plan = _graph_plan(lifecycle["plan"])
    _prepare_all_fixture_timing(json.loads(Path(expanded["dispatches_path"]).read_bytes()))
    events, _state, _head = read_execution_journal(journal, plan=expanded_plan, source_state=tuple(lifecycle["source_state"]))
    ready = next_ready_nodes(
        {**lifecycle, "current_source_state": lifecycle["source_state"]},
        journal_events=events,
        dispatch_set=json.loads(Path(expanded["dispatches_path"]).read_bytes()),
    )
    for entry in entries:
        if entry["result_contract"] == "compact-validation" and "verified" in entry["dispatch"]["requirement_ids"]:
            assert entry["node_id"] in ready["ready_node_ids"], ready
            verified["evidence_id"] = entry["dispatch"]["evidence_id"]
            resolution["checks"][0]["verification_evidence_id"] = verified["evidence_id"]
            sources.append(_compile_validator(entry, lifecycle, journal, verified))
    for entry in entries:
        if entry["result_contract"] == "compact-validation" and "later" in entry["dispatch"]["requirement_ids"]:
            assert entry["node_id"] not in ready["ready_node_ids"]
            events, _state, _head = read_execution_journal(journal, plan=expanded_plan, source_state=tuple(lifecycle["source_state"]))
            resumed = next_ready_nodes(
                {**lifecycle, "current_source_state": lifecycle["source_state"]},
                journal_events=events,
                dispatch_set=json.loads(Path(expanded["dispatches_path"]).read_bytes()),
            )
            assert entry["node_id"] in resumed["ready_node_ids"]
            later["evidence_id"] = entry["dispatch"]["evidence_id"]
            sources.append(_compile_validator(entry, lifecycle, journal, later))
    if early:
        sources.extend(_compile_repair_fixture_entry(entry, lifecycle, journal) for entry in entries if entry["dispatch"]["mode"] == "audit")
    for entry in entries:
        if entry["dispatch"].get("mode") != "synthesis":
            continue
        bundle = build_synthesis_bundle({**lifecycle, "sources": sources})
        payload = _synthesis_payload(entry["dispatch"], bundle)
        next(item for item in payload["validation_reconciliation"] if item["evidence_id"] == original["evidence_id"])["software_doi_resolution"] = resolution
        require_schema(payload, SCHEMA_ROOT / "synthesis-payload-v1.schema.json")
        dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"], "synthesis_bundle": bundle}
        content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
        Path(entry["artifact_path"]).write_bytes(content)
        Path(entry["metadata_path"]).write_text(json.dumps(metadata))
        source = {key: entry[key] for key in ("artifact_path", "metadata_path")}
        append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
        sources.append(source)
    output = tmp_path / "final.json"
    assert (
        main(
            [
                "finalize-proof",
                "--input",
                expanded["lifecycle_input_path"],
                "--journal",
                str(journal),
                "--dispatches",
                expanded["dispatches_path"],
                "--current-capture",
                expanded["current_capture_path"],
                "--output",
                str(output),
            ]
        )
        == 0
    )
    final = json.loads(output.read_bytes())
    assert final["graph_proof_status"] == "complete"
    assert final["repository_validation_status"] == "failed"
    assert final["repository_readiness"] == "ready"
    assert final["software_doi_resolutions"][0]["result"] == "failed"
    assert all(path.read_bytes() == content for path, content in preserved.items())
    Path(original["artifacts"][0]["path"]).write_text("[]")
    assert (
        main(
            [
                "finalize-proof",
                "--input",
                expanded["lifecycle_input_path"],
                "--journal",
                str(journal),
                "--dispatches",
                expanded["dispatches_path"],
                "--current-capture",
                expanded["current_capture_path"],
                "--output",
                str(tmp_path / "tampered.json"),
            ]
        )
        == 2
    )
