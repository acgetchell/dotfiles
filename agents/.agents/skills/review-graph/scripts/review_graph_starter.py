"""Construct branch and whole-repository release presets from operator choices."""

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from review_graph_plan import (
    DEFAULT_ROUTING_CATALOG,
    DEFAULT_SKILL_ROOT,
    build_routing_projection,
    classify_repository_paths,
    load_routing_catalog,
    validate_isolation_root,
)
from review_graph_receipts import artifact_reference
from review_graph_schema import require_schema, require_schema_definition

REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "references"
STARTER_SCHEMA = REFERENCE_ROOT / "schemas" / "bootstrap-starter-v1.schema.json"
STARTER_EXAMPLE = REFERENCE_ROOT / "bootstrap-starter-v1.json"
RELEASE_EXAMPLE = REFERENCE_ROOT / "baseline-release-starter-v1.json"
RUNTIME_SCHEMA = REFERENCE_ROOT / "schemas" / "runtime-operation-inputs-v1.schema.json"


def starter_template(capture: dict[str, Any], choices: dict[str, Any]) -> dict[str, Any]:
    """Expand choices without inferring authorization, environment, or output policy."""
    require_schema(choices, STARTER_SCHEMA)
    release = choices.get("preset", "branch") == "baseline-release"
    mode = "baseline" if release else "branch"
    if capture.get("capture_mode") != mode or not capture.get("captured_scope_paths"):
        if release:
            msg = "baseline-release requires a nonempty baseline capture; recapture with --mode baseline"
            raise ValueError(msg)
        msg = "the just-ci starter requires a nonempty branch capture; use --input for other scopes"
        raise ValueError(msg)
    if release and capture.get("requested_paths"):
        msg = "baseline-release requires whole-repository capture; remove --path restrictions and recapture with --mode baseline"
        raise ValueError(msg)
    repository = Path(capture["repository_root"])
    root = Path(choices["artifact_root"])
    if not root.is_absolute() or not root.is_dir():
        msg = "starter artifact_root must be an existing absolute directory outside the repository"
        raise ValueError(msg)
    validate_isolation_root(str(root), repository)
    root = root.resolve()
    cache, log = root / "uv-cache", root / "ci.log"
    command = f"{shlex.join(['env', f'UV_CACHE_DIR={cache}', 'just', 'ci'])} > {shlex.quote(str(log))} 2>&1"
    ignored = [{**item, "repository_status": "ignored"} for item in choices["ignored_outputs"]]
    for index, item in enumerate(ignored):
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts or path.as_posix() != item["path"] or item["path"] == ".":
            msg = (
                f"$.ignored_outputs[{index}].path must be repository-relative (for example .pytest_cache); "
                'declare external output in external_artifacts: [{"path": "/tmp/review-proof/validation/cache", "kind": "cache"}]'
            )
            raise ValueError(msg)
    external = [{**item, "repository_status": "outside-repository"} for item in choices.get("external_artifacts", [])]
    for index, item in enumerate(external):
        path = Path(item["path"])
        if not path.is_absolute() or not path.resolve().is_relative_to(root):
            msg = f"$.external_artifacts[{index}].path must be absolute and inside artifact_root; use ignored_outputs for repository-relative outputs"
            raise ValueError(msg)
    instructions = set(choices["instruction_paths"])
    if release and (repository / "AGENTS.md").is_file():
        instructions.add("AGENTS.md")
    return {
        "authorization": choices["authorization"],
        "consulted_routers": choices["consulted_routers"],
        "instruction_paths": sorted(instructions),
        "execution_profile": choices["execution_profile"],
        **(
            {"release_readiness": True}
            if release
            else {"change_target": shlex.join(["git", "diff", capture["merge_base"], "--", *capture["captured_scope_paths"]])}
        ),
        "routing_overrides": choices.get("routing_overrides", []),
        "captured_path_dispositions": choices.get("captured_path_dispositions", []),
        "validation_requirements": [
            {
                "requirement_id": "repository-ci",
                "commands": [command],
                "working_directories": [str(repository)],
                "environment": f"{choices['environment']}; UV_CACHE_DIR={cache}",
                "toolchain": choices["toolchain"],
                "features": choices["features"],
                "platform": choices["platform"],
                "artifact_owner": "repository-ci",
                "mutation_lock": "repository validation outputs; serial",
                "request": f"Validate the captured {mode} with the repository just ci gate",
                "requested_scope": mode,
                "authority": "operator-selected repository baseline",
                "selection_reason": f"required repository baseline gate for this {mode} review",
                "mutation_classification": "declared validation outputs only; no source or Git mutation",
                "expected_evidence": f"just ci exit status, elapsed time, and command output in {log}",
                "elapsed_time_budget": choices["elapsed_time_budget"],
                "dependency_policy": "stop-on-failure",
                "meaningful_skips": [],
                "execution_strategy": "sequential",
                "independence_basis": "one serial repository gate",
                "isolation_root": str(root),
                "requires_isolation": False,
                "expected_workspace_effects": [item["path"] for item in ignored],
                "allowed_artifacts": [
                    {"path": str(cache), "kind": "cache", "repository_status": "outside-repository"},
                    {"path": str(log), "kind": "log", "repository_status": "outside-repository"},
                    *external,
                    *ignored,
                ],
                "canonical_recipe": "just ci",
                "baseline": True,
            }
        ],
    }


