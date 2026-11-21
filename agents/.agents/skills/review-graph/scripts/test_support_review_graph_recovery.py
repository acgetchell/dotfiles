"""Interrupted publication and execution-recovery scenarios for review-graph tests."""

import json
import os
import shlex
import subprocess
import tempfile
import time
from argparse import Namespace
from pathlib import Path
from typing import IO, Any

from review_graph_plan import plan_from_document
from review_graph_runtime import (
    JournalEventRequest,
    append_journal_event,
    capture_workspace_snapshot,
    compile_review,
    compile_validation,
    main,
    materialize_dispatches,
)
from test_support_review_graph import ROUTING_CATALOG, SKILL_ROOT, _json_plan, _sparse_plan_document
from test_support_review_graph_evidence import _compact_audit_payload, _publish_worker_bytes
from test_support_review_graph_lifecycle import _continuation_fixture, _late_validation_requirement
lazy import pytest


def _block_validator(entry: dict[str, Any], lifecycle: dict[str, Any], journal: Path) -> None:
    """Compile a blocked validation result and retain its limitation in the journal."""
    dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
    payload = {"schema_version": 3, "executions": [], "status": "blocked", "limitations": ["uv cache permission denied before checks started"]}
    content, metadata = compile_validation({"dispatch": dispatch, "payload": payload})
    Path(entry["artifact_path"]).write_bytes(content)
    Path(entry["metadata_path"]).write_text(json.dumps(metadata))
    append_journal_event(
        journal,
        lifecycle,
        JournalEventRequest(
            entry["node_id"], "blocked", source={key: entry[key] for key in ("artifact_path", "metadata_path")}, reason=payload["limitations"][0]
        ),
    )


def _recovery_fixture(tmp_path: Path, *, late: bool = False, extra_validator: bool = False) -> tuple[dict[str, Any], Namespace, dict[str, Any]]:
    """Prepare a runnable recovery request and identify the validator it targets."""
    lifecycle, dispatches, paths = _continuation_fixture(tmp_path)
    if extra_validator:
        planning = _sparse_plan_document()
        extra = {**planning["validation_requirements"][0], "requirement_id": "second-validation", "baseline": False, "environment": "second executor"}
        planning["validation_requirements"].append(extra)
        lifecycle["plan"] = _json_plan(
            plan_from_document(planning, catalog_path=ROUTING_CATALOG, skill_roots=(SKILL_ROOT,), repository_root=SKILL_ROOT.parents[2])
        )
        dispatches = materialize_dispatches(
            {
                **lifecycle,
                "artifact_store": str(tmp_path / "two-validators"),
                "authorization": "review-only",
                "repository_root": str(SKILL_ROOT.parents[2]),
                "state_verification_command": "capture_scope.py --mode baseline",
            }
        )
        paths["dispatches"].write_text(json.dumps(dispatches))
    validation = next(entry for entry in dispatches["dispatches"] if entry["result_contract"] == "compact-validation")
    for entry in dispatches["dispatches"]:
        if entry["dispatch"].get("mode") == "audit":
            payload = _compact_audit_payload(entry)
            planned = entry["dispatch"]["command_policy"]["planned_validation_units"][0]
            payload["validation_requirements"] = [
                {
                    "requirement_id": planned["requirement_ids"][0],
                    "planned_validation_digest": planned["planned_validation_digest"],
                    "owner": "review-validator",
                    "reason": "Exercise the dispatch contract",
                    "expected_evidence": "Exact baseline passes",
                }
            ]
            if late:
                payload["validation_requirements"].append(_late_validation_requirement())
            dispatch = {**entry["dispatch"], "before_state": lifecycle["source_state"], "after_state": lifecycle["source_state"]}
            content, metadata = compile_review({"dispatch": dispatch, "payload": payload})
            Path(entry["artifact_path"]).write_bytes(content)
            Path(entry["metadata_path"]).write_text(json.dumps(metadata))
            append_journal_event(
                paths["journal"],
                lifecycle,
                JournalEventRequest(entry["node_id"], "accepted", source={key: entry[key] for key in ("artifact_path", "metadata_path")}),
            )
    _block_validator(validation, lifecycle, paths["journal"])
    request = {
        **lifecycle,
        "artifact_store": str(tmp_path / "recovery"),
        "node_id": validation["node_id"],
        "failure_kind": "cache-access",
        "checks_started": False,
        "reason": "uv failed to open its cache before pytest launched",
        "remedy": "Use an accessible repository-local uv cache",
        "environment": "UV_CACHE_DIR=.uv-cache",
        "permission_change": "none",
    }
    args = Namespace(journal=paths["journal"], dispatches=paths["dispatches"], current_capture=paths["current-capture"])
    return request, args, validation


