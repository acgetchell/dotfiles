"""Replay review dispatch and publication costs; never simulate model review timing."""

import argparse
import io
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import types
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import Any

import review_graph_runtime as runtime
from research_repo_tools.process import ExecutableNotFoundError, format_exception_diagnostics, run_command_bytes
from review_graph_independent import CHECK_LABELS, render_independent_payload
from review_graph_integrity import digest_bytes
from review_graph_metrics import projected_waves, source_demand
from review_graph_plan import (
    DEFAULT_ROUTING_CATALOG,
    DEFAULT_SKILL_ROOT,
    ValidationRequirement,
    expand_compact_routing,
    independent_nodes_from_routing,
    load_routing_catalog,
    plan_graph,
    review_requirements_from_routing,
    synthesis_nodes_from_routing,
    validate_routing_ledger,
    validation_requirements_from_document,
)

RUNTIME_PATH = Path(runtime.__file__).resolve()
RUNTIME_INPUT_SCHEMA = RUNTIME_PATH.parents[1] / "references/schemas/runtime-operation-inputs-v1.schema.json"
BASELINE_REF = "da0e045d420a890d53a1e0993a0ecdfee5057c72"


def benchmark_fixture(root: Path, *, scale: int = 1) -> dict[str, Any]:
    """Build a scalable mixed-surface fixture, exhaustive routing, and 15 required nodes."""
    if scale < 1:
        msg = "fixture scale must be positive"
        raise ValueError(msg)
    python_paths = [f"src/module_{index}.py" for index in range(6 * scale)] + ["scripts/check.py", "tests/test_check.py"]
    doc_paths = ["README.md", *(f"docs/topic_{index}.md" for index in range(7 * scale))]
    files = {path: f'"""Benchmark source {path}."""\n\ndef normalize(value):\n    return int(value)\n' for path in python_paths}
    files.update({path: f"# {path}\n\nScientific fixture contract: integer input, deterministic output.\n" for path in doc_paths})
    files.update({"justfile": "check:\n    uv run pytest\n", "pyproject.toml": '[project]\nname = "review-benchmark"\nversion = "0.1.0"\n'})
    for path, content in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    identity = digest_bytes(json.dumps(files, sort_keys=True).encode())
    state = [identity, identity, identity]
    surfaces = {
        "repo.tooling": ["justfile", "pyproject.toml", *doc_paths],
        "docs.repository": doc_paths,
        "docs.scientific-software": doc_paths,
        **{f"python.{lens}": python_paths for lens in ("build", "cli", "parse", "scientific", "support-scripts", "tests")},
    }
    validations = [
        asdict(
            ValidationRequirement(
                requirement_id=name,
                captured_paths=tuple(files),
                source_state=(identity, identity, identity),
                commands=(command,) if command else (),
                working_directories=(str(root),) if command else (),
                environment="benchmark host",
                toolchain="fixture",
                features=(),
                platform="hosted matrix" if not command else "current host",
                artifact_owner="repository",
                mutation_lock="serial",
                baseline=index == 0,
                canonical_recipe=command,
                planning_blocker="No hosted commit for staged bytes" if not command else None,
            )
        )
        for index, (name, command) in enumerate((("baseline", "just check"), ("policy", "just ci"), ("hosted", None)))
    ]
    document = {
        "repository_root": str(root),
        "captured_paths": list(files),
        "captured_path_line_bounds": {path: len(content.splitlines()) for path, content in files.items()},
        "source_state": state,
        "concrete_change_target": True,
        "change_target": f"synthetic staged whole-repository {len(files)}-file change",
        "consulted_routers": ["review-graph", "python-review-orchestrator", "docs-review-orchestrator"],
        "execution_profile": "grouped",
        "scope_mode": "staged-only",
        "release_readiness": False,
        "routing_overrides": [
            {
                "catalog_id": catalog_id,
                "disposition": "selected",
                "reason": "fixture exercises this contract",
                "applicability_evidence": ["bounded Python/tooling/scientific docs fixture"],
                "review_surface": paths,
                "owners": [catalog_id.split(".")[0]],
            }
            for catalog_id, paths in surfaces.items()
        ],
        "validation_requirements": json.loads(json.dumps(validations)),
    }
    document["routing_overrides"].extend(
        {"catalog_id": catalog_id, "disposition": "not-applicable", "reason": reason, "applicability_evidence": [reason]}
        for catalog_id, reason in (
            ("docs.citations", "Fixture contains no citations or bibliography"),
            ("docs.rust-api", "Fixture contains no Rust APIs"),
            ("docs.scientific-crate", "Fixture is a Python package with no Cargo/release metadata"),
        )
    )
    # The in-memory planner supports synthetic identities without creating a Git
    # fixture. Production capture and line-bound verification remain untouched.
    catalog = load_routing_catalog(DEFAULT_ROUTING_CATALOG)
    decisions = expand_compact_routing(
        catalog,
        consulted_routers=document["consulted_routers"],
        captured_paths=list(files),
        overrides=document["routing_overrides"],
        change_target=document["change_target"],
    )
    plan = plan_graph(
        review_requirements_from_routing(catalog, decisions),
        validation_requirements_from_document(document, root),
        synthesis_nodes_from_routing(catalog, decisions),
        additional_nodes=independent_nodes_from_routing(catalog, decisions, change_target=document["change_target"]),
        routing_assessment=validate_routing_ledger(catalog, decisions, consulted_routers=document["consulted_routers"]),
        routing_decisions=decisions,
        captured_path_line_bounds=tuple(document["captured_path_line_bounds"].items()),
    )
    return {
        "plan": json.loads(json.dumps(asdict(plan))),
        "source_state": state,
        "repository_root": str(root),
        "authorization": "review-only",
        "state_verification_command": "synthetic fixture identity (no Git operations)",
        "concurrent_worker_limit": 4,
    }