def starter_preflight(plan: dict[str, Any], choices: dict[str, Any], repository_root: str) -> dict[str, Any]:
    """Bind operator observations to the planner's actual unit and exact command."""
    units = plan["coalesced_validation_units"]
    document = {
        "plan": plan,
        "repository_root": repository_root,
        "cache_paths": [artifact["path"] for unit in units for artifact in unit["allowed_artifacts"] if artifact["kind"] == "cache"],
        "command_policy": [{"command": command, **choices["command_policy"]} for unit in units for command in unit["commands"]],
        "execution_prerequisites": [{"node_id": unit["node_id"], **choices["execution_prerequisites"]} for unit in units],
    }
    require_schema_definition(document, RUNTIME_SCHEMA, "preflight-validation")
    return document


def starter_metrics(capture_path: Path, choices_path: Path, planning: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    """Measure serialized inputs and operations, without estimating model cost."""
    return {
        "preset": "baseline-release" if planning.get("release_readiness") else "branch",
        "cli_invocations": 1,
        "protocol_operations": ["bootstrap", "preflight-validation"],
        "protocol_operation_count": 2,
        "capture_input_bytes": capture_path.stat().st_size,
        "operator_input_bytes": choices_path.stat().st_size,
        "planning_input_bytes": len(json.dumps(planning, sort_keys=True, separators=(",", ":")).encode()),
        "preflight_input_bytes": len(json.dumps(preflight, sort_keys=True, separators=(",", ":")).encode()),
        "model_tokens": None,
        "provider_cost": None,
    }


def prepare_release(capture: dict[str, Any], artifact_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Discover instructions and routing candidates without inventing semantic decisions."""
    choices = json.loads(RELEASE_EXAMPLE.read_bytes())
    choices["artifact_root"] = str(artifact_root.resolve())
    surfaces = classify_repository_paths(capture["captured_scope_paths"], release_readiness=True)
    routers = {
        "cpp": "cpp-review-orchestrator",
        "rust": "rust-review-orchestrator",
        "python": "python-review-orchestrator",
        "documentation": "docs-review-orchestrator",
    }
    choices["consulted_routers"] = ["review-graph", *(router for surface, router in routers.items() if surface in surfaces)]
    choices["instruction_paths"] = starter_template(capture, choices)["instruction_paths"]
    repository = Path(capture["repository_root"])
    discovered = {
        (parent / "AGENTS.md").as_posix()
        for path in capture["captured_scope_paths"]
        for parent in Path(path).parents
        if (repository / parent / "AGENTS.md").is_file()
    }
    catalog = load_routing_catalog(DEFAULT_ROUTING_CATALOG, skill_roots=(DEFAULT_SKILL_ROOT,))
    return choices, {
        "instruction_paths": sorted(discovered),
        "instruction_policy": (
            "Root instructions are global; nested instructions are discovered per owned or declared dependency path at materialization. "
            "Inspect these instructions for transitive references and declare required instruction_paths explicitly."
        ),
        "routing_projection": build_routing_projection(catalog, consulted_routers=choices["consulted_routers"], captured_paths=capture["captured_scope_paths"]),
        "coverage_policy": (
            "Candidate matches do not assign ownership. Bootstrap reports captured_path_inventory and blocks whole-repository fanout until every "
            "unassigned path has an explicit assessment. Extend leaf review_surface for owned contracts; use captured_path_dispositions for "
            "dependencies, historical/archive files, or explicit user exclusions. Request independent contract coverage_units when justified."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Save reviewable baseline-release operator choices and a bounded discovery view."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset", choices=("baseline-release",))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True, help="existing external validation directory")
    parser.add_argument("--output", type=Path, required=True, help="new operator choices JSON")
    args = parser.parse_args(argv)
    try:
        capture = json.loads(args.capture.read_bytes())
        choices, discovery = prepare_release(capture, args.artifact_root)
        repository = Path(capture["repository_root"]).resolve()
        if args.output.resolve().is_relative_to(repository):
            msg = "starter output must be outside the reviewed repository"
            raise ValueError(msg)
        discovery_path = args.output.with_suffix(".discovery.json")
        for path, document in ((args.output, choices), (discovery_path, discovery)):
            content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
            try:
                with path.open("xb") as stream:
                    stream.write(content)
            except FileExistsError:
                if path.read_bytes() != content:
                    msg = f"refusing to overwrite non-identical starter output: {path}"
                    raise ValueError(msg) from None
        print(
            json.dumps(
                {
                    "operator_choices": artifact_reference(args.output),
                    "discovery": artifact_reference(discovery_path),
                    "operator_operations": 1,
                    "serialized_output_bytes": args.output.stat().st_size + discovery_path.stat().st_size,
                    "model_tokens": None,
                    "provider_cost": None,
                    "next_action": (
                        "Inspect routing candidates and unmatched_captured_paths, supply semantic routing_overrides and captured_path_dispositions, "
                        "confirm authorization, outputs and executor prerequisites, "
                        "then bootstrap --starter-config."
                    ),
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"status": "rejected", "message": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