def _interrupt_recovery_write(monkeypatch: pytest.MonkeyPatch, stage: str, name: str) -> list[Path]:
    """Fail below either direct or atomic publication after writing a prefix."""
    original_open, original_fdopen, original_mkstemp = Path.open, os.fdopen, tempfile.mkstemp
    descriptors: dict[int, Path] = {}
    interrupted: list[Path] = []

    def wrap(stream: IO[Any], path: Path) -> IO[Any]:
        """Instrument the selected destination or its temporary sibling for a short write."""
        target = path.name == name or path.name.startswith(f".{name}.")
        parent = path.parent.name
        selected = parent.startswith("launch-history-") if stage == "history" else parent.startswith("validation-recovered-")
        if target and (selected or stage == "result"):
            write = stream.write

            def fail(content: bytes) -> int:
                """Flush the first 17 bytes to disk before raising the injected write error."""
                write(content[:17])
                stream.flush()
                interrupted.append(path)
                msg = "injected interrupted recovery write"
                raise OSError(msg)

            monkeypatch.setattr(stream, "write", fail)
        return stream

    def open_path(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        """Intercept exclusive binary creation so direct writes use the same injected fault."""
        stream = original_open(path, mode, *args, **kwargs)
        return wrap(stream, path) if mode == "xb" else stream

    def mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        """Associate temporary file descriptors with paths for atomic write fault injection."""
        descriptor, path = original_mkstemp(*args, **kwargs)
        assert isinstance(descriptor, int)
        assert isinstance(path, str)
        descriptors[descriptor] = Path(path)
        return descriptor, path

    def fdopen(descriptor: int, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        """Wrap the binary stream when its descriptor belongs to a tracked temporary file."""
        stream = original_fdopen(descriptor, mode, *args, **kwargs)
        path = descriptors.pop(descriptor, None)
        return wrap(stream, path) if mode == "wb" and path is not None else stream

    monkeypatch.setattr(Path, "open", open_path)
    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(os, "fdopen", fdopen)
    return interrupted


DENIAL = "PermissionError: [Errno 1] Operation not permitted"


def _compile_aggregate(  # noqa: PLR0913 - preserve the exact modeled fault through execution and evidence compilation.
    lifecycle: dict[str, Any], args: Namespace, entry: dict[str, Any], directory: Path, *, permitted: bool, diagnostic: str = DENIAL
) -> dict[str, str]:
    """Run a deterministic executor fault model, then use the real compiler gates."""
    directory.mkdir()
    append_journal_event(args.journal, lifecycle, JournalEventRequest(entry["node_id"], "in-flight"))
    before = capture_workspace_snapshot(entry["dispatch"])
    unit = entry["dispatch"]["validation_unit"]
    preceding = []
    if len(unit["commands"]) > 1:
        started = time.monotonic()
        passed = subprocess.run(  # noqa: S603 - fixture-owned independent command, before the failing aggregate.
            shlex.split(unit["commands"][0]), cwd=unit["working_directories"][0], capture_output=True, check=True
        )
        preceding.append(
            {
                "command": unit["commands"][0],
                "working_directory": unit["working_directories"][0],
                "executor": entry["node_id"],
                "result": "passed",
                "exit_code": passed.returncode,
                "elapsed": f"{time.monotonic() - started}s",
                "evidence": "separate fixture command passed",
                "artifact_paths": [],
            }
        )
    started = time.monotonic()
    run = subprocess.run(  # noqa: S603 - fixture-owned aggregate models a denied capability without requiring actual socket access.
        shlex.split(unit["commands"][-1]),
        cwd=unit["working_directories"][0],
        env={**os.environ, "FIXTURE_SOCKET_ACCESS": "permitted" if permitted else "denied"},
        capture_output=True,
        check=False,
    )
    elapsed = time.monotonic() - started
    output = run.stdout + run.stderr
    assert b"2 checks passed" in output
    assert (b"build completed" in output) == permitted
    log = Path(unit["allowed_artifacts"][0]["path"])
    log.write_bytes(output)
    after = capture_workspace_snapshot(entry["dispatch"])
    status = "passed" if run.returncode == 0 else "failed"
    diagnostic = " ".join(diagnostic.split())
    fault_evidence = f"socket.bind: {diagnostic}" if diagnostic == DENIAL else diagnostic
    limitation = (
        "The modeled executor denied socket binding after checks ran; build was not reached."
        if diagnostic == DENIAL
        else "The modeled executor failed after checks ran; build was not reached."
    )
    payload = {
        "schema_version": 3,
        "status": status,
        "limitations": [] if permitted else [limitation],
        "executions": [
            *preceding,
            {
                "command": unit["commands"][-1],
                "working_directory": unit["working_directories"][0],
                "executor": entry["node_id"],
                "result": status,
                "exit_code": run.returncode,
                "elapsed": f"{elapsed}s",
                "evidence": "2 checks passed; build completed" if permitted else f"2 checks passed; {fault_evidence}; build not reached",
                "artifact_paths": [str(log)],
            },
        ],
    }
    _publish_worker_bytes(entry, json.dumps(payload).encode())
    for phase, snapshot in (("before", before), ("after", after)):
        if lifecycle.get("external_metadata_transitions"):
            snapshot["observed_source_state"] = lifecycle["current_source_state"]
        (directory / f"workspace-{phase}.json").write_text(json.dumps(snapshot))
    lifecycle_path = directory / "lifecycle.json"
    lifecycle_path.write_text(json.dumps(lifecycle))
    assert (
        main(
            [
                "compile-node",
                "--input",
                str(lifecycle_path),
                "--dispatches",
                str(args.dispatches),
                "--journal",
                str(args.journal),
                "--node-id",
                entry["node_id"],
                "--before-capture",
                str(args.current_capture),
                "--after-capture",
                str(args.current_capture),
                "--workspace-before",
                str(directory / "workspace-before.json"),
                "--workspace-after",
                str(directory / "workspace-after.json"),
                "--output",
                str(directory / "compiled.json"),
            ]
        )
        == 0
    )
    return {
        "log_path": str(log),
        "diagnostic": diagnostic,
        "before_capture": str(args.current_capture),
        "after_capture": str(args.current_capture),
        "workspace_before": str(directory / "workspace-before.json"),
        "workspace_after": str(directory / "workspace-after.json"),
    }