def _baseline_runtime(repository: Path, ref: str, *, schema_store: Path) -> types.ModuleType:
    if not ref or ref.startswith("-"):
        msg = "baseline-ref must be a nonempty Git revision, not an option"
        raise ValueError(msg)
    git = shutil.which("git")
    if git is None:
        msg = "benchmark comparison requires Git to read the baseline runtime"
        raise ValueError(msg)

    def read_revision(path: Path) -> bytes:
        relative = path.relative_to(repository).as_posix()
        try:
            return run_command_bytes(git, ("show", f"{ref}:{relative}"), cwd=repository, check=True, timeout=30).stdout
        except (ExecutableNotFoundError, OSError, subprocess.SubprocessError) as error:
            msg = (
                f"cannot read benchmark baseline {ref}; ensure the revision and its runtime/schema are available locally: {format_exception_diagnostics(error)}"
            )
            raise ValueError(msg) from error

    content = read_revision(RUNTIME_PATH)
    schema_content = read_revision(RUNTIME_INPUT_SCHEMA)
    schema_store.mkdir(parents=True, exist_ok=False)
    schema_path = schema_store / RUNTIME_INPUT_SCHEMA.name
    schema_path.write_bytes(schema_content)
    module = types.ModuleType("review_graph_benchmark_baseline")
    # Share planner/dependencies and skills; each runtime keeps its own public
    # input schema so removed current formats remain historical benchmark data.
    module.__file__ = str(RUNTIME_PATH)
    sys.modules[module.__name__] = module
    exec(compile(content, str(RUNTIME_PATH), "exec"), module.__dict__)  # noqa: S102 - explicitly selected trusted repository revision.
    module.__dict__["_RUNTIME_OPERATION_INPUT_SCHEMA"] = schema_path
    module.__dict__["benchmark_source_digest"] = digest_bytes(content)
    module.__dict__["benchmark_schema_digest"] = digest_bytes(schema_content)
    return module


def _payload(entry: dict[str, Any], ordinal: int) -> dict[str, Any]:
    findings = (
        [
            {
                "severity": "P2",
                "location": entry["dispatch"]["owned_paths"][0] + ":1",
                "summary": f"Seeded regression {ordinal}",
                "evidence": "Synthetic transcript for publication preservation, not a model-discovered defect.",
                "remediation": "Preserve this finding verbatim.",
            }
        ]
        if ordinal < 4
        else []
    )
    return {
        "changes": [],
        "command_policy_attested": True,
        "commands_executed": [],
        "files_inspected": entry["dispatch"]["owned_paths"],
        "findings": findings,
        "handoffs": [],
        "limitations": [],
        "nearby_contract_owners": [],
        "scope_limitations": [],
        "status": "completed" if findings else "no-findings",
        "validation_requirements": [],
    }


