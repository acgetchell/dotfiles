"""Capability-specific whole-file contracts across unrelated and relevant repairs."""

import json
import platform
import stat
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import pytest
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_integrity import digest_bytes, digest_json
from review_graph_plan import plan_from_document
from test_review_graph_reuse import _compile_args
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    _baseline_mutation_fixture,
    _complete_structural_fixture_routing,
    _run_test_git,
    _set_fixture_routing,
)
from test_review_graph_transitions import _materialize, _payload

CAPABILITIES = {
    "notebook": ("notebook.py", "docs/contracts/notebook.md"),
    "scientific": ("scientific.py", "docs/contracts/scientific.md"),
    "operations": ("tool.py", "docs/api.md"),
}


def _contract_request(
    tmp_path: Path, *, change: str = "operations", broad: bool = False, uncertain: bool = False
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Capture one audit with two independent capabilities and operational output."""
    tmp_path.mkdir(exist_ok=True)
    git, repository, template, _capture, _plan = _baseline_mutation_fixture(tmp_path)
    files = {
        "notebook.py": "def execute(cell):\n    return cell()\n",
        "scientific.py": "def mean(values):\n    return sum(values) / len(values)\n",
        "tool.py": 'def diagnostic(message):\n    return f"warning: {message}"\n',
        "docs/contracts/notebook.md": "# Notebook execution\n\nCells execute in order in one shared namespace.\n",
        "docs/contracts/scientific.md": "# Scientific calculations\n\nThe mean uses a nonempty sequence of finite values.\n",
        "docs/api.md": (
            "# API\n\n"
            "[Notebook contract](contracts/notebook.md).\n\n"
            "[Scientific contract](contracts/scientific.md).\n\n"
            "## Operational diagnostics\n\nThe diagnostic prefix is warning.\n"
        ),
        "pyproject.toml": '[project]\nname = "contract-fixture"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n',
        "AGENTS.md": "# Instructions\n\nReview each capability against its documented contract.\n",
    }
    for path, content in files.items():
        destination = repository / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    _run_test_git(git, "-C", str(repository), "add", ".")
    _run_test_git(git, "-C", str(repository), "commit", "-m", "independent capability contracts")
    template["consulted_routers"].append("docs-review-orchestrator")
    owned = [path for path, _contract in CAPABILITIES.values()]
    _set_fixture_routing(
        template,
        {
            "catalog_id": "python.cli",
            "disposition": "selected",
            "reason": "Fixture commands expose three independently documented capabilities",
            "applicability_evidence": owned,
            "owners": ["python"],
            "review_surface": owned,
        },
    )
    capture = _scope_data(git, repository, "baseline", None, ())
    _complete_structural_fixture_routing(template, cast("list[str]", capture["captured_scope_paths"]))
    plan = plan_from_document(bootstrap_document(capture, template), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    assert plan.dispatch_allowed, plan.blockers
    lifecycle, entries, _dispatches = _materialize(tmp_path, capture, plan)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["skill_id"] == "python-cli-review")
    payload = {
        **_payload(entry["dispatch"]["owned_paths"]),
        "status": "completed",
        "nearby_contract_owners": ["pyproject.toml", *(contract for _path, contract in CAPABILITIES.values())],
        "findings": [
            {
                "severity": "P2",
                "location": f"{path}:1",
                "summary": f"Missing {capability} failure regression",
                "evidence": "Seeded observation of missing capability-specific failure coverage.",
                "remediation": "Add an independent failure assertion for this contract.",
            }
            for capability, (path, _contract) in CAPABILITIES.items()
        ],
        "coverage_units": [
            {
                "unit_id": capability,
                "owned_paths": [path],
                "dependency_paths": sorted({"pyproject.toml", contract, *(["docs/api.md"] if broad else [])}),
                "dependency_uncertainty": "The notebook may also use operational support policy." if uncertain and capability == "notebook" else "",
                "finding_indices": [ordinal],
            }
            for ordinal, (capability, (path, contract)) in enumerate(CAPABILITIES.items(), start=1)
        ],
    }
    content, metadata = runtime.compile_review(
        {"dispatch": {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}, "payload": payload}
    )
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    changed = {
        **{name: contract for name, (_path, contract) in CAPABILITIES.items()},
        "implementation": "notebook.py",
        "manifest": "pyproject.toml",
        "instructions": "AGENTS.md",
    }
    path = changed.get(change, "docs/contracts/notebook.md")
    if change == "deleted-contract":
        (repository / path).unlink()
    elif change == "manifest":
        (repository / path).write_text(files[path].replace('version = "0.1.0"', 'version = "0.1.1"'), encoding="utf-8")
    elif change == "implementation":
        (repository / path).write_text(files[path].replace("return cell()", "return cell(), None"), encoding="utf-8")
    elif change == "mode":
        (repository / path).chmod((repository / path).stat().st_mode ^ stat.S_IXUSR)
    elif change == "symlink":
        target = tmp_path / "notebook-contract.md"
        target.write_text(files[path], encoding="utf-8")
        (repository / path).unlink()
        (repository / path).symlink_to(target)
    else:
        (repository / path).write_text(files[path] + "\nAdditional contract obligation.\n", encoding="utf-8")
    repaired = _scope_data(git, repository, "baseline", None, ())
    # Removing a document also requires a current routing inventory for its owners.
    captured_paths = set(cast("list[str]", repaired["captured_scope_paths"]))
    for override in template["routing_overrides"]:
        if override.get("review_surface"):
            override["review_surface"] = [item for item in override["review_surface"] if item in captured_paths]
    request = {
        **lifecycle,
        "previous_capture": capture,
        "new_capture": repaired,
        "planning_template": template,
        "authorization_before": "review-only",
        "authorization_after": "review-and-fix",
        "repair_epoch": 1,
        "changed_paths": [path],
        "artifact_store": str(tmp_path / "repair"),
        "state_verification_command": "capture_scope.py --mode baseline",
        "sources": [{key: entry[key] for key in ("artifact_path", "metadata_path")}],
    }
    return request, entry, payload


def _replay_contract_repair(
    tmp_path: Path, request: dict[str, Any], original: dict[str, Any], payload: dict[str, Any], *, fresh_findings: list[dict[str, Any]] | None = None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Publish and verify the new audit, retaining original immutable judgments."""
    original_bytes = {key: Path(original[key]).read_bytes() for key in ("artifact_path", "metadata_path")}
    result = runtime.advance_after_mutation(request)
    audits = [item for item in result["dispatch_set"]["dispatches"] if item["dispatch"]["skill_id"] == "python-cli-review"]
    assert len(audits) == 1
    entry = audits[0]
    decision = next(item for item in result["coverage_reuse_decisions"] if item["node_id"] == entry["node_id"])
    rechecked = {path for unit in decision["units"] if unit["disposition"] == "recheck" for path in unit["owned_paths"]}
    updated = {
        **_payload(sorted(rechecked)),
        "status": "completed",
        "findings": fresh_findings if fresh_findings is not None else [finding for finding in payload["findings"] if finding["location"].split(":")[0] in rechecked],
        "nearby_contract_owners": sorted(
            {path for unit in decision["units"] if unit["disposition"] == "recheck" for path in unit["dependency_paths"] if path != request["changed_paths"][0]}
        ),
    }
    # A changed contract is still an actual dependency when it remains present.
    changed = request["changed_paths"][0]
    if (
        any(changed in unit["dependency_paths"] for unit in decision["units"] if unit["disposition"] == "recheck")
        and (Path(request["new_capture"]["repository_root"]) / changed).is_file()
    ):
        updated["nearby_contract_owners"].append(changed)
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, json.dumps(updated).encode())
    assert runtime.main(_compile_args(result, entry, tmp_path / "compiled.json")) == 0
    record = runtime._load_evidence_source(entry, require_normalized=True)[4]
    assert record is not None
    assert record["files_inspected"] == sorted(rechecked)
    expected_findings = [finding for finding in payload["findings"] if finding["location"].split(":")[0] not in rechecked] + updated["findings"]
    assert len(record["findings"]) == len(expected_findings)
    for expected in expected_findings:
        actual = next(finding for finding in record["findings"] if finding["summary"] == expected["summary"])
        assert {field: actual[field] for field in expected} == expected
    reused_indices = {index for unit in decision["units"] if unit["disposition"] == "reused" for index in unit["finding_indices"]}
    view = entry["dispatch"].get("coverage_reuse")
    if view:
        assert len(view["original_findings"]) == 3
        for index in reused_indices:
            finding = payload["findings"][index - 1]
            retained = next(item for item in record["findings"] if item["summary"] == finding["summary"])
            assert retained["source_findings"] == [
                {"evidence_id": original["dispatch"]["evidence_id"], "finding_id": view["original_findings"][index - 1]["finding_id"]}
            ]
        assert record["coverage_reuse"] == view
    assert {key: Path(original[key]).read_bytes() for key in original_bytes} == original_bytes
    measurement = {
        "materialized_capability_audits": len(audits),
        "publication_calls": 1,
        "compilation_calls": 1,
        "rechecked_paths": len(rechecked),
        "reused_paths": len(entry["dispatch"]["owned_paths"]) - len(rechecked),
        "worker_input_bytes": Path(entry["worker_input_path"]).stat().st_size,
        "coverage_proof_bytes": Path(view["proof_reference"]["path"]).stat().st_size if view else 0,
        "model_worker_launches": 0,
        "provider_tokens": None,
        "provider_cost": None,
        "model_review_seconds": None,
    }
    return decision, record, measurement


