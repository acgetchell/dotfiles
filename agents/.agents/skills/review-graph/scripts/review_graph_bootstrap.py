#!/usr/bin/env python3
"""Merge a capture manifest into one schema-valid review-graph planning input."""

import argparse
import json
import shlex
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from review_graph_plan import DEFAULT_ROUTING_CATALOG, DEFAULT_SKILL_ROOT, plan_from_document
from review_graph_schema import SchemaValidationError, require_schema

PLANNING_SCHEMA = Path(__file__).resolve().parents[1] / "references" / "schemas" / "planning-input-v1.schema.json"
_SCOPE_MODES = {"baseline": "baseline", "branch": "branch", "staged": "staged-only", "worktree": "changed-file-only"}


def _source_state(capture: dict[str, Any]) -> list[object]:
    return [capture.get("scope_fingerprint"), capture.get("captured_worktree_fingerprint"), capture.get("repository_state_fingerprint")]


def _capture_command(capture: dict[str, Any]) -> str:
    command = ["capture_scope.py", "--mode", str(capture.get("capture_mode", "<missing>"))]
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True, help="capture_scope.py JSON manifest")
    parser.add_argument("--input", type=Path, required=True, help="compact routing and validation template")
    parser.add_argument("--output", type=Path, required=True, help="immutable normalized planning document")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_ROUTING_CATALOG)
    parser.add_argument("--skill-root", action="append", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Normalize, validate, plan, and persist one deterministic bootstrap result."""
    args = _parser().parse_args(argv)
    try:
        document = bootstrap_document(_read_object(args.capture), _read_object(args.input))
        require_schema(document, PLANNING_SCHEMA)
        root = Path(str(document["repository_root"]))
        plan = plan_from_document(document, catalog_path=args.catalog, skill_roots=tuple(args.skill_root or (DEFAULT_SKILL_ROOT,)), repository_root=root)
        output = {"plan": asdict(plan), "planning_input": document, "schema_version": 1}
        _write_once(args.output, output)
        return 0 if plan.dispatch_allowed else 2
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, SchemaValidationError):
            print(json.dumps(error.as_dict(), sort_keys=True), file=sys.stderr)
        else:
            print(f"review_graph_bootstrap: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
