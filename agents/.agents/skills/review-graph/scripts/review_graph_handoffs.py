"""Executable validator observations bound to the node's publication contract."""

import shlex
from pathlib import Path
from typing import Any

from review_graph_session import runtime_command


def audit_observations(dispatch: dict[str, Any], contract: Path) -> dict[str, Any]:
    """Give framework captures immutable destinations without shell redirection."""
    prefix = runtime_command(Path(__file__).with_name("capture_scope.py"))
    words = shlex.split(dispatch["state_verification_command"])
    if words[: len(prefix)] != prefix:
        return {}
    return {
        phase: {
            "capture_path": str(path),
            "receipt_path": str(path.with_suffix(".receipt.json")),
            "capture_command": shlex.join([*words, "--output", str(path)]),
        }
        for phase in ("before", "after")
        for path in (contract.parent / f"{dispatch['node_id']}.{phase}.capture.json",)
    }


def validation_observations(dispatch: dict[str, Any], contract: Path) -> dict[str, Any]:
    """Allocate fresh captures and workspace snapshots in this dispatch generation."""
    result = {}
    for phase in ("before", "after"):
        capture = contract.parent / f"{dispatch['node_id']}.{phase}.capture.json"
        workspace = contract.parent / f"{dispatch['node_id']}.{phase}.workspace.json"
        result[phase] = {
            "capture_path": str(capture),
            "capture_command": dispatch["state_verification_command"] + " > " + shlex.quote(str(capture)),
            "workspace_path": str(workspace),
            "workspace_command": runtime_command(
                Path(__file__).with_name("review_graph_runtime.py"),
                "snapshot-workspace",
                "--input",
                str(contract),
                "--current-capture",
                str(capture),
                "--output",
                str(workspace),
            ),
        }
    return result