@pytest.mark.parametrize("resolved", [True, False], ids=["resolved", "replaced"])
def test_rechecked_capability_reconciles_fresh_findings_with_immutable_history(tmp_path: Path, resolved: bool) -> None:
    request, original, payload = _contract_request(tmp_path, change="operations")
    replacement = {
        "severity": "P3",
        "location": "tool.py:2",
        "summary": "Clarify the repaired diagnostic contract",
        "evidence": "The repaired contract needs an example of its new obligation.",
        "remediation": "Add a current diagnostic example.",
    }
    _decision, record, _measurement = _replay_contract_repair(tmp_path, request, original, payload, fresh_findings=[] if resolved else [replacement])
    assert {finding["summary"] for finding in record["findings"]} == {
        "Missing notebook failure regression",
        "Missing scientific failure regression",
        *([] if resolved else [replacement["summary"]]),
    }
    assert all(finding["summary"] != "Missing operations failure regression" for finding in record["findings"])
    historical = record["coverage_reuse"]["original_findings"]
    assert {field: historical[2][field] for field in payload["findings"][2]} == payload["findings"][2]
    if not resolved:
        fresh = next(finding for finding in record["findings"] if finding["summary"] == replacement["summary"])
        assert {field: fresh[field] for field in replacement} == replacement
        assert "source_findings" not in fresh
        assert record["evidence_id"] != record["coverage_reuse"]["evidence_id"]


