"""Executable validator observations bound to the node's publication contract."""

import re
import shlex
from pathlib import Path
from typing import Any

from review_graph_session import runtime_command


def _literal_piece(piece: str) -> str:
    """Remove shell quoting without evaluating expansions."""
    if piece.startswith("'"):
        return piece[1:-1]
    if piece.startswith('"'):
        return re.sub(r'\\(["\\$`])', r"\1", piece[1:-1])
    if piece.startswith("\\"):
        return piece[1:]
    return piece


def _literal_words(command: str) -> list[str]:
    """Accept and decode literal shell pieces without evaluating the command."""
    # Single quotes preserve all bytes; double quotes must not expand variables
    # or commands. Escaped operators are literal, but line continuations are not.
    # Embedded tildes (for example HEAD~1) are literal; leading tildes and
    # assignment-value boundaries remain excluded because shells expand them.
    piece = r"""(?:[^\s'"\\<>|;&()$`*?\[\]{}~#]|(?<=[^\s=:])~|'[^']*'|"(?:[^"\\$`]|\\[^\r\n])*"|\\[^\r\n])"""
    if re.fullmatch(rf"[ \t]*{piece}+(?:[ \t]+{piece}+)*[ \t]*", command) is None:
        msg = "capture must be a literal command without shell operators or expansions"
        raise ValueError(msg)
    return ["".join(_literal_piece(part.group()) for part in re.finditer(piece, word.group())) for word in re.finditer(rf"{piece}+", command)]


def _capture_words(dispatch: dict[str, Any]) -> list[str] | None:
    """Rebind only the frozen capture interface; reject ambiguous shell outputs."""
    prefix = runtime_command(Path(__file__).with_name("capture_scope.py"))
    words = _literal_words(dispatch["state_verification_command"])
    if words[: len(prefix)] != prefix:
        if any(word == "--output" or word.startswith("--output=") for word in words):
            msg = (
                "custom capture command must emit full capture JSON on stdout without --output or shell operators; "
                "correct state_verification_command before materialization"
            )
            raise ValueError(msg)
        return None
    result = list(prefix)
    arguments = iter(words[len(prefix) :])
    for word in arguments:
        if word == "--output":
            if next(arguments, None) is None:
                msg = "capture --output requires a path; correct state_verification_command before materialization"
                raise ValueError(msg)
        elif not word.startswith("--output="):
            result.append(word)
    return result


def audit_observations(dispatch: dict[str, Any], contract: Path) -> dict[str, Any]:
    """Give framework captures immutable destinations without shell redirection."""
    words = _capture_words(dispatch)
    if words is None:
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
    durable = audit_observations(dispatch, contract)
    result = {}
    for phase in ("before", "after"):
        capture = contract.parent / f"{dispatch['node_id']}.{phase}.capture.json"
        workspace = contract.parent / f"{dispatch['node_id']}.{phase}.workspace.json"
        result[phase] = {
            "capture_path": str(capture),
            "capture_command": dispatch["state_verification_command"] + " > " + shlex.quote(str(capture)),
            **durable.get(phase, {}),
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
