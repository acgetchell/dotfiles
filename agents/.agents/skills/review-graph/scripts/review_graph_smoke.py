"""Exercise native timed validation, payload publication, and final proof on a tiny scripted graph."""

import argparse
import contextlib
import json
import os
import platform
import shlex
import signal
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from review_graph_integrity import digest_bytes
from review_graph_plan import DEFAULT_ROUTING_CATALOG, DEFAULT_SKILL_ROOT, GraphPlan, ValidationRequirement, plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    append_journal_event,
    compile_review,
    compile_validation,
    finalize_proof,
    materialize_dispatches,
    publish_worker_payload_bytes,
)

LIMIT = "Scripted protocol smoke only; no model review, repository readiness assessment, live routing, or cluster support claim."
CONTENT = "pub fn state() -> bool { true }\n"
VALIDATION_TIMEOUT_SECONDS = 30
INTERRUPTION_GRACE_SECONDS = 6


def write_json(path: Path, value: object) -> None:
    """Retain a new fixture artifact without replacing previous evidence."""
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def fixture_plan(repository: Path) -> GraphPlan:
    """Plan one scripted Rust audit, native validation, and required synthesis nodes."""
    identity = digest_bytes(CONTENT.encode())
    command = shlex.join([sys.executable, "-c", "from pathlib import Path; assert Path('state.rs').read_text() == 'pub fn state() -> bool { true }\\n'"])
    requirement = ValidationRequirement(
        requirement_id="smoke-validation",
        source_state=(identity, identity, identity),
        commands=(command,),
        working_directories=(str(repository),),
        environment="native offline protocol fixture",
        toolchain=f"Python {platform.python_version()}",
        features=(),
        platform=f"{sys.platform}-{platform.machine()}",
        artifact_owner="validator",
        mutation_lock="fixture read-only",
        requested_scope="baseline",
        capture_command="digest fixture bytes",
        captured_paths=("state.rs",),
        baseline=True,
        canonical_recipe=command,
        elapsed_time_budget="30s",
    )
    return plan_from_document(
        {
            "captured_paths": ["state.rs"],
            "captured_path_line_bounds": {"state.rs": 1},
            "source_state": [identity] * 3,
            "concrete_change_target": False,
            "consulted_routers": ["review-graph", "rust-review-orchestrator"],
            "execution_profile": "grouped",
            "release_readiness": False,
            "scope_mode": "baseline",
            "routing_overrides": [
                {
                    "catalog_id": "rust.invariants",
                    "disposition": "selected",
                    "owners": ["rust"],
                    "review_surface": ["state.rs"],
                    "reason": "scripted state fixture",
                    "applicability_evidence": [LIMIT],
                }
            ],
            "validation_requirements": [json.loads(json.dumps(asdict(requirement)))],
        },
        catalog_path=DEFAULT_ROUTING_CATALOG,
        skill_roots=(DEFAULT_SKILL_ROOT,),
        repository_root=repository,
    )