@pytest.mark.parametrize("change", ["operations", "notebook", "scientific", "implementation"])
def test_contract_repair_rechecks_only_its_capability_and_preserves_other_findings(tmp_path: Path, change: str) -> None:
    request, original, payload = _contract_request(tmp_path, change=change)
    decision, record, _measurement = _replay_contract_repair(tmp_path, request, original, payload)
    assert {unit["unit_id"]: unit["disposition"] for unit in decision["units"]} == {
        "notebook": "recheck" if change in {"notebook", "implementation"} else "reused",
        "scientific": "recheck" if change == "scientific" else "reused",
        "operations": "recheck" if change == "operations" else "reused",
    }
    assert all(unit["reason"] for unit in decision["units"])
    assert {unit["reason_code"] for unit in decision["units"]} == {"verified", "input-proof-failed"}
    assert [unit["input_changes"] for unit in decision["units"]] == [
        {
            "owned_paths": ["notebook.py"] if change == "implementation" else [],
            "dependency_paths": ["docs/contracts/notebook.md"] if change == "notebook" else [],
        },
        {"owned_paths": [], "dependency_paths": ["docs/contracts/scientific.md"] if change == "scientific" else []},
        {"owned_paths": [], "dependency_paths": ["docs/api.md"] if change == "operations" else []},
    ]
    assert all("input_changes" not in unit for unit in record["coverage_reuse"]["units"])


@pytest.mark.parametrize("change", ["manifest", "instructions"])
def test_shared_manifest_or_instructions_still_require_every_capability_recheck(tmp_path: Path, change: str) -> None:
    request, original, payload = _contract_request(tmp_path, change=change)
    decision, record, measurement = _replay_contract_repair(tmp_path, request, original, payload)
    assert all(unit["disposition"] == "recheck" and unit["reason"] for unit in decision["units"])
    assert "coverage_reuse" not in record
    assert measurement["rechecked_paths"] == 3


def test_uncertain_notebook_dependency_is_rechecked_after_operational_repair(tmp_path: Path) -> None:
    request, original, payload = _contract_request(tmp_path, uncertain=True)
    decision, _record, _measurement = _replay_contract_repair(tmp_path, request, original, payload)
    assert {unit["unit_id"]: unit["disposition"] for unit in decision["units"]} == {"notebook": "recheck", "scientific": "reused", "operations": "recheck"}
    notebook = next(unit for unit in decision["units"] if unit["unit_id"] == "notebook")
    assert notebook["reason_code"] == "dependency-uncertainty"
    assert notebook["reason"] == payload["coverage_units"][0]["dependency_uncertainty"]


def test_deleted_contract_cannot_preserve_its_capability_proof(tmp_path: Path) -> None:
    request, original, payload = _contract_request(tmp_path, change="deleted-contract")
    decision, _record, _measurement = _replay_contract_repair(tmp_path, request, original, payload)
    assert {unit["unit_id"]: unit["disposition"] for unit in decision["units"]} == {"notebook": "recheck", "scientific": "reused", "operations": "reused"}
    assert decision["units"][0]["reason_code"] == "input-proof-failed"
    assert decision["units"][0]["input_changes"] == {"owned_paths": [], "dependency_paths": ["docs/contracts/notebook.md"]}