def _read_worker_sources(entries: list[dict[str, Any]], repository: Path) -> dict[str, int]:
    reads: list[str] = []
    source_bytes = packet_bytes = 0
    for entry in entries:
        dispatch = entry["dispatch"]
        if dispatch.get("mode") not in {"audit", "independent-review"}:
            continue
        packet: dict[str, Any] = {}
        shared = dispatch.get("shared_inspection_evidence", {})
        if "source_packet_path" in shared:
            content = Path(shared["source_packet_path"]).read_bytes()
            if digest_bytes(content) != shared["source_packet_digest"]:
                msg = "source packet digest mismatch"
                raise ValueError(msg)
            packet_bytes += len(content)
            packet = {item["path"]: item for item in json.loads(content)["excerpts"]}
        for path in dispatch["owned_paths"]:
            excerpt = packet.get(path)
            if excerpt and excerpt["complete"] and digest_bytes(excerpt["text"].encode()) == excerpt["content_digest"]:
                continue
            content = (repository / path).read_bytes()
            reads.append(path)
            source_bytes += len(content)
    return {
        "source_file_reads": len(reads),
        "repeated_source_file_reads": len(reads) - len(set(reads)),
        "source_bytes_read": source_bytes,
        "packet_bytes_read": packet_bytes,
    }


def _independent_replay(module: types.ModuleType, entry: dict[str, Any], state: list[str]) -> dict[str, int]:
    """Replay a known native-label error; counts are scripted, not model retry rates."""
    dispatch = {**entry["dispatch"], "before_state": state, "after_state": state}
    payload = {
        "status": "no-findings",
        "files_inspected": dispatch["planned_paths"],
        "branches": "Synthetic whole-repository staged fixture.",
        "boundary_cases": "Static integer conversion, recipe and documentation inspection only.",
        "tests": "Scripted fixture transcript; no tests executed.",
        "findings": [],
        "no_finding_evidence": [],
        "handoffs": [],
        "before_state": state,
        "after_state": state,
        "source_mutated": False,
        "git_mutated": False,
        "command_policy_attested": True,
        "commands_executed": [],
        "limitations": [],
        "adversarial_checks": [
            {
                "check_id": key,
                "evidence": "Fixture contains only integer conversion, static recipes and prose; no fallback or asynchronous branches.",
                "inspected_paths": dispatch["planned_paths"],
            }
            for key, label in CHECK_LABELS.items()
            if label in dispatch["adversarial_checks"]
        ],
    }
    contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
    attempts = retries = operations = 0

    def publish(content: bytes) -> None:
        nonlocal attempts, operations
        attempts += 1
        if hasattr(module, "publish_worker_payload_bytes"):
            operations += 1
            receipt = module.publish_worker_payload_bytes(contract, content)
        else:
            operations += 1
            approval = module.review_worker_payload_write(contract, content)
            operations += 1
            receipt = module.persist_worker_payload_bytes(contract, content, approval_identity=approval["approval_identity"])
        _verify_publication(receipt, entry, content)

    if entry["result_contract"] == "compact-independent-review":
        publish(json.dumps(payload).encode())
        operations += 1
        native, metadata = module.compile_independent_payload({"dispatch": dispatch, "payload": payload})
    else:
        # Strip the structured binding for the legacy worker transcript, then
        # change only labels. Substantive observations remain identical.
        correct = (
            b"\n".join(line for line in render_independent_payload(payload, dispatch).splitlines() if not line.startswith(b"- Canonical worker payload:"))
            + b"\n"
        )
        malformed = correct.replace(b"- Inspected:", b"- Check:")
        try:
            publish(malformed)
            operations += 1
            module.compile_independent_review({"dispatch": dispatch, "status": "no-findings", "limitations": []}, malformed)
        except ValueError as error:
            if "adversarial" not in str(error):
                raise
            retries += 1
        else:
            msg = "legacy formatting replay unexpectedly accepted missing Inspected labels"
            raise ValueError(msg)
        publish(correct)
        operations += 1
        native, metadata = module.compile_independent_review({"dispatch": dispatch, "status": "no-findings", "limitations": []}, correct)
    Path(entry["artifact_path"]).write_bytes(native)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
    return {"publication_attempts": attempts, "formatting_only_retries": retries, "coordinator_api_operations": operations}