def stop_validation(process: subprocess.Popen[bytes]) -> None:
    """Let the timing helper record interruption, then remove surviving group members."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=INTERRUPTION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def run_validation(argv: list[str]) -> int:
    """Own the Linux/macOS validation process group through deadline and cancellation."""
    if os.name != "posix":
        msg = "Timed graph smoke requires POSIX process groups on Linux/macOS."
        raise ValueError(msg)
    with subprocess.Popen(argv, start_new_session=True) as process:  # noqa: S603 - fixed timing helper and fixture command.
        try:
            return process.wait(timeout=VALIDATION_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired, KeyboardInterrupt:
            stop_validation(process)
            raise


def validation_payload(entry: dict[str, Any], output: Path) -> dict[str, Any]:
    """Execute the planned command through the portable timing helper with a hard bound."""
    unit = entry["dispatch"]["validation_unit"]
    argv = shlex.split(unit["commands"][0])
    launch = output / "validation-launch.json"
    receipt = output / "validation-timing.jsonl"
    write_json(launch, {"schema_version": 1, "argv": argv, "working_directory": unit["working_directories"][0]})
    timing = DEFAULT_SKILL_ROOT / "review-validator/scripts/run_timed.py"
    try:
        code = run_validation([sys.executable, str(timing), "--input", str(launch), "--receipt", str(receipt)])
    except subprocess.TimeoutExpired:
        write_json(
            output / "validation-timeout.json",
            {
                "status": "timed-out",
                "deadline_seconds": VALIDATION_TIMEOUT_SECONDS,
                "cleanup_grace_seconds": INTERRUPTION_GRACE_SECONDS,
                "timing_receipt": str(receipt),
            },
        )
        msg = "Native smoke validation exceeded its deadline; interruption evidence retained."
        raise ValueError(msg) from None
    events = [json.loads(line) for line in receipt.read_text().splitlines()]
    finished = events[-1]
    if code != 0 or finished["status"] != "completed" or finished["exit_code"] != 0:
        msg = "Native smoke validation failed; no successful graph proof will be claimed."
        raise ValueError(msg)
    return {
        "artifacts": [],
        "executions": [
            {
                "artifact_paths": [],
                "command": unit["commands"][0],
                "elapsed": f"{finished['elapsed_seconds']:.9f}s",
                "evidence": f"Native timing receipt: {receipt}; fixture contents verified.",
                "executor": entry["node_id"],
                "exit_code": finished["exit_code"],
                "result": "passed",
                "working_directory": unit["working_directories"][0],
            }
        ],
        "limitations": [],
        "status": "passed",
    }


def review_payload(entry: dict[str, Any], plan: GraphPlan) -> dict[str, Any]:
    """Build explicitly scripted observations and reconcile the fixture predecessors."""
    dispatch = entry["dispatch"]
    payload: dict[str, Any] = {
        "changes": [],
        "command_policy_attested": True,
        "commands_executed": [],
        "files_inspected": ["state.rs"],
        "findings": [],
        "handoffs": [],
        "limitations": [],
        "scope_limitations": [],
        "nearby_contract_owners": [],
        "status": "no-findings",
        "validation_requirements": [],
    }
    if dispatch["mode"] == "synthesis":
        requirements = {
            f"{'validation' if node.mode == 'validation' else 'review'}:{node.node_id}": list(node.requirement_ids) for node in plan.actual_worker_nodes
        }
        platforms = {f"validation:{unit.node_id}": unit.platform for unit in plan.coalesced_validation_units}
        payload.update(
            readiness_verdict="ready",
            verdict_reasons=["Scripted fixture evidence reconciles; this verdict applies only to the synthetic fixture."],
            predecessor_coverage=[
                {"evidence_id": key, "requirement_ids": requirements[key], "disposition": "accepted"} for key in dispatch["predecessor_evidence_ids"]
            ],
            routing_closure={"complete": True, "unresolved_handoff_ids": [], "user_excluded_catalog_ids": []},
            validation_reconciliation=[
                {"evidence_id": key, "requirement_ids": requirements[key], "result": "passed", "platform": platforms[key], "execution_mode": "native"}
                for key in dispatch["predecessor_evidence_ids"]
                if key in platforms
            ],
            cross_surface_risks=[],
        )
    return payload


def run_smoke(output: Path) -> dict[str, Any]:
    """Publish immutable worker payloads, compile artifacts, and reload them for final proof."""
    output.mkdir(parents=True, exist_ok=False)
    repository = output / "fixture"
    repository.mkdir()
    (repository / "state.rs").write_text(CONTENT)
    plan = fixture_plan(repository)
    identity = digest_bytes(CONTENT.encode())
    state = [identity] * 3
    lifecycle = {"plan": json.loads(json.dumps(asdict(plan))), "source_state": state}
    write_json(output / "lifecycle.json", lifecycle)
    dispatches = materialize_dispatches(
        {
            **lifecycle,
            "artifact_store": str(output / "evidence"),
            "authorization": "review-only",
            "repository_root": str(repository),
            "state_verification_command": "digest fixture bytes",
        }
    )
    write_json(output / "dispatches.json", dispatches)
    sources = []
    for entry in dispatches["dispatches"]:
        validation = entry["result_contract"] == "compact-validation"
        payload = validation_payload(entry, output) if validation else review_payload(entry, plan)
        contract = json.loads(Path(entry["worker_payload_contract_path"]).read_bytes())
        receipt = publish_worker_payload_bytes(contract, json.dumps(payload).encode())
        write_json(output / f"{entry['node_id']}-publication.json", receipt)
        persisted = json.loads(Path(entry["worker_payload_path"]).read_bytes())
        dispatch = {**entry["dispatch"], "before_state": state, "after_state": state}
        compiler = compile_validation if validation else compile_review
        content, metadata = compiler({"dispatch": dispatch, "payload": persisted})
        Path(entry["artifact_path"]).write_bytes(content)
        write_json(Path(entry["metadata_path"]), metadata)
        source = {"artifact_path": entry["artifact_path"], "metadata_path": entry["metadata_path"], "kind": "validation" if validation else "review"}
        sources.append(source)
        append_journal_event(output / "execution.jsonl", lifecycle, JournalEventRequest(entry["node_id"], "accepted", source=source))
    current = digest_bytes((repository / "state.rs").read_bytes())
    request = {**lifecycle, "sources": sources, "current_source_state": [current] * 3}
    write_json(output / "final-request.json", request)
    final = finalize_proof(request)
    write_json(output / "final-proof.json", final)
    if final["graph_proof_status"] != "complete" or final["repository_validation_status"] != "passed":
        msg = "Smoke proof incomplete; inspect retained evidence."
        raise ValueError(msg)
    write_json(output / "smoke.json", {"status": "passed", "limit": LIMIT, "model_review": False, "proof": str(output / "final-proof.json")})
    return final


def main(argv: list[str] | None = None) -> int:
    """Run a bounded, offline smoke fixture without changing repository Git state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New artifact directory")
    args = parser.parse_args(argv)
    try:
        run_smoke(args.output.resolve())
    except (OSError, ValueError, subprocess.SubprocessError) as error:  # fmt: skip
        print(f"review_graph_smoke: {error}", file=sys.stderr)
        return 2
    print(args.output.resolve() / "final-proof.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
