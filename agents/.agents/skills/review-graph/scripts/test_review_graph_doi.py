"""DOI reconciliation preserves failed executions while allowing verified readiness."""

import base64
import json
import shlex
from argparse import Namespace
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from review_graph_doi import captured_software_inputs, validate_software_doi_resolution
from review_graph_plan import plan_from_document
from review_graph_reuse import SNAPSHOT_FORMAT, regular_file_fingerprint, source_snapshot
from review_graph_runtime import (
    JournalEventRequest,
    append_journal_event,
    build_synthesis_bundle,
    compile_review,
    compile_validation,
    main,
    materialize_dispatches,
    reconcile_validation_requirements,
)
from review_graph_schema import SchemaValidationError, require_schema, require_schema_definition
from review_graph_synthesis import validate_synthesis
from test_capture_scope import _capture, _commit_all, _init_repo
from test_review_graph_runtime import ROUTING_CATALOG, SCHEMA_ROOT, SKILL_ROOT, _compile_repair_fixture_entry, _json_plan, _sparse_plan_document
from test_review_graph_transitions import _synthesis_payload

CFF_CONTENT = b"title: 'Project: Scientific software'\n"


def _source_capture(root: Path) -> dict[str, Any]:
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


def _requirement(record: dict[str, Any], *, baseline: bool) -> dict[str, Any]:
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
            "allowed_artifacts": [{"path": artifact["path"], "kind": "report", "repository_status": "outside-repository"} for artifact in record["artifacts"]],
        }
    )
    return requirement


def _compile_validator(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path, record: dict[str, Any]) -> dict[str, str]:
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
        {"dispatch": dispatch, "payload": {key: record[key] for key in ("status", "executions", "artifacts")} | {"limitations": []}}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    source: dict[str, str] = {key: entry[key] for key in ("artifact_path", "metadata_path")}
    append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
    return source


def test_canonical_followup_expands_only_validation_and_finalizes_with_failed_history(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: PLR0915
    original, verified, resolution = _fixture(tmp_path)
    planning = _sparse_plan_document()
    planning["validation_requirements"] = [_requirement(original, baseline=True)]
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
        if entry["result_contract"] == "compact-validation":
            original["evidence_id"] = entry["dispatch"]["evidence_id"]
            sources.append(_compile_validator(entry, lifecycle, paths["journal"], original))
        elif entry["dispatch"]["mode"] == "audit":
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
    for entry in entries:
        if entry["result_contract"] == "compact-validation" and entry["node_id"] not in expanded["retained_node_ids"]:
            verified["evidence_id"] = entry["dispatch"]["evidence_id"]
            resolution["checks"][0]["verification_evidence_id"] = verified["evidence_id"]
            sources.append(_compile_validator(entry, lifecycle, journal, verified))
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