@pytest.mark.parametrize("change", ["mode", "symlink"])
def test_contract_identity_change_reports_recheck_without_changing_read_bytes(tmp_path: Path, change: str) -> None:
    request, original, payload = _contract_request(tmp_path, change=change)
    path = "docs/contracts/notebook.md"
    contract = Path(request["new_capture"]["repository_root"]) / path
    assert contract.read_bytes() == b"# Notebook execution\n\nCells execute in order in one shared namespace.\n"
    before = request["previous_capture"]["repository_path_fingerprints"]
    after = request["new_capture"]["repository_path_fingerprints"]
    assert before[path] != after[path]
    target = tmp_path / "notebook-contract.md"
    link_value = contract.readlink() if change == "symlink" else None
    decision, record, _measurement = _replay_contract_repair(tmp_path, request, original, payload)
    assert {unit["unit_id"]: unit["disposition"] for unit in decision["units"]} == {"notebook": "recheck", "scientific": "reused", "operations": "reused"}
    assert decision["units"][0]["input_changes"] == {"owned_paths": [], "dependency_paths": [path]}
    assert all("input_changes" not in unit for unit in record["coverage_reuse"]["units"])
    if change == "symlink":
        assert contract.is_symlink()
        assert contract.readlink() == link_value
        assert contract.samefile(target)
    else:
        assert contract.stat().st_mode & stat.S_IXUSR


def _measurement_provenance(snapshots: tuple[Any, Any], dispatch: dict[str, Any]) -> dict[str, Any]:
    """Bind scripted byte measurements to captured inputs and the running toolchain."""
    graph = Path(runtime.__file__).resolve().parents[1]
    scripts = {path.name: digest_bytes(path.read_bytes()) for path in sorted((graph / "scripts").glob("*.py"))}
    schemas = {path.name: digest_bytes(path.read_bytes()) for path in sorted((graph / "references/schemas").glob("*.json"))}
    project = SKILL_ROOT.parents[2]
    return {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "graph_scripts_digest": digest_json(scripts),
        "graph_schemas_digest": digest_json(schemas),
        "routing_catalog_digest": digest_bytes(ROUTING_CATALOG.read_bytes()),
        "fixture_snapshot_digests": {"origin": digest_json(snapshots[0]), "target": digest_json(snapshots[1])},
        "audit_skill": {
            "skill_id": dispatch["skill_id"],
            "skill_digest": digest_bytes(Path(dispatch["skill_path"]).read_bytes()),
            "reference_digests": {Path(path).name: digest_bytes(Path(path).read_bytes()) for path in dispatch["reference_paths"]},
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "research_repo_tools": version("research-repo-tools"),
            "pytest": version("pytest"),
            "pyproject_digest": digest_bytes((project / "pyproject.toml").read_bytes()),
            "uv_lock_digest": digest_bytes((project / "uv.lock").read_bytes()),
        },
    }


def test_broad_vs_capability_dependencies_measure_context_without_inferred_provider_cost(tmp_path: Path) -> None:
    measurements = {}
    snapshots = []
    for strategy in ("broad", "capability"):
        case = tmp_path / strategy
        request, original, payload = _contract_request(case, broad=strategy == "broad")
        snapshots.append((request["previous_capture"]["repository_path_fingerprints"], request["new_capture"]["repository_path_fingerprints"]))
        decision, _record, measurement = _replay_contract_repair(case, request, original, payload)
        measurements[strategy] = measurement
        expected = (
            {"notebook": "recheck", "scientific": "recheck", "operations": "recheck"}
            if strategy == "broad"
            else {"notebook": "reused", "scientific": "reused", "operations": "recheck"}
        )
        assert {unit["unit_id"]: unit["disposition"] for unit in decision["units"]} == expected
    assert snapshots[0] == snapshots[1]
    assert measurements["broad"]["rechecked_paths"] == 3
    assert measurements["capability"]["rechecked_paths"] == 1
    assert all(item["worker_input_bytes"] > 0 for item in measurements.values())
    assert measurements["capability"]["coverage_proof_bytes"] > 0
    report = {
        "fixture": "capability-contract-partitions",
        "measurements": measurements,
        "provenance": _measurement_provenance(snapshots[0], original["dispatch"]),
    }
    assert report["provenance"]["fixture_snapshot_digests"]["origin"] != report["provenance"]["fixture_snapshot_digests"]["target"]
    assert all(report["provenance"]["environment"].values())
    print(json.dumps({**report, "report_digest": digest_json(report)}, sort_keys=True))
