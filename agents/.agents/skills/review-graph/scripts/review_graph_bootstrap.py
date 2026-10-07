#!/usr/bin/env python3
"""Merge a capture manifest into one schema-valid review-graph planning input."""

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research_repo_tools.process import ExecutableNotFoundError, format_exception_diagnostics
from review_graph_plan import DEFAULT_ROUTING_CATALOG, DEFAULT_SKILL_ROOT, plan_from_document
from review_graph_receipts import stage_receipt
from review_graph_schema import SchemaValidationError, require_schema, require_schema_definition
from review_graph_starter import STARTER_EXAMPLE, STARTER_SCHEMA, starter_metrics, starter_preflight, starter_template

PLANNING_SCHEMA = Path(__file__).resolve().parents[1] / "references" / "schemas" / "planning-input-v1.schema.json"
RUNTIME_SCHEMA = Path(__file__).resolve().parents[1] / "references" / "schemas" / "runtime-operation-inputs-v1.schema.json"
_SCOPE_MODES = {"baseline": "baseline", "branch": "branch", "staged": "staged-only", "worktree": "changed-file-only"}


def _source_state(capture: dict[str, Any]) -> list[object]:
    return [capture.get("scope_fingerprint"), capture.get("captured_worktree_fingerprint"), capture.get("repository_state_fingerprint")]


def _capture_command(capture: dict[str, Any]) -> str:
    capture_script = Path(__file__).resolve().with_name("capture_scope.py")
    command = [str(Path(sys.executable).absolute()), str(capture_script), "--mode", str(capture.get("capture_mode", "<missing>"))]
    repository_root = capture.get("repository_root")
    if isinstance(repository_root, str) and repository_root:
        command.extend(("--repo", repository_root))
    base_ref = capture.get("base_ref")
    if isinstance(base_ref, str) and base_ref:
        command.extend(("--base", base_ref))
    for path in capture.get("requested_paths", []):
        command.extend(("--path", str(path)))
    return shlex.join(command)


def bootstrap_document(capture: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    """Bind trusted capture fields and validator identities without caller transcription."""
    merged = dict(template)
    capture_mode = capture.get("capture_mode")
    captured_paths = capture.get("captured_scope_paths")
    merged.update(
        {
            "base_ref": capture.get("base_ref"),
            "branch": capture.get("branch"),
            "capture_mode": capture_mode,
            "captured_path_line_bounds": capture.get("captured_path_line_bounds"),
            "captured_paths": captured_paths,
            "captured_scope_paths": captured_paths,
            "captured_worktree_fingerprint": capture.get("captured_worktree_fingerprint"),
            "head": capture.get("head"),
            "merge_base": capture.get("merge_base"),
            "repository_root": capture.get("repository_root"),
            "repository_state_fingerprint": capture.get("repository_state_fingerprint"),
            "requested_paths": capture.get("requested_paths"),
            "scope_fingerprint": capture.get("scope_fingerprint"),
            "source_state": _source_state(capture),
            "status": capture.get("status", []),
            "untracked_paths": capture.get("untracked_paths", []),
        }
    )
    merged.setdefault("authorization", "review-only")
    merged.setdefault("execution_profile", "grouped")
    merged.setdefault("release_readiness", False)
    merged.setdefault("routing_overrides", [])
    merged.setdefault("schema_version", 1)
    if capture_mode in _SCOPE_MODES:
        merged.setdefault("scope_mode", _SCOPE_MODES[capture_mode])
    if capture_mode == "baseline":
        merged.setdefault("concrete_change_target", False)
    elif isinstance(captured_paths, list):
        merged.setdefault("concrete_change_target", bool(captured_paths))

    capture_command = _capture_command(capture)
    raw_requirements = merged.get("validation_requirements", [])
    if isinstance(raw_requirements, list):
        normalized: list[object] = []
        for raw in raw_requirements:
            if not isinstance(raw, dict):
                normalized.append(raw)
                continue
            item = dict(raw)
            item["capture_command"] = capture_command
            item["captured_paths"] = captured_paths
            item["source_state"] = _source_state(capture)
            item.setdefault("allowed_artifacts", [])
            item.setdefault("baseline", False)
            item.setdefault("canonical_recipe", None)
            item.setdefault("evidence_id", None)
            item.setdefault("expected_workspace_effects", [])
            item.setdefault("isolation_root", None)
            item.setdefault("planning_blocker", None)
            item.setdefault("required", True)
            item.setdefault("requires_isolation", False)
            normalized.append(item)
        merged["validation_requirements"] = normalized
    return merged


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        msg = f"JSON root must be an object: {path}"
        raise TypeError(msg)
    return value


def _write_once(path: Path, value: object) -> None:
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            msg = f"refusing to overwrite non-identical bootstrap output: {path}"
            raise ValueError(msg) from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Every graph needs a repository validation requirement with baseline: true. "
            "This marks the repository check, not baseline review scope: a branch just ci unit uses "
            "baseline: true with requested_scope: branch. "
            "For the branch just-ci preset, use --starter-config instead of --input. "
            "Its artifact isolation root contains external cache/log output; requires_isolation=false "
            "keeps execution in the captured checkout. Starter mode runs read-only preflight before returning a dispatch command. "
            f"Starter choices: {STARTER_SCHEMA}; example: {STARTER_EXAMPLE}. "
            f"Field contracts: {PLANNING_SCHEMA}#/$defs/validationRequirement"
        ),
    )
    parser.add_argument("--capture", type=Path, required=True, help="capture_scope.py JSON manifest")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", type=Path, help="compact routing and validation template")
    inputs.add_argument("--starter-config", type=Path, help="explicit operator choices for the branch just-ci preset")
    parser.add_argument("--output", type=Path, required=True, help="immutable normalized planning document")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_ROUTING_CATALOG)
    parser.add_argument("--skill-root", action="append", type=Path)
    parser.add_argument("--full-output", action="store_true", help="print the complete saved bundle instead of a compact receipt")
    return parser


