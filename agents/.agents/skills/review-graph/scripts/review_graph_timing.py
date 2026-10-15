"""Bind explicit shell launches and fresh timing receipts before validator dispatch."""

import json
from pathlib import Path
from typing import Any

from review_graph_integrity import canonical_json, digest_bytes
from review_graph_session import runtime_command


def timing_prerequisite(contract_path: Path, node_id: str) -> dict[str, Any]:
    """Describe the operator's remaining shell-policy choice without choosing one."""
    return {
        "manifest_path": str(contract_path.parent / f"{node_id}.timing.json"),
        "prepare_command": runtime_command(
            Path(__file__).with_name("review_graph_runtime.py"),
            "prepare-validation-timing",
            "--input",
            str(contract_path),
            "--shell-policy",
            str(contract_path.parent / f"{node_id}.shell-policy.json"),
        ),
        "policy_shape": {"shell_argv": ["<absolute-execution-tool-shell>", "<exact-invocation-flags>"]},
        "instruction": (
            "Choose the execution tool's exact shell/argv policy, including login/profile flags. "
            "Preparation approves fresh timing artifact paths; execution permissions still apply."
        ),
    }


def timing_documents(dispatch: dict[str, Any], policy: object) -> tuple[dict[Path, bytes], dict[str, Any]]:
    """Construct immutable launches without executing or splitting any command."""
    if dispatch.get("mode") != "validation":
        msg = "timing preparation requires a validator dispatch"
        raise ValueError(msg)
    if not isinstance(policy, dict) or set(policy) != {"shell_argv"}:
        msg = "timing policy requires only shell_argv, explicitly chosen by the operator"
        raise ValueError(msg)
    shell = policy["shell_argv"]
    if not isinstance(shell, list) or not shell or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in shell):
        msg = "shell_argv requires nonempty literal strings"
        raise ValueError(msg)
    if not Path(shell[0]).is_absolute() or not Path(shell[0]).is_file():
        msg = "shell_argv must start with the explicitly chosen absolute execution-tool shell"
        raise ValueError(msg)
    manifest_path = Path(dispatch["timing_prerequisite"]["manifest_path"])
    unit = dispatch["validation_unit"]
    writes: dict[Path, bytes] = {}
    launches = []
    for command, directory in zip(unit["commands"], unit["working_directories"], strict=True):
        if not Path(directory).is_absolute() or not Path(directory).is_dir():
            msg = "timing launch requires an existing absolute dispatched working directory"
            raise ValueError(msg)
        index = len(launches)
        launch_path = manifest_path.with_name(f"{dispatch['node_id']}.timing-{index}.launch.json")
        receipt_path = manifest_path.with_name(f"{dispatch['node_id']}.timing-{index}.receipt.jsonl")
        if receipt_path.exists(follow_symlinks=False):
            msg = "timing receipt already exists; recover its result without rerunning validation"
            raise ValueError(msg)
        launch = {"schema_version": 1, "argv": [*shell, command], "working_directory": directory}
        content = (canonical_json(launch) + "\n").encode()
        writes[launch_path] = content
        launches.append(
            {
                "command": command,
                "working_directory": directory,
                "launch": {"path": str(launch_path), "digest": digest_bytes(content)},
                "receipt_path": str(receipt_path),
                "execute_command": runtime_command(
                    Path(dispatch["skill_path"]).parent / "scripts/run_timed.py", "--input", str(launch_path), "--receipt", str(receipt_path)
                ),
            }
        )
    manifest = {
        "schema_version": 1,
        "node_id": dispatch["node_id"],
        "source_state": dispatch["source_state"],
        "validation_identity": digest_bytes(canonical_json(unit).encode()),
        "policy": policy,
        "launches": launches,
    }
    writes[manifest_path] = (canonical_json(manifest) + "\n").encode()
    return writes, manifest


def timing_blocker(dispatch: dict[str, Any]) -> dict[str, Any] | None:
    """Hold an unstarted validator until its exact timing transport is available."""
    prerequisite = dispatch.get("timing_prerequisite")
    if prerequisite is None:
        return None  # Legacy saved dispatches retain their original protocol.
    path = Path(prerequisite["manifest_path"])
    try:
        if path.resolve() != path:
            msg = "timing manifest must not traverse symlinks"
            raise ValueError(msg)
        manifest = json.loads(path.read_bytes())
        writes, expected = timing_documents(dispatch, manifest["policy"])
        if manifest != expected:
            msg = "timing manifest differs from its bound validator identity"
            raise ValueError(msg)
        for target, content in writes.items():
            if target.resolve() != target or target.read_bytes() != content:
                msg = "timing launch bytes differ from the approved manifest"
                raise ValueError(msg)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"reason": str(error), **prerequisite}
    return None
