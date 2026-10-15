"""Broad audits retain complete provenance through publication and verification."""

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import review_graph_plan as plan
import review_graph_runtime as runtime
from capture_scope import _scope_data
from review_graph_bootstrap import bootstrap_document
from review_graph_integrity import digest_bytes
from test_review_graph_runtime import (
    ROUTING_CATALOG,
    SKILL_ROOT,
    STATE_FIXTURE,
    _captured_rust_repository,
    _compact_independent_payload,
    _compile_cli_paths,
    _json_plan,
    _sparse_plan_document,
    _worker_input_fixture,
)
from test_review_graph_transitions import _payload


@pytest.fixture
def broad_audit(tmp_path: Path) -> dict[str, Any]:
    """Publish 124 concrete external manifests and a complete coverage partition."""
    document, dispatches = _worker_input_fixture(tmp_path)
    entry = next(item for item in dispatches["dispatches"] if item["dispatch"].get("mode") == "audit")
    dependencies = []
    for index in range(124):
        manifest = (
            tmp_path / "external-cache" / "registry" / "src" / "index.crates.io-1949cf8c6b5b557f" / f"scientific-dependency-{index:03d}-0.12.3" / "Cargo.toml"
        )
        manifest.parent.mkdir(parents=True)
        manifest.write_text(f'[package]\nname = "scientific-dependency-{index:03d}"\nversion = "0.12.3"\n')
        dependencies.append(str(manifest))
    dependencies.extend(entry["dispatch"]["required_read_paths"])
    payload = {
        **_payload(entry["dispatch"]["owned_paths"], dispatch=entry["dispatch"]),
        "nearby_contract_owners": dependencies,
        "coverage_units": [
            {
                "unit_id": "build",
                "owned_paths": entry["dispatch"]["owned_paths"],
                "dependency_paths": dependencies,
                "dependency_uncertainty": "",
                "finding_indices": [],
            }
        ],
        "execution_facts": ["validators-not-executed", "source-captures-match", "git-not-mutated"],
    }
    payload_bytes = json.dumps(payload, indent=2).encode()
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    preflight = runtime.review_worker_payload_write(contract, payload_bytes)
    assert not any(Path(entry[key]).exists() for key in ("worker_payload_path", "artifact_path", "metadata_path"))
    receipt = runtime.publish_worker_payload_bytes(contract, payload_bytes)
    lifecycle, dispatch_path, capture = _compile_cli_paths(tmp_path, document, dispatches)
    assert (
        runtime.main(
            [
                "compile-node",
                "--input",
                str(lifecycle),
                "--dispatches",
                str(dispatch_path),
                "--node-id",
                entry["node_id"],
                "--before-capture",
                str(capture),
                "--after-capture",
                str(capture),
                "--journal",
                str(tmp_path / "journal.jsonl"),
                "--output",
                str(tmp_path / "compiled.json"),
            ]
        )
        == 0
    )
    return {
        "source": {key: entry[key] for key in ("artifact_path", "metadata_path")},
        "payload": payload,
        "payload_bytes": payload_bytes,
        "dispatch": {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]},
        "preflight": preflight,
        "receipt": receipt,
    }


