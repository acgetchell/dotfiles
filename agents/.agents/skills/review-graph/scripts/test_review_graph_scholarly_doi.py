"""Primary publication records reconcile dates without excusing wrong identities."""

import base64
import json
import runpy
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from review_graph_doi import captured_doi_inputs, validate_scholarly_doi_resolution
from review_graph_plan import plan_from_document
from review_graph_reuse import regular_file_fingerprint, source_snapshot
from review_graph_runtime import (
    JournalEventRequest,
    append_journal_event,
    build_synthesis_bundle,
    compile_review,
    compile_validation,
    main,
    materialize_dispatches,
)
from review_graph_schema import schema_diagnostics
from review_graph_synthesis import validate_synthesis
from test_review_graph_doi import _fixture, _requirement, _save_report, _source_capture
from test_review_graph_runtime import ROUTING_CATALOG, SCHEMA_ROOT, SKILL_ROOT, _compile_repair_fixture_entry, _json_plan, _sparse_plan_document
from test_review_graph_transitions import _synthesis_payload


def _scholarly_fixture(
    tmp_path: Path, *, mixed: bool = False, first_doi: str = "10.24033/rhm.30", adjacent: bool = False
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    original, verified, _software = _fixture(tmp_path)
    prefix, separator = ("- ", "\n") if adjacent else ("", "\n\n")
    references = (
        f"{prefix}Brezinski. La méthode de Cholesky. (2005). DOI: https://doi.org/{first_doi}{separator}"
        f"{prefix}Golub, Van Loan. Matrix Computations. (2013). DOI: https://doi.org/10.56021/9781421407944\n"
    ).encode()
    if mixed:
        references += b"\nSee CITATION.cff for this software citation. DOI: https://doi.org/10.5281/zenodo.123\n"
    capture = _source_capture(tmp_path)
    capture["repository_path_fingerprints"]["README.md"] = regular_file_fingerprint("README.md", references)
    capture["repository_path_fingerprints"] = dict(sorted(capture["repository_path_fingerprints"].items()))
    capture["repository_state_fingerprint"] = source_snapshot(capture).computed_fingerprint()
    source = {
        "path": str(tmp_path / "README.md"),
        "digest": "sha256:" + sha256(references).hexdigest(),
        "content_base64": base64.b64encode(references).decode(),
    }
    rows: list[dict[str, Any]] = []
    occurrences = []
    for doi, line, title, authors, local, resolved, url, authority in (
        (first_doi, 1, "La méthode de Cholesky", ["Brezinski"], "2005", "2018", f"https://www.numdam.org/articles/{first_doi}/", "journal-archive"),
        (
            "10.56021/9781421407944",
            2 if adjacent else 3,
            "Matrix Computations",
            ["Golub", "Van Loan"],
            "2013",
            "2012",
            "https://www.press.jhu.edu/books/title/10678/matrix-computations",
            "publisher",
        ),
    ):
        rows.append(
            {
                "doi": doi,
                "line": line,
                "status": "MISMATCH",
                "resolved_title": title,
                "resolved_authors": authors,
                "resolved_year": resolved,
                "resolved_container": None,
                "source": source,
                "local_years": [local],
                "mismatched_fields": ["year"],
                "title_score": 1.0,
                "author_score": 1.0,
                "date_provenance": {"issued": resolved},
            }
        )
        excerpt = f"{', '.join(authors)}. {title}. Publication year {local}. DOI {doi}."
        primary_path = tmp_path / f"primary-{line}.txt"
        primary_path.write_text(excerpt)
        occurrences.append(
            {
                "doi": doi,
                "line": line,
                "field": "year",
                "resolver_value": resolved,
                "disposition": "retain-local-publication-year",
                "reviewer": "fixture reviewer",
                "reason": "Primary publication record agrees with local year.",
                "primary_record": {
                    "path": str(primary_path),
                    "digest": "sha256:" + sha256(primary_path.read_bytes()).hexdigest(),
                    "url": url,
                    "authority": authority,
                    "retrieved_on": "2026-10-07",
                    "doi": doi,
                    "title": title,
                    "authors": authors,
                    "publication_year": local,
                    "excerpt": excerpt,
                },
            }
        )
    for record in (original, verified):
        new_rows = deepcopy(rows)
        if mixed:
            old_rows = json.loads(Path(record["artifacts"][0]["path"]).read_bytes())
            new_rows.append({**old_rows[0], "line": 5, "source": source})
        record["status"] = "failed"
        record["executions"][0].update(result="failed", exit_code=1)
        record["observed_source_state"] = list(source_snapshot(capture).source_state)
        record["artifacts"] = [_save_report(Path(record["artifacts"][0]["path"]), new_rows)]
        record["captured_doi_inputs"] = captured_doi_inputs(record, capture)
    resolution = {
        "reason": "Retain primary-supported publication dates.",
        "checks": [{"execution_index": 0, "original_report": original["artifacts"][0]["path"], "occurrences": occurrences}],
    }
    if mixed:
        resolution["checks"][0]["software_verification"] = {
            "evidence_id": verified["evidence_id"],
            "execution_index": 0,
            "report": verified["artifacts"][0]["path"],
        }
    return original, verified, resolution, capture


@pytest.mark.parametrize("first_doi", ["10.1007/example", "10.12345/paper.2018"])
@pytest.mark.parametrize("adjacent", [False, True])
def test_checker_output_reconciles_doi_digits_and_adjacent_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first_doi: str, adjacent: bool) -> None:
    original, _verified, resolution, _capture = _scholarly_fixture(tmp_path, first_doi=first_doi, adjacent=adjacent)
    rows = json.loads(Path(original["artifacts"][0]["path"]).read_bytes())
    source = rows[0]["source"]
    markdown = base64.b64decode(source["content_base64"]).decode()
    checker_path = SKILL_ROOT.parent / "scientific-citation-audit" / "scripts" / "validate_reference_dois.py"
    monkeypatch.syspath_prepend(str(checker_path.parent))
    checker = runpy.run_path(str(checker_path))
    resolved = {
        row["doi"]: {
            "title": row["resolved_title"],
            "author": [{"family": name} for name in row["resolved_authors"]],
            "issued": {"date-parts": [[int(row["resolved_year"])]]},
        }
        for row in rows
    }
    results = checker["validate_entries"](checker["extract_entries"](markdown), 1.0, 0.45, lambda doi, _timeout: resolved[doi.value])
    reported = [{**result.to_json_object(), "source": source} for result in results]
    assert [row["local_years"] for row in reported] == [["2005"], ["2013"]]
    original["artifacts"] = [_save_report(Path(original["artifacts"][0]["path"]), reported)]
    validate_scholarly_doi_resolution(resolution, original, {original["evidence_id"]: original})