def _verify_publication(receipt: dict[str, Any], entry: dict[str, Any], content: bytes) -> None:
    path = Path(entry["worker_payload_path"])
    if receipt.get("worker_payload_digest") != digest_bytes(content) or receipt.get("worker_payload_path") != str(path.resolve()):
        msg = "benchmark publication receipt does not match the payload digest or dispatch path"
        raise ValueError(msg)
    if path.read_bytes() != content:
        msg = "benchmark publication changed payload bytes"
        raise ValueError(msg)


def _validation_identity_metrics(entries: list[dict[str, Any]]) -> dict[str, Any]:
    embedded: list[bytes] = []
    sidecars: dict[str, int] = {}
    for entry in entries:
        for record in entry["dispatch"].get("command_policy", {}).get("planned_validation_units", []):
            if "execution_identity" in record:
                embedded.append(json.dumps(record["execution_identity"], sort_keys=True, separators=(",", ":")).encode())
            else:
                path = record["execution_identity_reference"]["path"]
                sidecars[path] = Path(path).stat().st_size
    return {
        "embedded_validation_identity_bytes": sum(map(len, embedded)),
        "repeated_validation_identity_bytes": sum(map(len, embedded)) - sum(map(len, set(embedded))),
        "shared_validation_identity_bytes": sum(sidecars.values()),
    }