def _starter_preflight(output: dict[str, Any], choices: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    # Import here: runtime also imports bootstrap_document for continuations.
    from review_graph_runtime import preflight_validation  # noqa: PLC0415

    document = starter_preflight(output["plan"], choices, output["planning_input"]["repository_root"])
    report = preflight_validation(document)
    output.update(
        preflight_input=document,
        preflight_report=report,
        starter_metrics=starter_metrics(args.capture, args.starter_config, output["planning_input"], document),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """Normalize, validate, plan, and persist one deterministic bootstrap result."""
    args = _parser().parse_args(argv)
    try:
        capture = _read_object(args.capture)
        choices = _read_object(args.starter_config) if args.starter_config else None
        template = starter_template(capture, choices) if choices is not None else _read_object(args.input)
        document = bootstrap_document(capture, template)
        require_schema(document, PLANNING_SCHEMA)
        root = Path(str(document["repository_root"]))
        plan = plan_from_document(document, catalog_path=args.catalog, skill_roots=tuple(args.skill_root or (DEFAULT_SKILL_ROOT,)), repository_root=root)
        plan_document = json.loads(json.dumps(asdict(plan)))
        source_state = _source_state(document)
        proof_store = args.output.resolve().parent
        materialization_input = {
            "artifact_store": str(proof_store / "artifacts"),
            "authorization": document["authorization"],
            "duplicate_command_authorizations": {},
            "execution_locations": {},
            "inspection_profile": "shared-read-only",
            "plan": plan_document,
            "repository_root": document["repository_root"],
            "routing_catalog_path": str(args.catalog.resolve()),
            "source_state": source_state,
            "state_verification_command": _capture_command(document),
        }
        lifecycle_input = {"plan": plan_document, "source_state": source_state}
        require_schema_definition(materialization_input, RUNTIME_SCHEMA, "materialize-dispatches")
        for operation in ("compile-node", "finalize-proof", "journal-append", "next-ready", "snapshot-workspace"):
            require_schema_definition(lifecycle_input, RUNTIME_SCHEMA, operation)
        output = {
            "capture": capture,
            "lifecycle_input": lifecycle_input,
            "materialization_input": materialization_input,
            "plan": plan_document,
            "planning_input": document,
            "schema_version": 1,
        }
        preflight = _starter_preflight(output, choices, args) if choices is not None else None
        dispatch_ready = plan.dispatch_allowed and (preflight is None or preflight["status"] == "ready")
        _write_once(args.output, output)
        receipt = stage_receipt("bootstrap", args.output, output)
        if preflight is not None:
            receipt.update(
                dispatch_allowed=dispatch_ready,
                preflight_status=preflight["status"],
                blockers=[*plan.blockers, *(blocker for unit in preflight["units"] for blocker in unit["blockers"])],
                starter_metrics=output["starter_metrics"],
            )
        receipt["next_command"] = (
            [
                sys.executable,
                str(Path(__file__).with_name("review_graph_runtime.py").resolve()),
                "materialize-dispatches",
                "--input",
                str(args.output.resolve()),
                "--output",
                str(args.output.resolve().with_suffix(".dispatches.json")),
            ]
            if dispatch_ready
            else None
        )
        receipt["next_operation_inputs"] = {"input": str(args.output.resolve()), "current_capture": str(args.capture.resolve())}
        print(json.dumps(output if args.full_output else receipt, sort_keys=True))
        return 0 if dispatch_ready else 2
    except (ExecutableNotFoundError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        if isinstance(error, SchemaValidationError):
            print(json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
        else:
            print(f"review_graph_bootstrap: {format_exception_diagnostics(error)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