@pytest.mark.parametrize("mixed", [False, True])
def test_primary_year_resolution_retains_failed_history_and_mixed_software(tmp_path: Path, mixed: bool) -> None:
    original, verified, resolution, _capture = _scholarly_fixture(tmp_path, mixed=mixed)
    records = [original, verified] if mixed else [original]
    payload = {
        "status": "no-findings",
        "findings": [],
        "readiness_verdict": "ready",
        "predecessor_coverage": [
            {"evidence_id": record["evidence_id"], "requirement_ids": record["requirement_ids"], "disposition": "accepted"} for record in records
        ],
        "routing_closure": {"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
        "validation_reconciliation": [],
    }
    for record in records:
        bound = deepcopy(resolution)
        bound["checks"][0]["original_report"] = record["artifacts"][0]["path"]
        if record is verified:
            del bound["checks"][0]["software_verification"]
        row = {
            "evidence_id": record["evidence_id"],
            "requirement_ids": record["requirement_ids"],
            "result": "failed",
            "execution_mode": "native",
            "platform": "native",
            "scholarly_doi_resolution": bound,
        }
        schema = json.loads((SCHEMA_ROOT / "synthesis-payload-v1.schema.json").read_text())["properties"]["validation_reconciliation"]["items"]
        assert not schema_diagnostics(row, schema)
        payload["validation_reconciliation"].append(row)
    predecessors = tuple(record["evidence_id"] for record in records)
    before = deepcopy(records)
    validate_synthesis(payload, predecessors, {"records": records, "plan_context": {"routing_catalog_closed": True}})
    assert records == before
    with pytest.raises(ValueError, match="ready synthesis"):
        validate_synthesis(payload, predecessors)
    (tmp_path / "README.md").write_text("changed after validation")
    validate_scholarly_doi_resolution(resolution, original, {verified["evidence_id"]: verified})


@pytest.mark.parametrize(
    "defect",
    [
        "title",
        "authors",
        "doi",
        "year",
        "network",
        "missing-occurrence",
        "duplicate",
        "report-bytes",
        "primary-bytes",
        "source",
        "unexecuted",
        "non-doi",
        "excerpt",
        "resolver",
        "unbound-source",
    ],
)
def test_primary_year_resolution_rejects_unproven_disagreements(tmp_path: Path, defect: str) -> None:  # noqa: C901, PLR0912
    original, _verified, resolution, _capture = _scholarly_fixture(tmp_path)
    occurrence = resolution["checks"][0]["occurrences"][0]
    report = Path(original["artifacts"][0]["path"])
    rows = json.loads(report.read_bytes())
    if defect in {"title", "authors", "doi"}:
        rows[0]["mismatched_fields"].append(defect)
    elif defect == "year":
        occurrence["primary_record"]["publication_year"] = "2006"
    elif defect == "network":
        rows[0]["status"] = "FAIL"
    elif defect == "missing-occurrence":
        resolution["checks"][0]["occurrences"].pop()
    elif defect == "duplicate":
        resolution["checks"][0]["occurrences"].append(deepcopy(occurrence))
    elif defect == "primary-bytes":
        Path(occurrence["primary_record"]["path"]).write_text("different evidence")
    elif defect == "source":
        rows[0]["source"]["digest"] = "sha256:" + "f" * 64
    elif defect == "unexecuted":
        original["executions"].append({"result": "blocked"})
    elif defect == "non-doi":
        original["executions"][0]["command"] = "false"
    elif defect == "excerpt":
        occurrence["primary_record"]["excerpt"] = "invented publication record"
    elif defect == "resolver":
        occurrence["resolver_value"] = "2017"
    elif defect == "unbound-source":
        original.pop("captured_doi_inputs")
    original["artifacts"] = [_save_report(report, rows)]
    if defect == "report-bytes":
        report.write_text("[]")
    with pytest.raises(ValueError, match="DOI reconciliation"):
        validate_scholarly_doi_resolution(resolution, original, {})


@pytest.mark.parametrize("defect", [None, "source", "bytes", "identity"])
def test_historical_year_reports_use_retained_source_evidence(tmp_path: Path, defect: str | None) -> None:
    original, _verified, resolution, capture = _scholarly_fixture(tmp_path)
    report = Path(original["artifacts"][0]["path"])
    rows = json.loads(report.read_bytes())
    bibliography = base64.b64decode(rows[0]["source"]["content_base64"])
    for row in rows:
        row["message"] = "resolved year does not appear in local entry"
        del row["mismatched_fields"], row["local_years"], row["source"]["content_base64"]
    original.pop("captured_doi_inputs")
    if defect == "identity":
        rows[0]["message"] = "resolved authors do not appear in local entry; resolved year does not appear in local entry"
    original["artifacts"] = [_save_report(report, rows)]
    capture_path, bibliography_path = tmp_path / "retained-capture.json", tmp_path / "retained-README.md"
    if defect == "source":
        capture["captured_worktree_fingerprint"] = "f" * 64
        capture["repository_state_fingerprint"] = source_snapshot(capture).computed_fingerprint()
    capture_path.write_text(json.dumps(capture))
    bibliography_path.write_bytes(bibliography)
    resolution["checks"][0]["source_evidence"] = {
        "capture_path": str(capture_path),
        "capture_digest": "sha256:" + sha256(capture_path.read_bytes()).hexdigest(),
        "bibliography_path": str(bibliography_path),
        "bibliography_digest": "sha256:" + sha256(bibliography).hexdigest(),
    }
    if defect == "bytes":
        bibliography_path.write_text("changed source")
    before = deepcopy(original)
    if defect is None:
        validate_scholarly_doi_resolution(resolution, original, {})
    else:
        with pytest.raises(ValueError, match="DOI reconciliation"):
            validate_scholarly_doi_resolution(resolution, original, {})
    assert original == before


def test_reconciliation_identifies_a_contradictory_publication_date_field(tmp_path: Path) -> None:
    original, _verified, resolution, _capture = _scholarly_fixture(tmp_path)
    path = Path(original["artifacts"][0]["path"])
    rows = json.loads(path.read_bytes())
    rows[0]["resolved_year"] = "2005"
    rows[0]["date_provenance"] = {"published-print": "2005", "issued": "2018"}
    occurrence = resolution["checks"][0]["occurrences"][0]
    occurrence["resolver_field"] = "issued"
    original["artifacts"] = [_save_report(path, rows)]
    validate_scholarly_doi_resolution(resolution, original, {})
    occurrence["resolver_field"] = "published-print"
    occurrence["resolver_value"] = "2005"
    with pytest.raises(ValueError, match="exact local/resolver disagreement"):
        validate_scholarly_doi_resolution(resolution, original, {})


def test_scholarly_resolution_final_proof_rechecks_primary_bytes(tmp_path: Path) -> None:
    original, _verified, resolution, capture = _scholarly_fixture(tmp_path)
    planning = _sparse_plan_document()
    planning["validation_requirements"] = [_requirement(original, baseline=True)]
    plan = plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
    lifecycle = {"plan": _json_plan(plan), "source_state": original["observed_source_state"]}
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(tmp_path / "artifacts"),
            "authorization": "review-only",
            "repository_root": str(SKILL_ROOT.parents[2]),
            "state_verification_command": "capture_scope.py --mode baseline",
        }
    )
    journal, dispatch_path, capture_path, lifecycle_path = (tmp_path / name for name in ("journal.json", "dispatch.json", "capture.json", "lifecycle.json"))
    dispatch_path.write_text(json.dumps(dispatches))
    capture_path.write_text(json.dumps(capture))
    lifecycle_path.write_text(json.dumps(lifecycle))
    sources = []
    for entry in dispatches["dispatches"]:
        if entry["dispatch"].get("mode") == "synthesis":
            continue
        if entry["result_contract"] == "compact-validation":
            dispatch = {
                **entry["dispatch"],
                "before_state": lifecycle["source_state"],
                "after_state": lifecycle["source_state"],
                "source_capture": capture,
                "workspace_before": [],
                "workspace_after": [
                    {"path": artifact["path"], "digest": artifact["artifact_digest"], "snapshot_mode": "content-sha256-v1", "status": "outside-repository"}
                    for artifact in original["artifacts"]
                ],
            }
            content, metadata = compile_validation(
                {"dispatch": dispatch, "payload": {key: original[key] for key in ("status", "executions", "artifacts")} | {"limitations": []}}
            )
            Path(entry["artifact_path"]).write_bytes(content)
            Path(entry["metadata_path"]).write_text(json.dumps(metadata))
            source = {key: entry[key] for key in ("artifact_path", "metadata_path")}
            append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
            sources.append(source)
            assert "captured_doi_inputs" in metadata["normalized_record"]
            assert metadata["source_capture"] == capture
        else:
            sources.append(_compile_repair_fixture_entry(entry, lifecycle, journal))
    for entry in dispatches["dispatches"]:
        if entry["dispatch"].get("mode") != "synthesis":
            continue
        bundle = build_synthesis_bundle({**lifecycle, "sources": sources})
        payload = _synthesis_payload(entry["dispatch"], bundle)
        payload["validation_reconciliation"][0]["scholarly_doi_resolution"] = resolution
        content, metadata = compile_review(
            {
                "dispatch": {
                    **entry["dispatch"],
                    "before_state": lifecycle["source_state"],
                    "after_state": lifecycle["source_state"],
                    "synthesis_bundle": bundle,
                },
                "payload": payload,
            }
        )
        Path(entry["artifact_path"]).write_bytes(content)
        Path(entry["metadata_path"]).write_text(json.dumps(metadata))
        source = {key: entry[key] for key in ("artifact_path", "metadata_path")}
        append_journal_event(journal, lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
        sources.append(source)
    output = tmp_path / "final.json"
    command = [
        "finalize-proof",
        "--input",
        str(lifecycle_path),
        "--journal",
        str(journal),
        "--dispatches",
        str(dispatch_path),
        "--current-capture",
        str(capture_path),
        "--output",
        str(output),
    ]
    assert main(command) == 0
    final = json.loads(output.read_bytes())
    assert final["repository_validation_status"] == "failed"
    assert final["repository_readiness"] == "ready"
    assert final["scholarly_doi_resolutions"][0]["result"] == "failed"
    Path(resolution["checks"][0]["occurrences"][0]["primary_record"]["path"]).write_text("altered primary evidence")
    assert main([*command[:-1], str(tmp_path / "tampered-final.json")]) == 2