def _trial(module: types.ModuleType, document: dict[str, Any], store: Path) -> dict[str, Any]:
    started = time.perf_counter()
    input_path, output_path = store.with_suffix(".input.json"), store.with_suffix(".output.json")
    input_path.write_text(json.dumps({**document, "artifact_store": str(store)}), encoding="utf-8")
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        result = module.main(["materialize-dispatches", "--input", str(input_path), "--output", str(output_path)])
    if result != 0:
        msg = "benchmark materialization CLI failed"
        raise ValueError(msg)
    dispatches = json.loads(output_path.read_bytes())
    cli_bytes = len(stdout.getvalue().encode())
    materialize_seconds = time.perf_counter() - started
    entries = dispatches["dispatches"]
    read_started = time.perf_counter()
    reads = _read_worker_sources(entries, Path(document["repository_root"]))
    read_seconds = time.perf_counter() - read_started
    findings: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    operations = 1  # Materialization, followed by actual review/persist/compile API calls.
    publish_started = time.perf_counter()
    for ordinal, entry in enumerate(item for item in entries if item["dispatch"].get("mode") == "audit"):
        payload = _payload(entry, ordinal)
        content = json.dumps(payload).encode()
        contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
        if hasattr(module, "publish_worker_payload_bytes"):
            receipt = module.publish_worker_payload_bytes(contract, content)
            operations += 1
        else:
            review = module.review_worker_payload_write(contract, content)
            receipt = module.persist_worker_payload_bytes(contract, content, approval_identity=review["approval_identity"])
            operations += 2
        _verify_publication(receipt, entry, content)
        receipts.append(receipt)
        dispatch = {**entry["dispatch"], "before_state": document["source_state"], "after_state": document["source_state"]}
        native, metadata = module.compile_review({"dispatch": dispatch, "payload": payload})
        if Path(entry["worker_payload_path"]).read_bytes() != content or metadata["evidence"]["status"] != payload["status"]:
            msg = "benchmark publication changed payload bytes or status"
            raise ValueError(msg)
        Path(entry["artifact_path"]).write_bytes(native)
        Path(entry["metadata_path"]).write_text(json.dumps(metadata), encoding="utf-8")
        findings.extend(metadata["normalized_record"]["findings"])
        operations += 1
    independent = [item for item in entries if item["dispatch"].get("mode") == "independent-review"]
    if len(independent) != 1 or "shared_inspection_evidence" in independent[0]["dispatch"]:
        msg = "benchmark must preserve one conclusion-blind independent dispatch"
        raise ValueError(msg)
    independent_replay = _independent_replay(module, independent[0], document["source_state"])
    manifest = {
        "dispatches": dispatches,
        "receipts": receipts,
        "findings": findings,
        "metrics": {
            "default_cli_output_bytes": cli_bytes,
            "full_result_bytes": output_path.stat().st_size,
            "coordinator_result_bytes": cli_bytes or output_path.stat().st_size,
            "per_worker_input_bytes": {item["node_id"]: Path(item["worker_input_path"]).stat().st_size for item in entries},
            **_validation_identity_metrics(entries),
            "independent_protocol_replay": independent_replay,
            "worker_input_bytes": sum(Path(item["worker_input_path"]).stat().st_size for item in entries),
            "worker_prompt_bytes": sum(len(item["worker_prompt"].encode()) for item in entries),
            "scripted_reads": reads,
            "coordinator_api_operations": operations + independent_replay["coordinator_api_operations"],
            "projected_publication_cli_invocations": sum(1 if "publish_command" in item["dispatch"]["worker_payload_persistence"] else 2 for item in entries),
            "materialize_seconds": materialize_seconds,
            "scripted_read_seconds": read_seconds,
            "publication_and_compile_seconds": time.perf_counter() - publish_started,
            "total_seconds": time.perf_counter() - started,
            "model_review_seconds": None,
        },
    }
    (store / "benchmark-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def run_benchmark(output: Path, *, baseline_ref: str = BASELINE_REF, repeats: int = 5, scale: int = 20) -> dict[str, Any]:
    """Retain paired immutable trials and honest measurements in a new output directory."""
    if repeats < 1:
        msg = "repeats must be positive"
        raise ValueError(msg)
    output.mkdir(parents=True, exist_ok=False)
    document = benchmark_fixture(output / "repository", scale=scale)
    baseline = _baseline_runtime(DEFAULT_SKILL_ROOT.parents[2], baseline_ref, schema_store=output / "baseline-schema")
    trials: dict[str, list[dict[str, Any]]] = {"before": [], "after_": []}
    for index in range(repeats):
        # Alternate first execution to reduce warm-cache ordering bias.
        order = [("before", baseline), ("after_", runtime)]
        for name, module in order if index % 2 == 0 else reversed(order):
            trials[name].append(_trial(module, document, output / f"{name}-{index:03d}"))
        if trials["before"][-1]["findings"] != trials["after_"][-1]["findings"]:
            msg = "baseline/current compiled findings differ"
            raise ValueError(msg)
    nodes = document["plan"]["actual_worker_nodes"]
    report = {
        "schema_version": 1,
        "fixture_source_state": document["source_state"],
        "baseline_ref": baseline_ref,
        "baseline_runtime_digest": baseline.benchmark_source_digest,
        "baseline_input_schema_digest": baseline.benchmark_schema_digest,
        "current_input_schema_digest": digest_bytes(RUNTIME_INPUT_SCHEMA.read_bytes()),
        "current_runtime_digest": digest_bytes(RUNTIME_PATH.read_bytes()),
        "plan": document["plan"],
        "concurrent_worker_limit": 4,
        "projected_waves": projected_waves(nodes, 4),
        "source_demand": source_demand(nodes, Path(document["repository_root"])),
        "seeded_findings_preserved": len(trials["after_"][0]["findings"]),
        "repeats": repeats,
        "results": {
            name.rstrip("_"): {
                "samples": [trial["metrics"] for trial in samples],
                "median_materialize_seconds": statistics.median(trial["metrics"]["materialize_seconds"] for trial in samples),
                "median_total_seconds": statistics.median(trial["metrics"]["total_seconds"] for trial in samples),
            }
            for name, samples in trials.items()
        },
        "limits": "Scripted protocol replay, not a model review. Four-slot waves are projections; nine audit payloads are published and compiled. "
        "One independent transcript is published/compiled with a scripted legacy label error and retry; "
        "validation/synthesis dispatches are not executed. Reads follow complete source packets with direct fallback. "
        "Four seeded findings test preservation, not recall. Current planner/dependencies/skills with each runtime's input schema isolate protocol changes. "
        "Coordinator bytes count stdout, or a full saved-result read when the legacy CLI is silent; actual stdout bytes are reported separately. "
        "No repository checks or Git mutations run. Timings exclude model work and Git baseline loading.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    """Run a paired benchmark without changing source or Git state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New output directory; default is a unique temporary directory")
    parser.add_argument("--baseline-ref", default=BASELINE_REF, help="Trusted local Git revision of the baseline runtime")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--scale", type=int, default=20, help="Mixed whole-repository fixture scale; 20 creates 265 paths")
    args = parser.parse_args(argv)
    output = args.output or Path(tempfile.mkdtemp(prefix="review-workflow-benchmark-")) / "results"
    try:
        run_benchmark(output.resolve(), baseline_ref=args.baseline_ref, repeats=args.repeats, scale=args.scale)
    except (OSError, ValueError) as error:
        print(f"review_graph_benchmark: {error}", file=sys.stderr)
        return 2
    print(output.resolve() / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