def test_broad_audit_compacts_without_changing_provenance(broad_audit: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    source = broad_audit["source"]
    metadata = json.loads(Path(source["metadata_path"]).read_bytes())
    _kind, expectation, evidence, content, record = runtime._load_evidence_source(source, require_normalized=True)
    assert isinstance(record, dict)
    assert isinstance(expectation, runtime.ReviewEvidenceExpectation)
    assert isinstance(evidence, runtime.ReviewEvidence)
    assert record is not None
    assert len(broad_audit["payload"]["nearby_contract_owners"]) == 124 + len(broad_audit["dispatch"]["required_read_paths"])
    assert expectation.canonical_worker_payload == broad_audit["payload"]
    assert runtime._canonical_worker_payload(content, expectation=expectation) == broad_audit["payload"]
    assert Path(metadata["worker_payload_path"]).read_bytes() == broad_audit["payload_bytes"]
    assert record["coverage_units"] == broad_audit["payload"]["coverage_units"]
    scope = content.decode().split("## Scope Inspected\n", 1)[1].split("## Findings\n", 1)[0].strip()
    assert len(scope.encode()) < 2048
    sizes = broad_audit["preflight"]["native_size_preflight"]
    assert sizes["scope_rendering"] == "reference"
    assert sizes["section_byte_counts"]["Scope Inspected"] == len(scope.encode())
    assert sizes["result_byte_count"] == len(content)
    assert max(sizes["section_byte_counts"].values()) <= sizes["section_limit"]
    assert broad_audit["receipt"]["artifact_write_review"]["native_size_preflight"] == sizes

    # Compare against the original inline renderer with only its size cap lifted.
    with monkeypatch.context() as patch:
        patch.setattr(runtime, "MAX_NATIVE_SECTION_BYTES", 1_048_576)
        patch.setattr(plan, "MAX_NATIVE_SECTION_BYTES", 1_048_576)
        inline, inline_metadata = runtime.compile_review({"dispatch": broad_audit["dispatch"], "payload": broad_audit["payload"]})
    inline_metadata = json.loads(json.dumps(inline_metadata))
    assert len(inline) > plan.MAX_NATIVE_SECTION_BYTES
    assert inline_metadata["expectation"]["canonical_worker_payload"] is None
    assert runtime._canonical_worker_payload(inline) == broad_audit["payload"]
    assert inline_metadata["expectation"]["audit_input_identity"] == metadata["expectation"]["audit_input_identity"]
    assert inline_metadata["evidence"]["fingerprints"] == metadata["evidence"]["fingerprints"]
    assert inline_metadata["normalized_record"] == {**record, "artifact_digest": inline_metadata["artifact_digest"]}
    assert not plan._review_native_result_blockers(content, expectation, evidence)


@pytest.mark.parametrize(
    "damage",
    [
        "metadata-missing",
        "payload-missing",
        "dependency",
        "partition",
        "input-identity",
        "normalized",
        "reference",
        "summary",
        "competing-inline",
        "sealed-missing",
        "sealed-changed",
        "sealed-rebound",
    ],
)
def test_broad_audit_rejects_missing_or_changed_bound_evidence(broad_audit: dict[str, Any], damage: str) -> None:  # noqa: C901, PLR0912 - explicit adversarial fixture cases.
    source = broad_audit["source"]
    metadata_path = Path(source["metadata_path"])
    metadata = json.loads(metadata_path.read_bytes())
    artifact = Path(source["artifact_path"])
    native = artifact.read_text()
    if damage == "metadata-missing":
        metadata_path.unlink()
    elif damage == "payload-missing":
        del metadata["expectation"]["canonical_worker_payload"]
    elif damage == "dependency":
        metadata["expectation"]["canonical_worker_payload"]["nearby_contract_owners"][0] += ".changed"
    elif damage == "partition":
        metadata["expectation"]["canonical_worker_payload"]["coverage_units"][0]["dependency_paths"].pop()
    elif damage == "input-identity":
        metadata["expectation"]["audit_input_identity"]["owned_paths"].append("uninspected.rs")
    elif damage == "normalized":
        metadata["normalized_record"]["coverage_units"] = []
    elif damage in {"reference", "summary", "competing-inline"}:
        if damage == "reference":
            native = native.replace(metadata["payload_digest"], "sha256:" + "0" * 64)
        elif damage == "summary":
            count = len(broad_audit["payload"]["nearby_contract_owners"])
            native = native.replace(f"{count} context paths", f"{count - 1} context paths")
        else:
            native = native.replace("## Findings", "- Canonical worker payload: {}\n\n## Findings")
        artifact.chmod(0o644)
        artifact.write_text(native)
        digest = digest_bytes(artifact.read_bytes())
        metadata["artifact_digest"] = metadata["evidence"]["raw_result_digest"] = metadata["normalized_record"]["artifact_digest"] = digest
    else:
        sealed = Path(metadata["worker_payload_path"])
        if damage == "sealed-missing":
            sealed.unlink()
        else:
            replacement = deepcopy(broad_audit["payload"])
            replacement["nearby_contract_owners"].pop()
            data = json.dumps(replacement).encode()
            sealed.chmod(0o644)
            sealed.write_bytes(data)
            if damage == "sealed-rebound":
                metadata["worker_payload_digest"] = digest_bytes(data)
                metadata["worker_payload_byte_count"] = len(data)
    if damage != "metadata-missing":
        metadata_path.chmod(0o644)
        metadata_path.write_text(json.dumps(metadata))
    with pytest.raises((ValueError, OSError), match=r"provenance|payload|normalized record|No such file"):
        runtime._load_evidence_source(source, require_normalized=True)


def test_compact_reference_cannot_verify_without_bound_payload(broad_audit: dict[str, Any]) -> None:
    content = Path(broad_audit["source"]["artifact_path"]).read_bytes()
    with pytest.raises(ValueError, match="bound canonical worker payload"):
        runtime._canonical_worker_payload(content)


@pytest.mark.parametrize("large", [False, True])
def test_independent_instruction_provenance_is_bounded_and_verified(tmp_path: Path, large: bool) -> None:
    capture = _captured_rust_repository(tmp_path)
    repository = Path(capture["repository_root"])
    instruction = repository / "AGENTS.md"
    instruction.write_text("Inspect every source contract.\n" * (3000 if large else 1))
    git = shutil.which("git")
    assert git is not None
    capture = _scope_data(git, repository, "baseline", None, (STATE_FIXTURE,))
    planning = _sparse_plan_document()
    planning.update(change_target=f"git diff -- {STATE_FIXTURE}", concrete_change_target=True, scope_mode="baseline")
    graph = plan.plan_from_document(bootstrap_document(capture, planning), catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=repository)
    document = {
        "plan": _json_plan(graph),
        "repository_root": capture["repository_root"],
        "source_state": [capture[key] for key in ("scope_fingerprint", "captured_worktree_fingerprint", "repository_state_fingerprint")],
        "authorization": "review-only",
        "state_verification_command": "capture_scope.py --mode baseline",
    }
    document["artifact_store"] = str(tmp_path / "independent-proof")
    entries = runtime.materialize_dispatches(document)
    entry = next(item for item in entries["dispatches"] if item["dispatch"]["mode"] == "independent-review")
    payload = _compact_independent_payload(entry["dispatch"])
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    runtime.publish_worker_payload_bytes(contract, json.dumps(payload).encode())
    content, metadata = runtime.compile_independent_payload(
        {"dispatch": {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}, "payload": payload}
    )
    metadata = json.loads(json.dumps(metadata))
    artifact, meta = (Path(entry[key]) for key in ("artifact_path", "metadata_path"))
    artifact.write_bytes(content)
    meta.write_text(json.dumps(metadata))
    source = {"artifact_path": str(artifact), "metadata_path": str(meta)}
    _kind, expectation, evidence, _content, _record = runtime._load_evidence_source(source, require_normalized=True)
    assert isinstance(expectation, runtime.ReviewEvidenceExpectation)
    assert isinstance(evidence, runtime.ReviewEvidence)
    assert expectation.audit_input_identity is not None
    assert dict(expectation.audit_input_identity.retained_inputs)["AGENTS.md"] == instruction.read_text()
    scope = content.decode().split("## Scope Inspected\n", 1)[1].split("\n## ", 1)[0].strip()
    assert len(scope.encode()) <= plan.MAX_NATIVE_SECTION_BYTES
    assert ("Audit input identity reference:" in scope) is large
    assert not plan._review_native_result_blockers(content, expectation, evidence)
    if large:
        reference = json.loads(scope.split("- Audit input identity reference: ", 1)[1])
        damaged = content.replace(reference["digest"].encode(), ("sha256:" + "0" * 64).encode())
        assert plan._scope_provenance_blockers(damaged.decode().split("## Scope Inspected\n", 1)[1].split("\n## ", 1)[0].strip(), expectation)
    identity = metadata["expectation"]["audit_input_identity"]
    identity["retained_inputs"][0][1] += "Tampered instruction."
    meta.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match=r"provenance|canonical payload|identity"):
        runtime._load_evidence_source(source, require_normalized=True)
