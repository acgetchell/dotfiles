"""Construct the branch just-ci preset from explicit operator choices."""

import json
import shlex
from pathlib import Path
from typing import Any

from review_graph_plan import validate_isolation_root
from review_graph_schema import require_schema, require_schema_definition

REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "references"
STARTER_SCHEMA = REFERENCE_ROOT / "schemas" / "bootstrap-starter-v1.schema.json"
STARTER_EXAMPLE = REFERENCE_ROOT / "bootstrap-starter-v1.json"
RUNTIME_SCHEMA = REFERENCE_ROOT / "schemas" / "runtime-operation-inputs-v1.schema.json"


def starter_template(capture: dict[str, Any], choices: dict[str, Any]) -> dict[str, Any]:
    """Expand choices without inferring authorization, environment, or output policy."""
    require_schema(choices, STARTER_SCHEMA)
    if capture.get("capture_mode") != "branch" or not capture.get("captured_scope_paths"):
        msg = "the just-ci starter requires a nonempty branch capture; use --input for other scopes"
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
    return {
        "authorization": choices["authorization"],
        "consulted_routers": choices["consulted_routers"],
        "instruction_paths": choices["instruction_paths"],
        "execution_profile": choices["execution_profile"],
        "change_target": f"Captured branch {capture.get('base_ref')}...{capture.get('head')} and captured workspace changes",
        "routing_overrides": choices.get("routing_overrides", []),
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
                "request": "Validate the captured branch with the repository just ci gate",
                "requested_scope": "branch",
                "authority": "operator-selected repository baseline",
                "selection_reason": "required repository baseline gate for this branch review",
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
